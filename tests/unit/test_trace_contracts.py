"""The same normalized contract against captured Cloud payloads and both providers."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from langfuse.api.observations.types.observations_v2response import ObservationsV2Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tracefix.contracts import TraceProvider
from tracefix.persistence.models import Base, TargetRun
from tracefix.targets.target_a.baseline import load_benchmark_snapshot
from tracefix.telemetry.provider import InMemoryTraceProvider, LangfuseTraceProvider
from tracefix.telemetry.schemas import TraceSummary
from tracefix.telemetry.verification import verify_evaluation

FIXTURES = Path(__file__).parents[1] / "fixtures" / "telemetry"


@pytest.mark.parametrize("name", ["success", "multi_step", "failure"])
def test_captured_cloud_contract(name):
    fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    runs, rows = fixture["runs"], fixture["observations"]
    memory = InMemoryTraceProvider(runs, rows)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        for run in runs:
            session.add(
                TargetRun(**{**run, "created_at": datetime.fromisoformat(run["created_at"])})
            )
    calls = []

    def get_many(**kwargs):
        calls.append(kwargs)
        # Force real SDK response parsing, multiple pages, reverse order, and a repeated row.
        selected = list(reversed(rows))
        page = selected[2:] if kwargs.get("cursor") else selected[:2]
        cursor = None if kwargs.get("cursor") else "next"
        if kwargs.get("cursor"):
            page += selected[:1]
        return ObservationsV2Response.model_validate({"data": page, "meta": {"cursor": cursor}})

    client = SimpleNamespace(api=SimpleNamespace(observations=SimpleNamespace(get_many=get_many)))
    remote = LangfuseTraceProvider(engine, client, request_interval=0)
    expected = TraceSummary.model_validate(fixture["expected_summary"])
    try:
        for provider in (memory, remote):
            assert isinstance(provider, TraceProvider)
            assert provider.get_trace_summary(runs[0]["run_id"]) == expected
            assert provider.get_run_metrics(runs[0]["run_id"]) == expected.metrics
            assert len(provider.list_tool_calls(runs[0]["run_id"])) == expected.metrics.tool_calls
            assert provider.list_runs()[0] == expected
            for observation_id in expected.observation_ids:
                item = provider.inspect_observation(runs[0]["run_id"], observation_id)
                assert item.run_id == expected.run_id
                assert item.trace_id == expected.trace_id
                assert item.observation_id == observation_id
            with pytest.raises(KeyError):
                provider.inspect_observation(runs[0]["run_id"], "foreign-observation")
        assert remote.verify(runs[0]["run_id"]).telemetry_status == "verified"
        assert all(call["trace_id"] == expected.trace_id for call in calls)
        assert all(call["from_start_time"] == calls[0]["from_start_time"] for call in calls)
    finally:
        engine.dispose()


def test_batch_verification_rejects_non_development_and_missing_runs(tmp_path):
    benchmark = load_benchmark_snapshot()
    fixture = json.loads((FIXTURES / "success.json").read_text(encoding="utf-8"))
    template = TraceSummary.model_validate(fixture["expected_summary"])
    summary = {
        "target_id": "target-a",
        "agent_version_id": "target-a:a0",
        "complete": True,
        "split": "development",
        "benchmark_snapshot_id": benchmark.benchmark_snapshot_id,
        "dataset_version": benchmark.dataset_version,
        "evaluator_version": benchmark.evaluator_version,
        "items": [{"task_id": task, "run_id": task} for task in benchmark.splits["development"]],
    }
    source, output = tmp_path / "summary.json", tmp_path / "verification.json"
    source.write_text(json.dumps(summary), encoding="utf-8")
    provider = SimpleNamespace(
        verify=lambda run_id: template.model_copy(update={"task_id": run_id, "run_id": run_id})
    )
    assert verify_evaluation(provider, source, output, wait_seconds=0)["verified"]
    summary["items"][0].pop("run_id")
    source.write_text(json.dumps(summary), encoding="utf-8")
    report = verify_evaluation(provider, source, output, wait_seconds=0)
    assert not report["verified"] and len(report["items"]) == 14
    summary["split"] = "held_out"
    source.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="14 development"):
        verify_evaluation(provider, source, output, wait_seconds=0)
