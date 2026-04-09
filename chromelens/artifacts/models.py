"""Versioned artifact dataclasses used for CI-friendly JSON outputs."""

from __future__ import annotations

from dataclasses import dataclass, field


ARTIFACT_SCHEMA_VERSION = "1.0"


@dataclass(slots=True)
class MetricSummaryArtifact:
    """Summary stats for a single numeric metric."""

    count: int = 0
    min: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    max: float = 0.0
    mean: float = 0.0


@dataclass(slots=True)
class CLSCulpritArtifact:
    """Best-effort culprit data for a layout shift."""

    selector: str = ""
    node_id: str = ""
    tag_name: str = ""
    element_id: str = ""
    classes: list[str] = field(default_factory=list)
    previous_rect: dict[str, float] = field(default_factory=dict)
    current_rect: dict[str, float] = field(default_factory=dict)
    confidence: str = "unknown"
    reason: str = ""


@dataclass(slots=True)
class CLSShiftArtifact:
    """A captured layout shift event and its likely culprits."""

    timestamp_ms: float = 0.0
    score: float = 0.0
    had_recent_input: bool = False
    culprits: list[CLSCulpritArtifact] = field(default_factory=list)


@dataclass(slots=True)
class ThirdPartyArtifact:
    """Stable representation of third-party cost metrics."""

    key: str
    domain: str
    ownership: str = "third_party"
    request_count: int = 0
    total_bytes: int = 0
    total_duration_ms: float = 0.0
    total_blocking_time_ms: float = 0.0
    script_execution_ms: float = 0.0
    long_task_count: int = 0
    pages_present: int = 0
    templates_present: int = 0
    attribution_confidence: str = "low"
    attribution_method: str = "unknown"
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PageArtifact:
    """Stable page-level artifact for a single URL."""

    page_id: str
    url: str
    normalized_url: str
    title: str = ""
    template_id: str = ""
    template_signature: str = ""
    template_reason: str = ""
    template_confidence: str = "unknown"
    status_code: int = 0
    error: str | None = None
    score: int = 0
    grade: str = "F"
    lcp_ms: float = 0.0
    fcp_ms: float = 0.0
    cls: float = 0.0
    ttfb_ms: float = 0.0
    dom_interactive_ms: float = 0.0
    dom_complete_ms: float = 0.0
    load_event_ms: float = 0.0
    total_blocking_time_ms: float = 0.0
    long_task_count: int = 0
    longest_long_task_ms: float = 0.0
    layout_count: int = 0
    style_recalc_count: int = 0
    paint_count: int = 0
    gc_duration_ms: float = 0.0
    script_duration_ms: float = 0.0
    task_duration_ms: float = 0.0
    total_bytes: int = 0
    third_party_bytes: int = 0
    third_party_request_count: int = 0
    screenshot_path: str | None = None
    har_path: str | None = None
    issues: list[str] = field(default_factory=list)
    third_parties: list[ThirdPartyArtifact] = field(default_factory=list)
    cls_shifts: list[CLSShiftArtifact] = field(default_factory=list)


@dataclass(slots=True)
class TemplateArtifact:
    """Aggregate artifact for a route template cluster."""

    template_id: str
    signature: str
    label: str
    reason: str = ""
    confidence: str = "unknown"
    page_count: int = 0
    sample_urls: list[str] = field(default_factory=list)
    score_summary: MetricSummaryArtifact = field(default_factory=MetricSummaryArtifact)
    tbt_summary: MetricSummaryArtifact = field(default_factory=MetricSummaryArtifact)
    lcp_summary: MetricSummaryArtifact = field(default_factory=MetricSummaryArtifact)
    cls_summary: MetricSummaryArtifact = field(default_factory=MetricSummaryArtifact)
    long_task_count_summary: MetricSummaryArtifact = field(default_factory=MetricSummaryArtifact)
    third_party_cost_summary: MetricSummaryArtifact = field(default_factory=MetricSummaryArtifact)
    total_third_party_bytes: int = 0
    avg_third_party_bytes: float = 0.0


@dataclass(slots=True)
class CrawlConfigArtifact:
    """CLI/config values that affect a run."""

    max_pages: int = 0
    max_depth: int = 0
    headless: bool = True
    screenshots: bool = False
    filmstrip: bool = False
    network: str | None = None
    device: str | None = None
    template_clustering: str = "off"
    route_patterns: str | None = None
    export_har: str = "off"


@dataclass(slots=True)
class EnvironmentArtifact:
    """Execution environment metadata."""

    python_version: str = ""
    platform: str = ""
    chromelens_version: str = ""
    working_directory: str = ""


@dataclass(slots=True)
class RunSummaryArtifact:
    """Top-level run summary used by reports and CI."""

    total_pages: int = 0
    site_score: int = 0
    site_grade: str = "F"
    crawl_duration_sec: float = 0.0
    template_count: int = 0
    third_party_count: int = 0
    common_issues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunArtifact:
    """Stable ChromeLens run artifact persisted as JSON."""

    schema_version: str = ARTIFACT_SCHEMA_VERSION
    artifact_type: str = "run"
    generated_at: str = ""
    site_url: str = ""
    crawl_config: CrawlConfigArtifact = field(default_factory=CrawlConfigArtifact)
    environment: EnvironmentArtifact = field(default_factory=EnvironmentArtifact)
    summary: RunSummaryArtifact = field(default_factory=RunSummaryArtifact)
    pages: list[PageArtifact] = field(default_factory=list)
    templates: list[TemplateArtifact] = field(default_factory=list)
    third_party_summary: list[ThirdPartyArtifact] = field(default_factory=list)


@dataclass(slots=True)
class MetricDeltaArtifact:
    """Absolute and relative change for a metric."""

    baseline: float = 0.0
    candidate: float = 0.0
    absolute_delta: float = 0.0
    percent_delta: float | None = None
    zero_baseline: bool = False
    status: str = "unchanged"


@dataclass(slots=True)
class DiffEntryArtifact:
    """Diff row for pages, templates, or third parties."""

    key: str
    label: str
    status: str
    metrics: dict[str, MetricDeltaArtifact] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiffSummaryArtifact:
    """Top-level diff summary."""

    regressions: int = 0
    improvements: int = 0
    unchanged: int = 0
    added: int = 0
    removed: int = 0
    failed_thresholds: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiffArtifact:
    """Artifact describing differences between two runs."""

    schema_version: str = ARTIFACT_SCHEMA_VERSION
    artifact_type: str = "diff"
    baseline_ref: str = ""
    candidate_ref: str = ""
    summary: DiffSummaryArtifact = field(default_factory=DiffSummaryArtifact)
    page_diffs: list[DiffEntryArtifact] = field(default_factory=list)
    template_diffs: list[DiffEntryArtifact] = field(default_factory=list)
    third_party_diffs: list[DiffEntryArtifact] = field(default_factory=list)
    threshold_results: dict[str, bool] = field(default_factory=dict)
