import pytest
from unittest.mock import patch
import requests  # Import requests
from es_knowledge_base_mcp.clients.web import extract_urls_from_webpage


@pytest.mark.asyncio
async def test_extract_urls_from_webpage():
    """Tests the extract_urls_from_webpage tool."""

    with patch("requests.get") as mock_get:
        mock_response = patch("requests.Response").start()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None  # Simulate success
        mock_response.content = """
        <html>
        <body>
            <a href="http://example.com/page1">Link 1</a>
            <a href="/page2">Link 2</a>
            <a href="https://anothersite.com/page3">Link 3</a>
        </body>
        </html>
        """.encode("utf-8")

        mock_get.return_value = mock_response

        domain_filter = "http://example.com"
        path_filter = "/"
        # Update assertion to check the new dictionary structure
        result = await extract_urls_from_webpage(url="http://example.com", domain_filter=domain_filter, path_filter=path_filter)

        assert result["page_is_noindex"] is False
        assert result["page_is_nofollow"] is False
        assert sorted(result["urls_to_crawl"]) == sorted(["http://example.com/page1", "http://example.com/page2"])
        assert result["skipped_urls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "html_content, expected_urls_to_crawl, expected_skipped_urls, expected_noindex, expected_nofollow",  # Add expected values for new return
    [
        (
            """
            <html>
            <body>
                <a href="http://example.com/page1">Link 1</a>
                <a href="/page2">Link 2</a>
                <a href="https://anothersite.com/page3">Link 3</a>
            </body>
            </html>
            """,
            sorted(["http://example.com/page1", "http://example.com/page2"]),
            [],
            False,
            False,
        ),
        (
            """
            <html>
            <body>
                <a href="http://example.com/page1#section1">Link 1</a>
                <a href="/page2?id=5">Link 2</a>
                <a href="http://example.com/page1">Link 3</a>
            </body>
            </html>
            """,
            sorted(list(set(["http://example.com/page1", "http://example.com/page2"]))),
            [],
            False,
            False,
        ),
        (
            """
            <html>
            <body>
                <a href="/page1">Link 1</a>
                <a href="/page1">Link 2</a>
                <a href="/page1#section1">Link 3</a>
                <a href="/page1?id=5">Link 4</a>
            </body>
            </html>
            """,
            sorted(list(set(["http://example.com/page1"]))),
            [],
            False,
            False,
        ),
        (
            """
            <html>
            <body>
            </body>
            </html>
            """,
            [],
            [],
            False,
            False,
        ),
        # New test cases for meta robots and nofollow links
        (
            """
            <html>
            <head>
                <meta name="robots" content="noindex, nofollow">
            </head>
            <body>
                <a href="/page1">Link 1</a>
                <a href="/page2" rel="nofollow">Link 2</a>
            </body>
            </html>
            """,
            sorted(["http://example.com/page1"]),
            sorted(["http://example.com/page2"]),
            True,
            True,
        ),
        (
            """
            <html>
            <head>
                <meta name="robots" content="noindex">
            </head>
            <body>
                <a href="/page1">Link 1</a>
                <a href="/page2" rel="nofollow">Link 2</a>
            </body>
            </html>
            """,
            sorted(["http://example.com/page1"]),
            sorted(["http://example.com/page2"]),
            True,
            False,
        ),
        (
            """
            <html>
            <head>
                <meta name="robots" content="nofollow">
            </head>
            <body>
                <a href="/page1">Link 1</a>
                <a href="/page2" rel="nofollow">Link 2</a>
            </body>
            </html>
            """,
            sorted(["http://example.com/page1"]),
            sorted(["http://example.com/page2"]),
            False,
            True,
        ),
        (
            """
            <html>
            <head>
                <meta name="robots" content="index, follow">
            </head>
            <body>
                <a href="/page1">Link 1</a>
                <a href="/page2" rel="nofollow">Link 2</a>
            </body>
            </html>
            """,
            sorted(["http://example.com/page1"]),
            sorted(["http://example.com/page2"]),
            False,
            False,
        ),
        (
            """
            <html>
            <body>
                <a href="/page1">Link 1</a>
                <a href="/page2" rel="nofollow">Link 2</a>
                <a href="/page3" rel="NOFOLLOW">Link 3</a> # Test case insensitivity
            </body>
            </html>
            """,
            sorted(["http://example.com/page1"]),
            sorted(["http://example.com/page2", "http://example.com/page3"]),
            False,
            False,
        ),
    ],
    ids=[
        "Basic HTML with multiple links",
        "HTML with duplicate and parameterized links",
        "HTML with only one link",
        "Empty HTML",
        "Meta robots noindex, nofollow and nofollow link",  # New ID
        "Meta robots noindex and nofollow link",  # New ID
        "Meta robots nofollow and nofollow link",  # New ID
        "Meta robots index, follow and nofollow link",  # New ID
        "Nofollow links with case insensitivity",  # New ID
    ],
)
async def test_extract_urls_from_webpage_parametrized(
    html_content, expected_urls_to_crawl, expected_skipped_urls, expected_noindex, expected_nofollow
):  # Update parameters
    """Tests the extract_urls_from_webpage tool with various inputs."""
    base_url = "http://example.com"
    with patch("requests.get") as mock_get:
        mock_response = patch("requests.Response").start()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None  # Simulate success
        mock_response.content = html_content.encode("utf-8")

        mock_get.return_value = mock_response

        domain_filter = base_url
        path_filter = "/"
        # Update assertion to check the new dictionary structure
        result = await extract_urls_from_webpage(url=base_url, domain_filter=domain_filter, path_filter=path_filter)

        assert result["page_is_noindex"] is expected_noindex
        assert result["page_is_nofollow"] is expected_nofollow
        assert sorted(result["urls_to_crawl"]) == sorted(expected_urls_to_crawl)
        assert sorted(result["skipped_urls"]) == sorted(expected_skipped_urls)


# Add a test case for HTTP errors
@pytest.mark.asyncio
async def test_extract_urls_from_webpage_http_error():
    """Tests extract_urls_from_webpage when an HTTP error occurs."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.exceptions.HTTPError("Mock HTTP Error")

        with pytest.raises(requests.exceptions.HTTPError):
            await extract_urls_from_webpage(url="http://example.com")
