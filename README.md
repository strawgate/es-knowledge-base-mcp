# Elasticsearch Knowledge Base MCP Server

## Overview

This MCP server empowers your AI Assistant to ASK, LEARN, and REMEMBER:
*   **ASK**: Ask questions of the gathered knowledge bases, in plain language like, "What's the best way to use `local_example` in ruby Rspec tests?".
*   **LEARN**: Obtain and index entire documentation stores (e.x. every word of every page of https://docs.pytest.org/en/stable/contents.html) from the Web, git repositories, or the local filesystem.
*   **REMEMBER**: Store working information, user preferences, and rules as "memories" for future reference.

This MCP Server is powered by [Elasticsearch Serverless Search (Start a free trial)](https://www.elastic.co/guide/en/serverless/current/what-is-elasticsearch-serverless.html) for inference, and vector search, and [Elastic Crawler](https://github.com/elastic/crawler) for crawling, parsing, and indexing.

## Benefits

This MCP Server significantly reduces token usage of the AI Assistant by allowing it to reference specific documentation for the task at hand instead of relying on the AI model's internal knowledge. This allows the AI Assistant to one-shot complex tasks because it doesn't need to guess parameter names, types, or usage. It also allows the AI Assistant to reference documentation as needed without needing to be trained on it.

## Demo

### Searching Documentation

See how you can autonomously search documentation stored in a knowledge base to gather details needed for a task:

https://github.com/user-attachments/assets/64b5fee1-a983-4a92-9485-bfc54f879374

### Crawling Documentation

Watch how you can identify project dependencies and automatically crawl relevant web documentation to build a knowledge base:

https://github.com/user-attachments/assets/c7226aa9-9b40-45fb-877b-8721550e0576


## Configuration

To use this server, the MCP host (e.g., Roo VS Code extension, Cline, VS Code) must be configured with the connection details for the target Elasticsearch cluster, including the host URL and authentication credentials (like an API Key).

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
                "password": true
            }
        ],
        "servers": {
            "es_knowledge_base_mcp": {
                "command": "uvx",
                "args": [
                    "git+https://github.com/strawgate/es-knowledge-base-mcp"
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
  "Knowledge Base": {
      "command": "uvx",
      "args": [
        "git+https://github.com/strawgate/es-knowledge-base-mcp"
      ],
      "env": {
        "ES_HOST": "https://YOUR_ELASTICSEARCH_HOST_URL:443",
        // --- Authentication: Provide EITHER API Key
        "ES_API_KEY": "YOUR_BASE64_ENCODED_API_KEY",
        // OR Username/Password
        "ES_USERNAME": "YOUR_ELASTICSEARCH_USERNAME",
        "ES_PASSWORD": "YOUR_ELASTICSEARCH_PASSWORD",
      },
      "alwaysAllow": [],
      "disabled": false
    }
```

## Available Tools

The `es_knowledge_base_mcp_debug` server provides the following tools:

### Knowledge Base Management
*   **`knowledge_base_create`**: Create a new knowledge base.
*   **`knowledge_base_get`**: Get a list of all knowledge bases.
*   **`knowledge_base_get_by_backend_id`**: Get a knowledge base by its backend ID.
*   **`knowledge_base_get_by_name`**: Get a knowledge base by its name.
*   **`knowledge_base_delete_by_backend_id`**: Delete a knowledge base by its backend ID.
*   **`knowledge_base_delete_by_name`**: Delete a knowledge base by its name.
*   **`knowledge_base_update_by_backend_id`**: Update the metadata of an existing knowledge base by its backend ID.
*   **`knowledge_base_update_by_name`**: Update the description of an existing knowledge base by its name.

### Memory
*   **`memory_encodings`**: Encode multiple memories into the memory knowledge base.
*   **`memory_encoding`**: Encode a single memory into the memory knowledge base.
*   **`memory_recall`**: Search the memory knowledge base using questions.
*   **`memory_recall_last`**: Retrieve the most recent memories from the memory knowledge base.

### Ask
*   **`ask_questions`**: Ask questions of the knowledge base.
*   **`ask_questions_for_kb`**: Ask questions of a specific knowledge base.

### Learn
*   **`learn_extract_urls_from_webpage`**: Extracts all unique URLs from a given webpage.
*   **`learn_from_web_documentation`**: Starts a crawl job based on a seed page and creates a knowledge base entry for it.
*   **`learn_active_documentation_requests`**: Returns a list of active documentation requests.

### Fetch
*   **`fetch_webpage`**: Fetches a webpage and converts it to Markdown format.

### Bulk Operations
*   **`call_tool_bulk`**: Call a single tool multiple times in a single request.
*   **`call_tools_bulk`**: Call multiple tools in a single request.

## Resources

*   **`kb://entry`**: Access the details (Title, Source, Description) of a specific knowledge base entry using its unique ID or assigned name.


## Contributing

For details on local development, setup, and contributing to this project, please see the [Contributing Guide](contributing.md).
