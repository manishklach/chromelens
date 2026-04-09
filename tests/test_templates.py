from pathlib import Path

from chromelens.analysis.templates import (
    RoutePatternRule,
    build_template_artifacts,
    load_route_pattern_rules,
    match_route_template,
)
from chromelens.artifacts.models import PageArtifact


def test_match_route_template_heuristic_id() -> None:
    match = match_route_template("https://example.com/products/123", strategy="auto")
    assert match.signature == "/products/:id"
    assert match.label == "Products Template"


def test_match_route_template_slug_numeric() -> None:
    match = match_route_template("https://example.com/products/sku-abc-12345", strategy="auto")
    assert match.signature == "/products/:slug"


def test_match_route_template_custom_rule() -> None:
    rules = [RoutePatternRule(pattern=r"^/blog/\d{4}/\d{2}/[^/]+$", replacement="/blog/:year/:month/:slug", label="Blog Article Template")]
    match = match_route_template("https://example.com/blog/2026/04/hello-world", strategy="rules", rules=rules)
    assert match.signature == "/blog/:year/:month/:slug"
    assert match.label == "Blog Article Template"


def test_load_route_pattern_rules_json(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text('[{"pattern":"^/products/[^/]+$","replacement":"/products/:id","label":"Product Template"}]', encoding="utf-8")
    rules = load_route_pattern_rules(str(rules_path))
    assert len(rules) == 1
    assert rules[0].replacement == "/products/:id"


def test_build_template_artifacts_groups_pages() -> None:
    pages = [
        PageArtifact(page_id="1", url="https://example.com/products/123", normalized_url=""),
        PageArtifact(page_id="2", url="https://example.com/products/456", normalized_url=""),
        PageArtifact(page_id="3", url="https://example.com/blog/2026/04/post", normalized_url=""),
    ]
    updated_pages, templates = build_template_artifacts(pages, strategy="auto")
    assert len(updated_pages) == 3
    assert len(templates) == 2
    product_template = next(template for template in templates if template.signature == "/products/:id")
    assert product_template.page_count == 2
