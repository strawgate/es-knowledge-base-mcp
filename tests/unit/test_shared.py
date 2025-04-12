import inspect
from esdocmanagermcp.components.shared import format_search_results_plain_text


def test_format_search_results_empty():
    assert format_search_results_plain_text([]) == "No search results found."


def test_format_search_results_single_basic():
    results = [{"title": "Test Title 1", "url": "http://example.com/1"}]
    expected = inspect.cleandoc("""
        Title: Test Title 1
        URL: http://example.com/1
        ---
    """)
    assert format_search_results_plain_text(results) == expected


def test_format_search_results_single_with_match():
    results = [
        {
            "title": "Test Title 2",
            "url": "http://example.com/2",
            "match": [" snippet one ", "snippet two"],
        }
    ]
    expected = inspect.cleandoc("""
        Title: Test Title 2
        URL: http://example.com/2
        Relevant Snippets:
        - snippet one
        - snippet two
        ---
        """)
    assert format_search_results_plain_text(results) == expected


def test_format_search_results_single_with_non_array_content():
    results = [
        {
            "title": "Test Title 3",
            "url": "http://example.com/3",
            "content": " content one ",
        }
    ]
    expected = inspect.cleandoc("""
        Title: Test Title 3
        URL: http://example.com/3
        Content:
        - content one
        ---
    """)
    assert format_search_results_plain_text(results) == expected


def test_format_search_results_single_with_match_and_content():
    results = [
        {
            "title": "Test Title 4",
            "url": "http://example.com/4",
            "match": [" match snippet "],
            "content": [" content snippet "],
        }
    ]
    expected = inspect.cleandoc("""
        Title: Test Title 4
        URL: http://example.com/4
        Relevant Snippets:
        - match snippet
        ---
    """)
    assert format_search_results_plain_text(results) == expected


def test_format_search_results_multiple():
    results = [
        {"title": "Result A", "url": "http://a.com"},
        {"title": "Result B", "url": "http://b.com", "match": ["b match"]},
    ]
    expected = inspect.cleandoc("""
        Title: Result A
        URL: http://a.com
        ---
        Title: Result B
        URL: http://b.com
        Relevant Snippets:
        - b match
        ---
    """)
    assert format_search_results_plain_text(results) == expected


def test_format_search_results_missing_title():
    results = [{"url": "http://example.com/notitle"}]
    expected = inspect.cleandoc("""
        Title: No title found
        URL: http://example.com/notitle
        ---
    """)
    assert format_search_results_plain_text(results) == expected


def test_format_search_results_missing_url():
    results = [{"title": "No URL Title"}]
    expected = inspect.cleandoc("""
        Title: No URL Title
        URL: No URL found
        ---
    """)
    assert format_search_results_plain_text(results) == expected


def test_format_search_results_missing_both():
    results = [{}]
    expected = inspect.cleandoc("""
        Title: No title found
        URL: No URL found
        ---
    """)
    assert format_search_results_plain_text(results) == expected
