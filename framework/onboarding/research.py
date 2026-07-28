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


# ---------------------------------------------------------------------------
# CONNECTOR REGISTRY — what is ACTUALLY connected, probed rather than declared.
# ---------------------------------------------------------------------------
# WHY THIS EXISTS. ``framework.onboarding.journey.entry_plan`` classifies entry
# into connected / seeded / ungranted, and the ``connected`` mode — "sources are
# connected, so sweep them, derive, and ASSERT with a citation" — is the exact
# mechanism of the Captain's 2026-07-26 ruling. Its reader consulted a state key
# (``entry_grants``) that NOTHING in the tree ever wrote, so the mode was
# structurally unreachable: two of three advertised modes could fire and the one
# the direction is about could not. This is the writer.
#
# PROBED, NEVER DECLARED — and that distinction is the whole design. A row in a
# config file saying "jira" is a claim; a HEAD that resolves to a sha is a fact.
# Every probe below answers by DOING its cheapest read and reports what it saw;
# a probe that cannot complete is REFUSED WITH ITS REASON rather than dropped,
# because a silent skip is how "nothing is connected" and "I never looked"
# become indistinguishable — the same defect class as a sweep claiming a
# negative it never earned, one surface up.
#
# NO NETWORK, NO CREDENTIALS, NO SUBPROCESS. Every probe is a bounded local
# file read. That is not a limitation to be lifted later: the ingest hypothesis
# was REFUTED by decisive experiment (of four findings, one needed more than one
# file and ZERO needed more than one system), so the adjudicated first build is
# a small cross-source JOIN with a named consumer, not an ingest engine. A probe
# that needed a credential would be the first brick of the engine that was
# refuted.
#
# DELIBERATELY NOT A CONNECTOR: the MCP estate above. ``inventory_mcp_estate``
# reads the CABINET's declared servers (.mcp.json, extensions.yml) — the wrong
# subject, as the altitude direction gate found. Counting it here would let a
# cabinet that has connected nothing of the OPERATOR's world enter the connected
# mode and assert about an estate it never read.
CONNECTOR_REGISTRY_SCHEMA = "cabinet.connector-registry/v1"
_EGRESS_REL = "instance/config/egress.yml"
#: A resolved git object id: sha-1 today, sha-256 for a repo created with
#: ``--object-format=sha256``. Anything else is an unresolved HEAD.
_GIT_OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def _packed_ref(git_dir: Path, ref: str):
    """Resolve one ref from ``.git/packed-refs``. A fresh clone packs its refs,
    so a loose-file-only reader would call a perfectly live repo unresolvable."""
    try:
        text = (git_dir / "packed-refs").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return None


def _probe_repo(source_root) -> dict:
    """Is a version-control system connected? Only if its HEAD RESOLVES.

    The degenerate end is the point: a ``.git`` directory that exists but whose
    HEAD names a ref with no object is a repo the cabinet cannot read, and
    counting it would put the connected mode's assert-with-citation promise
    behind a source that answers nothing. The sweep never sees this — ``.git``
    is in ``SKIP_DIRS`` — so this is a genuinely second system, read here and
    nowhere else.
    """
    row = {"kind": "repo", "name": "repo", "connected": False}
    if not source_root:
        return {**row, "reason": "no_ratified_source"}
    root = Path(source_root)
    git = root / ".git"
    if not git.is_dir():
        return {**row, "reason": "no_git_dir"}
    try:
        head = (git / "HEAD").read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return {**row, "reason": "git_head_unreadable"}
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        # A ref is a repo-relative path segment sequence; ".." or an absolute
        # form would read outside .git, so it is refused rather than resolved.
        if not ref.startswith("refs/") or ".." in ref.split("/"):
            return {**row, "reason": "git_head_unresolvable"}
        try:
            head = git.joinpath(*ref.split("/")).read_text(
                encoding="utf-8", errors="ignore").strip()
        except OSError:
            head = _packed_ref(git, ref) or ""
    if not _GIT_OID_RE.match(head):
        return {**row, "reason": "git_head_unresolvable"}
    return {
        "kind": "repo",
        "name": f"repo:{root.name}",
        "connected": True,
        "evidence": f"HEAD {head[:12]}",
    }


