"""JavaScript snippets for extracting Web Vitals via PerformanceObserver."""

EXTRACT_WEB_VITALS_JS = """
() => {
    const result = {
        lcp_ms: 0,
        fcp_ms: 0,
        cls: 0,
        ttfb_ms: 0,
        dom_interactive_ms: 0,
        dom_complete_ms: 0,
        load_event_ms: 0,
    };

    // Navigation Timing
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav) {
        result.ttfb_ms = nav.responseStart || 0;
        result.dom_interactive_ms = nav.domInteractive || 0;
        result.dom_complete_ms = nav.domComplete || 0;
        result.load_event_ms = nav.loadEventEnd || 0;
    }

    // First Contentful Paint
    const paintEntries = performance.getEntriesByType('paint');
    for (const entry of paintEntries) {
        if (entry.name === 'first-contentful-paint') {
            result.fcp_ms = entry.startTime;
        }
    }

    // Largest Contentful Paint (last observed)
    const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
    if (lcpEntries.length > 0) {
        result.lcp_ms = lcpEntries[lcpEntries.length - 1].startTime;
    }

    // Cumulative Layout Shift
    const clsEntries = performance.getEntriesByType('layout-shift');
    let clsValue = 0;
    for (const entry of clsEntries) {
        if (!entry.hadRecentInput) {
            clsValue += entry.value;
        }
    }
    result.cls = clsValue;

    return result;
}
"""
