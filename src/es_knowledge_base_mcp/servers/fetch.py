import httpx
import markdownify
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from bs4 import BeautifulSoup
from typing import Callable, Dict
import re

logger = get_logger("knowledge-base-mcp.fetch")


class FetchServer:
    """Fetch server for general data fetching tools."""

    response_wrapper: Callable

    def __init__(self, response_wrapper: Callable | None = None):
        """Initialize the Fetch server."""
        self.response_wrapper = response_wrapper or (lambda response: response)

    def register_with_mcp(self, mcp: FastMCP):
        """Register the tools with the MCP server."""

        # Register the tools with the MCP server, wrapped with the response wrapper.
        mcp.add_tool(self.response_wrapper(self.webpage_to_markdown))
        mcp.add_tool(self.response_wrapper(self.from_github))
        mcp.add_tool(self.response_wrapper(self.webpage))

    async def async_init(self):
        """Initialize the Fetch server asynchronously."""
        pass

    async def async_shutdown(self):
        """Shutdown the Fetch server asynchronously."""
        pass

    async def webpage_to_markdown(self, url: str) -> str:
        """
        Fetches a webpage and returns its content as markdown.

        Args:
            url: The URL of the webpage to fetch.

        Returns:
            The webpage content as a markdown string.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()  # Raise an exception for bad status codes
            html_content = response.text
            markdown_content = markdownify.markdownify(html_content)
            return markdown_content
        except httpx.RequestError as e:
            return f"Error fetching {url}: {e}"
        except httpx.HTTPStatusError as e:
            return f"Error fetching {url}: HTTP status code {e.response.status_code}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    async def webpage(self, url: str) -> str:
        """
        Fetches a webpage and strips out content not useful to an LLM or user.

        Args:
            url: The URL of the webpage to fetch.

        Returns:
            The cleaned text content of the webpage.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()  # Raise an exception for bad status codes
            html_content = response.text
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove script and style elements
            for script_or_style in soup(["script", "style"]):
                script_or_style.extract()

            # Remove common irrelevant tags (adjust as needed)
            irrelevant_tags = ["nav", "footer", "aside", "form", "input", "button"]
            for tag_name in irrelevant_tags:
                for tag in soup.find_all(tag_name):
                    tag.extract()

            # Get text and clean up whitespace
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            # Remove blank lines
            cleaned_text = "\n".join(line for line in lines if line)

            return cleaned_text
        except httpx.RequestError as e:
            return f"Error fetching {url}: {e}"
        except httpx.HTTPStatusError as e:
            return f"Error fetching {url}: HTTP status code {e.response.status_code}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    async def from_github(self, github_blob_url: str) -> str | Dict[str, str]:
        """
        Fetches content from a GitHub blob URL by converting it to a raw content URL.

        Args:
            github_blob_url: The GitHub blob URL (e.g., https://github.com/.../file.md).

        Returns:
            The fetched content as markdown or cleaned text, or an error dictionary.
        """
        raw_url_result = self._convert_github_blob_to_raw(github_blob_url)
        if isinstance(raw_url_result, dict) and "error" in raw_url_result:
            return raw_url_result  # Return error if URL conversion failed

        # Ensure raw_url is a string before proceeding
        if not isinstance(raw_url_result, str):
            return {"error": f"Unexpected result from URL conversion: {raw_url_result}"}

        raw_url: str = raw_url_result

        # Decide whether to return markdown or cleaned text based on the file extension
        if raw_url.lower().endswith((".md", ".markdown")):
            # For markdown files, return markdown content
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(raw_url)
                    response.raise_for_status()
                return response.text  # Return raw markdown content
            except httpx.RequestError as e:
                return {"error": f"Error fetching raw content from {raw_url}: {e}"}
            except httpx.HTTPStatusError as e:
                return {"error": f"Error fetching raw content from {raw_url}: HTTP status code {e.response.status_code}"}
            except Exception as e:
                return {"error": f"An unexpected error occurred: {e}"}
        else:
            # For other file types, use the new webpage tool
            return await self.webpage(raw_url)

    def _convert_github_blob_to_raw(self, github_blob_url: str) -> str | Dict[str, str]:
        """
        Converts a GitHub blob URL to a raw content URL.

        Args:
            github_blob_url: The GitHub blob URL.

        Returns:
            The raw content URL or an error dictionary if the URL is invalid.
        """
        # Example: https://github.com/dry-rb/dry-validation/blob/release-1.10/docsite/source/pattern-matching.html.md
        # Becomes: https://raw.githubusercontent.com/dry-rb/dry-validation/release-1.10/docsite/source/pattern-matching.html.md

        match = re.match(r"https://github.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)", github_blob_url)
        if not match:
            return {"error": f"Invalid GitHub blob URL format: {github_blob_url}"}

        owner, repo, branch, file_path = match.groups()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
        return raw_url
