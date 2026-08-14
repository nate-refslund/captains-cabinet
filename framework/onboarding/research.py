"""research_repo — read a LOCAL product repo into a profile.

No network, no mutation, and NEVER reads .env / secret files: it inspects
package.json / pyproject / README / .claude config / .mcp.json / .git config
for NAMES (deps, plugins, repo url), never values. This is the gather-then-decide
front end of onboarding — the Chair learns what a product IS before wiring it.

Also home to ``inventory_mcp_estate`` (Phase 2, onboarding-vision-2026-07-14):
the interview's consent-gated MCP-estate glance — server NAMES only, from the
repo's declared surfaces, honoring the null-hatch zero-captain-data spirit
(no consent ⇒ no reads at all).

AND to the CONNECTOR READ LANE (Captain ruling 2026-07-29 — "gather from
connectors through read-only"): ``sweep_connectors`` takes the credentials the
operator declared in ``instance/config/connectors.yml``, calls each connector's
inventory endpoint READ-ONLY, and returns names, dates, actors and counts. It
reaches the network on purpose; the read-only ceiling is mechanical, the
verb set is unreachable-by-construction, and nothing about any tool, vendor or
industry is known to this module. See the section header above it for the full
contract and for why the module's former "no network, no credentials" law was
superseded rather than merely relaxed.

AND to the SEARCH PLANE (``run_search_probes``), which is where the seed
question's outward probes actually RUN. The onboarding core proposes them and
holds no socket; this module holds the socket, so a few words from the operator
become a real look outward instead of a plan nobody executed. Same shape as the
read lane above and the same law: the operator declares a search tool in
``instance/config/connectors.yml``, this module knows only "a query goes HERE
and results come back THERE", and every answer that comes back is UNTRUSTED
TEXT which is displayed and matched, never interpreted.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
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
    Parse failures are honest empties, never a traceback. ``sources`` lists ONLY
    the paths a declaration block was read FROM — not the paths consulted, and
    NOT every path read: the two surfaces differ, measured, and the difference is
    not deliberate. A ``.mcp.json`` parsed fine without ``mcpServers`` is absent
    from ``sources``; an extensions file parsed fine without ``mcps:`` is listed.
    So an unreadable pair, a pair declaring nothing, and a bare root can all
    return one document, and it cannot tell "I looked" from "I never looked" —
    the conflation this section exists to refuse, surviving inside it. Pinned by
    ``test_inventory_bare_root_and_malformed_are_honest_empties`` and by
    ``test_sources_omits_a_read_path_that_declared_nothing``; both the split and
    the symmetry want a behaviour change, not a quieter sentence."""
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
# THE PROBES ARE LOCAL; THE READ LANE BELOW IS NOT — and the sentence that used
# to stand here ("no network, no credentials ... not a limitation to be lifted
# later") was SUPERSEDED by Captain ruling 2026-07-29: "GATHER FROM CONNECTORS
# THROUGH READ-ONLY, and websearch/internet/network is allow-all by default",
# restating the 2026-07-26 ordering inversion ("during onboarding, connect tools
# and then gather information ... through that, the cabinet may even know
# everything about the company and projects and products and teams").
#
# WHY THE OLD SENTENCE WAS WRONG, stated so it cannot come back. It justified
# itself with the ingest experiment — "of four findings, one needed more than
# one file and ZERO needed more than one system". That experiment refuted
# INGEST-EVERYTHING-INTO-A-VAULT; its fixture's second system was a CSV ALREADY
# ON DISK, so the network hop was presupposed as done by a human. No-credential
# was never an experimental arm, and a refutation of ingest is not a refutation
# of LOOKING. The tree said so one module over: ``framework.onboarding.estate``
# already recorded that widening to new source kinds "is a later unit; the
# schema below already has the shape for them".
#
# WHAT IS STILL TRUE, and is now enforced by code rather than by a comment: the
# probes in THIS section stay bounded local file reads, because they run on
# every commit and every snapshot. The credentialed lane is a SEPARATE,
# operator-triggered pass (``sweep_connectors``) whose result the probes then
# read off state — so a hot path never opens a socket, and a connector that has
# not been swept cannot grant the connected mode.
#
# NEVER WRITE, NEVER SEND. That ceiling is not configurable and is asserted
# MECHANICALLY before a socket exists (``assert_read_only``): GET, or a POST
# whose body is a GraphQL read document carrying no ``mutation``/``subscription``
# token. There is no code path in this module that can emit any other verb.
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


def _probe_sweep(sweep) -> list:
    """Rows for every connector a credentialed sweep actually READ.

    THE ONLY EVIDENCE ACCEPTED HERE IS A COMPLETED READ. A declaration in
    ``instance/config/connectors.yml`` grants nothing — that is a claim, and the
    section header above says why claims do not count. What this reads is the
    contents-free summary ``sweep_connectors`` persisted onto the journey's own
    state: a connector row appears as connected only when that pass came back
    with at least one item, and every connector that was declared and did NOT
    answer arrives here carrying the reason it did not (``credential_absent``,
    ``egress_closed_no_allowed_hosts``, ``http_401`` ...). A declared connector
    that is silently dropped would make "nothing is connected" and "I never
    looked" indistinguishable, one surface up from where that already bit.

    Local by construction: the sweep already happened, in its own operator-
    triggered action. Nothing in this function opens a socket.
    """
    rows = []
    if not isinstance(sweep, dict):
        return rows
    for entry in sweep.get("connectors") or ():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        row = {"kind": "connector", "name": f"connector:{name}", "connected": False}
        try:
            items = int(entry.get("items") or 0)
        except (TypeError, ValueError):
            items = 0
        if entry.get("connected") and items > 0:
            rows.append({**row, "connected": True, "evidence": f"{items} item(s)"})
        else:
            rows.append({**row, "reason": str(entry.get("reason") or "sweep_returned_nothing")})
    return rows


def probe_connectors(root, *, source_root=None, ratified=False, exports=(),
                     sweep=None) -> dict:
    """The registry: every probe, its verdict, and the grants that follow.

    ``grants`` is the three-key block the entry-mode reader consults, and it is
    DERIVED here rather than declared anywhere: ``connectors`` are the names of
    probes that answered, ``local_files`` is a Captain-ratified First Window,
    ``web`` is the egress ceiling. ``refused`` carries every probe that did not
    answer WITH ITS REASON, so "nothing is connected" is always accompanied by
    what was tried.

    ``sweep`` is the contents-free result of the credentialed read lane, handed
    in from state so this stays a local read (see ``_probe_sweep``).
    """
    probed = [_probe_repo(source_root if ratified else None)]
    probed.extend(_probe_exports(exports, source_root if ratified else None))
    probed.extend(_probe_sweep(sweep))
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


# ---------------------------------------------------------------------------
# THE READ LANE — credentialed, READ-ONLY gathering (Captain ruling 2026-07-29).
# ---------------------------------------------------------------------------
# WHAT THIS IS. The LOOK step of look -> infer -> ask -> go deeper: bounded,
# contents-free, and outward. It answers "what is this operator connected to,
# and what is in there" with names, dates, actors and counts — never bodies,
# never rows, never a field the operator did not declare.
#
# AGNOSTIC TO EVERYTHING, and that is a code property rather than an intention.
# NOTHING in this module names a tool, a vendor, a host, an industry, a role or
# an entity kind. A connector is exactly three things: a credential, an
# inventory call, and a timestamp field. Whoever the operator is, whatever they
# use, they describe it in ``instance/config/connectors.yml`` — the instance
# layer, where deployment specifics belong — and this executor knows only the
# shape. Ask what a connector IS and the honest answer is "the operator told
# me"; that is the whole design, and it is why the framework must never grow a
# per-system client.
#
# THE CEILING, which is not configurable:
#   * READ ONLY. ``assert_read_only`` runs BEFORE a socket exists. GET, or a
#     POST whose body is a GraphQL read document with no ``mutation`` /
#     ``subscription`` token. Every other verb is unreachable — there is no
#     branch in this file that can emit one — and a method-override header is
#     refused, because a write smuggled inside a GET is still a write.
#   * NO REDIRECTS. The credential goes to the declared origin or nowhere. A
#     followed 30x hands an Authorization header to whatever the response says,
#     which turns a config file into an exfiltration primitive.
#   * BOUNDED. A call budget, a per-call timeout, a response-size cap and an
#     item cap, all enforced here rather than trusted to the far end.
#   * CONTENTS-FREE. Only the declared name / updated / actor paths are read out
#     of each item, each coerced to a short scalar string. An actor path may
#     resolve to a PERSON-SHAPED object or a list of them, so that one step is
#     walked at a fixed key set and a per-row cap; nothing else is descended
#     into. The response body is never persisted and never returned.
#
# EVERY FAILURE IS NAMED. A connector that does not answer is REFUSED WITH ITS
# REASON, never dropped: a missing credential, a closed egress ceiling, an HTTP
# status, an unparseable body and a truncated page all read differently, and
# collapsing them is how "nothing is connected" gets confused with "I never
# looked" — the failure this program has now paid for at three altitudes.
#
# AND A DECLARATION THAT MISSED IS NOT AN EMPTY ESTATE. The same rule applied
# one level down, where it was being broken: a mistyped ``items_path`` returned
# no items, and no items was reported as ``inventory_returned_no_items`` — the
# reason an empty system gets. So the operator's first pass at their own config,
# the moment this lane is most likely to be wrong, read back as "you have
# nothing there". Every declared path now reports whether it RESOLVED, and a
# path that never did is named as itself.
CONNECTOR_SWEEP_SCHEMA = "cabinet.connector-sweep/v1"
CONNECTORS_REL = "instance/config/connectors.yml"
#: The curated catalog onboarding offers, shipped as DATA in the instance
#: layer (it ships as an ``.example`` twin; the framework names no vendor). Read
#: as a full one-string path so the layer-separation gate, which flags a bare
#: ``"instance"`` token, does not read this as a framework->instance coupling —
#: the same reason ``CONNECTORS_REL`` above is written this way.
TEMPLATES_REL = "instance/config/connector-templates.yml.example"
CONNECTOR_TEMPLATES_SCHEMA = "cabinet.connector-templates/v1"
#: An env var NAME the credential is stored under. The SAME anchor the dashboard
#: env-var editor enforces (actions/env.ts), so a name accepted here is one the
#: safe .env writer will also accept.
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
#: The longest an operator-supplied template field (a custom URL, a dotted path)
#: may be. A list URL with query args is the long case; a body has no business
#: arriving through a path field, so this is generous, not unbounded.
_MAX_DECLARED_FIELD_CHARS = 2000
#: The longest a connector label may be. It is shown, never parsed.
_MAX_CONNECTOR_NAME_CHARS = 120

