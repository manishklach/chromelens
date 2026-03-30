"""Site crawler — discovers all pages on a target website."""

from __future__ import annotations

import logging
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import DiscoveredPage

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_DEPTH = 3
DEFAULT_TIMEOUT = 10

SKIP_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".zip", ".tar", ".gz", ".mp4", ".mp3", ".woff", ".woff2",
    ".ttf", ".eot", ".ico", ".css", ".js", ".xml", ".json",
})


class SiteCrawler:
    """Discover all pages on a website via sitemap and recursive link extraction."""

    def __init__(
        self,
        base_url: str,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.exclude_patterns = exclude_patterns or []

        parsed = urlparse(self.base_url)
        self.scheme = parsed.scheme
        self.netloc = parsed.netloc
        self.origin = f"{parsed.scheme}://{parsed.netloc}"

        self._visited: set[str] = set()
        self._pages: list[DiscoveredPage] = []
        self._robot_parser: urllib.robotparser.RobotFileParser | None = None

    def crawl(self) -> list[DiscoveredPage]:
        """Run the full crawl: sitemap first, then recursive link extraction."""
        self._load_robots_txt()

        sitemap_pages = self._try_sitemap()
        if sitemap_pages:
            LOGGER.info("Found %d pages from sitemap.xml", len(sitemap_pages))
            for page in sitemap_pages:
                if len(self._pages) >= self.max_pages:
                    break
                if page.url not in self._visited:
                    self._visited.add(page.url)
                    self._pages.append(page)

        seed = DiscoveredPage(url=self.base_url, depth=0, source="seed")
        if self.base_url not in self._visited:
            self._visited.add(self.base_url)
            self._pages.append(seed)

        queue: list[DiscoveredPage] = list(self._pages)
        while queue and len(self._pages) < self.max_pages:
            current = queue.pop(0)
            if current.depth >= self.max_depth:
                continue
            child_urls = self._extract_links(current.url)
            for child_url in child_urls:
                if len(self._pages) >= self.max_pages:
                    break
                if child_url in self._visited:
                    continue
                if not self._is_allowed(child_url):
                    continue
                self._visited.add(child_url)
                child = DiscoveredPage(
                    url=child_url,
                    depth=current.depth + 1,
                    source="link",
                    parent_url=current.url,
                )
                self._pages.append(child)
                queue.append(child)

        LOGGER.info("Crawl complete: discovered %d pages", len(self._pages))
        return self._pages

    def _load_robots_txt(self) -> None:
        """Load and parse robots.txt for the target site."""
        robots_url = f"{self.origin}/robots.txt"
        try:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            self._robot_parser = rp
            LOGGER.debug("Loaded robots.txt from %s", robots_url)
        except Exception:
            LOGGER.debug("No robots.txt found at %s", robots_url)
            self._robot_parser = None

    def _is_allowed(self, url: str) -> bool:
        """Check if a URL is allowed by robots.txt and exclude patterns."""
        if self._robot_parser:
            try:
                if not self._robot_parser.can_fetch("*", url):
                    return False
            except Exception:
                pass

        for pattern in self.exclude_patterns:
            if pattern in url:
                return False

        return True

    def _try_sitemap(self) -> list[DiscoveredPage]:
        """Attempt to discover pages via sitemap.xml."""
        sitemap_url = f"{self.origin}/sitemap.xml"
        try:
            resp = requests.get(sitemap_url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.content, "xml")
            locs = soup.find_all("loc")
            pages = []
            for loc in locs:
                url = loc.get_text(strip=True)
                if self._is_same_origin(url) and self._is_html_url(url):
                    pages.append(DiscoveredPage(url=url, depth=0, source="sitemap"))
            return pages
        except Exception:
            LOGGER.debug("Could not fetch sitemap.xml")
            return []

    def _extract_links(self, page_url: str) -> list[str]:
        """Extract same-origin links from a page using requests + BeautifulSoup."""
        try:
            resp = requests.get(page_url, timeout=DEFAULT_TIMEOUT, headers={
                "User-Agent": "ChromeLens/0.1 (performance-audit)"
            })
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            links: list[str] = []
            for anchor in soup.find_all("a", href=True):
                href = anchor["href"]
                if isinstance(href, list):
                    href = href[0]
                absolute = urljoin(page_url, href)
                cleaned = absolute.split("#")[0].split("?")[0].rstrip("/")
                if cleaned and self._is_same_origin(cleaned) and self._is_html_url(cleaned):
                    links.append(cleaned)
            return list(dict.fromkeys(links))  # deduplicate preserving order
        except Exception as exc:
            LOGGER.debug("Failed to extract links from %s: %s", page_url, exc)
            return []

    def _is_same_origin(self, url: str) -> bool:
        """Check if a URL shares the same origin as the target site."""
        parsed = urlparse(url)
        return parsed.netloc == self.netloc

    def _is_html_url(self, url: str) -> bool:
        """Heuristically check if a URL likely points to an HTML page."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return False
        return True
