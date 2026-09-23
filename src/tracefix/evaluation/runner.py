"""Initial fixed-workload runner, not the future candidate promotion engine."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from tracefix.common.config import PROJECT_ROOT, load_settings
from tracefix.evaluation.tasks import load_tasks, score_task
from tracefix.persistence.database import make_engine
from tracefix.target_agent.cli import save_run
from tracefix.target_agent.config import DATA_ROOT, DEFAULT_CONFIG, digest, load_agent_config
from tracefix.target_agent.graph import run_target
from tracefix.target_agent.tools import ToolEnvironment


async def evaluate(tasks, config, settings, engine, output):
    output.mkdir(parents=True, exist_ok=True)
    items = []
    dataset_hash = digest((DATA_ROOT / "tasks/order_support.jsonl").read_text(encoding="utf-8"))
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
                    "difficulty": task.difficulty,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "tool_calls": len(run.observations),
                    "latency_ms": run.latency_ms,
                    "terminal_reason": run.terminal_reason,
                }
            )
        except Exception as exc:
            item = {
                "task_id": task.task_id,
                "difficulty": task.difficulty,
                "success": False,
                "reasons": [f"infrastructure_error:{type(exc).__name__}"],
            }
        items.append(item)
        print(
            f"{task.task_id}: {'PASS' if item['success'] else 'FAIL'} {item['reasons']}", flush=True
        )
        easy = [i for i in items if i["difficulty"] == "easy"]
        summary = {
            "dataset_hash": dataset_hash,
            "config_hash": config.content_hash(),
            "data_hash": baseline_hash,
            "model": settings.ollama_model,
            "complete": len(items) == len(tasks),
            "total": len(items),
            "passed": sum(i["success"] for i in items),
            "success_rate": sum(i["success"] for i in items) / len(items),
            "easy_passed": sum(i["success"] for i in easy),
            "easy_total": len(easy),
            "items": items,
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Evaluate the fixed order-support workload")
    parser.add_argument("--subset", choices=["easy", "all"], default="all")
    parser.add_argument("--model")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    settings = load_settings()
    if args.model:
        settings = settings.model_copy(update={"ollama_model": args.model})
    tasks = [t for t in load_tasks() if args.subset == "all" or t.difficulty == "easy"]
    output = args.output_dir or PROJECT_ROOT / "artifacts/evaluations" / uuid4().hex
    engine = make_engine(settings)
    try:
        result = asyncio.run(
            evaluate(tasks, load_agent_config(args.config), settings, engine, output)
        )
        print(f"Passed {result['passed']}/{result['total']}. Results: {output}")
        return 0 if result["passed"] == result["total"] else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