#: The only verbs reachable from this module. POST is admitted solely because a
#: read-only GraphQL query cannot be expressed as a GET on most endpoints.
_READ_METHODS = frozenset({"GET", "POST"})
#: A lawful POST body is a GraphQL document and nothing else. Restricting the
#: KEY SET is what stops "POST is allowed" from meaning "any REST write is
#: allowed": a JSON payload that is not {query, variables, operationName} is
#: refused before its content is even inspected.
_GRAPHQL_BODY_KEYS = frozenset({"query", "variables", "operationName"})
#: Token-boundary match, so a board named "Mutations" in a query string cannot
#: be mistaken for the keyword and a keyword cannot hide inside an identifier.
_WRITE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(mutation|subscription)(?![A-Za-z0-9_])", re.IGNORECASE)
#: Headers that ask a server to treat this request as a different verb. A read
#: lane that permits one is a write lane wearing a GET.
_METHOD_OVERRIDE_HEADERS = frozenset(
    {"x-http-method-override", "x-method-override", "x-http-method"})
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_FIELD_CHARS = 200
_DEFAULT_MAX_CALLS = 40
_DEFAULT_TIMEOUT = 25.0
_DEFAULT_MAX_ITEMS = 2000
_DEFAULT_MAX_PAGES = 12
#: The clock encodings a connector may DECLARE. A clock that exists in another
#: encoding is not an absent clock: read as text, an epoch stamp fails every
#: ISO test downstream and the sweep tells the operator "nothing I read carried
#: a date" about an estate that dates every row — a sensor describing itself
#: rather than the estate. Declared, never sniffed: guessing is how a 1970 date
#: appears, and an encoding this module does not know is REFUSED by name rather
#: than silently read as ISO.
_DATE_ENCODINGS = frozenset({"iso", "epoch_ms", "epoch_s"})
#: The keys an actor object may carry its name under, in preference order. Not a
#: taxonomy of people — a list of the words systems put a display name behind,
#: and the last resort is an opaque id, which still DISTINGUISHES two actors even
#: when it names neither.
#:
#: THE ORDER IS THE WHOLE CONTROL, and it is ordered by how well each word
#: DISTINGUISHES one person from another rather than by how nicely it reads. The
#: identifiers come before the descriptions: a person object that carries no name
#: and no handle but does carry a role word and an address resolved to the ROLE
#: while `title` outranked `email`, so two different people collapsed into one
#: actor, the distinct-actor count under-reported, and every row was attributed
#: to a word that is not anybody. A count that merges two people is worse than a
#: name nobody recognises, because only one of the two announces itself.
_ACTOR_NAME_KEYS = ("name", "login", "email", "id", "title")
#: Actors kept per item. A declared path that resolves to a list of two hundred
#: participants is a body arriving through the actor door; the cap holds the
#: contents-free property without refusing the ordinary two-or-three case.
_MAX_ACTORS_PER_ITEM = 8


class ReadOnlyViolation(RuntimeError):
    """A declared call could write. Raised BEFORE any socket is opened."""


def assert_read_only(call) -> None:
    """Mechanically refuse anything that is not a read. No network here.

    This is the Captain's one absolute limit expressed as code rather than as a
    promise: read freely, write never. It runs on the DECLARATION, so a spec
    that could write is refused at the config boundary and the credential is
    never even fetched, let alone sent.
    """
    if not isinstance(call, dict):
        raise ReadOnlyViolation("call_not_a_mapping")
    url = str(call.get("url") or "").strip()
    if not url.lower().startswith("https://"):
        raise ReadOnlyViolation("url_not_https")
    if len(url.split("://", 1)[1].split("/", 1)[0].strip()) == 0:
        raise ReadOnlyViolation("url_has_no_host")
    method = str(call.get("method") or "GET").strip().upper()
    if method not in _READ_METHODS:
        raise ReadOnlyViolation(f"method_not_read_only:{method}")
    headers = call.get("headers") or {}
    if not isinstance(headers, dict):
        raise ReadOnlyViolation("headers_not_a_mapping")
    # THE DECLARED HEADERS ARE NOT THE WHOLE WIRE. ``_request_of`` injects one
    # MORE header — the credential's, under whatever ``auth_header`` the spec
    # names — so checking only ``headers`` left the override channel open by
    # the back door: ``auth_header: X-HTTP-Method-Override`` with
    # ``auth_format: DELETE`` was emitted on a request this function had just
    # certified as a read (found by attacking the ceiling, 2026-07-29). Every
    # header name this module can put on the wire is checked here, or the
    # ceiling is a claim rather than a control.
    for key in (*headers, str(call.get("auth_header") or "Authorization")):
        if str(key).strip().lower() in _METHOD_OVERRIDE_HEADERS:
            raise ReadOnlyViolation(f"method_override_header:{key}")
    body = call.get("json")
    if method == "GET":
        if body is not None:
            raise ReadOnlyViolation("get_with_body")
        if _WRITE_TOKEN_RE.search(url):
            raise ReadOnlyViolation("write_token_in_url")
        return
    if not isinstance(body, dict):
        raise ReadOnlyViolation("post_body_not_a_graphql_document")
    if set(body) - _GRAPHQL_BODY_KEYS or "query" not in body:
        raise ReadOnlyViolation("post_body_not_a_graphql_document")
    if not isinstance(body.get("query"), str):
        raise ReadOnlyViolation("graphql_query_not_a_string")
    if _WRITE_TOKEN_RE.search(json.dumps(body, ensure_ascii=False)):
        raise ReadOnlyViolation("write_token_in_graphql_document")


