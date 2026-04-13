"""Tests for the configuration system."""

import os
from pathlib import Path

import pytest
import yaml

import intellapi.config as config_module
from intellapi.config import (
    IntellapiConfig,
    OutputFormat,
    Provider,
    resolve_config,
    read_user_config,
    write_user_config,
    read_project_config,
    write_project_config,
    USER_CONFIG_DIR,
    USER_CONFIG_FILE,
)


class TestConfigResolution:
    """Test the 3-layer config resolution."""

    def test_defaults(self):
        """Config has sensible defaults when nothing is set."""
        config = IntellapiConfig()
        assert config.output_format == OutputFormat.MD
        assert config.output_filename == "API_DOCUMENTATION.md"
        assert config.aws_region == "us-east-1"

    def test_env_var_override(self, monkeypatch):
        """Env vars override defaults."""
        monkeypatch.setenv("INTELLAPI_PROVIDER", "anthropic")
        monkeypatch.setenv("INTELLAPI_MODEL", "claude-3-haiku")
        config = resolve_config()
        assert config.provider == Provider.ANTHROPIC
        assert config.model == "claude-3-haiku"

    def test_cli_overrides_env(self, monkeypatch):
        """CLI overrides take highest precedence."""
        monkeypatch.setenv("INTELLAPI_MODEL", "env-model")
        config = resolve_config(cli_overrides={"model": "cli-model"})
        assert config.model == "cli-model"

    def test_project_config_read_write(self, tmp_path):
        """Write and read project config."""
        data = {"output_format": "txt", "exclude": ["tests/"]}
        path = write_project_config(data, tmp_path)
        assert path.exists()

        read_data = read_project_config(tmp_path)
        assert read_data["output_format"] == "txt"
        assert "tests/" in read_data["exclude"]

    def test_display_dict_masks_key(self):
        """display_dict masks the API key."""
        config = IntellapiConfig(api_key="sk-1234567890abcdef")
        display = config.display_dict()
        assert "sk-1234567890abcdef" not in str(display)
        assert "****" in display["api_key"]

    def test_secret_keys_are_ignored_in_config_files(self, monkeypatch, tmp_path):
        """Manual plaintext API keys in YAML are ignored during config resolution."""
        user_dir = tmp_path / ".intellapi"
        user_file = user_dir / "config.yml"
        monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr(config_module, "USER_CONFIG_FILE", user_file)

        user_dir.mkdir()
        user_file.write_text(
            yaml.safe_dump({"provider": "anthropic", "api_key": "plaintext-secret"}),
            encoding="utf-8",
        )

        config = resolve_config()
        assert config.provider == Provider.ANTHROPIC
        assert config.api_key is None

    def test_update_user_config_rejects_secret_keys(self, monkeypatch, tmp_path):
        """Secret values cannot be stored via config updates."""
        user_dir = tmp_path / ".intellapi"
        user_file = user_dir / "config.yml"
        monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr(config_module, "USER_CONFIG_FILE", user_file)

        with pytest.raises(ValueError):
            config_module.update_user_config("api_key", "secret")
