"""Privacy guardrail layer — runs before any code is sent to an LLM.

Hard-skip rules ensure secrets, credentials, and irrelevant files are never transmitted.
Minimization rules reduce the payload to only route-relevant code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from intellapi.utils import print_muted, console

# ─── Hard-Skip Patterns ────────────────────────────────────────────────────

# Files matching these names are never sent to the LLM
SKIP_FILENAMES: set[str] = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.staging",
    ".env.test",
    "credentials",
    "secrets.yml",
    "secrets.yaml",
    "secrets.json",
    ".netrc",
    ".npmrc",
    ".pypirc",
}

# Files with these extensions are never sent
SKIP_EXTENSIONS: set[str] = {
    # Certificates and keys
    ".pem", ".key", ".crt", ".cer", ".p12", ".pfx", ".jks", ".keystore",
    # Binaries and compiled
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".wasm", ".class",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z",
    # Media
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".webm",
    # Database
    ".db", ".sqlite", ".sqlite3", ".mdb",
    # Minified / bundled
    ".min.js", ".min.css", ".bundle.js",
    # Maps
    ".map",
    # Lock files (extension-based)
    ".lock",
}

# Files matching these glob-like name patterns are never sent
SKIP_NAME_PATTERNS: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "composer.lock",
    "Gemfile.lock",
}

# Directories that are always skipped entirely
SKIP_DIRECTORIES: set[str] = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".svelte-kit",
    ".nuxt",
    "coverage",
    "htmlcov",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "egg-info",
}

# Paths containing these segments are always skipped
SKIP_PATH_SEGMENTS: set[str] = {
    "aws/credentials",
    ".ssh",
}

# Default max file size (500KB)
DEFAULT_MAX_FILE_SIZE = 500 * 1024


# ─── Filter Results ────────────────────────────────────────────────────────


@dataclass
class PrivacyFilterResult:
    """Result of running the privacy filter on a list of files."""

    allowed: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)  # (path, reason)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def allowed_count(self) -> int:
        return len(self.allowed)


# ─── Core Filter ────────────────────────────────────────────────────────────


def filter_files(
    files: list[Path],
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
) -> PrivacyFilterResult:
    """Apply privacy guardrails to a list of files.

    Returns a PrivacyFilterResult with allowed files and skipped files+reasons.
    This MUST run before any code is sent to an LLM provider.
    """
    result = PrivacyFilterResult()

    for filepath in files:
        reason = _check_file(filepath, max_file_size)
        if reason:
            result.skipped.append((filepath, reason))
        else:
            result.allowed.append(filepath)

    return result


def _check_file(filepath: Path, max_file_size: int) -> str | None:
    """Check a single file against all privacy rules.

    Returns the skip reason if the file should be skipped, None if it passes.
    """
    name = filepath.name
    suffix = filepath.suffix.lower()
    path_str = str(filepath).replace("\\", "/")

    # 1. Filename match
    if name in SKIP_FILENAMES:
        return f"secret/credential file: {name}"

    # 2. Extension match
    if suffix in SKIP_EXTENSIONS:
        return f"excluded file type: {suffix}"

    # 3. Name pattern match (e.g., package-lock.json)
    if name in SKIP_NAME_PATTERNS:
        return f"lock/generated file: {name}"

    # 4. Check for .min.js, .bundle.js (compound extensions)
    if name.endswith(".min.js") or name.endswith(".min.css") or name.endswith(".bundle.js"):
        return f"minified/bundled file: {name}"

    # 5. Directory segments in path
    parts = filepath.parts
    for part in parts:
        if part in SKIP_DIRECTORIES:
            return f"excluded directory: {part}/"

    # 6. Path segment match
    for segment in SKIP_PATH_SEGMENTS:
        if segment in path_str:
            return f"sensitive path: {segment}"

    # 7. File size check
    try:
        size = filepath.stat().st_size
        if size > max_file_size:
            size_kb = size // 1024
            return f"file too large: {size_kb}KB > {max_file_size // 1024}KB"
    except OSError:
        return "unreadable file"

    # 8. Check if file looks binary (first 8KB)
    if _is_binary(filepath):
        return "binary file"

    return None


def _is_binary(filepath: Path, sample_size: int = 8192) -> bool:
    """Check if a file is binary by looking for null bytes in the first chunk."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(sample_size)
            return b"\x00" in chunk
    except OSError:
        return True  # If we can't read it, treat as binary


# ─── Audit Log ──────────────────────────────────────────────────────────────


def print_audit_log(result: PrivacyFilterResult) -> None:
    """Print the privacy audit log (used with --verbose)."""
    console.print("\n[bold]Privacy Audit Log[/bold]")
    console.print(f"  Files allowed: {result.allowed_count}")
    console.print(f"  Files skipped: {result.skipped_count}")

    if result.skipped:
        console.print("\n  [dim]Skipped files:[/dim]")
        for filepath, reason in result.skipped:
            print_muted(f"  [x] {filepath} -- {reason}")

    if result.allowed:
        console.print("\n  [dim]Allowed files:[/dim]")
        for filepath in result.allowed:
            print_muted(f"  [+] {filepath}")

    console.print()
