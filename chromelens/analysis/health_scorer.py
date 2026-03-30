"""Health scorer — computes per-page and site-wide performance scores."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

from chromelens.profiler import PageProfile

from . import PageHealthScore, SiteHealthReport, ThirdPartyImpact, TraceInsight

LOGGER = logging.getLogger(__name__)

# Google Web Vitals thresholds (good / needs-improvement / poor)
LCP_GOOD_MS = 2500
LCP_POOR_MS = 4000
FCP_GOOD_MS = 1800
FCP_POOR_MS = 3000
CLS_GOOD = 0.1
CLS_POOR = 0.25
TTFB_GOOD_MS = 800
TTFB_POOR_MS = 1800
TBT_GOOD_MS = 200
TBT_POOR_MS = 600

GRADE_THRESHOLDS = [
    (90, "A"),
    (75, "B"),
    (55, "C"),
    (35, "D"),
    (0, "F"),
]


def _score_metric(value: float, good: float, poor: float) -> int:
    """Score a single metric on 0-100 scale. Lower is better for the raw value."""
    if value <= good:
        return 100
    if value >= poor:
        return 0
    # Linear interpolation between good and poor
    return max(0, min(100, int(100 * (poor - value) / (poor - good))))


def _grade_from_score(score: int) -> str:
    """Convert a numeric score to a letter grade."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


class HealthScorer:
    """Compute performance health scores for pages and sites."""

    def score_page(self, profile: PageProfile, trace_insight: TraceInsight) -> PageHealthScore:
        """Compute a health score for a single profiled page."""
        issues: list[str] = []

        # Vitals scoring (weighted)
        lcp_score = _score_metric(profile.vitals.lcp_ms, LCP_GOOD_MS, LCP_POOR_MS)
        fcp_score = _score_metric(profile.vitals.fcp_ms, FCP_GOOD_MS, FCP_POOR_MS)
        cls_score = _score_metric(profile.vitals.cls, CLS_GOOD, CLS_POOR)
        ttfb_score = _score_metric(profile.vitals.ttfb_ms, TTFB_GOOD_MS, TTFB_POOR_MS)

        vitals_score = int(0.35 * lcp_score + 0.25 * fcp_score + 0.25 * cls_score + 0.15 * ttfb_score)

        if profile.vitals.lcp_ms > LCP_POOR_MS:
            issues.append(f"LCP is {profile.vitals.lcp_ms:.0f}ms (poor, >4000ms)")
        elif profile.vitals.lcp_ms > LCP_GOOD_MS:
            issues.append(f"LCP is {profile.vitals.lcp_ms:.0f}ms (needs improvement)")

        if profile.vitals.cls > CLS_POOR:
            issues.append(f"CLS is {profile.vitals.cls:.3f} (poor, >0.25)")
        elif profile.vitals.cls > CLS_GOOD:
            issues.append(f"CLS is {profile.vitals.cls:.3f} (needs improvement)")

        # Performance scoring (trace-based)
        tbt_score = _score_metric(trace_insight.total_blocking_time_ms, TBT_GOOD_MS, TBT_POOR_MS)
        long_task_penalty = min(30, len(trace_insight.long_tasks) * 5)
        gc_penalty = min(20, int(trace_insight.gc_duration_ms / 50))
        performance_score = max(0, tbt_score - long_task_penalty - gc_penalty)

        if trace_insight.total_blocking_time_ms > TBT_POOR_MS:
            issues.append(f"Total Blocking Time is {trace_insight.total_blocking_time_ms:.0f}ms (poor)")
        if len(trace_insight.long_tasks) > 5:
            issues.append(f"{len(trace_insight.long_tasks)} long tasks detected on main thread")
        if trace_insight.gc_duration_ms > 100:
            issues.append(f"GC pauses total {trace_insight.gc_duration_ms:.0f}ms")

        # Network scoring
        third_party_reqs = [r for r in profile.network_requests if r.is_third_party]
        total_size = sum(r.size_bytes for r in profile.network_requests)
        third_party_size = sum(r.size_bytes for r in third_party_reqs)

        network_score = 100
        if total_size > 5_000_000:
            network_score -= 30
            issues.append(f"Total page weight: {total_size / 1_000_000:.1f}MB")
        elif total_size > 2_000_000:
            network_score -= 15
            issues.append(f"Page weight: {total_size / 1_000_000:.1f}MB (consider optimizing)")

        if third_party_size > 500_000:
            network_score -= 20
            tp_kb = third_party_size / 1000
            issues.append(f"Third-party scripts: {tp_kb:.0f}KB across {len(third_party_reqs)} requests")

        console_errors = [m for m in profile.console_messages if m.level == "error"]
        if console_errors:
            network_score -= min(10, len(console_errors) * 3)
            issues.append(f"{len(console_errors)} console error(s)")

        network_score = max(0, network_score)

        # Composite score
        composite = int(0.45 * vitals_score + 0.35 * performance_score + 0.20 * network_score)

        if profile.error:
            composite = 0
            issues.insert(0, f"Page error: {profile.error}")

        return PageHealthScore(
            url=profile.url,
            title=profile.title,
            score=composite,
            grade=_grade_from_score(composite),
            vitals_score=vitals_score,
            performance_score=performance_score,
            network_score=network_score,
            issues=issues,
        )

    def score_site(
        self,
        site_url: str,
        page_scores: list[PageHealthScore],
        profiles: list[PageProfile],
        crawl_duration_sec: float,
    ) -> SiteHealthReport:
        """Compute a site-wide health report."""
        if not page_scores:
            return SiteHealthReport(site_url=site_url)

        site_score = int(sum(ps.score for ps in page_scores) / len(page_scores))

        # Third-party impact aggregation
        domain_stats: dict[str, ThirdPartyImpact] = defaultdict(
            lambda: ThirdPartyImpact(domain="")
        )
        for profile in profiles:
            seen_domains: set[str] = set()
            for req in profile.network_requests:
                if req.is_third_party and req.domain:
                    impact = domain_stats[req.domain]
                    impact.domain = req.domain
                    impact.request_count += 1
                    impact.total_bytes += req.size_bytes
                    impact.total_duration_ms += req.duration_ms
                    if req.resource_type not in impact.resource_types:
                        impact.resource_types.append(req.resource_type)
                    if req.domain not in seen_domains:
                        impact.pages_present += 1
                        seen_domains.add(req.domain)

        third_party_impacts = sorted(
            domain_stats.values(),
            key=lambda x: x.total_bytes,
            reverse=True,
        )

        # Common issues across pages
        all_issues: list[str] = []
        for ps in page_scores:
            all_issues.extend(ps.issues)
        issue_counts = Counter(all_issues)
        common_issues = [issue for issue, count in issue_counts.most_common(10) if count >= 2]

        return SiteHealthReport(
            site_url=site_url,
            total_pages=len(page_scores),
            site_score=site_score,
            site_grade=_grade_from_score(site_score),
            page_scores=page_scores,
            third_party_impacts=third_party_impacts,
            common_issues=common_issues,
            crawl_duration_sec=crawl_duration_sec,
        )
