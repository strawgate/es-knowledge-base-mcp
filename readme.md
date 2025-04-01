# Elasticsearch Documentation Manager MCP Server

## Overview

This MCP server provides tools to manage the crawling of documentation websites into Elasticsearch and perform searches using the ELSER model. It utilizes the `FastMCP` framework for simplified development and interacts with:

1.  A `elastic/crawler` Docker container (expected to be named `crawler`) to perform the actual web crawling.
2.  An Elasticsearch cluster for index template management, index listing, and ELSER-powered searching.

## Features / Tools

The server exposes the following tools for use by MCP clients (like AI agents):

*   **`setup_index_template()`**:
    *   **Description:** Creates or updates the standard index template (`docsmcp-template`) in Elasticsearch. This template includes mappings necessary for ELSER (`semantic_text` type for `body` and `headings`). It matches indices like `docsmcp-*` or `<prefix>-*`.
    *   **Arguments:** None.
    *   **Returns:** A success or error message string.

*   **`list_doc_indices(index_prefix: Optional[str] = "docsmcp")`**:
    *   **Description:** Lists Elasticsearch indices matching the specified prefix pattern (`<prefix>-*`).
    *   **Arguments:**
        *   `index_prefix` (Optional[str]): The prefix for indices to list. Defaults to `"docsmcp"`.
    *   **Returns:** A list of matching index names.

*   **`search_docs(query: str, index_prefix: Optional[str] = "docsmcp")`**:
    *   **Description:** Performs an ELSER sparse vector search (`text_expansion`) across documentation indices matching the specified prefix.
    *   **Arguments:**
        *   `query` (str): The search query string. Defaults to a semantic_search of body and headings.
        *   `index_prefix` (Optional[str]): The prefix for indices to search. Defaults to `"docsmcp"`.
    *   **Returns:** A list of Elasticsearch search hit objects (`_source` included).

*   **`crawl_domain(domain: str, seed_url: str, output_index_suffix: str, index_prefix: Optional[str] = "docsmcp")`**:
    *   **Description:** Initiates a web crawl using the `elastic/crawler` Docker container.
    *   **Arguments:**
        *   `domain` (str): The root domain being crawled (e.g., `playwright.dev`).
        *   `seed_url` (str): The starting URL for the crawl.
        *   `output_index_suffix` (str): A suffix to append to the index prefix to form the final index name (e.g., `playwright-docs`).
        *   `index_prefix` (Optional[str]): The prefix for the output index. Defaults to `"docsmcp"`. The final index will be `<index_prefix>-<output_index_suffix>`.
    *   **Returns:** A string containing the status, stdout, and stderr from the crawler process.

## Prerequisites

*   Python >= 3.10 (Check `pyproject.toml` or `requirements.txt` for specific version).
*   `uv` or `pip` for installing dependencies.
*   Docker installed and running.
*   The `elastic/crawler` Docker image pulled and running in a container named `crawler`. You can typically start it using `docker-compose up -d` from the root of the `es_crawler` repository.
*   Access to an Elasticsearch cluster (>= 8.x recommended).
*   The ELSER model (`.elser-2-elasticsearch` or similar) must be deployed and running on the target Elasticsearch cluster for the `search_docs` tool to function correctly.

## Setup & Installation (Local Development/Manual)

1.  Clone the parent repository (`es_crawler`) if you haven't already.
2.  Navigate to this directory: `cd /path/to/es_crawler/crawler/mcp-server`.
3.  Create a Python virtual environment: `python3 -m venv .venv`.
4.  Activate the virtual environment: `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\activate` (Windows).
5.  Install dependencies:
    *   If using `uv` and `requirements.txt`: `uv pip install -r requirements.txt`
    *   If using Poetry: `poetry install`

## Configuration

This server requires connection details for your Elasticsearch cluster, provided via environment variables when the server is launched by the MCP host (e.g., VS Code extension).

Configure the server in your global MCP settings file (e.g., `~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json` on macOS). Add or update the entry for `elasticsearch-documentation-manager-mcp`:

```json
{
  "mcpServers": {
    "... other servers ...": {},
    "elasticsearch-documentation-manager-mcp": {
      // Use absolute path to python in venv
      "command": "/Users/williameaston/Documents/Repositories/es_crawler/crawler/mcp-server/.venv/bin/python",
      // Use absolute path to server script
      "args": [
        "/Users/williameaston/Documents/Repositories/es_crawler/crawler/mcp-server/server.py"
      ],
      // No "cwd" needed if using absolute paths
      "env": {
        "ES_HOST": "https://your-es-host.example.com", // Include scheme (https://)
        "ES_PORT": "443", // Or your ES port
        "ES_USERNAME": "your_es_username",
        "ES_PASSWORD": "your_es_password",
        "ES_PIPELINE": "your-ingest-pipeline-name" // e.g., "search-default-ingestion"
      },
      "disabled": false,
      "alwaysAllow": []
    }
  }
}
Important: Replace placeholder values in the env block with your actual Elasticsearch credentials and ensure the paths in command and args are correct for your system.

Running the Server
The MCP server is designed to be launched automatically by the MCP host process (e.g., the VS Code extension or Claude Desktop) based on the configuration in mcp_settings.json.

For local debugging, you can manually set the required environment variables and run the server directly from its activated virtual environment:

export ES_HOST="https://your-es-host.example.com"
export ES_PORT="443"
export ES_USERNAME="your_es_username"
export ES_PASSWORD="your_es_password"
export ES_PIPELINE="your-ingest-pipeline-name"

uv run server.py