"""Reproducible LIVE failure demonstration; not part of baseline accuracy results."""

import asyncio
import json

from tracefix.common.config import PROJECT_ROOT, load_settings
from tracefix.evaluation.tasks import load_tasks, score_task
from tracefix.persistence.database import make_engine
from tracefix.target_agent.config import load_agent_config
from tracefix.target_agent.tools import ToolEnvironment
from tracefix.targets.target_a.observed import run_observed
from tracefix.telemetry.recording import TelemetrySession


def main():
    settings = load_settings()
    engine = make_engine(settings)
    task = load_tasks()[0]
    config = load_agent_config().model_copy(update={"max_tool_retries": 0, "max_steps": 4})
    output = PROJECT_ROOT / "artifacts/epic1-injected-failure"
    telemetry = TelemetrySession(settings)
    try:
        observed = asyncio.run(
            run_observed(
                task.public_task(),
                config,
                tools=ToolEnvironment(engine, injected_errors={"query_records": 100}),
                settings=settings,
                metadata={
                    "target_id": "target-a",
                    "agent_version_id": f"ad-hoc:{config.content_hash()[:12]}",
                    "dataset_version": "injected-demo",
                    "split": "development",
                },
                output=output,
                telemetry=telemetry,
            )
        )
        result = observed.result
        path = observed.run_file
        score = score_task(task, result)
        (output / "score.json").write_text(json.dumps(score, indent=2) + "\n", encoding="utf-8")
        print(f"Explicitly injected query_records outage. Run: {path}")
        print(f"Terminal reason: {result.terminal_reason}; correctness passed: {score['success']}")
        demonstrated = any(o.error == "injected_unavailable" for o in result.observations)
        return 0 if demonstrated and not score["success"] else 1
    finally:
        telemetry.finalize()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
