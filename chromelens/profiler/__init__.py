"""Profiler engine models and package init."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WebVitals:
    """Core Web Vitals and supporting metrics."""

    lcp_ms: float = 0.0   # Largest Contentful Paint
    fcp_ms: float = 0.0   # First Contentful Paint
    cls: float = 0.0       # Cumulative Layout Shift
    ttfb_ms: float = 0.0  # Time to First Byte
    dom_interactive_ms: float = 0.0
    dom_complete_ms: float = 0.0
    load_event_ms: float = 0.0


@dataclass(slots=True)
class CDPMetrics:
    """Chrome DevTools Protocol Performance.getMetrics snapshot."""

    timestamp: float = 0.0
    documents: int = 0
    frames: int = 0
    js_event_listeners: int = 0
    nodes: int = 0
    layout_count: int = 0
    recalc_style_count: int = 0
    layout_duration_ms: float = 0.0
    recalc_style_duration_ms: float = 0.0
    script_duration_ms: float = 0.0
    task_duration_ms: float = 0.0
    js_heap_used_bytes: int = 0
    js_heap_total_bytes: int = 0


@dataclass(slots=True)
class NetworkRequest:
    """A captured network request."""

    url: str
    method: str = "GET"
    resource_type: str = "other"
    status: int = 0
    size_bytes: int = 0
    duration_ms: float = 0.0
    domain: str = ""
    is_third_party: bool = False
    mime_type: str = ""


@dataclass(slots=True)
class ConsoleMessage:
    """A captured browser console message."""

    level: str  # "log", "warning", "error"
    text: str
    url: str = ""


@dataclass(slots=True)
class SystemMetrics:
    """Snapshot of hardware metrics from browser processes."""

    renderer_cpu_time_sec: float = 0.0
    renderer_memory_bytes: int = 0
    gpu_memory_bytes: int = 0
    gpu_cpu_time_sec: float = 0.0


@dataclass(slots=True)
class TimeSeriesMetric:
    """Time-series data point for charting."""

    timestamp_ms: float
    value: float


@dataclass
class PageProfile:
    """Complete performance profile for a single page."""

    url: str
    status_code: int = 200
    title: str = ""
    vitals: WebVitals = field(default_factory=WebVitals)
    cdp_metrics: CDPMetrics = field(default_factory=CDPMetrics)
    system_metrics: SystemMetrics = field(default_factory=SystemMetrics)
    cpu_timeline: list[TimeSeriesMetric] = field(default_factory=list)
    memory_timeline: list[TimeSeriesMetric] = field(default_factory=list)
    network_requests: list[NetworkRequest] = field(default_factory=list)
    console_messages: list[ConsoleMessage] = field(default_factory=list)
    trace_events: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    layout_shifts: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    screenshot_path: str | None = None
    har_path: str | None = None
    error: str | None = None
    profile_duration_ms: float = 0.0
