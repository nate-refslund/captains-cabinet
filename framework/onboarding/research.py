"""research_repo — read a LOCAL product repo into a profile.

No network, no mutation, and NEVER reads .env / secret files: it inspects
package.json / pyproject / README / .claude config / .mcp.json / .git config
for NAMES (deps, plugins, repo url), never values. This is the gather-then-decide
front end of onboarding — the Chair learns what a product IS before wiring it.

Also home to ``inventory_mcp_estate`` (Phase 2, onboarding-vision-2026-07-14):
the interview's consent-gated MCP-estate glance — server NAMES only, from the
repo's declared surfaces, honoring the null-hatch zero-captain-data spirit
(no consent ⇒ no reads at all).
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


# ---------------------------------------------------------------------------
# MCP-estate inventory (Phase 2, onboarding-vision-2026-07-14 §4) — NAMES only.
# ---------------------------------------------------------------------------
_EXTENSIONS_REL = "instance/config/extensions.yml"


def _extension_mcp_names(doc) -> list:
    """`name:` fields under the extensions file's ``mcps:`` list — nothing
    else is ever surfaced (no urls, no env names, no headers)."""
    if not isinstance(doc, dict):
        return []
    return [str(e["name"]) for e in (doc.get("mcps") or [])
            if isinstance(e, dict) and str(e.get("name") or "").strip()]


def inventory_mcp_estate(root: str, *, consent: bool = False) -> dict:
    """Consent-gated MCP-estate glance: server NAMES only, never values.

    NULL-HATCH SPIRIT: without an explicit ``consent=True`` (the Captain's
    in-interview yes) this reads NOTHING — not even a stat beyond the root —
    and returns an honest ``{"consented": False, "servers": [], "sources": []}``.
    With consent it surveys ONLY two declared surfaces under ``root``:

    * ``.mcp.json`` — the KEYS of ``mcpServers`` (command/url/env/headers are
      never read into the result), and
    * ``instance/config/extensions.yml`` (or its ``.example`` sibling when the
      real file does not exist) — each ``mcps:`` entry's ``name`` field.

    Never the user-level Claude config (Open Captain Call #4 — the consent
    boundary for that surface is unruled, so it stays out), never ``.env``.
    Parse failures are honest empties, never a traceback. ``sources`` lists
    the root-relative paths actually consulted."""
    if consent is not True:
        return {"consented": False, "servers": [], "sources": []}

    base = Path(root).expanduser()
    servers: set = set()
    sources: list = []

    mcp = _read_json(base / ".mcp.json")
    if isinstance(mcp, dict) and isinstance(mcp.get("mcpServers"), dict):
        servers.update(str(k) for k in mcp["mcpServers"])
        sources.append(".mcp.json")

    ext_rel = _EXTENSIONS_REL
    ext_path = base / ext_rel
    if not ext_path.is_file():
        ext_rel = _EXTENSIONS_REL + ".example"
        ext_path = base / ext_rel
    if ext_path.is_file():
        try:
            import yaml  # local: keep the module import-light
            names = _extension_mcp_names(
                yaml.safe_load(ext_path.read_text(encoding="utf-8")))
        except Exception:
            names = []
        else:
            sources.append(ext_rel)
        servers.update(names)

    return {"consented": True, "servers": sorted(servers), "sources": sources}
