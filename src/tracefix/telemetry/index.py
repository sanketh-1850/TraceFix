"""Durable correlation between local target runs and remote trace IDs."""

from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tracefix.persistence.models import TargetRun
from tracefix.target_agent.schemas import TargetRunResult


def save_target_run(
    engine: Engine,
    run: TargetRunResult,
    metadata: dict[str, str | None],
    trace_id: str | None,
    telemetry_status: str,
    *,
    executed_tool_calls: int | None = None,
) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            TargetRun(
                run_id=run.run_id,
                trace_id=trace_id,
                target_id=str(metadata["target_id"]),
                task_id=run.task_id,
                agent_version_id=str(metadata["agent_version_id"]),
                benchmark_version=metadata.get("benchmark_snapshot_id"),
                dataset_version=str(metadata["dataset_version"]),
                split=metadata.get("split"),
                model_id=run.model,
                status=run.status,
                terminal_reason=run.terminal_reason,
                telemetry_status=telemetry_status,
                model_calls=run.model_calls,
                tool_calls=(
                    len(run.observations) if executed_tool_calls is None else executed_tool_calls
                ),
                created_at=datetime.fromisoformat(run.started_at).replace(tzinfo=None),
            )
        )


def get_target_run(engine: Engine, run_id: str) -> TargetRun:
    with Session(engine) as session:
        record = session.get(TargetRun, run_id)
        if record is None:
            raise KeyError(f"Unknown target run: {run_id}")
        session.expunge(record)
        return record


def set_telemetry_status(engine: Engine, run_id: str, status: str) -> None:
    with Session(engine) as session, session.begin():
        record = session.get(TargetRun, run_id)
        if record is None:
            raise KeyError(f"Unknown target run: {run_id}")
        record.telemetry_status = status


def list_target_runs(engine: Engine, filters: dict) -> list[TargetRun]:
    query = select(TargetRun)
    for key in ("target_id", "task_id", "agent_version_id", "dataset_version", "status"):
        if filters.get(key) is not None:
            query = query.where(getattr(TargetRun, key) == filters[key])
    query = query.order_by(TargetRun.created_at.desc(), TargetRun.run_id.desc())
    with Session(engine) as session:
        records = list(
            session.scalars(query.limit(min(max(int(filters.get("limit", 50)), 1), 500)))
        )
        for record in records:
            session.expunge(record)
        return records
