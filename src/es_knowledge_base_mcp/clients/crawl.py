from __future__ import annotations

import urllib.parse
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import yaml
from aiodocker.docker import Docker
from aiodocker.exceptions import DockerError
from fastmcp.utilities.logging import get_logger
from requests import HTTPError

from es_knowledge_base_mcp.clients import docker as docker_utils
from es_knowledge_base_mcp.clients.docker import InjectFile
from es_knowledge_base_mcp.clients.web import extract_urls_from_webpage
from es_knowledge_base_mcp.errors.crawler import (
    CrawlerDockerError,
    CrawlerError,
    CrawlerValidationHTTPError,
    CrawlerValidationNoIndexNofollowError,
    CrawlerValidationTooManyURLsError,
)

if TYPE_CHECKING:
    from es_knowledge_base_mcp.models.settings import CrawlerSettings, ElasticsearchSettings

logger = get_logger("knowledge-base-mcp.crawl")

# endregion Crawler Settings


class Crawler:
    """Handles the logic for crawling websites using Docker."""

    docker_socket: str | None

    docker_client: Docker

    settings: CrawlerSettings

    # Container Label used to identify containers managed by this component
    MANAGED_BY_LABEL = "managed-by"
    MANAGED_BY_VALUE = "mcp-crawler"

    DOMAIN_LABEL = "crawl-domain"
    CRAWL_CONFIG_PATH = "/config/crawl.yml"

    def __init__(
        self,
        settings: CrawlerSettings,
        elasticsearch_settings: ElasticsearchSettings,
    ):
        """Initializes the Crawler component."""
        self.elasticsearch_settings = elasticsearch_settings

        self.settings = settings
        self.docker_socket = settings.docker_socket

        logger.debug("Crawler component initialized with settings: %s", self.settings)

    async def async_init(self) -> None:
        """Initializes the Docker client for the crawler."""
        logger.debug("Initializing Docker client for Crawler...")

        try:
            self.docker_client = Docker(url=self.docker_socket)
        except DockerError as e:
            msg = "Failed to initialize Docker client"
            logger.exception(msg)
            raise CrawlerError(message=msg) from e

        logger.debug("Docker client initialized.")

    async def async_shutdown(self) -> None:
        """Cleans up the Docker client for the crawler."""
        try:
            await self.docker_client.close()
        except Exception as e:
            msg = "Failed to close Docker client"
            logger.exception(msg)
            raise CrawlerError(message=msg) from e

    @asynccontextmanager
    async def handle_errors(self, operation: str = "Docker operation"):
        """Context manager to handle errors during Docker operations."""
        try:
            yield
        except DockerError as e:
            msg = f"Docker {operation} failed"
            logger.exception(msg)
            raise CrawlerDockerError(message=msg) from e
        except Exception as e:
            msg = f"Unexpected error during {operation}"
            logger.exception(msg)
            raise CrawlerError(message=msg) from e

    # region Prepare Config
    @classmethod
    async def _prepare_crawl_config_file(
        cls,
        domain: str,
        seed_url: str,
        filter_pattern: str,
        elasticsearch_index_name: str,
        crawler_es_settings: dict[str, Any],
        exclude_paths: list[str] | None = None,
    ) -> InjectFile:
        """Generates the crawler configuration content (as YAML) in memory. This configuration is the Crawler configuration
        which is documented in https://github.com/elastic/crawler/blob/main/docs/CONFIG.md.

        Returns:
            InjectFile: An object containing the generated config content and target path within the container.

        """
        additional_exclusion_rules = []

        if exclude_paths is not None:
            # if the path is a full url we need to extract the path from it
            trimmed_exclude_paths = [urllib.parse.urlparse(path).path for path in exclude_paths]
            additional_exclusion_rules.extend([{"policy": "deny", "type": "begins", "pattern": path} for path in trimmed_exclude_paths])

        config = {
            "domains": [
                {
                    "url": domain,
                    "seed_urls": [seed_url],
                    "crawl_rules": [
                        *additional_exclusion_rules,
                        {"policy": "allow", "type": "begins", "pattern": filter_pattern},
                        {"policy": "deny", "type": "regex", "pattern": ".*"},
                    ],
                }
            ],
            "log_level": "DEBUG",
            "output_sink": "elasticsearch",
            "output_index": elasticsearch_index_name,
            "elasticsearch": {
                **crawler_es_settings,
            },
        }

        config_container_path = cls.CRAWL_CONFIG_PATH

        return InjectFile(filename=config_container_path, content=yaml.dump(config, indent=2))

    # endregion Prepare Config

    @classmethod
    def derive_crawl_params(cls, url: str) -> dict[str, str]:
        """Derives crawl parameters using a heuristic based on the URL. Intelligently determine
        the right parameters to use based on the URL provided:
        1. If the url has a file extension, we assume it's a file. We then crawl everything that matches the url
            up to the last `/` character.
        2. If the url doesn't have a file extension, we assume it's a directory. We then crawl everything url
            starts with the url provided.

        Args:
            url: The URL to process.

        Returns:
            A dictionary containing "page_url", "domain", "filter_pattern", and "elasticsearch_index_name".

        """
        parsed = urllib.parse.urlparse(url)

        path = parsed.path
        filter_pattern = path

        # if end of the url is a file, we need to crawl everything that matches the url up to the last `/` character
        if not path.endswith("/") and "." in path.split("/")[-1]:
            filter_pattern = path[: path.rfind("/") + 1] or "/"

        return {
            "seed_url": url,
            "domain": parsed.scheme + "://" + parsed.netloc,
            "filter_pattern": filter_pattern,
        }

    # endregion Crawl Parameters
    # region Crawl Validation

    @classmethod
    async def validate_crawl(cls, url: str, max_child_page_limit: int = 500) -> dict[str, Any]:
        """Validates whether the target URL is suitable for crawling.

        Checks for potential issues such as excessive child URLs or 'noindex'/'nofollow' directives.

        Args:
            url: The URL to validate.
            max_child_page_limit: The maximum allowed number of child pages.

        Returns:
            A dictionary containing derived crawl parameters if validation is successful.

        Raises:
            CrawlerValidationHTTPError: If there's an HTTP error fetching the URL.
            CrawlerValidationNoIndexNofollowError: If the page has both 'noindex' and 'nofollow' directives.
            CrawlerValidationTooManyURLsError: If the number of child URLs exceeds the limit.

        """
        logger.debug(f"Validating url {url} for crawling")

        crawl_parameters = cls.derive_crawl_params(url)

        logger.debug(f"Derived crawl parameters: {crawl_parameters}")

        try:
            extraction_result = await extract_urls_from_webpage(
                url=url, domain_filter=crawl_parameters["domain"], path_filter=crawl_parameters["filter_pattern"]
            )

        except HTTPError as e:
            reason = f"Could not validate crawl. Failed to extract URLs from {url}: {e}"
            logger.exception(reason)
            raise CrawlerValidationHTTPError(message=reason) from e

        if extraction_result["page_is_noindex"] and extraction_result["page_is_nofollow"]:
            reason = f"Validation failed: Seed URL {url} is marked with both 'noindex' and 'nofollow'."
            logger.error(reason)
            raise CrawlerValidationNoIndexNofollowError(message=reason)

        num_urls = len(extraction_result["urls_to_crawl"])
        logger.debug(f"Found {num_urls} URLs to crawl (excluding nofollow links).")

        if num_urls > max_child_page_limit:
            reason = f"""
            Could not validate crawl. Excessive child URLs ({num_urls} > {max_child_page_limit}).
            Validate that you're crawling a specific enough URL or consider setting max_child_page_limit.
            """
            logger.error(reason)
            raise CrawlerValidationTooManyURLsError(message=reason)

        return crawl_parameters

    # endregion Crawl Validation

    # region Image Handling
    async def pull_crawler_image(self) -> None:
        """Pulls the configured crawler Docker image."""
        image_name = self.settings.docker_image

        logger.debug(f"Pulling Docker image '{image_name}' for crawler...")

        await self.docker_client.images.pull(image_name)

    # endregion Image Handling

    # region Start Crawl

    async def crawl_domain(
        self,
        domain: str,
        seed_url: str,
        filter_pattern: str,
        elasticsearch_index_name: str,
        exclude_paths: list[str] | None = None,
    ) -> str:
        """Starts a crawl job asynchronously by launching a container.

        Args:
            domain (str): The domain to crawl.
            seed_url (str): The seed URL to start the crawl from.
            filter_pattern (str): The filter pattern for the crawl.
            elasticsearch_index_name (str): The suffix for the output index name.
            exclude_paths (str | None): Optional paths to exclude from the crawl.

        Returns:
            str: The ID of the started container.

        Example:
            >>> crawl_domain("http://example.com", "http://example.com/start", "/filter", "example_com")
            "container_id_123456"

        """
        logger.debug(f"Attempting to start crawl for domain '{domain}' -> index '{elasticsearch_index_name}'")

        config_file_to_inject = await self._prepare_crawl_config_file(
            domain=domain,
            seed_url=seed_url,
            filter_pattern=filter_pattern,
            exclude_paths=exclude_paths,
            elasticsearch_index_name=elasticsearch_index_name,
            crawler_es_settings=self.elasticsearch_settings.to_crawler_settings(),
        )

        random_id = uuid4().hex[:8]

        async with self.handle_errors("starting crawl container"):
            container_id = await docker_utils.start_container_with_files(
                docker_client=self.docker_client,
                container_name=f"mcp-crawler-{elasticsearch_index_name}-{random_id}",
                image_name=self.settings.docker_image,
                command=["ruby", "bin/crawler", "crawl", config_file_to_inject.filename],
                files_to_inject=[config_file_to_inject],
                labels={
                    self.MANAGED_BY_LABEL: self.MANAGED_BY_VALUE,
                    self.DOMAIN_LABEL: domain,
                },
            )

            logger.info(f"Started crawl for domain '{domain}' -> index '{elasticsearch_index_name}' with container ID '{container_id}'")

            return container_id

    # endregion Crawl

    # region Manage Crawls
    async def list_crawls(self) -> list[dict[str, Any]]:
        """Lists all containers managed by this crawler component."""
        label_filter = f"{self.MANAGED_BY_LABEL}={self.MANAGED_BY_VALUE}"

        async with self.handle_errors("listing crawl containers"):
            return await docker_utils.get_containers_details(self.docker_client, label_filter)

    async def get_crawl_logs(self, container_id: str) -> str:
        """Gets logs for a specific crawl container.

        Args:
            container_id (str): The ID of the container to retrieve logs for.

        """
        async with self.handle_errors("getting crawl logs"):
            return await docker_utils.container_logs(self.docker_client, container_id)

    async def stop_crawl(self, container_id: str) -> None:
        """Stops and removes a specific crawl container.

        Args:
            container_id (str): The ID of the container to stop and remove.

        """
        async with self.handle_errors("stopping crawl container"):
            await docker_utils.remove_container(self.docker_client, container_id)

    # endregion Manage Crawls

    # region Cleanup

    async def remove_completed_crawls(self) -> dict[str, Any]:
        """Removes all completed (exited) crawl containers managed by this component.
        Returns a summary of the operation.
        """
        logger.info("Attempting to remove completed crawl containers...")

        async with self.handle_errors("removing completed crawl containers"):
            crawler_containers = await docker_utils.get_containers(
                self.docker_client, f"{self.MANAGED_BY_LABEL}={self.MANAGED_BY_VALUE}", all_containers=True
            )

        completed_crawls = [container for container in crawler_containers if container["State"] == "exited"]

        logger.debug(f"Found {len(completed_crawls)} completed crawls.")

        async with self.handle_errors("removing completed crawl containers"):
            [await docker_utils.remove_container(self.docker_client, container["Id"]) for container in completed_crawls]

        logger.info(f"Removed {len(completed_crawls)} completed crawls.")

        return {
            "removed": len(completed_crawls),
            "total": len(crawler_containers),
        }

    # endregion Cleanup
