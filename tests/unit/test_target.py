import asyncio
import json

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tracefix.evaluation.tasks import ExpectedFact, fact_matches, load_tasks, score_task
from tracefix.persistence.models import Base, ProjectMetadata, TargetCustomer, TargetOrder
from tracefix.target_agent.config import load_agent_config
from tracefix.target_agent.data import load_fixtures, seed_data, snapshot
from tracefix.target_agent.graph import run_target
from tracefix.target_agent.schemas import TargetTask
from tracefix.target_agent.tools import ToolEnvironment, ToolError, calculate


@pytest.fixture
def engine():
    db = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(db)
    seed_data(db)
    yield db
    db.dispose()


def test_seed_counts_idempotence_conflict_atomicity(engine):
    assert seed_data(engine) == 0
    with Session(engine) as session:
        assert len(list(session.scalars(select(TargetOrder)))) == 30
    fixtures = load_fixtures()
    fixtures["customers"].insert(0, {"id": "NEW", "name": "new", "tier": "gold"})
    fixtures["customers"][1]["name"] = "conflict"
    with pytest.raises(ValueError, match="Conflicting fixture"):
        seed_data(engine, fixtures)
    with Session(engine) as session:
        assert session.get(TargetCustomer, "NEW") is None


def test_snapshot_uses_actual_data(engine):
    before = snapshot(engine)
    with Session(engine) as session, session.begin():
        session.get(TargetCustomer, "C001").tier = "changed"
    assert snapshot(engine) != before


def test_query_filters_items_and_read_only_injection(engine):
    tools = ToolEnvironment(engine)
    result = tools.execute("query_records", {"entity": "orders", "filters": {"id": "ORD-010"}}, "q")
    assert result.ok and len(result.data[0]["items"]) == 2
    assert result.source_ids == ["order:ORD-010"]
    assert (
        tools.execute(
            "query_records", {"entity": "orders", "filters": {"sql": "DROP TABLE x"}}, "q"
        ).error
        == "invalid_filter"
    )
    assert (
        tools.execute(
            "query_records", {"entity": "orders", "filters": {"id": "' OR 1=1 --"}}, "q"
        ).error
        == "not_found"
    )
    assert tools.execute("query_records", {"entity": "orders", "limit": 1}, "q").truncated
    assert (
        tools.execute("query_records", {"entity": "orders", "limit": 1000}, "q").error
        == "invalid_arguments"
    )


def test_search_policy_missing_and_provenance(engine):
    tools = ToolEnvironment(engine)
    first = tools.execute(
        "search_documents", {"query": "standard shipping business days", "limit": 1}, "s"
    )
    second = tools.execute(
        "search_documents", {"query": "standard shipping business days", "limit": 1}, "s"
    )
    assert first.data == second.data
    assert first.source_ids == ["policy:SHIP-001"]
    assert first.observation_id != second.observation_id
    assert tools.execute("search_documents", {"query": "zzzzzz"}, "s").data == []
    assert tools.execute("lookup_policy", {"policy_id": "RETURN-000"}, "p").error == "not_found"
    assert (
        tools.execute("lookup_policy", {"policy_id": "../server.env"}, "p").error
        == "invalid_arguments"
    )
    assert tools.execute("shell", {}, "x").error == "unknown_tool"


@pytest.mark.parametrize(
    "expression", ['__import__("os")', "2**100", "1/0", "x+1", "True+1", "[1][0]", "1e100"]
)
def test_calculator_rejects_unsafe_or_invalid_expression(expression):
    with pytest.raises(ToolError):
        calculate(expression)


def test_decimal_calculation():
    assert calculate("0.1 + 0.2") == "0.3"
    assert calculate("(40 * 2) + 15") == "95"
    assert calculate("0e-1000000") == "0"
    with pytest.raises(ToolError):
        calculate("1e-1000000")


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.seen = []

    async def ainvoke(self, messages):
        self.seen.append([m.content for m in messages])
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(messages)
        return response


def call(name, args, identity="call-1"):
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": identity, "type": "tool_call"}]
    )


def final(facts, evidence):
    return AIMessage(
        content=json.dumps({"answer": "Verified answer", "facts": facts, "evidence_ids": evidence}),
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )


