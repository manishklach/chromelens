# ChromeLens Next Release Requirements

## 1. Executive Summary

ChromeLens today is a Python-based site crawler and Chrome DevTools Protocol profiling tool that discovers same-origin pages, profiles them with Playwright + CDP, analyzes raw trace events for main-thread and rendering signals, and emits a Rich terminal summary plus a single-file HTML dashboard. Its implementation is compact and pragmatic: discovery lives in `chromelens.discovery`, profiling in `chromelens.profiler`, trace reduction and scoring in `chromelens.analysis`, and report rendering in `chromelens.report`.

The current gap is not data capture on individual pages; it is comparison, aggregation, and repeatability. ChromeLens can tell a user that a specific page was slow, but it does not yet provide a stable run artifact, template-level grouping for large crawls, robust before/after diffing, actionable layout-shift culprit extraction, or a containerized CI-first operating model. The code already contains the ingredients for a stronger platform, but not yet the packaging and data contracts needed for repeatable engineering workflows.

The next version should evolve ChromeLens from a page-by-page profiler into a template-aware, diff-capable, CI-friendly performance analysis platform. This release should preserve the existing crawl/profile/analyze/report pipeline while adding stable machine-readable artifacts, route clustering, comparative analysis layers, richer attribution, and standard export/packaging features.

These features matter because:

- Developers need a way to identify representative templates instead of manually scanning dozens or hundreds of near-duplicate URLs.
- Performance engineers need trace-derived comparisons across runs, routes, and third parties rather than one-off page snapshots.
- CI/CD systems need deterministic artifacts, threshold-based failure behavior, and containerized reproducibility.
- Open-source adopters need a practical tool that fits Playwright/CDP-based workflows without requiring a full observability platform.

## 2. Current-State Assessment

### 2.1 Repository Structure and Current Modules

Current package layout:

- `chromelens/cli.py`
  - Click-based CLI entrypoint.
  - Defines one command group and one main command: `crawl`.
- `chromelens/discovery/__init__.py`
  - Defines `DiscoveredPage`.
- `chromelens/discovery/crawler.py`
  - Implements `SiteCrawler`.
  - Uses `requests`, `BeautifulSoup`, `urllib.robotparser`, and sitemap parsing.
- `chromelens/profiler/__init__.py`
  - Defines `WebVitals`, `CDPMetrics`, `NetworkRequest`, `ConsoleMessage`, `SystemMetrics`, `TimeSeriesMetric`, `PageProfile`.
- `chromelens/profiler/page_profiler.py`
  - Implements `PageProfiler`.
  - Uses Playwright sync API and direct CDP sessions.
  - Supports page profiling and scripted flow profiling.
  - Supports optional screenshots, filmstrip capture, network throttling, and Playwright device emulation.
- `chromelens/profiler/vitals.py`
  - Contains JS snippet for extracting navigation timing, FCP, LCP, and CLS from the browser.
- `chromelens/analysis/__init__.py`
  - Defines `LongTask`, `ThirdPartyImpact`, `FilmstripFrame`, `TraceInsight`, `PageHealthScore`, `SiteHealthReport`.
- `chromelens/analysis/trace_analyzer.py`
  - Parses raw trace events into TBT, long tasks, layout/style/paint counts, GC counts/duration, CPU bins, memory timeline, and filmstrip frames.
- `chromelens/analysis/health_scorer.py`
  - Computes page and site scores.
  - Aggregates third-party impact by domain based on network requests.
- `chromelens/report/cli_report.py`
  - Renders site summary tables in terminal.
- `chromelens/report/html_report.py`
  - Combines profiles, scores, and trace insights for rendering.
- `chromelens/report/templates/dashboard.html`
  - Current single-file dashboard template using Chart.js CDN.
- `chromelens/demo_flow.py`
  - Demonstrates scripted interaction flow profiling.
- `scripts/run_benchmark.py`
  - External benchmark harness that profiles lists of URLs and generates docs pages.
- `tests/test_core.py`
  - Minimal unit tests for models, trace analysis, and health scoring.

### 2.2 Current Crawl/Profile/Analyze/Report Pipeline

The current `crawl` command in `chromelens/cli.py` performs four in-process phases:

1. Discovery
   - `SiteCrawler` loads `robots.txt`, tries `sitemap.xml`, seeds the base URL, then recursively fetches same-origin HTML links via `requests`.
   - URL normalization is simple and destructive: fragments and query strings are stripped during link extraction, trailing slash is trimmed, and same-origin filtering is enforced.

2. Profiling
   - `PageProfiler` launches Chromium through Playwright, creates a context per page, optionally emulates a device, optionally applies network emulation, then attaches a CDP session.
   - It enables `Performance`, optionally `Network`, starts `Tracing`, navigates to the page with `wait_until="networkidle"`, waits an extra 1500 ms, stops tracing, calls `Performance.getMetrics`, attempts `SystemInfo.getProcessInfo`, evaluates vitals JS, and optionally saves a screenshot.
   - Network responses and console messages are collected per page.
   - Raw trace events are retained in memory in each `PageProfile`.

3. Analysis and Scoring
   - `TraceAnalyzer.analyze()` converts trace events into a `TraceInsight`.
   - `HealthScorer.score_page()` combines vitals, TBT/long-task/GC penalties, network size, third-party request size, and console errors into a 0-100 score and letter grade.
   - `HealthScorer.score_site()` computes site average score, aggregates third-party impact by domain, and finds common issues repeated across pages.

