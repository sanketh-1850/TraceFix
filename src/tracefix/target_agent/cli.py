import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from tracefix.common.config import PROJECT_ROOT, load_settings
from tracefix.persistence.database import make_engine
from tracefix.target_agent.config import DEFAULT_CONFIG, load_agent_config
from tracefix.target_agent.data import seed_data
from tracefix.target_agent.graph import run_target
from tracefix.target_agent.schemas import TargetTask
from tracefix.target_agent.tools import ToolEnvironment

ARTIFACTS = PROJECT_ROOT / "artifacts/target"


def save_run(run, output: Path = ARTIFACTS):
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{run.run_id}.json"
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def seed_main():
    engine = make_engine(load_settings())
    try:
        print(f"Seed complete: {seed_data(engine)} new records")
        return 0
    except ValueError as exc:
        print(str(exc))  # Only reports fixture identifiers, never database credentials.
        return 1
    except Exception as exc:
        print(f"Seed failed ({type(exc).__name__}); check database access and migrations.")
        return 1
    finally:
        engine.dispose()


def run_main():
    parser = argparse.ArgumentParser(description="Run the local order-support target agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task-id")
    group.add_argument("--prompt")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model")
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS)
    args = parser.parse_args()
    if args.task_id:
        from tracefix.evaluation.tasks import load_tasks

        matching = [t for t in load_tasks() if t.task_id == args.task_id]
        if not matching:
            parser.error("Unknown task ID")
        task = matching[0].public_task()
    else:
        task = TargetTask(task_id=f"custom-{uuid4().hex[:8]}", prompt=args.prompt)
    settings = load_settings()
    if args.model:
        settings = settings.model_copy(update={"ollama_model": args.model})
    engine = make_engine(settings)
    try:
        result = asyncio.run(
            run_target(
                task,
                load_agent_config(args.config),
                tools=ToolEnvironment(engine),
                settings=settings,
            )
        )
        path = save_run(result, args.output_dir)
        print(result.answer.answer if result.answer else result.terminal_reason)
        if result.answer:
            print(json.dumps(result.answer.facts))
        print(f"Run: {path}")
        return 0 if result.status == "completed" else 1
    except Exception as exc:
        print(f"Run failed ({type(exc).__name__}); check database, configuration and Ollama.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_main())
