# async def update_dynamic_resources():
#     """
#     Updates MCP dynamic resources based on available documentation indices.
#     Creates a resource for each index, allowing users to search within it.
#     """
#     logger.info("Updating dynamic search resources...")

#     index_names: list[str] = await list_documentation_types()  # Wrapped call

#     if not index_names:
#         logger.info("No documentation indices found, no resources to update.")
#         # Consider removing existing resources if desired? For now, just don't add.
#         return

#     for index_name in index_names:
#         # Define the actual handler function for this specific index
#         # This closure captures the current index_name

#         # remove the index prefix from the index_name for the uri
#         # This allows for a cleaner URI
#         prefix = searcher.settings.es_index_prefix
#         name_without_prefix = (
#             index_name.split(prefix + "-")[1]
#             if index_name.startswith(prefix + "-")
#             else index_name
#         )

#         async def dynamic_search_wrapper(
#             query: str, _index=index_name
#         ) -> Dict[str, Any]:  # Changed signature
#             search_results = await search_documentation(index_name=_index, query=query)

#             return {"search_results": search_results}

#         uri = f"docs://{name_without_prefix}/{{query}}"
#         name = f"docs_{name_without_prefix}"
#         description = "Search {name_without_prefix} for documentation."
#         mime_type = "application/json"

#         logger.info(
#             "Registering dynamic documentation resource template for index: %s with URI: %s",
#             index_name,
#             uri,
#         )

#         @mcp.resource(
#             uri=uri,
#             name=name,  # Unique name for each index to avoid conflicts
#             description=description,
#             mime_type=mime_type,  # Ensure consistent MIME type for all dynamic resources
#         )
#         async def docs_resource(query: str):
#             """
#             Wrapper function to call the dynamic resource handler.
#             This allows the MCP to route requests to the appropriate handler.
#             """
#             # Call the handler function with the index name and query
#             return await dynamic_search_wrapper(_index=index_name, query=query)

#     logger.info("Finished updating dynamic search resources.")