4. Reporting
   - `print_cli_report()` emits terminal tables.
   - `generate_html_report()` renders a single HTML file using the current dashboard template.

### 2.3 Current Artifact Outputs

Current outputs from `crawl` are:

- `report.html` in the requested output directory.
- Optional screenshots under `output/screenshots/`.
- In-memory score/profile/trace structures, but no stable persisted run artifact from the main CLI.

Current outputs outside the main CLI:

- `scripts/run_benchmark.py` writes `benchmark_results.json` and generated docs pages, but this is benchmark-specific, not a versioned core artifact contract.

### 2.4 Current CLI Surface

Current CLI surface is limited to:

- `chromelens --verbose`
- `chromelens crawl URL`

Current `crawl` options:

- `--output / -o`
- `--max-pages`
- `--max-depth`
- `--headless / --headed`
- `--screenshots / --no-screenshots`
- `--filmstrip / --no-filmstrip`
- `--network`
- `--device`

Notable current CLI limitations:

- No command for `analyze`, `diff`, `cluster`, `export`, or `report` from existing artifacts.
- No persisted machine-readable artifact emitted by default.
- No explicit CI gating flags or exit codes beyond process success/failure.
- Top-level `--help` currently risks a Windows encoding failure because the CLI docstring/help includes non-ASCII emoji.

### 2.5 Current Limitations Motivating This Release

The codebase suggests the following limitations that directly motivate the requested work:

- Page-level only: site reports are flat lists of URLs; there is no template-level grouping.
- No stable schema: dataclasses are internal structures, not a versioned public artifact format.
- No diffing: there is no baseline/candidate comparison at page, template, or third-party level.
- Third-party analysis is size-centric and network-centric; it does not attempt CPU attribution from trace data.
- CLS is captured only as a scalar in `WebVitals`; individual layout shift events and culprits are not extracted.
- Headless/headed divergence is user-selectable but not measurable as a first-class paired mode.
- No HAR export.
- No official Docker image or CI packaging guidance.
- Reporting is strong for single-run visualization but does not support comparison workflows.
- Tests are minimal and mostly unit-level; there are no artifact-schema, snapshot, or compatibility tests.

## 3. Product Goals

This release should meet the following product goals:

- Reduce noise from large crawls by aggregating related routes into stable template signatures while preserving page-level drill-down.
- Enable repeatable before/after performance comparisons using persisted, versioned run artifacts.
- Expose third-party cost primarily by main-thread harm and user-facing performance impact, not only payload size.
- Make CLS debugging actionable by surfacing likely culprit nodes, shifts, and visual overlays.
- Detect and quantify headless versus headed discrepancies as an explicit trustworthiness check.
- Improve interoperability with downstream tooling through JSON artifacts and HAR export.
- Improve deployability through a pre-packaged Docker image suitable for GitHub Actions, Jenkins, and local CI runners.
- Preserve the current core flow and keep adoption cost low for existing ChromeLens users.

## 4. Non-Goals

This release explicitly does not attempt to do the following:

- Become a full Real User Monitoring platform.
- Replace browser lab profiling with statistically rigorous field telemetry.
- Provide perfect script CPU attribution for every trace event; attribution may remain heuristic and best-effort.
- Deliver full visual regression testing or pixel diffing.
- Rebuild discovery around a distributed crawler or asynchronous architecture.
- Rewrite the reporting stack away from the current HTML dashboard approach.
- Require external AI APIs for clustering or attribution.
- Guarantee that headless/headed divergence can be fully normalized across every environment.
- Support every possible HAR producer/consumer nuance beyond broadly compatible HAR 1.2 export.

## 5. Detailed Functional Requirements

### 5.1 Route Clustering / Template View

#### Problem Statement

In large crawls, many URLs represent the same structural page template, such as product detail pages, category listings, blog articles, or localized variants. The current page list forces users to inspect many near-duplicates manually, which obscures systemic issues and makes regression tracking noisy.

#### User Stories

- As a performance engineer, I want `/products/123` and `/products/456` grouped together so I can reason about the product detail template rather than every individual SKU.
- As a developer, I want to override default clustering rules for my routing conventions.
- As a CI user, I want template-level summaries and thresholds so a crawl with hundreds of pages does not produce unmanageable noise.
- As an advanced user, I want page-level detail preserved so I can drill down from a template cluster to an outlier page.

#### Functional Requirements

- ChromeLens SHALL compute a route template signature for each profiled page in a crawl run.
- The default clustering implementation SHALL be fully offline and deterministic.
- Default heuristics SHOULD operate on normalized URL path segments and optionally query parameter retention rules.
- Default heuristics SHALL support common dynamic-segment detection patterns, including:
  - Numeric IDs.
  - UUID-like segments.
  - Slug-plus-ID combinations.
  - Long opaque hashes or tokens.
  - Locale prefixes when configured.
- ChromeLens SHALL preserve the original URL and page-level metrics even when a page belongs to a template cluster.
- ChromeLens SHALL compute template-level aggregate metrics from member pages, including:
  - Page count.
  - Representative sample URLs.
  - Mean, median, p75, p90, and max for key metrics where enough pages exist.
  - LCP, FCP, CLS, TTFB summaries.
  - TBT summaries.
  - Long-task count summaries.
  - Layout/style/paint summaries.
  - Third-party summaries aggregated across pages in the cluster.
