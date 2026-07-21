"""Twin-drift pin for presets/developer vs presets/work (PRESET-DEV-1).

The developer preset is a FLAT COPY of the work preset (flat only, no
inheritance — presets/README.md) plus an explicit, ratified delta set.
Near-duplicate presets drift silently (the shipped-pack copy⇄canonical
defect class test_memory_distill.py pins for doctrine packs); this module
is the same pin at preset scale:

  * every developer file OUTSIDE the allowlist is byte-identical to its
    work twin (a work-side fix must be re-copied, not forked);
  * every work file HAS a developer counterpart (flat-copy completeness);
  * every ALLOWLISTED delta actually differs (an allowlist entry that
    became byte-equal is rot — remove it);
  * developer-only files are exactly the declared kit additions;
  * the kit's contracts hold: preset.yml onboarding block
    (declarations-only, framework-neutral), the root .mcp.json additive
    entries (env placeholders, never literal secrets), the marketplace
    row;
  * residue battery: zero mother-instance residue and zero secret-shaped
    strings anywhere in presets/developer/ + packs/preset-developer-pack/
    (residue literals live HERE, in the ratchet, per the
    test_no_launcher_hardcode.py precedent — the scanned trees must never
    contain them).

Run: python3.12 -m pytest cabinet/scripts/tests/test_preset_developer_parity.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORK = REPO / "presets" / "work"
DEV = REPO / "presets" / "developer"
PACK = REPO / "packs" / "preset-developer-pack"

# developer-relative path -> work-relative twin, where the FILENAME differs.
# test_org_scenarios_developer.py: neither tests/ dir has an __init__.py, so
# under repo-root pytest collection a same-basename module in two dirs is a
# collection-time import collision — the rename is load-bearing.
RENAMED_TWINS = {
    "measurement/tests/test_org_scenarios_developer.py":
        "measurement/tests/test_org_scenarios.py",
}

# developer-relative paths RATIFIED to differ from their work twin
# (2026-07-17 developer-preset wave; see the PRESET-DEV-1 ledger row).
ALLOWED_DELTA = {
    "preset.yml",                    # name/description/onboarding lane_mcps + hire guidance
    "terminology.yml",               # + coordinator_title: First Mate (display layer)
    "safety-addendum.md",            # + connector rows, declared-OFF table, trifecta legs
    "constitution-addendum.md",      # software product-kind framing
    "validate.sh",                   # + neutrality assert + residue battery
    "cto-first-assignment.md",       # + GitHub-surface walk, REST-not-MCP note
    "agents/cos.md",                 # First Mate display title (machine id cos frozen)
    "agents/cto.md",                 # + mcp__github tool + GitHub work-surface bullet
    "agents/cpo.md",                 # + product-CEO pairing paragraph
    "measurement/tests/test_org_scenarios_developer.py",  # renamed + namespace swap
    # Self-identification fixes (review finding cp1#1 — a copied file whose
    # own header/instructions pointed at presets/work would have a developer
    # deployment installing/seeding from the WORK tree; headers now name this
    # location, content otherwise byte-twin):
    "measurement/README.md",         # install/pytest paths + renamed test name
    "schemas.sql",                   # header self-id (tables byte-twin)
    "starter-spaces/business-brain.yml",  # header self-id + --preset developer
}

# developer-only additions (no work twin by design — the software kit).
NO_TWIN = {
    "README.md",
    "connectors/github.md",
    "connectors/playwright.md",
    "connectors/neon.md",
    "connectors/vercel.md",
    "connectors/sentry.md",
    "connectors/stripe.md",
    "connectors/posthog.md",
    "connectors/resend.md",
    "starter/probes.yml",
    "starter-spaces/product-journal.yml",
}


def _rel_files(root: Path) -> set[str]:
    return {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def _twin_for(dev_rel: str) -> str:
    return RENAMED_TWINS.get(dev_rel, dev_rel)


class TestFlatCopyParity:
    def test_every_work_file_has_a_developer_counterpart(self):
        dev_files = _rel_files(DEV)
        covered = {_twin_for(d) for d in dev_files}
        missing = _rel_files(WORK) - covered
        assert not missing, (
            f"work files with no developer counterpart (flat-copy hole — "
            f"re-copy them): {sorted(missing)}"
        )

    def test_developer_extras_are_exactly_the_declared_kit(self):
        extras = {
            d for d in _rel_files(DEV)
            if _twin_for(d) not in _rel_files(WORK)
        }
        assert extras == NO_TWIN, (
            f"undeclared developer-only files (extend NO_TWIN deliberately or "
            f"remove them): {sorted(extras ^ NO_TWIN)}"
        )

    def test_non_delta_files_byte_identical(self):
        drifted = []
        for dev_rel in sorted(_rel_files(DEV)):
            if dev_rel in ALLOWED_DELTA or dev_rel in NO_TWIN:
                continue
            twin = WORK / _twin_for(dev_rel)
            if not twin.is_file():
                continue  # covered by the extras test
            if (DEV / dev_rel).read_bytes() != twin.read_bytes():
                drifted.append(dev_rel)
        assert not drifted, (
            f"developer files drifted from their work twin outside the "
            f"ratified allowlist (re-copy from work, or ratify + allowlist): "
            f"{drifted}"
        )

    def test_allowlisted_deltas_actually_differ(self):
        stale = []
        for dev_rel in sorted(ALLOWED_DELTA):
            dev_f = DEV / dev_rel
            twin = WORK / _twin_for(dev_rel)
            assert dev_f.is_file(), f"allowlisted delta missing: {dev_rel}"
            assert twin.is_file(), f"allowlisted twin missing: {_twin_for(dev_rel)}"
            if dev_f.read_bytes() == twin.read_bytes():
                stale.append(dev_rel)
        assert not stale, (
            f"allowlist rot — these no longer differ from their twin (drop "
            f"them from ALLOWED_DELTA): {stale}"
        )


class TestKitContracts:
    def test_preset_yml_declarations(self):
        text = (DEV / "preset.yml").read_text(encoding="utf-8")
        try:
            import yaml
            data = yaml.safe_load(text)
        except ModuleNotFoundError:
            data = None
        if data is not None:
            assert data["name"] == "developer"
            ob = data["onboarding"]
            # declarations-only + framework-neutral: no plugin is universal
            assert ob["cabinet_default_plugins"] == []
            assert ob["lane_mcps"] == [
                "library", "telegram", "github", "playwright", "neon-ro"]
        # personal-source plugin ids never in the onboarding block (either path)
        onboarding_block = text[text.index("onboarding:"):]
        active = "\n".join(
            ln for ln in onboarding_block.splitlines()
            if not ln.lstrip().startswith("#"))
        assert not re.search(r"\b(corridor|brain)\b", active), (
            "instance-specific plugin ids re-imported into the developer "
            "onboarding defaults")

    def test_mcp_json_additive_entries(self):
        mcp = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
        servers = mcp["mcpServers"]
        # pre-existing entries still present (additive-only law)
        for legacy in ("neon", "notion", "vercel", "redis-trigger-channel",
                       "cabinet-comms", "make"):
            assert legacy in servers, f"pre-existing .mcp.json entry lost: {legacy}"
        gh = servers["github"]
        assert gh["url"] == "https://api.githubcopilot.com/mcp/"
        assert gh["headers"]["Authorization"] == "Bearer ${GITHUB_PAT}"
        ro = servers["neon-ro"]
        assert "readonly=true" in ro["url"]
        assert ro["headers"]["Authorization"] == "Bearer ${NEON_API_KEY}"
        pw = servers["playwright"]
        assert pw["command"] == "npx"
        assert pw["args"] == ["-y", "@playwright/mcp"]  # unpinned first-party
        # no OAuth-only server rides the developer lane_mcps by name
        for name in ("github", "neon-ro", "playwright"):
            assert "oauth" not in json.dumps(servers[name]).lower()

    def test_marketplace_carries_the_pack(self):
        mkt = json.loads(
            (REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        rows = {p["name"]: p for p in mkt["plugins"]}
        row = rows["preset-developer-pack"]
        assert row["source"]["path"] == "packs/preset-developer-pack"
        assert "developer" in rows["captains-cabinet"]["description"], (
            "core plugin description no longer names the developer preset")

    def test_pack_references_never_copies_payload(self):
        pack_files = _rel_files(PACK)
        assert "manifest.yml" in pack_files
        assert ".claude-plugin/plugin.json" in pack_files
        assert "skills/preset-developer/SKILL.md" in pack_files
        # orientation-only: no preset payload files inside the pack
        payload_shaped = {f for f in pack_files
                          if f.startswith(("agents/", "connectors/",
                                           "starter", "measurement/"))
                          or f in ("preset.yml", "schemas.sql", "validate.sh")}
        assert not payload_shaped, (
            f"pack copies preset payload (must reference presets/developer/ "
            f"instead): {sorted(payload_shaped)}")


# ---------------------------------------------------------------------------
# Residue battery — the scanned trees ship to every fork, so they must carry
# zero mother-instance residue. The real name/employer/product/tooling tokens
# are PER-DEPLOYMENT and never ride a public egg cut, so they load from the
# untracked, gitignored instance/config/publish-scan-patterns.local (the same
# per-captain file the publish gate + the fixture leak-audit use — R166) when
# present (dev box + source-instance CI keep full teeth), else its shipped
# synthetic template twin. The .local ``word:``/``sub:`` kinds preserve the
# original word-bounded-vs-substring split (short/common tokens word-bounded so
# "coordinate"/"designate" never false-positive; distinctive tokens substring);
# the telegram-chat-id shape stays hardcoded — it is a captain-agnostic
# STRUCTURAL pattern, not a real value. No real literal is tracked here.
# ---------------------------------------------------------------------------
_PATTERNS_LOCAL = REPO / "instance" / "config" / "publish-scan-patterns.local"
_PATTERNS_EXAMPLE = REPO / "instance" / "config" / "publish-scan-patterns.local.example"


def _load_scan_tokens() -> "tuple[list[str], list[str]]":
    """(sub_tokens, word_tokens) from the per-deployment publish-scan file, else
    its synthetic template twin, else empty. Plain file read (no import/eval)."""
    src = _PATTERNS_LOCAL if _PATTERNS_LOCAL.is_file() else _PATTERNS_EXAMPLE
    subs: list[str] = []
    words: list[str] = []
    if src.is_file():
        for raw in src.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("pattern "):
                continue
            kind, _, value = line[len("pattern "):].strip().partition(":")
            if not value:
                continue
            (words if kind == "word" else subs if kind == "sub" else []).append(value)
    return subs, words


def _build_residue() -> "re.Pattern[str]":
    subs, words = _load_scan_tokens()
    alts = [re.escape(s) for s in subs] + [r"\b%s\b" % re.escape(w) for w in words]
    # captain-agnostic STRUCTURAL shape (telegram chat/hq id refs) — always on.
    alts.append(r"telegram.{0,8}(?:chat|hq).{0,4}id")
    return re.compile("|".join(alts), re.IGNORECASE)


_RESIDUE = _build_residue()

# corridor/brain are personal-source PLUGIN ids: they must never be WIRED in
# the kit. Plugin ids live on CONFIG surfaces (yml/json values), so the id
# scan covers those, non-comment lines only — prose docs may NAME the
# exclusion (the shipped work preset.yml documents "corridor, brain belong to
# instance overlays" in a comment; the flat copy keeps it) but cannot wire a
# plugin. The full-residue scan above still sweeps every file for hard
# residue (names/products/paths).
_CORRIDOR = re.compile(r"\bcorridor\b", re.IGNORECASE)

# 'brain' hand-check split: 'Business Brain' Space naming (incl. the
# business_brain template slug) is legitimate; the brain PLUGIN id is not.
# (The software kit's own Space is 'Product Journal' — renamed off the
# vault-ratcheted product-compound token, test_vault_rename_ratchet.py.)
_BRAIN_OK_LINE = re.compile(
    r"(product|business)[ \-_]brain|brain[- ]?plugin[- ]?id", re.IGNORECASE)
_BRAIN = re.compile(r"\bbrain\b", re.IGNORECASE)

_SECRET_SHAPES = re.compile(r"sk-|ghp_|pat_|xoxb|AKIA|-----BEGIN")

# validate.sh line that CARRIES the enforcement pattern (the one sanctioned
# residue-literal carrier inside the kit — it excludes itself in-script and
# is filtered by pattern-definition shape here, so the REST of validate.sh
# stays fully swept).
_CARRIER_LINE = re.compile(r"^\s*residue_pattern=")

_CONFIG_SUFFIXES = {".yml", ".yaml", ".json"}


def _scan(trees, pattern, line_filter=None, suffixes=None):
    hits = []
    for tree in trees:
        for f in sorted(tree.rglob("*")):
            if not f.is_file() or "__pycache__" in f.parts:
                continue
            if suffixes and f.suffix not in suffixes:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    if line_filter and line_filter(line):
                        continue
                    hits.append(f"{f.relative_to(REPO)}:{i}: {line.strip()[:120]}")
    return hits


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


class TestResidueBattery:
    TREES = (DEV, PACK)

    def test_zero_personal_residue(self):
        hits = _scan(self.TREES, _RESIDUE,
                     line_filter=lambda ln: bool(_CARRIER_LINE.match(ln)))
        assert not hits, "personal residue in the shipped kit:\n" + "\n".join(hits)

    def test_corridor_plugin_id_never_wired(self):
        hits = _scan(self.TREES, _CORRIDOR,
                     line_filter=_is_comment, suffixes=_CONFIG_SUFFIXES)
        assert not hits, (
            "corridor plugin id on a config surface of the shipped kit:\n"
            + "\n".join(hits))

    def test_brain_plugin_id_never_wired(self):
        hits = _scan(
            self.TREES, _BRAIN, suffixes=_CONFIG_SUFFIXES,
            line_filter=lambda ln: _is_comment(ln) or bool(
                _BRAIN_OK_LINE.search(ln)))
        assert not hits, (
            "'brain' on a config surface outside Product/Business Brain "
            "Space naming (the brain PLUGIN id must not ship):\n"
            + "\n".join(hits))

    def test_zero_secret_shaped_strings(self):
        hits = _scan(self.TREES, _SECRET_SHAPES)
        assert not hits, "secret-shaped strings in the kit:\n" + "\n".join(hits)

    def test_env_names_upper_snake(self):
        """Every ${...} placeholder on the kit's declaration surfaces + its
        .mcp.json entries is an env-var NAME (UPPER_SNAKE), mirroring
        generate-instance's intake gate. Shell scripts are excluded — bash
        internals (${BASH_SOURCE[0]}, array expansions) are not env
        declarations."""
        env_re = re.compile(r"\$\{([^}]+)\}")
        name_re = re.compile(r"^[A-Z][A-Z0-9_]{2,63}(?::-[^}]*)?$")
        bad = []
        for tree in self.TREES:
            for f in sorted(tree.rglob("*")):
                if not f.is_file() or "__pycache__" in f.parts:
                    continue
                if f.suffix == ".sh":
                    continue
                try:
                    text = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for m in env_re.finditer(text):
                    if not name_re.match(m.group(1)):
                        bad.append(f"{f.relative_to(REPO)}: ${{{m.group(1)}}}")
        mcp = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
        for name in ("github", "neon-ro"):
            for v in mcp["mcpServers"][name].get("headers", {}).values():
                for m in env_re.finditer(v):
                    if not name_re.match(m.group(1)):
                        bad.append(f".mcp.json[{name}]: ${{{m.group(1)}}}")
        assert not bad, "non-UPPER_SNAKE env placeholders:\n" + "\n".join(bad)
