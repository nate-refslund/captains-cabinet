"""research_repo — read a LOCAL product repo into a profile.

No network, no mutation, and NEVER reads .env / secret files: it inspects
package.json / pyproject / README / .claude config / .mcp.json / .git config
for NAMES (deps, plugins, repo url), never values. This is the gather-then-decide
front end of onboarding — the Chair learns what a product IS before wiring it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# package.json dependency name (exact or prefix) → stack tag
_DEP_STACK = {
    "next": "nextjs", "@neondatabase": "neon", "@vercel": "vercel",
    "react": "react", "drizzle-orm": "drizzle", "tailwindcss": "tailwind",
    "@modelcontextprotocol": "mcp-server", "stripe": "stripe", "playwright": "playwright",
}


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _name(repo: Path) -> str:
    pkg = _read_json(repo / "package.json")
    if isinstance(pkg, dict) and pkg.get("name"):
        return str(pkg["name"])
    pyproj = repo / "pyproject.toml"
    if pyproj.is_file():
        m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)',
                      pyproj.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(1)
    return repo.name


def _summary(repo: Path) -> str:
    for fn in ("README.md", "README.rst", "README.txt", "readme.md"):
        f = repo / fn
        if not f.is_file():
            continue
        paras = [p.strip() for p in re.split(r"\n\s*\n", f.read_text(errors="ignore")) if p.strip()]
        for p in paras:
            if p.lstrip().startswith("#") and "\n" not in p.strip():
                continue  # a lone heading line
            cleaned = re.sub(r"^#+\s.*\n", "", p) if p.lstrip().startswith("#") else p
            cleaned = " ".join(cleaned.split())
            if cleaned:
                return cleaned[:300]
        return ""
    return ""


def _stack(repo: Path) -> list:
    tags = set()
    pkg = _read_json(repo / "package.json")
    if isinstance(pkg, dict):
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        for dep in deps:
            for needle, tag in _DEP_STACK.items():
                if dep == needle or dep.startswith(needle):
                    tags.add(tag)
    if (repo / "pyproject.toml").is_file() or (repo / "requirements.txt").is_file():
        tags.add("python")
    return sorted(tags)


def _plugins(repo: Path) -> list:
    found = set()
    for fn in ("settings.json", "settings.local.json"):
        data = _read_json(repo / ".claude" / fn)
        if isinstance(data, dict):
            for entry in (data.get("enabledPlugins") or []):
                found.add(str(entry).split("@")[0])
    mcp = _read_json(repo / ".mcp.json")
    if isinstance(mcp, dict):
        for k in (mcp.get("mcpServers") or {}):
            found.add(str(k))
    return sorted(found)


def _repo_url(repo: Path):
    cfg = repo / ".git" / "config"
    if not cfg.is_file():
        return None
    m = re.search(r"url\s*=\s*(\S+)", cfg.read_text(errors="ignore"))
    if not m:
        return None
    url = m.group(1).strip()
    if url.endswith(".git"):
        url = url[:-4]
    ssh = re.match(r"git@([^:]+):(.+)", url)  # git@github.com:org/repo → https
    if ssh:
        url = f"https://{ssh.group(1)}/{ssh.group(2)}"
    return url


def research_repo(repo_path: str) -> dict:
    """Read a local product repo → a profile dict. Reads NAMES only, never .env."""
    repo = Path(repo_path).expanduser()
    if not repo.is_dir():
        raise FileNotFoundError(f"repo path not a directory: {repo}")
    return {
        "name": _name(repo),
        "summary": _summary(repo),
        "stack": _stack(repo),
        "plugins": _plugins(repo),
        "repo_url": _repo_url(repo),
        "has_claude": (repo / ".claude").is_dir(),
        "path": str(repo),
    }
