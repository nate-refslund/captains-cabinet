"""Library retirement ratchet (2026-07-16) — no NEW callers of the removed
record-vector embed path.

The retirement (Captain-ratified, closes memory-study Q4/C7) removed the
Library's second vector store WRITE path:

  * library.sh create/update no longer call memory_get_embedding or bind an
    embedding value into library_records INSERTs.
  * dashboard src/lib/library.ts lost getEmbedding (Voyage) entirely.

This ratchet greps the tree so the path cannot quietly resurface. The
DORMANT surfaces stay allowlisted by construction: cabinet/sql DDL keeps the
column/trigger (no destructive DDL shipped), library_search still reads
LEGACY vectors (query-side embed — a read, not a record-vector write), and
memory.sh's own embed functions serve cabinet_memory, which is the blessed
store. If you need vectors on Library-shaped data, use cabinet_memory.

Also ratcheted here (docs track the code):
  * CLAUDE.md + docs/templates/CLAUDE-egg.md (the egg template BECOMES the
    public egg's CLAUDE.md at export) route Cabinet knowledge to the vault +
    memory_search — never to the deregistered Library MCP;
  * no non-germline agent frontmatter grants the retired mcp__library tool
    (germline grant surfaces — .claude/settings.json allow-list,
    cabinet/mcp-scope.yml — keep dangling-but-harmless entries until the
    ceremony; see the runbook's follow-ups);
  * the retire-library-export.py archive dirs stay gitignored (runtime-only —
    exported DB-derived records must never ride a commit into the egg);
  * the staged comment-only ceremony patch for schg-locked
    start-officer-mac.sh stays appliable until the Captain window lands it.

Run: python3.12 -m pytest cabinet/scripts/tests/test_library_retirement_ratchet.py -q
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LIBRARY_SH = REPO / "cabinet/scripts/lib/library.sh"
DASH_LIBRARY_TS = REPO / "cabinet/dashboard/src/lib/library.ts"

# Source trees where a resurrected write path would live. cabinet/sql is
# deliberately NOT scanned (dormant DDL keeps the embedding column); tests
# and docs mention the patterns by name and are excluded.
SCAN_ROOTS = ("cabinet/scripts", "cabinet/channels", "cabinet/dashboard/src",
              "framework")
SCAN_SUFFIXES = {".sh", ".bash", ".py", ".ts", ".tsx", ".js", ".mjs"}
EXCLUDE_PARTS = {"node_modules", ".next", ".git", "tests", "__tests__",
                 "fixtures"}


def _scan_files():
    for root in SCAN_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if EXCLUDE_PARTS & set(path.parts):
                continue
            if path.name.endswith((".test.ts", ".test.tsx")):
                continue
            yield path


def _fn_body(text: str, name: str, next_name: str) -> str:
    start = text.index(f"{name}() {{")
    end = text.index(f"{next_name}()", start)
    return text[start:end]


def test_library_sh_write_path_stays_vector_free():
    text = LIBRARY_SH.read_text()
    create = _fn_body(text, "library_create_record", "library_update_record")
    update = _fn_body(text, "library_update_record", "library_get_record")
    for body, label in ((create, "library_create_record"),
                        (update, "library_update_record")):
        assert "memory_get_embedding" not in body, (
            f"{label} re-grew a record-vector embed call — the Library's "
            "second vector store is retired; use the cabinet_memory queue")
        assert "::vector" not in body and ":'embedding'" not in body, (
            f"{label} binds an embedding into SQL again")
        assert "memory_queue_embed" in body, (
            f"{label} lost the cabinet_memory mirror queue — that's the "
            "search-continuity path and must stay")


def test_dashboard_library_ts_has_no_voyage_and_no_vector_write():
    text = DASH_LIBRARY_TS.read_text()
    assert "voyageai" not in text, "Voyage embed client resurfaced in library.ts"
    assert "getEmbedding" not in text, "getEmbedding resurfaced in library.ts"
    assert "embedded_at" not in text, "embedded_at write resurfaced in library.ts"
    # Every INSERT INTO library_records in the dashboard lib is vector-free.
    for m in re.finditer(r"INSERT INTO library_records[\s\S]{0,400}", text):
        assert "embedding" not in m.group(0), (
            "library_records INSERT regained an embedding column:\n" + m.group(0))


def test_no_new_record_vector_writers_repo_wide():
    """Any INSERT into / UPDATE of library_records that touches an
    `embedding` column, anywhere in the scanned source trees, is a
    regression. (cabinet/sql dormant DDL + tests are excluded by design;
    the 044 trigger CLEARS the column, and lives in sql/.)"""
    offenders = []
    ins_re = re.compile(r"INSERT INTO library_records[\s\S]{0,400}")
    upd_re = re.compile(r"UPDATE library_records[\s\S]{0,200}")
    for path in _scan_files():
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for m in ins_re.finditer(text):
            chunk = m.group(0)
            # Column-list / VALUES containing a bare `embedding` token.
            if re.search(r"\bembedding\b", chunk):
                offenders.append(f"{path}: INSERT …embedding…")
        for m in upd_re.finditer(text):
            if re.search(r"SET[\s\S]{0,120}\bembedding\b", m.group(0)):
                offenders.append(f"{path}: UPDATE …SET embedding…")
    assert offenders == [], (
        "record-vector write path resurfaced:\n" + "\n".join(offenders))


def test_library_mcp_stays_deregistered():
    """Both MCP config layers stay library-free (deregistered 2026-07-16).
    Re-registration is a deliberate Captain-visible act — see the runbook."""
    import json
    for cfg in (REPO / ".mcp.json", REPO / ".mcp.json.mac-native"):
        data = json.loads(cfg.read_text())
        assert "library" not in data.get("mcpServers", {}), (
            f"{cfg.name}: library MCP server re-registered — the Library is "
            "retired (docs/runbooks/library-retirement-2026-07-16.md)")


def test_runbook_exists_and_names_the_archive():
    runbook = REPO / "docs/runbooks/library-retirement-2026-07-16.md"
    text = runbook.read_text()
    assert "library-archive" in text
    assert "retire-library-export.py" in text
    assert "memory_search" in text
    # The export is NOT auto-indexed (the post-file-write hook only fires on
    # Claude-session tool writes) — the runbook must keep the operator step.
    assert "backfill-memory.sh" in text


ROUTING_DOCS = ("CLAUDE.md", "docs/templates/CLAUDE-egg.md")


def test_routing_docs_point_knowledge_at_vault_not_library_mcp():
    """CLAUDE.md is the highest-traffic officer doctrine file, and the egg
    template becomes the PUBLIC egg's CLAUDE.md at export (egg-export.sh
    claude-egg-swap). Neither may route Cabinet knowledge to an MCP server
    that no longer boots."""
    for rel in ROUTING_DOCS:
        text = (REPO / rel).read_text()
        assert "Library MCP" not in text, (
            f"{rel} still routes knowledge to the retired Library MCP — "
            "knowledge = the vault (product-brain/), recall = memory_search")
        assert "mcp__library" not in text, (
            f"{rel} references the retired mcp__library tool")
        assert "memory_search" in text, (
            f"{rel} lost the replacement recall route (memory_search)")


AGENT_GRANT_ROOTS = ("instance/agents", "presets")


def test_no_agent_frontmatter_grants_the_retired_library_tool():
    """The server is deregistered from both .mcp.json layers, so a tools:
    grant is a dangling no-op — but new agent files are written by copying
    existing ones, and a dangler invites resurrection-by-copy. Germline
    grant surfaces (.claude/settings.json allow-list, cabinet/mcp-scope.yml)
    are schg-locked and deliberately NOT scanned — they carry their entries
    until the ceremony (runbook follow-ups)."""
    offenders = []
    for root in AGENT_GRANT_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or "agents" not in path.parts:
                continue
            if not (path.name.endswith(".md")
                    or path.name.endswith(".md.template")):
                continue
            if "mcp__library" in path.read_text(errors="replace"):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "agent files still grant the retired mcp__library tool: "
        + ", ".join(sorted(offenders)))


def test_library_archive_export_dirs_are_gitignored():
    """retire-library-export.py writes DB-derived officer/instance knowledge
    into <root>/{vault,product-brain}/library-archive/. product-brain/ is
    TRACKED and ships in the public egg (egg-export cuts from HEAD) — the
    archive is runtime-only and must never be committable."""
    lines = [ln.strip() for ln in (REPO / ".gitignore").read_text().splitlines()]
    for required in ("product-brain/library-archive/", "vault/library-archive/"):
        assert required in lines, (
            f".gitignore lost the '{required}' runtime-only guard — exported "
            "Library records would ride a commit into the public egg")


# =========================================================================
# Staged germline ceremony patch (comment-only) — keep it appliable
# =========================================================================

STAGED_PATCH = (REPO / "docs/proposals"
                / "germline-library-retirement-2026-07-16.patch")
START_OFFICER_MAC = REPO / "cabinet/scripts/start-officer-mac.sh"
_PATCHED_MARK = "library deregistered 2026-07-16"


@pytest.mark.skipif(shutil.which("patch") is None,
                    reason="patch(1) unavailable")
def test_staged_ceremony_patch_stays_appliable_and_comment_only(tmp_path):
    """The stale 'notion/linear/neon/library' merge-comment fix for the
    schg-locked start-officer-mac.sh ships as a staged patch
    (docs/proposals/germline-library-retirement-2026-07-16.patch — a plain
    FILE directly under docs/proposals/ BY CONTRACT: t_proposals_archive
    rm -f's each entry and a subdirectory would abort the egg export) and is
    applied only inside a Captain unlock window (see the same-named
    -addendum doc). STATE-AWARE: post-ceremony the live file carries the new
    comment and the patch is spent — skip. Runs entirely on COPIES; never
    touches the lock. Comment-only is ENFORCED: non-comment lines must be
    byte-identical before/after."""
    live = START_OFFICER_MAC.read_text(errors="replace")
    if _PATCHED_MARK in live:
        pytest.skip("ceremony landed — staged patch already applied")
    assert "notion/linear/neon/library" in live, (
        "start-officer-mac.sh's merge-comment changed shape — re-derive the "
        "staged patch + addendum before the ceremony")
    tree = tmp_path / "tree" / "cabinet" / "scripts"
    tree.mkdir(parents=True)
    shutil.copy(START_OFFICER_MAC, tree / "start-officer-mac.sh")
    with STAGED_PATCH.open("rb") as fh:
        proc = subprocess.run(["patch", "-p1", "-d", str(tmp_path / "tree")],
                              stdin=fh, capture_output=True, timeout=60)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert not list((tmp_path / "tree").rglob("*.rej")), "patch produced rejects"
    patched = (tree / "start-officer-mac.sh").read_text(errors="replace")
    assert _PATCHED_MARK in patched
    strip = lambda text: [ln for ln in text.splitlines()
                          if not ln.lstrip().startswith("#")]
    assert strip(live) == strip(patched), (
        "staged ceremony patch must stay comment-only — zero behavior change")
    syntax = subprocess.run(["bash", "-n", str(tree / "start-officer-mac.sh")],
                            capture_output=True, text=True, timeout=30)
    assert syntax.returncode == 0, syntax.stderr
