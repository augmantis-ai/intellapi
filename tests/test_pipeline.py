"""Pipeline regression tests."""

from __future__ import annotations

import json
from pathlib import Path

from intellapi.config import IntellapiConfig, OutputFormat, Provider
from intellapi.generator.pipeline import run_pipeline
from intellapi.llm.schemas import DocumentationDraft


class TestPipeline:
    def test_source_only_fastapi_generation_uses_python_extractor(self, monkeypatch, tmp_path):
        """A source-only FastAPI app should generate through the extractor pipeline."""
        fixture_dir = Path(__file__).parent / "fixtures" / "sample_fastapi"

        class FakeLLMClient:
            def __init__(self, config):
                self.config = config

            def generate_documentation(self, ir):
                assert ir.service_name == "Sample API"
                assert len(ir.endpoints) == 8
                assert any(endpoint.handler_name == "create_user" for endpoint in ir.endpoints)
                return DocumentationDraft(
                    service_overview="Sample API generated from source.",
                    endpoints=[],
                    models=[],
                    error_handling="none",
                    caveats=[],
                )

        monkeypatch.setattr("intellapi.generator.pipeline.LLMClient", FakeLLMClient)

        config = IntellapiConfig(
            provider=Provider.OPENAI_COMPATIBLE,
            api_key="fake-key",
            output_path=str(tmp_path / "docs" / "fastapi.md"),
        )

        output_path = run_pipeline(fixture_dir, config)
        assert output_path == (tmp_path / "docs" / "fastapi.md").resolve()
        assert output_path.exists()

    def test_source_only_nextjs_generation_uses_node_extractor(self, monkeypatch, tmp_path):
        """A source-only Next.js app should generate through the Node extractor pipeline."""
        fixture_dir = Path(__file__).parent / "fixtures" / "sample_nextjs"

        class FakeLLMClient:
            def __init__(self, config):
                self.config = config

            def generate_documentation(self, ir):
                assert ir.service_name == "sample-nextjs-app"
                assert {(endpoint.method, endpoint.path) for endpoint in ir.endpoints} == {
                    ("GET", "/api/users"),
                    ("POST", "/api/users"),
                }
                return DocumentationDraft(
                    service_overview="Sample Next.js API generated from source.",
                    endpoints=[],
                    models=[],
                    error_handling="none",
                    caveats=[],
                )

        monkeypatch.setattr("intellapi.generator.pipeline.LLMClient", FakeLLMClient)

        config = IntellapiConfig(
            provider=Provider.OPENAI_COMPATIBLE,
            api_key="fake-key",
            output_path=str(tmp_path / "docs" / "nextjs.md"),
        )

        output_path = run_pipeline(fixture_dir, config)
        assert output_path == (tmp_path / "docs" / "nextjs.md").resolve()
        assert output_path.exists()

    def test_openapi_file_is_used_for_generation_and_custom_output_path(self, monkeypatch, tmp_path):
        """OpenAPI input should drive generation and respect custom output paths."""
        project_dir = tmp_path / "service"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

        openapi_path = tmp_path / "openapi.json"
        openapi_path.write_text(
            json.dumps(
                {
                    "openapi": "3.1.0",
                    "info": {"title": "Users API"},
                    "paths": {
                        "/users": {
                            "get": {
                                "summary": "List users",
                                "operationId": "listUsers",
                                "responses": {
                                    "200": {
                                        "description": "ok",
                                        "content": {
                                            "application/json": {
                                                "schema": {
                                                    "type": "array",
                                                    "items": {"$ref": "#/components/schemas/User"},
                                                }
                                            }
                                        },
                                    }
                                },
                            }
                        }
                    },
                    "components": {
                        "schemas": {
                            "User": {
                                "type": "object",
                                "required": ["id", "name"],
                                "properties": {
                                    "id": {"type": "integer"},
                                    "name": {"type": "string"},
                                },
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        class FakeLLMClient:
            def __init__(self, config):
                self.config = config

            def generate_documentation(self, ir):
                assert len(ir.endpoints) == 1
                assert ir.endpoints[0].path == "/users"
                assert ir.models[0].name == "User"
                return DocumentationDraft(
                    service_overview=f"{ir.service_name} overview",
                    endpoints=[],
                    models=[],
                    error_handling="none",
                    caveats=[],
                )

        monkeypatch.setattr("intellapi.generator.pipeline.LLMClient", FakeLLMClient)

        config = IntellapiConfig(
            provider=Provider.OPENAI_COMPATIBLE,
            api_key="fake-key",
            output_format=OutputFormat.BOTH,
            output_path=str(tmp_path / "docs" / "generated.md"),
            openapi_file=str(openapi_path),
        )

        output_path = run_pipeline(project_dir, config)
        assert output_path == (tmp_path / "docs" / "generated.md").resolve()
        assert (tmp_path / "docs" / "generated.md").exists()
        assert (tmp_path / "docs" / "generated.txt").exists()

    def test_generation_without_endpoints_fails_fast(self, tmp_path):
        """Source-only runs with no endpoints should stop instead of writing weak docs."""
        project_dir = tmp_path / "service"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")

        config = IntellapiConfig(provider=Provider.OPENAI_COMPATIBLE, api_key="fake-key")
        result = run_pipeline(project_dir, config, dry_run=False)
        assert result is None
