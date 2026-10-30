"""Reproduce Epic 2 Cloud smoke, failure, Judge, and captured-contract evidence."""

import argparse
import asyncio
import json
import time
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tracefix.common.config import load_settings
from tracefix.evaluation.runner import evaluate
from tracefix.evaluation.tasks import load_tasks, score_task
from tracefix.persistence.database import make_engine
from tracefix.target_agent.tools import ToolEnvironment
from tracefix.targets.target_a.baseline import load_agent_version, load_benchmark_snapshot
from tracefix.targets.target_a.observed import run_observed
from tracefix.telemetry.index import get_target_run, list_target_runs
from tracefix.telemetry.provider import InMemoryTraceProvider, LangfuseTraceProvider
from tracefix.telemetry.recording import JudgeRecorder, TelemetrySession
from tracefix.telemetry.redaction import sanitize
from tracefix.telemetry.verification import verify_run


class FixtureModel(BaseChatModel):
    scenario: str
    model_name: str = "fixture-model"

    @property
    def _llm_type(self):
        return "telemetry-fixture"

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.scenario == "model-error":
            raise ConnectionError("simulated model outage")
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="partial answer",
                        response_metadata={"done_reason": "length"},
                        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    )
                )
            ]
        )


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def metadata(version, benchmark):
    return {
        "target_id": "target-a",
        "agent_version_id": version.agent_version_id,
        "agent_version_hash": version.content_hash,
        "benchmark_snapshot_id": benchmark.benchmark_snapshot_id,
        "dataset_version": benchmark.dataset_version,
        "evaluator_version": benchmark.evaluator_version,
        "split": "development",
    }


