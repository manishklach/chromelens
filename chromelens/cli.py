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

    # Phase 1: Discovery
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Discovering pages...", total=None)
        crawler = SiteCrawler(base_url=url, max_pages=max_pages, max_depth=max_depth)
        pages = crawler.crawl()
        progress.update(task, description=f"Discovered {len(pages)} pages")
        progress.stop()

    console.print(f"  ✓ Found [green]{len(pages)}[/] pages")
    console.print()

    # Phase 2: Profiling
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
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Profiling pages...", total=len(pages))
            for i, page in enumerate(pages):
                progress.update(task, description=f"[{i+1}/{len(pages)}] {page.url}")
                profile = profiler.profile_page(page.url, site_origin=url)
                profiles.append(profile)
                insight = analyzer.analyze(profile.trace_events)
                trace_insights.append(insight)
                progress.advance(task)

    console.print(f"  ✓ Profiled [green]{len(profiles)}[/] pages")
    console.print()

    # Phase 3: Scoring
    scorer = HealthScorer()
    page_scores = []
    for profile, insight in zip(profiles, trace_insights):
        score = scorer.score_page(profile, insight)
        page_scores.append(score)

    crawl_duration = time.perf_counter() - start_time
    report = scorer.score_site(
        site_url=url,
        page_scores=page_scores,
        profiles=profiles,
        crawl_duration_sec=crawl_duration,
    )

    # Phase 4: Report
    print_cli_report(report)

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
    )
    artifact_output_path = Path(artifact_path) if artifact_path else output_dir / "run.json"
    write_artifact_json(run_artifact, artifact_output_path)
    html_path = output_dir / "report.html"
    generate_html_report(report, profiles, trace_insights, html_path, artifact=run_artifact)
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


if __name__ == "__main__":
    main()
