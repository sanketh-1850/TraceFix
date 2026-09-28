"""Early cross-target boundaries; concrete implementations arrive in later epics."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TraceProvider(Protocol):
    """Return normalized trace evidence without exposing vendor-specific objects."""

    def get_trace_summary(self, run_id: str) -> Mapping[str, Any]: ...

    def list_tool_calls(self, run_id: str) -> Sequence[Mapping[str, Any]]: ...


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