def capture(provider, run_id, path, secrets):
    verify_run(provider, run_id)
    record, rows = provider._rows(run_id)
    for row in rows:
        row.pop("projectId", None)
        row["project_id"] = "fixture-project"
        for key in ("input", "output"):
            value = row.get(key)
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            row[key] = json.dumps(sanitize(value, secrets=secrets)) if value is not None else None
    rows = sanitize(rows, secrets=secrets, limit=16000)
    snapshot = InMemoryTraceProvider([record], rows)
    summary = snapshot.get_trace_summary(run_id)
    if summary.telemetry_status != "verified":
        raise RuntimeError(f"Cannot capture an incomplete trace: {summary.verification_issues}")
    write(
        path,
        {
            "provenance": "Captured from US Langfuse Observations v2; synthetic development data",
            "runs": [record],
            "observations": rows,
            "expected_summary": summary.model_dump(mode="json"),
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["smoke", "failures", "judge", "capture"])
    parser.add_argument("--output", type=Path, default=Path("artifacts/epic2"))
    parser.add_argument("--run-id")
    args = parser.parse_args()
    version, benchmark = load_agent_version(), load_benchmark_snapshot()
    version.verify_current_files()
    benchmark.verify_current_files()
    settings = version.model_settings.apply(load_settings())
    telemetry = TelemetrySession(settings)
    if telemetry.client is None:
        raise RuntimeError("Enable and configure Langfuse before Cloud verification")
    engine = make_engine(settings)
    provider = LangfuseTraceProvider(engine, telemetry.client)
    try:
        if args.phase == "capture":
            if not args.run_id:
                parser.error("capture requires --run-id")
            capture(
                provider,
                args.run_id,
                args.output,
                telemetry.secrets + (settings.langfuse_public_key,),
            )
            return 0
        if args.phase == "smoke":
            tasks = [task for task in load_tasks() if task.task_id in {"T01", "T06", "T08", "T10"}]
            summary = asyncio.run(
                evaluate(
                    tasks,
                    version.agent_config,
                    settings,
                    engine,
                    args.output / "smoke",
                    metadata(version, benchmark),
                    telemetry,
                )
            )
            telemetry.flush()
            results = [
                verify_run(provider, item["run_id"]).model_dump(mode="json")
                for item in summary["items"]
            ]
        elif args.phase == "failures":
            task = next(task for task in load_tasks() if task.task_id == "T01")
            results = []
            for scenario in ("tool-outage", "model-error", "truncation"):
                fixture = scenario != "tool-outage"
                effective = (
                    settings.model_copy(update={"ollama_model": "fixture-model"})
                    if fixture
                    else settings
                )
                config = version.agent_config.model_copy(
                    update={"max_tool_retries": 0, "max_steps": 4}
                )
                observed = asyncio.run(
                    run_observed(
                        task.public_task(),
                        config,
                        settings=effective,
                        tools=ToolEnvironment(
                            engine, injected_errors={"query_records": 100} if not fixture else None
                        ),
                        metadata={
                            "target_id": "target-a",
                            "agent_version_id": f"ad-hoc:{scenario}",
                            "dataset_version": "telemetry-fixtures-v1",
                        },
                        output=args.output / "failures",
                        telemetry=telemetry,
                        model=FixtureModel(scenario=scenario) if fixture else None,
                    )
                )
                telemetry.flush()
                result = verify_run(provider, observed.result.run_id).model_dump(mode="json")
                result["scenario"] = scenario
                score = score_task(task, observed.result)
                assert not score["success"]
                result["correctness"] = score
                if scenario == "tool-outage":
                    assert any(
                        o.error == "injected_unavailable" for o in observed.result.observations
                    )
                else:
                    assert observed.result.terminal_reason == (
                        "model_unavailable" if scenario == "model-error" else "truncated_generation"
                    )
                if scenario == "model-error":
                    assert not result["metrics"]["usage_complete"]
                    assert result["metrics"]["input_tokens"] is None
                results.append(result)
                print(
                    f"{scenario}: {observed.result.terminal_reason}; telemetry verified", flush=True
                )
        else:
            if not args.run_id:
                parser.error("judge requires a source target --run-id")
            get_target_run(engine, args.run_id)
            recorder = JudgeRecorder(telemetry)
            results = []
            for mode in ("generic", "specialized"):
                started = perf_counter()
                judge_run_id = uuid4().hex
                diagnosis = {"failure_type": "unknown", "simulation": True}
                with recorder.run(
                    judge_run_id=judge_run_id,
                    mode=mode,
                    target_id="target-a",
                    source_target_run_id=args.run_id,
                    manifest_version=version.manifest_hash,
                ) as (trace_id, span):
                    span.update(metadata={"simulation": "true"})
                    with telemetry.client.start_as_current_observation(
                        name="simulate-diagnosis",
                        as_type="generation",
                        model="fixture-model",
                        input={"source_target_run_id": args.run_id},
                        output={"decision": "inspect source"},
                        usage_details={"input": 2, "output": 3},
                    ):
                        pass
                    with recorder.diagnostic_tool(
                        "inspect-run", {"run_id": args.run_id}, "diagnostic-1"
                    ) as tool:
                        tool.update(output={"run_id": args.run_id, "available": True})
                    recorder.finish(
                        span,
                        diagnosis=diagnosis,
                        fallback_used=mode == "specialized",
                        tokens=5,
                        tool_calls=1,
                        latency_ms=(perf_counter() - started) * 1000,
                    )
                telemetry.flush()
                deadline = time.monotonic() + 60
                while True:
                    rows = provider._observations(trace_id)
                    if len(rows) >= 3 and any(
                        r.get("output") and r["name"] == "tracefix-judge" for r in rows
                    ):
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Simulated Judge trace ingestion incomplete")
                    time.sleep(3)
                root = next(row for row in rows if row["name"] == "tracefix-judge")
                assert root["metadata"]["judge_run_id"] == judge_run_id
                assert root["metadata"]["mode"] == mode
                assert root["metadata"]["source_target_run_id"] == args.run_id
                assert len([r for r in rows if r["type"] == "GENERATION"]) == 1
                assert len([r for r in rows if r["type"] == "TOOL"]) == 1
                assert json.loads(root["output"]) == diagnosis
                assert str(root["metadata"]["tokens"]) == "5"
                assert (
                    str(root["metadata"]["fallback_used"]).lower()
                    == str(mode == "specialized").lower()
                )
                generation = next(r for r in rows if r["type"] == "GENERATION")
                usage = generation.get("usageDetails") or generation.get("usage_details")
                assert usage["input"] == 2
                assert usage["output"] == 3
                assert all(r.get("endTime") or r.get("end_time") for r in rows)
                assert all(
                    (r.get("parentObservationId") or r.get("parent_observation_id")) == root["id"]
                    for r in rows
                    if r["id"] != root["id"]
                )
                assert trace_id != get_target_run(engine, args.run_id).trace_id
                results.append(
                    {
                        "judge_run_id": judge_run_id,
                        "trace_id": trace_id,
                        "mode": mode,
                        "source_target_run_id": args.run_id,
                        "verified": True,
                        "input_tokens": 2,
                        "output_tokens": 3,
                        "fallback_used": mode == "specialized",
                        "diagnosis": diagnosis,
                    }
                )
            target_traces = {row.trace_id for row in list_target_runs(engine, {"limit": 500})}
            assert not target_traces.intersection(result["trace_id"] for result in results)
        write(args.output / f"{args.phase}-verification.json", results)
        print(f"{args.phase}: {len(results)} verified runs", flush=True)
        return 0
    finally:
        telemetry.finalize()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
