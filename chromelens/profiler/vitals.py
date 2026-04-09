"""JavaScript snippets for extracting Web Vitals via PerformanceObserver."""

EXTRACT_WEB_VITALS_JS = """
() => {
    const buildSelector = (node) => {
        if (!node || !node.tagName) return '';
        const tag = node.tagName.toLowerCase();
        const elementId = node.id ? `#${node.id}` : '';
        const classes = node.classList && node.classList.length
            ? '.' + Array.from(node.classList).slice(0, 3).join('.')
            : '';
        return `${tag}${elementId}${classes}`;
    };

    const rectToObject = (rect) => {
        if (!rect) return null;
        return {
            x: rect.x || 0,
            y: rect.y || 0,
            width: rect.width || 0,
            height: rect.height || 0,
        };
    };

    const result = {
        lcp_ms: 0,
        fcp_ms: 0,
        cls: 0,
        ttfb_ms: 0,
        dom_interactive_ms: 0,
        dom_complete_ms: 0,
        load_event_ms: 0,
        layout_shifts: [],
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

        const sources = (entry.sources || []).map((source) => {
            const node = source.node;
            return {
                selector: buildSelector(node),
                node_id: '',
                element_id: node && node.id ? node.id : '',
                tag_name: node && node.tagName ? node.tagName.toLowerCase() : '',
                classes: node && node.classList ? Array.from(node.classList).slice(0, 5) : [],
                previous_rect: rectToObject(source.previousRect),
                current_rect: rectToObject(source.currentRect),
            };
        });

        result.layout_shifts.push({
            value: entry.value,
            had_recent_input: entry.hadRecentInput,
            timestamp_ms: entry.startTime,
            sources,
        });
    }
    result.cls = clsValue;

    return result;
}
"""
