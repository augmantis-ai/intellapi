"""Tests for the framework detector."""

from pathlib import Path

from intellapi.scanner.framework_detector import detect_framework, discover_backend_candidates

FIXTURES = Path(__file__).parent / "fixtures"


class TestFrameworkDetector:
    """Test framework auto-detection."""

    def test_detect_fastapi(self):
        """Detect FastAPI from sample project."""
        results = detect_framework(FIXTURES / "sample_fastapi")
        assert len(results) >= 1
        top = results[0]
        assert top.framework == "fastapi"
        assert top.language == "python"
        assert top.confidence >= 0.7

    def test_detect_express(self):
        """Detect Express from sample project."""
        results = detect_framework(FIXTURES / "sample_express")
        assert len(results) >= 1
        top = results[0]
        assert top.framework == "express"
        assert top.language in ("javascript", "typescript")
        assert top.confidence >= 0.7

    def test_detect_nextjs(self):
        """Detect Next.js from sample project."""
        results = detect_framework(FIXTURES / "sample_nextjs")
        assert len(results) >= 1
        top = results[0]
        assert top.framework == "nextjs"
        assert top.language in ("javascript", "typescript")
        assert top.confidence >= 0.7

    def test_detect_sveltekit(self):
        """Detect SvelteKit from sample project."""
        results = detect_framework(FIXTURES / "sample_sveltekit")
        assert len(results) >= 1
        top = results[0]
        assert top.framework == "sveltekit"
        assert top.language in ("javascript", "typescript")
        assert top.confidence >= 0.7

    def test_empty_directory(self, tmp_path):
        """Return empty results for an empty directory."""
        results = detect_framework(tmp_path)
        assert results == []

    def test_returns_evidence(self):
        """Detection results include human-readable evidence."""
        results = detect_framework(FIXTURES / "sample_fastapi")
        assert len(results) >= 1
        assert len(results[0].evidence) > 0

    def test_discover_backend_candidates(self, tmp_path):
        """Candidate discovery finds backend subdirectories for the CLI picker."""
        fastapi_dir = tmp_path / "backend-fastapi"
        fastapi_dir.mkdir()
        (fastapi_dir / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")

        nextjs_dir = tmp_path / "backend-next"
        (nextjs_dir / "app" / "api" / "users").mkdir(parents=True)
        (nextjs_dir / "package.json").write_text('{"dependencies":{"next":"15.0.0"}}')
        (nextjs_dir / "tsconfig.json").write_text("{}")
        (nextjs_dir / "app" / "api" / "users" / "route.ts").write_text(
            "export async function GET() { return Response.json([]) }\n"
        )

        candidates = discover_backend_candidates(tmp_path)
        paths = {candidate.path for candidate in candidates}
        assert fastapi_dir in paths
        assert nextjs_dir in paths
