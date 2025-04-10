import logging
import io
import tarfile
import datetime
import aiodocker
from aiodocker.exceptions import DockerError
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# region Start Container
@dataclass
class InjectFile:
    """Represents a file to be injected into a container."""

    filename: str  # Full path *inside* the container (e.g., "/app/config/crawl.yml")
    content: str  # File content as a string


def _prepare_files_tar_stream(files: List[InjectFile]) -> io.BytesIO:
    """Creates an in-memory tar stream containing multiple files. Raises RuntimeError on failure."""
    tar_stream = io.BytesIO()
    try:
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            for file_to_inject in files:
                # Tar paths should be relative to the root specified in put_archive (which is '/')
                # Ensure filename is treated as the full path within the tar archive.
                # TarInfo name should not have a leading '/' according to spec,
                # but put_archive needs it if copying to root. Let's strip for TarInfo.
                tar_path = file_to_inject.filename.lstrip("/")

                logger.debug(f"Adding file '{tar_path}' to tar stream (original: '{file_to_inject.filename}')")
                file_bytes = file_to_inject.content.encode("utf-8")
                tarinfo = tarfile.TarInfo(name=tar_path)
                tarinfo.size = len(file_bytes)
                tarinfo.mtime = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                tar.addfile(tarinfo, io.BytesIO(file_bytes))
        tar_stream.seek(0)
        logger.debug(f"Prepared in-memory tar stream for {len(files)} files.")
        return tar_stream
    except (IOError, tarfile.TarError) as e:
        logger.error(f"Failed to prepare files tar stream: {e}")
        raise RuntimeError(f"Failed to prepare files tar stream: {e}")


async def pull_image(docker_client: aiodocker.Docker, image_name: str):
    """Pulls a Docker image if it's not present locally. Raises DockerError on failure."""
    try:
        await docker_client.images.inspect(image_name)
        logger.info(f"Image '{image_name}' already exists locally.")
    except DockerError as e:
        if e.status == 404:
            logger.info(f"Pulling image '{image_name}'...")
            try:
                await docker_client.images.pull(image_name)
                logger.info(f"Image '{image_name}' pulled successfully.")
            except DockerError as pull_err:
                logger.error(f"Failed to pull image '{image_name}': {pull_err}")
                raise  # Re-raise pull error
        else:
            logger.error(f"Error inspecting image '{image_name}': {e}")
            raise  # Re-raise other inspect errors


async def start_container_with_files(
    docker_client: aiodocker.Docker,
    image_name: str,
    command: List[str],
    files_to_inject: List[InjectFile],
    labels: Dict[str, str],
    container_name: Optional[str] = None,
) -> str:
    """
    Creates, injects files into, and starts a container. Returns container ID.
    Cleans up container if any step fails before successful start.
    Does NOT wait for the container to exit. AutoRemove is False.
    Raises DockerError or RuntimeError on failure.
    """
    container: Optional[aiodocker.containers.DockerContainer] = None
    container_config = {
        "Image": image_name,
        "Cmd": command,
        "Labels": labels or {},
        "HostConfig": {
            "AutoRemove": False,  # Important for async management
        },
    }
    logger.debug(f"Preparing container '{container_name or 'unnamed'}' for image '{image_name}' with labels {labels}")

    try:
        # 1. Create Container
        container = await docker_client.containers.create(config=container_config, name=container_name)
        # Use ID for logging consistency
        container_id_log = container.id[:12] if container and hasattr(container, "id") else "N/A"
        logger.info(f"Container '{container_id_log}' created with name '{container_name or 'None'}'.")

        # 2. Prepare and Copy Files (if any)
        if files_to_inject:
            # This can raise RuntimeError
            tar_stream = _prepare_files_tar_stream(files_to_inject)
            try:
                logger.debug(f"Copying {len(files_to_inject)} file(s) to container '{container_id_log}' at path '/'")
                tar_data = tar_stream.read()
                # Copy relative to root, InjectFile.filename contains full path
                # This can raise DockerError
                await container.put_archive(path="/", data=tar_data)
                logger.info(f"Files copied to container '{container_id_log}'.")
            finally:
                tar_stream.close()  # Ensure stream is closed even if put_archive fails

        # 3. Start Container
        logger.info(f"Starting container '{container_id_log}'...")
        # This can raise DockerError
        await container.start()
        logger.info(f"Container '{container_id_log}' started successfully.")
        return container.id  # Return full ID

    except (DockerError, RuntimeError, Exception) as e:
        # Log the primary error leading to potential cleanup
        container_id_log = container.id[:12] if container and hasattr(container, "id") else "N/A"
        logger.error(f"Failed during setup/start of container '{container_id_log}' for image '{image_name}': {e}")
        # Attempt cleanup if container object exists
        if container:
            logger.warning(f"Attempting cleanup of failed container {container_id_log}...")
            try:
                await container.delete(force=True)
                logger.info(f"Cleaned up failed container {container_id_log}.")
            except Exception as cleanup_err:
                # Log cleanup error but raise the original error
                logger.error(f"Failed to cleanup container {container_id_log} after setup/start error: {cleanup_err}")
        else:
            logger.warning(
                f"Container object does not exist or failed before creation, no cleanup needed for image '{image_name}'."
            )
        raise  # Re-raise the original error that caused the failure


