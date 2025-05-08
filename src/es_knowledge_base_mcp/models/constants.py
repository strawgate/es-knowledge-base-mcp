"""Constants used across the knowledge base MCP."""

from typing import Any

BASE_LOGGER_NAME = "knowledge-base-mcp"

SEMANTIC_TEXT_MAPPING: dict[str, Any] = {
    "type": "semantic_text",
    "inference_id": ".elser-2-elasticsearch",
    "model_settings": {"service": "elasticsearch", "task_type": "sparse_embedding"},
}

CRAWLER_INDEX_MAPPING: dict[str, Any] = {
    "properties": {
        "@timestamp": {"type": "date"},
        "body": SEMANTIC_TEXT_MAPPING,
        "headings": SEMANTIC_TEXT_MAPPING,
        "id": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "last_crawled_at": {"type": "date"},
        "links": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "meta_keywords": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "title": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "url": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "url_host": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "url_path": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "url_path_dir1": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "url_path_dir2": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "url_path_dir3": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "url_port": {"type": "long"},
        "url_scheme": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
    }
}