- ChromeLens SHALL assign a stable template identifier within a run artifact.
- ChromeLens SHALL support rule-based overrides via config for:
  - Explicit regex-to-template mappings.
  - Query parameter include/exclude behavior.
  - Locale collapsing rules.
  - Path segment masking rules.
  - Pages to exclude from clustering.
- ChromeLens SHOULD support future AI-assisted clustering as an extension point, but the initial implementation SHALL not require network access or external APIs.
- The AI-assisted extension point, if later implemented, SHALL operate after deterministic preprocessing and SHALL be optional.

#### Inputs

- Existing discovered/profiled page URLs.
- Optional config file section for template rules.
- Optional CLI flags controlling clustering mode.

#### Outputs

- Page artifact entries enriched with template signature and template ID.
- Template aggregation artifact for the run.
- HTML report sections for template overview and template drill-down.
- Optional CLI summary table for top/bottom templates.

#### CLI/Report/Dashboard Changes

- `crawl` SHALL enable template clustering by default unless disabled.
- CLI SHALL expose a flag such as `--template-mode [auto|off]` and optional config path.
- HTML report SHALL include:
  - Template overview table.
  - Sorting by worst p75/p90 metric or template score.
  - Drill-down from template to member pages.
  - Clear labeling of template rules and overrides if applied.

#### Edge Cases

- Low-sample templates with only one page SHALL still appear and behave like single-member clusters.
- Homepages and empty-path routes SHALL not be over-normalized into generic buckets.
- Query parameters used for true route identity SHALL be preservable through config.
- Internationalized routes may be grouped or split depending on config.
- Pages discovered from sitemap versus links SHALL still converge to the same template when normalized.

#### Acceptance Criteria

- On a crawl containing multiple obvious parametric URL families, ChromeLens groups them into consistent template clusters without removing page-level detail.
- Config overrides can merge or split templates predictably.
- Template aggregates remain stable across repeated runs on the same URL set.
- HTML report users can navigate from a template summary to specific URLs and outliers.

#### Dependencies / Technical Considerations

- This feature depends on a stable run artifact and page identifiers.
- New module placement should fit existing style, for example `chromelens/analysis/templates.py` or `chromelens/analysis/route_clustering.py`.
- Aggregation logic should not depend on HTML rendering and must be reusable by diffing and CI gating.

### 5.2 Performance Diffing Engine

#### Problem Statement

ChromeLens can analyze a single run, but cannot compare baseline and candidate results in a structured way. This blocks CI use cases and makes regressions hard to quantify.

#### User Stories

- As a maintainer, I want to compare a PR run against `main` and fail the build if key metrics regress past thresholds.
- As a performance engineer, I want per-page, per-template, and per-third-party deltas in machine-readable and human-readable form.
- As a developer, I want clear statements like "template `/products/{id}` regressed p75 TBT by 180 ms".

#### Functional Requirements

- ChromeLens SHALL define a versioned, stable run artifact schema suitable for storing the results of a crawl run.
- ChromeLens SHALL implement diffing between two run artifacts: baseline and candidate.
- Diffing SHALL support:
  - Per-page metrics.
  - Per-template aggregates.
  - Third-party summaries.
  - Overall site summary metrics.
- Diff matching SHALL use stable identifiers:
  - Exact normalized URL for page-level comparisons.
  - Template ID/signature for template-level comparisons.
  - Domain/origin key for third-party comparisons.
- Diffing SHALL explicitly handle:
  - Added URLs.
  - Removed URLs.
  - Added/removed templates.
  - Added/removed third parties.
- Diff engine SHALL emit:
  - A JSON diff artifact.
  - CLI diff summary.
  - HTML diff report.
- Diff engine SHALL support configurable regression thresholds for CI gating at:
  - Overall run level.
  - Template level.
  - Page level.
  - Third-party metrics where applicable.
- Diff output SHALL include human-readable regression statements with metric name, baseline, candidate, absolute delta, and percent delta where meaningful.
- Build failure behavior SHALL be deterministic and controllable by CLI flags.

#### Inputs

- Two run artifact files.
- Optional threshold config/flags.
- Optional selection filters such as URL, template, or metric subsets.

#### Outputs

- Diff artifact JSON.
- Optional diff HTML at a specified path.
- Terminal summary and exit code.

#### CLI/Report/Dashboard Changes

- New command SHOULD be added, such as `chromelens diff baseline.json candidate.json`.
- `crawl` MAY support in-process diffing when given a baseline artifact via flag.
- HTML diff report SHALL separate:
  - Summary regressions.
  - Site-level score and metric deltas.
  - Template-level regressions.
  - Page-level regressions.
  - Added/removed pages.
  - Third-party deltas.

#### Edge Cases

- If a page exists only in candidate or baseline, the diff SHALL mark it added or removed and SHALL not fabricate missing metrics.
- If template definitions change due to clustering rule changes, the diff SHALL surface schema/config incompatibility or template matching degradation.
- If artifacts come from different schema versions, the diff SHALL either:
  - Use an explicit compatibility path, or
  - Fail with a clear error describing incompatibility.

#### Acceptance Criteria

- Baseline/candidate artifacts with overlapping pages produce accurate deltas.
- Added/removed pages are clearly represented.
- Threshold breaches produce non-zero exit codes when gating is enabled.
- HTML diff report is understandable without needing to inspect raw JSON.

#### Dependencies / Technical Considerations

