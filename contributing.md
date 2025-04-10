# Contributing & Local Development

This document outlines how to set up the Elasticsearch Documentation Manager MCP Server for local development and debugging. For standard usage instructions, please refer to the main [README.md](readme.md).

## Prerequisites

*   Python >= 3.13 (as specified in `pyproject.toml`).
*   `uv` for installing dependencies and running the server.
*   Docker installed and running.
*   Access to an Elasticsearch cluster (>= 8.x recommended) with the ELSER model deployed

## Local Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/strawgate/es-documentation-manager-mcp.git
    ```
2.  **Navigate to the project directory:**
    ```bash
    cd es-documentation-manager-mcp
    ```
3.  **Install dependencies using `uv`:**
    ```bash
    uv sync
    ```

## Local Configuration & Running

When running locally for development, you typically configure the server directly via environment variables or an `.env` file, rather than relying on the MCP host's injection mechanism.

### 1. Environment Variables

You need to provide connection details for your Elasticsearch cluster and other settings.

**Create a `.env` file** in the project root directory with the following content, replacing placeholder values with your actual details:

```dotenv
# --- Required Settings ---
ES_HOST="YOUR_ELASTICSEARCH_HOST_URL" # e.g., https://your-deployment.es.us-east-1.aws.elastic.cloud:443

# Option 1: API Key (Recommended)
ES_API_KEY="YOUR_BASE64_ENCODED_API_KEY" # e.g., askmdlamsekmalwkm43qlk23m4qk234==

# Option 2: Username/Password (Uncomment and fill if not using API Key)
# ES_USERNAME="YOUR_ELASTICSEARCH_USERNAME"
# ES_PASSWORD="YOUR_ELASTICSEARCH_PASSWORD"

# --- Optional Settings ---
ES_PIPELINE="your-ingest-pipeline-name"
MCP_TRANSPORT="sse"

# --- Optional Settings ---
# ES_INDEX_PREFIX="docsmcp" # Prefix for created indices (default: "docsmcp")
# CRAWLER_IMAGE="ghcr.io/strawgate/es-crawler:main" # Crawler image to use (default: ghcr.io/strawgate/es-crawler:main)
```

### 2. Running the Server Locally

With the environment variables set (either exported in your shell or defined in `.env`), run the server using `uv`:

```bash
uv run python esdocmanagermcp/server.py
```

This command executes the `main()` function within the `server.py` script. The server will start and listen for MCP connections based on the `MCP_TRANSPORT` setting.

### 3. Configuring MCP Host for Local Development (Optional)

If you want to test the locally running server with your MCP host (e.g., Roo VS Code extension), you can configure it to connect to your local instance. Update your `mcp_settings.json`:

```json
{
  "mcpServers": {
    "esdocmanagermcp-local": { // Use a distinct name like "-local"
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/your/cloned/es-documentation-manager-mcp", // <-- IMPORTANT: Update this path
        "python",
        "esdocmanagermcp/server.py"
      ],
      "cwd": "/absolute/path/to/your/cloned/es-documentation-manager-mcp", // <-- IMPORTANT: Update this path
      "env": {
        "ES_HOST": "https://YOUR_ELASTICSEARCH_HOST_URL:443",
        // --- Authentication: Provide EITHER API Key
        "ES_API_KEY": "YOUR_BASE64_ENCODED_API_KEY",
        // OR Username/Password
        "ES_USERNAME": "YOUR_ELASTICSEARCH_USERNAME",
        "ES_PASSWORD": "YOUR_ELASTICSEARCH_PASSWORD",

        "MCP_TRANSPORT": "sse"
      },
      "alwaysAllow": [
        "get_documentation_types",
        "pull_crawler_image",
        "crawl_domains",
        "list_crawls",
        "get_crawl_status",
        "get_crawl_logs",
        "stop_crawl",
        "remove_completed_crawls",
        "search_specific_documentation",
        "search_all_documentation",
        "get_document_by_url",
        "get_document_by_title"
      ],
      "disabled": false
    }
    // ... other servers ...
  }
}
```

## Development Tasks (Makefile)

A `Makefile` is provided to simplify common development tasks:

*   **Install dependencies:**
    ```bash
    make install
    # or directly: uv sync
    ```
*   **Lint and format code:** (Uses Ruff)
    ```bash
    make lint
    ```
*   **Run tests:** (Uses Pytest)
    ```bash
    make test
    ```
*   **Run lint and tests:**
    ```bash
    make all
    ```
*   **Run MCP Inspector:** (Requires the server to be running, e.g., via debugger or `uv run`)
    ```bash
    make inspector
    # or directly: ./run-mcp-inspector.sh
    ```

Use `make help` to see all available targets.

### 4. Debugging

To debug the server:
1.  Set up your environment variables (e.g., using the `.env` file).
2.  Start the server using your IDE's debugger (e.g., using the provided VS Code launch configuration in `.vscode/launch.json`).
3.  In a separate terminal, run the MCP Inspector to interact with the running server:
    ```bash
    make inspector
    ```