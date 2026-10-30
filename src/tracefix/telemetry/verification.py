"""Bounded, resumable verification of a frozen development evaluation."""

import json
import time
from pathlib import Path

from tracefix.targets.target_a.baseline import load_benchmark_snapshot
from tracefix.telemetry.provider import IncompleteTrace, TelemetryUnavailable


def verify_run(provider, run_id: str, wait_seconds: float = 60):
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return provider.verify(run_id)
        except IncompleteTrace:
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(5, max(0, deadline - time.monotonic())))


def verify_evaluation(provider, summary_path: Path, output: Path, wait_seconds: float = 60):
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    benchmark = load_benchmark_snapshot()
    benchmark.verify_current_files()
    expected = benchmark.splits["development"]
    items = summary.get("items", [])
    task_ids = [item.get("task_id") for item in items]
    if (
        summary.get("target_id") != "target-a"
        or summary.get("agent_version_id") != "target-a:a0"
        or summary.get("benchmark_snapshot_id") != benchmark.benchmark_snapshot_id
        or summary.get("dataset_version") != benchmark.dataset_version
        or summary.get("evaluator_version") != benchmark.evaluator_version
        or summary.get("split") != "development"
        or not summary.get("complete")
        or len(task_ids) != len(expected)
        or set(task_ids) != set(expected)
    ):
        raise ValueError("Expected a complete frozen A0 evaluation of the 14 development tasks")
    report = {"summary": str(summary_path), "verified": False, "items": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    for item in items:
        row = {"task_id": item["task_id"], "run_id": item.get("run_id")}
        try:
            if not row["run_id"]:
                raise IncompleteTrace("Evaluation item has no saved run")
            result = verify_run(provider, row["run_id"], wait_seconds)
            if result.task_id != item["task_id"] or result.agent_version_id != "target-a:a0":
                raise IncompleteTrace("Evaluation item does not match indexed run identity")
            row.update(result.model_dump(mode="json"))
        except (KeyError, IncompleteTrace, TelemetryUnavailable) as exc:
            row.update(
                telemetry_status="unavailable"
                if isinstance(exc, TelemetryUnavailable)
                else "incomplete",
                verification_issues=[str(exc)],
            )
        report["items"].append(row)
        report["verified"] = len(report["items"]) == 14 and all(
            entry["telemetry_status"] == "verified" for entry in report["items"]
        )
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
