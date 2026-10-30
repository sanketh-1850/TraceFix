"""Normalize Langfuse observations behind the TraceProvider contract."""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine

from tracefix.telemetry.index import get_target_run, list_target_runs, set_telemetry_status
from tracefix.telemetry.redaction import sanitize
from tracefix.telemetry.schemas import (
    ObservationExcerpt,
    RunListFilters,
    RunMetrics,
    ToolCallRecord,
    TraceSummary,
    excerpt,
)


class TelemetryUnavailable(RuntimeError):
    pass


class IncompleteTrace(RuntimeError):
    pass


def _payload(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def _utc(value):
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, exclude_none=False)
    if hasattr(value, "dict"):
        return value.dict(by_alias=True)
    raise TypeError("Unsupported telemetry payload")


def _field(row: dict, *names, default=None):
    for name in names:
        if name in row:
            return row[name]
    return default


def _millis(start, end):
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        duration = (b - a).total_seconds() * 1000
        return round(duration, 3) if duration >= 0 else None
    except (ValueError, TypeError):
        return None


def _usage_value(row: dict, details: dict, direct: tuple[str, ...], fallback: tuple[str, ...]):
    for key in fallback:
        if details.get(key) is not None:
            return details[key]
    value = _field(row, *direct)
    # Cloud includes legacy zero aggregates even when a failed generation reported no usage.
    # An explicit zero in usageDetails remains known; an empty details object does not.
    if value == 0 and not details and ("usageDetails" in row or "usage_details" in row):
        return None
    return value


