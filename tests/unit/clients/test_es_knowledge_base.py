import pytest

from es_knowledge_base_mcp.clients.es_knowledge_base import ElasticsearchKnowledgeBaseClient


@pytest.mark.parametrize(
    ("url", "expected_index_name"),
    [
        ("http://www.python.org/docs/index.html", "www_python_org.docs.index_html"),
        ("https://www.python.org/docs/index.html", "www_python_org.docs.index_html"),
        ("https://example.com/path/to/resource?query=1", "example_com.path.to.resourcequery1"),
        (
            "https://example.com/very-long-path/that-exceeds-the-fifty-character-limit/by-quite-a-bit",
            "example_com.very_long_path.that_exceeds_the_fifty",
        ),
        ("https://domain_with_underscores.com/path", "domain_with_underscores_com.path"),
        ("https://domain-with-hyphens.com/path", "domain_with_hyphens_com.path"),
        ("https://example.com/path#fragment", "example_com.pathfragment"),
        ("example.com", "example_com"),
        ("http://localhost:8000/api/v1", "localhost8000.api.v1"),
        ("https://!@#$%^&*().com/", "com"),
        ("https://a_b-c.d/e.f-g/h", "a_b_c_d.e_f_g.h"),
        (
            "https://this.is.a.very.long.domain.name.that.will.surely.be.truncated/path",
            "this_is_a_very_long_domain_name_that_will_surely_b",
        ),
        ("http://127.0.0.1/", "127_0_0_1"),
        ("", ""),  # Empty input
        ("https://Example.com/Path", "example_com.path"),
    ],
)
def test_url_to_index_name(url: str, expected_index_name: str):
    """Tests the url_to_index_name function with various inputs."""
    assert ElasticsearchKnowledgeBaseClient._url_to_index_name(url) == expected_index_name


# @pytest.mark.parametrize(
#     "kb_create_proto",
#     [
#         KnowledgeBaseCreateProto(
#             name="Test KB 1",
#             data_source="http://example.com/kb1",
#             description="Description for KB 1",
#             type="web",
#         ),
#         KnowledgeBaseCreateProto(
#             name="Test KB 2",
#             data_source="file:///path/to/kb2",
#             description="",  # Test missing description with empty string
#             type="file",
#         ),
#     ],
#     ids=["full_fields", "missing_description"],
# )
# def test_build_metadata_mapping(kb_create_proto: KnowledgeBaseCreateProto, snapshot: SnapshotAssertion):
#     """Tests the _build_metadata_mapping method."""
#     # Use mock objects for settings and client
#     mapping = ElasticsearchKnowledgeBaseClient._build_metadata_mapping(kb_create_proto)
#     assert mapping == snapshot


# @pytest.mark.parametrize(
#     "phrase, size, fragments",
#     [
#         ("search query", 5, 5),
#         ("another phrase", 10, 3),
#         ("", 5, 5),  # Empty phrase
#         ("phrase with special characters !@#$", 5, 5),
#     ],
#     ids=["basic", "custom_size_fragments", "empty_phrase", "special_chars"],
# )
# def test_phrase_to_query(phrase: str, size: int, fragments: int, snapshot: SnapshotAssertion):
#     """Tests the _phrase_to_query classmethod."""
#     query = ElasticsearchKnowledgeBaseClient._phrase_to_query(phrase, size, fragments)
#     assert query == snapshot


# @pytest.mark.parametrize(
#     "hit, knowledge_base_name",
#     [
#         (  # Case 1: Full hit with source and highlight
#             {
#                 "_index": "test-index",
#                 "_id": "1",
#                 "_score": 1.5,
#                 "_source": {"title": "Doc Title 1", "url": "http://example.com/doc1", "body": "This is the full body content."},
#                 "highlight": {"body": ["This is the <em>highlighted</em> content."]},
#             },
#             "Test KB",
#         ),
#         (  # Case 2: Hit with only source
#             {
#                 "_index": "test-index",
#                 "_id": "2",
#                 "_score": 0.8,
#                 "_source": {"title": "Doc Title 2", "url": "http://example.com/doc2", "body": "Another full body content."},
#                 "highlight": {},  # No highlight
#             },
#             "Test KB",
#         ),
#         (  # Case 3: Hit with missing source fields
#             {
#                 "_index": "test-index",
#                 "_id": "3",
#                 "_score": 0.5,
#                 "_source": {"url": "http://example.com/doc3"},  # Missing title and body
#                 "highlight": {"body": ["Highlighted content only."]},
#             },
#             "Test KB",
#         ),
#         (  # Case 4: Hit with empty highlight
#             {
#                 "_index": "test-index",
#                 "_id": "4",
#                 "_score": 0.6,
#                 "_source": {"title": "Doc Title 4", "url": "http://example.com/doc4", "body": "Content with empty highlight."},
#                 "highlight": {"body": []},  # Empty highlight list
#             },
#             "Test KB",
#         ),
#         (  # Case 5: Hit with unexpected score type (should still work)
#             {
#                 "_index": "test-index",
#                 "_id": "5",
#                 "_score": "1.2",  # Score as string
#                 "_source": {"title": "Doc Title 5", "url": "http://example.com/doc5", "body": "Content with string score."},
#                 "highlight": {"body": ["Highlighted content."]},
#             },
#             "Test KB",
#         ),
#     ],
#     ids=["full_hit", "source_only", "missing_source_fields", "empty_highlight", "string_score"],
# )
# def test_hit_to_document(hit: dict, knowledge_base_name: str, snapshot: SnapshotAssertion):
#     """Tests the _hit_to_document method."""
#     # Use mock objects for settings and client
#     document = ElasticsearchKnowledgeBaseClient._hit_to_document(knowledge_base_name, hit)
#     assert document.model_dump() == snapshot