def _dig(doc, path):
    """One dotted path into a decoded JSON document. Empty path = the root."""
    cur = doc
    if path in (None, ""):
        return cur
    for part in str(path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _scalar(value):
    """A short scalar string, or None. Containers are NEVER flattened into text:
    that is how a body leaks out of a lane that promised names only."""
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    text = " ".join(str(value).split())
    return text[:_MAX_FIELD_CHARS] or None


def _stamp(value, encoding: str):
    """One declared clock field, normalised to a comparable instant — or None.

    ISO is passed through as the short scalar it already is. An epoch encoding is
    converted here, because every reader downstream (the period, the presence
    question, the ranker's clock admission) tests for a leading ``YYYY-MM-DD``
    and an epoch integer silently fails all three at once.
    """
    if encoding == "iso":
        return _scalar(value)
    if value is None or isinstance(value, bool) or isinstance(value, (dict, list, tuple, set)):
        return None
    try:
        seconds = float(value) / (1000.0 if encoding == "epoch_ms" else 1.0)
        # ZERO AND BELOW ARE SENTINELS, NOT INSTANTS. Systems write 0 for "never
        # set", and converted faithfully that becomes 1970-01-01 — a date, which
        # ranks, sorts and reports as a real reading. Absent is what it means.
        if seconds <= 0:
            return None
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _people(value, budget: int) -> list:
    """The actor names at one declared path: a string, an object, or a list.

    ONE ITEM DOES NOT HAVE EXACTLY ONE ACTOR, and assuming so loses the operator
    precisely where they are most likely to appear — the assignees, the
    participants, the parties. ``_scalar`` returns None for any container, so
    before this the whole list was dropped and the connector reported zero
    distinct actors while carrying the operator's own handle in every row. The
    walk is one level deep, at ``_ACTOR_NAME_KEYS``, capped: enough to read a
    person out of the shape systems store people in, never enough to read a body.
    """
    if value is None or isinstance(value, bool) or budget <= 0:
        return []
    if isinstance(value, dict):
        for key in _ACTOR_NAME_KEYS:
            text = _scalar(value.get(key))
            if text:
                return [text]
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for entry in value:
            out.extend(_people(entry, budget - len(out)))
            if len(out) >= budget:
                return out[:budget]
        return out
    text = _scalar(value)
    return [text] if text else []


def _paged(value, page: int):
    """Substitute the page cursor. ``str.replace``, never ``str.format`` — a
    GraphQL document is full of braces and ``format`` would raise on all of
    them."""
    if isinstance(value, str):
        return value.replace("{page}", str(page))
    if isinstance(value, dict):
        return {k: _paged(v, page) for k, v in value.items()}
    if isinstance(value, list):
        return [_paged(v, page) for v in value]
    return value


def _http_fetch(request, timeout):
    """The only socket in this module. No redirects, capped read.

    Returns ``(status, payload_bytes)``; a transport failure raises. A 30x is
    surfaced as a status rather than followed, so the credential cannot be
    handed to a host the operator never declared.
    """
    import urllib.error  # local: keep the module import-light
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(
        request["url"], data=request.get("body"),
        headers=dict(request.get("headers") or {}), method=request["method"])
    try:
        with opener.open(req, timeout=timeout) as resp:
            return int(getattr(resp, "status", 0) or 0), resp.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:  # includes the refused redirects
        try:
            payload = exc.read(_MAX_RESPONSE_BYTES + 1)
        except Exception:
            payload = b""
        return int(exc.code), payload


def _request_of(call, credential: str, page: int) -> dict:
    """A declared call + a credential -> the wire request. Never logged."""
    headers = {str(k): str(v) for k, v in (call.get("headers") or {}).items()}
    auth_header = str(call.get("auth_header") or "Authorization")
    auth_format = str(call.get("auth_format") or "{credential}")
    headers[auth_header] = auth_format.replace("{credential}", credential)
    body = None
    method = str(call.get("method") or "GET").strip().upper()
    if method == "POST":
        headers.setdefault("Content-Type", "application/json")
        body = json.dumps(_paged(call.get("json") or {}, page),
                          ensure_ascii=False).encode("utf-8")
    return {"url": _paged(str(call["url"]), page), "method": method,
            "headers": headers, "body": body}


def _one_call(call, credential, page, *, fetch, timeout):
    """Execute one declared call. Returns ``(document, reason)`` — exactly one
    of the two is None, so a caller can never mistake an error for an empty
    estate."""
    request = _request_of(call, credential, page)
    try:
        status, payload = fetch(request, timeout)
    except Exception as exc:
        return None, f"unreachable:{type(exc).__name__}"
    if status != 200:
        return None, f"http_{status}"
    if len(payload) > _MAX_RESPONSE_BYTES:
        return None, "response_too_large"
    try:
        return json.loads(payload.decode("utf-8", errors="replace")), None
    except Exception:
        return None, "response_not_json"


def _items_of(doc, call) -> tuple:
    """``(items, reason)`` — the inventory items, or why there are none.

    A single object counts as one item: an estate with exactly one thing in it is
    not an empty estate. And a path that resolved to NOTHING is reported as a
    missed path rather than as an empty list, because those two are the same
    bytes and opposite facts — one says the operator has nothing, the other says
    this module was told to look in the wrong place.
    """
    found = _dig(doc, call.get("items_path"))
    if isinstance(found, list):
        return [i for i in found if isinstance(i, (dict, str, int, float))], None
    if isinstance(found, dict):
        return [found], None
    path = str(call.get("items_path") or "")
    if found is None:
        return [], f"items_path_missed:{path or '(root)'}"
    return [], f"items_path_not_a_list:{path or '(root)'}"


def _sweep_one(spec, credential, *, fetch, timeout, max_items, budget) -> dict:
    """One connector, read read-only, reported contents-free."""
    name = str(spec.get("name") or "").strip()
    call = spec.get("inventory")
    row = {"name": name, "connected": False, "calls": 0,
           "items": 0, "rows": [], "identities": [], "not_reached": []}
    try:
        assert_read_only(call)
    except ReadOnlyViolation as exc:
        return {**row, "reason": f"read_only_refused:{exc}"}
    row["host"] = str(call["url"]).split("://", 1)[1].split("/", 1)[0]
    encoding = str(call.get("date_encoding") or "iso").strip().lower()
    if encoding not in _DATE_ENCODINGS:
        # REFUSED, not read as ISO. A typo here does not lose a clock quietly —
        # it produces a whole sweep with no period, which reads as a fact about
        # the estate. One named word is cheaper to fix than a false negative.
        return {**row, "reason": f"date_encoding_unknown:{encoding}"}
    actor_fields = call.get("actor_field")
    actor_fields = [actor_fields] if isinstance(actor_fields, str) else list(actor_fields or ())
    actor_fields = [str(f) for f in actor_fields if str(f).strip()]

    identity = spec.get("identity")
    if isinstance(identity, dict):
        try:
            assert_read_only(identity)
        except ReadOnlyViolation as exc:
            row["not_reached"].append(f"{name}: identity call refused ({exc})")
        else:
            if budget["left"] > 0:
                budget["left"] -= 1
                row["calls"] += 1
                doc, reason = _one_call(identity, credential, 1,
                                        fetch=fetch, timeout=timeout)
                if reason:
                    row["not_reached"].append(f"{name}: identity unread ({reason})")
                else:
                    for path in identity.get("value_paths") or ():
                        value = _scalar(_dig(doc, path))
                        if value:
                            row["identities"].append(value)

    page_spec = spec.get("page") if isinstance(spec.get("page"), dict) else {}
    try:
        max_pages = max(1, min(int(page_spec.get("max_pages") or 1), _DEFAULT_MAX_PAGES))
    except (TypeError, ValueError):
        max_pages = 1
    try:
        first = int(page_spec.get("start") or 1)
    except (TypeError, ValueError):
        first = 1
    # OPTIONAL, AND IT IS WHAT MAKES THE TRUNCATION CAVEAT EARNED. Declaring the
    # page size the call asked for lets a SHORT final page prove the estate was
    # exhausted, so the "may be larger" sentence is printed only when it is
    # actually true. Undeclared, the caveat is printed on every complete sweep —
    # over-disclosure, which is the safe side of an unearned clean negative.
    try:
        page_size = int(page_spec.get("size") or 0)
    except (TypeError, ValueError):
        page_size = 0

    seen = set()
    reason = None
    page = first
    last_page_items = None
    # What each DECLARED path did, counted while reading rather than inferred
    # afterwards from an absence. "This estate has no clock" and "the clock path
    # I was given never resolved" produce identical rows and want opposite
    # answers from the operator.
    read = 0
    nameless = 0
    stamped = 0
    dated = 0
    peopled = 0
    for page in range(first, first + max_pages):
        if budget["left"] <= 0:
            row["not_reached"].append(f"{name}: call budget spent at page {page}")
            break
        budget["left"] -= 1
        row["calls"] += 1
        doc, reason = _one_call(call, credential, page, fetch=fetch, timeout=timeout)
        if reason:
            break
        items, reason = _items_of(doc, call)
        last_page_items = len(items)
        if not items:
            break
        for item in items:
            read += 1
            title = _scalar(_dig(item, call.get("name_field")) if isinstance(item, dict) else item)
            if not title:
                nameless += 1
                continue
            updated = _stamp(_dig(item, call.get("updated_field")), encoding) \
                if isinstance(item, dict) else None
            actors = []
            if isinstance(item, dict):
                for field in actor_fields:
                    actors.extend(_people(_dig(item, field), _MAX_ACTORS_PER_ITEM - len(actors)))
            stamped += 1 if updated else 0
            dated += 1 if _day(updated) else 0
            peopled += 1 if actors else 0
            key = (title, updated)
            if key in seen:
                continue
            seen.add(key)
            entry = {"connector": name, "name": title, "updated": updated}
            if actors:
                entry["actors"] = actors
            row["rows"].append(entry)
            if len(row["rows"]) >= max_items:
                row["not_reached"].append(
                    f"{name}: stopped at the {max_items}-item cap")
                break
        if len(row["rows"]) >= max_items:
            break
        exhausted = page_size > 0 and last_page_items is not None and last_page_items < page_size
        if page == first + max_pages - 1 and not exhausted:
            row["not_reached"].append(
                f"{name}: stopped after {max_pages} page(s) with a full page still "
                f"coming back — the estate may be larger")
    if reason and not row["rows"]:
        return {**row, "reason": reason}
    # A PAGE PAST THE END IS EXHAUSTION, NOT A MISSED DECLARATION. Sources stop
    # carrying the list once it runs out — `{}`, or the key nulled — and that is
    # the same bytes as a mistyped `items_path`. Here, rows were already read at
    # that very path, so it resolved and the miss is the end of the estate: the
    # only honest reading, and printing the miss instead told an operator whose
    # config is correct that it is not. Every OTHER reason (an HTTP status, an
    # unreachable host, an unparseable body) still surfaces — those are real
    # truncation, and silently dropping them is the failure this lane exists to
    # refuse.
    if reason and not str(reason).startswith("items_path_"):
        row["not_reached"].append(f"{name}: paging stopped early ({reason})")
    row["items"] = len(row["rows"])
    row["items_read"] = read
    row["connected"] = row["items"] > 0
    if not row["connected"]:
        # THREE WAYS TO COME BACK WITH NOTHING, and they are not the same fact.
        row["reason"] = f"name_path_missed:{call.get('name_field') or '(item)'}" \
            if read else "inventory_returned_no_items"
    elif nameless:
        row["not_reached"].append(
            f"{name}: {nameless} of {read} items carried nothing at the declared "
            f"name path ({call.get('name_field') or '(item)'}), so they are not in this ranking")
    if read and call.get("updated_field") and not stamped:
        row["not_reached"].append(
            f"{name}: the declared date path ({call['updated_field']}) resolved on none of "
            f"{read} items, so what looks like an undated system may be a mistyped path")
    elif read and call.get("updated_field") and not dated:
        # PRESENT BUT UNREADABLE is its own answer, and the one the period, the
        # presence question and the ranker's clock admission all fail silently
        # on: every one of them tests for a leading date and gets nothing, so a
        # fully stamped system reports as having no clock. The message names the
        # fix rather than the symptom.
        row["not_reached"].append(
            f"{name}: the declared date path ({call['updated_field']}) resolved on {stamped} of "
            f"{read} items but none of it is a date I can read — if that system stamps in epoch "
            f"time, declare date_encoding: epoch_ms (or epoch_s) beside the path")
    if read and actor_fields and not peopled:
        row["not_reached"].append(
            f"{name}: the declared actor path ({', '.join(actor_fields)}) resolved on none of "
            f"{read} items, so I cannot tell whether any of this is yours")
    dates = sorted(r["updated"] for r in row["rows"] if r.get("updated"))
    row["latest"] = dates[-1] if dates else None
    row["actors"] = len({a for r in row["rows"] for a in (r.get("actors") or ())})
    return row


#: The two lanes a declared connector can belong to, decided by the CALL it
#: carries and never by a label it claims. ``inventory`` is the estate sweep;
#: ``search`` is the outward query the seed question's probes ride. A label
#: would let a declaration choose its own ceiling, and the search ceiling is
#: the looser of the two on body shape — so the lane is read off the slot the
#: author actually filled in, which is the one thing they cannot fake by
#: writing a word.
CONNECTOR_KIND_INVENTORY = "inventory"
CONNECTOR_KIND_SEARCH = "search"


def _spec_kind(entry) -> str:
    """Which lane a declared connector belongs to, or ``""`` for neither.

    ``inventory`` wins when both are present, so every connector declared
    before the search lane existed keeps the exact lane it had.
    """
    if not isinstance(entry, dict):
        return ""
    if isinstance(entry.get(CONNECTOR_KIND_INVENTORY), dict):
        return CONNECTOR_KIND_INVENTORY
    if isinstance(entry.get(CONNECTOR_KIND_SEARCH), dict):
        return CONNECTOR_KIND_SEARCH
    return ""


def load_connector_specs(root, *, not_reached=None,
                         kind=CONNECTOR_KIND_INVENTORY) -> list:
    """Connectors the OPERATOR declared. Absent file = an honest empty list.

    ``kind`` selects the lane (see ``_spec_kind``). A lawful connector of the
    OTHER lane is FILTERED, never refused: it is somebody else's business, and
    reporting it as broken would put a false repair job in front of an operator
    whose config is correct — the same defect this function's refusal messages
    exist to avoid, inverted. Only an entry that is a connector of no lane at
    all is named.

    No connector is built in. A cabinet that has been told about nothing reads
    nothing, and says so — which is the correct behaviour for a fresh hatch and
    the reason this returns ``[]`` rather than inventing a default estate.

    AN ABSENT FILE IS THE ONLY HONEST EMPTY, and this function used to return
    the same ``[]`` for two things that are not that — committing, in the
    loader, the exact failure the section header above forbids one function
    down. A declaration that WOULD NOT PARSE came back indistinguishable from
    an operator who declared nothing; a single malformed ENTRY was dropped
    without a word, so a sweep over a file naming two connectors reported
    ``declared: 1``, swept the sibling, called it connected, and left
    ``not_reached`` EMPTY — a confident result that omits a source it threw
    away.

    Both now append to the caller's ``not_reached`` list with the operator's
    own path, what is wrong, and (for an entry) WHICH one, so the refusal is
    something a person can go and fix rather than a clean negative nobody
    earned. The list is optional because a caller that wants only the COUNT
    stays a one-liner; passing nothing loses the reasons, never a spec.
    """
    refused = not_reached if isinstance(not_reached, list) else []
    path = Path(root).expanduser() / CONNECTORS_REL
    if not path.is_file():
        return []
    try:
        import yaml  # local: keep the module import-light

        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        declared = (doc.get("connectors") or []) if isinstance(doc, dict) else None
    except Exception as exc:
        # THE EXCEPTION'S TYPE, NEVER ITS TEXT. A YAML parse error quotes the
        # offending SOURCE LINE back at you (verified by execution), and this
        # file is the one the operator edits next to their credentials — so the
        # obvious "make the message more helpful" edit would put a line of their
        # config into a document this lane promises is contents-free. Pinned by
        # test_a_parse_failure_never_echoes_the_line_that_broke.
        declared, problem = None, f"would not parse ({type(exc).__name__})"
    else:
        problem = "carries no `connectors:` list"
    if not isinstance(declared, list):
        refused.append(
            f"{CONNECTORS_REL} {problem}, so NO connector declared in it was read — "
            "that is a broken file, not evidence that you have no connectors")
        return []
    out = []
    for position, entry in enumerate(declared, start=1):
        name = str(entry.get("name") or "").strip() if isinstance(entry, dict) else ""
        found = _spec_kind(entry) if name else ""
        if found == kind:
            out.append(entry)
            continue
        if found:
            continue  # a lawful connector of the other lane — not this caller's
        refused.append(
            f"{CONNECTORS_REL} entry {position}" + (f" ({name})" if name else "")
            + " was skipped, so nothing in it was read: a connector needs a "
              "non-empty `name` and either an `inventory:` mapping saying what "
              "to list or a `search:` mapping saying how to send a query")
    return out


# --- DECLARING a connector from onboarding: the write half of the read lane ---
#
# The read lane above takes connectors as given. This is how one gets there
# WITHOUT a hand-edit of the config: onboarding offers a curated catalog
# (``instance/config/connector-templates.yml.example`` — DATA, so the framework
# still knows no vendor), the operator picks one and supplies a credential and
# at most a field or two, and the entry is written into the same
# ``instance/config/connectors.yml`` the sweep reads. Three properties are load-
# bearing and each is enforced below, not promised:
#
#   * THE SHAPE COMES FROM THE TEMPLATE, not the caller. Only paths the template
#     author declared under ``fields[].into`` ever take an operator value, so a
#     surface cannot smuggle an arbitrary connector shape through this door.
#   * IT IS STILL A READ. ``assert_read_only`` runs on the BUILT inventory before
#     anything is written, so a template that could write — or a custom URL that
#     is not https — is refused at declaration, exactly as the sweep would refuse
#     it, and the config never gains an entry that could not be swept anyway.
#   * THE CREDENTIAL VALUE NEVER ARRIVES HERE. Only its env var NAME is written;
#     the value is placed in ``cabinet/.env`` by the dashboard's own safe writer.


class ConnectorDeclarationError(ValueError):
    """A connector could not be declared. The message is operator-facing and
    contents-free — it names what to fix, never echoes a credential or a body."""


def load_connector_templates(root) -> dict:
    """The curated catalog, keyed by id. Absent or unreadable ⇒ ``{}``.

    This is a CONVENIENCE library, not operator config: a hatch that deleted it
    simply offers no shortcuts, and a shipped pack that will not parse must not
    take onboarding down with it. So unlike ``load_connector_specs`` — where an
    unreadable file is an operator error worth naming — every problem here is an
    empty catalog, and the open-ended ``rest`` template a good pack carries is
    what keeps "no shortcut for your tool" from meaning "no way to connect it".
    """
    path = Path(root).expanduser() / TEMPLATES_REL
    if not path.is_file():
        return {}
    try:
        import yaml  # local: keep the module import-light

        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    declared = (doc.get("templates") or []) if isinstance(doc, dict) else []
    if not isinstance(declared, list):
        return {}
    out: dict = {}
    for tpl in declared:
        if not isinstance(tpl, dict):
            continue
        tid = str(tpl.get("id") or "").strip()
        connector = tpl.get("connector")
        # A template is usable only if it carries an id and a connector that
        # declares a read call in one of the two lanes — the same floor the
        # loader holds a declared connector to. A malformed one is dropped from
        # the list, never surfaced half-built for the operator to trip over.
        if tid and isinstance(connector, dict) and _spec_kind(connector):
            out.setdefault(tid, tpl)
    return out


def _set_dotted(obj: dict, dotted: str, value) -> None:
    """Write ``value`` at a dotted path, making intermediate mappings as needed.

    The path is the template author's, never the operator's — that is what keeps
    an operator value confined to the field it was collected for.
    """
    parts = [p for p in str(dotted).split(".") if p]
    if not parts:
        return
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def build_connector_from_template(templates: dict, template_id: str, *,
                                  name: str, credential_env: str,
                                  fields=None) -> dict:
    """Resolve a template + the operator's answers into one connector entry.

    Raises :class:`ConnectorDeclarationError` — operator-facing, contents-free —
    on anything that would not be a lawful read. The returned entry carries the
    env var NAME under ``credential_env`` and never a credential value.
    """
    from copy import deepcopy

    tpl = templates.get(str(template_id or "").strip())
    if not isinstance(tpl, dict):
        raise ConnectorDeclarationError(
            "That is not a tool I know how to set up. Pick one from the list, or "
            "use “Another REST list” to describe your own.")
    entry = deepcopy(tpl.get("connector") or {})
    lane = _spec_kind(entry)
    if not lane:
        raise ConnectorDeclarationError(
            "That template is missing its read shape, so it cannot be set up.")

    declared = {}
    for field in tpl.get("fields") or []:
        if isinstance(field, dict) and str(field.get("key") or "").strip():
            declared[str(field.get("key")).strip()] = field
    supplied = fields or {}
    if not isinstance(supplied, dict):
        raise ConnectorDeclarationError("The details for this tool were not readable.")
    # An answer to a question this template never asked is refused rather than
    # written somewhere: the operator fills the fields on offer, nothing else.
    for key in supplied:
        if str(key) not in declared:
            raise ConnectorDeclarationError(f"“{key}” is not something this tool asks for.")
    for key, field in declared.items():
        raw = supplied.get(key)
        text = "" if raw is None else str(raw).strip()
        if not text:
            if field.get("required"):
                label = str(field.get("label") or key)
                raise ConnectorDeclarationError(f"{label} is needed to set this up.")
            continue  # blank optional ⇒ keep the template's own default
        if len(text) > _MAX_DECLARED_FIELD_CHARS:
            raise ConnectorDeclarationError(
                f"“{field.get('label') or key}” is too long.")
        if "\n" in text or "\r" in text:
            raise ConnectorDeclarationError(
                f"“{field.get('label') or key}” cannot contain a line break.")
        # THE OPERATOR SUPPLIES A NAME, NOT AN ADDRESS. Where a template's list
        # lives under the operator's own workspace slug, region or account, the
        # honest question is "what is your workspace called" — and asking a
        # non-technical operator to paste a whole API URL instead is how a
        # connect step turns back into a config file. `into_format` is the
        # TEMPLATE AUTHOR's sentence with one hole in it; the operator fills the
        # hole and nothing else.
        #
        # AND THE SCHEME STAYS THE AUTHOR'S. The format must begin with the
        # literal `https://`, so no operator value can choose the scheme and no
        # pack edit can quietly introduce a plaintext one. Where the format also
        # pins the host (`https://<host>/…/{value}/…`) the value lands
        # after the authority component is already closed, so nothing inside it
        # can move the request elsewhere; where the value IS the host (a
        # self-hosted install), the operator is naming their own server, which is
        # the same consent the open template already takes. Checked here rather
        # than assumed, because a pack edit is data and this is the only place
        # that can refuse a bad one.
        shape = str(field.get("into_format") or "")
        if shape:
            if "{value}" not in shape or not shape.startswith("https://"):
                raise ConnectorDeclarationError(
                    "That tool's setup is malformed, so it was not set up.")
            text = shape.replace("{value}", text)
        _set_dotted(entry, str(field.get("into") or ""), text)

    label = " ".join(str(name or "").split())[:_MAX_CONNECTOR_NAME_CHARS] or str(template_id).strip()
    entry["name"] = label
    cred = str(credential_env or "").strip()
    if not _ENV_NAME_RE.match(cred):
        raise ConnectorDeclarationError(
            "The credential name must be UPPER_SNAKE_CASE (letters, digits, "
            "underscore), so it is a valid environment variable.")
    entry["credential_env"] = cred

    # THE CEILING, on the BUILT call, before a byte is written. A template whose
    # inventory could write, or a custom URL that is not https, is refused here
    # with the same verdict the sweep would give it — so the config can never
    # gain an entry the read lane would then reject. Each lane is held to ITS
    # OWN ceiling: a search shape may not be admitted by the inventory rule (it
    # would be refused — a search POST is not a GraphQL document) and an
    # inventory shape may not borrow the search rule, which is looser on body
    # shape. ``_spec_kind`` reads the slot that was filled, so neither can be
    # chosen by the template author writing a word.
    try:
        assert_declaration_read_only(entry)
    except ReadOnlyViolation as exc:
        raise ConnectorDeclarationError(
            f"That would not be a read-only connection ({exc}), so it was not "
            "set up. The cabinet only ever lists; it never writes.") from None
    return entry


def _host_of(entry: dict) -> str:
    """The host a connector's credential will reach — for the consent line.

    Reads whichever lane the entry declared: a search tool has no inventory
    call, and printing an empty consent line beside a credential that is about
    to leave the machine is the one sentence in this flow that must be true.
    """
    call = entry.get(_spec_kind(entry)) if isinstance(entry, dict) else None
    url = str((call or {}).get("url") or "")
    if "://" not in url:
        return ""
    return url.split("://", 1)[1].split("/", 1)[0].split("?", 1)[0]


def write_connector_declaration(root, entry: dict) -> dict:
    """Add one built entry to ``instance/config/connectors.yml``, never clobbering.

    Create-if-absent, append-if-present, and REFUSE a name already declared —
    existing entries (and any comments the operator wrote beside them) are left
    byte-for-byte. The write is validated by re-parsing the whole file before it
    lands and re-reading it after, so a green return is a measured fact rather
    than a hopeful one. Returns ``{"name", "host"}`` — contents-free.
    """
    import yaml  # local: keep the module import-light

    # LAST LINE OF DEFENSE before a write, for a caller that reached here without
    # going through build_connector_from_template. Surfaced as the same operator-
    # facing, contents-free error every other declaration refusal uses.
    try:
        assert_declaration_read_only(entry)
    except ReadOnlyViolation as exc:
        raise ConnectorDeclarationError(
            f"That would not be a read-only connection ({exc}), so it was not "
            "written.") from None
    root_path = Path(root).expanduser()
    path = root_path / CONNECTORS_REL
    name = str(entry.get("name") or "").strip()
    if not name:
        raise ConnectorDeclarationError("A connector needs a name.")
    # BOTH LANES, because the name has to be unique in the FILE and not merely
    # in one caller's view of it. Loading only the inventory lane would let a
    # search tool and a list connector share a name, and the round-trip check
    # below (which counts entries) would then be comparing against a partial
    # census of what is already there.
    existing = (load_connector_specs(root_path, kind=CONNECTOR_KIND_INVENTORY)
                + load_connector_specs(root_path, kind=CONNECTOR_KIND_SEARCH))
    if any(str(s.get("name") or "").strip() == name for s in existing):
        raise ConnectorDeclarationError(
            f"A connector named “{name}” is already set up. Choose a different name.")

    block = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True,
                           default_flow_style=False)
    indented = "".join((("  " + line) if line.strip() else line) + "\n"
                       for line in block.splitlines())
    if path.is_file():
        base = path.read_text(encoding="utf-8")
        if base and not base.endswith("\n"):
            base += "\n"
        new_text = base + indented
    else:
        new_text = (
            "# This deployment's declared connectors — READ-ONLY inventory calls.\n"
            "# Shape, ceiling and rationale: instance/config/connectors.yml.example.\n"
            "# Written by onboarding when you connect a tool. Credentials are env\n"
            "# var NAMES; the values live in cabinet/.env and never enter this file.\n"
            "#\n"
            "# The egg export drops this file (live instance values never ship); a\n"
            "# fresh cabinet starts with no connectors and the .example twin to copy.\n\n"
            "schema: cabinet.connectors/v1\n\n"
            "connectors:\n"
            + indented
        )

    # PARSE THE WHOLE REBUILT FILE BEFORE IT LANDS. An append that produced a
    # document the loader would reject, or one that did not round-trip the entry
    # intact, is refused here rather than written and discovered by a later
    # sweep. Both are internal invariants (the caller already validated the
    # entry), so a failure is this function's bug, named as one.
    doc = yaml.safe_load(new_text)
    parsed = doc.get("connectors") if isinstance(doc, dict) else None
    if not isinstance(parsed, list):
        raise ConnectorDeclarationError(
            "The connector could not be written cleanly, so nothing was changed.")
    landed = [e for e in parsed if isinstance(e, dict)
              and str(e.get("name") or "").strip() == name]
    if len(parsed) != len(existing) + 1 or len(landed) != 1 or landed[0] != entry:
        raise ConnectorDeclarationError(
            "The connector could not be written cleanly, so nothing was changed.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")

    # MEASURED, NOT REPORTED. Read it back through the same loader a sweep uses.
    reloaded = load_connector_specs(root_path, kind=_spec_kind(entry))
    if not any(str(s.get("name") or "").strip() == name for s in reloaded):
        raise ConnectorDeclarationError(
            "The connector did not persist, so it will not be read. Try again.")
    return {"name": name, "host": _host_of(entry)}


