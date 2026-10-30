import asyncio
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tracefix.common.config import Settings
from tracefix.persistence.models import Base, TargetRun
from tracefix.target_agent.data import seed_data
from tracefix.target_agent.graph import run_target
from tracefix.target_agent.schemas import TargetTask
from tracefix.target_agent.tools import ToolEnvironment
from tracefix.targets.target_a.baseline import load_agent_version
from tracefix.targets.target_a.observed import run_observed
from tracefix.telemetry.provider import (
    InMemoryTraceProvider,
    LangfuseTraceProvider,
    TelemetryUnavailable,
)
from tracefix.telemetry.recording import JudgeRecorder, TelemetrySession, judge_metadata
from tracefix.telemetry.redaction import sanitize


class FakeModel:
    def __init__(self):
        self.step = 0

    async def ainvoke(self, messages, config=None):
        self.step += 1
        if self.step == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_policy",
                        "args": {"policy_id": "RETURN-001"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )
        return AIMessage(
            content=json.dumps(
                {
                    "answer": "30 days",
                    "facts": {"days": 30},
                    "evidence_ids": ["policy:RETURN-001"],
                }
            ),
            usage_metadata={"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
        )


@pytest.fixture
def engine():
    db = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(db)
    seed_data(db)
    yield db
    db.dispose()


def test_observed_wrapper_preserves_a0_result_and_indexes_identity(engine, tmp_path):
    version = load_agent_version()
    version.verify_current_files()
    task = TargetTask(task_id="T02", prompt="What is the return period?")
    settings = Settings(_env_file=None)
    raw = asyncio.run(
        run_target(task, version.agent_config, tools=ToolEnvironment(engine), model=FakeModel())
    )
    metadata = {
        "target_id": "target-a",
        "agent_version_id": "target-a:a0",
        "benchmark_snapshot_id": "target-a-order-support-v1",
        "dataset_version": "order-support-dataset-v1",
        "split": "development",
    }
    observed = asyncio.run(
        run_observed(
            task,
            version.agent_config,
            tools=ToolEnvironment(engine),
            settings=settings,
            metadata=metadata,
            output=tmp_path,
            telemetry=TelemetrySession(settings),
            model=FakeModel(),
        )
    )
    assert observed.result.status == raw.status == "completed"
    assert observed.result.answer == raw.answer
    assert observed.result.model_calls == raw.model_calls == 2
    assert [o.tool for o in observed.result.observations] == [o.tool for o in raw.observations]
    assert observed.run_file.exists()
    with Session(engine) as session:
        indexed = session.get(TargetRun, observed.result.run_id)
        assert indexed.trace_id is None and indexed.telemetry_status == "disabled"
        assert indexed.agent_version_id == "target-a:a0"
        assert indexed.benchmark_version == "target-a-order-support-v1"


def test_tracing_wrapper_passes_callback_without_changing_target_result(engine, tmp_path):
    class FakeSpan:
        def update(self, **kwargs):
            self.updated = kwargs

    class FakeTelemetry:
        status = "pending"
        secrets = ()

        def trace_id(self):
            return "0" * 32

        def callback(self):
            return object()

        @contextmanager
        def root(self, name, trace_id, metadata, input_data):
            assert trace_id == "0" * 32
            span = FakeSpan()
            yield span
            self.root_output = span.updated

        @contextmanager
        def tool(self, name, args, call_id):
            span = FakeSpan()
            yield span
            self.tool_output = span.updated

    telemetry = FakeTelemetry()
    version = load_agent_version()
    observed = asyncio.run(
        run_observed(
            TargetTask(task_id="T02", prompt="What is the return period?"),
            version.agent_config,
            tools=ToolEnvironment(engine),
            settings=Settings(_env_file=None),
            metadata={
                "target_id": "target-a",
                "agent_version_id": "target-a:a0",
                "dataset_version": "order-support-dataset-v1",
            },
            output=tmp_path,
            telemetry=telemetry,
            model=FakeModel(),
        )
    )
    assert observed.result.status == "completed"
    assert observed.trace_id == "0" * 32
    assert telemetry.root_output["metadata"]["run_id"] == observed.result.run_id
    assert telemetry.tool_output["metadata"]["local_observation_id"].startswith("obs:")
    with Session(engine) as session:
        assert session.get(TargetRun, observed.result.run_id).trace_id == "0" * 32


def test_missing_cloud_credentials_preserve_local_result(engine, tmp_path):
    settings = Settings(langfuse_enabled=True, _env_file=None)
    telemetry = TelemetrySession(settings)
    assert telemetry.status == "unavailable"
    observed = asyncio.run(
        run_observed(
            TargetTask(task_id="T02", prompt="What is the return period?"),
            load_agent_version().agent_config,
            tools=ToolEnvironment(engine),
            settings=settings,
            metadata={
                "target_id": "target-a",
                "agent_version_id": "target-a:a0",
                "dataset_version": "order-support-dataset-v1",
            },
            output=tmp_path,
            telemetry=telemetry,
            model=FakeModel(),
        )
    )
    assert observed.result.status == "completed"
    assert observed.run_file.exists()
    with Session(engine) as session:
        record = session.get(TargetRun, observed.result.run_id)
        assert record.telemetry_status == "unavailable"


def test_recorder_update_failure_preserves_local_result(engine, tmp_path):
    class BrokenSpan:
        def update(self, **kwargs):
            raise RuntimeError("exporter failed")

    class BrokenTelemetry:
        status = "pending"
        secrets = ()

        def trace_id(self):
            return "f" * 32

        def callback(self):
            return None

        @contextmanager
        def root(self, *args):
            yield BrokenSpan()

        @contextmanager
        def tool(self, *args):
            yield BrokenSpan()

    telemetry = BrokenTelemetry()
    observed = asyncio.run(
        run_observed(
            TargetTask(task_id="T02", prompt="What is the return period?"),
            load_agent_version().agent_config,
            tools=ToolEnvironment(engine),
            settings=Settings(_env_file=None),
            metadata={
                "target_id": "target-a",
                "agent_version_id": "target-a:a0",
                "dataset_version": "order-support-dataset-v1",
            },
            output=tmp_path,
            telemetry=telemetry,
            model=FakeModel(),
        )
    )
    assert observed.result.status == "completed"
    assert len(observed.result.observations) == 1
    assert observed.telemetry_status == "unavailable"
    with Session(engine) as session:
        assert session.get(TargetRun, observed.result.run_id).telemetry_status == "unavailable"


def test_recursive_redaction_keeps_diagnostic_content():
    raw = {
        "authorization": "Bearer topsecret",
        "nested": [
            {"db_password": "topsecret", "text": "policy URL https://u:p@example.org/x"},
            "password=hunter2 and Bearer abc123",
        ],
    }
    clean = sanitize(raw, secrets=("hunter2", "topsecret"))
    assert "topsecret" not in str(clean)
    assert "hunter2" not in str(clean)
    assert "u:p@" not in str(clean)
    assert clean["nested"][0]["text"].startswith("policy URL")


def test_langfuse_callback_nests_generation_in_local_exporter():
    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        host="http://127.0.0.1:9",
        span_exporter=exporter,
    )
    try:
        handler = CallbackHandler(public_key="pk-lf-test")

        async def invoke():
            with client.start_as_current_observation(name="tracefix-target-a", as_type="span"):
                await FakeListChatModel(responses=["hello"]).ainvoke(
                    "hi", config={"callbacks": [handler]}
                )

        asyncio.run(invoke())
        client.flush()
        spans = exporter.get_finished_spans()
        assert {span.name for span in spans} == {"tracefix-target-a", "FakeListChatModel"}
        assert len({span.context.trace_id for span in spans}) == 1
    finally:
        client.shutdown()


