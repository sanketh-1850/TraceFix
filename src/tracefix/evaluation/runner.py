"""Versioned Target A evaluation runner; candidate promotion belongs to later epics."""

import argparse
import asyncio
import json
import math
from pathlib import Path
from uuid import uuid4

from tracefix.common.config import PROJECT_ROOT, load_settings
from tracefix.evaluation.tasks import EVALUATOR_VERSION, load_tasks, score_task, select_tasks
from tracefix.persistence.database import make_engine
from tracefix.target_agent.cli import save_run
from tracefix.target_agent.config import digest, load_agent_config
from tracefix.target_agent.graph import run_target
from tracefix.target_agent.tools import ToolEnvironment
from tracefix.targets.target_a.baseline import (
    DEFAULT_AGENT_VERSION,
    DEFAULT_BENCHMARK,
    load_agent_version,
    load_benchmark_snapshot,
)


def _tool_retries(observations) -> int:
    failed = set()
    retries = 0
    for observation in observations:
        key = json.dumps([observation.tool, observation.arguments], sort_keys=True)
        if key in failed:
            retries += 1
        if not observation.ok:
            failed.add(key)
    return retries


def _metric_summary(items: list[dict]) -> dict:
    latencies = sorted(item["latency_ms"] for item in items if item.get("latency_ms") is not None)
    p95 = latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else None
    return {
        "task_count": len(items),
        "passed": sum(item["success"] for item in items),
        "failed": sum(not item["success"] for item in items),
        "success_rate": sum(item["success"] for item in items) / len(items),
        "input_tokens": sum(item.get("input_tokens") or 0 for item in items),
        "input_tokens_known_tasks": sum(item.get("input_tokens") is not None for item in items),
        "output_tokens": sum(item.get("output_tokens") or 0 for item in items),
        "output_tokens_known_tasks": sum(item.get("output_tokens") is not None for item in items),
        "model_calls": sum(item.get("model_calls") or 0 for item in items),
        "tool_calls": sum(item.get("tool_calls") or 0 for item in items),
        "tool_errors": sum(item.get("tool_errors") or 0 for item in items),
        "tool_retries": sum(item.get("tool_retries") or 0 for item in items),
        "latency_ms_total": round(sum(latencies), 3),
        "latency_ms_mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "latency_ms_p95": p95,
    }


def _build_summary(items, tasks, metadata, dataset_hash, config, model, data_hash):
    easy = [item for item in items if item["difficulty"] == "easy"]
    metrics = _metric_summary(items)
    return {
        **metadata,
        "dataset_hash": dataset_hash,
        "config_hash": config.content_hash(),
        "data_hash": data_hash,
        "model": model,
        "complete": len(items) == len(tasks),
        "total": len(items),
        "passed": metrics["passed"],
        "success_rate": metrics["success_rate"],
        "easy_passed": sum(item["success"] for item in easy),
        "easy_total": len(easy),
        "metrics": metrics,
        "items": items,
    }


async def evaluate(tasks, config, settings, engine, output, metadata=None):
    if not tasks:
        raise ValueError("Evaluation requires at least one task")
    output.mkdir(parents=True, exist_ok=True)
    items = []
    dataset_hash = digest(
        (PROJECT_ROOT / "data/tasks/order_support.jsonl").read_text(encoding="utf-8")
    )
    metadata = metadata or {
        "target_id": "target-a",
        "agent_version_id": "test",
        "agent_version_hash": None,
        "benchmark_snapshot_id": "test",
        "dataset_version": "test",
        "evaluator_version": EVALUATOR_VERSION,
        "split": "test",
    }
    baseline_hash = None
    for task in tasks:
        print(f"Running {task.task_id} ({task.difficulty})...", flush=True)
        try:
            run = await run_target(
                task.public_task(), config, tools=ToolEnvironment(engine), settings=settings
            )
            path = save_run(run, output)
            item = score_task(task, run)
            if baseline_hash is None:
                baseline_hash = run.data_hash
            if run.data_hash != baseline_hash:
                item["success"] = False
                item["reasons"].append("data_snapshot_changed")
            item.update(
                {
                    "run_id": run.run_id,
                    "run_file": path.name,
                    "agent_version_id": metadata["agent_version_id"],
                    "difficulty": task.difficulty,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "model_calls": run.model_calls,
                    "tool_calls": len(run.observations),
                    "tool_errors": sum(not observation.ok for observation in run.observations),
                    "tool_retries": _tool_retries(run.observations),
                    "latency_ms": run.latency_ms,
                    "terminal_reason": run.terminal_reason,
                }
            )
        except Exception as exc:
            item = {
                "task_id": task.task_id,
                "agent_version_id": metadata["agent_version_id"],
                "difficulty": task.difficulty,
                "success": False,
                "reasons": [f"infrastructure_error:{type(exc).__name__}"],
                "input_tokens": None,
                "output_tokens": None,
                "model_calls": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "tool_retries": 0,
                "latency_ms": None,
                "terminal_reason": "infrastructure_error",
            }
        items.append(item)
        print(
            f"{task.task_id}: {'PASS' if item['success'] else 'FAIL'} {item['reasons']}",
            flush=True,
        )
        summary = _build_summary(
            items, tasks, metadata, dataset_hash, config, settings.ollama_model, baseline_hash
        )
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    return summary


