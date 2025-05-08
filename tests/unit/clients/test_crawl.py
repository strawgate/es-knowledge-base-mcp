from unittest.mock import AsyncMock, patch

import pytest
from requests import HTTPError

from es_knowledge_base_mcp.clients.crawl import Crawler
from es_knowledge_base_mcp.clients.docker import InjectFile
from es_knowledge_base_mcp.errors.crawler import (
    CrawlerValidationHTTPError,
    CrawlerValidationNoIndexNofollowError,
    CrawlerValidationTooManyURLsError,
)  # Import new error


@pytest.mark.parametrize(
    "url, expected_params",
    [
        (
            "http://example.com/docs/file.html",
            {
                "seed_url": "http://example.com/docs/file.html",
                "domain": "http://example.com",
                "filter_pattern": "/docs/",
            },
        ),
        (
            "https://anothersite.com/guide/",
            {
                "seed_url": "https://anothersite.com/guide/",
                "domain": "https://anothersite.com",
                "filter_pattern": "/guide/",
            },
        ),
        (
            "http://example.com",
            {
                "seed_url": "http://example.com",
                "domain": "http://example.com",
                "filter_pattern": "",
            },
        ),
        (
            "http://example.com/file.txt",
            {
                "seed_url": "http://example.com/file.txt",
                "domain": "http://example.com",
                "filter_pattern": "/",
            },
        ),
    ],
    ids=[
        "URL with file extension",
        "URL with trailing slash",
        "Root URL",
        "Root URL with file extension",
    ],
)
def test_derive_crawl_params(url, expected_params):
    """Tests the derive_crawl_params static method."""
    params = Crawler.derive_crawl_params(url)
    assert params == expected_params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mock_extract_return, expected_exception, limit_override",  # Update parameter name
    [
        # Original test cases, updated for new return structure
        ({"page_is_noindex": False, "page_is_nofollow": False, "urls_to_crawl": ["url1", "url2"], "skipped_urls": []}, None, None),
        ({"side_effect": HTTPError("Test HTTP Error")}, CrawlerValidationHTTPError, None),
        (
            {"page_is_noindex": False, "page_is_nofollow": False, "urls_to_crawl": [f"url{i}" for i in range(6)], "skipped_urls": []},
            CrawlerValidationTooManyURLsError,
            5,
        ),
        # New test case: noindex and nofollow
        (
            {"page_is_noindex": True, "page_is_nofollow": True, "urls_to_crawl": ["url1"], "skipped_urls": ["url2"]},
            CrawlerValidationNoIndexNofollowError,
            None,
        ),
        # Test case: too many URLs, ensuring skipped_urls are ignored for the count
        (
            {
                "page_is_noindex": False,
                "page_is_nofollow": False,
                "urls_to_crawl": [f"url{i}" for i in range(6)],
                "skipped_urls": ["skipped1", "skipped2"],
            },
            CrawlerValidationTooManyURLsError,
            5,
        ),
    ],
    ids=[
        "success",
        "http_error",
        "too_many_urls_to_crawl",  # Update ID
        "noindex_and_nofollow",  # New ID
        "too_many_urls_excluding_skipped",  # New ID
    ],
)
@patch("es_knowledge_base_mcp.clients.crawl.extract_urls_from_webpage", new_callable=AsyncMock)
async def test_validate_crawl(mock_extract_urls, mock_extract_return, expected_exception, limit_override):  # Update parameter name
    """Tests validate_crawl scenarios using parametrization."""
    test_url = "http://example.com"  # Inlined value
    max_limit = 10  # Inlined value

    # Configure the mock based on the provided return value or side effect
    if "side_effect" in mock_extract_return:
        mock_extract_urls.side_effect = mock_extract_return["side_effect"]
    else:
        mock_extract_urls.return_value = mock_extract_return

    current_limit = limit_override if limit_override is not None else max_limit

    expected_derived_params = Crawler.derive_crawl_params(test_url)

    if expected_exception:
        with pytest.raises(expected_exception):
            await Crawler.validate_crawl(test_url, current_limit)
    else:
        params = await Crawler.validate_crawl(test_url, current_limit)
        assert params == expected_derived_params

    mock_extract_urls.assert_called_once_with(
        url=test_url,
        domain_filter=expected_derived_params["domain"],
        path_filter=expected_derived_params["filter_pattern"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "domain, seed_url, filter_pattern, index_name, es_settings",
    [
        ("http://example.com", "http://example.com/start", "/start.*", "test_index", {"host": "localhost", "port": 9200}),
        ("http://example.com", "http://example.com/start", "", "test_index", {"host": "localhost", "port": 9200}),
        ("http://example.com", "http://example.com/start", "/start.*", "test_index", {}),
        (
            "https://sub.example.org",
            "https://sub.example.org/docs/page1",
            "/docs/.*",
            "docs_index",
            {"host": "es-host", "port": 9201, "user": "elastic"},
        ),
        ("http://minimal.com", "http://minimal.com/", "/", "minimal_idx", {"host": "127.0.0.1"}),
        ("https://secure.com", "https://secure.com/app", "/app.*", "secure_idx", {"host": "secure-es", "port": 9200, "use_ssl": True}),
    ],
    ids=[
        "basic",
        "empty_filter",
        "empty_es_settings",
        "different_values",
        "minimal_es",
        "https_ssl",
    ],
)
async def test__prepare_crawl_config_file(
    snapshot,
    domain: str,
    seed_url: str,
    filter_pattern: str,
    index_name: str,
    es_settings: dict,
):
    """Tests _prepare_crawl_config_file using parametrization and snapshot testing."""
    inject_file = await Crawler._prepare_crawl_config_file(domain, seed_url, filter_pattern, index_name, es_settings)

    assert isinstance(inject_file, InjectFile)
    assert inject_file == snapshot
