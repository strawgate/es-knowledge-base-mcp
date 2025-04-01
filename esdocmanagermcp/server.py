import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional, AsyncIterator, Dict, Any, List
from urllib.parse import urlparse
import aiodocker
from elasticsearch import (
    AsyncElasticsearch,
)
from pydantic import ValidationError

import mcp.server.fastmcp as fastmcp

from esdocmanagermcp.components.shared import (
    AppSettings,
    create_es_client,
    generate_index_template,
    get_crawler_es_settings,
)
from esdocmanagermcp.components.crawl import Crawler, CrawlerSettings
from esdocmanagermcp.components.search import Searcher, SearcherSettings


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# region Globals
# --- Component Instances (initialized in lifespan) ---
crawler: Optional[Crawler] = None
searcher: Optional[Searcher] = None

# --- Load Minimal Settings for MCP Initialization ---
try:
    bootstrap_settings = AppSettings()
    mcp_transport_setting = bootstrap_settings.mcp_transport
    logger.info(f"Using MCP transport: {mcp_transport_setting}")
except ValidationError as e:
    logger.error(f"Initial configuration error loading MCP transport: {e}")
    raise RuntimeError("Failed to load initial MCP transport configuration.") from e
except Exception as e:
    logger.error(f"Unexpected error loading initial MCP transport configuration: {e}")
    raise RuntimeError("Unexpected error during initial configuration loading.") from e


# region Lifespan
@dataclass
class AppContext:
    """Holds initialized components for the application."""

    crawler: Crawler
    searcher: Searcher
    es_client: AsyncElasticsearch
    docker_client: aiodocker.Docker


@asynccontextmanager
async def app_lifespan(server: fastmcp.FastMCP) -> AsyncIterator[AppContext]:
    """
    Manages application startup and shutdown:
    - Loads configuration.
    - Initializes Elasticsearch and Docker clients.
    - Initializes Crawler and Searcher components.
    - Performs initial setup (ES ping, index template, dynamic resources).
    - Yields context with initialized components.
    - Cleans up resources on shutdown.
    """
    global crawler, searcher, docker_client

    logger.info("Executing application startup sequence...")

    try:
        settings = AppSettings()
        logger.info("Application settings loaded successfully.")

        # Initialize Component Settings from AppSettings
        crawler_settings = CrawlerSettings(
            crawler_image=settings.crawler_image,
            crawler_output_settings=get_crawler_es_settings(settings=settings),
            es_index_prefix=settings.es_index_prefix,
        )
        searcher_settings = SearcherSettings(
            es_index_prefix=settings.es_index_prefix,
        )

        # Initialize Clients
        es_client_instance: AsyncElasticsearch = create_es_client(settings=settings)
        docker_client_instance: aiodocker.Docker = aiodocker.Docker()
        context: Optional[AppContext] = None

        # Initialize Components
        crawler_instance = Crawler(
            docker_client=docker_client_instance,
            settings=crawler_settings,
        )
        searcher_instance = Searcher(
            es_client=es_client_instance,
            settings=searcher_settings,
        )

        # 5. Create AppContext
        context = AppContext(
            crawler=crawler_instance,
            searcher=searcher_instance,
            es_client=es_client_instance,
            docker_client=docker_client_instance,
        )

        if not await es_client_instance.ping():
            raise RuntimeError("Elasticsearch connection failed post-initialization.")

        await es_client_instance.indices.put_index_template(
            name="es_doc_manager_mcp",
            **(
                generate_index_template(
                    pipeline_name=settings.es_pipeline,
                    index_pattern=settings.es_index_prefix + "-*",
                )
            ),  # Assuming index pattern is set to settings.es_index_prefix)
        )

        crawler = context.crawler
        searcher = context.searcher
        docker_client = context.docker_client

        await update_dynamic_resources()

        logger.info("yielding to mcp server")

        yield context

    except Exception as startup_error:
        logger.critical(
            f"Application startup failed critically: {startup_error}", exc_info=True
        )
        raise

    finally:
        logger.info("Executing application shutdown sequence...")
        if es_client_instance:
            try:
                logger.info("Closing Elasticsearch client...")
                await es_client_instance.close()
                logger.info("Elasticsearch client closed.")
            except Exception as e:
                logger.error(
                    f"Error closing Elasticsearch client during shutdown: {e}",
                    exc_info=True,
                )

        if docker_client_instance:
            try:
                logger.info("Closing Docker client (aiodocker)...")
                await docker_client_instance.close()
                logger.info("Docker client (aiodocker) closed.")
            except Exception as e:
                logger.error(
                    f"Error closing Docker client (aiodocker) during shutdown: {e}",
                    exc_info=True,
                )

        logger.info("Shutdown sequence complete.")


