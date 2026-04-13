"""DocumentationDraft schema — the structured output contract for LLM responses.

The LLM is prompted to return JSON matching this schema.
The response is validated locally via Pydantic, with one repair retry on failure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Any
import json

class EndpointDoc(BaseModel):
    """Documentation for a single API endpoint."""

    method: str
    path: str
    summary: str
    description: str
    parameters: list[ParameterDoc] = Field(default_factory=list)
    request_body: RequestBodyDoc | None = None
    response: ResponseDoc | None = None
    auth_required: bool = False
    example_request: str | None = None
    example_response: str | None = None


class ParameterDoc(BaseModel):
    """Documentation for a single parameter."""

    name: str
    location: str = "query"  # query | path | header | body
    type: str = "string"
    required: bool = True
    description: str = ""


class RequestBodyDoc(BaseModel):
    """Documentation for a request body."""

    content_type: str = "application/json"
    schema_name: str | None = None
    fields: list[FieldDoc] = Field(default_factory=list)
    example: Any | None = None

    @field_validator("example", mode="before")
    @classmethod
    def stringify_example(cls, v: Any) -> str | None:
        if isinstance(v, (dict, list)):
            return json.dumps(v, indent=2)
        return str(v) if v is not None else None


class ResponseDoc(BaseModel):
    """Documentation for a response."""

    status_code: int = 200
    content_type: str = "application/json"
    schema_name: str | None = None
    fields: list[FieldDoc] = Field(default_factory=list)
    example: Any | None = None

    @field_validator("example", mode="before")
    @classmethod
    def stringify_example(cls, v: Any) -> str | None:
        if isinstance(v, (dict, list)):
            return json.dumps(v, indent=2)
        return str(v) if v is not None else None


class FieldDoc(BaseModel):
    """Documentation for a single field in a schema."""

    name: str
    type: str = "string"
    required: bool = True
    description: str = ""


class ModelDoc(BaseModel):
    """Documentation for a data model / schema."""

    name: str
    description: str = ""
    fields: list[FieldDoc] = Field(default_factory=list)


class ExampleDoc(BaseModel):
    """A usage example for the API."""

    title: str
    description: str
    code: str
    language: str = "bash"  # bash, python, javascript, etc.


class DocumentationDraft(BaseModel):
    """The complete documentation output from the LLM.

    This is the JSON schema the LLM is instructed to return.
    It is validated locally via Pydantic after parsing.
    """

    service_overview: str
    auth_summary: str | None = None
    endpoints: list[EndpointDoc] = Field(default_factory=list)
    models: list[ModelDoc] = Field(default_factory=list)
    error_handling: str = ""
    dependencies: str | None = None
    example_usage: list[ExampleDoc] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ─── Update forward refs (needed for nested models) ────────────────────────
# Pydantic v2 handles this automatically, but be explicit for clarity.
EndpointDoc.model_rebuild()
RequestBodyDoc.model_rebuild()
ResponseDoc.model_rebuild()
