import json

from tracefix.common.config import Settings
from tracefix.contracts import EvaluationAdapter, TargetAdapter, TraceProvider
from tracefix.evaluation.tasks import EVALUATOR_VERSION, load_tasks, select_tasks
from tracefix.target_agent.config import load_agent_config
from tracefix.targets.target_a.baseline import (
    DEFAULT_MANIFEST,
    build_target_manifest,
    load_agent_version,
    load_benchmark_snapshot,
    load_target_manifest,
)


def test_epic_zero_adapter_boundaries_are_runtime_protocols():
    assert TraceProvider._is_protocol and hasattr(TraceProvider, "get_trace_summary")
    assert TargetAdapter._is_protocol and hasattr(TargetAdapter, "run")
    assert EvaluationAdapter._is_protocol and hasattr(EvaluationAdapter, "evaluate")


def test_committed_target_manifest_is_exported_from_real_tool_schemas():
    expected = build_target_manifest(load_agent_config())
    assert load_target_manifest() == expected
    assert json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8")) == expected
    assert all(not tool["state_changing"] for tool in expected["tools"])
    assert {tool["name"] for tool in expected["tools"]} == {
        "search_documents",
        "query_records",
        "calculator",
        "lookup_policy",
    }


def test_a0_is_frozen_and_matches_current_target_implementation():
    version = load_agent_version()
    version.verify_current_files()
    assert version.agent_version_id == "target-a:a0"
    assert version.agent_config == load_agent_config()
    assert version.mutable_paths
    assert version.immutable_constraints
    overridden = version.model_settings.apply(
        Settings(ollama_model="different", ollama_seed=999, _env_file=None)
    )
    assert overridden.ollama_model == "qwen3:4b"
    assert overridden.ollama_seed == 42


def test_frozen_benchmark_partitions_every_task_and_preserves_strata():
    snapshot = load_benchmark_snapshot()
    snapshot.verify_current_files()
    tasks = load_tasks()
    development = select_tasks(snapshot.task_ids("development"), tasks)
    held_out = select_tasks(snapshot.task_ids("held_out"), tasks)
    assert snapshot.evaluator_version == EVALUATOR_VERSION
    assert len(development) == 14
    assert len(held_out) == 6
    assert {task.task_id for task in development + held_out} == {
        task.task_id for task in tasks
    }
    assert {task.difficulty for task in development} == {"easy", "multi", "recovery"}
    assert {task.difficulty for task in held_out} == {"easy", "multi", "recovery"}
    assert snapshot.optimizer_allowed_splits == ["development"]
