"""Prompt templates for documentation generation.

The system prompt instructs the LLM to:
- Use ONLY information from the provided source code
- Return valid JSON matching the DocumentationDraft schema
- Mark uncertain sections with explicit caveats
- Include realistic request/response examples
"""

from __future__ import annotations

import json

from intellapi.llm.schemas import DocumentationDraft
from intellapi.scanner.ir import IntermediateRepresentation


def build_system_prompt() -> str:
    """Build the system prompt that instructs the LLM on output format and rules."""
    schema = DocumentationDraft.model_json_schema()

    return f"""You are an expert technical writer and API architect. Your task is to generate
professional, comprehensive API documentation based on the source code analysis provided to you.

## Rules

1. **Adhere to Code Truth**: Use ONLY information from the provided source code analysis. Do NOT invent endpoints, parameters, or behaviors that are not evidenced in the source.
2. **Handle Ambiguity Gracefully**: When you are uncertain about something (e.g., exact response format, auth mechanism, error codes), add it to the "caveats" list with a clear description of what needs verification.
3. **Developer-Centric Focus**: Write documentation that a developer can immediately use to integrate with the API. Keep explanations concise, clear, and actionable.
4. **Rich Examples**: Include realistic JSON example requests and responses with plausible sample data. **CRITICAL:** For any `example` fields in the schema, provide them as native nested JSON objects/arrays directly, do NOT use stringified/escaped JSON strings (e.g. use `{{"example": {{"id": 1}}}}` instead of `{{"example": "{{\\"id\\": 1}}"}}`). Our parser handles native types.
5. **Logical Grouping**: Ensure the `service_overview` makes logical sense. Note that if no specific groups are given, aim to provide a comprehensive overall view.
6. **Authentication & Security**: Clearly describe authentication requirements if they are detected, or declare it in caveats if it is unclear.
7. **Succinct Explanations**: Give brief but valuable summaries for endpoints, using standard HTTP semantics to infer constraints (like what errors might be thrown, e.g., 404 for 'get by ID' or 401 for 'auth required').

## Output Format

Return ONLY valid JSON matching this exact schema. No markdown wrapping the JSON (unless necessary to parse), no commentary, no conversational text — just the raw JSON object.

```json
{json.dumps(schema, indent=2)}
```

Remember: output ONLY the JSON object, nothing else."""


def build_user_prompt(ir: IntermediateRepresentation, max_output_tokens: int = 8192) -> str:
    """Build the user prompt containing the extracted code analysis."""
    sections: list[str] = []

    sections.append(f"# Source Code Analysis: {ir.service_name}")
    
    # Heuristic: A rich endpoint with examples takes ~800 tokens to generate.
    safe_endpoint_count = max_output_tokens // 800

    if len(ir.endpoints) > safe_endpoint_count:
        sections.append(
            "\n**CRITICAL TOKEN LIMIT WARNING:**\n"
            f"This codebase has many endpoints. Your max output capacity is {max_output_tokens}. "
            "To prevent your JSON response from being truncated by max-token limits, "
            "you MUST OMIT all `example`, `example_request`, and `example_response` payload fields (set them to null) "
            "for ALL endpoints and models. Keep all textual descriptions extremely brief (1 sentence max)."
        )

    sections.append(f"Framework: {ir.framework}")
    sections.append(f"Language: {ir.language}")

    if ir.dependencies:
        sections.append(f"\n## Dependencies\n{', '.join(ir.dependencies)}")

    if ir.auth_patterns:
        sections.append(f"\n## Authentication Patterns\n" + "\n".join(
            f"- {p}" for p in ir.auth_patterns
        ))

    if ir.middleware:
        sections.append(f"\n## Middleware\n" + "\n".join(
            f"- {m}" for m in ir.middleware
        ))

    if ir.extraction_warnings:
        sections.append(f"\n## Extraction Warnings\n" + "\n".join(
            f"- {warning}" for warning in ir.extraction_warnings
        ))

    if ir.endpoints:
        sections.append("\n## Endpoints")
        for ep in ir.endpoints:
            sections.append(f"\n### {ep.method} {ep.path}")
            sections.append(f"Handler: {ep.handler_name}")
            sections.append(f"Source: {ep.source_file}:{ep.line_number}")
            sections.append(f"Confidence: {ep.confidence:.0%}")

            if ep.docstring:
                sections.append(f"Docstring: {ep.docstring}")

            if ep.decorators:
                sections.append(f"Decorators: {', '.join(ep.decorators)}")

            if ep.parameters:
                sections.append("Parameters:")
                for p in ep.parameters:
                    req = "required" if p.required else "optional"
                    sections.append(
                        f"  - {p.name}: {p.type or 'any'} ({p.location}, {req})"
                    )

            if ep.request_body:
                sections.append(f"Request Body: {ep.request_body.name}")
                for f in ep.request_body.fields:
                    sections.append(f"  - {f.name}: {f.type or 'any'}")

            if ep.response_model:
                sections.append(f"Response Model: {ep.response_model.name}")
                for f in ep.response_model.fields:
                    sections.append(f"  - {f.name}: {f.type or 'any'}")

            if ep.auth_required is not None:
                sections.append(
                    f"Auth: {'required' if ep.auth_required else 'not required'}"
                )

    if ir.models:
        sections.append("\n## Data Models")
        for model in ir.models:
            sections.append(f"\n### {model.name}")
            if model.docstring:
                sections.append(f"Description: {model.docstring}")
            for f in model.fields:
                req = "required" if f.required else "optional"
                sections.append(f"  - {f.name}: {f.type or 'any'} ({req})")

    return "\n".join(sections)


def build_repair_prompt(original_response: str, error_message: str) -> str:
    """Build a repair prompt when the LLM's JSON output fails validation."""
    return f"""Your previous response was not valid JSON or did not match the required schema.

Error: {error_message}

Your previous response (first 2000 chars):
{original_response[:2000]}

Please fix the JSON and return ONLY the corrected JSON object matching the schema.
Do not include any markdown formatting, code fences, or commentary."""
