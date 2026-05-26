"""Tests for the product stack detector."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.products.stack_detector import detect_stack


# ---------------------------------------------------------------------------
# Fixtures: synthetic repo shapes
# ---------------------------------------------------------------------------


def _touch(p: Path, content: str = "") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


@pytest.fixture
def python_fastapi_repo(tmp_path):
    """Python + FastAPI + pytest + postgres + GitHub Actions."""
    _touch(tmp_path / "pyproject.toml",
           '[project]\nname = "x"\n[tool.poetry.dependencies]\nfastapi = "^0.110"\npytest = "*"\n')
    _touch(tmp_path / "tests" / "test_foo.py", "def test_x(): pass\n")
    _touch(tmp_path / "docker-compose.yml",
           "services:\n  db:\n    image: postgres:16\n")
    _touch(tmp_path / ".github" / "workflows" / "ci.yml", "name: ci\n")
    return tmp_path


@pytest.fixture
def nextjs_typescript_repo(tmp_path):
    """Next.js + TypeScript + Vitest + Vercel deploy."""
    _touch(tmp_path / "package.json",
           '{"name":"x","dependencies":{"next":"^14","react":"^18"},"devDependencies":{"vitest":"^1"}}')
    _touch(tmp_path / "tsconfig.json", "{}\n")
    _touch(tmp_path / "next.config.js", "module.exports = {};\n")
    _touch(tmp_path / "vitest.config.ts", "export default {};\n")
    _touch(tmp_path / "vercel.json", "{}\n")
    return tmp_path


@pytest.fixture
def go_repo(tmp_path):
    """Go module with Dockerfile."""
    _touch(tmp_path / "go.mod", "module foo\n\ngo 1.21\n")
    _touch(tmp_path / "main.go", "package main\nfunc main() {}\n")
    _touch(tmp_path / "Dockerfile", "FROM golang:1.21\n")
    return tmp_path


@pytest.fixture
def polyglot_monorepo(tmp_path):
    """Monorepo: Python backend + Next.js frontend + Redis + GitHub Actions."""
    _touch(tmp_path / "backend" / "pyproject.toml", "")
    _touch(tmp_path / "frontend" / "package.json",
           '{"dependencies":{"next":"^14"}}')
    # Top-level Python manifest (poly-detect should still pick up python)
    _touch(tmp_path / "requirements.txt", "fastapi==0.110\nredis==5.0\n")
    _touch(tmp_path / "package.json", '{"name":"monorepo"}')
    _touch(tmp_path / "next.config.ts", "export default {};\n")
    _touch(tmp_path / ".env.example", "REDIS_URL=redis://localhost\nPOSTGRES_URL=postgres://x\n")
    _touch(tmp_path / ".github" / "workflows" / "test.yml", "")
    return tmp_path


@pytest.fixture
def bare_repo(tmp_path):
    """Empty repo — README only."""
    _touch(tmp_path / "README.md", "# Empty\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDetectStack:
    def test_python_fastapi(self, python_fastapi_repo):
        m = detect_stack(python_fastapi_repo)
        assert "python" in m["languages"]
        assert "fastapi" in m["frameworks"]
        assert "pytest" in m["test_runners"]
        assert "postgres" in m["databases"]
        assert "docker" in m["deploy_targets"]
        assert "github-actions" in m["ci_providers"]
        assert m["detected_at"]  # nonempty timestamp

    def test_nextjs_typescript(self, nextjs_typescript_repo):
        m = detect_stack(nextjs_typescript_repo)
        assert "typescript" in m["languages"]
        assert "javascript" in m["languages"]  # package.json implies js
        assert "nextjs" in m["frameworks"]
        assert "react" in m["frameworks"]
        assert "vitest" in m["test_runners"]
        assert "vercel" in m["deploy_targets"]

    def test_go(self, go_repo):
        m = detect_stack(go_repo)
        assert m["languages"] == ["go"]
        assert m["frameworks"] == []
        assert m["test_runners"] == []
        assert "docker" in m["deploy_targets"]

    def test_polyglot_monorepo(self, polyglot_monorepo):
        m = detect_stack(polyglot_monorepo)
        # Both languages detected
        assert "python" in m["languages"]
        assert "javascript" in m["languages"]
        # Frameworks from both halves
        assert "fastapi" in m["frameworks"]
        assert "nextjs" in m["frameworks"]
        # Databases inferred from .env
        assert "redis" in m["databases"]
        assert "postgres" in m["databases"]
        assert "github-actions" in m["ci_providers"]

    def test_bare_repo_empty_lists(self, bare_repo):
        m = detect_stack(bare_repo)
        assert m["languages"] == []
        assert m["frameworks"] == []
        assert m["test_runners"] == []
        assert m["databases"] == []
        assert m["deploy_targets"] == []
        assert m["ci_providers"] == []
        assert m["detected_at"]  # timestamp present even on empty

    def test_nonexistent_repo_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect_stack(tmp_path / "does-not-exist")

    def test_path_must_be_directory(self, tmp_path):
        f = tmp_path / "afile"
        f.write_text("x")
        with pytest.raises(FileNotFoundError):
            detect_stack(f)
