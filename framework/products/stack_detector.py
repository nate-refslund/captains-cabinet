"""Product stack detector — introspects a cloned repo to identify its tech stack.

Phase 6 of the convergence plan. The Cabinet's `bootstrap-project.sh` clones
a product repo, then calls this detector to populate `product_metadata` in
the generated project YAML — so officers can answer "what's this product
built with?" without inventing data.

Detection is intentionally heuristic + file-based — no language servers, no
AST parsing, no network calls. Speed + reliability over completeness.

Usage:
    from framework.products.stack_detector import detect_stack

    metadata = detect_stack("/path/to/cloned/repo")
    # metadata = {
    #   "languages": ["python", "typescript"],
    #   "frameworks": ["fastapi", "nextjs"],
    #   "test_runners": ["pytest", "vitest"],
    #   "databases": ["postgres"],
    #   "deploy_targets": ["vercel"],
    #   "ci_providers": ["github-actions"],
    #   "detected_at": "2026-05-26T...",
    # }

CLI:
    python3 -m framework.products.stack_detector /path/to/repo
    python3 -m framework.products.stack_detector /path/to/repo --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Per-dimension detection rules
# ---------------------------------------------------------------------------
#
# Each rule is (slug, [file_or_glob predicate(s)]). Predicates are evaluated
# against the repo root; any hit adds the slug to that dimension's set.


def _file_exists(repo: Path, name: str) -> bool:
    return (repo / name).exists()


def _glob_any(repo: Path, pattern: str) -> bool:
    """True if at least one file matches the glob (recursive)."""
    return any(repo.glob(pattern))


def _read_contains(repo: Path, name: str, needle: str) -> bool:
    """True if file `name` exists and contains `needle` as a substring."""
    f = repo / name
    if not f.exists():
        return False
    try:
        return needle in f.read_text(errors="ignore")
    except (OSError, PermissionError):
        return False


# Languages — derived from canonical manifests + file extensions
_LANGUAGE_RULES: list[tuple[str, list[str]]] = [
    ("python",     ["pyproject.toml", "requirements.txt", "Pipfile", "setup.py"]),
    ("typescript", ["tsconfig.json", "tsconfig.base.json"]),
    ("javascript", ["package.json"]),  # may overlap with typescript
    ("go",         ["go.mod", "go.sum"]),
    ("rust",       ["Cargo.toml"]),
    ("ruby",       ["Gemfile", "Rakefile"]),
    ("java",       ["pom.xml", "build.gradle", "build.gradle.kts"]),
    ("php",        ["composer.json"]),
    ("elixir",     ["mix.exs"]),
    ("swift",      ["Package.swift"]),
    ("kotlin",     ["build.gradle.kts"]),
    ("csharp",     ["*.csproj", "*.sln"]),
    ("dart",       ["pubspec.yaml"]),
    ("scala",      ["build.sbt"]),
]


# Frameworks — heuristic, dependency-manifest based
_FRAMEWORK_FILE_RULES: list[tuple[str, list[str]]] = [
    ("nextjs",      ["next.config.js", "next.config.mjs", "next.config.ts"]),
    ("nuxt",        ["nuxt.config.ts", "nuxt.config.js"]),
    ("remix",       ["remix.config.js", "remix.config.ts"]),
    ("astro",       ["astro.config.mjs", "astro.config.ts"]),
    ("sveltekit",   ["svelte.config.js", "svelte.config.ts"]),
    ("vite",        ["vite.config.js", "vite.config.ts"]),
    ("django",      ["manage.py"]),
    ("rails",       ["config/application.rb", "config/routes.rb"]),
    ("phoenix",     ["lib/*_web.ex"]),  # rough
    ("laravel",     ["artisan"]),
]

# Frameworks via package.json content (substring match)
_FRAMEWORK_NPM_RULES: list[tuple[str, str]] = [
    ("react",       '"react"'),
    ("vue",         '"vue"'),
    ("nextjs",      '"next"'),
    ("expressjs",   '"express"'),
    ("nestjs",      '"@nestjs/core"'),
    ("fastify",     '"fastify"'),
    ("svelte",      '"svelte"'),
    ("angular",     '"@angular/core"'),
]

# Frameworks via pyproject/requirements
_FRAMEWORK_PY_RULES: list[tuple[str, list[tuple[str, str]]]] = [
    ("fastapi",     [("pyproject.toml", "fastapi"), ("requirements.txt", "fastapi")]),
    ("django",      [("pyproject.toml", "django"), ("requirements.txt", "Django")]),
    ("flask",       [("pyproject.toml", "flask"), ("requirements.txt", "Flask")]),
]


_TEST_RUNNER_RULES: list[tuple[str, list[str]]] = [
    ("pytest",      ["pytest.ini", "pyproject.toml", "tests"]),
    ("vitest",      ["vitest.config.ts", "vitest.config.js", "vitest.config.mts"]),
    ("jest",        ["jest.config.js", "jest.config.ts"]),
    ("mocha",       [".mocharc.js", ".mocharc.json"]),
    ("playwright",  ["playwright.config.ts", "playwright.config.js"]),
    ("cypress",     ["cypress.config.js", "cypress.config.ts"]),
]


# Databases — detected via env files, docker-compose, package-manager hints
_DB_FILE_RULES: list[tuple[str, list[str]]] = [
    ("postgres",    ["docker-compose.yml", "docker-compose.yaml", ".env", ".env.example"]),
    ("redis",       ["docker-compose.yml", "docker-compose.yaml", ".env", ".env.example"]),
    ("mongodb",     ["docker-compose.yml", "docker-compose.yaml", ".env", ".env.example"]),
    ("mysql",       ["docker-compose.yml", "docker-compose.yaml", ".env", ".env.example"]),
    ("sqlite",      ["dev.db", "db.sqlite3"]),
]

_DB_KEYWORD: dict[str, str] = {
    "postgres":   "postgres",
    "redis":      "redis",
    "mongodb":    "mongo",
    "mysql":      "mysql",
}


_DEPLOY_RULES: list[tuple[str, list[str]]] = [
    ("vercel",        ["vercel.json", ".vercel"]),
    ("netlify",       ["netlify.toml"]),
    ("railway",       ["railway.json", "railway.toml"]),
    ("render",        ["render.yaml"]),
    ("fly.io",        ["fly.toml"]),
    ("heroku",        ["Procfile", "app.json"]),
    ("docker",        ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]),
    ("kubernetes",    ["k8s", "kubernetes", "deployment.yaml"]),
]


_CI_RULES: list[tuple[str, list[str]]] = [
    ("github-actions",  [".github/workflows"]),
    ("gitlab-ci",       [".gitlab-ci.yml"]),
    ("circleci",        [".circleci/config.yml"]),
    ("travis",          [".travis.yml"]),
    ("buildkite",       [".buildkite/pipeline.yml"]),
    ("jenkins",         ["Jenkinsfile"]),
]


# ---------------------------------------------------------------------------
# Detection driver
# ---------------------------------------------------------------------------


def _detect_file_based(repo: Path, rules: list[tuple[str, list[str]]]) -> list[str]:
    """Walk file-existence rules, return matched slugs in order."""
    detected: list[str] = []
    for slug, names in rules:
        for name in names:
            # `*` triggers glob; otherwise direct exists check
            if "*" in name or "?" in name:
                if _glob_any(repo, name):
                    detected.append(slug)
                    break
            else:
                if _file_exists(repo, name):
                    detected.append(slug)
                    break
    return detected


def _detect_languages(repo: Path) -> list[str]:
    langs = _detect_file_based(repo, _LANGUAGE_RULES)
    # `package.json` alone implies javascript; if tsconfig.json is also present,
    # both javascript and typescript stay (TypeScript projects often compile to JS).
    # No deduplication needed — order matters for "primary" inference upstream.
    return list(dict.fromkeys(langs))  # preserve order, dedupe


def _detect_frameworks(repo: Path) -> list[str]:
    fmw = _detect_file_based(repo, _FRAMEWORK_FILE_RULES)

    # Augment from package.json content
    if (repo / "package.json").exists():
        try:
            pkg = (repo / "package.json").read_text(errors="ignore")
            for slug, needle in _FRAMEWORK_NPM_RULES:
                if needle in pkg and slug not in fmw:
                    fmw.append(slug)
        except (OSError, PermissionError):
            pass

    # Augment from Python manifests
    for slug, checks in _FRAMEWORK_PY_RULES:
        for fname, needle in checks:
            if _read_contains(repo, fname, needle):
                if slug not in fmw:
                    fmw.append(slug)
                break

    return fmw


def _detect_test_runners(repo: Path) -> list[str]:
    detected: list[str] = []
    for slug, names in _TEST_RUNNER_RULES:
        if slug == "pytest":
            # pytest is implied by either a pyproject.toml referencing pytest
            # or an actual tests/ dir + python files
            if _read_contains(repo, "pyproject.toml", "pytest") or \
               (repo / "pytest.ini").exists() or \
               ((repo / "tests").is_dir() and any((repo / "tests").glob("test_*.py"))):
                detected.append(slug)
        elif slug == "jest":
            # jest config OR `"jest"` in package.json
            if any((repo / n).exists() for n in names) or \
               _read_contains(repo, "package.json", '"jest"'):
                detected.append(slug)
        else:
            if any((repo / n).exists() for n in names):
                detected.append(slug)
    return detected


def _detect_databases(repo: Path) -> list[str]:
    detected: list[str] = []
    for slug in _DB_KEYWORD:
        keyword = _DB_KEYWORD[slug]
        # Look for the keyword in common env / compose / config files
        candidates = ["docker-compose.yml", "docker-compose.yaml", ".env",
                      ".env.example", "config.yml", "config.yaml"]
        for fname in candidates:
            if _read_contains(repo, fname, keyword):
                detected.append(slug)
                break

    # sqlite — direct file presence
    if (repo / "dev.db").exists() or (repo / "db.sqlite3").exists() or \
       any(repo.glob("*.sqlite")):
        if "sqlite" not in detected:
            detected.append("sqlite")
    return detected


def _detect_deploy(repo: Path) -> list[str]:
    return _detect_file_based(repo, _DEPLOY_RULES)


def _detect_ci(repo: Path) -> list[str]:
    detected: list[str] = []
    for slug, names in _CI_RULES:
        for name in names:
            target = repo / name
            if name.endswith("workflows"):
                # github-actions: .github/workflows is a directory with .yml files
                if target.is_dir() and any(target.glob("*.yml")) or any(target.glob("*.yaml")):
                    detected.append(slug)
                    break
            else:
                if target.exists():
                    detected.append(slug)
                    break
    return detected


def detect_stack(repo_path: str | Path) -> dict[str, Any]:
    """Run all detection rules over the repo and return the metadata dict."""
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise FileNotFoundError(f"Repo path not a directory: {repo}")

    return {
        "languages": _detect_languages(repo),
        "frameworks": _detect_frameworks(repo),
        "test_runners": _detect_test_runners(repo),
        "databases": _detect_databases(repo),
        "deploy_targets": _detect_deploy(repo),
        "ci_providers": _detect_ci(repo),
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect tech stack of a cloned product repository."
    )
    parser.add_argument("repo", help="Path to the cloned repo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    try:
        metadata = detect_stack(args.repo)
    except FileNotFoundError as e:
        print(f"stack-detector: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(metadata, indent=2))
    else:
        for k, v in metadata.items():
            if isinstance(v, list):
                print(f"  {k:15} {', '.join(v) if v else '(none)'}")
            else:
                print(f"  {k:15} {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
