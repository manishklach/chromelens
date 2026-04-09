"""Route clustering and template aggregation helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any
from urllib.parse import urlsplit

from chromelens.artifacts.models import MetricSummaryArtifact, PageArtifact, TemplateArtifact

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)
INTEGER_RE = re.compile(r"^\d+$")
HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLUG_NUMERIC_RE = re.compile(r"^(?P<slug>[a-z0-9-]+)-(?P<num>\d{2,})$", re.IGNORECASE)
YEAR_RE = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^(0?[1-9]|1[0-2])$")


@dataclass(slots=True)
class RoutePatternRule:
    """User-supplied route normalization rule."""

    pattern: str
    replacement: str
    label: str = ""


@dataclass(slots=True)
class RouteTemplateMatch:
    """Template signature derived for a URL."""

    template_id: str
    signature: str
    label: str
    reason: str
    confidence: str
    normalized_url: str


def load_route_pattern_rules(path: str | None) -> list[RoutePatternRule]:
    """Load route pattern rules from JSON or YAML if available."""
    if not path:
        return []

    pattern_path = Path(path)
    if not pattern_path.exists():
        raise FileNotFoundError(f"Route pattern file not found: {pattern_path}")

    payload: Any
    suffix = pattern_path.suffix.lower()
    raw_text = pattern_path.read_text(encoding="utf-8")

    if suffix == ".json":
        payload = json.loads(raw_text)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised only when YAML used without dependency
            raise RuntimeError("YAML route patterns require PyYAML to be installed.") from exc
        payload = yaml.safe_load(raw_text)
    else:
        raise ValueError("Route pattern file must be .json, .yaml, or .yml")

    if not isinstance(payload, list):
        raise ValueError("Route pattern file must contain a list of rules")

    rules: list[RoutePatternRule] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each route pattern rule must be an object")
        rules.append(
            RoutePatternRule(
                pattern=str(item.get("pattern", "")),
                replacement=str(item.get("replacement", "")),
                label=str(item.get("label", "")),
            )
        )
    return rules


def match_route_template(
    url: str,
    *,
    strategy: str = "auto",
    rules: list[RoutePatternRule] | None = None,
) -> RouteTemplateMatch:
    """Compute a stable template signature for a URL."""
    split = urlsplit(url)
    normalized_url = split.path or "/"
    normalized_url = normalized_url.rstrip("/") or "/"

    if strategy == "off":
        signature = normalized_url
        label = _label_from_signature(signature)
        return RouteTemplateMatch(
            template_id=_template_id(signature),
            signature=signature,
            label=label,
            reason="template clustering disabled",
            confidence="high",
            normalized_url=normalized_url,
        )

    for rule in rules or []:
        if not rule.pattern or not rule.replacement:
            continue
        if re.search(rule.pattern, normalized_url):
            signature = re.sub(rule.pattern, rule.replacement, normalized_url)
            signature = signature or "/"
            label = rule.label or _label_from_signature(signature)
            return RouteTemplateMatch(
                template_id=_template_id(signature),
                signature=signature,
                label=label,
                reason=f"matched custom rule: {rule.pattern}",
                confidence="high",
                normalized_url=normalized_url,
            )

    if strategy == "rules":
        signature = normalized_url
        label = _label_from_signature(signature)
        return RouteTemplateMatch(
            template_id=_template_id(signature),
            signature=signature,
            label=label,
            reason="no custom rule matched",
            confidence="low",
            normalized_url=normalized_url,
        )

    signature, reason = _heuristic_signature(normalized_url)
    label = _label_from_signature(signature)
    return RouteTemplateMatch(
        template_id=_template_id(signature),
        signature=signature,
        label=label,
        reason=reason,
        confidence="medium" if signature != normalized_url else "low",
        normalized_url=normalized_url,
    )


def build_template_artifacts(
    pages: list[PageArtifact],
    *,
    strategy: str,
    rules: list[RoutePatternRule] | None = None,
) -> tuple[list[PageArtifact], list[TemplateArtifact]]:
    """Assign template metadata to pages and build template aggregates."""
    grouped: dict[str, list[PageArtifact]] = defaultdict(list)
    updated_pages: list[PageArtifact] = []

    for page in sorted(pages, key=lambda item: item.url):
        match = match_route_template(page.url, strategy=strategy, rules=rules)
        page.template_id = match.template_id
        page.template_signature = match.signature
        page.template_reason = match.reason
        page.template_confidence = match.confidence
        page.normalized_url = match.normalized_url
        updated_pages.append(page)
        grouped[match.template_id].append(page)

    templates: list[TemplateArtifact] = []
    for template_id in sorted(grouped):
        template_pages = sorted(grouped[template_id], key=lambda item: item.url)
        first_page = template_pages[0]
        third_party_costs = [page.third_party_bytes for page in template_pages]
        templates.append(
            TemplateArtifact(
                template_id=template_id,
                signature=first_page.template_signature,
                label=_label_from_signature(first_page.template_signature),
                reason=first_page.template_reason,
                confidence=first_page.template_confidence,
                page_count=len(template_pages),
                sample_urls=[page.url for page in template_pages[:5]],
                score_summary=_summarize([page.score for page in template_pages]),
                tbt_summary=_summarize([page.total_blocking_time_ms for page in template_pages]),
                lcp_summary=_summarize([page.lcp_ms for page in template_pages]),
                cls_summary=_summarize([page.cls for page in template_pages]),
                long_task_count_summary=_summarize([float(page.long_task_count) for page in template_pages]),
                third_party_cost_summary=_summarize([float(value) for value in third_party_costs]),
                total_third_party_bytes=sum(third_party_costs),
                avg_third_party_bytes=mean(third_party_costs) if third_party_costs else 0.0,
            )
        )

    return updated_pages, sorted(templates, key=lambda item: (item.signature, item.template_id))


def _heuristic_signature(path: str) -> tuple[str, str]:
    """Normalize dynamic path segments into placeholders."""
    if path == "/":
        return "/", "root path"

    segments = [segment for segment in path.split("/") if segment]
    normalized_segments: list[str] = []
    replacements: list[str] = []

    for segment in segments:
        lowered = segment.lower()
        replacement = segment
        if UUID_RE.match(lowered):
            replacement = ":uuid"
        elif DATE_RE.match(lowered):
            replacement = ":date"
        elif INTEGER_RE.match(lowered):
            replacement = ":id"
        elif HEX_RE.match(lowered):
            replacement = ":hex"
        else:
            slug_match = SLUG_NUMERIC_RE.match(lowered)
            if slug_match:
                replacement = ":slug"
            elif YEAR_RE.match(lowered):
                replacement = ":year"
            elif MONTH_RE.match(lowered):
                replacement = ":month"

        if replacement != segment:
            replacements.append(f"{segment}->{replacement}")
        normalized_segments.append(replacement)

    signature = "/" + "/".join(normalized_segments)
    reason = "heuristic normalization"
    if replacements:
        reason = f"heuristic normalization ({', '.join(replacements[:3])})"
    return signature, reason


def _label_from_signature(signature: str) -> str:
    if signature == "/":
        return "Homepage Template"

    segments = [segment for segment in signature.split("/") if segment]
    if not segments:
        return "Homepage Template"

    lead = segments[0].replace("-", " ").replace("_", " ").title()
    if any(segment.startswith(":") for segment in segments[1:]) or segments[-1].startswith(":"):
        return f"{lead} Template"
    return f"{lead} Route"


def _template_id(signature: str) -> str:
    return hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]


def _summarize(values: list[float]) -> MetricSummaryArtifact:
    if not values:
        return MetricSummaryArtifact()

    sorted_values = sorted(float(value) for value in values)
    return MetricSummaryArtifact(
        count=len(sorted_values),
        min=sorted_values[0],
        p50=_percentile(sorted_values, 0.50),
        p75=_percentile(sorted_values, 0.75),
        p95=_percentile(sorted_values, 0.95),
        p99=_percentile(sorted_values, 0.99),
        max=sorted_values[-1],
        mean=mean(sorted_values),
    )


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * quantile)))
    return sorted_values[index]
