import logging
import yaml
import urllib.parse
import re
from typing import List, Dict, Any
import aiodocker
from aiodocker.exceptions import DockerError
from pydantic import BaseModel

from esdocmanagermcp.components.errors import (
    CrawlError,
    ContainerStartFailedError,
    ContainerNotFoundError,
)

from esdocmanagermcp.components.helpers import docker_utils
from esdocmanagermcp.components.helpers.docker_utils import InjectFile


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# region Settings
class CrawlerSettings(BaseModel):
    """Settings specific to the Crawler component."""

    crawler_image: str
    crawler_output_settings: dict[str, Any]
    es_index_prefix: str


# endregion Settings


# region Class Definition
class Crawler:
    """Handles the logic for crawling websites using Docker."""

    docker_client: aiodocker.Docker
    settings: CrawlerSettings

    # Container Label used to identify containers managed by this component
    MANAGED_BY_LABEL = "managed-by"
    MANAGED_BY_VALUE = "mcp-crawler"

    DOMAIN_LABEL = "crawl-domain"
    CONFIG_FILENAME = "crawl.yml"

    # region __init__
    def __init__(
        self,
        docker_client: aiodocker.Docker,
        settings: CrawlerSettings,
    ):
        """Initializes the Crawler component."""
        self.docker_client = docker_client
        self.settings = settings
        logger.info("Crawler component initialized.")

    # endregion __init__

    # region Private Methods
    async def _prepare_crawl_config_file(
        self, domain: str, seed_url: str, filter_pattern: str, output_index: str
    ) -> InjectFile:
        """
        Generates the crawler configuration content (as YAML) in memory.

        Returns:
            InjectFile: An object containing the generated config content and target path within the container.
        """

        config = {
            "domains": [
                {
                    "url": domain,
                    "seed_urls": [seed_url],
                    "crawl_rules": [
                        {"policy": "allow", "type": "begins", "pattern": filter_pattern},
                        {"policy": "deny", "type": "regex", "pattern": ".*"},
                    ],
                }
            ],
            "output_sink": "elasticsearch",
            "output_index": output_index,
            "elasticsearch": {
                **self.settings.crawler_output_settings,
            },
        }

        config_container_path = "/config/" + self.CONFIG_FILENAME

        return InjectFile(filename=config_container_path, content=yaml.dump(config, indent=2))

    def _derive_destination_index_name(
        self, domain: str, path: str
    ):
        """Derive an index-friendly name from the domain and path.
        
        Args:
            domain (str): The domain name.
            path (str): The path to be included in the index name.

        Returns:
            str: A sanitized index name derived from the domain and path.

        Example:
            >>> _derive_destination_index_name("example.com", "/full-path/to/resource/index.html")
            "example_com.full_path.to.resource.index_html"
        """
        destination_index_name = domain.lower() + path.lower()

        # convert discuss.elastic.co to discuss_elastic_co
        destination_index_name = destination_index_name.replace(".", "_")
        destination_index_name = destination_index_name.replace("-", "_")
        destination_index_name = destination_index_name.replace("//", "/")

        # convert /microsoft/vscode to .microsoft.vscode
        destination_index_name = destination_index_name.replace("/", ".")

        # Replace any sequence of characters not allowed in index names (non-alphanumeric, '.', '_') with a single underscore
        destination_index_name = re.sub(r"[^a-z0-9._]+", "_", destination_index_name)

        # Remove leading/trailing underscores/dots/hyphens
        destination_index_name = destination_index_name.strip("_.-")

        return destination_index_name

    def derive_crawl_params_from_dir(
        self, seed_dir: str
    ) -> Dict[str, str]:
        """
        Derives crawl parameters from a directory seed URL.
        Args:
            seed_dir: The directory seed URL to process.
        Returns:
            A dictionary containing "domain", "filter_pattern", and "output_index_suffix".

        Example:
        >>> derive_crawl_params_from_dir("http://example.com/full-path/to/resource/")
        {
            "domain": "example.com",
            "filter_pattern": "/full-path/to/resource/",
            "output_index_suffix": "example_com.full_path.to.resource"
        }
        """
        parsed = urllib.parse.urlparse(seed_dir)

        scheme = parsed.scheme
        domain = parsed.netloc
        path = parsed.path
        filter_pattern = path

        return {
            "domain": scheme + "://" + domain,
            "filter_pattern": filter_pattern,
            "page_url": seed_dir,
            "output_index_suffix": self._derive_destination_index_name(domain, path)
        }

    def derive_crawl_params_from_url(
        self, seed_url: str
    ) -> Dict[str, str]:
        """Derives crawl parameters from a URL seed URL.
        Args:
            seed_url: The URL seed URL to process.
        Returns:
            A dictionary containing "domain", "filter_pattern", and "output_index_suffix".
        
        Example:
        >>> derive_crawl_params_from_url("http://example.com/full-path/to/resource/index.html")
        {
            "domain": "example.com",
            "filter_pattern": "/full-path/to/resource/",
            "output_index_suffix": "example_com.full_path.to.resource.index_html"
        }
        """
        parsed = urllib.parse.urlparse(seed_url)

        scheme = parsed.scheme
        domain = parsed.netloc
        path = parsed.path or "/"
        filter_pattern = path

        # if the path ends with a slash, keep it as is, if not, remove the last segment
        if path and not path.endswith("/"):
            last_slash_index = path.rfind("/")
            if last_slash_index != -1:
                filter_pattern = path[: last_slash_index + 1]

        return {
            "domain": scheme + "://" + domain,
            "page_url": seed_url,
            "filter_pattern": filter_pattern,
            "output_index_suffix": self._derive_destination_index_name(domain, path)
        }

    # region Public Methods
    async def pull_crawler_image(self) -> None:
        """Pulls the configured crawler Docker image."""
        image_name = self.settings.crawler_image

        logger.info(f"Attempting to pull crawler image '{image_name}'...")

        await docker_utils.pull_image(self.docker_client, image_name)

    async def crawl_domain(
        self,
        domain: str,
        seed_url: str,
        filter_pattern: str,
        output_index_suffix: str,
    ) -> str:
        """
        Starts a crawl job asynchronously by launching a container.
        Returns the container ID upon successful start.
        Raises ContainerStartFailedError if the container cannot be started.
        """
        output_index = f"{self.settings.es_index_prefix}-{output_index_suffix}"

        logger.info(f"Attempting to start crawl for domain '{domain}' -> index '{output_index}'")

        config_file_to_inject = await self._prepare_crawl_config_file(domain, seed_url, filter_pattern, output_index)

        try:
            container_id = await docker_utils.start_container_with_files(
                docker_client=self.docker_client,
                image_name=self.settings.crawler_image,
                command=["ruby", "bin/crawler", "crawl", config_file_to_inject.filename],
                files_to_inject=[config_file_to_inject],
                labels={
                    self.MANAGED_BY_LABEL: self.MANAGED_BY_VALUE,
                    self.DOMAIN_LABEL: domain,
                },
            )
            return container_id
        
        except (DockerError, RuntimeError) as e:
            raise ContainerStartFailedError(f"Failed to start container for domain '{domain}': {e}") from e

    async def list_crawls(self) -> List[Dict[str, Any]]:
        """Lists all containers managed by this crawler component."""
        label_filter = f"{self.MANAGED_BY_LABEL}={self.MANAGED_BY_VALUE}"

        containers = await docker_utils.list_containers(self.docker_client, label_filter)

        return containers

    async def get_crawl_status(self, container_id: str) -> Dict[str, Any]:
        """Gets the status and details of a specific crawl container."""
        logger.info(f"Getting status for crawl container '{container_id[:12]}'...")

        details = await docker_utils.get_container_details(self.docker_client, container_id)

        if details is None:
            raise ContainerNotFoundError(f"Container '{container_id[:12]}' not found.")

        state = details.get("State", {})
        config = details.get("Config", {})
        labels = config.get("Labels", {})

        if labels.get(self.MANAGED_BY_LABEL) != self.MANAGED_BY_VALUE:
            raise CrawlError(f"Container '{container_id[:12]}' is not a managed crawl container.")

        status_data = {
            "id": details.get("Id"),
            "short_id": details.get("Id", "")[:12],
            "name": details.get("Name", "").lstrip("/"),
            "state": state.get("Status"),
            "running": state.get("Running"),
            "exit_code": state.get("ExitCode"),
            "error": state.get("Error"),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "image": config.get("Image"),
            "labels": labels,
            "crawl_domain": labels.get(self.DOMAIN_LABEL, "N/A"),
        }

        return status_data

    async def get_crawl_logs(self, container_id: str, tail: str = "all") -> str:
        """Gets logs for a specific crawl container."""

        try:
            logs = await docker_utils.get_container_logs(self.docker_client, container_id, tail)
        except RuntimeError as e:
            raise ContainerNotFoundError(str(e)) from e

        return logs

    async def stop_crawl(self, container_id: str) -> None:
        """Stops and removes a specific crawl container."""
        removed = await docker_utils.remove_container(self.docker_client, container_id, force=True)

        if not removed:
            raise ContainerNotFoundError(f"Container '{container_id[:12]}' not found.")


    async def remove_completed_crawls(self) -> Dict[str, Any]:
        """
        Removes all completed (exited) crawl containers managed by this component.
        Returns a summary of the operation.
        """
        logger.info("Attempting to remove completed crawl containers...")

        removed_count = 0
        errors = []

        label_filter = f"{self.MANAGED_BY_LABEL}={self.MANAGED_BY_VALUE}"

        containers = await docker_utils.list_containers(self.docker_client, label_filter, all_containers=True)
        logger.debug(f"Found {len(containers)} managed containers (including non-running).")

        for container_info in containers:
            container_id = container_info.get("id")
            container_state = container_info.get("state")
            short_id = container_id[:12] if container_id else "N/A"

            if container_state != "exited":
                logger.debug(f"Skipping container {short_id} (state: {container_state}).")
                continue

            logger.info(f"Found exited container: {short_id}. Attempting removal...")
            try:
                if await docker_utils.remove_container(self.docker_client, container_id, force=False):
                    logger.info(f"Successfully removed container {short_id}.")
                    removed_count += 1
                else:
                    logger.warning(f"Attempted to remove container {short_id} but was not removed.")
            except DockerError as e:
                logger.error(f"Failed to remove container {short_id}: {e}")
                errors.append({"container_id": short_id, "error": str(e)})
            except Exception as e: # Catch broad exceptions during cleanup to avoid stopping the entire process
                logger.error(f"Unexpected error removing container {short_id}: {e}")
                errors.append({"container_id": short_id, "error": f"Unexpected error: {str(e)}"})

        logger.info(f"Completed removal process. Removed: {removed_count}, Errors: {len(errors)}.")
        return {"removed_count": removed_count, "errors": errors}


# endregion Public Methods


# endregion Class Definition
