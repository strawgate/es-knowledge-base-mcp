import pytest
from unittest.mock import MagicMock

# Assuming Crawler, CrawlerSettings, ParameterDerivationError are importable
# Adjust the import path based on your project structure
from esdocmanagermcp.components.crawl import (
    Crawler,
    CrawlerSettings,
    ParameterDerivationError,
)

# Use pytest mark for async functions
pytestmark = pytest.mark.asyncio


# Dummy settings for Crawler initialization in tests
@pytest.fixture
def crawler_settings():
    return CrawlerSettings(
        crawler_image="dummy_image:latest",
        crawler_output_settings={"host": "dummy_es"},
        es_index_prefix="test-prefix",
    )


# Fixture to create a Crawler instance for tests
@pytest.fixture
def crawler(crawler_settings):
    # Mock the docker client as it's not needed for this unit test
    mock_docker_client = MagicMock()
    return Crawler(docker_client=mock_docker_client, settings=crawler_settings)


# --- Test Cases for _derive_crawl_params_from_seed ---


@pytest.mark.parametrize(
    "seed_url, expected_params",
    [
        # Basic HTTPS
        (
            "https://www.elastic.co/guide/en/index.html",
            {
                "domain": "https://www.elastic.co",
                "filter_pattern": "/guide/en/",
                "output_index_suffix": "www_elastic_co.guide.en",
            },
        ),
        # Basic HTTP
        (
            "http://example.com/docs/main/",
            {
                "domain": "http://example.com",
                "filter_pattern": "/docs/main/",
                "output_index_suffix": "example_com.docs.main",
            },
        ),
        # Root path with trailing slash
        (
            "https://docs.python.org/",
            {
                "domain": "https://docs.python.org",
                "filter_pattern": "/",
                "output_index_suffix": "docs_python_org",  # Path '/' results in empty sanitized path, suffix is just domain
            },
        ),
        # Root path without trailing slash
        (
            "https://docs.python.org",
            {
                "domain": "https://docs.python.org",
                "filter_pattern": "/",  # Should normalize to '/'
                "output_index_suffix": "docs_python_org",
            },
        ),
        # Deeper path without trailing slash
        (
            "https://developer.mozilla.org/en-US/docs/Web/API/",
            {
                "domain": "https://developer.mozilla.org",
                "filter_pattern": "/en-US/docs/Web/API/",
                "output_index_suffix": "developer_mozilla_org.en_us.docs.web.api",  # Note: case normalized
            },
        ),
        # Path with hyphens and numbers
        (
            "https://www.rfc-editor.org/rfc/rfc9110.html",
            {
                "domain": "https://www.rfc-editor.org",
                "filter_pattern": "/rfc/",
                "output_index_suffix": "www_rfc_editor_org.rfc",
            },
        ),
        # Domain with port
        (
            "http://localhost:8080/my/app/",
            {
                "domain": "http://localhost:8080",
                "filter_pattern": "/my/app/",
                "output_index_suffix": "localhost_8080.my.app",
            },
        ),
        # Path with only special chars (results in just domain suffix)
        (
            "https://test.com/!@#$%^/",
            {
                "domain": "https://test.com",
                "filter_pattern": "/",
                "output_index_suffix": "test_com",  # Path sanitizes to empty
            },
        ),
        # Previous failure case with valid domain
        (
            "https://www.elastic.co/guide/en/elasticsearch/client/ruby-api/current/index.html",
            {
                "domain": "https://www.elastic.co",
                "filter_pattern": "/guide/en/elasticsearch/client/ruby-api/current/",
                "output_index_suffix": "www_elastic_co.guide.en.elasticsearch.client.ruby_api.current",
            },
        ),
    ],
)
async def test_derive_crawl_params_success(crawler, seed_url, expected_params):
    """Tests successful derivation of parameters for various valid URLs."""
    derived_params = await crawler.derive_crawl_params_from_seed(seed_url)
    assert derived_params == expected_params


@pytest.mark.parametrize(
    "invalid_seed_url, expected_error_msg_part",
    [
        ("", "Seed URL cannot be empty"),  # Empty URL
        ("invalid-url", "Invalid seed URL format"),  # Malformed URL
        ("https://", "Invalid seed URL format"),  # Missing netloc
        ("://example.com", "Invalid seed URL format"),  # Missing scheme
    ],
)
async def test_derive_crawl_params_failure(
    crawler, invalid_seed_url, expected_error_msg_part
):
    """Tests that ParameterDerivationError is raised for invalid URLs."""
    with pytest.raises(ParameterDerivationError) as excinfo:
        await crawler.derive_crawl_params_from_seed(invalid_seed_url)
    assert expected_error_msg_part in str(excinfo.value)