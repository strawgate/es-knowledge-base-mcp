import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlparse
import anyio
import elasticsearch
import mcp.server.fastmcp as fastmcp
from mcp.server.fastmcp.resources import Resource
from mcp.server.fastmcp.resources.templates import ResourceTemplate # Added import
from mcp.server.fastmcp.resources.types import FunctionResource
import os
import pathlib
import yaml
import datetime
import logging
import docker
from docker.errors import APIError, ImageNotFound, ContainerError
import functools # Added for partial
import json # Added for potential JSON formatting/parsing if needed later
from typing import AsyncIterator, Optional, List, Dict, Any, Tuple # Added Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuration from Environment Variables ---
# Mandatory
try:
    ES_HOST = os.environ["ES_HOST"]
    ES_PORT = os.environ["ES_PORT"]
    ES_PIPELINE = os.environ["ES_PIPELINE"]  # Ingest pipeline name
except KeyError as e:
    raise RuntimeError(f"Missing required environment variable: {e}") from e

# Authentication - Prioritize API Key, fallback to Basic Auth
ES_API_KEY = os.environ.get("ES_API_KEY")
ES_USERNAME = os.environ.get("ES_USERNAME")
ES_PASSWORD = os.environ.get("ES_PASSWORD")

auth_method = None
if ES_API_KEY:
    auth_method = "api_key"
    logger.info("Using API Key authentication for Elasticsearch.")
elif ES_USERNAME and ES_PASSWORD:
    auth_method = "basic_auth"
    logger.info("Using Basic Authentication (username/password) for Elasticsearch.")
else:
    raise RuntimeError(
        "Missing Elasticsearch authentication environment variables. "
        "Set either ES_API_KEY or both ES_USERNAME and ES_PASSWORD."
    )


# --- Constants ---
TEMPLATE_NAME = "docsmcp-template"
DEFAULT_INDEX_PREFIX = "docsmcp"
CRAWLER_CONFIG_DIR_DOCKER = "/app/config/domains"  # Path inside the Docker container where temp configs will be mounted/placed

# --- Initialize Async Elasticsearch Client ---
try:
    es_client_args = {
        "hosts": [{"host": ES_HOST, "port": int(ES_PORT), "scheme": "https"}],
        "request_timeout": 180,
        "http_compress": True
    }
    if auth_method == "api_key":
        es_client_args["api_key"] = ES_API_KEY
    elif auth_method == "basic_auth":
        es_client_args["basic_auth"] = (ES_USERNAME, ES_PASSWORD)

    es_client = elasticsearch.AsyncElasticsearch(**es_client_args)
    logger.info(f"Elasticsearch client initialized using {auth_method}.")
except ValueError as e:
    # Catch specific error for port conversion
    if "invalid literal for int()" in str(e):
        raise RuntimeError(
            f"Invalid ES_PORT value: '{ES_PORT}'. Must be an integer."
        ) from e
    else:
        raise RuntimeError(
            f"Configuration error initializing Elasticsearch client: {e}"
        ) from e
except Exception as e:
    raise RuntimeError(f"Failed to initialize Elasticsearch client: {e}") from e

@dataclass
class AppContext:
    es_client: elasticsearch.AsyncElasticsearch


