"""ChromeLens CLI — Full-site performance X-ray."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from chromelens.analysis.health_scorer import HealthScorer
from chromelens.analysis.diffing import diff_run_artifacts, load_run_artifact
from chromelens.analysis.trace_analyzer import TraceAnalyzer
from chromelens.artifacts.builders import build_run_artifact
from chromelens.artifacts.serializer import write_artifact_json
from chromelens.discovery.crawler import SiteCrawler
from chromelens.export.har import export_har_files
from chromelens.profiler.page_profiler import PageProfiler
from chromelens.report.cli_report import print_cli_report, print_diff_report
from chromelens.report.html_report import generate_diff_html_report, generate_html_report

console = Console()
LOGGER = logging.getLogger("chromelens")


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def main(verbose: bool) -> None:
    """🔬 ChromeLens — Full-site performance X-ray via Chrome DevTools Protocol."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(name)s %(levelname)s: %(message)s")


def _discover_pages(url: str, max_pages: int, max_depth: int) -> list:
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Discovering pages...", total=None)
        crawler = SiteCrawler(base_url=url, max_pages=max_pages, max_depth=max_depth)
        pages = crawler.crawl()
        progress.update(task, description=f"Discovered {len(pages)} pages")
        progress.stop()
    return pages


def _profile_pages(
    url: str,
    pages: list,
    *,
    output_dir: Path,
    headless: bool,
    screenshots: bool,
    filmstrip: bool,
    network: str | None,
    device: str | None,
    export_har: str,
) -> tuple[list, list]:
    screenshot_dir = output_dir / "screenshots" if screenshots else None
    profiles = []
    analyzer = TraceAnalyzer()
    trace_insights = []

    with PageProfiler(
        headless=headless,
        screenshot_dir=screenshot_dir,
        filmstrip=filmstrip,
        device_name=device,
        network_profile=network,
    ) as profiler:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task("Profiling pages...", total=len(pages))
            for i, page in enumerate(pages):
                progress.update(task, description=f"[{i + 1}/{len(pages)}] {page.url}")
                profile = profiler.profile_page(page.url, site_origin=url)
                profiles.append(profile)
                trace_insights.append(analyzer.analyze(profile.trace_events))
                progress.advance(task)

    if export_har != "off":
        export_har_files(profiles, output_dir / "har", export_har)

    return profiles, trace_insights


def _score_report(url: str, profiles: list, trace_insights: list, crawl_duration: float):
    scorer = HealthScorer()
    page_scores = [scorer.score_page(profile, insight) for profile, insight in zip(profiles, trace_insights)]
    return scorer.score_site(
        site_url=url,
        page_scores=page_scores,
        profiles=profiles,
        crawl_duration_sec=crawl_duration,
    )


def _run_single_mode(
    url: str,
    *,
    output_dir: Path,
    pages: list | None,
    max_pages: int,
    max_depth: int,
    headless: bool,
    screenshots: bool,
    filmstrip: bool,
    network: str | None,
    device: str | None,
    artifact_path: str | None,
    template_clustering: str,
    route_patterns: str | None,
    export_har: str,
):
    start_time = time.perf_counter()
    discovered_pages = pages or _discover_pages(url, max_pages, max_depth)
    profiles, trace_insights = _profile_pages(
        url,
        discovered_pages,
        output_dir=output_dir,
        headless=headless,
        screenshots=screenshots,
        filmstrip=filmstrip,
        network=network,
        device=device,
        export_har=export_har,
    )
    report = _score_report(url, profiles, trace_insights, time.perf_counter() - start_time)
    run_artifact = build_run_artifact(
        report,
        profiles,
        trace_insights,
        output_dir=output_dir,
        max_pages=max_pages,
        max_depth=max_depth,
        headless=headless,
        screenshots=screenshots,
        filmstrip=filmstrip,
        network=network,
        device=device,
        template_clustering=template_clustering,
        route_patterns=route_patterns,
        export_har=export_har,
    )
    artifact_output_path = Path(artifact_path) if artifact_path else output_dir / "run.json"
    write_artifact_json(run_artifact, artifact_output_path)
    html_path = output_dir / "report.html"
    generate_html_report(report, profiles, trace_insights, html_path, artifact=run_artifact)
    return discovered_pages, report, run_artifact, artifact_output_path, html_path


