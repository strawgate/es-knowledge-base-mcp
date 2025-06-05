"""Utility functions for web-related operations."""

from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from fastmcp.utilities.logging import get_logger

logger = get_logger("knowledge-base-mcp.utils")


async def extract_urls_from_webpage(url: str, domain_filter: str | None = None, path_filter: str | None = None) -> dict[str, Any]:
    """Extracts all unique URLs from a given webpage, stripping fragments and query parameters. Optionally,
    filters URLs based on a specific domain and path. Also extracts meta robots directives.

    Args:
        url: The URL of the webpage to extract URLs from.
        domain_filter: Optional filter to restrict URLs to a specific domain.
        path_filter: Optional filter to restrict URLs to a specific path.

    Returns:
        A dictionary containing page directives and categorized URLs:
        {
            "page_is_noindex": bool,
            "page_is_nofollow": bool, # From meta tag
            "urls_to_crawl": List[str], # Unique, sorted list
            "skipped_urls": List[str]  # Unique, sorted list
        }

    Example:
        >>> result = await extract_urls_from_webpage("http://example.com")
        >>> result["urls_to_crawl"]
        ["http://example.com/page1", "http://example.com/page2"]

    """
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    # Extract Meta Robots Directives
    page_is_noindex = False
    page_is_nofollow = False
    meta_robots = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "robots"})  # type: ignore
    if meta_robots and meta_robots.get("content"):  # type: ignore
        content = meta_robots.get("content", "").lower()  # type: ignore
        if "noindex" in content:
            page_is_noindex = True
        if "nofollow" in content:
            page_is_nofollow = True

    # Modify Link Extraction & Categorization
    urls_to_crawl = set()
    skipped_urls = set()

    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag) or not a.get("href"):
            continue

        href = a["href"]
        is_nofollow_link = False
        rel_attr = a.get("rel", [])  # type: ignore
        if isinstance(rel_attr, str):
            rel_attr = rel_attr.split()
        if "nofollow" in [rel.lower() for rel in rel_attr]:  # type: ignore
            is_nofollow_link = True

        # Existing logic to build absolute URL (urljoin)
        absolute_url = urljoin(url, str(href))

        # Existing logic to parse and clean URL (urlparse, urlunparse)
        parsed_url = urlparse(absolute_url)
        cleaned_url = urlunparse(parsed_url._replace(fragment="", query=""))
        parsed_domain = parsed_url.scheme + "://" + parsed_url.netloc

        # Existing filter logic (domain_filter, path_filter)
        if path_filter and not parsed_url.path.startswith(path_filter):
            continue
        if domain_filter and parsed_domain != domain_filter:
            continue

        # Add to appropriate set based on nofollow status
        if is_nofollow_link:
            skipped_urls.add(cleaned_url)
        else:
            urls_to_crawl.add(cleaned_url)

    # Update Return Statement
    return {
        "page_is_noindex": page_is_noindex,
        "page_is_nofollow": page_is_nofollow,
        "urls_to_crawl": sorted(urls_to_crawl),
        "skipped_urls": sorted(skipped_urls),
    }
