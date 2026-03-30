"""Trace analyzer — extracts bottleneck signals from Chrome trace JSON."""

from __future__ import annotations

import logging
from typing import Any

from . import LongTask, TraceInsight

LOGGER = logging.getLogger(__name__)

LONG_TASK_THRESHOLD_US = 50_000  # 50ms in microseconds


class TraceAnalyzer:
    """Parse Chrome trace events and extract performance signals."""

    def analyze(self, trace_events: list[dict[str, Any]]) -> TraceInsight:
        """Extract insights from a list of Chrome trace events."""
        insight = TraceInsight()

        for event in trace_events:
            ph = event.get("ph", "")
            cat = event.get("cat", "")
            name = event.get("name", "")
            dur = event.get("dur", 0)  # microseconds
            ts = event.get("ts", 0)

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

        # Sort long tasks by duration descending
        insight.long_tasks.sort(key=lambda t: t.duration_ms, reverse=True)

        return insight