class NormalizedTraceProvider:
    def _record(self, run_id: str) -> dict:
        raise NotImplementedError

    def _observations(self, trace_id: str) -> list[dict]:
        raise NotImplementedError

    def _records(self, filters: dict) -> list[dict]:
        raise NotImplementedError

    def _rows(self, run_id: str):
        record = self._record(run_id)
        if not record.get("trace_id"):
            raise TelemetryUnavailable("Run has no remote trace")
        unique = {}
        for row in self._observations(record["trace_id"]):
            item = _dict(row)
            if _field(item, "traceId", "trace_id") != record["trace_id"]:
                raise TelemetryUnavailable("Observation belongs to another trace")
            unique[str(item["id"])] = item
        rows = list(unique.values())
        rows.sort(
            key=lambda row: (
                str(_field(row, "startTime", "start_time", default="")),
                str(row["id"]),
            )
        )
        return record, rows

    @staticmethod
    def _local_summary(record: dict, *, status: str | None = None) -> TraceSummary:
        started_at = record["created_at"]
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return TraceSummary(
            run_id=record["run_id"],
            trace_id=record.get("trace_id"),
            target_id=record["target_id"],
            task_id=record["task_id"],
            agent_version_id=record["agent_version_id"],
            dataset_version=record["dataset_version"],
            benchmark_version=record.get("benchmark_version"),
            model_id=record["model_id"],
            status=record["status"],
            terminal_reason=record["terminal_reason"],
            telemetry_status=status or record["telemetry_status"],
            started_at=started_at,
            metrics=RunMetrics(
                run_id=record["run_id"],
                trace_id=record.get("trace_id"),
                model_calls=record["model_calls"],
                tool_calls=record["tool_calls"],
                tool_errors=None,
                input_tokens=None,
                output_tokens=None,
                latency_ms=None,
                usage_complete=False,
            ),
            observation_ids=[],
        )

    def get_trace_summary(self, run_id: str) -> TraceSummary:
        record, rows = self._rows(run_id)
        trace_id = record["trace_id"]
        roots = [
            row
            for row in rows
            if _field(row, "name") == "tracefix-target-a"
            and (_field(row, "metadata", default={}) or {}).get("run_id") == run_id
        ]
        generations = [
            row for row in rows if str(_field(row, "type", default="")).upper() == "GENERATION"
        ]
        tools = [row for row in rows if str(_field(row, "type", default="")).upper() == "TOOL"]
        expected_identity = {
            "kind": "target",
            "target_id": record["target_id"],
            "task_id": record["task_id"],
            "agent_version_id": record["agent_version_id"],
            "dataset_version": record["dataset_version"],
            "model_id": record["model_id"],
            "terminal_reason": record["terminal_reason"],
            "outcome": record["status"],
        }
        if record.get("benchmark_version"):
            expected_identity["benchmark_snapshot_id"] = record["benchmark_version"]
        if record.get("split"):
            expected_identity["split"] = record["split"]
        root_metadata = _field(roots[0], "metadata", default={}) or {} if roots else {}
        issues = []
        if len(roots) != 1:
            issues.append(f"target_roots:expected=1,received={len(roots)}")
        for key, value in expected_identity.items():
            if str(root_metadata.get(key)) != str(value):
                issues.append(f"identity_mismatch:{key}")
        for key, actual in (("model_calls", len(generations)), ("tool_calls", len(tools))):
            if actual != record[key]:
                issues.append(f"{key}:expected={record[key]},received={actual}")
            if str(root_metadata.get(f"expected_{key}")) != str(record[key]):
                issues.append(f"expected_count_mismatch:{key}")
        by_id = {str(row["id"]): row for row in rows}
        root_id = str(roots[0]["id"]) if len(roots) == 1 else None
        for row in rows:
            identity = str(row["id"])
            if (_field(row, "metadata", default={}) or {}).get("kind") == "judge":
                issues.append(f"judge_observation:{identity}")
            if _field(row, "endTime", "end_time") is None:
                issues.append(f"unfinished_observation:{identity}")
            elif (
                _millis(_field(row, "startTime", "start_time"), _field(row, "endTime", "end_time"))
                is None
            ):
                issues.append(f"invalid_timing:{identity}")
            if root_id and identity != root_id:
                parent = _field(row, "parentObservationId", "parent_observation_id")
                seen = {identity}
                while parent != root_id:
                    if not parent or str(parent) in seen or str(parent) not in by_id:
                        issues.append(f"orphan_observation:{identity}")
                        break
                    seen.add(str(parent))
                    parent = _field(
                        by_id[str(parent)], "parentObservationId", "parent_observation_id"
                    )
        for row in generations:
            if not _field(row, "model"):
                issues.append(f"missing_model:{row['id']}")
            elif _field(row, "model") != record["model_id"]:
                issues.append(f"model_mismatch:{row['id']}")
        for row in tools:
            metadata = _field(row, "metadata", default={}) or {}
            if not metadata.get("call_id"):
                issues.append(f"missing_tool_call_id:{row['id']}")
            output = sanitize(_payload(_field(row, "output")))
            if metadata.get("local_observation_id"):
                if not isinstance(output, dict) or (
                    output.get("observation_id") != metadata["local_observation_id"]
                    or output.get("call_id") != metadata.get("call_id")
                ):
                    issues.append(f"tool_observation_mapping:{row['id']}")
        complete = not issues
        status = "verified" if complete else "incomplete"
        usage = []
        for row in generations:
            details = _field(row, "usageDetails", "usage_details", default={}) or {}
            usage.append(
                (
                    _usage_value(
                        row,
                        details,
                        ("inputUsage", "input_usage"),
                        ("input", "input_tokens", "prompt_tokens"),
                    ),
                    _usage_value(
                        row,
                        details,
                        ("outputUsage", "output_usage"),
                        ("output", "output_tokens", "completion_tokens"),
                    ),
                )
            )
        usage_complete = complete and all(a is not None and b is not None for a, b in usage)
        root = roots[0] if roots else None
        metrics = RunMetrics(
            run_id=run_id,
            trace_id=trace_id,
            model_calls=len(generations),
            tool_calls=len(tools),
            tool_errors=sum(
                str(_field(row, "level", default="")).upper() == "ERROR" for row in tools
            ),
            input_tokens=sum(int(a) for a, _ in usage)
            if complete and all(a is not None for a, _ in usage)
            else None,
            output_tokens=sum(int(b) for _, b in usage)
            if complete and all(b is not None for _, b in usage)
            else None,
            latency_ms=_millis(
                _field(root, "startTime", "start_time"), _field(root, "endTime", "end_time")
            )
            if root
            else None,
            usage_complete=usage_complete,
        )
        started_at = record["created_at"]
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return TraceSummary(
            run_id=run_id,
            trace_id=trace_id,
            target_id=record["target_id"],
            task_id=record["task_id"],
            agent_version_id=record["agent_version_id"],
            dataset_version=record["dataset_version"],
            benchmark_version=record.get("benchmark_version"),
            model_id=record["model_id"],
            status=record["status"],
            terminal_reason=record["terminal_reason"],
            telemetry_status=status,
            started_at=started_at,
            metrics=metrics,
            observation_ids=[str(row["id"]) for row in rows],
            verification_issues=issues,
        )

    def list_tool_calls(self, run_id: str) -> list[ToolCallRecord]:
        record, rows = self._rows(run_id)
        tools = []
        for row in rows:
            if str(_field(row, "type", default="")).upper() != "TOOL":
                continue
            metadata = _field(row, "metadata", default={}) or {}
            output = sanitize(_payload(_field(row, "output")))
            output = output if isinstance(output, dict) else {}
            tools.append(
                ToolCallRecord(
                    run_id=run_id,
                    trace_id=record["trace_id"],
                    observation_id=str(row["id"]),
                    local_observation_id=metadata.get("local_observation_id"),
                    call_id=metadata.get("call_id"),
                    tool=str(_field(row, "name", default="unknown")),
                    ok=output.get("ok"),
                    source_ids=output.get("source_ids") or [],
                    latency_ms=_millis(
                        _field(row, "startTime", "start_time"), _field(row, "endTime", "end_time")
                    ),
                    error=output.get("error"),
                )
            )
        return tools

    def inspect_observation(self, run_id: str, observation_id: str) -> ObservationExcerpt:
        record, rows = self._rows(run_id)
        for row in rows:
            metadata = _field(row, "metadata", default={}) or {}
            if observation_id not in {str(row["id"]), str(metadata.get("local_observation_id"))}:
                continue
            input_text, input_cut = excerpt(sanitize(_payload(_field(row, "input"))))
            output_text, output_cut = excerpt(sanitize(_payload(_field(row, "output"))))
            return ObservationExcerpt(
                run_id=run_id,
                trace_id=record["trace_id"],
                observation_id=str(row["id"]),
                parent_observation_id=_field(row, "parentObservationId", "parent_observation_id"),
                kind=str(_field(row, "type", default="UNKNOWN")),
                name=str(_field(row, "name", default="unknown")),
                input_excerpt=input_text,
                output_excerpt=output_text,
                status_message=sanitize(_field(row, "statusMessage", "status_message")),
                latency_ms=_millis(
                    _field(row, "startTime", "start_time"),
                    _field(row, "endTime", "end_time"),
                ),
                truncated=input_cut or output_cut,
            )
        raise KeyError(f"Observation is not part of run {run_id}: {observation_id}")

    def get_run_metrics(self, run_id: str) -> RunMetrics:
        return self.get_trace_summary(run_id).metrics

    def list_runs(self, filters: dict | None = None) -> list[TraceSummary]:
        selected = RunListFilters.model_validate(filters or {}).model_dump(exclude_none=True)
        summaries = []
        for record in self._records(selected):
            if not record.get("trace_id"):
                summaries.append(self._local_summary(record))
                continue
            try:
                summaries.append(self.get_trace_summary(record["run_id"]))
            except TelemetryUnavailable:
                summaries.append(self._local_summary(record, status="unavailable"))
        return summaries


