# Elasticsearch Documentation Manager MCP Server

## Overview

This MCP server provides tools to manage the crawling of documentation websites into Elasticsearch and perform searches using the ELSER model. It utilizes the `FastMCP` framework for simplified development and interacts with:

1.  A Docker container running the `ghcr.io/strawgate/es-crawler:main` image (or as configured via `CRAWLER_IMAGE` env var) to perform the actual web crawling.
2.  An Elasticsearch cluster for index listing and ELSER-powered searching. Indices created will use the prefix `docsmcp-` by default (configurable via `ES_INDEX_PREFIX` env var).

## Features / Tools

The server exposes the following tools for use by MCP clients (like AI agents), based on the connected `esdocmanagermcp` server:

*   **`search_documentation(index_name: str, query: str)`**:
    *   **Description:** Performs a search query against a specified documentation index using ELSER.
    *   **Arguments:**
        *   `index_name` (str): The name of the Elasticsearch index to search.
        *   `query` (str): The search query string.
    *   **Returns:** A dictionary containing search results.

*   **`pull_crawler_image()`**:
    *   **Description:** Pulls the configured crawler Docker image ('crawler_image' setting) if not present locally.
    *   **Arguments:** None.
    *   **Returns:** Status message.

*   **`crawl_complex_domain(domain: str, seed_url: str, filter_pattern: str, output_index_suffix: str)`**:
    *   **Description:** Starts crawling a website using the configured Elastic crawler Docker image, indexing content into a specified Elasticsearch index suffix.
    *   **Arguments:**
        *   `domain` (str): The primary domain name (e.g., `https://www.elastic.co`).
        *   `seed_url` (str): The starting URL for the crawl (e.g., `https://www.elastic.co/guide/en/index.html`).
        *   `filter_pattern` (str): URL prefix pattern to restrict the crawl (e.g., `/guide/en/`).
        *   `output_index_suffix` (str): Suffix to append to the default prefix (e.g., `elastic_co.guide_en_index`).
    *   **Returns:** The container ID of the started crawl.

*   **`crawl_domains(seed_urls: List[str])`**:
    *   **Description:** Starts one or many crawl jobs based on a list of seed URLs. It automatically derives necessary parameters like domain, filter pattern, and index suffix from each seed URL.
    *   **Arguments:**
        *   `seed_urls` (List[str]): A list of starting URLs for the crawls.
    *   **Returns:** A list of dictionaries, each containing the `seed_url`, `status` ('success' or 'error'), and `container_id` (if successful) for each requested crawl.

*   **`list_crawls()`**:
    *   **Description:** Lists currently running or recently completed crawl containers managed by this server.
    *   **Arguments:** None.
    *   **Returns:** List of crawl container details.

*   **`get_crawl_status(container_id: str)`**:
    *   **Description:** Gets the detailed status of a specific crawl container by its ID.
    *   **Arguments:**
        *   `container_id` (str): The full or short ID of the container.
    *   **Returns:** Detailed status information.

*   **`get_crawl_logs(container_id: str, tail: str = "all")`**:
    *   **Description:** Gets the logs from a specific crawl container.
    *   **Arguments:**
        *   `container_id` (str): The full or short ID of the container.
        *   `tail` (str): Number of lines to show from the end (e.g., "100", default: "all").
    *   **Returns:** Container logs.

*   **`stop_crawl(container_id: str)`**:
    *   **Description:** Stops and removes a specific crawl container by its ID.
    *   **Arguments:**
        *   `container_id` (str): The full or short ID of the container.
    *   **Returns:** Status message.

*   **`remove_completed_crawls()`**:
    *   **Description:** Removes all completed (status 'exited') crawl containers managed by this server.
    *   **Arguments:** None.
    *   **Returns:** Summary dictionary with 'removed_count' and 'errors'.

*   **`list_doc_indices()`**:
    *   **Description:** Lists available Elasticsearch documentation indices managed by this server (matching the configured prefix).
    *   **Arguments:** None.
    *   **Returns:** List of index names.

## Prerequisites

*   Python >= 3.13 (as specified in `pyproject.toml`).
*   `uv` for installing dependencies and running the server.
*   Docker installed and running.
*   Access to an Elasticsearch cluster (>= 8.x recommended) with the ELSER model deployed and an appropriate ingest pipeline configured (see `ES_PIPELINE` below).

## Setup & Installation

1.  Clone this repository: `git clone <repository_url>`
2.  Navigate to the project directory: `cd es-documentation-manager-mcp`
3.  Install dependencies using `uv`: `uv sync`

## Configuration

This server requires connection details for your Elasticsearch cluster. Authentication can be done using *either* an API Key *or* Username/Password. These details, along with other settings, are provided via environment variables when the server is launched by the MCP host (e.g., the Roo VS Code extension).

You need to configure the server in your global MCP settings file. The exact location varies by operating system and the MCP host application (e.g., for VS Code on macOS).

Add or update the entry for `esdocmanagermcp`:

