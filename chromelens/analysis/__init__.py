"""Analysis engine models and package init."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LongTask:
    """A main-thread task exceeding 50ms."""

    name: str
    duration_ms: float
    start_ms: float
    category: str = ""


@dataclass(slots=True)
class ThirdPartyImpact:
    """Aggregated impact of a third-party domain."""

    domain: str
    request_count: int = 0
    total_bytes: int = 0
    total_duration_ms: float = 0.0
    resource_types: list[str] = field(default_factory=list)
    pages_present: int = 0  # how many pages this 3P appears on


@dataclass(slots=True)
class TraceInsight:
    """Extracted insights from a Chrome trace."""

    long_tasks: list[LongTask] = field(default_factory=list)
    total_blocking_time_ms: float = 0.0
    layout_count: int = 0
    style_recalc_count: int = 0
    script_compile_events: int = 0
    gc_events: int = 0
    gc_duration_ms: float = 0.0
    paint_count: int = 0


@dataclass(slots=True)
class PageHealthScore:
    """Health score for a single page."""

    url: str
    title: str = ""
    score: int = 100  # 0-100
    grade: str = "A"  # A, B, C, D, F
    vitals_score: int = 100
    performance_score: int = 100
    network_score: int = 100
    issues: list[str] = field(default_factory=list)


@dataclass
class SiteHealthReport:
    """Aggregate health report for the entire site."""

    site_url: str
    total_pages: int = 0
    site_score: int = 100
    site_grade: str = "A"
    page_scores: list[PageHealthScore] = field(default_factory=list)
    third_party_impacts: list[ThirdPartyImpact] = field(default_factory=list)
    common_issues: list[str] = field(default_factory=list)
    crawl_duration_sec: float = 0.0