def run(engine, responses, **limits):
    model = FakeModel(responses)
    result = asyncio.run(
        run_target(
            TargetTask(task_id="test", prompt="A public question"),
            load_agent_config().model_copy(update=limits),
            tools=ToolEnvironment(engine),
            model=model,
        )
    )
    return result, model


def test_sequential_calls_and_scoring(engine):
    task = load_tasks()[11]
    model = FakeModel(
        [
            call("query_records", {"entity": "orders", "filters": {"id": "ORD-001"}}),
            call("calculator", {"expression": "25*2"}, "call-2"),
            lambda messages: final(
                {"total": "50.00"},
                ["order:ORD-001", json.loads(messages[-1].content)["observation_id"]],
            ),
        ]
    )
    result = asyncio.run(
        run_target(
            task.public_task(), load_agent_config(), tools=ToolEnvironment(engine), model=model
        )
    )
    assert result.status == "completed" and len(result.observations) == 2
    assert score_task(task, result)["success"]
    assert result.input_tokens is None  # Tool-call mock has no usage; no invented zero total.
    assert all("expected_facts" not in str(messages) for messages in model.seen)
    bad = result.model_copy(deep=True)
    bad.answer.facts["total"] = "51.00"
    assert not score_task(task, bad)["success"]
    bad.answer.facts["total"] = "50.00"
    bad.answer.evidence_ids.append("invented")
    assert "unsupported_evidence" in score_task(task, bad)["reasons"]


def test_tool_error_recovery(engine):
    result, _ = run(
        engine,
        [
            call("lookup_policy", {"policy_id": "RETURN-000"}),
            call("lookup_policy", {"policy_id": "RETURN-001"}, "call-2"),
            final({"days": 30}, ["policy:RETURN-001"]),
        ],
    )
    assert result.status == "completed"
    assert result.observations[0].error == "not_found"


@pytest.mark.parametrize(
    "limit,expected",
    [
        ({"max_steps": 1}, "max_steps"),
        ({"max_tool_calls": 1}, "max_tool_calls"),
        ({"max_tool_retries": 0}, "max_tool_retries"),
    ],
)
def test_hard_limits(engine, limit, expected):
    response = call("lookup_policy", {"policy_id": "RETURN-000"})
    result, _ = run(engine, [response] * 5, **limit)
    assert result.terminal_reason == expected


def test_answer_repair_and_fabricated_sources(engine):
    result, _ = run(
        engine,
        [
            call("lookup_policy", {"policy_id": "RETURN-001"}),
            AIMessage(content="not JSON"),
            final({"days": 30}, ["policy:RETURN-001"]),
        ],
    )
    assert result.status == "completed" and result.model_calls == 3
    result, _ = run(engine, [final({"status": "yes"}, ["invented"])] * 2)
    assert result.terminal_reason == "invalid_answer"


def test_truncation_and_model_error(engine):
    result, _ = run(
        engine, [AIMessage(content="partial", response_metadata={"done_reason": "length"})]
    )
    assert result.terminal_reason == "truncated_generation"
    result, _ = run(engine, [ConnectionError("offline")])
    assert result.terminal_reason == "model_unavailable"


def test_timeout(engine):
    class Slow:
        async def ainvoke(self, messages):
            await asyncio.sleep(0.2)

    result = asyncio.run(
        run_target(
            TargetTask(task_id="timeout", prompt="test"),
            load_agent_config().model_copy(update={"timeout_seconds": 0.02}),
            tools=ToolEnvironment(engine),
            model=Slow(),
        )
    )
    assert result.terminal_reason == "timeout"


def test_task_contract_and_independent_fact_rules():
    tasks = load_tasks()
    assert len(tasks) == 20
    assert sum(t.difficulty == "easy" for t in tasks) == 10
    assert sum(t.difficulty == "multi" for t in tasks) == 8
    assert all("expected" not in key for t in tasks for key in t.public_task().model_dump())
    assert fact_matches(ExpectedFact(value="50.00", rule="decimal"), "50.01")
    assert not fact_matches(ExpectedFact(value="50.00", rule="decimal"), "50.02")
    assert not fact_matches(ExpectedFact(value="1", rule="decimal"), True)
    assert not fact_matches(ExpectedFact(value=True, rule="boolean"), "true")
    assert not fact_matches(ExpectedFact(value="1", rule="decimal"), "NaN")
    assert fact_matches(ExpectedFact(value=None, rule="null"), None)