def fixture_records():
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    base = {
        "target_id": "target-a",
        "task_id": "T02",
        "agent_version_id": "target-a:a0",
        "dataset_version": "order-support-dataset-v1",
        "benchmark_version": "target-a-order-support-v1",
        "model_id": "qwen3:4b",
        "status": "completed",
        "terminal_reason": "completed",
        "telemetry_status": "pending",
        "created_at": now,
        "model_calls": 1,
        "tool_calls": 1,
    }
    runs = [
        {**base, "run_id": "run1", "trace_id": "trace1"},
        {**base, "run_id": "run2", "trace_id": "trace2", "model_calls": 2},
    ]
    observations = []
    for run_id, trace_id in (("run1", "trace1"), ("run2", "trace2")):
        observations.extend(
            [
                {
                    "id": f"{run_id}-root",
                    "traceId": trace_id,
                    "type": "SPAN",
                    "name": "tracefix-target-a",
                    "metadata": {
                        "kind": "target",
                        "run_id": run_id,
                        "target_id": "target-a",
                        "task_id": "T02",
                        "agent_version_id": "target-a:a0",
                        "dataset_version": "order-support-dataset-v1",
                        "model_id": "qwen3:4b",
                        "terminal_reason": "completed",
                        "outcome": "completed",
                        "benchmark_snapshot_id": "target-a-order-support-v1",
                        "expected_model_calls": "1" if run_id == "run1" else "2",
                        "expected_tool_calls": "1",
                    },
                    "startTime": "2026-09-27T00:00:00Z",
                    "endTime": "2026-09-27T00:00:01Z",
                },
                {
                    "id": f"{run_id}-gen",
                    "traceId": trace_id,
                    "type": "GENERATION",
                    "name": "ChatOllama",
                    "model": "qwen3:4b",
                    "parentObservationId": f"{run_id}-root",
                    "startTime": "2026-09-27T00:00:00Z",
                    "endTime": "2026-09-27T00:00:01Z",
                    "inputUsage": 10,
                    "outputUsage": 5,
                },
                {
                    "id": f"{run_id}-tool",
                    "traceId": trace_id,
                    "type": "TOOL",
                    "name": "lookup_policy",
                    "parentObservationId": f"{run_id}-root",
                    "metadata": {"call_id": "call-1", "local_observation_id": "obs:local"},
                    "output": json.dumps(
                        {
                            "ok": True,
                            "source_ids": ["policy:RETURN-001"],
                            "error": None,
                            "observation_id": "obs:local",
                            "call_id": "call-1",
                        }
                    ),
                    "startTime": "2026-09-27T00:00:00Z",
                    "endTime": "2026-09-27T00:00:01Z",
                },
            ]
        )
    return runs, observations


