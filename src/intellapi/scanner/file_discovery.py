"""File discovery — walk directories, respect ignore rules.

Discovers source files for analysis while respecting .gitignore,
.intellapiignore, and built-in exclusion rules.
"""

from __future__ import annotations

from pathlib import Path

import pathspec

from intellapi.privacy import SKIP_DIRECTORIES

# Source file extensions we care about
PYTHON_EXTENSIONS = {".py"}
JS_TS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
SVELTE_EXTENSIONS = {".svelte"}
ALL_SOURCE_EXTENSIONS = PYTHON_EXTENSIONS | JS_TS_EXTENSIONS | SVELTE_EXTENSIONS


def discover_files(
    target_dir: Path,
    extensions: set[str] | None = None,
) -> list[Path]:
    """Recursively discover source files in the target directory.

    Respects .gitignore and .intellapiignore via pathspec.
    Skips well-known non-source directories.

    Args:
        target_dir: Root directory to scan.
        extensions: File extensions to include. Defaults to all source extensions.

    Returns:
        Sorted list of discovered file paths.
    """
    target_dir = target_dir.resolve()
    exts = extensions or ALL_SOURCE_EXTENSIONS

    # Load ignore patterns
    ignore_spec = _load_ignore_spec(target_dir)

    result: list[Path] = []
    _walk_directory(target_dir, target_dir, exts, ignore_spec, result)

    return sorted(result)


def _walk_directory(
    root: Path,
    current: Path,
    extensions: set[str],
    ignore_spec: pathspec.PathSpec | None,
    result: list[Path],
) -> None:
    """Recursively walk a directory, filtering by extensions and ignore rules."""
    try:
        entries = sorted(current.iterdir())
    except PermissionError:
        return

    for entry in entries:
        # Get relative path for ignore matching
        try:
            rel_path = entry.relative_to(root)
        except ValueError:
            continue

        rel_str = str(rel_path).replace("\\", "/")

        if entry.is_dir():
            # Skip well-known excluded directories
            if entry.name in SKIP_DIRECTORIES:
                continue

            # Skip if matched by ignore spec
            if ignore_spec and ignore_spec.match_file(rel_str + "/"):
                continue

            _walk_directory(root, entry, extensions, ignore_spec, result)

        elif entry.is_file():
            # Check extension
            if entry.suffix.lower() not in extensions:
                continue

            # Skip if matched by ignore spec
            if ignore_spec and ignore_spec.match_file(rel_str):
                continue

            result.append(entry)


def _load_ignore_spec(target_dir: Path) -> pathspec.PathSpec | None:
    """Load .gitignore and .intellapiignore patterns."""
    patterns: list[str] = []

    for ignore_file in [".gitignore", ".intellapiignore"]:
        ignore_path = target_dir / ignore_file
        if ignore_path.exists():
            try:
                with open(ignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            except OSError:
                continue

    if not patterns:
        return None

    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
