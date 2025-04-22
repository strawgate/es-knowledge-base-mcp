# Unit Test Plan for `es_knowledge_base_mcp/clients`

This plan outlines the unit tests to be written for specific functions and methods in the `es_knowledge_base_mcp/clients` directory that currently lack coverage and are suitable for unit testing based on the criteria of being helper functions, class methods, or easy-to-test methods with minimal setup. The plan incorporates the use of `pytest` parametrization and `syrupy` for snapshot testing where appropriate.

## Functions/Methods to Test:

1.  `src/es_knowledge_base_mcp/clients/docker.py`: `InjectFile.to_tar_stream`
2.  `src/es_knowledge_base_mcp/clients/es_knowledge_base.py`: `_build_metadata_mapping`
3.  `src/es_knowledge_base_mcp/clients/es_knowledge_base.py`: `_phrase_to_query` (classmethod)
4.  `src/es_knowledge_base_mcp/clients/es_knowledge_base.py`: `_hit_to_document`

## Test Plan Details:

### 1. `src/es_knowledge_base_mcp/clients/docker.py`: `InjectFile.to_tar_stream`

*   **File:** `tests/unit/clients/test_docker.py` (Create this file if it doesn't exist)
*   **Test Function:** `test_inject_file_to_tar_stream`
*   **Approach:** Use `pytest.mark.parametrize` to test different scenarios.
*   **Test Cases:**
    *   Basic filename and content.
    *   Filename including directory paths (e.g., `/config/file.yml`).
    *   Empty content.
*   **Assertion Method:** Directly assert on the content and structure of the generated tar stream by reading it back using the `tarfile` module. Verify the presence of the correct file, its name within the archive, and its content. Snapshot testing is not suitable for binary streams.

### 2. `src/es_knowledge_base_mcp/clients/es_knowledge_base.py`: `_build_metadata_mapping`

*   **File:** `tests/unit/clients/test_es_knowledge_base.py` (Add to this existing file)
*   **Test Function:** `test_build_metadata_mapping`
*   **Approach:** Use `pytest.mark.parametrize` to test different `KnowledgeBaseCreateProto` inputs.
*   **Test Cases:**
    *   A `KnowledgeBaseCreateProto` object with all fields (`name`, `data_source`, `description`, `type`) populated.
    *   A `KnowledgeBaseCreateProto` object where some optional fields (`description`) are missing or `None`.
*   **Assertion Method:** Use `syrupy` snapshot testing (`assert generated_mapping == snapshot`) to verify the structure and content of the generated Elasticsearch `_meta` dictionary for each parameterized input.

### 3. `src/es_knowledge_base_mcp/clients/es_knowledge_base.py`: `_phrase_to_query` (classmethod)

*   **File:** `tests/unit/clients/test_es_knowledge_base.py` (Add to this existing file)
*   **Test Function:** `test_phrase_to_query`
*   **Approach:** Use `pytest.mark.parametrize` to test various combinations of `phrase`, `size`, and `fragments` inputs.
*   **Test Cases:**
    *   A sample search phrase with default `size` and `fragments`.
    *   A sample search phrase with custom `size` and `fragments` values.
    *   An empty search phrase.
    *   A phrase with special characters (if applicable to the query structure).
*   **Assertion Method:** Use `syrupy` snapshot testing (`assert generated_query == snapshot`) to verify the structure and content of the generated Elasticsearch query body dictionary for each parameterized input.

### 4. `src/es_knowledge_base_mcp/clients/es_knowledge_base.py`: `_hit_to_document`

*   **File:** `tests/unit/clients/test_es_knowledge_base.py` (Add to this existing file)
*   **Test Function:** `test_hit_to_document`
*   **Approach:** Use `pytest.mark.parametrize` to test different Elasticsearch hit dictionary structures.
*   **Test Cases:**
    *   A sample hit dictionary including both `_source` (with `title`, `url`, `body`) and `highlight` (with `body` highlights).
    *   A sample hit dictionary including only the `_source` section (with `title`, `url`, `body`).
    *   A hit dictionary where `_source` is missing or incomplete.
    *   A hit dictionary where `highlight` is present but empty or incomplete.
    *   A hit dictionary with unexpected data types for fields like `_score`.
*   **Assertion Method:** Use `syrupy` snapshot testing (`assert generated_document.model_dump() == snapshot`) to verify the structure and content of the generated `KnowledgeBaseDocument` object (converting it to a dictionary using `model_dump()` for snapshot comparison) for each parameterized input.

## Implementation Notes:

*   Ensure necessary imports (`pytest`, `syrupy`, relevant classes/dataclasses) are present in the test files.
*   For snapshot tests, run `pytest` with the `--snapshot-update` flag initially to generate the snapshot files. Review the generated snapshots to ensure they match the expected output.
*   Use clear and descriptive test case IDs in parametrization.