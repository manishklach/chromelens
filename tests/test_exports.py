from pathlib import Path

from chromelens.analysis.cls import build_cls_shift_artifacts
from chromelens.analysis.third_party_cost import aggregate_third_party_cost
from chromelens.artifacts.models import ThirdPartyArtifact
from chromelens.export.har import export_har_files
from chromelens.profiler import NetworkRequest, PageProfile


def test_build_cls_shift_artifacts_preserves_culprits() -> None:
    shifts = build_cls_shift_artifacts(
        [
            {
                "timestamp_ms": 120.0,
                "value": 0.18,
                "had_recent_input": False,
                "sources": [
                    {
                        "selector": "img.hero",
                        "tag_name": "img",
                        "node_id": "hero",
                        "classes": ["hero"],
                        "current_rect": {"x": 10, "y": 15, "width": 200, "height": 100},
                    }
                ],
            }
        ]
    )
    assert shifts[0].culprits[0].selector == "img.hero"
    assert shifts[0].culprits[0].confidence == "high"
    assert shifts[0].culprits[0].element_id == ""


def test_build_cls_shift_artifacts_partial_metadata_stays_distinct() -> None:
    shifts = build_cls_shift_artifacts(
        [
            {
                "timestamp_ms": 120.0,
                "value": 0.18,
                "had_recent_input": False,
                "sources": [
                    {
                        "node_id": "backend-42",
                        "tag_name": "div",
                        "classes": ["banner"],
                    }
                ],
            }
        ]
    )
    culprit = shifts[0].culprits[0]
    assert culprit.node_id == "backend-42"
    assert culprit.element_id == ""
    assert culprit.confidence == "medium"


def test_build_cls_shift_artifacts_no_metadata_case() -> None:
    shifts = build_cls_shift_artifacts(
        [{"timestamp_ms": 120.0, "value": 0.18, "had_recent_input": False, "sources": [{}]}]
    )
    culprit = shifts[0].culprits[0]
    assert culprit.confidence == "low"
    assert culprit.reason == "no culprit metadata available"


def test_export_har_files_per_page(tmp_path: Path) -> None:
    profile = PageProfile(
        url="https://example.com/products/123",
        network_requests=[
            NetworkRequest(
                url="https://cdn.example/script.js",
                method="GET",
                resource_type="script",
                status=200,
                size_bytes=1024,
                duration_ms=42.0,
                domain="cdn.example",
                is_third_party=True,
                mime_type="application/javascript",
            )
        ],
    )
    mapping = export_har_files([profile], tmp_path, "per-page")
    assert profile.url in mapping
    assert Path(mapping[profile.url]).exists()


def test_aggregate_third_party_cost_deduplicates_notes_and_prefers_medium_confidence() -> None:
    rows = [
        ThirdPartyArtifact(
            key="ads.example",
            domain="ads.example",
            attribution_confidence="low",
            attribution_method="total_byte_share",
            notes=["Estimated from total third-party byte share."],
            pages_present=1,
        ),
        ThirdPartyArtifact(
            key="ads.example",
            domain="ads.example",
            attribution_confidence="medium",
            attribution_method="script_byte_share",
            notes=["Estimated from third-party script byte share."],
            pages_present=1,
        ),
    ]
    aggregated = aggregate_third_party_cost(rows, templates_by_domain={"ads.example": {"tpl-a", "tpl-b"}})
    assert aggregated[0].attribution_confidence == "medium"
    assert aggregated[0].attribution_method == "script_byte_share"
    assert aggregated[0].notes == ["Estimated from third-party script byte share."]
    assert aggregated[0].templates_present == 2