@main.command()
@click.argument("url")
@click.option("--output", "-o", default="reports/chromelens", help="Output directory for the report.")
@click.option("--max-pages", default=20, help="Maximum number of pages to profile.")
@click.option("--max-depth", default=3, help="Maximum crawl depth.")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode.")
@click.option("--screenshots/--no-screenshots", default=True, help="Capture page screenshots.")
@click.option("--filmstrip/--no-filmstrip", default=True, help="Capture rendering filmstrip in report.")
@click.option("--network", type=click.Choice(["lte", "fast-3g", "slow-3g", "mcdonalds", "starbucks", "airport", "offline"]), default=None, help="Throttle network connection.")
@click.option("--device", default=None, help="Emulate a specific mobile device (e.g. 'Pixel 5', 'iPhone 13').")
@click.option("--artifact-path", default=None, help="Optional JSON run artifact path. Defaults to <output>/run.json.")
@click.option("--template-clustering", type=click.Choice(["auto", "rules", "off"]), default="auto", help="Route template clustering strategy.")
@click.option("--route-patterns", default=None, help="Optional JSON/YAML file with custom route normalization rules.")
@click.option("--export-har", type=click.Choice(["off", "per-page", "combined", "both"]), default="off", help="Export captured network requests in HAR format.")
def crawl(
    url: str,
    output: str,
    max_pages: int,
    max_depth: int,
    headless: bool,
    screenshots: bool,
    filmstrip: bool,
    network: str | None,
    device: str | None,
    artifact_path: str | None,
    template_clustering: str,
    route_patterns: str | None,
    export_har: str,
) -> None:
    """Crawl a website and generate a performance report.

    Example: chromelens crawl https://example.com --output reports/example
    """
    output_dir = Path(output)
    start_time = time.perf_counter()

    console.print()
    console.print("[bold magenta]🔬 ChromeLens[/] — Full-site Performance X-Ray")
    console.print(f"   Target: [cyan]{url}[/]")
    console.print(f"   Max pages: {max_pages} · Max depth: {max_depth}")
    console.print()

    pages = _discover_pages(url, max_pages, max_depth)
    console.print(f"  ✓ Found [green]{len(pages)}[/] pages")
    console.print()
    _, report, run_artifact, artifact_output_path, html_path = _run_single_mode(
        url,
        output_dir=output_dir,
        pages=pages,
        max_pages=max_pages,
        max_depth=max_depth,
        headless=headless,
        screenshots=screenshots,
        filmstrip=filmstrip,
        network=network,
        device=device,
        artifact_path=artifact_path,
        template_clustering=template_clustering,
        route_patterns=route_patterns,
        export_har=export_har,
    )
    print_cli_report(report)
    console.print(f"  📄 HTML report: [cyan]{html_path}[/]")
    console.print(f"  🧾 Run artifact: [cyan]{artifact_output_path}[/]")
    console.print()

