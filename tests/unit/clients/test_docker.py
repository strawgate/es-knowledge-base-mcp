import pytest
import tarfile
from es_knowledge_base_mcp.clients.docker import InjectFile


@pytest.mark.parametrize(
    "filename, content, expected_filename_in_tar",
    [
        ("test_file.txt", "hello world", "test_file.txt"),
        ("/config/file.yml", "key: value", "config/file.yml"),
        ("empty_file.txt", "", "empty_file.txt"),
    ],
    ids=["basic_file", "file_with_path", "empty_file"],
)
def test_inject_file_to_tar_stream(filename: str, content: str, expected_filename_in_tar: str):
    """Tests the InjectFile.to_tar_stream method."""
    inject_file = InjectFile(filename=filename, content=content)
    tar_stream = inject_file.to_tar_stream()

    # Read the tar stream back to verify content
    with tarfile.open(fileobj=tar_stream, mode="r") as tar:
        members = tar.getmembers()
        assert len(members) == 1, "Expected exactly one file in the tar archive"

        tarinfo = members[0]
        assert tarinfo.name == expected_filename_in_tar, (
            f"Expected filename in tar to be '{expected_filename_in_tar}' but got '{tarinfo.name}'"
        )
        assert tarinfo.size == len(content.encode("utf-8")), (
            f"Expected file size to be {len(content.encode('utf-8'))} but got {tarinfo.size}"
        )

        extracted_file = tar.extractfile(tarinfo)
        assert extracted_file is not None, "Failed to extract file from tar"
        extracted_content = extracted_file.read().decode("utf-8")
        assert extracted_content == content, f"Expected file content to be '{content}' but got '{extracted_content}'"