class InMemoryTraceProvider(NormalizedTraceProvider):
    def __init__(self, runs: list[dict], observations: list[dict]):
        self.runs = {run["run_id"]: run for run in runs}
        self.observations = observations

    def _record(self, run_id: str) -> dict:
        return self.runs[run_id]

    def _observations(self, trace_id: str) -> list[dict]:
        return [row for row in self.observations if _field(row, "traceId", "trace_id") == trace_id]

    def _records(self, filters: dict) -> list[dict]:
        rows = list(self.runs.values())
        for key in ("target_id", "task_id", "agent_version_id", "dataset_version", "status"):
            if filters.get(key) is not None:
                rows = [row for row in rows if row[key] == filters[key]]
        rows.sort(key=lambda row: (str(row["created_at"]), row["run_id"]), reverse=True)
        return rows[: filters["limit"]]


class LangfuseTraceProvider(NormalizedTraceProvider):
    def __init__(self, engine: Engine, client, *, request_interval: float = 3.0):
        self.engine = engine
        self.client = client
        self.request_interval = request_interval
        self._next_request = 0.0
        self._query_start = None

    def _record(self, run_id: str) -> dict:
        record = _db_record(self.engine, run_id)
        self._query_start = _utc(record["created_at"])
        return record

    def _records(self, filters: dict) -> list[dict]:
        return [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in list_target_runs(self.engine, filters)
        ]

    def _observations(self, trace_id: str) -> list[dict]:
        rows = []
        cursor = None
        seen_cursors = set()
        start = self._query_start or datetime.now(timezone.utc)
        try:
            while True:
                kwargs = {
                    "trace_id": trace_id,
                    "fields": "core,basic,metadata,model,usage,metrics,io",
                    "limit": 100,
                    "from_start_time": start - timedelta(minutes=1),
                    "to_start_time": start + timedelta(days=1),
                }
                if cursor:
                    kwargs["cursor"] = cursor
                page = self._request(kwargs)
                data = _field(_dict(page), "data", default=[])
                rows.extend(_dict(item) for item in data)
                meta = _field(_dict(page), "meta", default={}) or {}
                cursor = _field(_dict(meta), "cursor")
                if not cursor:
                    return rows
                if cursor in seen_cursors:
                    raise TelemetryUnavailable("Langfuse repeated a pagination cursor")
                seen_cursors.add(cursor)
        except TelemetryUnavailable:
            raise
        except Exception as exc:
            raise TelemetryUnavailable("Langfuse observations could not be retrieved") from exc

    def _request(self, kwargs):
        for attempt in range(3):
            time.sleep(max(0, self._next_request - time.monotonic()))
            self._next_request = time.monotonic() + self.request_interval
            try:
                return self.client.api.observations.get_many(**kwargs)
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if status in {401, 403}:
                    raise TelemetryUnavailable("Langfuse authorization failed") from exc
                if attempt == 2 or (status != 429 and (status is None or status < 500)):
                    raise
                headers = getattr(exc, "headers", None) or {}
                delay = float(headers.get("Retry-After", headers.get("retry-after", 2**attempt)))
                if delay > 60:
                    raise TelemetryUnavailable("Langfuse rate limited; retry later") from exc
                self._next_request = time.monotonic() + max(delay, self.request_interval)

    def verify(self, run_id: str) -> TraceSummary:
        try:
            record, rows = self._rows(run_id)
            snapshot = InMemoryTraceProvider([record], rows)
            summary = snapshot.get_trace_summary(run_id)
            snapshot.list_tool_calls(run_id)
            snapshot.get_run_metrics(run_id)
            for observation_id in summary.observation_ids:
                snapshot.inspect_observation(run_id, observation_id)
        except TelemetryUnavailable:
            set_telemetry_status(self.engine, run_id, "unavailable")
            raise
        except ValueError as exc:
            set_telemetry_status(self.engine, run_id, "incomplete")
            raise IncompleteTrace(f"Invalid normalized evidence for run {run_id}") from exc
        set_telemetry_status(self.engine, run_id, summary.telemetry_status)
        if summary.telemetry_status != "verified":
            raise IncompleteTrace(
                f"Incomplete trace for run {run_id}: {', '.join(summary.verification_issues)}"
            )
        return summary


def _db_record(engine: Engine, run_id: str) -> dict:
    record = get_target_run(engine, run_id)
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def local_trace_summary(engine: Engine, run_id: str, *, status: str | None = None) -> TraceSummary:
    return NormalizedTraceProvider._local_summary(_db_record(engine, run_id), status=status)
