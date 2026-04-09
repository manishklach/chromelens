"""Builders that convert current in-memory models into stable artifacts."""

from __future__ import annotations

import hashlib
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from chromelens import __version__
from chromelens.analysis import PageHealthScore, SiteHealthReport, TraceInsight
from chromelens.analysis.templates import build_template_artifacts, load_route_pattern_rules
from chromelens.artifacts.models import (
    CLSShiftArtifact,
    CrawlConfigArtifact,
    EnvironmentArtifact,
    PageArtifact,
    RunArtifact,
    RunSummaryArtifact,
    ThirdPartyArtifact,
)
from chromelens.profiler import PageProfile


def _page_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def build_run_artifact(
    report: SiteHealthReport,
    profiles: list[PageProfile],
    insights: list[TraceInsight],
    *,
    output_dir: Path,
    max_pages: int,
    max_depth: int,
    headless: bool,
    screenshots: bool,
    filmstrip: bool,
    network: str | None,
    device: str | None,
    template_clustering: str = "off",
    route_patterns: str | None = None,
    export_har: str = "off",
) -> RunArtifact:
    """Build the stable run artifact from current report models."""
    profile_map = {profile.url: profile for profile in profiles}
    insight_map = {profile.url: insight for profile, insight in zip(profiles, insights)}

    pages: list[PageArtifact] = []
    for score in sorted(report.page_scores, key=lambda item: item.url):
        profile = profile_map.get(score.url)
        insight = insight_map.get(score.url)
        if profile is None or insight is None:
            continue

        page_third_parties = sorted(
            _build_page_third_party_rows(profile, insight),
            key=lambda item: (item.total_blocking_time_ms, item.total_bytes, item.domain),
            reverse=True,
        )
        cls_shifts = _build_cls_shift_rows(profile)

        pages.append(
            PageArtifact(
                page_id=_page_id(profile.url),
                url=profile.url,
                normalized_url=profile.url,
                title=profile.title,
                status_code=profile.status_code,
                error=profile.error,
                score=score.score,
                grade=score.grade,
                lcp_ms=profile.vitals.lcp_ms,
                fcp_ms=profile.vitals.fcp_ms,
                cls=profile.vitals.cls,
                ttfb_ms=profile.vitals.ttfb_ms,
                dom_interactive_ms=profile.vitals.dom_interactive_ms,
                dom_complete_ms=profile.vitals.dom_complete_ms,
                load_event_ms=profile.vitals.load_event_ms,
                total_blocking_time_ms=insight.total_blocking_time_ms,
                long_task_count=len(insight.long_tasks),
                longest_long_task_ms=insight.long_tasks[0].duration_ms if insight.long_tasks else 0.0,
                layout_count=insight.layout_count,
                style_recalc_count=insight.style_recalc_count,
                paint_count=insight.paint_count,
                gc_duration_ms=insight.gc_duration_ms,
                script_duration_ms=profile.cdp_metrics.script_duration_ms,
                task_duration_ms=profile.cdp_metrics.task_duration_ms,
                total_bytes=sum(request.size_bytes for request in profile.network_requests),
                third_party_bytes=sum(request.size_bytes for request in profile.network_requests if request.is_third_party),
                third_party_request_count=sum(1 for request in profile.network_requests if request.is_third_party),
                screenshot_path=profile.screenshot_path,
                issues=list(score.issues),
                third_parties=page_third_parties,
                cls_shifts=cls_shifts,
            )
        )

    rules = load_route_pattern_rules(route_patterns)
    pages, templates = build_template_artifacts(
        pages,
        strategy=template_clustering,
        rules=rules,
    )

    third_party_summary = sorted(
        [
            ThirdPartyArtifact(
                key=impact.domain,
                domain=impact.domain,
                request_count=impact.request_count,
                total_bytes=impact.total_bytes,
                total_duration_ms=impact.total_duration_ms,
                pages_present=impact.pages_present,
                attribution_confidence="low",
            )
            for impact in report.third_party_impacts
        ],
        key=lambda item: (item.total_bytes, item.domain),
        reverse=True,
    )

    return RunArtifact(
        generated_at=datetime.now(UTC).isoformat(),
        site_url=report.site_url,
        crawl_config=CrawlConfigArtifact(
            max_pages=max_pages,
            max_depth=max_depth,
            headless=headless,
            screenshots=screenshots,
            filmstrip=filmstrip,
            network=network,
            device=device,
            template_clustering=template_clustering,
            route_patterns=route_patterns,
            export_har=export_har,
        ),
        environment=EnvironmentArtifact(
            python_version=sys.version.split()[0],
            platform=platform.platform(),
            chromelens_version=__version__,
            working_directory=str(output_dir.resolve()),
        ),
        summary=RunSummaryArtifact(
            total_pages=report.total_pages,
            site_score=report.site_score,
            site_grade=report.site_grade,
            crawl_duration_sec=report.crawl_duration_sec,
            template_count=len(templates),
            third_party_count=len(third_party_summary),
            common_issues=list(report.common_issues),
        ),
        pages=pages,
        templates=templates,
        third_party_summary=third_party_summary,
    )


def _build_page_third_party_rows(profile: PageProfile, insight: TraceInsight) -> list[ThirdPartyArtifact]:
    """Create per-page third-party rows using current network-only attribution."""
    rows: dict[str, ThirdPartyArtifact] = {}
    third_party_requests = [request for request in profile.network_requests if request.is_third_party and request.domain]
    if not third_party_requests:
        return []

    total_third_party_bytes = sum(request.size_bytes for request in third_party_requests) or 1
    for request in third_party_requests:
        row = rows.get(request.domain)
        if row is None:
            row = ThirdPartyArtifact(key=request.domain, domain=request.domain)
            rows[request.domain] = row
        row.request_count += 1
        row.total_bytes += request.size_bytes
        row.total_duration_ms += request.duration_ms

    # Approximate blocking time proportionally by third-party bytes for schema v1.
    for row in rows.values():
        byte_share = row.total_bytes / total_third_party_bytes
        row.total_blocking_time_ms = insight.total_blocking_time_ms * byte_share
        row.script_execution_ms = profile.cdp_metrics.script_duration_ms * byte_share
        row.long_task_count = int(round(len(insight.long_tasks) * byte_share))
        row.pages_present = 1
        row.attribution_confidence = "low"
        row.notes.append("Blocking and script time are approximated from byte share in schema v1.")

    return sorted(rows.values(), key=lambda item: item.domain)


def _build_cls_shift_rows(profile: PageProfile) -> list[CLSShiftArtifact]:
    """Convert raw page metadata into artifact shifts if available."""
    shifts: list[CLSShiftArtifact] = []
    raw_shifts = getattr(profile, "layout_shifts", [])
    for raw_shift in raw_shifts:
        shifts.append(
            CLSShiftArtifact(
                timestamp_ms=float(raw_shift.get("timestamp_ms", 0.0)),
                score=float(raw_shift.get("value", 0.0)),
                had_recent_input=bool(raw_shift.get("had_recent_input", False)),
            )
        )
    return shifts