- Requires persisted run artifacts and explicit schema versioning.
- Requires stable page/template/third-party identifiers.
- Diff logic should be separate from report rendering, for example under `chromelens/analysis/diffing.py`.

### 5.3 Comparative Third-Party Cost Analysis

#### Problem Statement

Current third-party impact is aggregated by domain using request count, bytes, and duration, then sorted by total bytes. This is helpful but incomplete because the main-thread cost of third-party JavaScript is often more important than transfer size.

#### User Stories

- As a performance engineer, I want to know which third parties consume the most main-thread time, not just which ones ship the most bytes.
- As a developer, I want first-party assets hosted on CDNs I control to be marked as owned and not unfairly blamed as third-party.
- As a site owner, I want a site-wide and per-page wall-of-shame view for third-party harm.

#### Functional Requirements

- ChromeLens SHALL compute an enriched third-party summary that combines network data with trace-derived evidence where possible.
- The initial attribution model MAY be approximate, but it SHALL:
  - Distinguish network attribution from trace/CPU attribution.
  - Emit confidence labels.
  - Explain uncertainty in the report.
- Third-party aggregation SHALL support both domain-level and origin-level keys, with config controlling the grouping key.
- ChromeLens SHALL distinguish first-party and third-party using origin comparisons plus config-based ownership overrides.
- Ownership overrides SHALL support:
  - Domain allowlists.
  - Domain aliases.
  - Explicit owned-domain mappings.
- ChromeLens SHALL rank third parties by at least:
  - Total network bytes.
  - Total request count.
  - Total response duration.
  - Approximate main-thread blocking contribution.
  - Page coverage.
- Per-page output SHALL show the highest-cost third parties for that page.
- Site-wide output SHALL provide a comparative wall-of-shame view across the run.
- Attribution logic SHOULD correlate:
  - `NetworkRequest` URLs/domains.
  - Trace event categories/names where script URLs or frame/origin information are present.
  - Resource type and MIME type hints.
- Confidence levels SHALL be represented as at least `high`, `medium`, `low`, `unknown`.

#### Inputs

- Page network requests.
- Trace events and derived long tasks.
- Optional ownership/allowlist config.

#### Outputs

- Per-page third-party cost summaries.
- Site-wide third-party summary artifact.
- Diff-compatible third-party identifiers and metrics.

#### CLI/Report/Dashboard Changes

- CLI summary SHOULD show the top third parties by CPU impact and bytes separately.
- HTML report SHALL include:
  - Site-wide wall-of-shame table.
  - Per-page top offenders.
  - Attribution confidence badges.
  - First-party/third-party labeling and ownership overrides if applied.

#### Edge Cases

- Script CPU time may lack a URL; ChromeLens SHALL record unattributed CPU cost rather than silently drop it.
- Shared CDN domains may host both owned and external assets; config must be able to override classification.
- Inline scripts may consume CPU without a network request.
- Cross-origin iframes may create attribution ambiguity; output should surface ambiguity explicitly.

#### Acceptance Criteria

- Reports surface a more useful ranking than raw bytes alone.
- Ownership override config changes classification deterministically.
- The report clearly distinguishes confident attribution from approximate attribution.

#### Dependencies / Technical Considerations

- May require enabling additional trace categories or parsing more event fields.
- Should avoid promising perfect attribution when the raw trace does not support it.

### 5.4 CLS Heatmap / Layout Shift Culprit Extraction

#### Problem Statement

ChromeLens currently captures only aggregate CLS, which tells users a page shifted but not what moved or why. That is not actionable enough for debugging.

#### User Stories

- As a frontend engineer, I want to see the largest layout shift contributors and the likely DOM elements involved.
- As a performance engineer, I want a screenshot or thumbnail overlay to quickly identify shift hotspots.
- As a CI reviewer, I want the diff report to tell me if layout instability worsened on a template.

#### Functional Requirements

- ChromeLens SHALL parse layout shift events from available browser/trace/browser-performance sources.
- ChromeLens SHALL identify the most significant layout shift contributors per page.
- Where available, ChromeLens SHALL extract culprit metadata, including:
  - CSS selector or best-effort selector.
  - Tag name.
  - Element ID.
  - Class list or abbreviated class signature.
  - Bounding box before/after or current bounding box.
  - Shift score contribution.
  - Timestamp.
- If full selector reconstruction is not available from trace data alone, ChromeLens MAY use in-page JS collection during profiling to enrich layout shift attribution.
- ChromeLens SHALL provide confidence scoring for culprit extraction and clearly disclose when the mapping is best-effort.
- HTML report SHALL include a CLS section for pages with non-trivial CLS that shows:
  - Total CLS.
  - Top shift events.
  - Suspect elements.
  - Optional annotated screenshot or thumbnail overlay.
- Overlay generation MAY be best-effort and static.
- If overlay generation is unavailable, the report SHALL still present structured culprit metadata.

#### Inputs

- Page trace events.
- Browser performance entries for `layout-shift`.
- Optional page screenshot.

#### Outputs

- CLS culprit schema in run artifact.
- Optional annotated image assets.
- Report cards and diff summaries for CLS changes.

#### CLI/Report/Dashboard Changes

- `crawl` MAY enable CLS culprit extraction by default when screenshots are enabled.
- HTML report SHALL show a visible CLS debugging section for affected pages.
- Diff report SHALL highlight pages/templates with meaningful CLS regressions and list changed culprit candidates when possible.

#### Edge Cases

