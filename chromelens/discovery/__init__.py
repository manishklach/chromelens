"""Discovery engine models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DiscoveredPage:
    """A page discovered during site crawling."""

    url: str
    depth: int
    source: str  # "sitemap", "link", or "seed"
    parent_url: str | None = None