# endregion Lifespan

# --- Initialize FastMCP Server ---
mcp = fastmcp.FastMCP(
    "esdocmanagermcp",
    transport=mcp_transport_setting,
    lifespan=app_lifespan,
)
logger.info("FastMCP server instance created, running %s.", mcp_transport_setting)
# endregion Globals


@mcp.prompt()
async def list_documentation_indices() -> str:
    """Provides guidance on how to use the 'list_doc_indices' tool to see available documentation indices (which correspond to searchable resources)."""
    return "To see which documentation sets have been crawled and are available for searching, use the 'list_doc_indices' tool."


@mcp.prompt()
async def search_documentation_prompt(query: str) -> str:
    """Provides guidance on how to search crawled documentation using the available dynamic resources (e.g., 'Search: elastic-docs')."""
    logger.info(
        f"Prompt received: Guidance for searching documentation (example query: '{query}')."
    )
    indices = await searcher.list_doc_indices()

    guidance = (
        "To search crawled documentation, use the dynamic resources provided by the server. "
        "Searching simply entails entering in plain text what you're looking for. "
        "These resources typically look like 'search_<documentation_suffix>'.\n\n"
        "You can see the available documentation sets by using the 'list_doc_indices' tool.\n"
        f"{', '.join(indices)}"
    )
    return guidance


@mcp.tool()
async def search_documentation(index_name: str, query: str) -> dict:
    """
    Performs a search query against a specified documentation index using ELSER.

    Args:
        index_name: The name of the Elasticsearch index to search.
        query: The search query string.

    Returns:
        A dictionary containing search results.
    """
    logger.info(
        f"Tool Shim: Received search request for index '{index_name}' with query '{query}'."
    )

    search_results = await searcher.search_docs(index_name=index_name, query=query)
    return {"search_results": search_results}


@mcp.prompt(
    description="Provides guidance on how to use the 'crawl_domain' tool to crawl a website and index its documentation into Elasticsearch."
)
async def crawl_website_documentation(
    url,
) -> str:
    """Provides guidance on using the 'crawl_domain' tool."""
    logger.info(
        f"Prompt received: Guidance for crawl_domain tool url: {url}."
    )

    # Extract domain from the URL, use url_parse to get the netloc, keep the www and scheme but nothing after the tld
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    scheme = parsed_url.scheme + "://"
    seed_url = url
    # the filter pattern is normally the second last part of the path
    # e.g., https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html -> https://www.elastic.co/guide/en/elasticsearch/reference/current/
    path_components = parsed_url.path.split("/")
    filter_pattern = "/".join(
        path_components[: len(path_components) - 1]
    ) if len(path_components) >= 2 else parsed_url.path
    
    # take the domain and filtered_path, and convert 
    #www_elastic_co.guide_en_elasticsearch_reference_current
    recommended_index_suffix = f"{domain.replace('.', '_')}.{'_'.join(path_components[1:-1])}"

    guidance = (
        "To crawl a website and index its documentation, use the 'crawl_domain' tool. "
        "This tool runs the Elastic web crawler in a Docker container.\n\n"
        "Required parameters:\n"
        f"  - domain: The primary domain name (e.g., '{scheme + "://" + domain or 'https://www.example.com'}'). Must include scheme. Cannot include a path\n"
        f"  - seed_url: The starting URL for the crawl (e.g., '{seed_url or 'https://www.example.com/docs/index.html'}').\n"
        f"  - filter_pattern: A URL prefix the crawler should stay within (e.g., '{filter_pattern or '/docs/'}').\n"
        f"  - output_index_suffix: A suffix added to '{searcher.settings.es_index_prefix}-' to create the final index name (e.g., '{recommended_index_suffix or 'my-docs'}' results in '{searcher.settings.es_index_prefix}-{recommended_index_suffix or 'my-docs'}').\n\n"
        "The tool will start the crawl in the background and return a message with the container ID.\n"
        "Use 'list_crawls', 'get_crawl_status', and 'get_crawl_logs' to monitor progress.\n"
        "Based on the url you provided me, you should run:\n"
        f"  crawl_domain(domain='{domain}', seed_url='{seed_url}', filter_pattern='{filter_pattern}', output_index_suffix='{recommended_index_suffix}')\n\n"
    )
    return guidance


