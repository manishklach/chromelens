# ChromeLens Roadmap

This roadmap turns ChromeLens from a strong crawler-and-dashboard tool into a repeatable performance engineering platform for real CI/CD use.

It is intentionally practical. The focus is not on adding flashy features as fast as possible, but on making the core system more trustworthy, more configurable, and more useful on real sites with messy route structures, flaky environments, and large third-party footprints.

## Current foundation

ChromeLens now has a solid base in `main`:

- stable `run.json` and `diff.json` artifacts
- route template clustering with heuristic and rule-based modes
- artifact-driven diffing for CI workflows
- best-effort third-party cost analysis with confidence labeling
- best-effort CLS culprit extraction
- headed vs headed comparison mode
- HAR export support
- Docker packaging and CI smoke coverage

That base is strong enough to support a more deliberate roadmap.

## Guiding principles

### 1. Stable artifacts first

Artifacts are the contract. HTML dashboards are important, but machine-readable outputs are what make ChromeLens usable in CI, regression workflows, and future integrations.

### 2. Honest attribution over false precision

Third-party CPU attribution and CLS culprit extraction are useful even when approximate, but ChromeLens should always disclose confidence and method rather than pretending to have perfect source attribution.

### 3. Template-aware analysis over raw URL noise

Large crawls become useful only when similar routes are clustered safely. Template controls and explainability matter as much as the clustering itself.

### 4. CI usefulness beats novelty

When tradeoffs appear, ChromeLens should prefer deterministic behavior, stable exit codes, readable diffs, and reproducible artifacts over experimental complexity.

### 5. Real-site validation matters

Every major feature should be tested not only with fixtures, but also against a small set of real-world sites with different shapes such as e-commerce, docs/blog, SPA-heavy apps, and content sites.

## Phase 1: Post-merge stabilization

### Goals

- validate the newly merged artifact, clustering, diffing, and reporting stack on real sites
- tighten rough edges before expanding scope
- improve trust in the current output

### Priority work

- run ChromeLens against 3-5 different real sites and document findings
- tune template clustering based on real route patterns and false-positive cases
- review dashboard and CLI wording for places where precision is overstated
- tighten artifact/schema compatibility expectations
- improve fixture coverage for real-world edge cases discovered during validation

### Exit criteria

- template clustering behaves reasonably on multiple site archetypes
- diff output is understandable and useful on controlled before/after runs
- third-party and CLS sections feel trustworthy in real reports
- no urgent correctness fixes remain from post-merge validation

## Phase 2: Template controls and explainability

### Goals

Make route clustering safer, more configurable, and easier to debug.

### Priority work

- richer route pattern config with comments/examples for common site types
- route clustering debug view showing:
  - raw URL
  - normalized URL
  - chosen template signature
  - confidence
  - why the match happened
- support for query-parameter handling policies
- optional exclusions for routes that should never be clustered
- stronger labels for template families such as product, article, search, category, account, checkout

### Why this matters

As users adopt ChromeLens on larger sites, template clustering will become one of the main trust levers. Safe controls and explainability will matter more than additional heuristics alone.

## Phase 3: Better CI regression workflows

### Goals

Turn diffing into a cleaner, more actionable CI gatekeeper.

### Priority work

- improved threshold policies with grouped pass/fail summaries
- clearer CLI and HTML diff narratives for regressions vs crawl-shape changes
- stronger handling of added/removed routes and template count changes
- optional PR-oriented summary output format
- baseline/candidate comparison presets for common workflows
- improved exit-code semantics and documentation for CI systems

### Stretch ideas

- markdown summary output for GitHub PR comments
- top-regression ranking for templates and pages
- trend-oriented summaries across multiple saved runs

## Phase 4: Stronger third-party attribution

### Goals

Increase confidence and usefulness of third-party cost analysis without overclaiming precision.

### Priority work

- stronger script URL attribution from trace data where available
- better separation of first-party CDN vs truly external third-party origins
- ownership override/allowlist config for business-controlled domains
- improved wall-of-shame ranking views by:
  - blocking time
  - script execution time
  - request count
  - transfer size
- per-template third-party offender breakdowns

### Stretch ideas

- attribution confidence rollups
- method-specific visuals showing whether results came from script-byte share or total-byte share
- optional domain grouping for vendor families

## Phase 5: CLS and visual debugging improvements

### Goals

Make layout-shift analysis much more actionable.

### Priority work

- better screenshot annotation for top shift culprits
- richer culprit metadata presentation in reports
- stronger fallback behavior when selector data is incomplete
- clearer grouping of high-impact shifts vs noisy minor shifts
- report language that explains exactly how much of the culprit mapping is inferred

### Stretch ideas

- simple overlay thumbnails for before/after bounding boxes
- template-level CLS culprit rollups
- shift categories such as image late-load, font swap, ad slot expansion, hydration movement

## Phase 6: Artifact ecosystem and interoperability

### Goals

Make ChromeLens easier to integrate with other tooling.

### Priority work

- schema evolution policy for `run.json` and `diff.json`
- artifact changelog/versioning notes in docs
- raw trace export options where practical
- more explicit HAR mapping/index behavior
- optional machine-readable summaries for dashboards and PR systems

### Stretch ideas

- artifact ingestion utility for downstream analysis scripts
- conversion helpers for common external tools
- optional compressed artifact bundles for large crawls

## Phase 7: Fleet-scale and observability polish

### Goals

Improve operational quality for larger crawls and recurring usage.

### Priority work

- performance tuning for larger crawls and report generation
- more detailed logging and diagnostics for failed pages
- better crawl-shape summaries for large route sets
- improved Docker documentation and runtime guidance
- expanded CI smoke and integration coverage

### Stretch ideas

- richer progress telemetry during long crawls
- resource usage summaries for crawl runs
- optional parallelization controls for more predictable fleet-wide behavior

## Phase 8: Research / advanced workflows

These are promising but should come only after the core gets harder and more trusted.

### Candidate areas

- statistical anti-flake diffing and repeated-run comparison models
- longitudinal trend analysis across many stored runs
- stronger mode-comparison analytics for GPU/compositor-sensitive routes
- AI-assisted clustering suggestions layered on top of the current rule/heuristic system
- AI-assisted issue summarization built from stable artifacts, not from raw trace guesswork

## Release framing

A practical way to think about the next evolution:

- **v0.2.x** — stabilize the newly merged artifact/template/diff foundation
- **v0.3.x** — improve clustering controls and CI workflow quality
- **v0.4.x** — deepen attribution and visual debugging
- **v0.5.x** — expand artifact interoperability and fleet-scale polish

## What should happen next

The next best step is a short stabilization sprint, not another large feature drop.

Recommended immediate sequence:

1. validate ChromeLens on several very different real sites
2. tune template clustering and report wording from those results
3. strengthen CI regression outputs and baseline handling where needed
4. then move into deeper third-party attribution and CLS visualization

That ordering keeps the foundation trustworthy while still moving the product forward.
