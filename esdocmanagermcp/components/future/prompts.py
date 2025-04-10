# @mcp.prompt()
# async def get_started_with_documentation() -> str:
#     """When using the docs tool, always start by searching for dependencies, finding the web url of the online documentation, and then using the crawl_domain tool to crawl the documentation."""
#     return [
#         "It's always a great idea to have documentation available when starting a new project. You can use the 'crawl_domain' tool to crawl a website and index its documentation into Elasticsearch. This will allow you to search through the documentation using the 'search_documentation' tool."
#         "Just review the major runtime and development dependencies in the project and grab the documentation for those dependencies."
#         "Review the other prompts for more information on how to use the tools."
#     ]

# @mcp.prompt()
# async def list_documentation_indices() -> str:
#     """Provides guidance on how to use the 'list_doc_indices' tool to see available documentation indices (which correspond to searchable resources)."""
#     return "To see which documentation sets have been crawled and are available for searching, use the 'list_doc_indices' tool."


# @mcp.prompt()
# async def search_documentation_prompt(query: str) -> str:
#     """Provides guidance on how to search crawled documentation using the available dynamic resources (e.g., 'Search: elastic-docs')."""
#     logger.info(
#         f"Prompt received: Guidance for searching documentation (example query: '{query}')."
#     )
#     indices = await searcher.list_doc_indices()

#     guidance = (
#         "To search crawled documentation, use the dynamic resources provided by the server. "
#         "Searching simply entails entering in plain text what you're looking for. "
#         "These resources typically look like 'search_<documentation_suffix>'.\n\n"
#         "You can see the available documentation sets by using the 'list_doc_indices' tool.\n"
#         f"{', '.join(indices)}"
#     )
#     return guidance


# @mcp.prompt(
#     description="Provides guidance on how to use the 'crawl_complex_domain' tool to crawl a website and index its documentation into Elasticsearch."
# )
# async def crawl_custom_website_documentation(
#     url,
# ) -> str:
#     """Provides guidance on using the 'crawl_complex_domain' tool."""
#     logger.info(
#         f"Prompt received: Guidance for crawl_complex_domain tool url: {url}."
#     )

#     # Extract domain from the URL, use url_parse to get the netloc, keep the www and scheme but nothing after the tld
#     parsed_url = urlparse(url)
#     domain = parsed_url.netloc
#     scheme = parsed_url.scheme + "://"
#     seed_url = url
#     # the filter pattern is normally the second last part of the path
#     # e.g., https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html -> https://www.elastic.co/guide/en/elasticsearch/reference/current/
#     path_components = parsed_url.path.split("/")
#     filter_pattern = "/".join(
#         path_components[: len(path_components) - 1]
#     ) if len(path_components) >= 2 else parsed_url.path

#     # take the domain and filtered_path, and convert
#     #www_elastic_co.guide_en_elasticsearch_reference_current
#     recommended_index_suffix = f"{domain.replace('.', '_')}.{'_'.join(path_components[1:-1])}"

#     guidance = (
#         "To crawl a website and index its documentation, use the 'crawl_domain' tool. "
#         "This tool runs the Elastic web crawler in a Docker container.\n\n"
#         "Required parameters:\n"
#         f"  - domain: The primary domain name (e.g., '{scheme + "://" + domain or 'https://www.example.com'}'). Must include scheme. Cannot include a path\n"
#         f"  - seed_url: The starting URL for the crawl (e.g., '{seed_url or 'https://www.example.com/docs/index.html'}').\n"
#         f"  - filter_pattern: A URL prefix the crawler should stay within (e.g., '{filter_pattern or '/docs/'}').\n"
#         f"  - output_index_suffix: A suffix added to '{searcher.settings.es_index_prefix}-' to create the final index name (e.g., '{recommended_index_suffix or 'my-docs'}' results in '{searcher.settings.es_index_prefix}-{recommended_index_suffix or 'my-docs'}').\n\n"
#         "The tool will start the crawl in the background and return a message with the container ID.\n"
#         "Use 'list_crawls', 'get_crawl_status', and 'get_crawl_logs' to monitor progress. Crawling can take some time so no need to check on status constantly.\n"
#         "Based on the url you provided me, you should run:\n"
#         f"  crawl_domain(domain='{domain}', seed_url='{seed_url}', filter_pattern='{filter_pattern}', output_index_suffix='{recommended_index_suffix}')\n\n"
#     )
#     return guidance


# @mcp.prompt(
#     description="Provides guidance on how to use the 'crawl_complex_domain' tool to crawl a website and index its documentation into Elasticsearch."
# )
# async def crawl_web_documentation(
#     url,
# ) -> str:
#     """Provides guidance on using the 'crawl_domains' tool."""
#     logger.info(
#         f"Prompt received: Guidance for crawl_domains tool url: {url}."
#     )

#     guidance = (
#         "To crawl many websites and index their documentation, use the 'crawl_domains' tool."
#         "The best way to use this tool is to first review the major runtime and development dependencies in the project and find the documentation for those dependencies. "
#         "Then, pass the URLs, all at once, to the crawl_domains tool. It's better to grab more documentation than you need!\n\n"
#     )
#     return guidance


# endregion Prompts
