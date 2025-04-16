# Elasticsearch Knowledge Base MCP Server

## Overview

This MCP server provides tools to your AI Assistant allowing it to crawl and search documentation autonomously. It utilizes the `FastMCP` framework for simplified development and interacts with:

1.  A Docker container running the `ghcr.io/strawgate/es-crawler:main` image (or as configured via `CRAWLER_IMAGE` env var) to perform the actual web crawling.
2.  An Elasticsearch cluster for index listing and ELSER-powered searching. Indices created will use the prefix `docsmcp-` by default (configurable via `ES_INDEX_PREFIX` env var). Using an [Elasticsearch Serverless Search project](https://www.elastic.co/guide/en/serverless/current/what-is-elasticsearch-serverless.html) is a lightning fast way to get started.

## Demo

### Searching Documentation

In this demo we plan out a project that relies on several specific APIs in Elasticsearch. The LLM autonomously vector searches the documentation to get the nitty gritty API details and response examples it'll need to properly implement the project:

https://github.com/user-attachments/assets/64b5fee1-a983-4a92-9485-bfc54f879374

### Crawling Documentation

In this demo we open a git repository and tell the LLM we're getting started with this project. It proceeds to look at the dependencies and grab relevant documentation.

https://github.com/user-attachments/assets/c7226aa9-9b40-45fb-877b-8721550e0576



## Configuration

This server requires connection details for your Elasticsearch cluster and is configured directly within your MCP host's settings file (e.g., `mcp_settings.json` for the Roo VS Code extension).

The recommended way to run this server is using `uvx`, which handles fetching and running the code directly from GitHub. 

### VS Code 

1. Open the command palette (Ctrl+Shift+P or Cmd+Shift+P).
2. Type "Settings" and select "Preferences: Open User Settings (JSON)".
3. Add the following MCP Server configuration

```json
{
    "mcp": {
        "inputs": [

            {
                "type": "promptString",
                "id": "es-host",
                "description": "Elasticsearch Host",
                "password": false
            },
            {
                "type": "promptString",
                "id": "es-api-key",
                "description": "Elasticsearch API Key",
                "password": false
            }
        ],
        "servers": {
            "External Documentation - GitHub": {
                "command": "uvx",
                "args": [
                    "git+https://github.com/strawgate/es-documentation-manager-mcp"
                ],
                "env": {
                    "ES_HOST": "${input:es-host}",
                    "ES_API_KEY": "${input:es-api-key}",
                },
            }
        }
    }
}
```

### Cline / Roo Code
Add the following configuration block to your `mcpServers` object:

```json
  "External Documentation": {
      "command": "uvx",
      "args": [
        "git+https://github.com/strawgate/es-documentation-manager-mcp"
      ],
      "env": {
        "ES_HOST": "https://YOUR_ELASTICSEARCH_HOST_URL:443",
        // --- Authentication: Provide EITHER API Key
        "ES_API_KEY": "YOUR_BASE64_ENCODED_API_KEY",
        // OR Username/Password
        "ES_USERNAME": "YOUR_ELASTICSEARCH_USERNAME",
        "ES_PASSWORD": "YOUR_ELASTICSEARCH_PASSWORD",
      },
      "alwaysAllow": [
        "get_documentation_types",
        "pull_crawler_image",
        "crawl_domains",
        "search_specific_documentation",
        "search_all_documentation",
        "get_document_by_url",
        "get_document_by_title"
      ],
      "disabled": false
    }
```

## Features / Tools

The server exposes the following tools for use by MCP clients (like AI agents), based on the connected `es_knowledge_base_mcp` server:

*   **`get_documentation_types(include_doc_count: bool = False)`**:
    *   **Description:** Retrieves the list of documentation types (indices) available. Useful for discovering specific indices to target with `search_specific_documentation`.
    *   **Arguments:**
        *   `include_doc_count` (bool, optional): Whether to include the document count for each type. Defaults to `False`.
    *   **Returns:** A list of documentation type names (strings) or a list of dictionaries containing `type` and `documents` if `include_doc_count` is `True`.

*   **`delete_documentation(type: str)`**:
    *   **Description:** Deletes a specific documentation index from Elasticsearch. Wildcards are not allowed.
    *   **Arguments:**
        *   `type` (str): The type name (index suffix) of the documentation to delete (e.g., `elastic_co.guide_en_index`).
    *   **Returns:** A status message indicating success or failure.

*   **`pull_crawler_image()`**:
    *   **Description:** Pulls the configured crawler Docker image (`CRAWLER_IMAGE` setting) if not present locally.
    *   **Arguments:** None.
    *   **Returns:** Status message indicating if the image is available or was pulled.

*   **`crawl_domains(seed_pages: str | List[str] | None = None, seed_dirs: str | List[str] | None = None)`**:
    *   **Description:** Starts one or many crawl jobs based on lists of seed pages and/or directories. It automatically derives necessary parameters like domain, filter pattern, and index suffix.
    *   **Arguments:**
        *   `seed_pages` (str or List[str], optional): URLs where crawling follows links matching the path *after* the last `/`. Good for specific files (e.g., `README.md`) where siblings should be included.
        *   `seed_dirs` (str or List[str], optional): URLs where crawling follows links that are *children* of the provided URL path. Good for broader directory structures.
    *   **Returns:** A list of dictionaries, each containing the result for a processed seed URL (`seed_url`, `success`, `container_id` or `message`).

*   **`list_crawls()`**:
    *   **Description:** Lists currently running or recently completed crawl containers managed by this server.
    *   **Arguments:** None.
    *   **Returns:** A formatted string listing managed crawl containers with their status (Domain, Done, Errored, ID, Name, State, Status).

*   **`get_crawl_status(container_id: str)`**:
    *   **Description:** Gets the detailed status of a specific crawl container by its ID.
    *   **Arguments:**
        *   `container_id` (str): The full or short ID of the container.
    *   **Returns:** A formatted string with detailed status information.

*   **`get_crawl_logs(container_id: str, tail: str = "all")`**:
    *   **Description:** Gets the logs from a specific crawl container.
    *   **Arguments:**
        *   `container_id` (str): The full or short ID of the container.
        *   `tail` (str): Number of lines to show from the end (e.g., "100", default: "all").
    *   **Returns:** The container logs as a string, or a message if not found.

*   **`stop_crawl(container_id: str)`**:
    *   **Description:** Stops and removes a specific crawl container by its ID.
    *   **Arguments:**
        *   `container_id` (str): The full or short ID of the container.
    *   **Returns:** Status message confirming stop and removal.

*   **`remove_completed_crawls()`**:
    *   **Description:** Removes all completed (status 'exited') crawl containers managed by this server.
    *   **Arguments:** None.
    *   **Returns:** Summary dictionary with `removed_count` and `errors`.

*   **`search_specific_documentation(types: str, query: str)`**:
    *   **Description:** Performs a search query against specified documentation types (indices) using vector search.
    *   **Arguments:**
        *   `types` (str): Comma-separated list of documentation types (index suffixes) to query. Wildcards (`*`) are allowed (e.g., `*python*`, `fastapi, *django*`).
        *   `query` (str): The search query describing what you're looking for.
    *   **Returns:** A dictionary containing formatted search results.

*   **`search_all_documentation(question: str, results: int = 5)`**:
    *   **Description:** Performs a vector search query against *all* available documentation indices.
    *   **Arguments:**
        *   `question` (str): The search query describing what you're looking for or the problem to solve.
        *   `results` (int, optional): The maximum number of results to return (default: 5).
    *   **Returns:** A dictionary containing formatted search results.

*   **`get_document_by_url(doc_url: str)`**:
    *   **Description:** Retrieves the full content of a specific document identified by its URL.
    *   **Arguments:**
        *   `doc_url` (str): The exact URL of the document stored in Elasticsearch.
    *   **Returns:** The formatted content of the document if found, otherwise indicates not found.

*   **`get_document_by_title(doc_title: str)`**:
    *   **Description:** Retrieves the full content of a document identified by its title using a match query.
    *   **Arguments:**
        *   `doc_title` (str): The title of the document to retrieve.
    *   **Returns:** The formatted content of the document if found, otherwise indicates not found.

## Prerequisites

*   Python >= 3.13 (as specified in `pyproject.toml`).
*   `uv` for installing dependencies and running the server.
*   Docker installed and running.
*   Access to an Elasticsearch cluster (>= 8.x recommended) with the ELSER model deployed and an appropriate ingest pipeline configured (see `ES_PIPELINE` below).

## Contributing

For local development and contribution, please see the [Contributing Guide](contributing.md).