- Some pages may expose CLS but no reliable node attribution.
- Late shifts after the reporting window may be missed.
- Dynamic or removed DOM nodes may prevent exact selector reconstruction.
- Cross-origin frame shifts may be only partially attributable.

#### Acceptance Criteria

- Pages with significant CLS surface at least one structured culprit candidate when browser data permits.
- Reports clearly distinguish exact attribution from heuristic attribution.
- Users can identify likely shift regions visually or via metadata without opening DevTools manually.

#### Dependencies / Technical Considerations

- May require augmenting `EXTRACT_WEB_VITALS_JS` or adding a dedicated in-page collector.
- Should minimize profiler overhead and not distort the very metrics being measured.

### 5.5 Headless vs Headed Reality Check

#### Problem Statement

ChromeLens already supports headless or headed execution, but not direct comparison. Users have no first-class way to detect when headless results are materially different from real visible-browser behavior.

#### User Stories

- As a maintainer, I want to verify whether headless measurements are representative enough for CI gating.
- As a performance engineer, I want page-level and template-level deltas between headless and headed modes.
- As a debugging user, I want screenshot pairs to understand where rendering behavior diverges.

#### Functional Requirements

- ChromeLens SHALL support a paired-run mode that profiles the same URL set in both headless and headed browser modes.
- Paired mode SHALL reuse the same discovery result or input URL list to ensure like-for-like comparison.
- ChromeLens SHALL compute page-level and template-level deltas between headless and headed metrics.
- Paired mode SHALL support optional screenshot pairs for direct visual comparison.
- ChromeLens SHALL support configurable thresholds that define meaningful divergence for:
  - LCP.
  - CLS.
  - TBT.
  - Score.
  - Optional screenshot mismatch indicator if later implemented.
- The report SHALL present headless/headed comparison as a trustworthiness or reproducibility check, not as a universal truth.
- The output SHALL include caveats about environment sensitivity, rendering nondeterminism, and anti-bot behavior.

#### Inputs

- URL set or run artifact.
- Browser mode options.
- Optional screenshot capture.

#### Outputs

- Mode-comparison artifact.
- HTML paired comparison report or section.
- Optional gating result if divergence exceeds thresholds.

#### CLI/Report/Dashboard Changes

- `crawl` SHOULD support a mode such as `--reality-check` or `--compare-modes`.
- Alternative design: separate command such as `chromelens reality-check URL`.
- HTML report SHALL include:
  - Summary of divergence rate.
  - Worst divergent pages/templates.
  - Screenshot pair links when enabled.

#### Edge Cases

- Headed mode may be unavailable in some CI environments; the feature SHALL fail clearly or allow skipping.
- Anti-bot defenses may behave differently across modes.
- Runs are sensitive to hardware, GPU, display server, and window manager conditions.

#### Acceptance Criteria

- Paired mode profiles the same route set in both modes and emits clear deltas.
- Meaningful divergences are easy to identify.
- The resulting artifact is reusable by future diffing/reporting logic.

#### Dependencies / Technical Considerations

- Strongly benefits from run artifact reuse and deterministic URL ordering.
- In CI, headed mode may require `xvfb` or equivalent; Docker image and docs must account for this.

### 5.6 HAR Export

#### Problem Statement

ChromeLens captures network requests internally, but cannot currently export standard HAR files for downstream tooling, debugging, or sharing.

#### User Stories

- As a developer, I want to open the network log in standard HAR-compatible tools.
- As a performance engineer, I want to correlate ChromeLens results with external HAR viewers and regression tools.

#### Functional Requirements

- ChromeLens SHALL support HAR export in a broadly compatible HAR 1.2 format.
- Export SHALL support:
  - One HAR per page.
  - Optional combined HAR for the run when feasible.
- HAR generation SHALL map from current network capture structures and enrich them where required to fit the HAR schema.
- The export SHALL document limits where exact HAR fields are unavailable from current capture data.
- HAR export SHALL preserve request URL, method, status, MIME type, timing fields where available, and payload/response size approximations where available.
- If a field cannot be reliably populated, ChromeLens SHALL either omit it when allowed by the schema or fill it with a documented placeholder/default.

#### Inputs

- `NetworkRequest` logs per page.
- Optional page metadata and timings.

#### Outputs

- `.har` files under the output directory.
- Artifact references to HAR file paths.

#### CLI/Report/Dashboard Changes

- `crawl` SHOULD support `--har [off|per-page|combined|both]`.
- Report MAY link to generated HAR files, but HAR export is primarily for machine/tool interoperability.

#### Edge Cases

- Current capture is response-oriented rather than request lifecycle-complete; some HAR timing/detail fidelity will be limited.
- Redirect chains and cached resource semantics may be incomplete unless capture is expanded.
- Combined HAR files may become very large on large crawls.

#### Acceptance Criteria

- Generated HAR files open in at least one common HAR viewer without schema errors.
- Per-page HAR output corresponds to the page network requests captured during profiling.
- Limitations are documented and surfaced in generated metadata.

#### Dependencies / Technical Considerations

- May require improving network capture in `PageProfiler` beyond the current response callback model.
- HAR generation should be modular and usable independently from HTML reporting.

### 5.7 Docker / CI Packaging

#### Problem Statement

ChromeLens currently relies on local Python and Playwright setup, which increases CI friction and environment drift.

#### User Stories

- As a CI maintainer, I want a prebuilt Docker image that already contains Python, ChromeLens, Playwright, and Chromium dependencies.
- As a Jenkins or GitHub Actions user, I want predictable output directory mounting and non-root-safe defaults.