def test_provider_normalizes_complete_and_partial_traces():
    runs, observations = fixture_records()
    provider = InMemoryTraceProvider(runs, observations)
    summary = provider.get_trace_summary("run1")
    assert summary.telemetry_status == "verified"
    assert summary.metrics.input_tokens == 10
    assert summary.metrics.output_tokens == 5
    assert summary.metrics.latency_ms == 1000
    assert provider.list_tool_calls("run1")[0].local_observation_id == "obs:local"
    assert provider.inspect_observation("run1", "obs:local").observation_id == "run1-tool"
    with pytest.raises(KeyError):
        provider.inspect_observation("run1", "run2-tool")
    assert provider.get_trace_summary("run2").telemetry_status == "incomplete"
    assert provider.get_trace_summary("run2").metrics.input_tokens is None
    assert len(provider.list_runs({"task_id": "T02"})) == 2


def test_provider_redacts_truncates_and_keeps_missing_usage_unknown():
    runs, observations = fixture_records()
    observations[1].pop("inputUsage")
    observations[1].pop("outputUsage")
    observations[1]["input"] = {"authorization": "Bearer secret", "text": "x" * 5000}
    provider = InMemoryTraceProvider(runs, observations)
    summary = provider.get_trace_summary("run1")
    assert summary.telemetry_status == "verified"
    assert summary.metrics.input_tokens is None
    assert not summary.metrics.usage_complete
    detail = provider.inspect_observation("run1", "run1-gen")
    assert detail.truncated
    assert "secret" not in detail.input_excerpt

    observations[1]["usageDetails"] = {"input": 0, "output": 5}
    metrics = provider.get_run_metrics("run1")
    assert metrics.input_tokens == 0
    assert metrics.output_tokens == 5

    observations[1]["usageDetails"] = {}
    observations[1].update(inputUsage=0, outputUsage=0)
    assert provider.get_run_metrics("run1").input_tokens is None
    observations[1]["usageDetails"] = {"input": 0, "output": 0}
    assert provider.get_run_metrics("run1").input_tokens == 0


def test_provider_lists_local_runs_during_cloud_outage(engine):
    runs, _ = fixture_records()
    disabled = {**runs[0], "run_id": "local", "trace_id": None, "telemetry_status": "disabled"}
    memory = InMemoryTraceProvider([disabled], [])
    assert memory.list_runs()[0].telemetry_status == "disabled"
    assert memory.list_runs()[0].metrics.tool_errors is None

    with Session(engine) as session, session.begin():
        session.add(TargetRun(**runs[0]))

    def unauthorized(**kwargs):
        raise PermissionError("unauthorized")

    client = SimpleNamespace(
        api=SimpleNamespace(observations=SimpleNamespace(get_many=unauthorized))
    )
    provider = LangfuseTraceProvider(engine, client, request_interval=0)
    with pytest.raises(TelemetryUnavailable):
        provider.get_trace_summary("run1")
    assert provider.list_runs()[0].telemetry_status == "unavailable"


