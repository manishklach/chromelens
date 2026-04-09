from pathlib import Path
import json

from chromelens.analysis.diffing import diff_run_artifacts, load_run_artifact


def _run_payload(score: int, tbt_ms: float, cls: float, script_duration_ms: float, template_tbt_p75: float) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "run",
        "site_url": "https://example.com",
        "pages": [
            {
                "url": "https://example.com/products/123",
                "score": score,
                "lcp_ms": 1500,
                "cls": cls,
                "total_blocking_time_ms": tbt_ms,
                "long_task_count": 2,
                "script_duration_ms": script_duration_ms,
            }
        ],
        "templates": [
            {
                "signature": "/products/:id",
                "label": "Product Template",
                "page_count": 1,
                "tbt_summary": {"p50": tbt_ms, "p75": template_tbt_p75, "p95": template_tbt_p75, "p99": template_tbt_p75},
                "lcp_summary": {"p75": 1500},
                "cls_summary": {"p75": cls},
            }
        ],
        "third_party_summary": [
            {
                "domain": "ads.example",
                "total_bytes": 120000,
                "request_count": 3,
                "total_blocking_time_ms": 45,
                "script_execution_ms": 80,
                "long_task_count": 1,
            }
        ],
    }


def test_diff_run_artifacts_detects_regressions() -> None:
    baseline = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    candidate = _run_payload(score=80, tbt_ms=180, cls=0.08, script_duration_ms=120, template_tbt_p75=180)
    diff = diff_run_artifacts(
        baseline,
        candidate,
        baseline_ref="baseline.json",
        candidate_ref="candidate.json",
        max_tbt_regression_pct=20,
        max_cls_regression=0.02,
        max_script_duration_regression_pct=10,
    )
    assert diff.summary.regressions >= 1
    assert "max_tbt_regression_pct" in diff.summary.failed_thresholds
    assert "max_cls_regression" in diff.summary.failed_thresholds


def test_load_run_artifact_from_disk(tmp_path: Path) -> None:
    artifact_path = tmp_path / "run.json"
    artifact_path.write_text(json.dumps(_run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)), encoding="utf-8")
    loaded = load_run_artifact(artifact_path)
    assert loaded["artifact_type"] == "run"


def test_load_run_artifact_rejects_wrong_type(tmp_path: Path) -> None:
    artifact_path = tmp_path / "run.json"
    artifact_path.write_text(json.dumps({"schema_version": "1.0", "artifact_type": "diff"}), encoding="utf-8")
    try:
        load_run_artifact(artifact_path)
    except ValueError as exc:
        assert "not a ChromeLens run artifact" in str(exc)
    else:
        raise AssertionError("Expected ValueError for wrong artifact type")


def test_load_run_artifact_rejects_unsupported_schema(tmp_path: Path) -> None:
    artifact_path = tmp_path / "run.json"
    payload = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    payload["schema_version"] = "999.0"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_run_artifact(artifact_path)
    except ValueError as exc:
        assert "unsupported ChromeLens schema_version" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported schema version")


def test_diff_run_artifacts_zero_baseline_positive_tbt_is_regression() -> None:
    baseline = _run_payload(score=90, tbt_ms=0, cls=0.0, script_duration_ms=0, template_tbt_p75=0)
    candidate = _run_payload(score=85, tbt_ms=50, cls=0.0, script_duration_ms=0, template_tbt_p75=50)
    diff = diff_run_artifacts(
        baseline,
        candidate,
        baseline_ref="baseline.json",
        candidate_ref="candidate.json",
        max_tbt_regression_pct=10,
    )
    metric = diff.page_diffs[0].metrics["total_blocking_time_ms"]
    assert metric.zero_baseline is True
    assert metric.percent_delta is None
    assert "max_tbt_regression_pct" in diff.summary.failed_thresholds


def test_diff_run_artifacts_zero_baseline_positive_script_duration_is_regression() -> None:
    baseline = _run_payload(score=90, tbt_ms=0, cls=0.0, script_duration_ms=0, template_tbt_p75=0)
    candidate = _run_payload(score=85, tbt_ms=0, cls=0.0, script_duration_ms=25, template_tbt_p75=0)
    diff = diff_run_artifacts(
        baseline,
        candidate,
        baseline_ref="baseline.json",
        candidate_ref="candidate.json",
        max_script_duration_regression_pct=5,
    )
    metric = diff.page_diffs[0].metrics["script_duration_ms"]
    assert metric.zero_baseline is True
    assert "max_script_duration_regression_pct" in diff.summary.failed_thresholds


def test_diff_run_artifacts_zero_to_zero_is_unchanged() -> None:
    baseline = _run_payload(score=90, tbt_ms=0, cls=0.0, script_duration_ms=0, template_tbt_p75=0)
    candidate = _run_payload(score=90, tbt_ms=0, cls=0.0, script_duration_ms=0, template_tbt_p75=0)
    diff = diff_run_artifacts(baseline, candidate, baseline_ref="a", candidate_ref="b")
    metric = diff.page_diffs[0].metrics["total_blocking_time_ms"]
    assert metric.zero_baseline is False
    assert metric.status == "unchanged"


def test_diff_run_artifacts_added_entry_is_not_regression() -> None:
    baseline = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    candidate = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    candidate["pages"].append({"url": "https://example.com/new", "score": 70, "lcp_ms": 2000, "cls": 0.1, "total_blocking_time_ms": 40, "long_task_count": 1, "script_duration_ms": 10})
    diff = diff_run_artifacts(baseline, candidate, baseline_ref="a", candidate_ref="b")
    added = next(entry for entry in diff.page_diffs if entry.key == "https://example.com/new")
    assert added.status == "added"


def test_diff_run_artifacts_removed_entry_is_not_regression() -> None:
    baseline = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    baseline["pages"].append({"url": "https://example.com/old", "score": 70, "lcp_ms": 2000, "cls": 0.1, "total_blocking_time_ms": 40, "long_task_count": 1, "script_duration_ms": 10})
    candidate = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    diff = diff_run_artifacts(baseline, candidate, baseline_ref="a", candidate_ref="b")
    removed = next(entry for entry in diff.page_diffs if entry.key == "https://example.com/old")
    assert removed.status == "removed"


def test_diff_run_artifacts_missing_nested_metric_diffs_safely() -> None:
    baseline = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    candidate = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    del candidate["templates"][0]["cls_summary"]
    diff = diff_run_artifacts(baseline, candidate, baseline_ref="a", candidate_ref="b")
    template_entry = diff.template_diffs[0]
    assert "cls_summary.p75" in template_entry.metrics


def test_diff_run_artifacts_note_wording_is_literal() -> None:
    baseline = _run_payload(score=90, tbt_ms=120, cls=0.03, script_duration_ms=90, template_tbt_p75=120)
    candidate = _run_payload(score=85, tbt_ms=180, cls=0.03, script_duration_ms=120, template_tbt_p75=180)
    diff = diff_run_artifacts(baseline, candidate, baseline_ref="a", candidate_ref="b")
    notes = diff.page_diffs[0].notes
    assert "Blocking time increased on this entry." in notes
    assert "Script execution time increased on this entry." in notes