def _probe_web(root) -> dict:
    """Is the web reachable? The egress ceiling decides, and it is FAIL-CLOSED.

    ``instance/config/egress.yml`` is the Captain-owned live switch. An absent
    or unparseable file is NOT permission — it is an unknown ceiling, and an
    unknown ceiling reads as closed. Without this the seed question's web
    probes would be emitted against a plane that would refuse every one of
    them, which is an interview whose answers go nowhere.
    """
    row = {"kind": "web", "name": "web", "connected": False}
    path = Path(root).expanduser() / _EGRESS_REL
    if not path.is_file():
        return {**row, "reason": "egress_config_absent"}
    try:
        import yaml  # local: keep the module import-light

        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {**row, "reason": "egress_config_unreadable"}
    if not isinstance(doc, dict):
        return {**row, "reason": "egress_config_unreadable"}
    hosts = doc.get("allow_hosts")
    hosts = [str(h) for h in hosts if str(h).strip()] if isinstance(hosts, list) else []
    if doc.get("enforce") is False:
        return {"kind": "web", "name": "web", "connected": True,
                "evidence": "egress unenforced"}
    if not hosts:
        return {**row, "reason": "egress_closed_no_allowed_hosts"}
    return {"kind": "web", "name": "web", "connected": True,
            "evidence": f"{len(hosts)} allowed host(s)"}


def _probe_exports(exports, source_root=None) -> list:
    """Structured tracker exports the charter-bound read already PARSED.

    Half of this probe cannot run here and says so by construction: proving an
    export is real means reading its ROWS, and reading file contents is only
    lawful inside a Captain-ratified Charter. So ``framework.onboarding.journey``
    does the reading and hands the counts in; the vocabulary, the merge and the
    grant derivation stay in one place.

    THE OTHER HALF RUNS EVERY TIME, and it is the difference between a probe and
    a declaration. A row count persisted at ratification is a fact about the
    past; whether that file is still there is a fact about now. Without this
    stat a deleted export would keep granting the connected mode forever — the
    cabinet asserting against a source that no longer exists, which is the exact
    failure "probed, never declared" is here to prevent. A file that parsed to
    ZERO rows is likewise refused, not counted: a tracker with no rows is a
    file, not a connection.
    """
    rows = []
    base = Path(source_root) if source_root else None
    for export in exports or ():
        if not isinstance(export, dict):
            continue
        path = str(export.get("path") or "").strip()
        if not path:
            continue
        try:
            count = int(export.get("rows") or 0)
        except (TypeError, ValueError):
            count = 0
        row = {"kind": "tracker_export", "name": f"tracker_export:{path}",
               "connected": False}
        if base is not None and not (base / path).is_file():
            rows.append({**row, "reason": "export_missing"})
        elif count > 0:
            rows.append({"kind": "tracker_export", "name": f"tracker_export:{path}",
                         "connected": True, "evidence": f"{count} row(s)"})
        else:
            rows.append({**row, "reason": "export_parsed_no_rows"})
    return rows


def probe_connectors(root, *, source_root=None, ratified=False, exports=()) -> dict:
    """The registry: every probe, its verdict, and the grants that follow.

    ``grants`` is the three-key block the entry-mode reader consults, and it is
    DERIVED here rather than declared anywhere: ``connectors`` are the names of
    probes that answered, ``local_files`` is a Captain-ratified First Window,
    ``web`` is the egress ceiling. ``refused`` carries every probe that did not
    answer WITH ITS REASON, so "nothing is connected" is always accompanied by
    what was tried.
    """
    probed = [_probe_repo(source_root if ratified else None)]
    probed.extend(_probe_exports(exports, source_root if ratified else None))
    probed.append(_probe_web(root))
    connected = [r for r in probed if r.get("connected")]
    refused = [r for r in probed if not r.get("connected")]
    return {
        "schema": CONNECTOR_REGISTRY_SCHEMA,
        "connected": connected,
        "refused": refused,
        "grants": {
            # ``web`` is a REACHABILITY grant, not a connected source: it names
            # no estate, so it must not put entry into the connected mode where
            # the cabinet would claim to have read the operator's world.
            "connectors": sorted(r["name"] for r in connected if r["kind"] != "web"),
            "local_files": bool(ratified),
            "web": any(r["kind"] == "web" for r in connected),
        },
    }