@asynccontextmanager
async def app_lifespan(server: fastmcp) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context"""
    # --- Startup Logic ---
    logger.info("Executing startup sequence via lifespan...")
    try:
        logger.info("Pinging Elasticsearch...")
        if not await es_client.ping():
            logger.error(
                "ERROR: Could not ping Elasticsearch. Check connection and credentials. Dynamic resources will not be registered."
            )
            # Decide whether to raise and stop server start
            # raise RuntimeError("Failed to ping Elasticsearch")
        else:
            logger.info("Successfully connected to Elasticsearch.")
            # Ensure index template exists before registering resources
            logger.info("Setting up index template...")
            await _internal_setup_index_template() # Ensure this runs first
            logger.info("Index template setup complete (or already exists).")

            # Register dynamic resources based on existing indices
            logger.info("Updating dynamic documentation resources...")
            await _update_dynamic_doc_resources() # Call the new registration function
            logger.info("Dynamic documentation resource update complete.")

    except elasticsearch.AuthenticationException:
        logger.error(
            "ERROR: Elasticsearch authentication failed. Check ES_USERNAME/ES_PASSWORD."
        )
        # raise RuntimeError("Elasticsearch authentication failed")
    except elasticsearch.ConnectionError as e:
        logger.error(
            f"ERROR: Could not connect to Elasticsearch at {ES_HOST}:{ES_PORT}. Error: {e}"
        )
        # raise RuntimeError("Failed to connect to Elasticsearch") from e
    except Exception:
        logger.exception("ERROR: Unexpected error during Elasticsearch startup check.")
        # raise RuntimeError("Unexpected startup error") from e

    try:
        yield AppContext(es_client=es_client) # Yield the context
    finally:
        # --- Shutdown Logic ---
        logger.info("Executing shutdown sequence via lifespan...")
        if es_client:
            try:
                await es_client.close()
                logger.info("Elasticsearch client closed.")
            except Exception:
                logger.exception("Error closing Elasticsearch client during shutdown.")
# --- Main Execution Block ---

# if __name__ == "__main__":
#     # Using anyio.run for startup/shutdown management outside of mcp.run()
#     # as FastMCP might not have built-in lifespan events yet.

# --- Initialize FastMCP Server ---
mcp = fastmcp.FastMCP("elasticsearch-documentation-manager-mcp", lifespan=app_lifespan)
logger.info("FastMCP server initialized.")
# --- Tool Handlers ---


@mcp.tool()  # Internal tool, not directly user-facing via prompt
async def _internal_setup_index_template() -> str:
    """
    Internal tool to create or update the Elasticsearch index template.

    Ensures the template 'docsmcp-template' exists with standard mappings
    (title, url, content, crawled_at, ml.inference.*) and settings
    (default_pipeline from ES_PIPELINE env var) for indices matching
    'docsmcp-*'.
    """
    logger.info(f"Internal: Setting up index template: {TEMPLATE_NAME}")
    template_body = {
        "index_patterns": [
            f"{DEFAULT_INDEX_PREFIX}-*",
        ],
        "template": {
            "settings": {
                "index": {
                    "default_pipeline": ES_PIPELINE,  # Use the configured ingest pipeline
                    "number_of_shards": "1",
                }
            },
            "mappings": {
                "dynamic_templates": [],
                "properties": {
                    "body": {
                        "type": "semantic_text",
                        "inference_id": ".elser-2-elasticsearch",
                        "model_settings": {
                            "service": "elasticsearch",
                            "task_type": "sparse_embedding",
                        },
                    },
                    "headings": {
                        "type": "semantic_text",
                        "inference_id": ".elser-2-elasticsearch",
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
        "priority": 500,  # High priority to override defaults
        "_meta": {
            "description": "Index template for crawled documentation managed by MCP",
            "created_by": "elasticsearch-documentation-manager-mcp",
        },
    }
    try:
        response = await es_client.indices.put_index_template(
            name=TEMPLATE_NAME,
            index_patterns=template_body[
                "index_patterns"
            ],  # Pass index_patterns at top level for >= 8.0
            template=template_body["template"],
            priority=template_body["priority"],
            meta=template_body["_meta"],
            # body=template_body, # Deprecated way for older versions
            ignore=[400],  # Ignore if template already exists (400 Bad Request)
        )
        logger.info(f"Put index template response: {response}")
        if response.get("acknowledged", False):
            msg = f"Index template '{TEMPLATE_NAME}' created or updated successfully."
            logger.info(msg)
            return msg
        else:
            # Check if it was ignored due to existing template (might not be explicit in response)
            # Let's try getting it to confirm
            try:
                await es_client.indices.get_index_template(name=TEMPLATE_NAME)
                msg = f"Index template '{TEMPLATE_NAME}' already exists."
                logger.info(msg)
                return msg
            except elasticsearch.NotFoundError:
                msg = f"Failed to create or update index template '{TEMPLATE_NAME}'. Response: {response}"
                logger.error(msg)
                return msg
            except Exception as get_err:
                msg = f"Failed to create/update template '{TEMPLATE_NAME}' and failed to verify existence. Get error: {get_err}. Put response: {response}"
                logger.error(msg)
                return msg

    except elasticsearch.ApiError as e:
        logger.error(f"Elasticsearch API Error setting up template: {e}")
        # Note: The original code had duplicate return statements here. Consolidating.
        return f"Error setting up index template: {e.message}"
    except Exception as e:
        logger.exception("Unexpected error setting up index template.")
        return f"Unexpected error setting up index template: {e}"


@mcp.prompt(
    description="Create or update the Elasticsearch index template named 'docsmcp-template'. This template defines standard mappings (title, url, content, crawled_at, ml.inference.*) and settings (default_pipeline from ES_PIPELINE env var) for indices matching 'docsmcp-*'. Use this to ensure new documentation indices have the correct structure and processing pipeline."
)
async def setup_documentation_index_template() -> str:
    """
    Ensures the standard Elasticsearch index template ('docsmcp-template')
    is created or updated.

    This template is crucial for ensuring that crawled documentation indices
    have the correct structure, mappings, and ingest pipeline settings.
    It applies to indices matching 'docsmcp-*'.

    Returns:
        A status message indicating success or failure.
    """
    logger.info("Prompt received: Setting up documentation index template.")
    try:
        result = await _internal_setup_index_template()
        # Handle potential None return if error occurred in internal function and wasn't caught
        if result is None:
            logger.error(
                "Prompt error: Internal template setup failed without explicit message."
            )
            return "Internal error during template setup."
        logger.info(f"Prompt finished: Setup template result: {result}")
        return result
    except Exception as e:
        logger.exception("Prompt error: Unexpected error during template setup.")
        return f"Unexpected error during template setup: {e}"


@mcp.tool()  # Internal tool, not directly user-facing via prompt
async def _internal_list_doc_indices(
    index_prefix: Optional[str] = DEFAULT_INDEX_PREFIX,
) -> List[str]:
    """
    Internal tool to list Elasticsearch indices matching a prefix.

    Args:
        index_prefix: The prefix to filter indices by (defaults to 'docsmcp').

    Returns:
        A list of matching index names, or an empty list on error.
    """
    fastmcp.server.logger
    search_pattern = f"{index_prefix}-*" if index_prefix else "*"
    logger.info(f"Internal: Listing indices with pattern: {search_pattern}")
    try:
        response = await es_client.cat.indices(
            index=search_pattern, format="json", h="index", s="index:asc"
        )
        indices = [item["index"] for item in response if "index" in item]
        logger.info(f"Found indices: {indices}")
        return indices
    except elasticsearch.ApiError as e:
        logger.error(f"Elasticsearch API Error listing indices: {e}")
        # Return empty list or raise? Returning empty list might be safer for client.
        return []
    except Exception:
        logger.exception("Unexpected error listing indices.")
        # Note: Original code was missing return here. Adding it.
        return []


@mcp.prompt(
    description="List the names of Elasticsearch indices related to crawled documentation. You can optionally provide an 'index_prefix' (defaults to 'docsmcp') to filter the indices (e.g., 'docsmcp-elastic-co'). Returns a list of index names."
)
async def list_documentation_indices(
    index_prefix: Optional[str] = DEFAULT_INDEX_PREFIX,
) -> List[str]:
    """
    Lists the names of Elasticsearch indices related to crawled documentation.

    Allows filtering by an optional index prefix.

    Args:
        index_prefix: The prefix to filter indices by (e.g., 'docsmcp-elastic-co').
                      Defaults to 'docsmcp'.

    Returns:
        A list of matching index names. Returns an empty list if none are found
        or an error occurs.
    """
    logger.info(
        f"Prompt received: Listing documentation indices (prefix: {index_prefix})."
    )
    try:
        indices = await _internal_list_doc_indices(index_prefix=index_prefix)
        logger.info(f"Prompt finished: Found {len(indices)} indices.")
        return indices
    except Exception as e:
        logger.exception("Prompt error: Unexpected error listing indices.")
        # Return empty list as per internal function's behavior on error
        return []


@mcp.tool()  # Internal tool, not directly user-facing via prompt
async def _internal_search_docs(
    query: str, index_prefix: Optional[str] = DEFAULT_INDEX_PREFIX
) -> List[Dict[str, Any]]:
    """
    Internal tool to perform an ELSER search on documentation indices.

    Args:
        query: The search query string.
        index_prefix: The prefix for indices to search (defaults to 'docsmcp').

    Returns:
        A list of raw Elasticsearch hit dictionaries, including '_source'
        and 'highlight', or a list containing an error dictionary on failure.
    """
    search_pattern = f"{index_prefix}*" if index_prefix else "*"
    logger.info(
        f"Internal: Searching indices '{search_pattern}' for query: '{query}' using ELSER"
    )

    # Basic ELSER Query Structure - Assumes model 'elser_model_1' is deployed
    # TODO: Make model name configurable?
    search_body = {
        "query": {
            "semantic": {
                "field": "body",
                "query": query,
            }
        },
        "_source": ["title", "url", "crawled_at"],  # Return specific fields
        "size": 10,  # Limit results
        "highlight": {  # Add highlighting on the body field
            "fields": {"body": {}}
        }
    }

    try:
        response = await es_client.search(
            index=search_pattern,
            **search_body,
            ignore=[404],  # Ignore if no indices match the pattern
        )
        hits = response.get("hits", {}).get("hits", [])
        logger.info(f"Search returned {len(hits)} hits.")
        # Optionally log the hits themselves if debugging is needed (can be verbose)
        # logger.debug(f"Search hits: {hits}")
        return hits
    except elasticsearch.NotFoundError:
        logger.warning(
            f"Search failed: No indices found matching pattern '{search_pattern}'."
        )
        return []
    except elasticsearch.ApiError as e:
        # Specifically check for errors related to ELSER model or field missing
        if "No text expansion model" in str(e) or "model_id" in str(e):
            logger.error(
                f"ELSER search error: Model '.elser_model_1' might not be deployed or field 'ml.inference.content_expanded.tokens' is missing. Error: {e}"
            )
            # Consider returning a specific error message or structure
            return [{"error": "ELSER model/field issue", "details": str(e)}]
        logger.error(f"Elasticsearch API Error searching documents: {e}")
        return [
            {"error": "Search API error", "details": str(e)}
        ]  # Return error structure
    except Exception as e:
        logger.exception("Unexpected error searching documents.")
        return [
            {"error": "Unexpected search error", "details": str(e)}
        ]  # Return error structure


@mcp.prompt(
    description="Search crawled documentation using Elastic Learned Sparse Encoder (ELSER). Provide a 'query' string. Optionally specify an 'index_prefix' (defaults to 'docsmcp') to search within specific indices (e.g., 'docsmcp-elastic-co'). Requires the '.elser_model_1' model to be deployed in Elasticsearch. Returns a list of relevant text snippets (highlights) from the matching documents."
)
async def search_documentation(
    query: str, index_prefix: Optional[str] = DEFAULT_INDEX_PREFIX
) -> List[Tuple[str, str, List[str]]]: # Updated return type annotation
    """
    Searches documentation indices using ELSER and returns relevant chunks
    grouped by document title and URL.

    Args:
        query: The search query string.
        index_prefix: The prefix for indices to search (defaults to 'docsmcp').

    Returns:
        A list of tuples with the format (title, url, [chunks]) for each
        matching document. Returns an empty list if no results or an error occurs.
    """
    logger.info(
        f"Prompt received: Searching documentation for '{query}' (prefix: {index_prefix})."
    )
    results: List[Tuple[str, str, List[str]]] = [] # Initialize results list
    try:
        # Call the internal tool to get raw hits
        raw_hits = await _internal_search_docs(query=query, index_prefix=index_prefix)

        # Check if the internal tool returned an error structure
        if raw_hits and isinstance(raw_hits[0], dict) and "error" in raw_hits[0]:
            error_details = raw_hits[0].get("details", "Unknown error")
            logger.error(
                f"Prompt error: Internal search failed: {raw_hits[0]['error']} - {error_details}"
            )
            return [] # Return empty list on internal error

        # Process hits to extract title, url, and chunks
        for hit in raw_hits:
            source = hit.get("_source", {})
            title = source.get("title", "Unknown Title")
            url = source.get("url", "Unknown URL")
            chunks = []
            if "highlight" in hit and "body" in hit["highlight"]:
                # highlight['body'] is expected to be a list of strings (chunks)
                chunks = hit["highlight"]["body"]
            else:
                logger.warning(f"Hit missing highlight or body in highlight: {hit.get('_id')}")

            if chunks: # Only add if we found highlight chunks
                results.append((title, url, chunks))
            else:
                logger.debug(f"Skipping hit {hit.get('_id')} due to missing chunks.")


        logger.info(f"Prompt finished: Found {len(results)} documents with highlights.")
        return results # Return the list of tuples

    except Exception as e:
        logger.exception(
            "Prompt error: Unexpected error during documentation search."
        )
        return [] # Return empty list on unexpected errors


@mcp.tool()  # Internal tool, not directly user-facing via prompt
async def _internal_crawl_domain(
    domain: str,
    seed_url: str,
    filter: str,
    output_index_suffix: str,
    index_prefix: Optional[str] = DEFAULT_INDEX_PREFIX,
) -> str:
    """
    Internal tool to run the documentation crawler using the Docker SDK.

    Generates a temporary config file based on inputs, runs the
    'elastic/crawler' container to execute the crawl, captures logs,
    and cleans up the temporary file.

    Args:
        domain: The domain name for the crawl config (e.g., 'elastic.co').
        seed_url: The starting URL for the crawl.
        output_index_suffix: Suffix for the target Elasticsearch index.
        index_prefix: Prefix for the target Elasticsearch index (defaults to 'docsmcp').

    Returns:
        A string containing the status, logs (stdout/stderr), and exit code
        of the crawler container run.
    """
    if not domain or not seed_url or not output_index_suffix:
        raise ValueError(
            "Missing required arguments: domain, seed_url, output_index_suffix"
        )

    effective_index_prefix = index_prefix if index_prefix else DEFAULT_INDEX_PREFIX
    output_index = f"{effective_index_prefix}-{output_index_suffix}"
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    temp_config_filename = f"temp_crawl_{domain}_{timestamp}.yml"

    # --- Paths ---
    script_dir = pathlib.Path(__file__).parent.resolve()
    temp_config_path_host = script_dir / temp_config_filename
    # Path *inside* the Docker container where the crawler expects the config
    container_config_dir = CRAWLER_CONFIG_DIR_DOCKER  # e.g., "/app/config/domains"
    temp_config_path_docker = f"{container_config_dir}/{temp_config_filename}"

    logger.info(f"Internal: Initiating crawl for domain '{domain}' (seed: {seed_url})")
    logger.info(f"Internal: Output index: {output_index}")
    logger.info(f"Internal: Temp config host path: {temp_config_path_host}")
    logger.info(f"Internal: Temp config docker path: {temp_config_path_docker}")

    # crawl_rules:
    #   - policy: allow       # the policy for this rule, either: allow | deny
    #     type: begins       # the type of rule, any of: begins | ends | contains | regex
    #     pattern: https://www.w3schools.com/html/     # the pattern string for the rule
    #   - policy: deny
    #     type: regex
    #     pattern: .*

    # --- Generate YAML Config Content ---
    crawl_config = {
        "domain": domain,
        "seed_urls": [seed_url],
        "output": {
            "elasticsearch": {
                "index": output_index,
                "pipeline": ES_PIPELINE,
            }
        },
        "crawl_rules": [
            {
                "policy": "allow",
                "type": "begins",
                "pattern": filter,
            },
            {
                "policy": "deny",
                "type": "regex",
                "pattern": "*", 
            },
        ],
        "limits": {"max_depth": 5, "max_pages": 100},
        "behavior": {"respect_robots_txt": True, "delay_seconds": 1.0},
    }

    # --- Docker SDK Execution ---
    logs = ""
    return_code = -1
    status = "Failure"
    error_message = ""
    client = None

    try:
        # --- Initialize Docker Client ---
        try:
            client = docker.from_env()
            # Optionally ping the Docker daemon
            client.ping()
            logger.info("Internal: Docker client initialized successfully.")
        except Exception as docker_init_err:
            logger.error(
                f"Internal: Failed to initialize Docker client: {docker_init_err}"
            )
            return f"Error: Could not connect to Docker daemon. Is it running? Details: {docker_init_err}"

        # --- Write Temp Config File ---
        logger.debug(f"Internal: Writing temp config to {temp_config_path_host}")
        with open(temp_config_path_host, "w") as f:
            yaml.dump(crawl_config, f, default_flow_style=False)
        logger.debug("Internal: Temp config written.")

        # --- Define Container Run Parameters ---
        image_name = "elastic/crawler:latest"  # TODO: Consider making configurable
        # Command to execute inside the container
        command = ["bin/crawler", "crawl", temp_config_path_docker]
        # Mount the directory containing the temp config file (read-only)
        volumes = {
            str(temp_config_path_host.parent): {
                "bind": container_config_dir,
                "mode": "ro",
            }
        }

        logger.info(
            f"Internal: Running container '{image_name}' with command: {' '.join(command)}"
        )
        logger.debug(f"Internal: Volumes: {volumes}")

        # --- Run Container Synchronously ---
        container_logs_bytes = client.containers.run(
            image=image_name,
            command=command,
            volumes=volumes,
            auto_remove=True,  # Remove container after execution
            stdout=True,  # Capture stdout
            stderr=True,  # Capture stderr
            detach=False,  # Run in foreground (synchronously)
        )
        # If run succeeds without ContainerError, exit code is 0
        return_code = 0
        status = "Success"
        logs = container_logs_bytes.decode("utf-8", errors="replace")
        logger.info(f"Internal: Container finished with return code: {return_code}")
        logger.debug(f"Internal: Container logs:\n{logs}")

    except ImageNotFound:
        error_message = f"Error: Docker image '{image_name}' not found. Please pull it."
        logger.error(f"Internal: {error_message}")
        status = "Failure"
        return_code = -1  # Indicate image missing
    except ContainerError as e:
        # Error occurred *inside* the container
        return_code = e.exit_status
        logs = (
            e.stderr.decode("utf-8", errors="replace")
            if e.stderr
            else "No stderr captured."
        )
        error_message = f"Error: Crawler container exited with status {return_code}."
        logger.error(f"Internal: {error_message}\nContainer stderr:\n{logs}")
        status = "Failure"
    except APIError as e:
        # Docker daemon API error
        error_message = f"Error: Docker API error occurred: {e}"
        logger.error(f"Internal: {error_message}")
        status = "Failure"
        return_code = -1  # Indicate API error
    except Exception as e:
        # Other unexpected errors
        error_message = f"Error: An unexpected error occurred: {e}"
        logger.exception("Internal: Unexpected error during Docker crawl execution.")
        status = "Failure"
        return_code = -1  # Indicate unexpected error
    finally:
        # --- Cleanup Temp Config File ---
        if temp_config_path_host.exists():
            try:
                os.remove(temp_config_path_host)
                logger.debug(
                    f"Internal: Removed temp config file: {temp_config_path_host}"
                )
            except OSError as e:
                cleanup_error = (
                    f"Error removing temp config file {temp_config_path_host}: {e}"
                )
                logger.error(f"Internal: {cleanup_error}")
                # Append cleanup error to logs/error message if possible
                if error_message:
                    error_message += f"\nAdditionally: {cleanup_error}"
                else:
                    error_message = cleanup_error
                # Don't overwrite status if already failed
                if status == "Success":
                    status = "Failure (Cleanup Failed)"

    # --- Format and Return Result ---
    # Combine logs and any specific error message captured
    final_output = logs
    if error_message and error_message not in final_output:
        # Prepend error if not already in logs (e.g., API errors)
        final_output = f"{error_message}\n---\n{logs}" if logs else error_message

    result_message = (
        f"Crawl {status} (Return Code: {return_code})\n"
        f"Domain: {domain}\n"
        f"Output Index: {output_index}\n"
        f"--- LOGS ---\n{final_output}\n"
    )
    return result_message


@mcp.prompt(
    description="Initiate a documentation crawl for a specific website. Provide the 'domain' (e.g., 'elastic.co'), a 'seed_url' to start crawling (e.g., 'https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html'), and an 'output_index_suffix' (e.g., 'elastic-co-docs'). Optionally provide an 'index_prefix' (defaults to 'docsmcp'). The final index will be '<index_prefix>-<output_index_suffix>'. This runs the crawler in a Docker container and returns the status and logs."
)
async def crawl_website_documentation(
    seed_url: str,
    output_index_suffix: str,
    index_prefix: Optional[str] = DEFAULT_INDEX_PREFIX,
    domain: Optional[str] = None,
    filter: Optional[str] = None
) -> str:
    """
    Initiates a documentation crawl for a given website domain and seed URL.

    This command runs the 'elastic/crawler' Docker container on-demand
    to perform the crawl and index the content into Elasticsearch under
    an index named '<index_prefix>-<output_index_suffix>'.

    Args:
        seed_url: The starting URL for the crawler.
        filter: Optional filter for urls to scrape. Defaults to one level up from the seed_url.
        domain: optional domain for configuration (e.g., 'elastic.co'). Defaults to domain from seed_url.
        output_index_suffix: Optional suffix for the target Elasticsearch index (e.g., 'elastic-co-docs').
        index_prefix: Optional prefix for the target Elasticsearch index (defaults to 'docsmcp').

    Returns:
        A string containing the status (Success/Failure), return code,
        and logs (stdout/stderr) from the crawler container execution.
    """
    logger.info(
        f"Prompt received: Crawling website documentation for domain '{domain}' (seed: {seed_url})"
    )
    parsed_url = urlparse(seed_url)

    if filter is None:
        # take the seed url and go up one level and use that as the filter
        # so if the seed url is https://www.w3schools.com/html/intro.html, the filter would be https://www.w3schools.com/html
        filter = seed_url[:seed_url.rfind('/')]

    if domain is None:
        # Extract the domain from the seed URL
        # For example, if the seed URL is https://www.w3schools.com/html/intro.html,
        # the domain would bea w3schools.com
        domain = parsed_url.scheme + "://" + parsed_url.netloc

    if output_index_suffix is None:
        # If the seed URL is https://www.w3schools.com/html/intro.html
        # the default output_index_suffix is w3schools_com.html.intro_html
        output_index_suffix = (
            parsed_url.netloc.replace(".", "_").replace("www","") + 
            parsed_url.path.replace(".", "_").replace("/",".")
        )

    try:
        result = await _internal_crawl_domain(
            domain=domain,
            filter=filter,
            seed_url=seed_url,
            output_index_suffix=output_index_suffix,
            index_prefix=index_prefix,
        )
        logger.info(f"Prompt finished: Crawl result received.")
        # The internal function already formats the result string including logs
        return result
    except ValueError as ve:
        # Catch specific validation errors from the internal function
        logger.error(f"Prompt error: Invalid arguments for crawl: {ve}")
        return f"Error: Invalid arguments provided - {ve}"
    except Exception as e:
        logger.exception("Prompt error: Unexpected error during website crawl.")
        return f"Unexpected error initiating crawl: {e}"


# --- Dynamic Resource Handler ---

async def _handle_dynamic_doc_resource(index_name: str, query: Optional[str] = None) -> Dict[str, Any]:
    """
    Handles requests for dynamic documentation resources based on index name.

    Calls the search_documentation prompt with the provided index_name and query,
    then formats the results into a JSON dictionary.

    Args:
        index_name: The specific documentation index to search (derived from URI).
        query: The search query string (derived from URI path).

    Returns:
        A dictionary containing search results under the 'results' key,
        or an error dictionary under the 'error' key.
    """
    logger.info(f"Dynamic resource request for index: {index_name}, Query: '{query}'")
    try:
        # Prepare query for search_documentation (expects non-optional string)
        search_query = query.strip() if query else ""
        logger.debug(f"Calling search_documentation with query='{search_query}', index_prefix='{index_name}'")

        # Call the existing prompt function
        # Note: search_documentation already handles its own internal errors and returns []
        search_results: List[Tuple[str, str, List[str]]] = await search_documentation(
            query=search_query, index_prefix=index_name
        )

        # Format results
        formatted_results = []
        for title, url, chunks in search_results:
            formatted_results.append({
                "title": title,
                "url": url,
                "chunks": chunks
            })

        logger.info(f"Formatted {len(formatted_results)} results for index '{index_name}'.")
        return {"results": formatted_results}

    except Exception as e:
        # Catch errors in this handler itself or unexpected errors from search_documentation
        logger.exception(f"Error handling dynamic resource or formatting results for index '{index_name}'")
        return {"error": f"Failed to process resource request for index '{index_name}'", "details": str(e)}


# --- Dynamic Resource Registration ---

async def _update_dynamic_doc_resources():
    """
    Registers a ResourceTemplate to handle dynamic documentation searches.

    The template matches URIs like 'docs://{index_name}/{query}' and routes
    them to the _handle_dynamic_doc_resource function.
    """
    logger.info("Registering dynamic documentation resource template...")
   # try:
        # Define the URI template. Parameters {index_name} and {query} will be extracted.
        # Note: ResourceTemplate uses simple regex matching, not Starlette path converters.
        # The {query} part will match everything after the index name until the end.
    uri_template = f"docs://{{index_name}}/{{query}}"

    docs_indices = await _internal_list_doc_indices(index_prefix=DEFAULT_INDEX_PREFIX)

    for docs_index in docs_indices:

        uri = f"docs://{docs_index}/{{query}}"
        name = f"es_doc_search_{docs_index}"
        description = "Search {docs_index} for documentation."
        mime_type = "application/json"

        logger.info("Registering dynamic documentation resource template for index: %s with URI: %s", docs_index, uri)
        @mcp.resource(
            uri =uri,
            name=name,  # Unique name for each index to avoid conflicts
            description=description,
            mime_type=mime_type  # Ensure consistent MIME type for all dynamic resources
        )
        async def docs_resource(query: str):
            """
            Wrapper function to call the dynamic resource handler.
            This allows the MCP to route requests to the appropriate handler.
            """
            # Call the handler function with the index name and query
            return await _handle_dynamic_doc_resource(index_name=docs_index, query=query)

    # # # Create the ResourceTemplate using the handler function
    # doc_search_template = ResourceTemplate.from_function(
    #     fn=_handle_dynamic_doc_resource,
    #     uri_template=uri_template,
    #     name="dynamic_doc_search", # A single name for the template
    #     description="Dynamically handles documentation searches for any 'docs://<index_name>/<query>' URI.",
    #     mime_type="application/json" # Handler returns JSON
    # )

    #     #logger.info(f"Successfully registered resource template for URI: {uri_template}")

    #     # Now get the full list of indices and register them

    # docs_indices = await _internal_list_doc_indices(index_prefix=DEFAULT_INDEX_PREFIX)
    # for docs_index in docs_indices:
    #     # Register the resource template for each index
    #     # This will allow dynamic routing to the handler based on the index name

    #     uri = f"docs://{docs_index}/{{query}}"
    #     name = f"es_doc_search_{docs_index}"  # Unique name for each index to avoid conflicts
    #     description = "Search {docs_index} for documentation."
    #     mime_type = "application/json"  # Ensure consistent MIME type for all dynamic resources

    #     FnResource = await doc_search_template.create_resource(
    #         uri = uri,  # The URI for this specific index
    #         params={
    #             "index_name": docs_index  # Pass the index name to the handler
    #             # Note: The query parameter will be passed automatically by the ResourceTemplate
    #             # when it calls _handle_dynamic_doc_resource
    #         }
    #     )

        # FnResource = FunctionResource(
        #     fn=lambda: _handle_dynamic_doc_resource,
        #     name=name,
        #     uri=uri,
        #     description=description,
        #     mime_type=mime_type
        # )
        # await doc_search_template.create_resource(
        #     f"docs://{docs_index}/{{query}}", {"index_name": docs_index}
        # )
        logger.info(f"Registered dynamic resource for index: {docs_index}: {name}")

    #except Exception as e:
    #    logger.exception("Failed to register the dynamic documentation resource template.")

if __name__ == "__main__":
    mcp.run(transport = "sse")