# endregion Start Container


# region Container Info
async def list_containers(
    docker_client: aiodocker.Docker, label_filter: str, all_containers: bool = False
) -> List[Dict[str, Any]]:
    """Lists containers matching a label filter, returning basic info."""
    try:
        # Filter format: "label=key=value" or just "label=key"
        label_filter_str = label_filter if "=" in label_filter else f"{label_filter}"
        containers = await docker_client.containers.list(all=all_containers, filters={"label": [label_filter_str]})
        container_list = [
            {
                "id": c.id,
                "short_id": c.id[:12],
                "names": c._container.get("Names", []),
                "image": c._container.get("Image", ""),
                "status": c._container.get("Status", ""),  # Raw Docker status string
                "state": c._container.get("State", ""),  # e.g., running, exited
                "labels": c._container.get("Labels", {}),
                # Ensure Created timestamp is handled correctly
                "created": datetime.datetime.fromtimestamp(
                    c._container.get("Created", 0), tz=datetime.timezone.utc
                ).isoformat()
                if c._container.get("Created")
                else None,
            }
            for c in containers
        ]
        logger.debug(f"Found {len(container_list)} containers with label filter '{label_filter_str}'")
        return container_list
    except DockerError as e:
        logger.error(f"Failed to list containers with label filter '{label_filter}': {e}")
        raise


async def get_container_details(docker_client: aiodocker.Docker, container_id: str) -> Optional[Dict[str, Any]]:
    """Gets detailed info (from 'inspect') for a specific container ID."""
    container_id_short = container_id[:12]
    try:
        container = await docker_client.containers.get(container_id)
        details = await container.show()
        logger.debug(f"Retrieved details for container '{container_id_short}'")
        return details
    except DockerError as e:
        if e.status == 404:
            logger.warning(f"Container '{container_id_short}' not found when getting details.")
            return None
        else:
            logger.error(f"Failed to get details for container '{container_id_short}': {e}")
            raise


async def get_container_logs(docker_client: aiodocker.Docker, container_id: str, tail: str = "all") -> str:
    """Gets logs for a specific container ID. Raises RuntimeError if not found."""
    container_id_short = container_id[:12]
    try:
        container = await docker_client.containers.get(container_id)
        log_opts = {"stdout": True, "stderr": True, "tail": tail}
        logs_stream = await container.log(**log_opts)
        logs = "".join(logs_stream)
        logger.debug(f"Retrieved logs (tail={tail}) for container '{container_id_short}'")
        return logs
    except DockerError as e:
        if e.status == 404:
            logger.error(f"Container '{container_id_short}' not found when getting logs.")
            # Raise specific error as per plan
            raise RuntimeError(f"Container '{container_id_short}' not found.") from e
        else:
            logger.error(f"Failed to get logs for container '{container_id_short}': {e}")
            raise


# endregion Container Info

# region Cleanup Container


async def remove_container(docker_client: aiodocker.Docker, container_id: str, force: bool = True) -> bool:
    """Stops (implicitly via force=True) and removes a container. Returns True if removed, False if not found."""
    container_id_short = container_id[:12]
    logger.warning(f"Attempting to remove container '{container_id_short}' (force={force})...")
    try:
        container = await docker_client.containers.get(container_id)
        # force=True in delete implicitly handles stopping if running
        await container.delete(force=force)
        logger.info(f"Successfully removed container '{container_id_short}'.")
        return True
    except DockerError as e:
        if e.status == 404:
            logger.warning(f"Container '{container_id_short}' not found during removal attempt.")
            return False  # Indicate it wasn't found
        else:
            logger.error(f"Failed to remove container '{container_id_short}': {e}")
            raise


# endregion Cleanup Container
