"""HTML report generator — produces a single-file interactive dashboard."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

from chromelens.analysis import PageHealthScore, SiteHealthReport, TraceInsight
from chromelens.artifacts.models import RunArtifact
from chromelens.profiler import PageProfile

LOGGER = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class PageDetail:
    """Combined profile + score for template rendering."""

    profile: PageProfile
    score: PageHealthScore
    insight: TraceInsight


def generate_html_report(
    report: SiteHealthReport,
    profiles: list[PageProfile],
    insights: list[TraceInsight],
    output_path: Path,
    artifact: RunArtifact | None = None,
) -> Path:
    """Generate a single-file HTML dashboard report."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("dashboard.html")

    # Build page details (matched by URL)
    profile_map = {p.url: p for p in profiles}
    insight_map = {p.url: i for p, i in zip(profiles, insights)}
    page_details: list[PageDetail] = []
    for ps in sorted(report.page_scores, key=lambda x: x.score):
        profile = profile_map.get(ps.url)
        insight = insight_map.get(ps.url)
        if profile and insight:
            page_details.append(PageDetail(profile=profile, score=ps, insight=insight))

    # Chart data
    page_labels = [
        urlparse(ps.url).path or "/" for ps in sorted(report.page_scores, key=lambda x: x.score)
    ]
    page_scores_data = [ps.score for ps in sorted(report.page_scores, key=lambda x: x.score)]

    html = template.render(
        report=report,
        artifact=artifact,
        page_details=page_details,
        page_labels=page_labels,
        page_scores_data=page_scores_data,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    LOGGER.info("HTML report written to %s", output_path)
    return output_path
