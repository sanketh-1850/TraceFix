"""Runtime contracts. Expected answers deliberately live outside this module."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetTask(StrictModel):
    task_id: str
    prompt: str


class TargetAnswer(StrictModel):
    answer: str = Field(min_length=1)
    facts: dict[str, StrictStr | StrictInt | StrictFloat | StrictBool | None]
    evidence_ids: list[str]


class Observation(StrictModel):
    observation_id: str
    call_id: str
    tool: str
    arguments: dict[str, Any]
    ok: bool
    data: Any = None
    source_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    truncated: bool = False
    latency_ms: float = 0


class TargetRunResult(StrictModel):
    run_id: str
    task_id: str
    prompt: str
    started_at: str
    config_hash: str
    data_hash: str | None
    model: str
    model_settings: dict[str, Any]
    status: Literal["completed", "failed"]
    terminal_reason: str
    answer: TargetAnswer | None = None
    observations: list[Observation]
    messages: list[dict[str, Any]]
    model_calls: int
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    injected_failure: bool = False
