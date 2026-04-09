"""CLI report output using Rich for terminal rendering."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from chromelens.analysis import SiteHealthReport
from chromelens.artifacts.models import DiffArtifact

console = Console()


def _score_color(score: int) -> str:
    """Return a Rich color string for a health score."""
    if score >= 90:
        return "green"
    if score >= 55:
        return "yellow"
    return "red"


def print_cli_report(report: SiteHealthReport) -> None:
    """Print a summary report to the terminal."""
    console.print()


def print_diff_report(diff: DiffArtifact) -> None:
    """Print a concise diff summary to the terminal."""
    console.print()
    console.print(f"[bold magenta]🔬 ChromeLens Diff[/] — {diff.baseline_ref} → {diff.candidate_ref}")
    console.print()
    console.print(f"  Regressions: [red]{diff.summary.regressions}[/]")
    console.print(f"  Improvements: [green]{diff.summary.improvements}[/]")
    console.print(f"  Added: {diff.summary.added} · Removed: {diff.summary.removed}")
    if diff.summary.failed_thresholds:
        console.print(f"  Thresholds failed: [red]{', '.join(diff.summary.failed_thresholds)}[/]")

    table = Table(title="Top Regressions", show_lines=False, border_style="dim")
    table.add_column("Type", width=10)
    table.add_column("Label", overflow="ellipsis")
    table.add_column("TBT Δ", justify="right")
    table.add_column("CLS Δ", justify="right")
    table.add_column("Script Δ", justify="right")

    for collection_name, entries in (
        ("page", diff.page_diffs),
        ("template", diff.template_diffs),
        ("3P", diff.third_party_diffs),
    ):
        for entry in entries:
            if entry.status != "regression":
                continue
            tbt = entry.metrics.get("total_blocking_time_ms") or entry.metrics.get("tbt_summary.p75")
            cls = entry.metrics.get("cls") or entry.metrics.get("cls_summary.p75")
            script = entry.metrics.get("script_duration_ms")
            table.add_row(
                collection_name,
                entry.label,
                _format_metric_delta(tbt),
                _format_metric_delta(cls),
                _format_metric_delta(script),
            )

    if table.row_count:
        console.print()
        console.print(table)
    console.print()


def _format_metric_delta(metric: object) -> str:
    if metric is None:
        return "-"
    if not hasattr(metric, "absolute_delta"):
        return "-"
    absolute_delta = getattr(metric, "absolute_delta", 0.0)
    percent_delta = getattr(metric, "percent_delta", None)
    if percent_delta is None:
        return f"{absolute_delta:+.2f}"
    return f"{absolute_delta:+.2f} ({percent_delta:+.1f}%)"
    console.print(f"[bold magenta]🔬 ChromeLens Report[/] — {report.site_url}")
    console.print()

    # Site score
    color = _score_color(report.site_score)
    console.print(f"  Site Score: [{color} bold]{report.site_score}[/] ({report.site_grade})")
    console.print(f"  Pages: {report.total_pages}")
    console.print(f"  Duration: {report.crawl_duration_sec:.1f}s")
    console.print()

    # Page table
    table = Table(title="Page Scores", show_lines=False, border_style="dim")
    table.add_column("Grade", width=6, justify="center")
    table.add_column("Score", width=6, justify="right")
    table.add_column("URL", overflow="ellipsis")
    table.add_column("Issues", width=8, justify="right")

    for ps in sorted(report.page_scores, key=lambda x: x.score):
        color = _score_color(ps.score)
        table.add_row(
            f"[{color}]{ps.grade}[/]",
            f"[{color}]{ps.score}[/]",
            ps.url,
            str(len(ps.issues)),
        )

    console.print(table)

    # Top issues
    if report.common_issues:
        console.print()
        console.print("[bold yellow]Common Issues:[/]")
        for issue in report.common_issues[:5]:
            console.print(f"  ⚠ {issue}")

    # Third-party domains
    if report.third_party_impacts:
        console.print()
        tp_table = Table(title="Third-Party Impact", show_lines=False, border_style="dim")
        tp_table.add_column("Domain", overflow="ellipsis")
        tp_table.add_column("Requests", justify="right")
        tp_table.add_column("Size", justify="right")
        tp_table.add_column("Pages", justify="right")

        for tp in report.third_party_impacts[:10]:
            tp_table.add_row(
                tp.domain,
                str(tp.request_count),
                f"{tp.total_bytes / 1000:.1f}KB",
                str(tp.pages_present),
            )
        console.print(tp_table)

    console.print()
