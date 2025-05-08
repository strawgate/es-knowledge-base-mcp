"""Base models and utilities for data structures."""

from typing import Any

from pydantic import BaseModel, ConfigDict


def prune_schema(schema: dict[str, Any]) -> None:
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)


class ExportableModel(BaseModel):
    """Base model for exportable objects, providing a method to convert to a dictionary."""

    model_config = ConfigDict(json_schema_extra=prune_schema)

    def __getstate__(self):
        """Only include the underlying dictionary in the state for serialization."""
        return self.model_dump()
