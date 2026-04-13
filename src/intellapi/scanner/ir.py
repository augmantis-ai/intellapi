"""Intermediate Representation — framework-agnostic data models.

All extractors produce an IntermediateRepresentation, regardless of
the source language or framework. This is the contract between the
scanner layer and the LLM/generator layers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParamInfo(BaseModel):
    """A single parameter for an endpoint."""

    name: str
    type: str | None = None
    required: bool = True
    default: str | None = None
    location: str = "query"  # query | path | header | body
    description: str | None = None


class FieldInfo(BaseModel):
    """A single field in a data model."""

    name: str
    type: str | None = None
    required: bool = True
    default: str | None = None
    description: str | None = None


class ModelInfo(BaseModel):
    """A data model / schema (Pydantic, dataclass, serializer, DTO, etc.)."""

    name: str
    docstring: str | None = None
    fields: list[FieldInfo] = Field(default_factory=list)
    source_file: str | None = None
    line_number: int | None = None


class EndpointInfo(BaseModel):
    """A single API endpoint extracted from source code."""

    method: str  # GET, POST, PUT, DELETE, PATCH, etc.
    path: str  # /api/users/{id}
    handler_name: str
    docstring: str | None = None
    parameters: list[ParamInfo] = Field(default_factory=list)
    request_body: ModelInfo | None = None
    response_model: ModelInfo | None = None
    auth_required: bool | None = None
    decorators: list[str] = Field(default_factory=list)
    source_file: str = ""
    line_number: int = 0
    confidence: float = 1.0  # 0.0–1.0, lower means less certain


class IntermediateRepresentation(BaseModel):
    """Framework-agnostic representation of an analyzed codebase.

    This is the single data structure that flows from extractors
    into the LLM prompt builder and documentation renderer.
    """

    service_name: str = "API Service"
    framework: str = "unknown"  # fastapi | flask | django_rest | express | nextjs | sveltekit
    language: str = "unknown"  # python | javascript | typescript
    endpoints: list[EndpointInfo] = Field(default_factory=list)
    models: list[ModelInfo] = Field(default_factory=list)
    middleware: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    auth_patterns: list[str] = Field(default_factory=list)
    source_evidence: dict[str, list[str]] = Field(default_factory=dict)
    extraction_warnings: list[str] = Field(default_factory=list)
    # Maps section names to source file paths for traceability
