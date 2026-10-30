"""Live local trace capture without transmitting data to Langfuse Cloud."""

import asyncio

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tracefix.common.config import load_settings
from tracefix.evaluation.tasks import load_tasks
from tracefix.persistence.database import make_engine
from tracefix.target_agent.tools import ToolEnvironment
from tracefix.targets.target_a.baseline import load_agent_version, load_benchmark_snapshot
from tracefix.targets.target_a.observed import run_observed
from tracefix.telemetry.recording import TelemetrySession

pytestmark = pytest.mark.integration


def test_live_target_a_generations_and_tools_share_trace(tmp_path):
    settings = load_settings().model_copy(
        update={"langfuse_enabled": False, "langfuse_public_key": "pk-lf-local-test"}
    )
    version = load_agent_version()
    version.verify_current_files()
    benchmark = load_benchmark_snapshot()
    benchmark.verify_current_files()
    task = next(task for task in load_tasks() if task.task_id == "T01")
    exporter = InMemorySpanExporter()
    telemetry = TelemetrySession(settings)
    telemetry.client = Langfuse(
        public_key="pk-lf-local-test",
        secret_key="sk-lf-local-test",
        host="http://127.0.0.1:9",
        span_exporter=exporter,
    )
    telemetry.status = "pending"
    engine = make_engine(settings)
    try:
        observed = asyncio.run(
            run_observed(
                task.public_task(),
                version.agent_config,
                tools=ToolEnvironment(engine),
                settings=settings,
                metadata={
                    "target_id": "target-a",
                    "agent_version_id": version.agent_version_id,
                    "benchmark_snapshot_id": benchmark.benchmark_snapshot_id,
                    "dataset_version": benchmark.dataset_version,
                    "split": "development",
                },
                output=tmp_path,
                telemetry=telemetry,
            )
        )
        telemetry.flush()
        spans = exporter.get_finished_spans()
        kinds = [span.attributes.get("langfuse.observation.type") for span in spans]
        assert observed.result.status == "completed"
        assert kinds.count("generation") == observed.result.model_calls
        assert kinds.count("tool") == len(observed.result.observations)
        assert kinds.count("span") == 1
        assert {span.context.trace_id for span in spans} == {int(observed.trace_id, 16)}
    finally:
        telemetry.shutdown()
        engine.dispose()
