"""Utility functions for interacting with Docker."""

import datetime
import io
import logging
import tarfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from aiodocker.docker import Docker, DockerContainer
from aiodocker.exceptions import DockerError

from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME

logger = logging.getLogger(BASE_LOGGER_NAME).getChild("utils").getChild("docker")


# region File Injection
@dataclass
class InjectFile:
    """Represents a file to be injected into a container."""

    filename: str  # Full path *inside* the container (e.g., "/app/config.yml")
    content: str  # File content as a string

    def to_tar_stream(self) -> io.BytesIO:
        """Converts the file content to a tar stream."""
        tar_stream = io.BytesIO()

        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            file_bytes = self.content.encode("utf-8")
            tarinfo = tarfile.TarInfo(name=self.filename.lstrip("/"))
            tarinfo.size = len(file_bytes)
            tarinfo.mtime = int(datetime.datetime.now(datetime.UTC).timestamp())
            tar.addfile(tarinfo, io.BytesIO(file_bytes))

        tar_stream.seek(0)

        return tar_stream


@asynccontextmanager
async def handle_errors(operation: str) -> AsyncIterator[None]:
    """Context manager for error handling."""
    logger.debug(f"Attempting {operation}...")

    try:
        yield
    except DockerError:
        logger.exception(f"Docker error during {operation}")
        raise
    except Exception:
        logger.exception(f"Unexpected error during {operation}")
        raise

    logger.debug(f"Completed {operation}.")


# region Start Container


async def start_container_with_files(
    docker_client: Docker,
    image_name: str,
    command: list[str],
    files_to_inject: list[InjectFile],
    labels: dict[str, str],
    container_name: str | None = None,
) -> str:
    """Creates a container, injects files into it, and then starts it.

    Args:
        docker_client: Docker client instance.
        image_name: Name of the Docker image to use.
        command: Command to run in the container.
        files_to_inject: List of files to inject into the container.
        labels: Labels to apply to the container.
        container_name: Optional name for the container.

    Returns:
        str:  12-character container ID.

    Example:
        >>> container_id = await start_container_with_files(
                docker_client,
                image_name="my_image:latest",
                command=["python", "app.py"],
                files_to_inject=[InjectFile(filename="/app/config.yml", content="config content")],
                labels={"env": "test"},
                container_name="my_container"
            )
    12-character container ID is returned.

    """
    container: DockerContainer | None = None

    container_config = {
        "Image": image_name,
        "Cmd": command,
        "Labels": labels or {},
        "HostConfig": {"AutoRemove": False},
        "MemoryReservation": 512 * 1024 * 1024,  # 512 MB
    }

    logger.debug(f"Preparing container '{container_name or 'unnamed'}' for image '{image_name}' with labels {labels}")

    async with handle_errors("image pull"):
        await docker_client.images.pull(image_name)

    async with handle_errors("container setup"):
        container = await docker_client.containers.create(config=container_config, name=container_name)
        logger.debug(f"Created container '{container.id}'.")

    if files_to_inject:
        logger.debug(f"Preparing to inject {len(files_to_inject)} file(s) into container '{container.id}'.")
        [await container.put_archive(path="/", data=file.to_tar_stream()) for file in files_to_inject]

    async with handle_errors("container start"):
        await container.start()

    return container.id


# endregion Start Container


# region Container Info
async def get_containers(docker_client: Docker, label_filter: str, all_containers: bool = False) -> list[DockerContainer]:
    """Lists containers matching a label filter, returning basic info."""
    label_filter_str = label_filter if "=" in label_filter else f"{label_filter}"

    logger.debug(f"Listing containers with label filter '{label_filter_str}'...")

    async with handle_errors("container list"):
        containers = await docker_client.containers.list(all=all_containers, filters={"label": [label_filter_str]})

    logger.debug(f"Found {len(containers)} container(s) matching label filter '{label_filter_str}'.")

    return containers


async def get_containers_details(docker_client: Docker, label_filter: str, all_containers: bool = False) -> list[dict[str, Any]]:
    """Lists containers matching a label filter, returning detailed info."""
    containers = await get_containers(docker_client, label_filter, all_containers)

    return [container._container for container in containers]


async def container_logs(docker_client: Docker, container_id: str) -> str:
    """Retrieves logs for a specific container ID."""
    logger.debug(f"Retrieving logs for container '{container_id}'...")

    async with handle_errors("container logs"):
        container = await docker_client.containers.get(container_id)
        logs = await container.log(stdout=True, stderr=True)

    logger.debug(f"Retrieved logs for container '{container_id}'.")

    return "".join(logs)


# endregion Container Info

# region Cleanup Container


async def remove_container(docker_client: Docker, container_id: str) -> None:
    """Removes containers matching a label filter."""
    logger.debug(f"Removing container '{container_id}'...")

    async with handle_errors("container removal"):
        container = await docker_client.containers.get(container_id)
        await container.delete(force=True)

    logger.debug(f"Removed container '{container_id}'.")


async def remove_containers(docker_client: Docker, label_filter: str) -> None:
    """Removes containers matching a label filter."""
    containers = await get_containers(docker_client, label_filter)

    logger.debug(f"Removing {len(containers)} container(s) matching label filter '{label_filter}'...")

    async with handle_errors("container removal"):
        [await container.delete(force=True) for container in containers]

    logger.debug(f"Removed {len(containers)} container(s) matching label filter '{label_filter}'.")


# endregion Cleanup Container