def sweep_connectors(root, *, specs=None, env=None, fetch=None, now=None,
                     ceiling=None, max_calls=_DEFAULT_MAX_CALLS,
                     timeout=_DEFAULT_TIMEOUT, max_items=_DEFAULT_MAX_ITEMS) -> dict:
    """LOOK: read every declared connector, read-only, and report what is there.

    Returns the contents-free sweep document: one row per connector with its
    item count, freshest timestamp, distinct-actor count and call count; the
    ``(connector, name, updated)`` triples ``framework.onboarding.salience``
    ranks; the ESTATE identity strings that let the ranker DEMOTE a name the
    estate calls itself rather than delete it; and every refusal with its reason.

    THOSE IDENTITY STRINGS ARE NOT THE OPERATOR, and the difference is not
    pedantic. A connector's ``identity`` block asks the credential who it is, and
    a token issued to an integration answers with the INTEGRATION — a service
    account nobody sits at. That is a perfectly good answer to "what does this
    estate call itself", which is all demotion needs. It is the wrong answer to
    "who did this", and a reader that used it there would attribute an entire
    company's activity to a robot while reporting nothing about the person
    onboarding. Who the operator is comes from the onboarding record instead
    (:func:`operator_identity`), every claim about who did what carries
    :func:`attribution_basis`, and where the record resolves nothing the basis is
    ``unresolved`` and NO claim is made.

    THE CEILING IS CONSULTED FIRST. ``_probe_web`` reads the Captain-owned
    egress switch, and a closed ceiling refuses every connector before a socket
    is opened — a sweep that plans requests it cannot make is an interview whose
    answers go nowhere.
    """
    root_path = Path(root).expanduser()
    connectors, rows, identities, not_reached = [], [], [], []
    # THE LOADER'S OWN REFUSALS LAND HERE, in the same list as every other
    # named failure. A declaration the operator broke and a deployment that
    # declared nothing both produce zero specs, and without this they produced
    # the same document too — which is the one confusion this whole lane exists
    # to prevent.
    specs = (load_connector_specs(root_path, not_reached=not_reached)
             if specs is None else list(specs))
    env = os.environ if env is None else env
    fetch = _http_fetch if fetch is None else fetch
    ceiling = _probe_web(root_path) if ceiling is None else ceiling
    swept_at = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    budget = {"left": max(0, int(max_calls))}
    permitted = bool(ceiling.get("connected"))
    for spec in specs:
        name = str(spec.get("name") or "").strip()
        if not permitted:
            reason = str(ceiling.get("reason") or "egress_closed")
            connectors.append({"name": name, "connected": False, "items": 0,
                               "calls": 0, "reason": f"egress_{reason}"})
            continue
        credential = str((env.get(str(spec.get("credential_env") or "")) or "")).strip()
        if not credential:
            # The NAME is reported; the value never exists in a result, a log or
            # an exception message anywhere in this lane.
            connectors.append({"name": name, "connected": False, "items": 0,
                               "calls": 0, "reason": "credential_absent"})
            continue
        result = _sweep_one(spec, credential, fetch=fetch, timeout=timeout,
                            max_items=max_items, budget=budget)
        rows.extend({"connector": r["connector"], "name": r["name"],
                     "updated": r["updated"],
                     # The ACTORS survive onto the row. They were extracted per
                     # item and then collapsed to a distinct COUNT, which answers
                     # "how many people" and structurally cannot answer "which of
                     # them is you" — so no downstream reader could tell the
                     # operator's own activity from anyone else's, and a period
                     # could be presented as theirs without anything having
                     # checked. Plural, because one item does not have one actor.
                     **({"actors": r["actors"]} if r.get("actors") else {})}
                    for r in result["rows"])
        identities.extend(result["identities"])
        not_reached.extend(result["not_reached"])
        connectors.append({k: v for k, v in result.items()
                           if k not in ("rows", "identities", "not_reached")})
    if budget["left"] <= 0 and permitted and specs:
        not_reached.append("the sweep's call budget was fully spent")
    return {
        "schema": CONNECTOR_SWEEP_SCHEMA,
        "swept_at": swept_at,
        "declared": len(specs),
        "calls": max(0, int(max_calls)) - budget["left"],
        "connectors": connectors,
        "rows": rows,
        "identities": sorted(set(identities)),
        "not_reached": not_reached,
    }


