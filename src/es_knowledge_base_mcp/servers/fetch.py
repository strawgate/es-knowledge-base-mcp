"""MCP Server for fetching external resources."""

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from typing import Callable

from docling.document_converter import DocumentConverter


from es_knowledge_base_mcp.models.constants import BASE_LOGGER_NAME

logger = get_logger(BASE_LOGGER_NAME).getChild("fetch")


class FetchServer:
    """
    Server for fetching external resources like webpages.
    """

    response_wrapper: Callable

    def __init__(self, response_wrapper: Callable | None = None):
        self.response_wrapper = response_wrapper or (lambda response: response)

    def register_with_mcp(self, mcp: FastMCP):
        mcp.add_tool(self.response_wrapper(self.webpage))

    async def async_init(self):
        pass

    async def async_shutdown(self):
        pass

    async def webpage(self, url: str) -> str:
        """
        Fetches a webpage and converts it to Markdown format.
        Args:
            url (str): The URL of the webpage to fetch.
        Returns:
            str: The content of the webpage in Markdown format.
        """

        doc_converter = DocumentConverter()

        result = doc_converter.convert(url)

        return result.document.export_to_markdown()
