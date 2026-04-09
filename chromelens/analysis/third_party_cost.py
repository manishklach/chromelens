"""Approximate third-party cost attribution helpers."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse

from chromelens.analysis import TraceInsight
from chromelens.artifacts.models import ThirdPartyArtifact
from chromelens.profiler import NetworkRequest, PageProfile


def analyze_page_third_party_cost(profile: PageProfile, insight: TraceInsight, site_origin: str) -> list[ThirdPartyArtifact]:
    """Approximate third-party cost on a page using network and script shares."""
    site_netloc = urlparse(site_origin).netloc
    rows: dict[str, ThirdPartyArtifact] = {}
    third_party_requests = [request for request in profile.network_requests if _is_external(request, site_netloc)]
    if not third_party_requests:
        return []

    script_requests = [request for request in third_party_requests if _is_script(request)]
    total_script_bytes = sum(request.size_bytes for request in script_requests) or 0
    total_third_party_bytes = sum(request.size_bytes for request in third_party_requests) or 1

    for request in third_party_requests:
        row = rows.get(request.domain)
        if row is None:
            row = ThirdPartyArtifact(
                key=request.domain,
                domain=request.domain,
                ownership="third_party",
            )
            rows[request.domain] = row

        row.request_count += 1
        row.total_bytes += request.size_bytes
        row.total_duration_ms += request.duration_ms

    script_rows = defaultdict(int)
    for request in script_requests:
        script_rows[request.domain] += request.size_bytes

    for row in rows.values():
        if total_script_bytes > 0 and script_rows.get(row.domain):
            share = script_rows[row.domain] / total_script_bytes
            row.attribution_confidence = "medium"
            row.attribution_method = "script_byte_share"
            row.notes.append("Estimated from third-party script byte share.")
        else:
            share = row.total_bytes / total_third_party_bytes
            row.attribution_confidence = "low"
            row.attribution_method = "total_byte_share"
            row.notes.append("Estimated from total third-party byte share.")

        row.total_blocking_time_ms = insight.total_blocking_time_ms * share
        row.script_execution_ms = profile.cdp_metrics.script_duration_ms * share
        row.long_task_count = int(round(len(insight.long_tasks) * share))
        row.pages_present = 1

    return sorted(
        rows.values(),
        key=lambda item: (item.total_blocking_time_ms, item.script_execution_ms, item.total_bytes, item.domain),
        reverse=True,
    )


def aggregate_third_party_cost(
    pages: list[ThirdPartyArtifact],
    *,
    templates_by_domain: dict[str, set[str]] | None = None,
) -> list[ThirdPartyArtifact]:
    """Aggregate page-level third-party rows into a site-level wall of shame."""
    aggregated: dict[str, ThirdPartyArtifact] = {}
    for page_row in pages:
        row = aggregated.get(page_row.domain)
        if row is None:
            row = ThirdPartyArtifact(
                key=page_row.key,
                domain=page_row.domain,
                ownership=page_row.ownership,
            )
            aggregated[page_row.domain] = row
        row.request_count += page_row.request_count
        row.total_bytes += page_row.total_bytes
        row.total_duration_ms += page_row.total_duration_ms
        row.total_blocking_time_ms += page_row.total_blocking_time_ms
        row.script_execution_ms += page_row.script_execution_ms
        row.long_task_count += page_row.long_task_count
        row.pages_present += page_row.pages_present
        if page_row.attribution_confidence == "medium":
            row.attribution_confidence = "medium"
        if row.attribution_method != "script_byte_share" and page_row.attribution_method:
            row.attribution_method = page_row.attribution_method
        row.notes.extend(page_row.notes)

    for domain, row in aggregated.items():
        if templates_by_domain:
            row.templates_present = len(templates_by_domain.get(domain, set()))
        row.notes = _normalize_notes(row.notes, row.attribution_method)

    return sorted(
        aggregated.values(),
        key=lambda item: (item.total_blocking_time_ms, item.script_execution_ms, item.total_bytes, item.domain),
        reverse=True,
    )


def _is_external(request: NetworkRequest, site_netloc: str) -> bool:
    return bool(request.domain and request.domain != site_netloc)


def _is_script(request: NetworkRequest) -> bool:
    return request.resource_type == "script" or "javascript" in request.mime_type.lower()


def _normalize_notes(notes: list[str], attribution_method: str) -> list[str]:
    """Deduplicate page-level notes into one stable site-level explanation."""
    normalized = sorted({note.strip() for note in notes if note.strip()})
    if attribution_method == "script_byte_share":
        return ["Estimated from third-party script byte share."]
    if attribution_method == "total_byte_share":
        return ["Estimated from total third-party byte share."]
    return normalized