# ---------------------------------------------------------------------------
# THE SEARCH PLANE — the seed's own words, sent OUT, once, on the record.
# ---------------------------------------------------------------------------
# WHAT THIS IS. The onboarding core turns "what do you do?" into typed probes
# and then holds no socket to run them with, so the outward half of every seed
# answer arrived on the operator's card as *did not run*. That was honest and
# useless: a cabinet told it serves a named organisation could not go and find
# out what that organisation IS, which is the first thing a colleague would do.
# This is the executor for those probes, living beside the read lane because
# the two answer the same law — the operator declares what may be reached, the
# framework knows only the SHAPE, and every failure is named rather than
# collapsed into a clean negative.
#
# CONSENT IS THE CONNECT STEP, and it is not implied by the egress ceiling. A
# search sends the operator's OWN SENTENCE to a third party, which is a
# different act from listing their own estate through their own credential.
# What makes it lawful is that the operator went and connected a search tool
# for exactly this purpose; the catalog's setup steps say so in the operator's
# words, the query is printed back on the card, and no probe runs when no
# search tool is declared.
#
# THE CEILING, all of it enforced below rather than promised:
#   * READ ONLY, under ``assert_search_read_only`` — a SEPARATE gate from the
#     inventory lane's, narrower everywhere except body shape. See its
#     docstring for what it proves and, more importantly, what it does not.
#   * NO REDIRECTS — ``_http_fetch``'s opener refuses them, so the credential
#     reaches the declared origin or nowhere.
#   * THE EGRESS CEILING FIRST — ``_probe_web`` is consulted before a socket
#     exists, exactly as the sweep does it.
#   * BOUNDED — at most ``_MAX_SEARCH_PROBES`` probes, one call each, a short
#     timeout, ``_MAX_SEARCH_RESULTS`` results per probe, every field capped,
#     and a total byte budget across the whole run.
#   * THE QUERY IS PERCENT-ENCODED into a URL and JSON-ENCODED into a body, so
#     an operator sentence cannot add a parameter, a path segment or a field.
#
# AND WHAT COMES BACK IS UNTRUSTED TEXT. It is written by whoever ranked well
# for the operator's own words — an adversary can arrange to be one of those
# results. Two things make that safe here and they are both structural: the
# pipeline that consumes it is deterministic (no model reads it, nothing
# branches on it, nothing executes it), and every field is scrubbed and capped
# by ``_untrusted_text`` / ``_untrusted_url`` at the ONE place results enter.
# What a result can do is be displayed and be string-matched. What it cannot do
# is instruct anything, because nothing downstream takes instructions.
SEARCH_PROBE_SCHEMA = "cabinet.search-probe-result/v1"
#: The probe kind the core emits for an outward look. Named here, next to its
#: executor, so the core and the plane cannot drift on the spelling.
SEARCH_PROBE_KIND = "web_search"
#: The hole a template author leaves for the operator's words. Exactly one, and
#: the ceiling counts them.
SEARCH_QUERY_HOLE = "{query}"

#: How many outward probes one look-up may send. PUBLIC, because the core's
#: planner reads it: a plan that proposes more queries than this executor
#: will run reports the surplus as "did not run", which is an honest
#: sentence about a shortfall nobody needed to have.
MAX_SEARCH_PROBES = 3
_MAX_SEARCH_PROBES = MAX_SEARCH_PROBES
_MAX_SEARCH_RESULTS = 5
_MAX_SEARCH_TITLE = 160
_MAX_SEARCH_URL = 300
_MAX_SEARCH_SNIPPET = 300
#: Total displayed characters across a whole run. A per-field cap bounds one
#: result; this bounds the RUN, so a provider that answers every probe with the
#: maximum cannot grow the journey's state without limit.
_MAX_SEARCH_CHARS = 8 * 1024
_MAX_SEARCH_QUERY_CHARS = 200
#: Shorter than the sweep's, deliberately: this runs inside the onboarding
#: action lock while the operator waits on a card, and a search that has not
#: answered in twelve seconds is not going to make the card better.
_SEARCH_TIMEOUT = 12.0
_MAX_SEARCH_BODY_KEYS = 12
_MAX_SEARCH_BODY_BYTES = 2048
#: One nested mapping is allowed (a provider's "and give me an excerpt" block);
#: two is a document, and a document is what the GraphQL rule exists to bound.
_MAX_SEARCH_BODY_DEPTH = 2
_MAX_SEARCH_LIST_ITEMS = 10
#: Broader than the inventory lane's GraphQL token set, because a REST body
#: announces no verb of its own: if a declared search call NAMES a mutation
#: anywhere in its address or its skeleton, it is refused. Whole words, so a
#: host or a path segment that merely contains one of them is not caught by
#: accident.
_SEARCH_WRITE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(mutation|subscription|insert|update|delete|destroy|"
    r"remove|create|drop|write|upsert|patch|truncate|execute|revoke|grant)"
    r"(?![A-Za-z0-9_])", re.IGNORECASE)
#: Control characters, the two line separators a JSON string may legally
#: carry that break a rendered line anyway, and the two angle brackets.
#: Written as escapes, never as the characters themselves: a literal U+2028
#: in this file would end the source line for every tool that reads it, this
#: module's own editors included.
#:
#: THE ANGLE BRACKETS ARE NOT PARANOIA — measured 2026-08-14. A live provider
#: returns its snippets with the matched words wrapped in markup by default,
#: so the very first real answer this plane received carried tags. On today's
#: two surfaces that is inert (one escapes its text nodes, the other sends
#: plain messages), which is exactly the sort of safety that quietly stops
#: being true when a third surface is added by someone who never read this
#: file. A result is a CAPTION, so the cost of dropping brackets is a rare
#: "a < b" reading "a   b" — and what it buys is that no future renderer can
#: be handed markup by a stranger who ranked well for the operator's own words.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029<>]")


