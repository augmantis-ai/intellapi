"""Framework detection — auto-detect language and framework from project files.

Detection priority:
1. Manifest files (package.json → Node; pyproject.toml/requirements.txt → Python)
2. Directory conventions (app/api/ → Next.js; src/routes/+server → SvelteKit)
3. Import scanning (first 50 lines of likely entry files)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from intellapi.privacy import SKIP_DIRECTORIES
from intellapi.scanner.file_discovery import JS_TS_EXTENSIONS, PYTHON_EXTENSIONS


@dataclass
class DetectionResult:
    """Result of framework detection."""

    framework: str  # fastapi | flask | django_rest | express | nextjs | sveltekit | unknown
    language: str  # python | javascript | typescript | unknown
    confidence: float  # 0.0–1.0
    evidence: list[str]  # Human-readable reasons for the detection


@dataclass
class BackendCandidate:
    """A detected backend candidate directory plus its top detection."""

    path: Path
    detection: DetectionResult


def detect_framework(target_dir: Path) -> list[DetectionResult]:
    """Detect framework(s) in the target directory.

    Returns a list of detection results, sorted by confidence (highest first).
    Multiple results indicate a monorepo or ambiguous detection.
    """
    target_dir = target_dir.resolve()
    results: list[DetectionResult] = []

    # ── Check for Python frameworks ─────────────────────────────────────
    python_files = list(target_dir.rglob("*.py"))
    if python_files:
        result = _detect_python_framework(target_dir, python_files)
        if result:
            results.append(result)

    # ── Check for Next.js (must come before Express) ────────────────────
    nextjs_result = _detect_nextjs(target_dir)
    if nextjs_result:
        results.append(nextjs_result)

    # ── Check for SvelteKit ─────────────────────────────────────────────
    sveltekit_result = _detect_sveltekit(target_dir)
    if sveltekit_result:
        results.append(sveltekit_result)

    # ── Check for Express ───────────────────────────────────────────────
    if not nextjs_result:  # Avoid double-detecting Node projects
        express_result = _detect_express(target_dir)
        if express_result:
            results.append(express_result)

    # Sort by confidence
    results.sort(key=lambda r: r.confidence, reverse=True)

    return results


def discover_backend_candidates(target_dir: Path, max_depth: int = 3) -> list[BackendCandidate]:
    """Discover plausible backend roots beneath ``target_dir``."""
    root = target_dir.resolve()
    candidates: list[BackendCandidate] = []
    seen: set[Path] = set()

    for candidate_dir in _iter_candidate_directories(root, max_depth=max_depth):
        detections = detect_framework(candidate_dir)
        if not detections or candidate_dir in seen:
            continue
        candidates.append(BackendCandidate(path=candidate_dir, detection=detections[0]))
        seen.add(candidate_dir)

    candidates.sort(
        key=lambda c: (0 if c.path == root else 1, len(c.path.parts), -c.detection.confidence, str(c.path))
    )
    return candidates


def _iter_candidate_directories(root: Path, max_depth: int) -> list[Path]:
    """Yield directories that look like backend app roots."""
    result: list[Path] = [root]
    queue: list[tuple[Path, int]] = [(root, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue

        for entry in entries:
            if not entry.is_dir() or entry.name in SKIP_DIRECTORIES:
                continue

            queue.append((entry, depth + 1))
            if _looks_like_backend_root(entry):
                result.append(entry)

    return result


def _looks_like_backend_root(path: Path) -> bool:
    """Check for files/directories that usually indicate an app root."""
    manifest_files = {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "Pipfile",
        "setup.py",
        "manage.py",
    }

    try:
        names = {entry.name for entry in path.iterdir()}
    except OSError:
        return False

    if names & manifest_files:
        return True
    if any(path.glob("*.py")) or any(path.glob("*.js")) or any(path.glob("*.ts")):
        return True
    if (path / "src" / "routes").exists():
        return True
    if (path / "pages" / "api").exists():
        return True
    if (path / "app").exists():
        if any((path / "app").rglob("route.ts")) or any((path / "app").rglob("route.js")):
            return True
    return False


def _detect_python_framework(
    target_dir: Path, python_files: list[Path]
) -> DetectionResult | None:
    """Detect FastAPI, Flask, or Django REST from Python source files."""
    evidence: list[str] = []
    framework = "unknown"
    confidence = 0.0

    # Check requirements/pyproject for framework deps
    dep_files = [
        target_dir / "requirements.txt",
        target_dir / "pyproject.toml",
        target_dir / "Pipfile",
        target_dir / "setup.py",
    ]

    deps_text = ""
    for dep_file in dep_files:
        if dep_file.exists():
            try:
                deps_text += dep_file.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                pass

    # Check for FastAPI
    if "fastapi" in deps_text:
        evidence.append("FastAPI found in project dependencies")
        framework = "fastapi"
        confidence = 0.9

    # Check for Flask
    elif "flask" in deps_text:
        evidence.append("Flask found in project dependencies")
        framework = "flask"
        confidence = 0.9

    # Check for Django REST
    elif "djangorestframework" in deps_text or "rest_framework" in deps_text:
        evidence.append("Django REST Framework found in project dependencies")
        framework = "django_rest"
        confidence = 0.9

    # Check for Django (without REST)
    elif "django" in deps_text:
        evidence.append("Django found in project dependencies (no REST framework detected)")
        framework = "django_rest"
        confidence = 0.5

    # Fallback: scan source imports (first 50 lines per file, max 10 files)
    if framework == "unknown":
        scan_files = python_files[:10]
        for pf in scan_files:
            try:
                lines = pf.read_text(encoding="utf-8", errors="ignore").splitlines()[:50]
                content = "\n".join(lines)
                if "from fastapi" in content or "import fastapi" in content:
                    framework = "fastapi"
                    confidence = 0.8
                    evidence.append(f"FastAPI import found in {pf.name}")
                    break
                elif "from flask" in content or "import flask" in content:
                    framework = "flask"
                    confidence = 0.8
                    evidence.append(f"Flask import found in {pf.name}")
                    break
                elif "from rest_framework" in content:
                    framework = "django_rest"
                    confidence = 0.8
                    evidence.append(f"Django REST import found in {pf.name}")
                    break
            except OSError:
                continue

    if framework == "unknown":
        return None

    # Check for manage.py (Django confirmation)
    if (target_dir / "manage.py").exists() and "django" in framework:
        evidence.append("manage.py found (Django project)")
        confidence = min(confidence + 0.1, 1.0)

    return DetectionResult(
        framework=framework,
        language="python",
        confidence=confidence,
        evidence=evidence,
    )


def _detect_nextjs(target_dir: Path) -> DetectionResult | None:
    """Detect Next.js API routes from directory structure."""
    evidence: list[str] = []

    # Check package.json for next dependency
    pkg_json = target_dir / "package.json"
    if not pkg_json.exists():
        return None

    try:
        content = pkg_json.read_text(encoding="utf-8", errors="ignore").lower()
        if '"next"' not in content:
            return None
        evidence.append("'next' found in package.json")
    except OSError:
        return None

    # Check for App Router: app/**/route.{ts,js}
    app_dir = target_dir / "app"
    if app_dir.exists():
        route_files = list(app_dir.rglob("route.ts")) + list(app_dir.rglob("route.js"))
        if route_files:
            evidence.append(f"App Router: {len(route_files)} route files found in app/")

    # Check for Pages Router: pages/api/**
    pages_api = target_dir / "pages" / "api"
    if pages_api.exists():
        api_files = list(pages_api.rglob("*.ts")) + list(pages_api.rglob("*.js"))
        if api_files:
            evidence.append(f"Pages Router: {len(api_files)} API files found in pages/api/")

    # Also check src/ variants
    for prefix in [target_dir / "src"]:
        src_app = prefix / "app"
        if src_app.exists():
            route_files = list(src_app.rglob("route.ts")) + list(src_app.rglob("route.js"))
            if route_files:
                evidence.append(f"App Router: {len(route_files)} route files in src/app/")

    if len(evidence) < 2:  # Need next in package.json + at least one route
        return None

    # Determine language
    ts_config = (target_dir / "tsconfig.json").exists()
    language = "typescript" if ts_config else "javascript"

    return DetectionResult(
        framework="nextjs",
        language=language,
        confidence=0.9,
        evidence=evidence,
    )


def _detect_sveltekit(target_dir: Path) -> DetectionResult | None:
    """Detect SvelteKit endpoints from directory structure."""
    evidence: list[str] = []

    # Check package.json for @sveltejs/kit
    pkg_json = target_dir / "package.json"
    if not pkg_json.exists():
        return None

    try:
        content = pkg_json.read_text(encoding="utf-8", errors="ignore").lower()
        if '"@sveltejs/kit"' not in content:
            return None
        evidence.append("'@sveltejs/kit' found in package.json")
    except OSError:
        return None

    # Check for +server.ts/js files
    routes_dir = target_dir / "src" / "routes"
    if routes_dir.exists():
        server_files = (
            list(routes_dir.rglob("+server.ts"))
            + list(routes_dir.rglob("+server.js"))
        )
        if server_files:
            evidence.append(f"{len(server_files)} +server files found in src/routes/")
        else:
            return None
    else:
        return None

    ts_config = (target_dir / "tsconfig.json").exists()
    language = "typescript" if ts_config else "javascript"

    return DetectionResult(
        framework="sveltekit",
        language=language,
        confidence=0.9,
        evidence=evidence,
    )


def _detect_express(target_dir: Path) -> DetectionResult | None:
    """Detect Express from package.json and source imports."""
    evidence: list[str] = []

    # Check package.json
    pkg_json = target_dir / "package.json"
    if not pkg_json.exists():
        return None

    try:
        content = pkg_json.read_text(encoding="utf-8", errors="ignore").lower()
        if '"express"' not in content:
            return None
        evidence.append("'express' found in package.json")
    except OSError:
        return None

    # Confirm by scanning JS/TS files for express imports
    js_files = []
    for ext in JS_TS_EXTENSIONS:
        js_files.extend(target_dir.rglob(f"*{ext}"))

    for jf in list(js_files)[:10]:
        try:
            lines = jf.read_text(encoding="utf-8", errors="ignore").splitlines()[:50]
            content = "\n".join(lines)
            if "require('express')" in content or "require(\"express\")" in content:
                evidence.append(f"Express require() found in {jf.name}")
                break
            elif "from 'express'" in content or 'from "express"' in content:
                evidence.append(f"Express import found in {jf.name}")
                break
        except OSError:
            continue

    ts_config = (target_dir / "tsconfig.json").exists()
    language = "typescript" if ts_config else "javascript"

    return DetectionResult(
        framework="express",
        language=language,
        confidence=0.85,
        evidence=evidence,
    )
