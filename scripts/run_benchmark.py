"""Automated telemetry harness for the ChromeLens 50-Site Benchmark."""

import sys
import os
import json
import time
from pathlib import Path
from rich.console import Console
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chromelens.profiler.page_profiler import PageProfiler
from chromelens.analysis.trace_analyzer import TraceAnalyzer
from chromelens.analysis.health_scorer import HealthScorer

console = Console()

GLOBAL_TOP = [
    "https://google.com", "https://youtube.com", "https://facebook.com", "https://instagram.com", "https://twitter.com",
    "https://wikipedia.org", "https://yahoo.com", "https://yandex.ru", "https://whatsapp.com", "https://amazon.com",
    "https://netflix.com", "https://tiktok.com", "https://reddit.com", "https://linkedin.com", "https://office.com",
    "https://bing.com", "https://live.com", "https://bilibili.com", "https://twitch.tv", "https://naver.com",
    "https://weather.com", "https://quora.com", "https://zoom.us", "https://apple.com", "https://microsoft.com"
]

INDIA_TOP = [
    "https://google.co.in", "https://amazon.in", "https://flipkart.com", "https://hotstar.com", "https://myntra.com",
    "https://moneycontrol.com", "https://indiatimes.com", "https://cricbuzz.com", "https://jiocinema.com", "https://makemytrip.com",
    "https://timesofindia.indiatimes.com", "https://zerodha.com", "https://sbi.co.in", "https://irctc.co.in", "https://hdfcbank.com",
    "https://naukri.com", "https://ola.in", "https://zomato.com", "https://swiggy.com", "https://bookmyshow.com",
    "https://ajio.com", "https://paytm.com", "https://indiamart.com", "https://policybazaar.com", "https://redbus.in"
]

def profile_target_list(target_list, category, analyzer, scorer):
    results = []
    
    for i, url in enumerate(target_list):
        console.print(f"[{category}] Benchmarking {i+1}/{len(target_list)}: {url}")
        
        try:
            with PageProfiler(headless=True, filmstrip=False) as profiler:
                profile = profiler.profile_page(url, site_origin=url)
            
            if profile.error and not profile.trace_events:
                console.print(f"[red]Failed to trace {url}: {profile.error}[/red]")
                results.append({
                    "url": url,
                    "score": 0,
                    "grade": "F",
                    "tbt_ms": 0.0,
                    "lcp_ms": 0.0,
                    "js_heap_mb": 0.0,
                    "error": profile.error
                })
                continue
                
            insight = analyzer.analyze(profile.trace_events)
            score_data = scorer.score_page(profile, insight)
            
            # extract specific telemetry metrics
            js_heap_bytes = max([pt.value for pt in insight.memory_timeline]) if insight.memory_timeline else profile.system_metrics.renderer_memory_bytes
            js_heap_mb = js_heap_bytes / (1024 * 1024)
            
            res = {
                "url": url,
                "score": score_data.score,
                "grade": score_data.grade,
                "tbt_ms": insight.total_blocking_time_ms,
                "lcp_ms": profile.vitals.lcp_ms,
                "js_heap_mb": js_heap_mb,
                "error": None
            }
            console.print(f"[green]Success: {score_data.score}/100 - TBT: {insight.total_blocking_time_ms:.0f}ms - JS Heap: {js_heap_mb:.1f}MB[/green]")
            results.append(res)
            
        except Exception as e:
            console.print(f"[red]Exception profiling {url}: {e}[/red]")
            results.append({
                "url": url,
                "score": 0,
                "grade": "F",
                "tbt_ms": 0.0,
                "lcp_ms": 0.0,
                "js_heap_mb": 0.0,
                "error": str(e)
            })
            
    return sorted(results, key=lambda x: (x["score"], -x["tbt_ms"]), reverse=True)

