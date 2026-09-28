"""Frozen Target A contracts and integrity checks for the A0 baseline."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from tracefix.common.config import PROJECT_ROOT, Settings
from tracefix.target_agent.config import AgentConfig, digest
from tracefix.target_agent.schemas import StrictModel
from tracefix.target_agent.tools import SCHEMAS

TARGET_A_CONFIG_ROOT = PROJECT_ROOT / "configs/targets/target_a"
DEFAULT_MANIFEST = TARGET_A_CONFIG_ROOT / "manifest.json"
DEFAULT_AGENT_VERSION = TARGET_A_CONFIG_ROOT / "versions/a0.json"
DEFAULT_BENCHMARK = TARGET_A_CONFIG_ROOT / "benchmarks/order-support-v1.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenModelSettings(StrictModel):
    provider: Literal["ollama"] = "ollama"
    model: str
    num_ctx: int = Field(ge=1024)
    temperature: float = Field(ge=0, le=2)
    seed: int
    timeout_seconds: float = Field(gt=0)

    def apply(self, settings: Settings) -> Settings:
        return settings.model_copy(
            update={
                "ollama_model": self.model,
                "ollama_num_ctx": self.num_ctx,
                "ollama_temperature": self.temperature,
                "ollama_seed": self.seed,
                "ollama_timeout_seconds": self.timeout_seconds,
            }
        )


class AgentVersionSnapshot(StrictModel):
    schema_version: Literal[1]
    agent_version_id: str
    target_id: Literal["target-a"]
    status: Literal["frozen"]
    created_at: str
    source_commit: str
    benchmark_snapshot_id: str
    manifest_hash: str
    implementation_files: list[str]
    implementation_hash: str
    agent_config: AgentConfig
    model_settings: FrozenModelSettings
    mutable_paths: list[str]
    immutable_constraints: list[str]
    content_hash: str

    @model_validator(mode="after")
    def valid_content_hash(self):
        payload = self.model_dump(exclude={"content_hash"})
        if digest(payload) != self.content_hash:
            raise ValueError("Agent version content hash mismatch")
        return self

    def verify_current_files(self, manifest_path: Path = DEFAULT_MANIFEST) -> None:
        if file_sha256(manifest_path) != self.manifest_hash:
            raise ValueError("Target manifest no longer matches frozen A0")
        hashes = {
            path: file_sha256(PROJECT_ROOT / path) for path in sorted(self.implementation_files)
        }
        if digest(hashes) != self.implementation_hash:
            raise ValueError("Target implementation no longer matches frozen A0")


class BenchmarkSnapshot(StrictModel):
    schema_version: Literal[1]
    benchmark_snapshot_id: str
    target_id: Literal["target-a"]
    dataset_version: str
    evaluator_version: str
    created_at: str
    task_file: str
    task_file_hash: str
    evaluator_file: str
    evaluator_file_hash: str
    split_strategy: str
    optimizer_allowed_splits: list[Literal["development"]]
    final_held_out_split: Literal["held_out"]
    splits: dict[Literal["development", "held_out"], list[str]]
    content_hash: str

    @model_validator(mode="after")
    def validate_snapshot(self):
        payload = self.model_dump(exclude={"content_hash"})
        if digest(payload) != self.content_hash:
            raise ValueError("Benchmark snapshot content hash mismatch")
        development = set(self.splits["development"])
        held_out = set(self.splits["held_out"])
        if not development or not held_out or development & held_out:
            raise ValueError("Benchmark splits must be nonempty and disjoint")
        return self

    def verify_current_files(self) -> None:
        if file_sha256(PROJECT_ROOT / self.task_file) != self.task_file_hash:
            raise ValueError("Task data no longer matches the frozen benchmark")
        if file_sha256(PROJECT_ROOT / self.evaluator_file) != self.evaluator_file_hash:
            raise ValueError("Evaluator no longer matches the frozen benchmark")

    def task_ids(self, split: Literal["development", "held_out", "all"]) -> list[str]:
        if split == "all":
            return self.splits["development"] + self.splits["held_out"]
        return self.splits[split]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_agent_version(path: Path = DEFAULT_AGENT_VERSION) -> AgentVersionSnapshot:
    return AgentVersionSnapshot.model_validate(_read_json(path))


def load_benchmark_snapshot(path: Path = DEFAULT_BENCHMARK) -> BenchmarkSnapshot:
    return BenchmarkSnapshot.model_validate(_read_json(path))


def load_target_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    return _read_json(path)


def build_target_manifest(config: AgentConfig) -> dict[str, Any]:
    """Export the real schemas used by ToolEnvironment, avoiding a hand-written copy."""
    access = {
        "search_documents": "Reads local policy Markdown files.",
        "query_records": "Runs allowlisted, parameterized read-only SQL queries.",
        "calculator": "Evaluates a restricted arithmetic expression in memory.",
        "lookup_policy": "Reads one local policy Markdown file by validated ID.",
    }
    return {
        "schema_version": 1,
        "target_id": "target-a",
        "display_name": "TraceFix order-support agent",
        "orchestration_framework": "LangGraph",
        "agent_config_version": config.version,
        "behavior": {
            "response_contract": ["answer", "facts", "evidence_ids"],
            "requires_retrieved_evidence": True,
            "tool_errors_are_observations": True,
            "tools_execute_sequentially": True,
        },
        "tools": [
            {
                "name": name,
                "description": config.tool_descriptions[name],
                "arguments_schema": schema.model_json_schema(),
                "access": "read_only",
                "state_changing": False,
                "data_access": access[name],
            }
            for name, schema in SCHEMAS.items()
        ],
        "external_dependencies": [
            "Ollama",
            "MariaDB",
            "local policy documents",
        ],
    }