def test_langfuse_provider_reads_all_pages(engine):
    runs, observations = fixture_records()
    pages = iter(
        [
            {"data": observations[:2], "meta": {"cursor": "next"}},
            {"data": observations[2:3], "meta": {"cursor": None}},
        ]
    )
    calls = []

    def get_many(**kwargs):
        calls.append(kwargs)
        return next(pages)

    client = SimpleNamespace(api=SimpleNamespace(observations=SimpleNamespace(get_many=get_many)))
    provider = LangfuseTraceProvider(engine, client, request_interval=0)
    assert len(provider._observations("trace1")) == 3
    assert calls[0]["trace_id"] == "trace1"
    assert calls[1]["cursor"] == "next"
    assert calls[0]["from_start_time"] == calls[1]["from_start_time"]
    assert calls[0]["to_start_time"] == calls[1]["to_start_time"]


@pytest.mark.parametrize(
    "change,issue",
    [
        (lambda rows: rows[1].pop("endTime"), "unfinished_observation"),
        (lambda rows: rows[1].update(parentObservationId="other"), "orphan_observation"),
        (lambda rows: rows[0]["metadata"].update(kind="judge"), "identity_mismatch:kind"),
    ],
)
def test_verifier_rejects_wrong_hierarchy_and_partial_spans(change, issue):
    runs, rows = fixture_records()
    change(rows)
    summary = InMemoryTraceProvider(runs, rows).get_trace_summary("run1")
    assert summary.telemetry_status == "incomplete"
    assert any(issue in entry for entry in summary.verification_issues)


def test_duplicate_observations_do_not_inflate_metrics():
    runs, rows = fixture_records()
    provider = InMemoryTraceProvider(runs, list(reversed(rows)) + [rows[1]])
    assert provider.get_run_metrics("run1").model_calls == 1
    assert provider.get_trace_summary("run1").telemetry_status == "verified"


def test_flush_failure_updates_the_durable_index(engine, tmp_path):
    telemetry = TelemetrySession(Settings(_env_file=None))
    observed = asyncio.run(
        run_observed(
            TargetTask(task_id="T02", prompt="Return period"),
            load_agent_version().agent_config,
            tools=ToolEnvironment(engine),
            settings=Settings(_env_file=None),
            metadata={
                "target_id": "target-a",
                "agent_version_id": "target-a:a0",
                "dataset_version": "order-support-dataset-v1",
            },
            output=tmp_path,
            telemetry=telemetry,
            model=FakeModel(),
        )
    )

    def broken():
        raise ConnectionError("offline")

    telemetry.client = SimpleNamespace(flush=broken, shutdown=lambda: None)
    telemetry.finalize()
    with Session(engine) as session:
        assert session.get(TargetRun, observed.result.run_id).telemetry_status == "unavailable"
    assert observed.run_file.exists()


def test_real_judge_recorder_preserves_identity_and_separate_trace():
    exporter = InMemorySpanExporter()
    session = TelemetrySession(Settings(langfuse_public_key="pk-judge-test", _env_file=None))
    session.client = Langfuse(
        public_key="pk-judge-test",
        secret_key="sk-test",
        base_url="http://127.0.0.1:9",
        span_exporter=exporter,
    )
    recorder = JudgeRecorder(session)
    try:
        with session.root("tracefix-target-a", "a" * 32, {"kind": "target"}, {}):
            with recorder.run(
                judge_run_id="judge",
                mode="generic",
                target_id="target-a",
                source_target_run_id="target",
                manifest_version="v1",
            ) as (tid, span):
                with recorder.diagnostic_tool("inspect-run", {}, "diagnostic-1") as tool:
                    tool.update(output={"status": "failed"})
                recorder.finish(
                    span,
                    diagnosis={"failure_type": "unknown"},
                    fallback_used=False,
                    tokens=5,
                    tool_calls=1,
                    latency_ms=10,
                )
        session.flush()
        spans = exporter.get_finished_spans()
        judge = next(s for s in spans if s.name == "tracefix-judge")
        assert judge.context.trace_id == int(tid, 16) != int("a" * 32, 16)
        assert judge.attributes["langfuse.observation.metadata.mode"] == "generic"
        assert judge.attributes["langfuse.observation.metadata.judge_run_id"] == "judge"
    finally:
        session.shutdown()


@pytest.mark.parametrize("failure", ["enter", "exit", "callback"])
def test_recorder_lifecycle_failures_cannot_change_target_result(engine, tmp_path, failure):
    class Span:
        def update(self, **kwargs):
            pass

    class Client:
        @contextmanager
        def start_as_current_observation(self, **kwargs):
            if failure == "enter":
                raise ConnectionError("offline")
            yield Span()
            if failure == "exit":
                raise ConnectionError("offline")

    telemetry = TelemetrySession(Settings(_env_file=None))
    telemetry.client = Client()

    def callback():
        if failure == "callback":
            raise ConnectionError("offline")
        return None

    telemetry.callback = callback
    observed = asyncio.run(
        run_observed(
            TargetTask(task_id="T02", prompt="Return period"),
            load_agent_version().agent_config,
            tools=ToolEnvironment(engine),
            settings=Settings(_env_file=None),
            metadata={
                "target_id": "target-a",
                "agent_version_id": "target-a:a0",
                "dataset_version": "order-support-dataset-v1",
            },
            output=tmp_path,
            telemetry=telemetry,
            model=FakeModel(),
        )
    )
    assert observed.result.status == "completed"
    assert observed.result.model_calls == 2
    assert len(observed.result.observations) == 1
    assert observed.telemetry_status == "unavailable"


