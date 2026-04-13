"""CLI regression tests for milestone M1 behaviors."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import intellapi.cli as cli_module
from intellapi.cli import app


runner = CliRunner()


class TestCli:
    def test_config_set_rejects_api_key(self):
        """Secrets must not be persisted through config set."""
        result = runner.invoke(app, ["config", "set", "api_key", "secret-value"])
        assert result.exit_code == 1
        assert "cannot be stored in config files" in result.output

    def test_doctor_allows_env_only_configuration(self, monkeypatch, tmp_path):
        """Missing user config does not fail doctor when env config is valid."""
        project_dir = tmp_path / "service"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

        monkeypatch.setattr(cli_module, "USER_CONFIG_FILE", tmp_path / "missing-config.yml")
        monkeypatch.setenv("INTELLAPI_PROVIDER", "openai_compatible")
        monkeypatch.setenv("INTELLAPI_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("INTELLAPI_API_KEY", "env-secret")

        class FakeLLMClient:
            def __init__(self, config):
                self.provider_name = "Fake Provider"

            def validate_connection(self) -> bool:
                return True

        monkeypatch.setattr("intellapi.llm.client.LLMClient", FakeLLMClient)

        result = runner.invoke(app, ["doctor", "--path", str(project_dir)])
        assert result.exit_code == 0
        assert "Provider connectivity: OK" in result.output
        assert "All checks passed" in result.output

    def test_generate_dry_run_uses_selected_backend_candidate(self, monkeypatch, tmp_path):
        """Interactive picker chooses the requested backend directory."""
        fastapi_dir = tmp_path / "backend-fastapi"
        fastapi_dir.mkdir()
        (fastapi_dir / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

        nextjs_dir = tmp_path / "backend-next"
        (nextjs_dir / "app" / "api" / "users").mkdir(parents=True)
        (nextjs_dir / "package.json").write_text('{"dependencies":{"next":"15.0.0"}}', encoding="utf-8")
        (nextjs_dir / "tsconfig.json").write_text("{}", encoding="utf-8")
        (nextjs_dir / "app" / "api" / "users" / "route.ts").write_text(
            "export async function GET() { return Response.json([]) }\n",
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["generate", "--dry-run"], input="2\n")
        assert result.exit_code == 0
        assert "backend-next" in result.output
        assert "Framework: nextjs" in result.output

    def test_generate_dry_run_honors_custom_output_path(self, tmp_path):
        """Dry-run preview shows the actual requested output target."""
        project_dir = tmp_path / "service"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "generate",
                "--path",
                str(project_dir),
                "--dry-run",
                "--output",
                str(tmp_path / "docs" / "API.md"),
            ],
        )
        assert result.exit_code == 0
        assert "Output:" in result.output
        assert "API.md" in result.output
