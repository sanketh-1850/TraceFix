"""Target A inventory, frozen baseline, and future adapter implementation."""

from tracefix.targets.target_a.baseline import (
    DEFAULT_AGENT_VERSION,
    DEFAULT_BENCHMARK,
    load_agent_version,
    load_benchmark_snapshot,
    load_target_manifest,
)

__all__ = [
    "DEFAULT_AGENT_VERSION",
    "DEFAULT_BENCHMARK",
    "load_agent_version",
    "load_benchmark_snapshot",
    "load_target_manifest",
]
