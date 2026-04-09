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