@main.command()
@click.argument("baseline_artifact")
@click.argument("candidate_artifact")
@click.option("--output", "-o", default="reports/chromelens-diff", help="Output directory for diff artifacts.")
@click.option("--fail-on-regression", is_flag=True, help="Return exit code 2 if any configured threshold fails.")
@click.option("--max-tbt-regression-pct", type=float, default=None, help="Maximum allowed TBT regression percentage.")
@click.option("--max-new-long-tasks", type=int, default=None, help="Maximum allowed increase in long task count.")
@click.option("--max-cls-regression", type=float, default=None, help="Maximum allowed CLS regression.")
@click.option("--max-script-duration-regression-pct", type=float, default=None, help="Maximum allowed ScriptDuration regression percentage.")
def diff(
    baseline_artifact: str,
    candidate_artifact: str,
    output: str,
    fail_on_regression: bool,
    max_tbt_regression_pct: float | None,
    max_new_long_tasks: int | None,
    max_cls_regression: float | None,
    max_script_duration_regression_pct: float | None,
) -> None:
    """Diff two prior ChromeLens run artifacts without re-crawling."""
    output_dir = Path(output)
    baseline_path = Path(baseline_artifact)
    candidate_path = Path(candidate_artifact)
    baseline = load_run_artifact(baseline_path)
    candidate = load_run_artifact(candidate_path)

    diff_artifact = diff_run_artifacts(
        baseline,
        candidate,
        baseline_ref=str(baseline_path),
        candidate_ref=str(candidate_path),
        max_tbt_regression_pct=max_tbt_regression_pct,
        max_new_long_tasks=max_new_long_tasks,
        max_cls_regression=max_cls_regression,
        max_script_duration_regression_pct=max_script_duration_regression_pct,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    diff_json_path = output_dir / "diff.json"
    diff_html_path = output_dir / "diff.html"
    write_artifact_json(diff_artifact, diff_json_path)
    generate_diff_html_report(diff_artifact, diff_html_path)
    print_diff_report(diff_artifact)
    console.print(f"  📄 HTML diff report: [cyan]{diff_html_path}[/]")
    console.print(f"  🧾 JSON diff artifact: [cyan]{diff_json_path}[/]")

    if fail_on_regression and diff_artifact.summary.failed_thresholds:
        raise SystemExit(2)


@main.command("compare-modes")
@click.argument("url")
@click.option("--output", "-o", default="reports/chromelens-reality-check", help="Output directory for mode comparison outputs.")
@click.option("--max-pages", default=20, help="Maximum number of pages to profile.")
@click.option("--max-depth", default=3, help="Maximum crawl depth.")
@click.option("--screenshots/--no-screenshots", default=True, help="Capture page screenshots for both modes.")
@click.option("--filmstrip/--no-filmstrip", default=True, help="Capture rendering filmstrip in report.")
@click.option("--network", type=click.Choice(["lte", "fast-3g", "slow-3g", "mcdonalds", "starbucks", "airport", "offline"]), default=None, help="Throttle network connection.")
@click.option("--device", default=None, help="Emulate a specific mobile device (e.g. 'Pixel 5', 'iPhone 13').")
@click.option("--template-clustering", type=click.Choice(["auto", "rules", "off"]), default="auto", help="Route template clustering strategy.")
@click.option("--route-patterns", default=None, help="Optional JSON/YAML file with custom route normalization rules.")
@click.option("--export-har", type=click.Choice(["off", "per-page", "combined", "both"]), default="off", help="Export captured network requests in HAR format.")
@click.option("--reality-threshold-tbt-ms", type=float, default=None, help="Maximum allowed TBT delta between headless and headed modes.")
@click.option("--reality-threshold-cls", type=float, default=None, help="Maximum allowed CLS delta between headless and headed modes.")
def compare_modes(
    url: str,
    output: str,
    max_pages: int,
    max_depth: int,
    screenshots: bool,
    filmstrip: bool,
    network: str | None,
    device: str | None,
    template_clustering: str,
    route_patterns: str | None,
    export_har: str,
    reality_threshold_tbt_ms: float | None,
    reality_threshold_cls: float | None,
) -> None:
    """Run the same route set in headless and headed mode and compare the results."""
    output_dir = Path(output)
    console.print()
    console.print("[bold magenta]🔬 ChromeLens[/] — Headless vs Headed Reality Check")
    console.print(f"   Target: [cyan]{url}[/]")
    console.print()

    pages = _discover_pages(url, max_pages, max_depth)
    console.print(f"  ✓ Found [green]{len(pages)}[/] pages")
    console.print()

    _, _, _, headless_artifact_path, _ = _run_single_mode(
        url,
        output_dir=output_dir / "headless",
        pages=pages,
        max_pages=max_pages,
        max_depth=max_depth,
        headless=True,
        screenshots=screenshots,
        filmstrip=filmstrip,
        network=network,
        device=device,
        artifact_path=None,
        template_clustering=template_clustering,
        route_patterns=route_patterns,
        export_har=export_har,
    )
    _, _, _, headed_artifact_path, _ = _run_single_mode(
        url,
        output_dir=output_dir / "headed",
        pages=pages,
        max_pages=max_pages,
        max_depth=max_depth,
        headless=False,
        screenshots=screenshots,
        filmstrip=filmstrip,
        network=network,
        device=device,
        artifact_path=None,
        template_clustering=template_clustering,
        route_patterns=route_patterns,
        export_har=export_har,
    )

    diff_artifact = diff_run_artifacts(
        load_run_artifact(headless_artifact_path),
        load_run_artifact(headed_artifact_path),
        baseline_ref="headless",
        candidate_ref="headed",
        max_tbt_regression_pct=None,
        max_new_long_tasks=None,
        max_cls_regression=reality_threshold_cls,
        max_script_duration_regression_pct=None,
    )

    if reality_threshold_tbt_ms is not None:
        max_tbt_delta = max(
            (
                abs(entry.metrics["total_blocking_time_ms"].absolute_delta)
                for entry in diff_artifact.page_diffs
                if "total_blocking_time_ms" in entry.metrics
            ),
            default=0.0,
        )
        diff_artifact.threshold_results["reality_threshold_tbt_ms"] = max_tbt_delta <= reality_threshold_tbt_ms
        if not diff_artifact.threshold_results["reality_threshold_tbt_ms"]:
            diff_artifact.summary.failed_thresholds.append("reality_threshold_tbt_ms")

    diff_dir = output_dir / "compare"
    diff_dir.mkdir(parents=True, exist_ok=True)
    diff_json_path = diff_dir / "mode-diff.json"
    diff_html_path = diff_dir / "mode-diff.html"
    write_artifact_json(diff_artifact, diff_json_path)
    generate_diff_html_report(diff_artifact, diff_html_path)
    print_diff_report(diff_artifact)
    console.print(f"  📄 Mode diff report: [cyan]{diff_html_path}[/]")
    console.print(f"  🧾 Mode diff artifact: [cyan]{diff_json_path}[/]")
    console.print(f"  🖼 Screenshots: [cyan]{output_dir / 'headless' / 'screenshots'}[/] and [cyan]{output_dir / 'headed' / 'screenshots'}[/]")


if __name__ == "__main__":
    main()
