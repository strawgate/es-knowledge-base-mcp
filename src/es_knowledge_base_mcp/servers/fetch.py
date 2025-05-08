"""MCP Server for fetching external resources."""

from docling.document_converter import DocumentConverter
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from fastmcp.utilities.logging import get_logger
from pydantic import Field

from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME

logger = get_logger(BASE_LOGGER_NAME).getChild("fetch")


class FetchServer(MCPMixin):
    """Server for fetching external resources like webpages."""

    @mcp_tool()
    async def webpage(self, url: str = Field(description="The URL of the webpage to fetch.")) -> str:
        """Fetch a webpage and converts it to Markdown format.

        Returns:
            str: The content of the webpage in Markdown format.
        """
        doc_converter = DocumentConverter()

        result = doc_converter.convert(url)

        return result.document.export_to_markdown()
