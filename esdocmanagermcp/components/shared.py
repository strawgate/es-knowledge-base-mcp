import logging
import inspect

import os
from typing import Any, List, Optional, Dict
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, model_validator
from elasticsearch import AsyncElasticsearch

logger = logging.getLogger(__name__)

class LoggingSettings(BaseSettings):
    """Settings for configuring logging."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    # include the PID in the log format
    log_format: str = Field(
        f"%(asctime)s : {os.getpid()} - %(name)s - %(levelname)s - %(message)s",
        validation_alias="LOG_FORMAT",
    )
    log_file: Optional[str] = Field(None, validation_alias="LOG_FILE")

    def configure_logging(self):
        """Configure logging based on the settings."""
        logging.basicConfig(
            level=self.log_level,
            format=self.log_format,
            filename=self.log_file,
            filemode="a",
        )

class TransportSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mcp_transport: str = Field("stdio", validation_alias="MCP_TRANSPORT")

# region Settings
class AppSettings(BaseSettings):
    """Manages application configuration using environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    es_host: str = Field(..., validation_alias="ES_HOST")
    es_pipeline: str = Field("search-default-ingestion", validation_alias="ES_PIPELINE")
    es_api_key: Optional[SecretStr] = Field(None, validation_alias="ES_API_KEY")
    es_username: Optional[str] = Field(None, validation_alias="ES_USERNAME")
    es_password: Optional[SecretStr] = Field(None, validation_alias="ES_PASSWORD")
    es_index_prefix: str = Field("docsmcp", serialization_alias="ES_INDEX_PREFIX")

    crawler_image: str = Field("ghcr.io/strawgate/es-crawler:main", validation_alias="CRAWLER_IMAGE")


    @model_validator(mode="after")
    def check_auth_logic(self) -> "AppSettings":
        """Validate that either API key or username/password is provided, but not both."""
        api_key_set = self.es_api_key is not None
        basic_auth_set = self.es_username is not None and self.es_password is not None

        if not api_key_set and not basic_auth_set:
            raise ValueError(
                "Missing Elasticsearch authentication details. Provide ES_API_KEY or both ES_USERNAME and ES_PASSWORD."
            )
        if api_key_set and basic_auth_set:
            raise ValueError(
                "Conflicting Elasticsearch authentication details. Provide either ES_API_KEY or both ES_USERNAME and ES_PASSWORD, not both."
            )
        return self


# endregion Settings


# region Utility Functions
def generate_index_template(index_pattern: list[str], pipeline_name: str) -> Dict[str, Any]:
    """
    Generates the dictionary structure for an Elasticsearch index template.

    Args:
        index_pattern: List of patterns the template should apply to.
        pipeline_name: The default ingest pipeline to set for matching indices.

    Returns:
        A dictionary representing the Elasticsearch index template definition.
    """
    return {
        "index_patterns": index_pattern,
        "template": {
            "settings": {"index": {"default_pipeline": pipeline_name}},
            "mappings": {
                "dynamic_templates": [],
                "properties": {
                    "body": {
                        "type": "semantic_text",
                        "inference_id": ".elser-2-elasticsearch",  # TODO: Make configurable?
                        "model_settings": {
                            "service": "elasticsearch",
                            "task_type": "sparse_embedding",
                        },
                    },
                    "headings": {
                        "type": "semantic_text",
                        "inference_id": ".elser-2-elasticsearch",  # TODO: Make configurable?
                        "model_settings": {
                            "service": "elasticsearch",
                            "task_type": "sparse_embedding",
                        },
                    },
                    "id": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "last_crawled_at": {"type": "date"},
                    "links": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "meta_keywords": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "title": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "url": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "url_host": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "url_path": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "url_path_dir1": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "url_path_dir2": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "url_path_dir3": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "url_port": {"type": "long"},
                    "url_scheme": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                },
            },
        },
        "priority": 500,
        "_meta": {
            "description": "Index template for crawled documentation managed by MCP",
            "created_by": "elasticsearch-documentation-manager-mcp",
        },
    }


def get_crawler_es_settings(settings: AppSettings):
    """Generates the Elasticsearch connection settings dictionary required by the crawler."""
    # for some reason the crawler takes ES settings in a weird format
    parsed_url = urlparse(settings.es_host)

    es_port = parsed_url.port

    if es_port is None:
        # Default to 443 for HTTPS
        es_port = 443 if parsed_url.scheme == "https" else 80

    es_host_without_port = parsed_url.hostname
    es_host = parsed_url.scheme + "://" + es_host_without_port

    crawler_es_settings = {
        "host": es_host,  # e.g., https://cluster.aws.elastic.cloud
        "port": es_port,  # e.g., 443
        "request_timeout": 600,
        "elasticsearch.bulk_api.max_items": 1000,
        "elasticsearch.bulk_api.max_size_bytes": 10485760,
        "pipeline": settings.es_pipeline,
    }
    if settings.es_api_key:
        crawler_es_settings["api_key"] = settings.es_api_key.get_secret_value()
    elif settings.es_username and settings.es_password:
        crawler_es_settings["basic_auth"] = (
            settings.es_username,
            settings.es_password.get_secret_value(),
        )

    return crawler_es_settings


def create_es_client(settings: AppSettings):
    """
    Creates and returns an AsyncElasticsearch client instance based on AppSettings.
    Raises ValueError for config issues or RuntimeError for client creation failures.
    """

    es_client_args: Dict[str, Any] = {
        "hosts": [settings.es_host],
        "request_timeout": 180,
        "http_compress": True,
        "retry_on_status": (408, 429, 502, 503, 504),
        "retry_on_timeout": True,
        "max_retries": 5,
    }

    if settings.es_api_key:
        es_client_args["api_key"] = settings.es_api_key.get_secret_value()
    elif settings.es_username and settings.es_password:
        es_client_args["basic_auth"] = (
            settings.es_username,
            settings.es_password.get_secret_value(),
        )

    client = AsyncElasticsearch(**es_client_args)
    return client


def format_search_results_plain_text(search_results: List[Dict[str, Any]]) -> str:
    """Formats a list of search result dictionaries into a plain text string."""
    if not search_results:
        return "No search results found."

    results = []

    for i, result in enumerate(search_results):
        title = result.get("title", "No title found")
        url = result.get("url", "No URL found")

        if matches := result.get("match"):
            matches_str = "\n".join([f"- {match.strip()}" for match in matches])
            formatted_string = inspect.cleandoc("""
                Title: {title}
                URL: {url}
                Relevant Snippets:
                {matches}
                ---
            """).format(
                title=title,
                url=url,
                matches=matches_str,
            )
            results.append(formatted_string)

        elif content := result.get("content"):
            formatted_string = inspect.cleandoc("""
                Title: {title}
                URL: {url}
                Content:
                - {content}
                ---
            """).format(
                title=title,
                url=url,
                content=content.strip(),
            )
            results.append(formatted_string)
        else:
            formatted_string = inspect.cleandoc("""
                Title: {title}
                URL: {url}
                ---
            """).format(
                title=title,
                url=url,
            )
            results.append(formatted_string)

        return "\n".join(results)


# endregion Utility Functions