def _parser(*, frozen_a0: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rerun the frozen Target A A0 baseline"
            if frozen_a0
            else "Evaluate the versioned order-support workload"
        )
    )
    parser.add_argument(
        "--split",
        choices=["development", "held_out", "all"],
        default="development" if frozen_a0 else "all",
    )
    parser.add_argument("--subset", choices=["easy", "all"], default="all")
    parser.add_argument("--output-dir", type=Path)
    if not frozen_a0:
        parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
        parser.add_argument("--agent-version", type=Path, default=DEFAULT_AGENT_VERSION)
        parser.add_argument("--model")
        parser.add_argument("--config", type=Path)
    return parser


def _main(*, frozen_a0: bool) -> int:
    args = _parser(frozen_a0=frozen_a0).parse_args()
    benchmark_path = DEFAULT_BENCHMARK if frozen_a0 else args.benchmark
    version_path = DEFAULT_AGENT_VERSION if frozen_a0 else args.agent_version
    benchmark = load_benchmark_snapshot(benchmark_path)
    benchmark.verify_current_files()
    version = load_agent_version(version_path)
    version.verify_current_files()
    if version.benchmark_snapshot_id != benchmark.benchmark_snapshot_id:
        raise ValueError("Agent version and benchmark snapshot do not match")

    config = version.agent_config
    settings = version.model_settings.apply(load_settings())
    agent_version_id = version.agent_version_id
    agent_version_hash = version.content_hash
    if not frozen_a0 and args.config:
        config = load_agent_config(args.config)
        agent_version_id = f"ad-hoc:{config.content_hash()[:12]}"
        agent_version_hash = config.content_hash()
    if not frozen_a0 and args.model:
        settings = settings.model_copy(update={"ollama_model": args.model})
        agent_version_id = f"{agent_version_id}:model-override"

    tasks = select_tasks(benchmark.task_ids(args.split), load_tasks())
    if args.subset == "easy":
        tasks = [task for task in tasks if task.difficulty == "easy"]
    metadata = {
        "target_id": benchmark.target_id,
        "agent_version_id": agent_version_id,
        "agent_version_hash": agent_version_hash,
        "benchmark_snapshot_id": benchmark.benchmark_snapshot_id,
        "dataset_version": benchmark.dataset_version,
        "evaluator_version": benchmark.evaluator_version,
        "split": args.split,
    }
    output = args.output_dir or (
        PROJECT_ROOT
        / "artifacts/evaluations"
        / f"{agent_version_id.replace(':', '-')}-{args.split}-{uuid4().hex}"
    )
    engine = make_engine(settings)
    try:
        result = asyncio.run(evaluate(tasks, config, settings, engine, output, metadata))
        try:
            artifact_directory = str(output.resolve().relative_to(PROJECT_ROOT))
        except ValueError:
            artifact_directory = str(output.resolve())
        result["artifact_directory"] = artifact_directory.replace("\\", "/")
        (output / "summary.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Passed {result['passed']}/{result['total']}. Results: {output}")
        if frozen_a0:
            return 0 if result["complete"] else 1
        return 0 if result["passed"] == result["total"] else 1
    finally:
        engine.dispose()


def main() -> int:
    return _main(frozen_a0=False)


def a0_main() -> int:
    return _main(frozen_a0=True)


if __name__ == "__main__":
    raise SystemExit(main())
