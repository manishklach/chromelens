# ChromeLens v0.3.0

ChromeLens v0.3.0 turns the project from a single-run page profiler into a much stronger artifact-driven analysis tool for repeatable engineering workflows.

This release adds stable JSON run artifacts, route template clustering, artifact-to-artifact diffing, richer third-party cost analysis, best-effort CLS culprit extraction, headless-vs-headed paired comparisons, HAR export, Docker packaging, and expanded tests/docs.

## Highlights

### Stable JSON run artifacts

ChromeLens now writes a stable `run.json` artifact during `crawl`.

The artifact includes:

- crawl metadata and environment details
- per-page vitals, trace summaries, and issues
- template aggregates
- third-party cost summaries
- best-effort CLS shift summaries
- references to screenshots and HAR files when generated

This is the foundation for CI comparisons and downstream automation.

### Route template clustering

ChromeLens can now group families of routes such as:

- `/products/123`
- `/products/456`
- `/products/sku-abc-12345`

into reusable template signatures such as `/products/:id` or `/products/:slug`.

What shipped:

- offline deterministic clustering by default
- custom route rules from JSON or YAML
- template-level aggregation in the run artifact
- template view in the HTML dashboard

Example:

```bash
chromelens crawl https://example.com \
  --template-clustering auto \
  --route-patterns docs/examples-route-patterns.yaml
```

### Artifact diffing and CI gating

ChromeLens can now diff two previous run artifacts without re-crawling.

What shipped:

- `chromelens diff baseline.json candidate.json`
- JSON diff artifact
- HTML diff report
- CLI regression summary
- threshold-based CI exit behavior

Supported threshold flags include:

- `--max-tbt-regression-pct`
- `--max-new-long-tasks`
- `--max-cls-regression`
- `--max-script-duration-regression-pct`
- `--fail-on-regression`

Zero-baseline regressions are handled explicitly and no longer disappear behind `0%` fallback behavior.

### Estimated third-party cost analysis

The dashboard now includes an estimated third-party cost wall of shame.

What shipped:

- per-page and site-wide third-party cost rows
- estimated blocking time contribution
- estimated script execution contribution
- long-task association counts
- confidence labels and attribution method tracking

Important:

- third-party CPU and blocking attribution is estimated from captured evidence
- the report now states that approximation more clearly

### Best-effort CLS culprit extraction

ChromeLens now records best-effort layout shift culprit candidates when the browser exposes source metadata.

What shipped:

- layout shift event capture from browser performance entries
- culprit candidates with selector, tag/class metadata, and rects when available
- per-page CLS candidate display in the HTML report
- improved artifact semantics separating `node_id` and DOM `element_id`

Important:

- CLS culprit extraction remains best-effort
- the release copy has been tightened to avoid implying exact attribution

### Headless vs headed reality check

ChromeLens can now run the same route set in both modes and compare the outputs.

What shipped:

- `chromelens compare-modes https://example.com`
- headless and headed run artifacts
- mode diff artifact and HTML report
- optional thresholds for large divergence

Important:

- this mode is environment-sensitive and should be treated as a reality check, not a universal truth

### HAR export

ChromeLens can now export HAR files from captured network activity.

What shipped:

- `--export-har off|per-page|combined|both`
- per-page HAR files
- combined HAR output
- HAR file references in the run artifact

Important:

- HAR output reflects ChromeLens' captured network view
- it is intended for interoperability and inspection rather than full trace-level fidelity

### Docker and CI packaging

This release adds first-party packaging for CI workflows.

What shipped:

- production-oriented Dockerfile
- `.dockerignore`
- GitHub Actions smoke workflow example
- README instructions for Docker usage

## Hardening in this release

The merge-readiness pass for v0.3.0 also tightened several correctness edges:

- fixed year/month route normalization ordering
- narrowed slug normalization to reduce false-positive clustering
- added schema-version validation for run artifact loading
- clarified diff wording so it no longer overstates precision
- normalized third-party attribution notes at site level
- improved CLS confidence/reason semantics

## Backward compatibility

- existing `chromelens crawl URL` usage still works
- HTML reporting remains the default output
- new artifact fields are additive
- schema version remains `1.0` in this release

## Upgrade notes

- install/update dependencies after pulling v0.3.0
- `PyYAML` is now required for JSON/YAML route-pattern support
- Playwright Chromium installation is still required outside Docker

## Validation

Validated in this release:

- full Python test suite passing
- CLI help verified for `crawl`, `diff`, and `compare-modes`

## Known limitations

- third-party blocking and CPU attribution is still heuristic
- CLS culprit extraction depends on browser-provided source metadata
- diff artifacts are CI-friendly but not a statistical anti-flake system
- headed vs headless comparisons remain environment-sensitive

## Full command examples

```bash
chromelens crawl https://example.com \
  --output reports/example \
  --artifact-path reports/example/run.json \
  --template-clustering auto \
  --export-har per-page
```

```bash
chromelens diff reports/main/run.json reports/pr/run.json \
  --output reports/pr-diff \
  --fail-on-regression \
  --max-tbt-regression-pct 15 \
  --max-cls-regression 0.03 \
  --max-script-duration-regression-pct 10
```

```bash
chromelens compare-modes https://example.com \
  --output reports/reality-check \
  --reality-threshold-tbt-ms 100 \
  --reality-threshold-cls 0.03
```
