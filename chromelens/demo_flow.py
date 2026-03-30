"""Demo script for profiling a multi-step user interaction flow."""

import sys
import os
from pathlib import Path
from rich.console import Console

# Add parent to path to ensure modules resolve when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chromelens.profiler.page_profiler import PageProfiler
from chromelens.analysis.trace_analyzer import TraceAnalyzer
from chromelens.report.html_report import generate_html_report

console = Console()

def flipkart_flow(page):
    console.print("[cyan]Interaction 1: Dismissing login popups (if any)...[/cyan]")
    try:
        # Typically flipkart shows a dismissible span button
        page.click("span[role='button']:has-text('✕')", timeout=2000)
    except Exception:
        pass
        
    console.print("[cyan]Interaction 2: Scrolling down to trigger lazy loads...[/cyan]")
    page.mouse.wheel(0, 800)
    page.wait_for_timeout(1000)
    
    console.print("[cyan]Interaction 3: Typing 'Smartphone' in search bar...[/cyan]")
    try:
        page.fill("input[type='text'], input[title*='Search']", "Smartphone", timeout=3000)
        page.press("input[type='text'], input[title*='Search']", "Enter")
        console.print("[cyan]Interaction 4: Waiting for React SPA navigation + render...[/cyan]")
        page.wait_for_timeout(4000) # Wait for network + paint of SPA route
    except Exception as e:
        console.print(f"[yellow]Could not perform search dynamically: {e}[/yellow]")
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(2000)

def main():
    out_dir = Path("reports/flow_demo")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    console.print("[bold green]Starting ChromeLens Flow Profiler on Flipkart...[/bold green]")
    
    with PageProfiler(headless=True, screenshot_dir=out_dir / "screenshots", filmstrip=True) as profiler:
        # Profile the dynamic flow instead of a static page load
        profile = profiler.profile_flow(
            name="Flipkart Search Journey",
            start_url="https://flipkart.com",
            interaction_fn=flipkart_flow
        )
    
    if profile.error:
        console.print(f"[bold red]Flow profiling failed: {profile.error}[/bold red]")
        sys.exit(1)
        
    console.print("[bold green]Analyzing trace events...[/bold green]")
    insight = TraceAnalyzer().analyze(profile.trace_events)
    profile.insight = insight

    from chromelens.analysis.health_scorer import HealthScorer
    scorer = HealthScorer()
    page_score = scorer.score_page(profile, insight)
    report = scorer.score_site("https://flipkart.com", [page_score], [profile], profile.profile_duration_ms / 1000.0)
    
    # Generate unified report
    report_path = out_dir / "report.html"
    generate_html_report(report, [profile], [insight], report_path)
    console.print(f"\n[bold cyan]Done! Dynamic Flow Report available at: {report_path.absolute()}[/bold cyan]")

if __name__ == "__main__":
    main()