```json
{
  "mcpServers": {
    "esdocmanagermcp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/es-documentation-manager-mcp", // <-- IMPORTANT: Update this path
        "python",
        "esdocmanagermcp/server.py"
      ],
      "cwd": "/path/to/es-documentation-manager-mcp", // <-- IMPORTANT: Update this path
      "env": {
        "ES_HOST": "YOUR_ELASTICSEARCH_HOST_URL", // e.g., https://your-deployment.es.us-east-1.aws.elastic.cloud:443 (Required)
        // --- Authentication: Provide EITHER API Key OR Username/Password ---
        "ES_API_KEY": "YOUR_BASE64_ENCODED_API_KEY", // (Optional if using Username/Password) e.g., askmdlamsekmalwkm43qlk23m4qk234==
        "ES_USERNAME": "YOUR_ELASTICSEARCH_USERNAME", // (Optional if using API Key)
        "ES_PASSWORD": "YOUR_ELASTICSEARCH_PASSWORD", // (Optional if using API Key)
        // --- Required Settings ---
        "ES_PIPELINE": "your-ingest-pipeline-name", // (Required) Name of an existing ES ingest pipeline (e.g., .elser_model_2_linux-x86_64)
        // --- Optional Settings ---
        "ES_INDEX_PREFIX": "docsmcp", // (Optional) Prefix for created indices (default: "docsmcp")
        "CRAWLER_IMAGE": "ghcr.io/strawgate/es-crawler:main", // (Optional) Crawler image to use (default: ghcr.io/strawgate/es-crawler:main)
        // --- MCP Transport ---
        "MCP_TRANSPORT": "stdio" // Use "stdio" for VS Code extension. Server defaults to "sse" if unset.
      },
      "alwaysAllow": [ // Optional: Tools allowed without explicit user confirmation
        "list_doc_indices",
        "pull_crawler_image",
        "search_documentation"
      ],
      "disabled": false
    }
    // ... other servers ...
  }
}
```

**Important:**
*   Replace placeholder values (like `YOUR_ELASTICSEARCH_HOST_URL`, `YOUR_BASE64_ENCODED_API_KEY`, `your-ingest-pipeline-name`, etc.) with your actual Elasticsearch details.
*   Ensure you provide *either* `ES_API_KEY` *or* both `ES_USERNAME` and `ES_PASSWORD`.
*   The `ES_PIPELINE` must be an existing ingest pipeline in your Elasticsearch cluster, typically one configured for ELSER inference. The search ingest pipeline is the default pipeline.
*   **Crucially, update the `/path/to/es-documentation-manager-mcp` placeholders in `args` and `cwd` to the correct absolute path where you cloned this repository on your system.**
*   Indices created by the crawl tools will be named `{ES_INDEX_PREFIX}-{output_index_suffix}` (e.g., `docsmcp-elastic_co.guide_en_index`).

### Configuration Helper Script

To simplify generating the `mcpServers` JSON block (using API Key authentication), you can use the provided shell script `configure_mcp.sh`. Note: This script currently only supports configuration via `--es-api-key` and does not support username/password authentication.

**Usage:**

```bash
./configure_mcp.sh \
  --es-host "YOUR_ELASTICSEARCH_HOST_URL" \
  --es-api-key "YOUR_BASE64_ENCODED_API_KEY" \
  --es-pipeline "your-ingest-pipeline-name" \
  [--project-dir "/path/to/es-documentation-manager-mcp"] # Optional: Defaults to current dir
```

The script will print the JSON block to the console. You can copy and paste this into your `mcp_settings.json` file, replacing the existing `esdocmanagermcp` entry if necessary.

**Example:**

```bash
./configure_mcp.sh \
  --es-host "https://my-es.example.com:9200" \
  --es-api-key "AbCdEfGhIjKlMnOpQrStUvWxYz1234567890=" \
  --es-pipeline "elser-ingest-pipeline"
```

This will output the JSON configuration using the current directory for the project path.

## Running the Server

The MCP server is designed to be launched automatically by the MCP host process (e.g., the Roo VS Code extension) based on the configuration in `mcp_settings.json`. Ensure the host application (like VS Code) is restarted after modifying the settings file.

For direct local debugging (less common when using the MCP host configuration, as the host injects the environment variables):

1.  Set environment variables manually:
    ```bash
    # Required:
    export ES_HOST="YOUR_ELASTICSEARCH_HOST_URL"
    export ES_PIPELINE="your-ingest-pipeline-name"
    export MCP_TRANSPORT="stdio" # Or "sse" if not using stdio host

    # EITHER API Key:
    export ES_API_KEY="YOUR_BASE64_ENCODED_API_KEY"

    # OR Username/Password:
    # export ES_USERNAME="YOUR_ELASTICSEARCH_USERNAME"
    # export ES_PASSWORD="YOUR_ELASTICSEARCH_PASSWORD"

    # Optional:
    # export ES_INDEX_PREFIX="custom-prefix"
    # export CRAWLER_IMAGE="your-custom-crawler:latest"
    ```
2.  Run the server:
    ```bash
    uv run python esdocmanagermcp/server.py