# endregion Prompts


# region Crawler
@mcp.tool()
async def pull_crawler_image() -> str:
    """
    Pulls the configured crawler Docker image ('crawler_image' setting) if not present locally.
    """
    logger.info("Tool Shim: Received request to pull crawler image.")
    
    await crawler.pull_crawler_image()

    return f"Image '{crawler.settings.crawler_image}' is available locally or was pulled successfully."


@mcp.tool()
async def crawl_domain(
    domain: str, seed_url: str, filter_pattern: str, output_index_suffix: str
) -> str:
    """
    Starts crawling a website using the configured Elastic crawler Docker image,
    indexing content into a specified Elasticsearch index suffix. Returns the container ID.

    Args:
        domain: The primary domain name (e.g., https://www.elastic.co). Used for config generation.
        seed_url: The starting URL for the crawl. https://www.elastic.co/guide/en/index.html
        filter_pattern: URL prefix pattern to restrict the crawl (e.g., /guide/en/).
        output_index_suffix: Suffix to append to the default prefix (e.g., 'elastic_co.guide_en_index').
    """
    logger.info(
        f"Tool Shim: Received crawl request for domain '{domain}', suffix '{output_index_suffix}'"
    )

    container_id = await crawler.crawl_domain(
        domain=domain,
        seed_url=seed_url,
        filter_pattern=filter_pattern,
        output_index_suffix=output_index_suffix,
    )

    return f"Crawl started for domain '{domain}'. Container ID: {container_id}"


@mcp.tool()
async def list_crawls() -> str:
    """
    Lists currently running or recently completed crawl containers managed by this server.
    """
    logger.info("Tool Shim: Received request to list crawls.")
    
    containers: List[Dict[str, Any]] = await crawler.list_crawls()

    if not containers:
        return "No active or recent crawl containers found."

    formatted_list = ["Managed Crawl Containers:"]
    for container in containers:
        c_id = container.get("id", "N/A")[:12]
        c_name = container.get("names", ["N/A"])[0].lstrip("/")
        c_state = container.get("state", "N/A")
        c_status = container.get("status", "N/A")
        c_domain = container.get("labels", {}).get(crawler.DOMAIN_LABEL, "N/A")
        c_completed = True if c_status.startswith("Exited") else False
        c_errored = True if c_completed and not c_status.startswith("Exited (0)") else False
        c_succeeded = not c_errored
        formatted_list.append(
            f"  - Domain: {c_domain}, Done: {c_completed}, Errored: {c_errored}, ID: {c_id}, Name: {c_name}, , State: {c_state}, Status: {c_status}"
        )

    return "\n".join(formatted_list)


@mcp.tool()
async def get_crawl_status(container_id: str) -> str:
    """
    Gets the detailed status of a specific crawl container by its ID.

    Args:
        container_id: The full or short ID of the container.
    """
    logger.info(
        f"Tool Shim: Received request for status of container '{container_id[:12]}'."
    )
    
    status_data: Dict[str, Any] = await crawler.get_crawl_status(container_id)

    formatted_status = [
        f"Status for Container ID: {status_data.get('short_id', 'N/A')}"
    ]
    for key, value in status_data.items():
        formatted_status.append(f"  - {key.replace('_', ' ').title()}: {value}")

    return "\n".join(formatted_status)


