"""Inspect and verify normalized telemetry by local run ID."""

import argparse
import json
from pathlib import Path

from tracefix.common.config import load_settings
from tracefix.persistence.database import make_engine
from tracefix.telemetry.index import list_target_runs
from tracefix.telemetry.provider import (
    IncompleteTrace,
    LangfuseTraceProvider,
    TelemetryUnavailable,
    local_trace_summary,
)
from tracefix.telemetry.recording import TelemetrySession
from tracefix.telemetry.verification import verify_evaluation, verify_run


def main():
    parser = argparse.ArgumentParser(description="Inspect TraceFix target telemetry")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("summary", "tools", "observation", "metrics", "verify"):
        command = sub.add_parser(name)
        command.add_argument("run_id")
        if name == "observation":
            command.add_argument("observation_id")
    listing = sub.add_parser("list")
    listing.add_argument("--task-id")
    listing.add_argument("--agent-version-id")
    listing.add_argument("--limit", type=int, default=50)
    batch = sub.add_parser("verify-evaluation")
    batch.add_argument("summary", type=Path)
    batch.add_argument("--output", type=Path)
    batch.add_argument("--wait-seconds", type=float, default=60)
    args = parser.parse_args()
    settings = load_settings()
    engine = make_engine(settings)
    session = TelemetrySession(settings)
    try:
        if args.command == "verify-evaluation":
            if session.client is None:
                raise TelemetryUnavailable("Langfuse is not configured")
            report = verify_evaluation(
                LangfuseTraceProvider(engine, session.client),
                args.summary,
                args.output or args.summary.parent / "telemetry-verification.json",
                args.wait_seconds,
            )
            print(json.dumps(report, indent=2))
            return 0 if report["verified"] else 1
        elif args.command == "list":
            rows = list_target_runs(
                engine,
                {
                    "target_id": "target-a",
                    "task_id": args.task_id,
                    "agent_version_id": args.agent_version_id,
                    "limit": args.limit,
                },
            )
            result = [
                {
                    "run_id": row.run_id,
                    "trace_id": row.trace_id,
                    "task_id": row.task_id,
                    "agent_version_id": row.agent_version_id,
                    "telemetry_status": row.telemetry_status,
                }
                for row in rows
            ]
        else:
            if session.client is None:
                if args.command not in {"summary", "metrics"}:
                    raise TelemetryUnavailable("Langfuse is not configured")
                local = local_trace_summary(engine, args.run_id)
                result = local if args.command == "summary" else local.metrics
            else:
                provider = LangfuseTraceProvider(engine, session.client)
                if args.command in {"summary", "metrics"}:
                    try:
                        summary = provider.get_trace_summary(args.run_id)
                    except TelemetryUnavailable:
                        summary = local_trace_summary(engine, args.run_id, status="unavailable")
                    result = summary if args.command == "summary" else summary.metrics
                elif args.command == "tools":
                    result = provider.list_tool_calls(args.run_id)
                elif args.command == "observation":
                    result = provider.inspect_observation(args.run_id, args.observation_id)
                else:
                    result = verify_run(provider, args.run_id)
        if isinstance(result, list):
            payload = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in result
            ]
        else:
            payload = result.model_dump(mode="json")
        print(json.dumps(payload, indent=2))
        return 0
    except (KeyError, ValueError, IncompleteTrace, TelemetryUnavailable) as exc:
        print(str(exc))
        return 1
    finally:
        session.finalize()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
