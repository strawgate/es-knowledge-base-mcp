import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional, AsyncIterator, Dict, Any, List
import aiodocker
from elasticsearch import (
    AsyncElasticsearch,
)
from pydantic import ValidationError

import mcp.server.fastmcp as fastmcp

from esdocmanagermcp.components.shared import (
    AppSettings,
    TransportSettings,
    create_es_client,
    generate_index_template,
    format_search_results_plain_text,
    get_crawler_es_settings,
)
from esdocmanagermcp.components.crawl import Crawler, CrawlerSettings
from esdocmanagermcp.components.search import Searcher, SearcherSettings
from esdocmanagermcp.components.indices import IndicesManager

logging.basicConfig(
    filename='esdocmanagermcp.log', level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# disable pydantic validation error logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


crawler: Optional[Crawler] = None
searcher: Optional[Searcher] = None
indices_manager: Optional[IndicesManager] = None

# --- Load Minimal Settings for MCP Initialization ---
try:
    bootstrap_settings = TransportSettings()
    mcp_transport_setting = bootstrap_settings.mcp_transport
    logger.info(f"Using MCP transport: {mcp_transport_setting}")
except ValidationError as e:
    logger.error(f"Initial configuration error loading MCP transport: {e}")
    raise RuntimeError(f"Failed to load initial MCP transport configuration: {e}")
except Exception as e:
    logger.error(f"Unexpected error loading initial MCP transport configuration: {e}")
    raise RuntimeError(f"Unexpected error during initial configuration loading: {e}")


# region Lifespan
@dataclass
class AppContext:
    """Holds initialized components for the application."""

    crawler: Crawler
    searcher: Searcher
    es_client: AsyncElasticsearch
    docker_client: aiodocker.Docker
    indices_manager: IndicesManager


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
    global crawler, searcher, docker_client, indices_manager

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
        indices_manager_instance = IndicesManager(es_client=es_client_instance)

        # 5. Create AppContext
        context = AppContext(
            crawler=crawler_instance,
            searcher=searcher_instance,
            es_client=es_client_instance,
            docker_client=docker_client_instance,
            indices_manager=indices_manager_instance,
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
        indices_manager = context.indices_manager

        # await update_dynamic_resources()

        logger.info("yielding to mcp server")

        yield context

    except Exception as startup_error:
        raise RuntimeError(f"Application startup failed: {startup_error}") from startup_error

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
mcp = fastmcp.FastMCP("esdocmanagermcp", transport=mcp_transport_setting, lifespan=app_lifespan, log_level="ERROR")
logger.info("FastMCP server instance created, running %s.", mcp_transport_setting)
# endregion Globals


# region Indices Tools
@mcp.tool()
async def get_documentation_types(include_doc_count: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieve the list of documentation available from the MCP Server. Only needed if searching via search_all_documentation does not
    provide the desired results. Check this list to see what specific indices are available.

    Args:
        include_doc_count: Whether to include the document count in the response.
        include_creation_date: Whether to include the creation date in the response.
    """

    results = await indices_manager.list_elasticsearch_indices()

    # Sort alphabetically
    results.sort(key=lambda x: x["index"])

    if not include_doc_count:
        return "\n".join([result["index"].split(searcher.settings.es_index_prefix + "-")[1] for result in results])

    return [
        {
            "type": result["index"].split(searcher.settings.es_index_prefix + "-")[1],
            # "creation_date": result["creation.date.string"] if include_creation_date else None,
            "documents": result["docs.count"] if include_doc_count else None,
        }
        for result in results
    ]


@mcp.tool()
async def delete_documentation(type: str) -> str:
    """
    Deletes specific documentation from Elasticsearch.

    Args:
        type: The type name of the documentation index to delete (e.g., 'elastic_co.guide_en_index'). Wildcards are not allows.
    """
    full_index_name = f"{searcher.settings.es_index_prefix}-{type}"

    if "*" in type:
        raise ValueError("Wildcard '*' is not allowed in the type name.")

    logger.info(f"Tool: Received request to delete documentation index type '{type}' (full name: '{full_index_name}')")

    success = await indices_manager.delete_elasticsearch_index(full_index_name)

    if success:
        return f"Documentation index type '{type}' (index: {full_index_name}) was deleted or did not exist."
    else:
        return f"Error deleting documentation index type '{type}'. Check server logs for details."


# endregion Indices


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
async def crawl_domains(
    seed_pages: str | List[str] | None = None, seed_dirs: str | List[str] | None = None
) -> List[Dict[str, Any]]:
    """
    Starts one or many crawl jobs based on lists of seed pages and/or directories.

    Args:
    - `seed_pages`: Each URL in this list will be checked for content. When crawling, we'll follow links which match everything
      after the last `/` of the seed_page provided. Useful when your seed_url is a markdown, html or other file and you want sibling pages
      to be included. For example if https://github.com/microsoft/vscode/blob/main/README.md is provided, all pages starting with
      `https://github.com/microsoft/vscode/blob/main/` will be crawled.
    - `seed_dirs`: Each URL in this list will be checked for content. When crawling, we'll only follow links to child pages of the seed_dir
      provided. That is, we'll only follow links which start with the seed_dir url provided. For example if `https://github.com/microsoft/vscode/` is provided, only pages
      starting with `https://github.com/microsoft/vscode` will be crawled. Useful when removing everything after the
      last `/` would result in scraping hundreds of thousands of pages, i.e. `https://github.com/microsoft` would scrape all of github.

    Warnings:
    - Avoid crawling the root of a Github repository, crawl /blob/main/ or /tree/main/ instead unless you want all issues, discussions, PRs, commits, etc.
        if you do want to crawl those, crawl them as their own seed_dirs so you can update/prune without re-crawling everything again.
    - Avoid crawling large websites without a specific seed page or directory, as it may result in excessive data scraping.

    Returns:
        A list of dictionaries, each containing the result for a processed seed URL,
        including 'seed_url', 'scope_type', 'start_status' ('success' or 'error'),
        'container_id' (on success), or 'message' (on error).
    """

    # Ensure seed_pages and seed_dirs are lists
    seed_pages = [seed_pages] if isinstance(seed_pages, str) else seed_pages or []
    seed_dirs = [seed_dirs] if isinstance(seed_dirs, str) else seed_dirs or []

    logger.info(f"Tool: Received crawl_domains request. Pages: {len(seed_pages)}, Dirs: {len(seed_dirs)}.")

    crawler_jobs_to_start = []

    results = []

    for page_url in seed_pages:
        if page_url == "":
            continue
        logger.debug(f"Processing seed page: {page_url}")

        try:
            crawl_params = crawler.derive_crawl_params_from_url(page_url)
            crawler_jobs_to_start.append(crawl_params)
        except Exception as e:  # Blanket exception for now, we can be more specific later
            logger.error(f"Error processing seed page {page_url}: {e}", exc_info=True)
            results.append({"seed_url": page_url, "success": False, "message": str(e)})

    for dir_url in seed_dirs:
        if dir_url == "":
            continue
        logger.debug(f"Processing seed directory: {dir_url}")

        try:
            crawl_params = crawler.derive_crawl_params_from_dir(dir_url)
            crawler_jobs_to_start.append(crawl_params)
        except Exception as e:  # Blanket exception for now, we can be more specific later
            logger.error(f"Error processing seed directory {dir_url}: {e}", exc_info=True)
            results.append({"seed_url": dir_url, "success": False, "message": str(e)})

    for params in crawler_jobs_to_start:
        domain = params["domain"]
        page_url = params["page_url"]
        filter_pattern = params["filter_pattern"]
        output_index_suffix = params["output_index_suffix"]

        logger.debug(f"Derived parameters for {page_url}: {params}")

        container_id = await crawler.crawl_domain(
            domain=domain, seed_url=page_url, filter_pattern=filter_pattern, output_index_suffix=output_index_suffix
        )

        logger.info(f"Successfully initiated crawl for page {page_url}, container ID: {container_id[:12]}")

        results.append({"seed_url": page_url, "success": True, "container_id": container_id})

    logger.info(f"Finished crawl_domains processing. Results count: {len(results)}")
    return results


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
        # c_succeeded = not c_errored
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
    logger.info(f"Tool Shim: Received request for status of container '{container_id[:12]}'.")

    status_data: Dict[str, Any] = await crawler.get_crawl_status(container_id)

    formatted_status = [f"Status for Container ID: {status_data.get('short_id', 'N/A')}"]
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
    logger.info(f"Tool Shim: Received request for logs of container '{container_id[:12]}' (tail={tail}).")

    logs: str = await crawler.get_crawl_logs(container_id, tail)

    return logs if logs else f"No logs found or container '{container_id[:12]}' does not exist."


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
async def search_specific_documentation(types: str, query: str) -> dict:
    """
    Performs a search query against a specified documentation index. Gather the list of types from the get_documentation_types tool
    and use wildcards like `*python*` or `*pytest*,*python*`. Target as many types as will be useful. We use vector search and scoring
    to return the most useful hits so make sure your query describes what you're looking for!

    Args:
        type: The documentation types to query, can be comma separated and include trailing or leading wildcards.
        question: What are you searching for or what problem are you trying to solve in plain english?

    Returns:
        A dictionary containing search results.
    """
    logger.info(f"Tool: Received search request for types '{types}' with query '{query}'.")

    search_results = await searcher.documentation_search(type=types, query=query)
    return {"search_results": search_results}


@mcp.tool()
async def search_all_documentation(question: str, results: int = 8) -> dict:
    """
    Performs a vector search query against all documentation indices. We use vector search and scoring
    to return the most useful hits so make sure your query describes what you're looking for! Access to documentation significantly
    improves your responses by making detailed documentation available that is relevant to what you're working on.

    Args:
        question: What are you searching for or what problem are you trying to solve in plain english?
        results: How many answers to request (defaults to 8). Do not provide unless your initial query does not answer your question.

    Returns:
        A dictionary containing search results.

    """
    logger.info(f"Tool: Received search request for all docs with query '{question}'.")

    search_results = await searcher.documentation_search(type="*", query=question, results=results)

    return format_search_results_plain_text(search_results)


@mcp.tool()
async def get_document_by_url(doc_url: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the full content of a specific document identified by its URL. Useful when you find a fragment via search
    that's useful but you want to see the whole document.

    Args:
        doc_url: The exact URL of the document to retrieve from the documentation store
    """
    logger.info(f"Tool: Received get_document_by_url request for URL '{doc_url}''.")

    query_part = {"term": {"url.keyword": doc_url}}

    search_result = await searcher.get_document_by_query(query_body=query_part, types="*")

    return format_search_results_plain_text(search_results=search_result)


@mcp.tool()
async def get_document_by_title(doc_title: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the full content of a document identified by its title. Useful when you find a fragment via search
    that's useful but you want to see the whole document.

    Args:
        doc_title: The title of the document to retrieve.
    """
    logger.info(f"Tool: Received get_document_by_title request for title '{doc_title}'.")

    query_part = {"match": {"title": doc_title}}

    search_result = await searcher.get_document_by_query(query_body=query_part, types="*")

    return format_search_results_plain_text(search_results=search_result)


# endregion Searcher

# region Main Execution


def main():
    """Main entry point to run the MCP server."""
    logger.info("Starting MCP server...")
    mcp.run(mcp_transport_setting)
    logger.info("MCP server stopped.")


if __name__ == "__main__":
    main()

# endregion Main Execution
