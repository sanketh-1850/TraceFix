"""Early cross-target boundaries; concrete implementations arrive in later epics."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from tracefix.telemetry.schemas import ObservationExcerpt, RunMetrics, ToolCallRecord, TraceSummary


@runtime_checkable
class TraceProvider(Protocol):
    """Return normalized trace evidence without exposing vendor-specific objects."""

    def get_trace_summary(self, run_id: str) -> TraceSummary: ...

    def list_tool_calls(self, run_id: str) -> Sequence[ToolCallRecord]: ...

    def inspect_observation(self, run_id: str, observation_id: str) -> ObservationExcerpt: ...

    def get_run_metrics(self, run_id: str) -> RunMetrics: ...

    def list_runs(self, filters: dict | None = None) -> Sequence[TraceSummary]: ...


@runtime_checkable
class TargetAdapter(Protocol):
    """Run a named target version through a target-independent boundary."""

    @property
    def target_id(self) -> str: ...

    def run(self, task_id: str, agent_version_id: str) -> Any: ...


@runtime_checkable
class EvaluationAdapter(Protocol):
    """Evaluate a target version on a named, frozen dataset split."""

    @property
    def evaluator_version(self) -> str: ...

    def evaluate(
        self, agent_version_id: str, dataset_version: str, split: str
    ) -> Mapping[str, Any]: ...
