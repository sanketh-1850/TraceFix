"""Small, vendor-independent records consumed by diagnostic code."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TelemetryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ObservationExcerpt(TelemetryModel):
    run_id: str
    trace_id: str
    observation_id: str
    parent_observation_id: str | None = None
    kind: str
    name: str
    input_excerpt: str | None = None
    output_excerpt: str | None = None
    status_message: str | None = None
    latency_ms: float | None = None
    truncated: bool = False


class ToolCallRecord(TelemetryModel):
    run_id: str
    trace_id: str
    observation_id: str
    local_observation_id: str | None = None
    call_id: str | None = None
    tool: str
    ok: bool | None = None
    source_ids: list[str] = []
    latency_ms: float | None = None
    error: str | None = None


class RunMetrics(TelemetryModel):
    run_id: str
    trace_id: str | None
    model_calls: int
    tool_calls: int
    tool_errors: int | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float | None
    usage_complete: bool


class TraceSummary(TelemetryModel):
    run_id: str
    trace_id: str | None
    target_id: str
    task_id: str
    agent_version_id: str
    dataset_version: str
    benchmark_version: str | None
    model_id: str
    status: str
    terminal_reason: str
    telemetry_status: Literal["disabled", "pending", "unavailable", "incomplete", "verified"]
    started_at: datetime
    metrics: RunMetrics
    observation_ids: list[str]
    verification_issues: list[str] = Field(default_factory=list)


class RunListFilters(TelemetryModel):
    target_id: str | None = "target-a"
    task_id: str | None = None
    agent_version_id: str | None = None
    dataset_version: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


def excerpt(value: Any, limit: int = 4000) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if not isinstance(value, str):
        import json

        value = json.dumps(value, sort_keys=True, default=str)
    if len(value) <= limit:
        return value, False
    return value[:limit] + "...[truncated]", True
