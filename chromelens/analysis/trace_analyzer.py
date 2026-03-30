"""Trace analyzer — extracts bottleneck signals from Chrome trace JSON."""

from __future__ import annotations

import logging
from typing import Any

from . import FilmstripFrame, LongTask, TraceInsight

LOGGER = logging.getLogger(__name__)

LONG_TASK_THRESHOLD_US = 50_000  # 50ms in microseconds


class TraceAnalyzer:
    """Parse Chrome trace events and extract performance signals."""

    def analyze(self, trace_events: list[dict[str, Any]]) -> TraceInsight:
        """Extract insights from a list of Chrome trace events."""
        insight = TraceInsight()

        BIN_SIZE_MS = 100
        cpu_bins: dict[int, float] = {}

        for event in trace_events:
            ph = event.get("ph", "")
            cat = event.get("cat", "")
            name = event.get("name", "")
            dur = event.get("dur", 0)  # microseconds
            ts = event.get("ts", 0)

            ts_ms = ts / 1000.0

            # CPU time (sum duration for complete events into 100ms bins)
            if ph == "X" and dur > 0:
                bin_idx = int(ts_ms // BIN_SIZE_MS)
                cpu_bins[bin_idx] = cpu_bins.get(bin_idx, 0.0) + (dur / 1000.0)

            # Memory timeline
            if name == "UpdateCounters" and "data" in event.get("args", {}):
                js_mem = event["args"]["data"].get("jsHeapSizeUsed")
                if js_mem is not None:
                    from chromelens.profiler import TimeSeriesMetric
                    insight.memory_timeline.append(TimeSeriesMetric(timestamp_ms=ts_ms, value=float(js_mem)))

            # Long tasks (X = complete events on main thread)
            if ph == "X" and dur >= LONG_TASK_THRESHOLD_US:
                blocking_time = (dur - LONG_TASK_THRESHOLD_US) / 1000.0  # to ms
                insight.total_blocking_time_ms += blocking_time
                insight.long_tasks.append(LongTask(
                    name=name,
                    duration_ms=dur / 1000.0,
                    start_ms=ts / 1000.0,
                    category=cat,
                ))

            # Layout events
            if name == "Layout" and ph == "X":
                insight.layout_count += 1

            # Style recalculations
            if name in ("RecalcStyles", "UpdateLayoutTree") and ph == "X":
                insight.style_recalc_count += 1

            # Script compilation
            if name in ("v8.compile", "V8.CompileCode", "v8.parseOnBackground") and ph == "X":
                insight.script_compile_events += 1

            # Garbage collection
            if "GC" in name or name in ("MinorGC", "MajorGC", "V8.GC"):
                insight.gc_events += 1
                insight.gc_duration_ms += dur / 1000.0

            # Paint events
            if name in ("Paint", "PaintImage", "CompositeLayers") and ph == "X":
                insight.paint_count += 1

            # Filmstrip Screenshots
            if name == "Screenshot" and "snapshot" in event.get("args", {}):
                insight.filmstrip.append(FilmstripFrame(
                    timestamp_ms=ts / 1000.0,
                    base64_data=event["args"]["snapshot"]
                ))

        # Sort long tasks by duration descending
        insight.long_tasks.sort(key=lambda t: t.duration_ms, reverse=True)

        # Downsample filmstrip to max 10 frames evenly spaced
        insight.filmstrip.sort(key=lambda f: f.timestamp_ms)
        if len(insight.filmstrip) > 10:
            step = len(insight.filmstrip) / 10.0
            insight.filmstrip = [insight.filmstrip[int(i * step)] for i in range(10)]

        # Find the absolute start time across trace to normalize all timelines
        start_ts = 0.0
        if insight.filmstrip:
            start_ts = insight.filmstrip[0].timestamp_ms
        elif cpu_bins:
            start_ts = min(cpu_bins.keys()) * BIN_SIZE_MS

        from chromelens.profiler import TimeSeriesMetric

        # Populate CPU timeline from bins
        for bin_idx, duration in sorted(cpu_bins.items()):
            bin_ts = (bin_idx * BIN_SIZE_MS) - start_ts
            if bin_ts >= 0:
                insight.cpu_timeline.append(TimeSeriesMetric(timestamp_ms=bin_ts, value=duration))

        # Normalize memory timeline
        normalized_mem = []
        for point in insight.memory_timeline:
            rel_ts = point.timestamp_ms - start_ts
            if rel_ts >= 0:
                point.timestamp_ms = rel_ts
                normalized_mem.append(point)
        insight.memory_timeline = sorted(normalized_mem, key=lambda p: p.timestamp_ms)

        # Normalize filmstrip timestamps
        if insight.filmstrip:
            for frame in insight.filmstrip:
                frame.timestamp_ms -= start_ts

        return insight
