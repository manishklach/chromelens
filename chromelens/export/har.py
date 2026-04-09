"""HAR export helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from chromelens.profiler import NetworkRequest, PageProfile


def export_har_files(profiles: list[PageProfile], output_dir: Path, mode: str) -> dict[str, str]:
    """Export per-page and/or combined HAR files from captured network data."""
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}

    if mode in {"per-page", "both"}:
        for profile in profiles:
            page_name = _safe_name(profile.url)
            har_path = output_dir / f"{page_name}.har"
            har_path.write_text(json.dumps(_build_har_document(profile.network_requests, profile.url), indent=2), encoding="utf-8")
            mapping[profile.url] = str(har_path)
            profile.har_path = str(har_path)

    if mode in {"combined", "both"}:
        combined_requests: list[NetworkRequest] = []
        for profile in profiles:
            combined_requests.extend(profile.network_requests)
        combined_path = output_dir / "combined.har"
        combined_path.write_text(json.dumps(_build_har_document(combined_requests, "combined"), indent=2), encoding="utf-8")
        mapping["__combined__"] = str(combined_path)

    return mapping


def _build_har_document(requests: list[NetworkRequest], label: str) -> dict:
    started = datetime.now(UTC).isoformat()
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "ChromeLens", "version": "0.2.0"},
            "pages": [
                {
                    "startedDateTime": started,
                    "id": label,
                    "title": label,
                    "pageTimings": {},
                }
            ],
            "entries": [
                {
                    "startedDateTime": started,
                    "time": float(request.duration_ms),
                    "request": {
                        "method": request.method,
                        "url": request.url,
                        "httpVersion": "HTTP/1.1",
                        "cookies": [],
                        "headers": [],
                        "queryString": [],
                        "headersSize": -1,
                        "bodySize": -1,
                    },
                    "response": {
                        "status": request.status,
                        "statusText": "",
                        "httpVersion": "HTTP/1.1",
                        "cookies": [],
                        "headers": [],
                        "content": {
                            "size": request.size_bytes,
                            "mimeType": request.mime_type,
                        },
                        "redirectURL": "",
                        "headersSize": -1,
                        "bodySize": request.size_bytes,
                    },
                    "cache": {},
                    "timings": {
                        "blocked": 0,
                        "dns": -1,
                        "connect": -1,
                        "send": 0,
                        "wait": max(0.0, float(request.duration_ms)),
                        "receive": 0,
                        "ssl": -1,
                    },
                    "pageref": label,
                }
                for request in requests
            ],
        }
    }


def _safe_name(url: str) -> str:
    parsed = urlparse(url)
    name = parsed.path.strip("/").replace("/", "_") or "index"
    return name
