from pathlib import Path

from chromelens.analysis.cls import build_cls_shift_artifacts
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
