#!/bin/bash

# Default values
PROJECT_DIR=$(pwd)
ES_HOST=""
ES_API_KEY=""
ES_PIPELINE=""

# --- Argument Parsing ---
# Using a loop to handle arguments more robustly
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --es-host)
        ES_HOST="$2"
        shift # past argument
        shift # past value
        ;;
        --es-api-key)
        ES_API_KEY="$2"
        shift # past argument
        shift # past value
        ;;
        --es-pipeline)
        ES_PIPELINE="$2"
        shift # past argument
        shift # past value
        ;;
        --project-dir)
        PROJECT_DIR="$2"
        shift # past argument
        shift # past value
        ;;
        *)    # unknown option
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
done

# --- Validation ---
if [ -z "$ES_HOST" ]; then
    echo "Error: --es-host is required."
    exit 1
fi

if [ -z "$ES_API_KEY" ]; then
    echo "Error: --es-api-key is required."
    exit 1
fi

if [ -z "$ES_PIPELINE" ]; then
    echo "Error: --es-pipeline is required."
    exit 1
fi

# --- Get Absolute Path for Project Directory ---
# Ensure the provided directory exists and get its absolute path
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory '$PROJECT_DIR' not found."
    exit 1
fi
# Use realpath if available (more robust), otherwise fallback to cd/pwd
if command -v realpath &> /dev/null; then
    ABS_PROJECT_DIR=$(realpath "$PROJECT_DIR")
else
    ABS_PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)
fi

# --- Generate JSON Output ---
# Using printf for better control over formatting and escaping
printf '{\n'
printf '  "mcpServers": {\n'
printf '    "esdocmanagermcp": {\n'
printf '      "command": "uv",\n'
printf '      "args": [\n'
printf '        "run",\n'
printf '        "--directory",\n'
printf '        "%s",\n' "$ABS_PROJECT_DIR" # Use absolute path
printf '        "python",\n'
printf '        "esdocmanagermcp/server.py"\n'
printf '      ],\n'
printf '      "cwd": "%s",\n' "$ABS_PROJECT_DIR" # Use absolute path
printf '      "env": {\n'
printf '        "ES_HOST": "%s",\n' "$ES_HOST"
printf '        "ES_API_KEY": "%s",\n' "$ES_API_KEY"
printf '        "ES_PIPELINE": "%s",\n' "$ES_PIPELINE"
printf '        "MCP_TRANSPORT": "stdio"\n'
printf '      },\n'
printf '      "alwaysAllow": [\n'
printf '        "list_doc_indices",\n'
printf '        "pull_crawler_image",\n'
printf '        "search_documentation"\n'
printf '      ],\n'
printf '      "disabled": false\n'
printf '    }\n'
printf '    // Add other servers here if needed\n'
printf '  }\n'
printf '}\n'

# Make the script executable after creation
chmod +x configure_mcp.sh