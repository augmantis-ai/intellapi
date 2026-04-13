"""OpenAPI loading and merge helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import yaml

from intellapi.scanner.ir import EndpointInfo, FieldInfo, IntermediateRepresentation, ModelInfo, ParamInfo


def load_openapi_spec(openapi_file: str | None = None, openapi_url: str | None = None) -> tuple[dict[str, Any], str]:
    """Load an OpenAPI spec from a local file or remote URL."""
    if bool(openapi_file) == bool(openapi_url):
        raise ValueError("Specify exactly one of openapi_file or openapi_url.")

    if openapi_file:
        path = Path(openapi_file).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"OpenAPI file not found: {path}")
        text = path.read_text(encoding="utf-8")
        return _parse_openapi_text(text, source=str(path))

    assert openapi_url is not None
    response = httpx.get(openapi_url, timeout=15.0)
    response.raise_for_status()
    return _parse_openapi_text(response.text, source=openapi_url)


def merge_openapi_into_ir(ir: IntermediateRepresentation, spec: dict[str, Any], source: str) -> IntermediateRepresentation:
    """Merge OpenAPI-derived endpoints and models into the IR."""
    merged = ir.model_copy(deep=True)
    info = spec.get("info", {}) if isinstance(spec.get("info"), dict) else {}
    if info.get("title"):
        merged.service_name = info["title"]

    source_evidence = list(merged.source_evidence.get("openapi", []))
    source_evidence.append(source)
    merged.source_evidence["openapi"] = source_evidence

    components = spec.get("components", {}) if isinstance(spec.get("components"), dict) else {}
    schemas = components.get("schemas", {}) if isinstance(components.get("schemas"), dict) else {}

    models_by_name = {model.name: model for model in merged.models}
    for schema_name, schema in schemas.items():
        if schema_name not in models_by_name:
            models_by_name[schema_name] = _schema_to_model(schema_name, schema, spec)

    merged.models = sorted(models_by_name.values(), key=lambda model: model.name)

    endpoints_by_key = {(ep.method.upper(), ep.path): ep for ep in merged.endpoints}
    paths = spec.get("paths", {}) if isinstance(spec.get("paths"), dict) else {}
    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        shared_params = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not isinstance(operation, dict):
                continue

            endpoint = _operation_to_endpoint(path_name, method.upper(), operation, shared_params, spec)
            key = (endpoint.method.upper(), endpoint.path)
            existing = endpoints_by_key.get(key)
            if existing is None:
                endpoints_by_key[key] = endpoint
            else:
                endpoints_by_key[key] = _merge_endpoint(existing, endpoint)

    merged.endpoints = sorted(
        endpoints_by_key.values(),
        key=lambda ep: (ep.path, ep.method),
    )
    return merged


def _parse_openapi_text(text: str, source: str) -> tuple[dict[str, Any], str]:
    """Parse JSON or YAML OpenAPI content."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise ValueError(f"OpenAPI spec from {source} is not a valid object.")
    if "openapi" not in data and "swagger" not in data:
        raise ValueError(f"File at {source} does not look like an OpenAPI spec.")
    return data, source


def _operation_to_endpoint(
    path_name: str,
    method: str,
    operation: dict[str, Any],
    shared_params: list[Any],
    spec: dict[str, Any],
) -> EndpointInfo:
    params: list[ParamInfo] = []
    all_params = list(shared_params or []) + list(operation.get("parameters", []) or [])
    for param in all_params:
        resolved = _resolve_ref(param, spec)
        if not isinstance(resolved, dict):
            continue
        schema = _resolve_ref(resolved.get("schema"), spec) if resolved.get("schema") else {}
        schema_type = schema.get("type") if isinstance(schema, dict) else None
        params.append(
            ParamInfo(
                name=resolved.get("name", "unknown"),
                type=schema_type or "any",
                required=bool(resolved.get("required")),
                location=resolved.get("in", "query"),
                description=resolved.get("description"),
            )
        )

    request_body = None
    rb = _resolve_ref(operation.get("requestBody"), spec) if operation.get("requestBody") else None
    if isinstance(rb, dict):
        request_body = _content_to_model(rb.get("content"), spec, fallback_name=f"{_operation_name(operation, method)}Request")

    response_model = None
    responses = operation.get("responses", {})
    if isinstance(responses, dict):
        for status_code, response in responses.items():
            if not str(status_code).startswith("2"):
                continue
            resolved = _resolve_ref(response, spec)
            if isinstance(resolved, dict):
                response_model = _content_to_model(
                    resolved.get("content"),
                    spec,
                    fallback_name=f"{_operation_name(operation, method)}Response",
                )
                if response_model:
                    break

    auth_required = None
    if "security" in operation:
        auth_required = bool(operation["security"])

    return EndpointInfo(
        method=method,
        path=path_name,
        handler_name=_operation_name(operation, method),
        docstring=operation.get("description") or operation.get("summary"),
        parameters=params,
        request_body=request_body,
        response_model=response_model,
        auth_required=auth_required,
        decorators=[],
        source_file=operation.get("operationId", "openapi"),
        line_number=0,
        confidence=0.95,
    )


