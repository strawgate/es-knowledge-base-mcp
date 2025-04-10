
import pytest
from unittest.mock import MagicMock

from esdocmanagermcp.components.crawl import (
    Crawler,
    CrawlerSettings,
)

@pytest.fixture
def crawler_settings():
    return CrawlerSettings(
        crawler_image="dummy_image:latest",
        crawler_output_settings={"host": "dummy_es"},
        es_index_prefix="test-prefix",
    )


@pytest.fixture
def crawler(crawler_settings):
    mock_docker_client = MagicMock()
    return Crawler(docker_client=mock_docker_client, settings=crawler_settings)

@pytest.mark.parametrize(
    "domain, path, expected_suffix",
    [
        ("example.com", "/full-path/to/resource/index.html", "example_com.full_path.to.resource.index_html"),
        ("discuss.elastic.co", "/t/some-topic/123", "discuss_elastic_co.t.some_topic.123"),
        ("www.elastic-co.com", "/guide/en/", "www_elastic_co_com.guide.en"),
        ("test.com", "/", "test_com"), # Root path
        ("test.com", "", "test_com"), # Empty path
        ("localhost:8080", "/my/app/", "localhost_8080.my.app"),
        ("domain.com", "/path_with_underscores/", "domain_com.path_with_underscores"),
        ("domain.com", "/path/with/trailing/", "domain_com.path.with.trailing"),
        ("domain.com", "/path/with/file.ext", "domain_com.path.with.file_ext"),
        ("UPPER.COM", "/MixedCase/Path/", "upper_com.mixedcase.path"), # Case normalization
        ("domain.com", "/path with spaces/", "domain_com.path_with_spaces"), # Space handling (becomes underscore)
        ("domain.com", "/!@#$%^&*/", "domain_com"), # Special chars become underscore, strip handles ends
        ("domain.com", "//double//slash//", "domain_com.double.slash"), # Double slashes
        ("domain.com", "/leadingtrailing/", "domain_com.leadingtrailing"), # Ensure strip works
        ("domain.com", "/a.-_b/", "domain_com.a___b"), # Internal special chars
    ],
)
def test_derive_destination_index_name(crawler, domain, path, expected_suffix):
    """Tests the _derive_destination_index_name helper function."""
    derived_suffix = crawler._derive_destination_index_name(domain, path)
    assert derived_suffix == expected_suffix


@pytest.mark.parametrize(
    "seed_dir, expected_params",
    [
        # Example from docstring
        (
            "http://example.com/full-path/to/resource/",
            {
                "domain": "example.com",
                "filter_pattern": "http://example.com/full-path/to/resource/", # Uses the full seed_dir
                "output_index_suffix": "example_com.full_path.to.resource"
            }
        ),
        # HTTPS, root path
        (
            "https://docs.python.org/",
            {
                "domain": "docs.python.org",
                "filter_pattern": "https://docs.python.org/",
                "output_index_suffix": "docs_python_org"
            }
        ),
        # HTTP, deeper path
        (
            "http://example.com/docs/main/subsection/",
            {
                "domain": "example.com",
                "filter_pattern": "http://example.com/docs/main/subsection/",
                "output_index_suffix": "example_com.docs.main.subsection"
            }
        ),
        # Domain with port
        (
            "http://localhost:8080/my/app/",
            {
                "domain": "localhost:8080",
                "filter_pattern": "http://localhost:8080/my/app/",
                "output_index_suffix": "localhost_8080.my.app"
            }
        ),
        # Path with hyphens
         (
            "https://developer.mozilla.org/en-US/docs/Web/API/",
            {
                "domain": "developer.mozilla.org",
                "filter_pattern": "https://developer.mozilla.org/en-US/docs/Web/API/",
                "output_index_suffix": "developer_mozilla_org.en_us.docs.web.api"
            }
        ),
    ]
)
def test_derive_crawl_params_from_dir(crawler, seed_dir, expected_params):
    """Tests deriving parameters from directory-like seed URLs."""
    derived_params = crawler.derive_crawl_params_from_dir(seed_dir)
    assert derived_params == expected_params


@pytest.mark.parametrize(
    "seed_url, expected_params",
    [
        # Example from docstring
        (
            "http://example.com/full-path/to/resource/index.html",
            {
                "domain": "example.com",
                "filter_pattern": "/full-path/to/resource/", # Path up to last '/'
                "output_index_suffix": "example_com.full_path.to.resource.index_html" # Suffix uses full path
            }
        ),
        # Basic HTTPS file
        (
            "https://www.elastic.co/guide/en/index.html",
            {
                "domain": "www.elastic.co",
                "filter_pattern": "/guide/en/",
                "output_index_suffix": "www_elastic_co.guide.en.index_html"
            }
        ),
        # Deeper path file
        (
            "https://www.rfc-editor.org/rfc/rfc9110.html",
            {
                "domain": "www.rfc-editor.org",
                "filter_pattern": "/rfc/",
                "output_index_suffix": "www_rfc_editor_org.rfc.rfc9110_html"
            }
        ),
        # URL ending with slash (should behave like dir for filter_pattern, but use full path for suffix)
        (
            "https://developer.mozilla.org/en-US/docs/Web/API/",
            {
                "domain": "developer.mozilla.org",
                "filter_pattern": "/en-US/docs/Web/API/",
                "output_index_suffix": "developer_mozilla_org.en_us.docs.web.api"
            }
        ),
        # Root path URL (no file)
        (
            "https://docs.python.org/",
            {
                "domain": "docs.python.org",
                "filter_pattern": "/",
                "output_index_suffix": "docs_python_org"
            }
        ),
         # Root path URL (no file, no trailing slash) - urlparse adds '/'
        (
            "https://docs.python.org",
            {
                "domain": "docs.python.org",
                "filter_pattern": "/",
                "output_index_suffix": "docs_python_org"
            }
        ),
        # URL with query params (should be ignored)
        (
            "http://example.com/page?param=value&other=1",
             {
                "domain": "example.com",
                "filter_pattern": "/", # Path is just '/'
                "output_index_suffix": "example_com.page"
            }
        ),
        # URL with fragment (should be ignored)
        (
            "http://example.com/section#heading",
             {
                "domain": "example.com",
                "filter_pattern": "/", # Path is just '/'
                "output_index_suffix": "example_com.section"
            }
        ),
    ]
)
def test_derive_crawl_params_from_url(crawler, seed_url, expected_params):
    """Tests deriving parameters from file-like seed URLs."""
    derived_params = crawler.derive_crawl_params_from_url(seed_url)
    assert derived_params == expected_params