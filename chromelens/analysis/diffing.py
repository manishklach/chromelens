"""Artifact-to-artifact diffing for ChromeLens runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chromelens.artifacts.models import (
    ARTIFACT_SCHEMA_VERSION,
    DiffArtifact,
    DiffEntryArtifact,
    DiffSummaryArtifact,
    MetricDeltaArtifact,
)
from chromelens.artifacts.serializer import read_artifact_json


def load_run_artifact(path: Path) -> dict[str, Any]:
    """Load a run artifact and perform minimal validation."""
    payload = read_artifact_json(path)
    if payload.get("artifact_type") != "run":
        raise ValueError(f"{path} is not a ChromeLens run artifact")
    schema_version = str(payload.get("schema_version", ""))
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"{path} uses unsupported ChromeLens schema_version '{schema_version}'. "
            f"Expected '{ARTIFACT_SCHEMA_VERSION}'."
        )
    return payload


def diff_run_artifacts(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    baseline_ref: str,
    candidate_ref: str,
    max_tbt_regression_pct: float | None = None,
    max_new_long_tasks: int | None = None,
    max_cls_regression: float | None = None,
    max_script_duration_regression_pct: float | None = None,
) -> DiffArtifact:
    """Diff two run artifacts into a reusable diff artifact."""
    page_diffs = _diff_collection(
        baseline.get("pages", []),
        candidate.get("pages", []),
        key_field="url",
        label_field="url",
        metric_fields=["score", "lcp_ms", "cls", "total_blocking_time_ms", "long_task_count", "script_duration_ms"],
    )
    template_diffs = _diff_collection(
        baseline.get("templates", []),
        candidate.get("templates", []),
        key_field="signature",
        label_field="label",
        metric_fields=[
            "page_count",
            ("tbt_summary", "p50"),
            ("tbt_summary", "p75"),
            ("tbt_summary", "p95"),
            ("tbt_summary", "p99"),
            ("lcp_summary", "p75"),
            ("cls_summary", "p75"),
        ],
    )
    third_party_diffs = _diff_collection(
        baseline.get("third_party_summary", []),
        candidate.get("third_party_summary", []),
        key_field="domain",
        label_field="domain",
        metric_fields=["total_bytes", "request_count", "total_blocking_time_ms", "script_execution_ms", "long_task_count"],
    )

    threshold_results = _evaluate_thresholds(
        page_diffs=page_diffs,
        max_tbt_regression_pct=max_tbt_regression_pct,
        max_new_long_tasks=max_new_long_tasks,
        max_cls_regression=max_cls_regression,
        max_script_duration_regression_pct=max_script_duration_regression_pct,
    )

    summary = _build_summary(page_diffs + template_diffs + third_party_diffs)
    summary.failed_thresholds = [name for name, passed in threshold_results.items() if not passed]

    return DiffArtifact(
        baseline_ref=baseline_ref,
        candidate_ref=candidate_ref,
        summary=summary,
        page_diffs=page_diffs,
        template_diffs=template_diffs,
        third_party_diffs=third_party_diffs,
        threshold_results=threshold_results,
    )


def _diff_collection(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    key_field: str,
    label_field: str,
    metric_fields: list[str | tuple[str, str]],
) -> list[DiffEntryArtifact]:
    baseline_map = {str(row.get(key_field, "")): row for row in baseline_rows}
    candidate_map = {str(row.get(key_field, "")): row for row in candidate_rows}
    all_keys = sorted(set(baseline_map) | set(candidate_map))
    diffs: list[DiffEntryArtifact] = []

    for key in all_keys:
        base = baseline_map.get(key)
        cand = candidate_map.get(key)
        if base is None:
            notes = [f"New third-party domain detected: {key}"] if key_field == "domain" else []
            diffs.append(DiffEntryArtifact(key=key, label=str(cand.get(label_field, key)), status="added", notes=notes))
            continue
        if cand is None:
            diffs.append(DiffEntryArtifact(key=key, label=str(base.get(label_field, key)), status="removed"))
            continue

        metrics: dict[str, MetricDeltaArtifact] = {}
        statuses: set[str] = set()
        notes: list[str] = []
        for field in metric_fields:
            metric_name = field if isinstance(field, str) else ".".join(field)
            baseline_value = float(_resolve_field(base, field))
            candidate_value = float(_resolve_field(cand, field))
            delta = candidate_value - baseline_value
            percent_delta = None
            zero_baseline = False
            if baseline_value != 0:
                percent_delta = (delta / baseline_value) * 100.0
            elif candidate_value != 0:
                zero_baseline = True

            status = _classify_metric(metric_name, delta)
            statuses.add(status)
            metrics[metric_name] = MetricDeltaArtifact(
                baseline=baseline_value,
                candidate=candidate_value,
                absolute_delta=delta,
                percent_delta=percent_delta,
                zero_baseline=zero_baseline,
                status=status,
            )

        entry_status = "unchanged"
        if "regression" in statuses:
            entry_status = "regression"
        elif "improvement" in statuses:
            entry_status = "improvement"

        if "total_blocking_time_ms" in metrics and metrics["total_blocking_time_ms"].status == "regression":
            notes.append("Blocking time increased on this entry.")
        if "script_duration_ms" in metrics and metrics["script_duration_ms"].status == "regression":
            notes.append("Script execution time increased on this entry.")
        if any(metric.zero_baseline and metric.status == "regression" for metric in metrics.values()):
            notes.append("Regression from a zero baseline requires absolute-delta review.")

        diffs.append(
            DiffEntryArtifact(
                key=key,
                label=str(cand.get(label_field, base.get(label_field, key))),
                status=entry_status,
                metrics=metrics,
                notes=notes,
            )
        )

    return diffs


def _resolve_field(row: dict[str, Any], field: str | tuple[str, str]) -> float:
    if isinstance(field, str):
        return float(row.get(field, 0.0) or 0.0)
    parent, child = field
    nested = row.get(parent, {}) or {}
    if isinstance(nested, dict):
        return float(nested.get(child, 0.0) or 0.0)
    return 0.0


def _classify_metric(metric_name: str, delta: float) -> str:
    if abs(delta) < 1e-9:
        return "unchanged"
    lower_is_better = metric_name != "score"
    if lower_is_better:
        return "regression" if delta > 0 else "improvement"
    return "regression" if delta < 0 else "improvement"


def _build_summary(entries: list[DiffEntryArtifact]) -> DiffSummaryArtifact:
    summary = DiffSummaryArtifact()
    for entry in entries:
        if entry.status == "regression":
            summary.regressions += 1
        elif entry.status == "improvement":
            summary.improvements += 1
        elif entry.status == "added":
            summary.added += 1
        elif entry.status == "removed":
            summary.removed += 1
        else:
            summary.unchanged += 1
    return summary


def _evaluate_thresholds(
    *,
    page_diffs: list[DiffEntryArtifact],
    max_tbt_regression_pct: float | None,
    max_new_long_tasks: int | None,
    max_cls_regression: float | None,
    max_script_duration_regression_pct: float | None,
) -> dict[str, bool]:
    results: dict[str, bool] = {}

    if max_tbt_regression_pct is not None:
        worst = max(
            (
                _threshold_delta_value(diff.metrics["total_blocking_time_ms"])
                for diff in page_diffs
                if "total_blocking_time_ms" in diff.metrics
            ),
            default=0.0,
        )
        results["max_tbt_regression_pct"] = worst <= max_tbt_regression_pct

    if max_new_long_tasks is not None:
        worst = max(
            (
                diff.metrics["long_task_count"].absolute_delta
                for diff in page_diffs
                if "long_task_count" in diff.metrics
            ),
            default=0.0,
        )
        results["max_new_long_tasks"] = worst <= max_new_long_tasks

    if max_cls_regression is not None:
        worst = max(
            (
                diff.metrics["cls"].absolute_delta
                for diff in page_diffs
                if "cls" in diff.metrics
            ),
            default=0.0,
        )
        results["max_cls_regression"] = worst <= max_cls_regression

    if max_script_duration_regression_pct is not None:
        worst = max(
            (
                _threshold_delta_value(diff.metrics["script_duration_ms"])
                for diff in page_diffs
                if "script_duration_ms" in diff.metrics
            ),
            default=0.0,
        )
        results["max_script_duration_regression_pct"] = worst <= max_script_duration_regression_pct

    return results


def _threshold_delta_value(metric: MetricDeltaArtifact) -> float:
    """Return a deterministic threshold comparison value for percent-based metrics."""
    if metric.status != "regression":
        return 0.0
    if metric.percent_delta is not None:
        return metric.percent_delta
    if metric.zero_baseline and metric.candidate > 0:
        return float("inf")
    return 0.0
