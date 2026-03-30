"""Basic tests for ChromeLens core modules."""

from chromelens.analysis import LongTask, TraceInsight
from chromelens.analysis.health_scorer import HealthScorer, _grade_from_score, _score_metric
from chromelens.analysis.trace_analyzer import TraceAnalyzer
from chromelens.discovery import DiscoveredPage
from chromelens.profiler import CDPMetrics, PageProfile, WebVitals


def test_discovered_page() -> None:
    page = DiscoveredPage(url="https://example.com", depth=0, source="seed")
    assert page.url == "https://example.com"
    assert page.depth == 0


def test_web_vitals_defaults() -> None:
    vitals = WebVitals()
    assert vitals.lcp_ms == 0.0
    assert vitals.cls == 0.0


def test_cdp_metrics_defaults() -> None:
    metrics = CDPMetrics()
    assert metrics.nodes == 0
    assert metrics.js_heap_used_bytes == 0


def test_score_metric_good() -> None:
    assert _score_metric(500, 2500, 4000) == 100


def test_score_metric_poor() -> None:
    assert _score_metric(5000, 2500, 4000) == 0


def test_score_metric_mid() -> None:
    score = _score_metric(3000, 2500, 4000)
    assert 0 < score < 100


def test_grade_from_score() -> None:
    assert _grade_from_score(95) == "A"
    assert _grade_from_score(80) == "B"
    assert _grade_from_score(60) == "C"
    assert _grade_from_score(40) == "D"
    assert _grade_from_score(20) == "F"


def test_trace_analyzer_empty() -> None:
    analyzer = TraceAnalyzer()
    insight = analyzer.analyze([])
    assert insight.total_blocking_time_ms == 0.0
    assert insight.long_tasks == []


def test_trace_analyzer_long_task() -> None:
    analyzer = TraceAnalyzer()
    events = [
        {"ph": "X", "name": "RunTask", "dur": 100_000, "ts": 0, "cat": "devtools.timeline"},
    ]
    insight = analyzer.analyze(events)
    assert len(insight.long_tasks) == 1
    assert insight.long_tasks[0].duration_ms == 100.0
    assert insight.total_blocking_time_ms == 50.0  # 100ms - 50ms threshold


def test_trace_analyzer_layout() -> None:
    analyzer = TraceAnalyzer()
    events = [
        {"ph": "X", "name": "Layout", "dur": 5000, "ts": 0, "cat": ""},
        {"ph": "X", "name": "Layout", "dur": 3000, "ts": 5000, "cat": ""},
    ]
    insight = analyzer.analyze(events)
    assert insight.layout_count == 2


def test_health_scorer_perfect_page() -> None:
    scorer = HealthScorer()
    profile = PageProfile(
        url="https://example.com",
        vitals=WebVitals(lcp_ms=500, fcp_ms=400, cls=0.01, ttfb_ms=100),
        network_requests=[],
    )
    insight = TraceInsight()
    score = scorer.score_page(profile, insight)
    assert score.score >= 80
    assert score.grade in ("A", "B")


def test_health_scorer_poor_page() -> None:
    scorer = HealthScorer()
    profile = PageProfile(
        url="https://example.com",
        vitals=WebVitals(lcp_ms=6000, fcp_ms=5000, cls=0.5, ttfb_ms=3000),
        network_requests=[],
    )
    insight = TraceInsight(
        total_blocking_time_ms=1000,
        long_tasks=[LongTask(name="t", duration_ms=200, start_ms=0)] * 10,
    )
    score = scorer.score_page(profile, insight)
    assert score.score < 30
    assert score.grade in ("D", "F")
