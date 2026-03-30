"""Page profiler — captures Chrome DevTools Protocol traces, metrics, and Web Vitals."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Browser, sync_playwright

from . import CDPMetrics, ConsoleMessage, NetworkRequest, PageProfile, WebVitals
from .vitals import EXTRACT_WEB_VITALS_JS

LOGGER = logging.getLogger(__name__)

CDP_METRIC_MAP: dict[str, str] = {
    "Timestamp": "timestamp",
    "Documents": "documents",
    "Frames": "frames",
    "JSEventListeners": "js_event_listeners",
    "Nodes": "nodes",
    "LayoutCount": "layout_count",
    "RecalcStyleCount": "recalc_style_count",
    "LayoutDuration": "layout_duration_ms",
    "RecalcStyleDuration": "recalc_style_duration_ms",
    "ScriptDuration": "script_duration_ms",
    "TaskDuration": "task_duration_ms",
    "JSHeapUsedSize": "js_heap_used_bytes",
    "JSHeapTotalSize": "js_heap_total_bytes",
}

DURATION_FIELDS = {"layout_duration_ms", "recalc_style_duration_ms", "script_duration_ms", "task_duration_ms"}

TRACE_CATEGORIES = [
    "devtools.timeline",
    "blink.user_timing",
    "v8.execute",
    "loading",
]

FILMSTRIP_CATEGORY = "disabled-by-default-devtools.screenshot"


class PageProfiler:
    """Captures full performance profiles for individual pages via Playwright + CDP."""

    def __init__(
        self,
        headless: bool = True,
        screenshot_dir: Path | None = None,
        filmstrip: bool = True,
    ) -> None:
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        self.filmstrip = filmstrip
        self._pw_context: Any = None
        self._browser: Browser | None = None

    def __enter__(self) -> "PageProfiler":
        self._pw_context = sync_playwright().start()
        self._browser = self._pw_context.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._browser:
            self._browser.close()
        if self._pw_context:
            self._pw_context.stop()

    def profile_page(self, url: str, site_origin: str) -> PageProfile:
        """Profile a single page: CDP metrics, trace, vitals, network, console."""
        assert self._browser is not None, "Use PageProfiler as a context manager"
        profile = PageProfile(url=url)
        start_time = time.perf_counter()

        try:
            context = self._browser.new_context(
                user_agent="ChromeLens/0.1 (performance-audit)",
                viewport={"width": 1440, "height": 900},
            )
            page = context.new_page()

            # Capture network requests
            requests_log: list[NetworkRequest] = []
            page.on("response", lambda resp: self._on_response(resp, requests_log, site_origin))

            # Capture console messages
            console_log: list[ConsoleMessage] = []
            page.on("console", lambda msg: console_log.append(
                ConsoleMessage(level=msg.type, text=msg.text, url=url)
            ))

            # Create CDP session
            cdp = context.new_cdp_session(page)
            cdp.send("Performance.enable")

            # Start Chrome tracing
            trace_events: list[dict[str, Any]] = []
            cdp.on("Tracing.dataCollected", lambda params: trace_events.extend(params.get("value", [])))

            categories = list(TRACE_CATEGORIES)
            if self.filmstrip:
                categories.append(FILMSTRIP_CATEGORY)

            cdp.send("Tracing.start", {
                "categories": ",".join(categories),
                "options": "sampling-frequency=10000",
            })

            # Navigate
            response = page.goto(url, wait_until="networkidle", timeout=30000)
            if response:
                profile.status_code = response.status

            # Wait a bit for late metrics
            page.wait_for_timeout(1500)

            # Get page title
            profile.title = page.title()

            # Stop tracing
            cdp.send("Tracing.end")
            page.wait_for_timeout(500)  # allow trace data to flush

            # Collect CDP metrics
            raw_metrics = cdp.send("Performance.getMetrics")
            profile.cdp_metrics = self._parse_cdp_metrics(raw_metrics)

            # Collect Web Vitals
            try:
                vitals_raw = page.evaluate(EXTRACT_WEB_VITALS_JS)
                profile.vitals = WebVitals(
                    lcp_ms=float(vitals_raw.get("lcp_ms", 0)),
                    fcp_ms=float(vitals_raw.get("fcp_ms", 0)),
                    cls=float(vitals_raw.get("cls", 0)),
                    ttfb_ms=float(vitals_raw.get("ttfb_ms", 0)),
                    dom_interactive_ms=float(vitals_raw.get("dom_interactive_ms", 0)),
                    dom_complete_ms=float(vitals_raw.get("dom_complete_ms", 0)),
                    load_event_ms=float(vitals_raw.get("load_event_ms", 0)),
                )
            except Exception as exc:
                LOGGER.warning("Failed to extract Web Vitals for %s: %s", url, exc)

            # Screenshot
            if self.screenshot_dir:
                self.screenshot_dir.mkdir(parents=True, exist_ok=True)
                safe_name = urlparse(url).path.strip("/").replace("/", "_") or "index"
                ss_path = self.screenshot_dir / f"{safe_name}.png"
                page.screenshot(path=str(ss_path), full_page=True)
                profile.screenshot_path = str(ss_path)

            profile.network_requests = requests_log
            profile.console_messages = console_log
            profile.trace_events = trace_events

            cdp.detach()
            context.close()

        except Exception as exc:
            LOGGER.error("Error profiling %s: %s", url, exc)
            profile.error = str(exc)

        profile.profile_duration_ms = (time.perf_counter() - start_time) * 1000
        return profile

    def _on_response(self, response: Any, log: list[NetworkRequest], site_origin: str) -> None:
        """Capture a network response into the request log."""
        try:
            req = response.request
            parsed = urlparse(response.url)
            domain = parsed.netloc
            is_third_party = domain != urlparse(site_origin).netloc

            size = 0
            try:
                body = response.body()
                size = len(body) if body else 0
            except Exception:
                pass

            timing = response.request.timing
            duration = timing.get("responseEnd", 0) if isinstance(timing, dict) else 0

            log.append(NetworkRequest(
                url=response.url,
                method=req.method,
                resource_type=req.resource_type,
                status=response.status,
                size_bytes=size,
                duration_ms=float(duration),
                domain=domain,
                is_third_party=is_third_party,
                mime_type=response.headers.get("content-type", ""),
            ))
        except Exception:
            pass  # non-critical: don't fail the profile on a network capture issue

    def _parse_cdp_metrics(self, raw: dict[str, Any]) -> CDPMetrics:
        """Parse CDP Performance.getMetrics into a CDPMetrics dataclass."""
        metrics = CDPMetrics()
        for item in raw.get("metrics", []):
            name = item.get("name", "")
            value = item.get("value", 0)
            field_name = CDP_METRIC_MAP.get(name)
            if field_name:
                if field_name in DURATION_FIELDS:
                    value = value * 1000  # seconds → ms
                setattr(metrics, field_name, value)
        return metrics
