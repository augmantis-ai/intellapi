"""3-layer configuration management.

Layer 1 — User config:    ~/.intellapi/config.yml   (global defaults)
Layer 2 — Project config:  .intellapi.yml            (per-repo, committable)
Layer 3 — Keyring:         OS keyring                (secrets only)

Precedence: CLI flags > env vars > project config > user config > defaults
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

import keyring
import yaml
from pydantic import BaseModel, Field

from intellapi.utils import mask_secret

# ─── Constants ──────────────────────────────────────────────────────────────

KEYRING_SERVICE = "intellapi"
USER_CONFIG_DIR = Path.home() / ".intellapi"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.yml"
PROJECT_CONFIG_FILE = ".intellapi.yml"
SECRET_CONFIG_KEYS = {
    "api_key",
    "anthropic_api_key",
    "openai_api_key",
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
}

# ─── Enums ──────────────────────────────────────────────────────────────────


class Provider(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"


class OutputFormat(str, Enum):
    MD = "md"
    TXT = "txt"
    BOTH = "both"


# ─── Config Model ──────────────────────────────────────────────────────────


class IntellapiConfig(BaseModel):
    """Resolved configuration after merging all layers."""

    # Provider
    provider: Provider | None = None
    model: str | None = None

    # OpenAI-compatible settings
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None  # resolved at runtime, never persisted to file

    # Bedrock settings
    aws_region: str = "us-east-1"
    aws_profile: str | None = None

    # Output
    output_format: OutputFormat = OutputFormat.MD
    output_filename: str = "API_DOCUMENTATION.md"
    output_path: str | None = None

    # File filtering
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    # OpenAPI merge
    openapi_file: str | None = None
    openapi_url: str | None = None

    def display_dict(self) -> dict[str, Any]:
        """Return config as a display-safe dict with secrets masked."""
        data = self.model_dump(exclude_none=True)
        if "api_key" in data and data["api_key"]:
            data["api_key"] = mask_secret(data["api_key"])
        return data


# ─── YAML I/O ──────────────────────────────────────────────────────────────


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file, returning empty dict if missing or invalid."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return {}
            return _sanitize_config_data(data)
    except (yaml.YAMLError, OSError):
        return {}


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict to a YAML file, creating parent dirs as needed."""
    data = _sanitize_config_data(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# ─── Keyring ────────────────────────────────────────────────────────────────


def _keyring_available() -> bool:
    """Check if keyring backend is usable."""
    try:
        # Attempt a harmless read to verify backend is functional
        keyring.get_password(KEYRING_SERVICE, "__probe__")
        return True
    except Exception:
        return False


def store_api_key(provider: Provider, api_key: str) -> bool:
    """Store an API key in the OS keyring. Returns True on success."""
    if provider == Provider.BEDROCK:
        return False  # Bedrock uses AWS credential chain, not keyring
    try:
        keyring.set_password(KEYRING_SERVICE, provider.value, api_key)
        return True
    except Exception:
        return False


def retrieve_api_key(provider: Provider) -> str | None:
    """Retrieve an API key from the OS keyring."""
    if provider == Provider.BEDROCK:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, provider.value)
    except Exception:
        return None


def delete_api_key(provider: Provider) -> bool:
    """Delete an API key from the OS keyring."""
    try:
        keyring.delete_password(KEYRING_SERVICE, provider.value)
        return True
    except Exception:
        return False


# ─── User Config (Layer 1) ─────────────────────────────────────────────────


def read_user_config() -> dict[str, Any]:
    """Read global user config from ~/.intellapi/config.yml."""
    return _read_yaml(USER_CONFIG_FILE)


def write_user_config(data: dict[str, Any]) -> None:
    """Write global user config to ~/.intellapi/config.yml."""
    _write_yaml(USER_CONFIG_FILE, data)


def update_user_config(key: str, value: Any) -> None:
    """Update a single key in user config."""
    if key in SECRET_CONFIG_KEYS:
        raise ValueError(
            f"'{key}' is secret material and cannot be stored in config files. "
            "Use 'intellapi init' or environment variables instead."
        )
    data = read_user_config()
    data[key] = value
    write_user_config(data)


# ─── Project Config (Layer 2) ──────────────────────────────────────────────


def find_project_config(start_dir: Path | None = None) -> Path | None:
    """Walk up from start_dir looking for .intellapi.yml. Returns path or None."""
    current = (start_dir or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / PROJECT_CONFIG_FILE
        if candidate.exists():
            return candidate
    return None


def read_project_config(start_dir: Path | None = None) -> dict[str, Any]:
    """Read project config from .intellapi.yml, searching upward."""
    path = find_project_config(start_dir)
    if path is None:
        return {}
    return _read_yaml(path)


def write_project_config(data: dict[str, Any], target_dir: Path | None = None) -> Path:
    """Write project config to .intellapi.yml in target_dir (or cwd)."""
    target = (target_dir or Path.cwd()) / PROJECT_CONFIG_FILE
    _write_yaml(target, data)
    return target


# ─── Resolution ─────────────────────────────────────────────────────────────


def resolve_config(
    cli_overrides: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> IntellapiConfig:
    """Resolve config by merging all layers.

    Precedence: CLI flags > env vars > project config > user config > defaults
    """
    # Load .env file automatically if python-dotenv is available
    try:
        from dotenv import load_dotenv
        load_dotenv(project_dir / ".env" if project_dir else Path.cwd() / ".env")
    except ImportError:
        pass

    # Start with defaults (from Pydantic model)
    merged: dict[str, Any] = {}

    # Layer 1: user config
    merged.update(_strip_none(read_user_config()))

    # Layer 2: project config
    merged.update(_strip_none(read_project_config(project_dir)))

    # Layer 3: env vars
    env_map = {
        "INTELLAPI_PROVIDER": "provider",
        "INTELLAPI_MODEL": "model",
        "BEDROCK_MODEL_ID": "model",  # map user's BEDROCK_MODEL_ID to model
        "INTELLAPI_API_KEY": "api_key",
        "INTELLAPI_BASE_URL": "base_url",
        "AWS_DEFAULT_REGION": "aws_region",
        "AWS_REGION": "aws_region", # also map AWS_REGION
        "AWS_PROFILE": "aws_profile",
    }
    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            merged[config_key] = val

    # Layer 4: CLI overrides (highest priority)
    if cli_overrides:
        merged.update(_strip_none(cli_overrides))

    # Build config
    config = IntellapiConfig(**merged)

    # Resolve API key from keyring if not already set (and not bedrock)
    if config.provider and config.provider != Provider.BEDROCK and not config.api_key:
        config.api_key = retrieve_api_key(config.provider)

    # Last resort: INTELLAPI_API_KEY env var (already handled above but be explicit)
    if not config.api_key and config.provider and config.provider != Provider.BEDROCK:
        config.api_key = os.environ.get("INTELLAPI_API_KEY")

    return config


def _strip_none(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with None values from a dict."""
    return {k: v for k, v in d.items() if v is not None}


def _sanitize_config_data(data: dict[str, Any]) -> dict[str, Any]:
    """Drop secret keys so config files can never be used as secret storage."""
    return {k: v for k, v in data.items() if k not in SECRET_CONFIG_KEYS}