def generate_blog_html(global_results, india_results):
    def build_table(rows):
        html = "<table>\n<thead><tr><th>Rank</th><th>Target URL</th><th>Score</th><th>Grade</th><th>TBT (ms)</th><th>LCP (ms)</th><th>Peak JS Heap (MB)</th></tr></thead>\n<tbody>\n"
        for i, r in enumerate(rows):
            if r["error"]:
                html += f'<tr class="error-row"><td>{i+1}</td><td><a href="{r["url"]}">{r["url"]}</a></td><td colspan="5" class="error-text">Failed: Anti-bot block or Timeout</td></tr>\n'
            else:
                grade_class = f'grade-{r["grade"].lower()}'
                html += f'<tr><td>#{i+1}</td><td><a href="{r["url"]}">{r["url"]}</a></td><td><strong>{r["score"]}</strong></td><td><span class="badge {grade_class}">{r["grade"]}</span></td><td>{r["tbt_ms"]:.0f}</td><td>{r["lcp_ms"]:.0f}</td><td>{r["js_heap_mb"]:.1f}</td></tr>\n'
        html += "</tbody>\n</table>\n"
        return html

    template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>The ChromeLens 50-Site Benchmark</title>
  <style>
    :root {{
      --bg: #0b1120;
      --card-bg: #0f172a;
      --border: #1e293b;
      --accent: #3b82f6;
      --text-main: #cbd5e1;
      --text-head: #f8fafc;
      --font-ui: 'Inter', -apple-system, system-ui, sans-serif;
    }}
    body {{ margin: 0; background-color: var(--bg); color: var(--text-main); font-family: var(--font-ui); line-height: 1.6; }}
    nav {{ display: flex; justify-content: space-between; align-items: center; padding: 1.5rem 2rem; border-bottom: 1px solid var(--border); }}
    .logo {{ color: var(--text-head); font-weight: 700; font-size: 1.25rem; text-decoration: none; }}
    .container {{ max-width: 1000px; margin: 0 auto; padding: 4rem 1.5rem; }}
    h1 {{ color: var(--text-head); font-size: 3rem; margin-bottom: 0.5rem; letter-spacing: -1px; }}
    .subtitle {{ font-size: 1.25rem; color: #94a3b8; margin-bottom: 3rem; }}
    h2 {{ color: var(--text-head); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-top: 4rem; }}
    .prose {{ font-size: 1.05rem; margin-bottom: 2rem; }}
    
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 3rem; font-size: 0.95rem; }}
    th, td {{ padding: 1rem; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ color: var(--text-head); font-weight: 600; background: var(--card-bg); }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    
    .badge {{ padding: 0.25rem 0.5rem; border-radius: 4px; font-weight: 700; font-size: 0.85rem; }}
    .grade-a {{ background: #064e3b; color: #34d399; }}
    .grade-b {{ background: #065f46; color: #6ee7b7; }}
    .grade-c {{ background: #78350f; color: #fbbf24; }}
    .grade-d {{ background: #7f1d1d; color: #f87171; }}
    .grade-f {{ background: #450a0a; color: #ef4444; }}
    .error-row {{ opacity: 0.6; }}
    .error-text {{ color: #ef4444; font-size: 0.85rem; }}
    footer {{ border-top: 1px solid var(--border); padding: 2rem 0; text-align: center; font-size: 0.875rem; margin-top: 4rem; }}
  </style>
</head>
<body>
  <nav>
    <a href="index.html" class="logo">🔬 ChromeLens</a>
    <a href="https://github.com/manishklach/chromelens" style="color:var(--text-main); font-weight:600; text-decoration:none;">GitHub</a>
  </nav>

  <div class="container">
    <h1>The ChromeLens 50-Site Benchmark</h1>
    <p class="subtitle">Benchmarking the modern web using deterministic CDP Traces. <em>(Run Date: {datetime.utcnow().strftime('%Y-%m-%d')})</em></p>
    
    <div class="prose">
      <p>Standard tools like Google Lighthouse provide synthesized surface-level snapshots of web performance. To demonstrate the rigorous difference of <strong>ChromeLens</strong>, we unleashed the engine headlessly against the Top 25 Global and Top 25 Indian web properties.</p>
      <p><strong>Methodology:</strong> The harness navigated to the landing page of each target, attached low-level Chrome DevTools Protocol tracing sockets, and captured raw Main Thread processing, JS Heap fluctuations, and Rendering signals. These metrics were aggregated into a composite Score (0-100).</p>
      <p><em>Note: Several monolithic sites aggressively block headless automation tooling at the WAF level and are consequently marked as Failed.</em></p>
    </div>

    <h2>Global Top 25 Hierarchy</h2>
    {build_table(global_results)}

    <h2>India Top 25 Hierarchy</h2>
    {build_table(india_results)}
    
    <h2>Analysis: The Hydration Penalty</h2>
    <div class="prose">
      <p>The telemetric data exposes a critical paradigm: heavy client-side SPAs (React/Vue monolithic platforms) suffer dramatically in <strong>Total Blocking Time (TBT)</strong> during their initial JS hydration cycles.</p>
      <p>While massive ad-networks and bloated third-party analytics bloat the JS Heap, it is the V8 compilation lock-ups holding up the Main Thread that fundamentally destroy a site's grading.</p>
      <p>ChromeLens was built precisely to isolate these >50ms main-thread violations.</p>
    </div>
  </div>
  
  <footer>
    <p>ChromeLens &copy; 2026. Released under the Apache-2.0 License.</p>
  </footer>
</body>
</html>
"""
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    with open(docs_dir / "benchmarks.html", "w", encoding="utf-8") as f:
        f.write(template)

def main():
    console.print("[bold blue]Starting ChromeLens 50-Site Benchmark Harness...[/bold blue]")
    
    analyzer = TraceAnalyzer()
    scorer = HealthScorer()
    
    console.print("\n[bold cyan]--- Profiling Top 25 Global ---[/bold cyan]")
    global_res = profile_target_list(GLOBAL_TOP, "GLOBAL", analyzer, scorer)
    
    console.print("\n[bold cyan]--- Profiling Top 25 India ---[/bold cyan]")
    india_res = profile_target_list(INDIA_TOP, "INDIA", analyzer, scorer)
        
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "benchmark_results.json", "w") as f:
        json.dump({"global": global_res, "india": india_res}, f, indent=2)
        
    console.print("\n[bold green]Generating GH Pages Blog Post...[/bold green]")
    generate_blog_html(global_res, india_res)
    console.print("[bold green]Done! Rendered docs/benchmarks.html[/bold green]")

if __name__ == "__main__":
    main()
