"""Renderer tests."""

from intellapi.generator.renderer import render_markdown, render_plaintext
from intellapi.llm.schemas import DocumentationDraft, EndpointDoc, FieldDoc, ModelDoc, ParameterDoc, RequestBodyDoc, ResponseDoc


def _sample_draft() -> DocumentationDraft:
    return DocumentationDraft(
        service_overview="Sample API for renderer tests.",
        auth_summary="Bearer token required for write operations.",
        endpoints=[
            EndpointDoc(
                method="POST",
                path="/users",
                summary="Create user",
                description="Creates a new user.",
                auth_required=True,
                parameters=[ParameterDoc(name="trace_id", location="header", type="string", required=False, description="Trace header")],
                request_body=RequestBodyDoc(
                    schema_name="UserCreate",
                    fields=[FieldDoc(name="name", type="string", required=True, description="Full name")],
                ),
                response=ResponseDoc(
                    status_code=201,
                    schema_name="UserResponse",
                    fields=[FieldDoc(name="id", type="integer", required=True, description="Identifier")],
                ),
            )
        ],
        models=[ModelDoc(name="UserCreate", description="Input schema", fields=[FieldDoc(name="name", type="string", required=True, description="Full name")])],
        error_handling="Validation errors return 400.",
        dependencies="fastapi, pydantic",
        caveats=["Verify authentication header name."],
    )


def test_render_markdown_contains_sections():
    markdown = render_markdown(_sample_draft())
    assert "## Overview" in markdown
    assert "## Endpoints" in markdown
    assert "`POST` /users" in markdown
    assert "Authentication required" in markdown
    assert "## Data Models" in markdown


def test_render_plaintext_contains_sections():
    plaintext = render_plaintext(_sample_draft())
    assert "OVERVIEW" in plaintext
    assert "ENDPOINTS" in plaintext
    assert "POST /users" in plaintext
    assert "DATA MODELS" in plaintext
