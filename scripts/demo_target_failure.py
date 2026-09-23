"""Reproducible LIVE failure demonstration; not part of baseline accuracy results."""

import asyncio
import json

from tracefix.common.config import PROJECT_ROOT, load_settings
from tracefix.evaluation.tasks import load_tasks, score_task
from tracefix.persistence.database import make_engine
from tracefix.target_agent.cli import save_run
from tracefix.target_agent.config import load_agent_config
from tracefix.target_agent.graph import run_target
from tracefix.target_agent.tools import ToolEnvironment


def main():
    settings = load_settings()
    engine = make_engine(settings)
    task = load_tasks()[0]
    config = load_agent_config().model_copy(update={"max_tool_retries": 0, "max_steps": 4})
    output = PROJECT_ROOT / "artifacts/epic1-injected-failure"
    try:
        result = asyncio.run(
            run_target(
                task.public_task(),
                config,
                tools=ToolEnvironment(engine, injected_errors={"query_records": 100}),
                settings=settings,
            )
        )
        path = save_run(result, output)
        score = score_task(task, result)
        (output / "score.json").write_text(json.dumps(score, indent=2) + "\n", encoding="utf-8")
        print(f"Explicitly injected query_records outage. Run: {path}")
        print(f"Terminal reason: {result.terminal_reason}; correctness passed: {score['success']}")
        demonstrated = any(o.error == "injected_unavailable" for o in result.observations)
        return 0 if demonstrated and not score["success"] else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
