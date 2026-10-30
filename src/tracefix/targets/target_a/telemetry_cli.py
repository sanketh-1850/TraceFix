"""Supported standalone Target A command with A0-safe tracing."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from tracefix.common.config import PROJECT_ROOT, load_settings
from tracefix.evaluation.tasks import load_tasks
from tracefix.persistence.database import make_engine
from tracefix.target_agent.config import load_agent_config
from tracefix.target_agent.schemas import TargetTask
from tracefix.target_agent.tools import ToolEnvironment
from tracefix.targets.target_a.baseline import load_agent_version, load_benchmark_snapshot
from tracefix.targets.target_a.observed import run_observed
from tracefix.telemetry.recording import TelemetrySession


def run_main():
    parser = argparse.ArgumentParser(description="Run the traced Target A agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task-id")
    group.add_argument("--prompt")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "artifacts/target")
    args = parser.parse_args()

    version = load_agent_version()
    version.verify_current_files()
    benchmark = load_benchmark_snapshot()
    benchmark.verify_current_files()
    config = load_agent_config(args.config) if args.config else version.agent_config
    settings = version.model_settings.apply(load_settings())
    if args.model:
        settings = settings.model_copy(update={"ollama_model": args.model})
    if args.task_id:
        task = next((item for item in load_tasks() if item.task_id == args.task_id), None)
        if task is None:
            parser.error("Unknown task ID")
        public_task = task.public_task()
        split = "development" if args.task_id in benchmark.splits["development"] else "held_out"
    else:
        public_task = TargetTask(task_id=f"custom-{uuid4().hex[:8]}", prompt=args.prompt)
        split = None
    frozen = args.task_id is not None and not args.config and not args.model
    metadata = {
        "target_id": "target-a",
        "agent_version_id": version.agent_version_id
        if frozen
        else f"ad-hoc:{config.content_hash()[:12]}",
        "benchmark_snapshot_id": benchmark.benchmark_snapshot_id if frozen else None,
        "dataset_version": benchmark.dataset_version if frozen else "ad-hoc",
        "evaluator_version": benchmark.evaluator_version if frozen else None,
        "split": split if frozen else None,
    }
    engine = make_engine(settings)
    telemetry = TelemetrySession(settings)
    try:
        observed = asyncio.run(
            run_observed(
                public_task,
                config,
                tools=ToolEnvironment(engine),
                settings=settings,
                metadata=metadata,
                output=args.output_dir,
                telemetry=telemetry,
            )
        )
        result = observed.result
        print(result.answer.answer if result.answer else result.terminal_reason)
        if result.answer:
            print(json.dumps(result.answer.facts))
        print(f"Run: {observed.run_file}")
        print(f"Trace: {observed.trace_id or 'disabled'} ({observed.telemetry_status})")
        return 0 if result.status == "completed" else 1
    except Exception as exc:
        print(f"Run failed ({type(exc).__name__}); check database, configuration and Ollama.")
        return 1
    finally:
        telemetry.finalize()
        engine.dispose()