@mcp.tool()
async def get_crawl_logs(container_id: str, tail: str = "all") -> str:
    """
    Gets the logs from a specific crawl container.

    Args:
        container_id: The full or short ID of the container.
        tail: Number of lines to show from the end of the logs (e.g., "100", default: "all").
    """
    logger.info(
        f"Tool Shim: Received request for logs of container '{container_id[:12]}' (tail={tail})."
    )

    logs: str = await crawler.get_crawl_logs(container_id, tail)

    return (
        logs
        if logs
        else f"No logs found or container '{container_id[:12]}' does not exist."
    )


@mcp.tool()
async def stop_crawl(container_id: str) -> str:
    """
    Stops and removes a specific crawl container by its ID.

    Args:
        container_id: The full or short ID of the container.
    """
    logger.info(f"Tool Shim: Received request to stop container '{container_id[:12]}'.")
    
    await crawler.stop_crawl(container_id)

    return f"Container '{container_id[:12]}' stopped and removed successfully."


@mcp.tool()
async def remove_completed_crawls() -> Dict[str, Any]:
    """
    Removes all completed (status 'exited') crawl containers managed by this server.
    Returns a summary dictionary with 'removed_count' and 'errors'.
    """
    logger.info("Tool Shim: Received request to remove completed crawls.")
    result = await crawler.remove_completed_crawls()
    return result

# endregion Crawler

# region Searcher
@mcp.tool()
async def list_doc_indices() -> list[str]:
    """
    Lists available Elasticsearch documentation indices managed by this server
    (matching the configured prefix).
    """
    logger.info("Tool Shim: Received request to list documentation indices.")

    indices: List[str] = await searcher.list_doc_indices()
    return indices


async def update_dynamic_resources():
    """
    Updates MCP dynamic resources based on available documentation indices.
    Creates a resource for each index, allowing users to search within it.
    """
    logger.info("Updating dynamic search resources...")

    index_names: list[str] = await list_doc_indices()  # Wrapped call

    if not index_names:
        logger.info("No documentation indices found, no resources to update.")
        # Consider removing existing resources if desired? For now, just don't add.
        return

    for index_name in index_names:
        # Define the actual handler function for this specific index
        # This closure captures the current index_name

        # remove the index prefix from the index_name for the uri
        # This allows for a cleaner URI
        prefix = searcher.settings.es_index_prefix
        name_without_prefix = (
            index_name.split(prefix + "-")[1]
            if index_name.startswith(prefix + "-")
            else index_name
        )

        async def dynamic_search_wrapper(
            query: str, _index=index_name
        ) -> Dict[str, Any]:  # Changed signature
            search_results = await search_documentation(index_name=_index, query=query)

            return {"search_results": search_results}

        uri = f"docs://{name_without_prefix}/{{query}}"
        name = f"docs_{name_without_prefix}"
        description = "Search {name_without_prefix} for documentation."
        mime_type = "application/json"

        logger.info(
            "Registering dynamic documentation resource template for index: %s with URI: %s",
            index_name,
            uri,
        )

        @mcp.resource(
            uri=uri,
            name=name,  # Unique name for each index to avoid conflicts
            description=description,
            mime_type=mime_type,  # Ensure consistent MIME type for all dynamic resources
        )
        async def docs_resource(query: str):
            """
            Wrapper function to call the dynamic resource handler.
            This allows the MCP to route requests to the appropriate handler.
            """
            # Call the handler function with the index name and query
            return await dynamic_search_wrapper(_index=index_name, query=query)

    logger.info("Finished updating dynamic search resources.")


# endregion Searcher

# region Main Execution
if __name__ == "__main__":
    logger.info("Starting MCP server...")
    mcp.run(transport=mcp_transport_setting)
    logger.info("MCP server stopped.")
# endregion Main Execution