#### Functional Requirements

- The project SHALL provide an official Dockerfile and documented image usage.
- The image SHALL include:
  - Supported Python runtime.
  - Project installation.
  - Playwright Python package.
  - Chromium browser binary and required runtime libraries.
- The image SHOULD support running as non-root where practical.
- The image SHALL support mounting an output volume for reports and artifacts.
- The image SHALL be documented for GitHub Actions and Jenkins usage.
- The image SHALL document both headless-only CI usage and what is required for headed or paired mode.
- Build instructions SHALL be reproducible and pinned enough for stable CI behavior.

#### Inputs

- Standard CLI invocation.
- Mounted config and output paths.

#### Outputs

- Docker image.
- Example CI snippets and documentation.

#### CLI/Report/Dashboard Changes

- No direct report changes required.
- CLI docs SHALL include container examples and output path examples.

#### Edge Cases

- Headed mode may require additional system packages or virtual display support.
- Browser sandboxing may differ across CI providers.
- Large screenshots or traces may create high artifact volume in containerized runs.

#### Acceptance Criteria

- A user can run `chromelens crawl` inside the documented container and receive HTML plus JSON artifacts without manual browser installation.
- GitHub Actions and Jenkins examples are sufficient for a new user to run ChromeLens in CI.

#### Dependencies / Technical Considerations

- This depends on the finalized artifact/output directory layout.
- Container image should not bake in site-specific config or secrets.

## 6. Cross-Cutting Technical Requirements

- Backward compatibility:
  - Existing `chromelens crawl URL` usage SHALL continue to work.
  - Existing HTML report generation SHALL remain available.
  - Existing data classes may be extended, but current basic report outputs must not disappear abruptly.
- Schema/versioning strategy:
  - Every machine-readable artifact SHALL include `schema_version`.
  - Any incompatible artifact change SHALL increment the version.
- Deterministic artifact generation:
  - Output ordering SHALL be stable.
  - JSON serialization SHALL use stable key ordering where practical.
  - Identifiers and aggregates SHALL not depend on random ordering of dict/set iteration.
- Config surface:
  - New config SHOULD be supported via a file format already comfortable for Python tooling, such as TOML in `pyproject.toml` or a dedicated `.toml` file.
  - CLI flags SHALL override config values.
- Performance and scalability expectations:
  - New aggregation/diffing features SHALL work on crawls of at least hundreds of pages without requiring raw trace reprocessing in the HTML layer.
  - Template aggregation and diffing SHOULD operate on persisted artifacts rather than raw trace events whenever possible.
- Error handling:
  - Partial failures at the page level SHALL be represented in artifacts.
  - Diff/report commands SHALL fail clearly on missing or incompatible artifacts.
- Logging and diagnostics:
  - New phases SHALL emit structured and human-readable logs consistent with the current CLI style.
  - Artifact paths and schema versions SHOULD be logged.
- Security and privacy considerations:
  - Artifacts may contain URLs, console logs, screenshot paths, and third-party domains.
  - Documentation SHALL warn users before publishing artifacts from sensitive environments.
  - Future options SHOULD allow redaction of query strings, headers, or screenshots.
- Stable sort/order behavior:
  - Page lists, template lists, and third-party tables SHALL have deterministic default sorting.
- Portability constraints:
  - Features SHALL remain realistic for Python 3.10+ and Playwright-based execution.
  - The default implementation SHALL support Linux CI environments first; Windows/macOS should remain functional where practical.

## 7. Data Model / Artifact Requirements

ChromeLens SHALL introduce a first-class machine-readable run artifact and related derivative artifacts.

### 7.1 Run Artifact Schema

Minimum requirements:

- Top-level fields:
  - `schema_version`
  - `artifact_type` with value such as `run`
  - `generated_at`
  - `chromelens_version`
  - `site_url`
  - `crawl_config`
  - `environment`
  - `summary`
  - `pages`
  - `templates`
  - `third_party_summary`
- Required compatibility expectations:
  - Consumers MUST reject unsupported major schema versions.
  - Minor additive fields SHOULD be ignored safely.

Page entries SHALL include:

- Stable `page_id`
- Original URL
- Normalized URL used for matching
- Discovery metadata
- Template ID/signature
- Status/error fields
- Vitals
- CDP metrics
- Trace summary metrics
- Third-party per-page summary
- Screenshot/HAR paths if generated

### 7.2 Template Aggregation Schema

Each template entry SHALL include:

- `template_id`
- `template_signature`
- `display_name`
- `page_count`
- Representative sample URLs
- Aggregate score and grade
- Metric summaries including mean/median/p75/p90/max as applicable
- Long-task and layout-shift summaries
- Third-party summaries across member pages

### 7.3 Diff Artifact Schema

Minimum fields:

- `schema_version`
- `artifact_type` with value such as `diff`
- `baseline_ref`
- `candidate_ref`
- `compatibility`
- `summary`
- `page_diffs`
- `template_diffs`
- `third_party_diffs`
- `added_pages`
- `removed_pages`
- `added_templates`
- `removed_templates`
- `threshold_results`

Each diff entry SHALL include stable matching keys plus:

- Baseline metric value
- Candidate metric value
- Absolute delta
- Percent delta where valid
- Regression/improvement/neutral classification

### 7.4 Third-Party Summary Schema

Each entry SHALL include:

- Stable `third_party_key`
- Domain/origin
- Ownership classification (`first_party`, `third_party`, `owned_external`, `unknown`)
- Request count
- Total bytes
- Total duration
- Approximate CPU or blocking attribution metrics
- Attribution confidence
- Pages/templates present

### 7.5 CLS Culprit Schema

Per page, CLS culprit output SHALL include:

- Total CLS
- List of shift events
- Each event containing:
  - Timestamp
  - Shift score contribution
  - `had_recent_input`
  - Culprit candidates
- Culprit candidate fields:
  - Selector or node descriptor
  - Tag
  - ID
  - Classes
  - Bounding box if available
  - Confidence
  - Notes on uncertainty

### 7.6 Optional Mode-Comparison Schema

If paired mode is implemented, the mode comparison artifact SHALL include:

- `schema_version`
- `artifact_type` such as `mode_comparison`
- Shared crawl input metadata
- `headless_run_ref`
- `headed_run_ref`
- Page/template comparison entries
- Divergence threshold results

## 8. CLI Requirements

### 8.1 General Requirements

- Existing `crawl` command SHALL remain.
- New commands SHOULD be added rather than overloading `crawl` for every workflow.
- Commands SHALL prefer artifact-driven workflows once artifacts exist.

### 8.2 Proposed Commands and Flags

Recommended additions:

- `chromelens crawl URL`
  - New flags:
    - `--artifact-path`
    - `--template-mode [auto|off]`
    - `--config`
    - `--har [off|per-page|combined|both]`
    - `--fail-on-regression` only when baseline diffing is requested
    - `--baseline-artifact`
    - `--compare-modes`
- `chromelens diff BASELINE_ARTIFACT CANDIDATE_ARTIFACT`
  - Flags:
    - `--output`
    - `--json-out`
    - `--html-out`
    - `--thresholds`
    - `--fail-on-regression`
- `chromelens report ARTIFACT`
  - Renders HTML from an existing artifact without re-crawling.
- `chromelens export-har ARTIFACT`
  - Optional if HAR export is not folded into `crawl`.

### 8.3 Command Examples

```bash
chromelens crawl https://example.com \
  --output reports/example \
  --artifact-path reports/example/run.json \
  --template-mode auto
```

```bash
chromelens diff reports/main/run.json reports/pr/run.json \
  --html-out reports/pr/diff.html \
  --json-out reports/pr/diff.json \
  --fail-on-regression
```

```bash
chromelens crawl https://example.com \
  --compare-modes \
  --screenshots \
  --output reports/reality-check
```

### 8.4 Default Behavior

- `crawl` SHALL still generate the HTML report by default.
- `crawl` SHOULD also generate a run artifact by default in the output directory once the new schema exists.
- Template clustering SHOULD default to enabled.
- HAR export SHOULD default to off unless explicitly requested.

### 8.5 Backward Compatibility

- Existing flags and default HTML output SHALL remain valid.
- Any renamed behavior SHALL preserve aliases for at least one release where practical.

### 8.6 Exit Codes

Recommended exit code behavior:

- `0`: success, no gating failures.
- `1`: operational error, invalid config, unsupported schema, runtime failure.
- `2`: successful execution with regression threshold failure for CI gating.

## 9. Reporting / Dashboard Requirements

- Existing report strengths to preserve:
  - Single-file HTML.
  - Clear site summary.
  - Page drill-down.
  - Embedded charts/filmstrip.
- New single-run report sections:
  - Template overview.
  - Expanded third-party analysis.
  - CLS culprit section.
  - Optional HAR links.
- Diff report UX requirements:
  - Immediate top-line answer on pass/fail and worst regressions.
  - Separate regressions from improvements.
  - Clear treatment of added/removed pages and templates.
  - Metric deltas visible without opening JSON.
- Drill-down behavior:
  - Template -> page -> per-page detail.
  - Third-party summary -> pages/templates where present.
  - CLS section -> culprit candidates and overlay if available.
- Sorting/filtering expectations:
  - Sort templates by worst p75/p90 score or chosen metric.
  - Sort third parties by CPU harm by default, with alternate sort for bytes.
  - Filter to regressions only in diff view.
- Visual hierarchy:
  - Summary cards first.
  - Actionable hotspot tables second.
  - Detailed page/template sections below.
- Messaging around approximate attribution:
  - CPU attribution and CLS culprit extraction SHALL include badges or text indicating confidence and uncertainty.
- Dashboard implementation guidance:
  - Avoid forcing Jinja templates to recompute heavy aggregations.
  - Render from artifact-ready structures.

## 10. Testing Requirements

Required tests for new work:

- Unit tests:
  - Route normalization and clustering heuristics.
  - Template aggregation math.
  - Diff calculations and threshold evaluation.
  - Third-party attribution classification and ownership overrides.
  - CLS culprit extraction parsers.
  - HAR serialization.
- Integration tests:
  - End-to-end crawl producing a run artifact and HTML report.
  - Artifact-to-diff flow using fixtures.
  - Headless/headed paired mode on a controlled local fixture site where feasible.
- Artifact fixture tests:
  - Golden JSON fixtures for run artifacts, template aggregates, diff artifacts, and HAR files.
  - Backward compatibility checks for schema version handling.
- Regression tests for old behavior:
  - Existing `crawl` HTML generation.
  - Existing scoring behavior for basic traces.
  - Existing CLI flags.
