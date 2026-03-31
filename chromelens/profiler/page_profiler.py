"""Page profiler — captures Chrome DevTools Protocol traces, metrics, and Web Vitals."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable
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
    "disabled-by-default-devtools.timeline",
    "disabled-by-default-v8.gc"
]

FILMSTRIP_CATEGORY = "disabled-by-default-devtools.screenshot"

NETWORK_PROFILES = {
    "lte": {"offline": False, "latency": 20, "downloadThroughput": int(12 * 1024 * 1024 / 8), "uploadThroughput": int(5 * 1024 * 1024 / 8)},
    "fast-3g": {"offline": False, "latency": 40, "downloadThroughput": int(1.4 * 1024 * 1024 / 8), "uploadThroughput": int(0.75 * 1024 * 1024 / 8)},
    "slow-3g": {"offline": False, "latency": 400, "downloadThroughput": int(0.4 * 1024 * 1024 / 8), "uploadThroughput": int(0.4 * 1024 * 1024 / 8)},
    "mcdonalds": {"offline": False, "latency": 50, "downloadThroughput": int(2 * 1024 * 1024 / 8), "uploadThroughput": int(1 * 1024 * 1024 / 8)},
    "starbucks": {"offline": False, "latency": 30, "downloadThroughput": int(5 * 1024 * 1024 / 8), "uploadThroughput": int(2 * 1024 * 1024 / 8)},
    "airport": {"offline": False, "latency": 150, "downloadThroughput": int(1 * 1024 * 1024 / 8), "uploadThroughput": int(0.5 * 1024 * 1024 / 8)},
    "offline": {"offline": True, "latency": 0, "downloadThroughput": 0, "uploadThroughput": 0},
}


class PageProfiler:
    """Captures full performance profiles for individual pages via Playwright + CDP."""

    def __init__(
        self,
        headless: bool = True,
        screenshot_dir: Path | None = None,
        filmstrip: bool = True,
        device_name: str | None = None,
        network_profile: str | None = None,
    ) -> None:
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        self.filmstrip = filmstrip
        self.device_name = device_name
        self.network_profile = network_profile
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
            context_opts = {}
            if self.device_name:
                device = self._pw_context.devices.get(self.device_name)
                if device:
                    context_opts.update(device)
                else:
                    LOGGER.warning("Device '%s' not found in Playwright.", self.device_name)
            
            if not context_opts:
                context_opts["viewport"] = {"width": 1440, "height": 900}
                context_opts["user_agent"] = "ChromeLens/0.1 (performance-audit)"

            context = self._browser.new_context(**context_opts)
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

            # Setup Network Emulation
            if self.network_profile and self.network_profile in NETWORK_PROFILES:
                cdp.send("Network.enable")
                cdp.send("Network.emulateNetworkConditions", NETWORK_PROFILES[self.network_profile])

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

            # Collect System Metrics
            try:
                proc_info = cdp.send("SystemInfo.getProcessInfo")
                for p in proc_info.get("processInfo", []):
                    ptype = p.get("type", "").lower()
                    if "renderer" in ptype:
                        profile.system_metrics.renderer_cpu_time_sec += p.get("cpuTime", 0)
                        profile.system_metrics.renderer_memory_bytes += p.get("privateMemory", 0)
                    elif "gpu" in ptype:
                        profile.system_metrics.gpu_cpu_time_sec += p.get("cpuTime", 0)
                        profile.system_metrics.gpu_memory_bytes += p.get("privateMemory", 0)
            except Exception as exc:
                LOGGER.warning("Could not gather SystemInfo metrics: %s", exc)

            if profile.system_metrics.renderer_cpu_time_sec == 0:
                profile.system_metrics.renderer_cpu_time_sec = profile.cdp_metrics.task_duration_ms / 1000.0
            if profile.system_metrics.renderer_memory_bytes == 0:
                profile.system_metrics.renderer_memory_bytes = profile.cdp_metrics.js_heap_used_bytes

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

    def profile_flow(self, name: str, start_url: str, interaction_fn: Callable[[Any], None]) -> PageProfile:
        """Profile an interactive user journey flow (e.g. clicks, scrolls)."""
        assert self._browser is not None, "Use PageProfiler as a context manager"
        profile = PageProfile(url=name)
        start_time = time.perf_counter()

        try:
            context_opts = {}
            if self.device_name:
                device = self._pw_context.devices.get(self.device_name)
                if device:
                    context_opts.update(device)
                else:
                    LOGGER.warning("Device '%s' not found in Playwright.", self.device_name)
            
            if not context_opts:
                context_opts["viewport"] = {"width": 1440, "height": 900}
                context_opts["user_agent"] = "ChromeLens/0.1 (performance-audit)"

            context = self._browser.new_context(**context_opts)
            page = context.new_page()

            requests_log: list[NetworkRequest] = []
            page.on("response", lambda resp: self._on_response(resp, requests_log, start_url))

            console_log: list[ConsoleMessage] = []
            page.on("console", lambda msg: console_log.append(
                ConsoleMessage(level=msg.type, text=msg.text, url=name)
            ))

            cdp = context.new_cdp_session(page)
            cdp.send("Performance.enable")

            # Setup Network Emulation
            if self.network_profile and self.network_profile in NETWORK_PROFILES:
                cdp.send("Network.enable")
                cdp.send("Network.emulateNetworkConditions", NETWORK_PROFILES[self.network_profile])

            trace_events: list[dict[str, Any]] = []
            cdp.on("Tracing.dataCollected", lambda params: trace_events.extend(params.get("value", [])))

            categories = list(TRACE_CATEGORIES)
            if self.filmstrip:
                categories.append(FILMSTRIP_CATEGORY)

            cdp.send("Tracing.start", {
                "categories": ",".join(categories),
                "options": "sampling-frequency=10000",
            })

            # Navigate to the starting point
            response = page.goto(start_url, wait_until="networkidle", timeout=30000)
            if response:
                profile.status_code = response.status

            # Execute the arbitrary user interactions mid-trace!
            interaction_fn(page)

            page.wait_for_timeout(1500)
            profile.title = f"Flow: {name}"

            cdp.send("Tracing.end")
            page.wait_for_timeout(500)

            raw_metrics = cdp.send("Performance.getMetrics")
            profile.cdp_metrics = self._parse_cdp_metrics(raw_metrics)

            try:
                proc_info = cdp.send("SystemInfo.getProcessInfo")
                for p in proc_info.get("processInfo", []):
                    ptype = p.get("type", "").lower()
                    if "renderer" in ptype:
                        profile.system_metrics.renderer_cpu_time_sec += p.get("cpuTime", 0)
                        profile.system_metrics.renderer_memory_bytes += p.get("privateMemory", 0)
                    elif "gpu" in ptype:
                        profile.system_metrics.gpu_cpu_time_sec += p.get("cpuTime", 0)
                        profile.system_metrics.gpu_memory_bytes += p.get("privateMemory", 0)
            except Exception as exc:
                LOGGER.warning("Could not gather SystemInfo metrics: %s", exc)

            if profile.system_metrics.renderer_cpu_time_sec == 0:
                profile.system_metrics.renderer_cpu_time_sec = profile.cdp_metrics.task_duration_ms / 1000.0
            if profile.system_metrics.renderer_memory_bytes == 0:
                profile.system_metrics.renderer_memory_bytes = profile.cdp_metrics.js_heap_used_bytes

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
                LOGGER.warning("Failed to extract Web Vitals for flow %s: %s", name, exc)

            if self.screenshot_dir:
                self.screenshot_dir.mkdir(parents=True, exist_ok=True)
                safe_name = name.replace(" ", "_").lower()
                ss_path = self.screenshot_dir / f"{safe_name}.png"
                page.screenshot(path=str(ss_path), full_page=True)
                profile.screenshot_path = str(ss_path)

            profile.network_requests = requests_log
            profile.console_messages = console_log
            profile.trace_events = trace_events

            cdp.detach()
            context.close()

        except Exception as exc:
            LOGGER.error("Error profiling flow %s: %s", name, exc)
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