def test_timed_out_tool_is_counted_as_executed_without_changing_a0(engine, tmp_path):
    class SlowTools(ToolEnvironment):
        def execute(self, *args):
            time.sleep(0.1)
            return super().execute(*args)

    observed = asyncio.run(
        run_observed(
            TargetTask(task_id="timeout", prompt="Return period"),
            load_agent_version().agent_config.model_copy(update={"timeout_seconds": 0.05}),
            tools=SlowTools(engine),
            settings=Settings(_env_file=None),
            metadata={
                "target_id": "target-a",
                "agent_version_id": "ad-hoc:timeout",
                "dataset_version": "test",
            },
            output=tmp_path,
            telemetry=TelemetrySession(Settings(_env_file=None)),
            model=FakeModel(),
        )
    )
    assert observed.result.terminal_reason == "timeout"
    assert not observed.result.observations
    with Session(engine) as session:
        assert session.get(TargetRun, observed.result.run_id).tool_calls == 1


def test_hobby_rate_limit_is_retried_but_unauthorized_is_not(engine, monkeypatch):
    class APIError(Exception):
        status_code = 429
        headers = {"Retry-After": "4"}

    calls, delays = [], []

    def get_many(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise APIError()
        return {"data": [], "meta": {}}

    monkeypatch.setattr("tracefix.telemetry.provider.time.sleep", delays.append)
    client = SimpleNamespace(api=SimpleNamespace(observations=SimpleNamespace(get_many=get_many)))
    provider = LangfuseTraceProvider(engine, client, request_interval=0)
    assert provider._observations("trace") == []
    assert len(calls) == 2 and max(delays) > 3
    calls.clear()
    APIError.status_code = 401
    with pytest.raises(TelemetryUnavailable, match="authorization"):
        provider._observations("trace")
    assert len(calls) == 1


def test_verifier_rejects_repeated_cursor_and_foreign_observations(engine):
    client = SimpleNamespace(
        api=SimpleNamespace(
            observations=SimpleNamespace(
                get_many=lambda **kwargs: {"data": [], "meta": {"cursor": "same"}}
            )
        )
    )
    provider = LangfuseTraceProvider(engine, client, request_interval=0)
    with pytest.raises(TelemetryUnavailable, match="repeated"):
        provider._observations("trace")
    runs, rows = fixture_records()
    provider = InMemoryTraceProvider(runs, rows)
    provider._observations = lambda trace_id: rows
    with pytest.raises(TelemetryUnavailable, match="another trace"):
        provider.get_trace_summary("run1")


def test_judge_metadata_and_recorder_are_separate_from_target():
    class FakeSpan:
        def update(self, **kwargs):
            self.output = kwargs

    class FakeSession:
        secrets = ()

        def trace_id(self):
            return "judge-trace"

        @contextmanager
        def root(self, name, trace_id, metadata, input_data):
            self.name, self.metadata = name, metadata
            yield FakeSpan()

        @contextmanager
        def tool(self, name, args, call_id):
            yield FakeSpan()

    session = FakeSession()
    recorder = JudgeRecorder(session)
    with recorder.run(
        judge_run_id="judge-1",
        mode="specialized",
        target_id="target-a",
        source_target_run_id="target-1",
        manifest_version="manifest-1",
    ) as (trace_id, span):
        with recorder.diagnostic_tool("inspect_tool_call", {}, "call-1"):
            pass
        recorder.finish(
            span,
            diagnosis={"failure_type": "unknown"},
            fallback_used=True,
            tokens=20,
            tool_calls=1,
            latency_ms=100.0,
        )
    assert trace_id == "judge-trace"
    assert session.metadata["kind"] == "judge"
    assert session.metadata["source_target_run_id"] == "target-1"
    assert span.output["metadata"]["fallback_used"] == "true"
    with pytest.raises(ValueError):
        judge_metadata(
            judge_run_id="x",
            mode="invalid",
            target_id="target-a",
            source_target_run_id="r",
            manifest_version="m",
        )
