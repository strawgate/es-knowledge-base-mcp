import logging
import yaml
from typing import List, Dict, Any
import aiodocker
from aiodocker.exceptions import DockerError
from pydantic import BaseModel

from esdocmanagermcp.components.errors import (
    CrawlError,
    ContainerStartFailedError,
    ConfigGenerationError,
    ContainerNotFoundError,
)

from esdocmanagermcp.components.helpers import docker_utils
from esdocmanagermcp.components.helpers.docker_utils import InjectFile


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
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

    # region Constants
    docker_client: aiodocker.Docker
    settings: CrawlerSettings

    # Label used to identify containers managed by this component
    MANAGED_BY_LABEL = "managed-by"
    MANAGED_BY_VALUE = "mcp-crawler"
    DOMAIN_LABEL = "crawl-domain"
    CONFIG_FILENAME = "crawl.json"
    # endregion Constants

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
        Generates the crawler configuration in memory and returns an InjectFile object.
        Raises ConfigGenerationError on JSON serialization error.
        """
        config = {
            "domains": [{
                "url": domain,
                "seed_urls": [seed_url],
                "crawl_rules": [
                    {"policy": "allow", "type": "begins", "pattern": filter_pattern},
                    {"policy": "deny", "type": "regex", "pattern": ".*"},
                ]
            }],
            "output_sink": "elasticsearch",
            "output_index": output_index,
            "elasticsearch": {
                **self.settings.crawler_output_settings,
            }
        }
        # Define target path within the container
        config_container_path = "/config/" + self.CONFIG_FILENAME

        try:
            # Use indent for readability
            config_content = yaml.dump(config, indent=2)
            logger.debug(
                f"Generated config content in memory for {config_container_path}."
            )
            # Return InjectFile object directly
            return InjectFile(filename=config_container_path, content=config_content)
        except TypeError as e:
            logger.error(f"Error serializing config to JSON: {e}")
            raise ConfigGenerationError(
                f"Failed to serialize config to JSON: {e}"
            ) from e

    # endregion Private Methods

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
        Raises ConfigGenerationError or ContainerStartFailedError on failure.
        """
        if not domain or not seed_url or not filter_pattern or not output_index_suffix:
            msg = "Missing required arguments: domain, seed_url, filter_pattern, output_index_suffix"
            logger.error(msg)
            raise ValueError(msg)

        output_index = f"{self.settings.es_index_prefix}-{output_index_suffix}"
        logger.info(
            f"Attempting to start crawl for domain '{domain}' -> index '{output_index}'"
        )

        # 1. Prepare Config File Object
        try:
            logger.debug("Preparing crawler configuration file object...")
            config_file_to_inject = await self._prepare_crawl_config_file(
                domain, seed_url, filter_pattern, output_index
            )
            logger.debug("Crawler configuration file object prepared.")
        except ConfigGenerationError:
            raise  # Re-raise the specific error

        # 2. Define Container Parameters
        image_name = self.settings.crawler_image
        command = ["ruby", "bin/crawler", "crawl", config_file_to_inject.filename]
        labels = {
            self.MANAGED_BY_LABEL: self.MANAGED_BY_VALUE,
            self.DOMAIN_LABEL: domain,
        }
        files_to_inject = [config_file_to_inject]

        # 3. Start Container via Helper
        try:
            logger.debug("Starting container execution via helper...")
            container_id = await docker_utils.start_container_with_files(
                docker_client=self.docker_client,
                image_name=image_name,
                command=command,
                files_to_inject=files_to_inject,
                labels=labels,
            )
            logger.info(
                f"Successfully started crawl container '{container_id[:12]}' for domain '{domain}'."
            )
        except (DockerError, RuntimeError) as e:
            raise ContainerStartFailedError(
                f"Failed to start container for domain '{domain}': {e}"
            ) from e

        # 4. Return Container ID on Success
        return container_id

    async def list_crawls(self) -> List[Dict[str, Any]]:
        """Lists all containers managed by this crawler component."""
        logger.info("Listing managed crawl containers...")
        label_filter = f"{self.MANAGED_BY_LABEL}={self.MANAGED_BY_VALUE}"
        containers = await docker_utils.list_containers(
            self.docker_client, label_filter
        )
        return containers

    async def get_crawl_status(self, container_id: str) -> Dict[str, Any]:
        """Gets the status and details of a specific crawl container."""
        logger.info(f"Getting status for crawl container '{container_id[:12]}'...")

        details = await docker_utils.get_container_details(
            self.docker_client, container_id
        )
        if details is None:
            raise ContainerNotFoundError(f"Container '{container_id[:12]}' not found.")

        state = details.get("State", {})
        config = details.get("Config", {})
        labels = config.get("Labels", {})

        if labels.get(self.MANAGED_BY_LABEL) != self.MANAGED_BY_VALUE:
            raise CrawlError(
                f"Container '{container_id[:12]}' is not a managed crawl container."
            )

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
        logger.info(
            f"Getting logs (tail={tail}) for crawl container '{container_id[:12]}'..."
        )
        try:
            logs = await docker_utils.get_container_logs(
                self.docker_client, container_id, tail
            )
        except RuntimeError as e:  # Catch the specific "Not Found" error from helper
            raise ContainerNotFoundError(str(e)) from e
        # Allow other DockerErrors to propagate naturally

        return logs

    async def stop_crawl(self, container_id: str) -> None:
        """Stops and removes a specific crawl container."""
        logger.info(
            f"Attempting to stop and remove crawl container '{container_id[:12]}'..."
        )

        removed = await docker_utils.remove_container(
            self.docker_client, container_id, force=True
        )
        if not removed:
            raise ContainerNotFoundError(f"Container '{container_id[:12]}' not found.")
        # Implicitly returns None on success

    async def remove_completed_crawls(self) -> Dict[str, Any]:
        """
        Removes all completed (exited) crawl containers managed by this component.
        Returns a summary of the operation.
        """
        logger.info("Attempting to remove completed crawl containers...")
        removed_count = 0
        errors = []
        label_filter = f"{self.MANAGED_BY_LABEL}={self.MANAGED_BY_VALUE}"

        try:
            # List all managed containers first
            # Need all_containers=True to see exited ones
            containers = await docker_utils.list_containers(
                self.docker_client, label_filter, all_containers=True
            )
            logger.debug(f"Found {len(containers)} managed containers (including non-running).")

            for container_info in containers:
                container_id = container_info.get("id")
                container_state = container_info.get("state")
                short_id = container_id[:12] if container_id else "N/A"

                if container_state == "exited":
                    logger.info(f"Found exited container: {short_id}. Attempting removal...")
                    try:
                        # Don't force remove exited containers
                        removed = await docker_utils.remove_container(
                            self.docker_client, container_id, force=False
                        )
                        if removed:
                            logger.info(f"Successfully removed container {short_id}.")
                            removed_count += 1
                        else:
                            # This case might indicate the container was already gone
                            logger.warning(f"Container {short_id} not found during removal attempt, might have been removed already.")
                            # Optionally add to errors if this is unexpected
                            # errors.append({"container_id": short_id, "error": "Not found during removal"})
                    except DockerError as e:
                        logger.error(f"Failed to remove container {short_id}: {e}")
                        errors.append({"container_id": short_id, "error": str(e)})
                    except Exception as e: # Catch unexpected errors
                        logger.error(f"Unexpected error removing container {short_id}: {e}")
                        errors.append({"container_id": short_id, "error": f"Unexpected error: {str(e)}"})
                else:
                    logger.debug(f"Skipping container {short_id} (state: {container_state}).")

        except DockerError as e:
            logger.error(f"Error listing containers: {e}")
            errors.append({"container_id": None, "error": f"Failed to list containers: {str(e)}"})
        except Exception as e: # Catch unexpected errors during listing
            logger.error(f"Unexpected error during container listing: {e}")
            errors.append({"container_id": None, "error": f"Unexpected error during listing: {str(e)}"})


        result = {"removed_count": removed_count, "errors": errors}
        logger.info(f"Completed removal process. Removed: {removed_count}, Errors: {len(errors)}.")
        return result

    # endregion Public Methods


# endregion Class Definition
