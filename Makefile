# Makefile for esdocmanagermcp development tasks

.PHONY: help lint test inspector install

# Default target: Show help
help:
	@echo "Available targets:"
	@echo "  install    - Install dependencies using uv sync"
	@echo "  lint       - Run ruff check --fix and ruff format"
	@echo "  test       - Run pytest"
	@echo "  inspector  - Run the MCP Inspector script"
	@echo "  all        - Run lint and test"

# Install dependencies
install:
	uv sync

# Lint the code
lint:
	@echo "Running ruff format..."
	uv run ruff format .
	@echo "Running ruff check --fix..."
	uv run ruff check --fix .

# Run tests
test:
	@echo "Running pytest..."
	uv run pytest

# Run MCP Inspector
inspector:
	@echo "Running MCP Inspector..."
	./run-mcp-inspector.sh

# Run lint and test
all: lint test