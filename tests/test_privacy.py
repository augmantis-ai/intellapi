"""Tests for the privacy guardrail layer."""

from pathlib import Path

from intellapi.privacy import filter_files, PrivacyFilterResult


class TestPrivacyFilter:
    """Test the privacy guardrail layer."""

    def test_skip_env_files(self, tmp_path):
        """Skip .env files."""
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc123")
        py_file = tmp_path / "main.py"
        py_file.write_text("print('hello')")

        result = filter_files([env_file, py_file])
        assert py_file in result.allowed
        assert env_file not in result.allowed
        assert any(".env" in reason for _, reason in result.skipped)

    def test_skip_pem_files(self, tmp_path):
        """Skip certificate files."""
        pem_file = tmp_path / "server.pem"
        pem_file.write_text("-----BEGIN CERTIFICATE-----")

        result = filter_files([pem_file])
        assert result.allowed_count == 0
        assert result.skipped_count == 1

    def test_skip_lockfiles(self, tmp_path):
        """Skip lock files."""
        lock = tmp_path / "package-lock.json"
        lock.write_text("{}")

        result = filter_files([lock])
        assert result.allowed_count == 0

    def test_skip_large_files(self, tmp_path):
        """Skip files over the size threshold."""
        big_file = tmp_path / "big.py"
        big_file.write_text("x" * (600 * 1024))  # 600KB

        result = filter_files([big_file], max_file_size=500 * 1024)
        assert result.allowed_count == 0
        assert "too large" in result.skipped[0][1]

    def test_allow_normal_source(self, tmp_path):
        """Allow normal source files."""
        py_file = tmp_path / "app.py"
        py_file.write_text("from fastapi import FastAPI")

        result = filter_files([py_file])
        assert result.allowed_count == 1
        assert result.skipped_count == 0

    def test_skip_binary_files(self, tmp_path):
        """Skip binary files containing null bytes."""
        bin_file = tmp_path / "data.bin"
        bin_file.write_bytes(b"hello\x00world")

        result = filter_files([bin_file])
        assert result.allowed_count == 0

    def test_skip_minified_js(self, tmp_path):
        """Skip minified JavaScript files."""
        min_file = tmp_path / "app.min.js"
        min_file.write_text("var x=1;")

        result = filter_files([min_file])
        assert result.allowed_count == 0

    def test_skip_node_modules(self, tmp_path):
        """Skip files inside node_modules."""
        nm = tmp_path / "node_modules" / "express"
        nm.mkdir(parents=True)
        mod_file = nm / "index.js"
        mod_file.write_text("module.exports = {}")

        result = filter_files([mod_file])
        assert result.allowed_count == 0