def assert_search_read_only(call) -> None:
    """Mechanically refuse anything in the SEARCH slot that is not a query.

    A SEPARATE CEILING from :func:`assert_read_only`, deliberately not a
    widening of it. The inventory lane admits a POST only when the body is a
    GraphQL READ document, and that rule is sound for exactly one reason: a
    GraphQL document declares its own verb, so ``mutation`` can be refused by
    name. A REST search body declares nothing. Loosening the inventory rule to
    let search endpoints through would have admitted every REST write with
    them, so the search slot got its own gate and the inventory gate did not
    move a byte.

    WHAT THIS PROVES: the address is HTTPS and has a host; nothing this module
    can put on the wire asks the far end to treat the request as another verb
    (the injected credential header is checked too, which is where the
    inventory ceiling was once found open); no write verb is NAMED in the
    address or in the skeleton the template author wrote; the body is a bounded
    parameter bag rather than a document; and the operator's words go in at
    exactly ONE declared hole, counted here, so a call cannot quietly send the
    seed twice or send it somewhere the card does not show.

    WHAT IT DOES NOT PROVE, said plainly because a ceiling that implies a proof
    it does not have is worse than no ceiling: a flat JSON body cannot be told
    apart from a create payload by inspection. ``{"title": "…"}`` is a search
    parameter bag and an issue-creation payload in the same bytes. What stands
    between that and a write is WHERE this gate sits — a call reaches it only
    through a connector's ``search:`` slot, which nothing but the probe
    executor below ever reads, and the shipped catalog's shapes are verified
    against each provider's published reference. An operator who hand-writes a
    mutating endpoint into that slot has told their own cabinet to POST a
    search query at it. The framework refuses everything it can see; this
    paragraph is the honest edge of what it can see.
    """
    if not isinstance(call, dict):
        raise ReadOnlyViolation("call_not_a_mapping")
    url = str(call.get("url") or "").strip()
    if not url.lower().startswith("https://"):
        raise ReadOnlyViolation("url_not_https")
    if len(url.split("://", 1)[1].split("/", 1)[0].strip()) == 0:
        raise ReadOnlyViolation("url_has_no_host")
    method = str(call.get("method") or "GET").strip().upper()
    if method not in _READ_METHODS:
        raise ReadOnlyViolation(f"method_not_read_only:{method}")
    headers = call.get("headers") or {}
    if not isinstance(headers, dict):
        raise ReadOnlyViolation("headers_not_a_mapping")
    for key in (*headers, str(call.get("auth_header") or "Authorization")):
        if str(key).strip().lower() in _METHOD_OVERRIDE_HEADERS:
            raise ReadOnlyViolation(f"method_override_header:{key}")
    if _SEARCH_WRITE_TOKEN_RE.search(url):
        raise ReadOnlyViolation("write_token_in_url")
    body = call.get("json")
    if method == "GET":
        if body is not None:
            raise ReadOnlyViolation("get_with_body")
        serialized = ""
    else:
        if not isinstance(body, dict):
            raise ReadOnlyViolation("post_body_not_a_query_envelope")
        if not body or len(body) > _MAX_SEARCH_BODY_KEYS:
            raise ReadOnlyViolation("post_body_not_a_query_envelope")
        if not _query_envelope_ok(body, 1):
            raise ReadOnlyViolation("post_body_not_a_query_envelope")
        serialized = json.dumps(body, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > _MAX_SEARCH_BODY_BYTES:
            raise ReadOnlyViolation("post_body_too_large")
        if _SEARCH_WRITE_TOKEN_RE.search(serialized):
            raise ReadOnlyViolation("write_token_in_body")
    # EXACTLY ONE HOLE, across the whole declaration. Zero means the operator's
    # words never leave and the probe would search the template's placeholder;
    # more than one means the card shows a query that went to two places.
    holes = url.count(SEARCH_QUERY_HOLE) + serialized.count(SEARCH_QUERY_HOLE)
    if holes != 1:
        raise ReadOnlyViolation(f"query_placeholder_count:{holes}")


def _query_envelope_ok(value, depth: int) -> bool:
    """A bounded parameter bag: scalars, short scalar lists, one nesting."""
    if isinstance(value, dict):
        if depth > _MAX_SEARCH_BODY_DEPTH or len(value) > _MAX_SEARCH_BODY_KEYS:
            return False
        return all(isinstance(k, str) and k.strip()
                   and _query_envelope_ok(v, depth + 1)
                   for k, v in value.items())
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_SEARCH_LIST_ITEMS:
            return False
        return all(_query_envelope_ok(v, _MAX_SEARCH_BODY_DEPTH + 1)
                   for v in value)
    return value is None or isinstance(value, (str, int, float, bool))


def assert_declaration_read_only(entry) -> None:
    """Hold ONE declared connector to the ceiling of the lane it is in.

    The lane comes from ``_spec_kind`` — the slot the author actually filled —
    so a declaration cannot pick the looser gate by claiming a label. An entry
    that is a connector of no lane at all is refused rather than passed through
    unchecked, which is the difference between a gate and a lookup.
    """
    lane = _spec_kind(entry)
    if lane == CONNECTOR_KIND_SEARCH:
        assert_search_read_only(entry.get(CONNECTOR_KIND_SEARCH))
        return
    if lane == CONNECTOR_KIND_INVENTORY:
        assert_read_only(entry.get(CONNECTOR_KIND_INVENTORY))
        return
    raise ReadOnlyViolation("connector_declares_no_read_call")


def _untrusted_text(value, limit: int) -> str:
    """One field of a third party's answer, made safe to DISPLAY and no more.

    THE ONE PLACE A SEARCH RESULT ENTERS THIS SYSTEM, and everything downstream
    of it treats the output as a caption. Containers return empty rather than
    being flattened (the same rule ``_scalar`` holds for the read lane: a
    stringified object is a body arriving through a name field). Control
    characters — including the newline that would let one result forge a second
    line on a card, and the line separators JSON permits inside a string —
    become spaces. A lone surrogate is replaced rather than carried: it is legal
    in a decoded JSON string, illegal in UTF-8, and would crash the CLI that
    prints this state as JSON — the result taking the whole action down with it.
    """
    if value is None or isinstance(value, (dict, list, tuple, set, bool)):
        return ""
    import html as _html  # local: keep the module import-light

    # ENTITIES ARE DECODED BEFORE THE SCRUB, NEVER AFTER, AND EXACTLY ONCE.
    # Providers return their snippets HTML-escaped, so an operator was shown
    # "I&#x27;ve" and "&quot;" where their own eyes expected an apostrophe and a
    # quote — found by LOOKING at a real answer, 2026-08-14, not by reasoning
    # about one. The ORDER is the safety: a tag arriving as `&lt;script&gt;`
    # decodes to angle brackets and is then dropped by the scrub below, whereas
    # decoding afterwards would hand it through intact. One pass only, so a
    # doubly-encoded tag decodes to inert text rather than to markup.
    text = _CONTROL_RE.sub(" ", _html.unescape(str(value)))
    text = text.encode("utf-8", "replace").decode("utf-8", "replace")
    return " ".join(text.split())[:max(0, int(limit))]


def _untrusted_url(value) -> str:
    """A result's address, or nothing. An ALLOW-LIST of two schemes.

    This is what stops a result from handing a surface something that is not a
    web address at all: a rendered link is the one place a caption becomes a
    click, and a scheme that executes in the page ("javascript:") or carries
    its own payload ("data:") reaches the operator as an ordinary-looking
    citation. Anything that is not http/https, or that still contains a space
    after collapsing, is dropped — a result with no address is displayed
    without one rather than with a dangerous one.
    """
    text = _untrusted_text(value, _MAX_SEARCH_URL)
    low = text.lower()
    if not (low.startswith("https://") or low.startswith("http://")):
        return ""
    return "" if " " in text else text


def _search_request(call, credential: str, query: str) -> dict:
    """A declared search call + a credential + the operator's words -> the wire.

    THE QUERY IS ENCODED FOR THE SLOT IT LANDS IN, and that is the whole reason
    substitution lives in one function. Into a URL it is percent-encoded with an
    empty safe set, so no character in an operator's sentence can add a
    parameter, close the query string or walk the path. Into a body it is placed
    as a JSON VALUE and serialized, so quoting is the encoder's problem and not
    a string-concatenation hazard. Never logged.
    """
    import urllib.parse  # local: keep the module import-light

    headers = {str(k): str(v) for k, v in (call.get("headers") or {}).items()}
    auth_header = str(call.get("auth_header") or "Authorization")
    auth_format = str(call.get("auth_format") or "{credential}")
    headers[auth_header] = auth_format.replace("{credential}", credential)
    url = str(call["url"]).replace(
        SEARCH_QUERY_HOLE, urllib.parse.quote(query, safe=""))
    body = None
    method = str(call.get("method") or "GET").strip().upper()
    if method == "POST":
        headers.setdefault("Content-Type", "application/json")
        body = json.dumps(_query_filled(call.get("json") or {}, query),
                          ensure_ascii=False).encode("utf-8")
    return {"url": url, "method": method, "headers": headers, "body": body}


def _query_filled(value, query: str):
    """Substitute the query hole inside a declared body. Str-replace, never
    ``format`` — a provider's parameter names are not a format string."""
    if isinstance(value, str):
        return value.replace(SEARCH_QUERY_HOLE, query)
    if isinstance(value, dict):
        return {k: _query_filled(v, query) for k, v in value.items()}
    if isinstance(value, list):
        return [_query_filled(v, query) for v in value]
    return value


def _search_results(doc, call, *, max_results: int, budget: dict) -> tuple:
    """``(results, truncated)`` from one answered search call.

    Contents-free is the WRONG law here and the read lane's rule is deliberately
    not copied: a search result IS its title, address and one line — that is the
    citation, and stripping it would leave the operator a count. What replaces
    the contents-free rule is the untrusted-text rule above plus these caps, so
    what lands is bounded and inert rather than absent.
    """
    found = _dig(doc, call.get("results_path"))
    if isinstance(found, dict):
        found = [found]
    if not isinstance(found, list):
        return [], False
    out = []
    truncated = len(found) > max_results
    for item in found[:max_results]:
        title = _untrusted_text(_dig(item, call.get("title_field")),
                                _MAX_SEARCH_TITLE)
        link = _untrusted_url(_dig(item, call.get("url_field")))
        # OPTIONAL BY DESIGN. Several providers return a title and an address
        # and nothing else unless a second, heavier call is made; a result with
        # no line under it is still a citation, and refusing it would lose the
        # finding to keep the decoration.
        snippet = _untrusted_text(_dig(item, call.get("snippet_field")),
                                  _MAX_SEARCH_SNIPPET) \
            if call.get("snippet_field") else ""
        if not title and not link:
            continue
        cost = len(title) + len(link) + len(snippet)
        if budget["left"] - cost < 0:
            truncated = True
            break
        budget["left"] -= cost
        row = {"title": title, "url": link}
        if snippet:
            row["snippet"] = snippet
        out.append(row)
    return out, truncated


def _search_shape_problem(call) -> str:
    """What a declared search call is MISSING, by name, or ``""``.

    Separate from the ceiling on purpose: a call with no ``title_field`` is not
    dangerous, it is unfinished, and telling an operator "refused" about a
    typo sends them looking for a security problem they do not have.
    """
    if not isinstance(call, dict):
        return "no search call"
    if not str(call.get("title_field") or "").strip():
        return "title_field"
    if not str(call.get("url_field") or "").strip():
        return "url_field"
    return ""


def run_search_probes(root, probes, *, specs=None, env=None, fetch=None,
                      ceiling=None, timeout=_SEARCH_TIMEOUT,
                      max_probes=_MAX_SEARCH_PROBES,
                      max_results=_MAX_SEARCH_RESULTS) -> dict:
    """RUN the seed's outward probes through the operator's own search tool.

    Returns ``{"schema", "executed", "deferred", "provider"}``. Every probe
    lands in exactly one of the two lists and a deferred one always carries the
    reason it did not run — ``no_search_tool_connected`` and ``http_401`` and
    ``egress_closed_no_allowed_hosts`` are different facts with different fixes,
    and collapsing them is how "I found nothing" gets confused with "I never
    looked" at the one moment the operator is deciding whether this thing works.

    THE FIRST DECLARED SEARCH TOOL RUNS THE WHOLE SET. Deterministic (config
    order), recorded on every executed row as ``provider``, and one tool per run
    so a cabinet with three of them declared does not send the operator's
    sentence to all three.
    """
    root_path = Path(root).expanduser()
    if specs is None:
        specs = load_connector_specs(root_path, kind=CONNECTOR_KIND_SEARCH)
    else:
        specs = list(specs)
    env = os.environ if env is None else env
    fetch = _http_fetch if fetch is None else fetch

    wanted = [p for p in (probes or ())
              if isinstance(p, dict)
              and str(p.get("kind") or "") == SEARCH_PROBE_KIND
              and str(p.get("query") or "").strip()]
    result = {"schema": SEARCH_PROBE_SCHEMA, "executed": [], "deferred": [],
              "provider": None}

    def _defer(rows, reason):
        for row in rows:
            result["deferred"].append({
                "kind": SEARCH_PROBE_KIND,
                "query": str(row.get("query") or "")[:_MAX_SEARCH_QUERY_CHARS],
                "executed": False, "reason": reason})

    if not wanted:
        return result
    if not specs:
        _defer(wanted, "no_search_tool_connected")
        return result
    spec = specs[0]
    name = str(spec.get("name") or "").strip() or "search"
    call = spec.get(CONNECTOR_KIND_SEARCH)
    result["provider"] = name

    ceiling = _probe_web(root_path) if ceiling is None else ceiling
    if not ceiling.get("connected"):
        _defer(wanted, f"egress_{str(ceiling.get('reason') or 'closed')}")
        return result
    try:
        assert_search_read_only(call)
    except ReadOnlyViolation as exc:
        _defer(wanted, f"search_call_refused:{exc}")
        return result
    problem = _search_shape_problem(call)
    if problem:
        _defer(wanted, f"search_declares_no:{problem}")
        return result
    credential = str((env.get(str(spec.get("credential_env") or "")) or "")).strip()
    if not credential:
        # The env var NAME is reported; the value never exists in a result, a
        # log or an exception message anywhere in this plane.
        _defer(wanted, "search_credential_absent")
        return result

    budget = {"left": _MAX_SEARCH_CHARS}
    for index, probe in enumerate(wanted):
        query = " ".join(str(probe.get("query")).split())[:_MAX_SEARCH_QUERY_CHARS]
        if index >= max(0, int(max_probes)):
            _defer([probe], "probe_budget_spent")
            continue
        request = _search_request(call, credential, query)
        try:
            status, payload = fetch(request, timeout)
        except Exception as exc:
            _defer([probe], f"unreachable:{type(exc).__name__}")
            continue
        if status != 200:
            _defer([probe], f"http_{status}")
            continue
        if len(payload) > _MAX_RESPONSE_BYTES:
            _defer([probe], "response_too_large")
            continue
        try:
            doc = json.loads(payload.decode("utf-8", errors="replace"))
        except Exception:
            _defer([probe], "response_not_json")
            continue
        results, truncated = _search_results(doc, call, max_results=max_results,
                                             budget=budget)
        if not results:
            # A SEARCH THAT ANSWERED WITH NOTHING is not the same as one that
            # never ran, and it is not the same as a mistyped results_path
            # either — but from here those last two are the same bytes, so the
            # reason names the declared path rather than asserting an empty web.
            _defer([probe], "search_returned_nothing_at:"
                            f"{call.get('results_path') or '(root)'}")
            continue
        result["executed"].append({
            "kind": SEARCH_PROBE_KIND, "query": query, "executed": True,
            "provider": name, "results": results, "truncated": truncated})
    return result


# --- WHO, AND WHEN: the two claims a sweep makes without noticing -----------
#
# A sweep answers "what is there". Two further claims ride along silently unless
# something states them, and both are wrong often enough to matter:
#
#   "this activity is yours"       — it is not, unless somebody checked WHICH
#                                    actor is the operator, and the credential
#                                    cannot answer that (see sweep_connectors).
#   "this period is representative" — it is not, if the operator was away for
#                                    part of it, and nothing in an API says so.
#
# The rule below is the same in both cases: state the basis, and where the basis
# is missing ASK rather than assume. An operator invalidates a whole inference in
# four words ("that was my holiday"), and the loop's job is to make those four
# words easy to say without them having to notice unprompted that they are owed.

_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

#: A quiet stretch this long in the operator's OWN activity is worth asking
#: about. Not a threshold on the estate — a threshold on what a person would
#: recognise as "I was not there", which is why it is a fortnight and not a
#: percentile of anything.
QUIET_DAYS = 14


def operator_identity(record) -> dict:
    """Who the operator is, per connector, FROM THE ONBOARDING RECORD.

    Takes a plain mapping so this module never has to know which file the record
    is; the caller resolves that. It reads
    ``operator: {name: str, names: [str], handles: {<connector>: [str]}}``.

    A connector with no recorded handle resolves to nothing, and that is a
    legitimate outcome rather than a gap to be filled from somewhere else. An
    honest "I cannot tell which of these people is you" beats an attribution to
    whoever the token happened to be.

    ONE IDENTIFIER IS A STRING, NOT AN ITERABLE OF CHARACTERS. The record is a
    file a stranger writes by hand, and ``handles: {code: abcd}`` is the
    spelling a person reaches for first. Iterated, it becomes four accounts —
    ``a``, ``b``, ``c``, ``d`` — none of which the estate has, and the cabinet
    then says "I recognise you as a, b, c, d" and attributes nothing. Read as
    the one identifier it plainly is.
    """
    operator = record.get("operator") if isinstance(record, dict) else None
    operator = operator if isinstance(operator, dict) else {}
    handles = operator.get("handles") if isinstance(operator.get("handles"), dict) else {}
    names = [str(n).strip() for n in (operator.get("names") or ()) if str(n).strip()]
    if isinstance(operator.get("name"), str) and operator["name"].strip():
        names.append(operator["name"].strip())
    return {
        "names": sorted(set(names)),
        "handles": {str(k): sorted({str(v).strip() for v in _one_or_many(vs) if str(v).strip()})
                    for k, vs in handles.items()},
        "basis": "onboarding_record",
    }


def _one_or_many(value) -> list:
    """One identifier or a list of them — never a string walked per character."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


#: Identifiers accepted per connector when the operator answers, and the
#: guardrail on how many candidates one connector may put in the question.
#:
#: THE CANDIDATE BOUND IS A GUARDRAIL, NOT A SHORTLIST — it was 12, and 12 is a
#: head. Measured on a real estate: one connector carrying 531 of 665 rows
#: reported 30 accounts, and the operator's own carried exactly ONE row, ranking
#: about 25th. Their identifier was therefore not among the 12 offered, the
#: picker was the only writer of an identity, and no sequence of operator
#: actions could resolve the connector holding most of the estate. Rank must not
#: decide whether a person can say who they are. The bound stays only because
#: rows are themselves capped (``_DEFAULT_MAX_ITEMS`` items x
#: ``_MAX_ACTORS_PER_ITEM`` actors is thousands of strings), and where it binds
#: the question says so rather than presenting a head as the whole estate.
MAX_OPERATOR_HANDLES = 8
MAX_IDENTITY_CANDIDATES = 200

#: The longest identifier that can be RECORDED, which is deliberately the same
#: bound the sweep puts on an actor string it reads (``_MAX_FIELD_CHARS``). Tied
#: rather than chosen twice: a smaller bound here would refuse a candidate this
#: module itself offered, and a larger one would accept a string no connector
#: could ever have reported.
MAX_IDENTITY_CHARS = _MAX_FIELD_CHARS


def _fold(value) -> str:
    """One identifier, normalised for COMPARISON only — never for display.

    Whitespace-collapsed and casefolded, and that is the whole normalisation.
    What this deliberately is NOT is a similarity: no substring, no prefix, no
    edit distance, no "starts with the same word". A display-name near-match was
    measured working on one live estate and is fragile by construction — the
    failure it produces is an attribution to the WRONG PERSON, which reads
    exactly like a right one and is therefore never noticed by the reader who
    would care. An identifier the operator did not give is not theirs, however
    much it looks like it.
    """
    return " ".join(str(value or "").split()).casefold()


def _recorded_handles(operator, connector: str) -> list:
    """The identifiers the operator RECORDED for one connector, in order.

    Scalar-safe for the same reason :func:`operator_identity` is: this is
    reachable with a raw record, and one string walked per character resolves
    the operator to letters.
    """
    handles = (operator or {}).get("handles") or {}
    if not isinstance(handles, dict):
        return []
    return [str(h) for h in _one_or_many(handles.get(connector)) if str(h).strip()]


def _row_actors(row) -> list:
    return [str(a) for a in (row.get("actors") or ()) if str(a).strip()]


def attribution_share(rows, operator, connector: str) -> dict:
    """How much of ONE connector's reading is the operator's, counted.

    THE NUMBERS ARE THE HONEST FORM OF THE CLAIM. "Your top project" was
    measured wrong on a live estate — the operator believed the busiest work was
    his and the rows carried a colleague — and no amount of further reading
    corrects it, because the sentence never said what it rested on. "3 of 56
    there are yours, 52 carry someone else" is the same reading and cannot
    mislead in that direction: the reader sees the share and can contradict it.

    ``no_actor`` is its own number rather than folded into ``others``, because
    "somebody else did this" and "this connector reports nobody at all" are
    opposite facts about the estate that would otherwise print identically.
    """
    wanted = {_fold(h) for h in _recorded_handles(operator, connector)}
    total = mine = blank = 0
    for row in rows or ():
        if str(row.get("connector") or "") != connector:
            continue
        total += 1
        actors = _row_actors(row)
        if not actors:
            blank += 1
        elif wanted & {_fold(a) for a in actors}:
            mine += 1
    return {"rows": total, "mine": mine, "others": total - mine - blank,
            "no_actor": blank}


def _share_phrase(share) -> str:
    """The share as a sentence fragment, or "" when there is nothing to say."""
    rows, mine, others = share["rows"], share["mine"], share["others"]
    if not rows:
        return ""
    if share["no_actor"] == rows:
        return (f"though that connector reported no actor on any of its {rows} "
                "rows, so nothing there can be attributed to anyone yet")
    if mine:
        # EVERY ROW IS ACCOUNTED FOR, or the reader silently subtracts. Measured
        # on a live estate: 58 rows, 28 the operator's, 13 a colleague's — and
        # 17 that name nobody at all, which a two-number sentence turns into a
        # gap the reader fills with whichever of the two they were thinking of.
        tail = f", and {others} carry another actor" if others else ""
        blank = f", and {share['no_actor']} report no actor at all" if share["no_actor"] else ""
        return f"that is {mine} of the {rows} rows I read there{tail}{blank}"
    return (f"though none of the {rows} rows I read there carry it, so I am "
            "still not claiming any of that activity is yours")


def attribution_basis(operator, connector: str, rows=None) -> dict:
    """What any claim about who-did-what in this connector rests on.

    Returned WITH the claim, always. "Who did what" read off a shared integration
    credential is the most confidently wrong fact a sweep can produce, and it
    looks exactly like a correct one — so the basis travels with the claim rather
    than being available on request.

    PER CONNECTOR, AND ONLY THIS ONE. An estate where the record names the
    operator in one system and not in another resolves the first and withholds
    the second; nothing here fails a whole sweep because one connector could not
    be resolved, and nothing here borrows a neighbouring connector's answer.

    ``rows`` is optional and, when given, the claim carries its numbers — a
    resolved identity that matches NOTHING the connector reported is a real and
    common outcome (a handle typed for a system whose rows name no actor at all),
    and it must not read as attribution.
    """
    names = _recorded_handles(operator, connector)
    share = attribution_share(rows, operator, connector) if rows is not None else None
    phrase = _share_phrase(share) if share else ""
    if names:
        statement = (f"in {connector} I recognise you as {', '.join(names)}, "
                     "because that is what the onboarding record says")
        return {"connector": connector, "basis": "onboarding_record", "identifies": names,
                "statement": statement + (f" — {phrase}" if phrase else ""),
                **({"share": share} if share else {})}
    return {"connector": connector, "basis": "unresolved", "identifies": [],
            "statement": f"in {connector} I cannot tell which actor is you, so I am not "
                         "claiming any of that activity is yours",
            **({"share": share} if share else {})}


def identity_candidates(rows, connector: str) -> list:
    """This connector's account identifiers, busiest first, capped at
    ``MAX_IDENTITY_CANDIDATES``.

    NOT NECESSARILY EVERY ACCOUNT, and nothing in the returned value says which
    case this is. This line used to read "EVERY account identifier this
    connector reported" and to say that frequency "no longer decides
    membership"; both are false above the cap, where the list is a head again
    and frequency decides membership at 200 instead of at 12. Nothing
    misbehaves today only because the one production caller compensates:
    :func:`identity_question` counts the estate itself (``_distinct_actors``)
    and publishes ``accounts``, ``withheld`` and ``complete`` beside the list,
    and the surface opens a typed field where the cap binds. A NEW caller taking
    this list as exhaustive would present a head as the whole estate — the
    defect the cap was raised from 12 to fix, at a bigger number. Take the offer
    from :func:`identity_question`, or count the estate yourself.

    THE CANDIDATES ARE THE ESTATE'S OWN STRINGS, which is what makes the ask
    answerable with a tap instead of a spelling. An operator who types a name
    types the one they use for themselves; a connector stores the one its API
    returns, and where those differ a typed answer matches nothing and reads as
    "none of this is yours".

    FREQUENCY ORDERS THE LIST, AND BELOW THE CAP IT NO LONGER DECIDES
    MEMBERSHIP. This returned the 12 busiest, and on a real estate the
    operator's own account was 25th of 30 on the connector carrying 531 of 665
    rows — so the one person the question is FOR was the one it could not offer.
    The busiest actor on a shared tracker is whoever files the most tickets,
    which is a fact about process volume and not about who is reading this card.
    """
    counts: dict = {}
    for row in rows or ():
        if str(row.get("connector") or "") != connector:
            continue
        for actor in _row_actors(row):
            text = " ".join(actor.split())
            counts[text] = counts.get(text, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"identifier": name, "rows": count}
            for name, count in ranked[:MAX_IDENTITY_CANDIDATES]]


def _distinct_actors(rows, connector: str) -> int:
    """How many actors the connector reported — the TRUE count, uncapped.

    Separate from :func:`identity_candidates` on purpose. That list carries a
    guardrail, and a note counting the OFFERED list would report the guardrail
    as a fact about the operator's colleagues — a number describing this module.
    It is also what makes ``withheld`` measurable, so a surface can tell whether
    the offer it is rendering is the whole estate or part of it.
    """
    return len({" ".join(a.split()) for row in (rows or ())
                if str(row.get("connector") or "") == connector
                for a in _row_actors(row)})


def identity_question(rows, operator) -> dict | None:
    """The connectors that still cannot recognise the operator, as a QUESTION.

    ``operator_identity`` has had a reader since it landed and never had a
    WRITER: no question anywhere asked who the operator is in each system, so on
    every real estate the record resolved nothing, all attribution was withheld,
    and the withholding was correct and permanent. This is the ask that ends
    that — the same structural defect the entry grants once had, where a branch
    that only a writer could reach was unreachable in production by any sequence
    of operator actions.

    ``None`` when every connector is already resolved, so a surface that renders
    this never prints a settled question. A connector whose rows carry NO actor
    is still listed, with ``reports_no_actor`` set: recording a handle for it is
    honest and attributes nothing, and saying so is the difference between "you
    have not told me" and "I cannot use what you tell me here".

    ``complete`` IS THE FIELD A SURFACE HAS TO OBEY. Where every account the
    connector reported is offered, "none of these is you" is a true terminal
    state and a free-text field there can only introduce a spelling the estate
    does not use. Where the guardrail binds and ``withheld`` accounts are not on
    the list, a picker CANNOT be the only door — an estate with more than
    ``MAX_IDENTITY_CANDIDATES`` distinct accounts on one connector is a large
    company, not a pathology, and this cabinet has no right to tell the person
    reading the card that they are not in their own estate.
    """
    connectors = sorted({str(r.get("connector") or "")
                         for r in (rows or ()) if r.get("connector")})
    asking = []
    for connector in connectors:
        if _recorded_handles(operator, connector):
            continue
        candidates = identity_candidates(rows, connector)
        total = sum(1 for r in rows if str(r.get("connector") or "") == connector)
        distinct = _distinct_actors(rows, connector)
        withheld = distinct - len(candidates)
        entry = {"connector": connector, "rows": total, "candidates": candidates,
                 "reports_no_actor": not candidates,
                 "accounts": distinct, "withheld": withheld,
                 "complete": withheld <= 0}
        entry["note"] = (
            f"{connector} reported no actor on any of its {total} rows, so until its "
            "actor path is declared, even your own account attributes nothing there"
            if not candidates else
            f"{connector}: {distinct} account(s) appear across {total} rows"
            + (f", and I can only offer {len(candidates)} of them here — if none of "
               f"those {len(candidates)} is you, type the account name instead"
               if withheld > 0 else ", and all of them are offered here"))
        asking.append(entry)
    if not asking:
        return None
    named = ", ".join(entry["connector"] for entry in asking)
    return {
        "question": f"I cannot tell which of the actors I read is you in {named}. "
                    "Which account is yours in each? Until you say, I am claiming "
                    "none of that work is yours.",
        "connectors": asking,
        "is_a_question": True,
    }


def _day(value):
    match = _DAY_RE.match(str(value or "").strip())
    return match.group(0) if match else None


def period_read(rows) -> dict:
    """The window a sweep actually covers, in the ROWS' own terms.

    Never a window chosen here. "The last 90 days" asserts a period nothing
    verified — the sources decide what they date, and some of them date nothing.
    Reporting the observed extent plus how many rows carried a date at all is the
    honest version of the same sentence, and it is what makes the assumption
    underneath it visible enough to be contradicted.
    """
    stamps, dated, total = [], 0, 0
    for row in rows or ():
        total += 1
        day = _day(row.get("updated"))
        if day:
            dated += 1
            stamps.append(day)
    if not stamps:
        return {"from": None, "to": None, "dated_rows": 0, "rows": total,
                "basis": "no source dated anything, so this sweep has no period at all"}
    return {"from": min(stamps), "to": max(stamps), "dated_rows": dated, "rows": total,
            "basis": "the earliest and latest dates the sources themselves carried"}


def presence_question(rows, operator, period, *, quiet_days: int = QUIET_DAYS):
    """A gap in the operator's OWN activity, handed back as a QUESTION.

    Never as a finding. A quiet fortnight inside the window may be a holiday, a
    leave, or another job, and everything derived from it is then wrong in a way
    no additional data repairs. Where the record does not resolve the operator
    for a connector, NO gap is claimed there at all — an unattributable silence
    is not evidence about the operator, and treating it as such is precisely the
    unearned negative this lane exists to avoid.
    """
    mine: dict = {}
    for row in rows or ():
        connector = str(row.get("connector") or "")
        wanted = {_fold(h) for h in _recorded_handles(operator, connector)}
        # ANY of the row's actors being the operator makes the row theirs. A row
        # names everyone the declared paths resolved, and the operator is often
        # the second name in it — matching only a single actor field would report
        # a quiet fortnight that the data contradicts.
        if not wanted or not wanted & {_fold(a) for a in _row_actors(row)}:
            continue
        day = _day(row.get("updated"))
        if day:
            mine.setdefault(connector, []).append(day)
    days = sorted({d for values in mine.values() for d in values})
    if len(days) < 2:
        return None
    gaps = []
    for earlier, later in zip(days, days[1:]):
        span = (datetime.fromisoformat(later).replace(tzinfo=timezone.utc)
                - datetime.fromisoformat(earlier).replace(tzinfo=timezone.utc)).days
        if span >= quiet_days:
            gaps.append((span, earlier, later))
    if not gaps:
        return None
    span, earlier, later = max(gaps)
    connectors = sorted(mine)
    return {
        "question": f"I read {period.get('from')} to {period.get('to')}, and between "
                    f"{earlier} and {later} — {span} days — I see nothing from you in "
                    f"{', '.join(connectors)}. Was that time away, or was the work "
                    "happening somewhere I cannot see?",
        "options": ["I was away", "the work was elsewhere", "that is right, it was quiet"],
        "gap_days": span, "from": earlier, "to": later,
        "attribution": [attribution_basis(operator, c) for c in connectors],
        "is_a_question": True,
    }


def who_and_when(rows, record=None) -> dict:
    """The sweep's two silent claims, made out loud, in one block.

    One call so a consumer cannot take the period and forget the basis: the
    period is only meaningful alongside who it is a period OF, and the whole
    point of this pair is that they travel together.
    """
    operator = operator_identity(record)
    period = period_read(rows)
    connectors = sorted({str(r.get("connector") or "") for r in (rows or ()) if r.get("connector")})
    return {
        "operator": operator,
        "period": period,
        # ROWS TRAVEL WITH THE BASIS, so a resolved connector states its SHARE
        # rather than the bare fact of recognition. A basis without numbers
        # licenses "your top project"; with them the only sentence available is
        # the one that says how much of this is actually the operator's.
        "attribution": [attribution_basis(operator, c, rows) for c in connectors],
        "identity_question": identity_question(rows, operator),
        "presence_question": presence_question(rows, operator, period),
    }


def who_and_when_lines(block) -> list:
    """The same block as sentences for the operator-facing not-reached list.

    The period sentence NAMES its assumption instead of implying it, and an
    unresolved connector says so rather than being quietly omitted — a
    disclosure that only mentions what it managed to resolve is how a partial
    read starts reading as a complete one.
    """
    lines = []
    period = (block or {}).get("period") or {}
    if period.get("from"):
        lines.append(
            f"what I ranked is dated {period['from']} to {period['to']} "
            f"({period.get('dated_rows')} of {period.get('rows')} carried a date), "
            "and I am assuming that period is representative of your work")
    else:
        lines.append("nothing I read carried a date, so this has no period at all")
    attribution = list((block or {}).get("attribution") or ())
    # THE RESOLVED HALF IS DISCLOSED TOO, and it used to be silent. Only the
    # unresolved connectors got a sentence, so a reader was told what could not
    # be attributed and never what WAS — which is the half that can be wrong,
    # and the half a person can correct in four words. Each resolved line
    # carries its share, so "yours" always arrives as a proportion.
    for entry in attribution:
        if entry.get("basis") != "unresolved":
            lines.append(entry["statement"])
    unresolved = [a["connector"] for a in attribution if a.get("basis") == "unresolved"]
    if unresolved:
        lines.append(
            "I cannot tell which actor is you in " + ", ".join(unresolved)
            + ", so I am not claiming any of that activity is yours")
    identity = (block or {}).get("identity_question")
    if identity:
        lines.append(identity["question"])
        lines.extend(entry["note"] for entry in identity["connectors"]
                     if entry.get("reports_no_actor"))
    question = (block or {}).get("presence_question")
    if question:
        lines.append(question["question"])
    return lines