def test_project_metadata_unchanged_by_seed(engine):
    with Session(engine) as session, session.begin():
        session.add(ProjectMetadata(key="keep", value="unchanged"))
    seed_data(engine)
    with Session(engine) as session:
        assert session.get(ProjectMetadata, "keep").value == "unchanged"


def test_ground_truth_matches_committed_business_fixtures():
    from datetime import date
    from decimal import Decimal

    fixtures = load_fixtures()
    orders = {row["id"]: row for row in fixtures["orders"]}
    tasks = {task.task_id: task for task in load_tasks()}
    for task_id, order_id, key in [
        ("T12", "ORD-001", "total"),
        ("T16", "ORD-005", "refund"),
        ("T18", "ORD-010", "total"),
    ]:
        total = sum(
            Decimal(i["unit_price"]) * i["quantity"]
            for i in fixtures["order_items"]
            if i["order_id"] == order_id
        )
        assert total == Decimal(tasks[task_id].expected_facts[key].value)
    for task_id, order_id, reference in [
        ("T11", "ORD-001", "2026-09-11"),
        ("T15", "ORD-004", "2026-09-11"),
        ("T17", "ORD-008", "2026-09-17"),
    ]:
        order = orders[order_id]
        age = (date.fromisoformat(reference) - date.fromisoformat(order["delivered_on"])).days
        eligible = order["condition"] == "unused" and 0 <= age <= 30
        assert tasks[task_id].expected_facts["eligible"].value is eligible
    assert "ORD-999" not in orders


def test_injected_failure_is_labelled_and_recoverable(engine):
    env = ToolEnvironment(engine, injected_errors={"lookup_policy": 1})
    first = env.execute("lookup_policy", {"policy_id": "RETURN-001"}, "a")
    second = env.execute("lookup_policy", {"policy_id": "RETURN-001"}, "b")
    assert env.injected and first.error == "injected_unavailable" and second.ok


def test_unexpected_tool_failure_becomes_observation(engine, monkeypatch):
    tools = ToolEnvironment(engine)

    def broken(args):
        raise RuntimeError("private exception details")

    monkeypatch.setattr(tools, "calculator", broken)
    result = tools.execute("calculator", {"expression": "1+1"}, "a")
    assert result.error == "internal_tool_error"
    assert "private exception" not in result.model_dump_json()


def test_missing_database_schema_produces_failed_run():
    empty = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    try:
        result, model = run(empty, [])
        assert result.terminal_reason == "data_source_unavailable"
        assert result.data_hash is None and not model.seen
    finally:
        empty.dispose()


def test_repair_cannot_execute_new_tools(engine):
    result, _ = run(
        engine, [AIMessage(content="not json"), call("calculator", {"expression": "1+1"})]
    )
    assert result.terminal_reason == "invalid_answer"
    assert not result.observations
    assert result.messages[-1]["tool_call_id"] == "call-1"


def test_evaluation_continues_after_infrastructure_failure(engine, tmp_path, monkeypatch):
    from tracefix.common.config import Settings
    from tracefix.evaluation import runner

    tasks = load_tasks()[:2]
    valid, _ = run(
        engine,
        [
            call("query_records", {"entity": "customers", "filters": {"id": "C001"}}),
            final({"tier": "gold"}, ["customer:C001"]),
        ],
    )
    calls = []

    async def fake_run(task, config, **kwargs):
        calls.append(task.task_id)
        assert set(task.model_dump()) == {"task_id", "prompt"}
        if task.task_id == "T01":
            raise ConnectionError("private connection detail")
        return valid.model_copy(update={"task_id": "T02"})

    monkeypatch.setattr(runner, "run_target", fake_run)
    result = asyncio.run(
        runner.evaluate(tasks, load_agent_config(), Settings(_env_file=None), engine, tmp_path)
    )
    assert calls == ["T01", "T02"]
    assert result["complete"] and result["passed"] == 1
    assert result["success_rate"] == 0.5
    assert result["agent_version_id"] == "test"
    assert result["evaluator_version"] == "order-support-scorer-v1"
    assert result["metrics"]["failed"] == 1
    assert result["metrics"]["model_calls"] == valid.model_calls
    assert "private connection detail" not in (tmp_path / "summary.json").read_text()