- Deterministic snapshot/golden tests:
  - Template view HTML fragments or structured render context.
  - Diff summary output.
- Minimum test coverage expectation:
  - New modules SHOULD target meaningful coverage around logic-heavy paths, especially clustering, diffing, schema serialization, and threshold handling.

## 11. Implementation Plan

### Phase 1: Shared Schemas and Artifact Versioning

Scope:

- Introduce artifact models and serializers.
- Persist run artifact from `crawl`.
- Add `schema_version`, stable IDs, and deterministic serialization.

Likely files/modules:

- New `chromelens/artifacts/` package or similar.
- Modifications to `chromelens/cli.py`.
- Modifications to `chromelens/report/html_report.py` to accept artifact-backed structures.
- Tests for schema serialization.

### Phase 2: Route Clustering

Scope:

- Implement deterministic route normalization and template clustering.
- Add config overrides.
- Add template aggregation to artifact and report.

Likely files/modules:

- New `chromelens/analysis/route_clustering.py`.
- New config parsing module.
- Updates to HTML report template.

### Phase 3: Diff Engine

Scope:

- Implement run artifact comparison.
- Add CLI diff command.
- Add JSON diff artifact and HTML diff report.

Likely files/modules:

- New `chromelens/analysis/diffing.py`.
- New report template for diff view.
- CLI additions.

### Phase 4: Third-Party Analysis

Scope:

- Enrich third-party aggregation with ownership overrides and approximate CPU attribution.
- Improve report presentation and diff compatibility.

Likely files/modules:

- New or extended `chromelens/analysis/third_party.py`.
- Updates to profiler capture if additional trace/network fields are required.

### Phase 5: CLS Culprit Extraction

Scope:

- Capture detailed layout shift events and culprit metadata.
- Add overlay or thumbnail annotation path if feasible.

Likely files/modules:

- New `chromelens/analysis/cls_analysis.py`.
- Updates to `chromelens/profiler/vitals.py` and possibly `page_profiler.py`.

### Phase 6: Headed/Headless Paired Mode

Scope:

- Add paired-run orchestration and mode-comparison artifact/report.

Likely files/modules:

- CLI orchestration updates.
- New comparison module or extension of diffing infrastructure.

### Phase 7: HAR Export and Docker Packaging

Scope:

- HAR serializer and CLI flag/command.
- Dockerfile, docs, and CI examples.

Likely files/modules:

- New export module.
- Repository root `Dockerfile`.
- GitHub Actions examples under `docs/` or `.github/`.

### Phase 8: Tests, Docs, and Polish

Scope:

- Expand fixtures and integration coverage.
- Update README and command docs.
- Clean up Windows CLI encoding issue and other compatibility rough edges.

### Recommended Order of Implementation

Recommended order:

1. Artifact schema/versioning.
2. Route clustering/template aggregation.
3. Diff engine.
4. Third-party enrichment.
5. CLS culprit extraction.
6. Headless/headed paired mode.
7. HAR export.
8. Docker/CI packaging.

### Risks

- Overloading the initial schema with raw trace payloads that make artifacts too large.
- Building diffing before identifiers and template semantics are stable.
- Overpromising attribution precision for third-party CPU or CLS culprits.
- Introducing rendering/report complexity before data contracts are settled.

### Areas Where Abstraction Should Be Introduced Carefully

- Keep raw-capture models separate from persisted artifact models.
- Keep aggregation logic separate from Jinja rendering.
- Do not tightly couple diffing to one specific HTML layout.
- Avoid refactoring the crawler/profiler into a new execution engine unless required.

## 12. Open Questions / Tradeoffs

- How aggressive should route normalization be by default for slugged URLs and query parameters?
- What should count as the same template across locales, market prefixes, A/B parameters, or pagination?
- Should CI regression thresholds default to p75 template metrics, page averages, worst-page metrics, or a combination?
- How should uncertain CLS culprit mapping be represented: numeric confidence only, or confidence plus reason text?
- How should script CPU time be attributed when trace events lack script URLs?
- Should combined HAR be optional-only due to size, with per-page HAR as the default export mode?
- How much raw trace data should the run artifact retain versus summarize?
- Should the diff engine compare only like-for-like pages discovered in both runs, or optionally include discovery drift as a first-class signal?

## 13. Final Recommendation

ChromeLens should keep its current architecture and evolve it by inserting a stable artifact layer between analysis and reporting. That is the highest-leverage move because route clustering, diffing, CI gating, third-party comparative analysis, and paired-mode validation all depend on durable, versioned outputs more than on new browser automation primitives.

The minimum viable version of each requested feature should be:

- Route clustering: deterministic URL-based template signatures with config overrides and template summary tables.
- Diffing: artifact-to-artifact comparison for page, template, and third-party metrics with JSON and HTML output.
- Third-party analysis: ownership-aware domain aggregation plus approximate CPU attribution with confidence labels.
- CLS debugging: top layout shift events with best-effort culprit metadata and report presentation, with overlays optional.
- Headless/headed reality check: paired runs with page/template deltas and optional screenshot pairs.
- HAR export: per-page HAR first, combined HAR optional.
- Docker/CI: official image plus documented GitHub Actions and Jenkins usage.

The strongest foundation is:

1. Define and ship the run artifact schema.
2. Build route clustering on top of that schema.
3. Build diffing once stable identifiers exist.

Once those three pieces land, the rest of the release becomes easier to implement, easier to test, and much more valuable in CI/CD workflows.
