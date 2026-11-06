"""Find and download a website's public PDFs, politely.

robots.txt is obeyed (pages and sitemaps), each request waits ``delay``
seconds after the previous one, counts and sizes are capped, and the
User-Agent says what this is. Only the site's own host (and its subdomains)
is visited. Downloads are named by number, never by URL, inside one folder.
"""
from __future__ import annotations

import gzip
import hashlib
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

from loguru import logger

USER_AGENT = "RAWRS-AccessibilityAudit/0.1 (automated check of public PDFs; obeys robots.txt)"


@dataclass(frozen=True)
class Limits:
    max_pages: int = 150          # HTML pages read to find PDF links
    max_pdfs: int = 40
    max_pdf_bytes: int = 40_000_000
    max_html_bytes: int = 3_000_000
    max_sitemaps: int = 10
    delay_seconds: float = 1.0
    timeout_seconds: float = 30.0
    crawl_depth: int = 2          # fallback crawl when there is no sitemap


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, site: str) -> bool:
    host = _host(url)
    return urlparse(url).scheme in ("http", "https") and (host == site or host.endswith("." + site))


# Folders where city CMSs serve files without a .pdf suffix (CivicPlus
# /DocumentCenter/View/123/Name, /files/...). A candidate only counts once
# its bytes start with %PDF (download()).
_DOCUMENT_PATH = re.compile(r"/(documentcenter|documents?|downloads?|files|uploads|media)(/|$)", re.I)


def is_pdf_link(url: str) -> bool:
    path = urlparse(url).path
    if path.lower().endswith(".pdf"):
        return True
    last = path.rsplit("/", 1)[-1]
    # ponytail: folder-name heuristic; ceiling: other CMS layouts are missed
    # (add their folder, or a HEAD content-type probe).
    return bool(_DOCUMENT_PATH.search(path)) and "." not in last


def document_key(url: str) -> Tuple[str, str, str]:
    """Same file whatever the scheme, www prefix or case of the host."""
    parts = urlparse(url)
    return _host(url), parts.path, parts.query


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            self.hrefs += [value for name, value in attrs if name == "href" and value]


def page_links(html: str, base_url: str) -> List[str]:
    parser = _Links()
    parser.feed(html)
    return [urldefrag(urljoin(base_url, href.strip()))[0] for href in parser.hrefs]


def sitemap_locs(data: bytes) -> Tuple[List[str], List[str]]:
    """(child sitemaps, page URLs) from a sitemap or sitemap index, gzip or not."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return [], []
    locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    return (locs, []) if root.tag.endswith("sitemapindex") else ([], locs)


@dataclass
class Fetcher:
    site: str
    limits: Limits
    robots: urllib.robotparser.RobotFileParser = field(default_factory=urllib.robotparser.RobotFileParser)
    _last: float = 0.0
    requests: int = 0

    def get(self, url: str, max_bytes: int) -> Optional[Tuple[str, str, bytes]]:
        """(final URL, content type, body), or None when refused, off-site, too big or failed."""
        if not same_site(url, self.site) or not self.robots.can_fetch(USER_AGENT, url):
            return None
        wait = self._last + self.limits.delay_seconds - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.limits.timeout_seconds) as response:
                final = response.geturl()
                if not same_site(final, self.site):
                    return None
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    logger.info("audit: skipped {} (over {} bytes)", url, max_bytes)
                    return None
                return final, response.headers.get_content_type(), body
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            logger.info("audit: could not fetch {}: {}", url, exc)
            return None


def resolve(start_url: str, limits: Limits) -> str:
    """Where the start URL really lives (old domains often redirect to a new one)."""
    request = urllib.request.Request(start_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=limits.timeout_seconds) as response:
            return response.geturl()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return start_url


def open_site(start_url: str, limits: Limits) -> Fetcher:
    fetcher = Fetcher(_host(start_url), limits)
    robots_url = urljoin(start_url, "/robots.txt")
    fetcher.robots.set_url(robots_url)
    request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=limits.timeout_seconds) as response:
            fetcher.robots.parse(response.read(500_000).decode("utf-8", "replace").splitlines())
    except urllib.error.HTTPError as exc:
        # As robotparser does: 401/403 means stay out, other errors mean no rules.
        fetcher.robots.parse(["User-agent: *", "Disallow: /"] if exc.code in (401, 403) else [])
    except (urllib.error.URLError, TimeoutError, OSError):
        fetcher.robots.parse([])
    return fetcher


def _from_sitemaps(fetcher: Fetcher, start_url: str) -> List[str]:
    # Relative "Sitemap: /sitemap.xml" lines are off-spec but common.
    queue = [urljoin(start_url, u) for u in fetcher.robots.site_maps() or ["/sitemap.xml"]]
    seen, pages = set(), []
    while queue and len(seen) < fetcher.limits.max_sitemaps:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        got = fetcher.get(url, fetcher.limits.max_html_bytes)
        if got:
            children, locs = sitemap_locs(got[2])
            queue += children
            pages += locs
    return pages


def discover(start_url: str, fetcher: Fetcher) -> Tuple[List[str], dict]:
    """PDF URLs on the site: from the sitemap, else a shallow crawl from ``start_url``."""
    limits = fetcher.limits
    listed = _from_sitemaps(fetcher, start_url)
    # Keyed by document_key so www/non-www and #fragments are one file; value = first URL seen.
    pdfs = {}
    for u in listed:
        if is_pdf_link(u) and same_site(u, fetcher.site):
            pdfs.setdefault(document_key(u), u)
    queue = [(u, limits.crawl_depth) for u in listed if not is_pdf_link(u)] or [(start_url, limits.crawl_depth)]
    seen, pages_read = set(), 0
    while queue and pages_read < limits.max_pages and len(pdfs) < limits.max_pdfs * 3:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        got = fetcher.get(url, limits.max_html_bytes)
        if not got or got[1] not in ("text/html", "application/xhtml+xml"):
            continue
        pages_read += 1
        for link in page_links(got[2].decode("utf-8", "replace"), got[0]):
            if not same_site(link, fetcher.site):
                continue
            if is_pdf_link(link):
                pdfs.setdefault(document_key(link), link)
            elif depth > 0 and not listed:
                queue.append((link, depth - 1))
    unique = list(pdfs.values())
    return unique, {"source": "sitemap" if listed else "crawl", "pages_read": pages_read,
                    "sitemap_urls": len(listed), "pdf_links_found": len(unique)}


def download(pdf_urls: List[str], fetcher: Fetcher, folder: Path) -> List[Tuple[str, Path]]:
    """Up to ``max_pdfs`` files that really are PDFs, saved as 0001.pdf, 0002.pdf, ..."""
    folder.mkdir(parents=True, exist_ok=True)
    saved: List[Tuple[str, Path]] = []
    seen = set()  # content hashes: two addresses can serve the same file
    for url in pdf_urls[: fetcher.limits.max_pdfs * 3]:  # candidates may turn out not to be PDFs
        if len(saved) >= fetcher.limits.max_pdfs:
            break
        got = fetcher.get(url, fetcher.limits.max_pdf_bytes)
        if not got or not got[2].startswith(b"%PDF") or hashlib.sha256(got[2]).digest() in seen:
            continue
        seen.add(hashlib.sha256(got[2]).digest())
        path = folder / f"{len(saved) + 1:04d}.pdf"
        path.write_bytes(got[2])
        saved.append((url, path))
    return saved
