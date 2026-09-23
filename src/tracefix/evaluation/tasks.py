"""Private rubrics are stripped before calling the target agent."""

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field

from tracefix.target_agent.config import DATA_ROOT
from tracefix.target_agent.schemas import StrictModel, TargetRunResult, TargetTask


class ExpectedFact(StrictModel):
    value: str | int | bool | None
    rule: Literal["text", "boolean", "decimal", "null"]


class BenchmarkTask(StrictModel):
    task_id: str
    prompt: str
    expected_facts: dict[str, ExpectedFact]
    required_sources: list[str] = Field(default_factory=list)
    required_error: str | None = None
    require_calculator: bool = False
    expected_tools: list[str] = Field(default_factory=list)
    tags: list[str]
    difficulty: Literal["easy", "multi", "recovery"]

    def public_task(self):
        return TargetTask(task_id=self.task_id, prompt=self.prompt)


def load_tasks() -> list[BenchmarkTask]:
    tasks = [
        BenchmarkTask.model_validate_json(line)
        for line in (DATA_ROOT / "tasks/order_support.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    if len({task.task_id for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs")
    return tasks


def fact_matches(expected: ExpectedFact, actual) -> bool:
    if expected.rule == "null":
        return actual is None
    if expected.rule == "boolean":
        return type(actual) is bool and actual == expected.value
    if expected.rule == "text":
        return (
            isinstance(actual, str)
            and actual.strip().casefold() == str(expected.value).strip().casefold()
        )
    if isinstance(actual, bool) or actual is None:
        return False
    try:
        value = Decimal(str(actual))
        return value.is_finite() and abs(value - Decimal(str(expected.value))) <= Decimal("0.01")
    except InvalidOperation:
        return False


def score_task(task: BenchmarkTask, run: TargetRunResult) -> dict:
    reasons = []
    if run.task_id != task.task_id:
        reasons.append("task_id_mismatch")
    if run.status != "completed":
        reasons.append(f"incomplete:{run.terminal_reason}")
    answer = run.answer
    if answer is None:
        reasons.append("missing_answer")
    else:
        for key, expected in task.expected_facts.items():
            if key not in answer.facts or not fact_matches(expected, answer.facts[key]):
                reasons.append(f"incorrect_fact:{key}")
        cited = set(answer.evidence_ids)
        available = {o.observation_id for o in run.observations}
        available.update(s for o in run.observations for s in o.source_ids)
        if not cited or not cited <= available:
            reasons.append("unsupported_evidence")
        # Citing a tool observation counts as citing the source IDs contained in that observation.
        covered = cited | {
            s for o in run.observations if o.observation_id in cited for s in o.source_ids
        }
        if not set(task.required_sources) <= covered:
            reasons.append("missing_required_sources")
        if task.require_calculator and not any(
            o.ok
            and o.tool == "calculator"
            and o.observation_id in cited
            and any(
                f.rule == "decimal" and fact_matches(f, o.data.get("result"))
                for f in task.expected_facts.values()
            )
            for o in run.observations
        ):
            reasons.append("missing_calculation_evidence")
        if task.required_error and not any(
            o.error == task.required_error and o.observation_id in cited for o in run.observations
        ):
            reasons.append("missing_error_evidence")
    used = {o.tool for o in run.observations}
    return {
        "task_id": task.task_id,
        "success": not reasons,
        "reasons": reasons,
        "expected_tools_used": set(task.expected_tools) <= used,
        "tools_used": sorted(used),
    }