def _operation_name(operation: dict[str, Any], method: str) -> str:
    return operation.get("operationId") or operation.get("summary") or f"{method.lower()}_operation"


def _content_to_model(content: Any, spec: dict[str, Any], fallback_name: str) -> ModelInfo | None:
    if not isinstance(content, dict):
        return None
    for media_type in ("application/json", "application/*+json", "*/*"):
        media = content.get(media_type)
        if not isinstance(media, dict):
            continue
        schema = _resolve_ref(media.get("schema"), spec)
        if not isinstance(schema, dict):
            continue
        if "$ref" in media.get("schema", {}):
            ref_name = media["schema"]["$ref"].rsplit("/", 1)[-1]
            return _schema_to_model(ref_name, schema, spec)
        return _schema_to_model(fallback_name, schema, spec)
    return None


def _schema_to_model(name: str, schema: Any, spec: dict[str, Any]) -> ModelInfo:
    resolved = _resolve_ref(schema, spec)
    if not isinstance(resolved, dict):
        return ModelInfo(name=name)

    fields: list[FieldInfo] = []
    required = set(resolved.get("required", []) or [])
    properties = resolved.get("properties", {})
    if isinstance(properties, dict):
        for field_name, field_schema in properties.items():
            field_resolved = _resolve_ref(field_schema, spec)
            field_type = _schema_type(field_resolved)
            fields.append(
                FieldInfo(
                    name=field_name,
                    type=field_type,
                    required=field_name in required,
                    description=field_resolved.get("description") if isinstance(field_resolved, dict) else None,
                )
            )
    elif resolved.get("type") == "array":
        item_schema = _resolve_ref(resolved.get("items"), spec)
        fields.append(
            FieldInfo(
                name="items",
                type=f"array[{_schema_type(item_schema)}]",
                required=True,
                description=resolved.get("description"),
            )
        )

    return ModelInfo(
        name=name,
        docstring=resolved.get("description"),
        fields=fields,
        source_file="openapi",
        line_number=0,
    )


def _schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "any"
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    schema_type = schema.get("type")
    if schema_type == "array":
        return f"array[{_schema_type(schema.get('items'))}]"
    return schema_type or "any"


def _resolve_ref(value: Any, spec: dict[str, Any]) -> Any:
    if not isinstance(value, dict) or "$ref" not in value:
        return value

    ref = value["$ref"]
    if not ref.startswith("#/"):
        return value

    current: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(current, dict):
            return value
        current = current.get(part)
        if current is None:
            return value
    return current


def _merge_endpoint(existing: EndpointInfo, incoming: EndpointInfo) -> EndpointInfo:
    """Prefer source-extracted fields but backfill from OpenAPI where empty."""
    merged = existing.model_copy(deep=True)
    if not merged.docstring:
        merged.docstring = incoming.docstring
    if not merged.parameters:
        merged.parameters = incoming.parameters
    if merged.request_body is None:
        merged.request_body = incoming.request_body
    if merged.response_model is None:
        merged.response_model = incoming.response_model
    if merged.auth_required is None:
        merged.auth_required = incoming.auth_required
    merged.confidence = max(merged.confidence, incoming.confidence)
    return merged
