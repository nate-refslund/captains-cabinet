"""Bootstrap memory-chain locks — day-1 org recall infrastructure (static).

Grep-level, offline locks (read_text + regex + ``bash -n``; no network, no
Neon, no Redis) over the clean-room bootstrap chain that Wave-1 (2026-07-07)
depends on. Each assertion pins one link a fresh org box needs for recall to
work on day 1 — if a future change drops the link, the failure lands HERE
with the reason, not as a silent zero-recall outage on the next deployment:

  * cabinet-bootstrap.sh applies ``cabinet_memory.sql`` (the memory estate),
    ``cabinet_research.sql`` (the research estate) and
    ``cabinet-memory-content-tsv.sql`` (the hybrid lexical substrate) —
    memory_search hard-references content_tsv, so a bootstrap that skips any
    of these boots a box whose every search hard-errors;
  * cabinet/sql/cabinet_memory.sql base schema itself carries content_tsv
    (column + GIN index — either apply order must converge);
  * cabinet/services.yml carries the memory-chain service rows:
    memory-worker (embed queue drain), memory-reconcile (hook-missed /
    hash-drift catch-up), self-improvement-loop (the learning cadence);
  * the post-file-write memory hook watches the org knowledge corpus (the
    cabinet vault — vault/, formerly product-brain/) so org knowledge written
    by officers is embedded as it lands; the hook lives in the schg-locked
    germline hooks dir — its vault/ + docs/ patterns LANDED on master
    2026-07-17 (CG-30 master-first; the LIVE schg inode syncs at the Captain
    checkout window; patches/germline-vault-hook-watch-2026-07-17.patch stays
    as the ceremony reference) while the nightly reconcile (unlocked) walks
    vault/, legacy product-brain/, and docs/**/*.md directly as the coverage
    netting;
  * the hook and reconcile watch lists stay in sync BY DESIGN — the
    hook⊆reconcile direction is pinned here so a hook pattern can never
    exist without its nightly-netting twin.

Run: python3 -m pytest cabinet/scripts/tests/test_bootstrap_memory_chain.py -q
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

# Captured at import (collection) time, BEFORE any test runs:
# test_library_mcp_client patches the global subprocess.Popen and the patch
# can leak across modules in a whole-repo run — restore the real one around
# our spawns so a leaked FakePopen can't fail these tests.
_REAL_POPEN = subprocess.Popen

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

BOOTSTRAP_SH = _SCRIPTS_DIR / "cabinet-bootstrap.sh"
MEMORY_SQL = _REPO_ROOT / "cabinet/sql/cabinet_memory.sql"
SERVICES_YML = _REPO_ROOT / "cabinet/services.yml"
PFWM_HOOK = _SCRIPTS_DIR / "hooks/post-file-write-memory.sh"
RECONCILE_SH = _SCRIPTS_DIR / "memory-reconcile.sh"
BACKFILL_SH = _SCRIPTS_DIR / "backfill-memory.sh"


def _bash_n(path: Path) -> None:
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True, timeout=60
        )
    finally:
        subprocess.Popen = patched
    assert proc.returncode == 0, f"bash -n {path.name} failed: {proc.stderr}"


def _on_a_live_line(needle_regex: str, text: str) -> bool:
    """True when the pattern appears on a NON-comment line (nothing but
    non-``#`` characters before the match) — a comment mention alone must
    not satisfy an apply-list / watch-list lock."""
    return re.search(rf"^[^#\n]*{needle_regex}", text, re.M) is not None


# ---------------------------------------------------------------------------
# bash syntax — the chain's scripts must at least parse
# ---------------------------------------------------------------------------

def test_bash_syntax_cabinet_bootstrap():
    _bash_n(BOOTSTRAP_SH)


def test_bash_syntax_post_file_write_memory_hook():
    _bash_n(PFWM_HOOK)


# ---------------------------------------------------------------------------
# cabinet-bootstrap.sh — the schema apply list
# ---------------------------------------------------------------------------

def test_bootstrap_applies_memory_base_schema():
    text = BOOTSTRAP_SH.read_text()
    assert _on_a_live_line(r"cabinet_memory\.sql", text), (
        "cabinet-bootstrap.sh no longer applies cabinet_memory.sql — a fresh "
        "box would boot with NO memory estate (zero recall)"
    )


def test_bootstrap_applies_research_schema():
    text = BOOTSTRAP_SH.read_text()
    assert _on_a_live_line(r"cabinet_research\.sql", text), (
        "cabinet-bootstrap.sh apply list must include cabinet_research.sql — "
        "embed-research/search-research hard-error without the table"
    )


def test_bootstrap_applies_content_tsv_migration():
    text = BOOTSTRAP_SH.read_text()
    assert _on_a_live_line(r"cabinet-memory-content-tsv\.sql", text), (
        "cabinet-bootstrap.sh apply list must include "
        "cabinet-memory-content-tsv.sql — memory_search hard-references "
        "content_tsv (hybrid lexical leg); without it every search on a "
        "pre-existing estate hard-errors"
    )


# ---------------------------------------------------------------------------
# cabinet_memory.sql — base schema carries the hybrid lexical substrate
# ---------------------------------------------------------------------------

def test_cabinet_memory_base_schema_carries_content_tsv():
    """Wave-1 fix: the base schema itself must carry content_tsv (column +
    GIN index), so a deployment that ran ONLY cabinet_memory.sql still has a
    working hybrid search — either apply order converges."""
    text = MEMORY_SQL.read_text()
    assert re.search(
        r"ADD COLUMN IF NOT EXISTS content_tsv\s+tsvector", text
    ), "cabinet_memory.sql lost the content_tsv column (hybrid lexical leg)"
    assert re.search(r"USING GIN\s*\(content_tsv\)", text), (
        "cabinet_memory.sql lost the GIN index on content_tsv"
    )


# ---------------------------------------------------------------------------
# services.yml — the memory-chain rows exist in the fleet manifest
# ---------------------------------------------------------------------------

def test_services_manifest_carries_memory_chain_rows():
    data = yaml.safe_load(SERVICES_YML.read_text())
    rows = data.get("services") if isinstance(data, dict) else data
    assert isinstance(rows, list), "cabinet/services.yml: no services list"
    names = {r.get("name") for r in rows if isinstance(r, dict)}
    for required in ("memory-worker", "memory-reconcile", "self-improvement-loop"):
        assert required in names, (
            f"cabinet/services.yml lost the {required} row — the memory "
            f"chain (embed → reconcile → learn) no longer runs unattended"
        )


# ---------------------------------------------------------------------------
# post-file-write-memory.sh — the hook watches the org knowledge corpus
# ---------------------------------------------------------------------------

def test_post_file_write_hook_watches_the_org_corpus():
    """The hook must watch the org corpus under SOME name: the legacy
    product-brain pattern (kept as an alias for un-migrated/external corpora)
    or the vault/ pattern (lands via the 2026-07-17 germline ceremony patch —
    the hooks dir is schg-locked). Losing BOTH would mean org corpus writes
    are never embedded at write time (day-1 org knowledge waits on the
    nightly reconcile)."""
    text = PFWM_HOOK.read_text()
    assert (_on_a_live_line(r"product[-_]brain", text)
            or _on_a_live_line(r"\*/vault/\*\.md", text)), (
        "post-file-write-memory.sh watch list mentions neither the legacy "
        "product-brain pattern nor */vault/*.md — org corpus writes would "
        "never be embedded at write time"
    )


# ---------------------------------------------------------------------------
# memory-reconcile.sh — the nightly netting walks the vault corpus + docs/
# (vault wave 2026-07-17: reconcile is UNLOCKED and lands first; the hook's
# matching patterns ride the germline ceremony patch)
# ---------------------------------------------------------------------------

def test_bash_syntax_memory_reconcile():
    _bash_n(RECONCILE_SH)


def test_bash_syntax_backfill_memory():
    _bash_n(BACKFILL_SH)


def test_reconcile_walks_the_vault_corpus():
    text = RECONCILE_SH.read_text()
    assert _on_a_live_line(r"CABINET_ROOT/vault", text), (
        "memory-reconcile.sh must walk $CABINET_ROOT/vault — the cabinet "
        "vault would otherwise drift out of cabinet_memory (and until the "
        "hook ceremony patch lands, reconcile is the ONLY vault coverage)"
    )
    assert _on_a_live_line(r"reconcile_file product_brain\b", text), (
        "vault corpus rows must keep source_type=product_brain — the DB "
        "row taxonomy predates the rename; changing it orphans every "
        "existing row's (source_type, source_id) upsert identity"
    )


def test_reconcile_walks_the_legacy_corpus_dir():
    text = RECONCILE_SH.read_text()
    assert _on_a_live_line(r"CABINET_ROOT/product-brain", text), (
        "memory-reconcile.sh must keep walking the legacy product-brain/ "
        "dir — un-migrated checkouts still hold their corpus there"
    )


def test_reconcile_walks_framework_docs():
    text = RECONCILE_SH.read_text()
    assert _on_a_live_line(r"CABINET_ROOT/docs", text), (
        "memory-reconcile.sh must walk $CABINET_ROOT/docs — the docs/ tree "
        "joined the memory index (vault wave 2026-07-17)"
    )
    assert _on_a_live_line(r"reconcile_file framework_doc\b", text), (
        "docs/**/*.md rows must land as source_type=framework_doc"
    )


def test_reconcile_snapshot_covers_the_new_types():
    """The hash-drift snapshot SELECT must include product_brain +
    framework_doc — otherwise every walked vault/docs file misses the
    ladder-1 hash compare and re-queues EVERY night (nightly re-embed
    churn, not netting)."""
    text = RECONCILE_SH.read_text()
    m = re.search(r"source_type IN \(([^)]*)\)", text, re.S)
    assert m, "memory-reconcile.sh lost its source_type IN (...) snapshot filter"
    for required in ("'product_brain'", "'framework_doc'"):
        assert required in m.group(1), (
            f"snapshot SELECT must include {required} — walked files of that "
            f"type would re-queue every night without hash comparison"
        )


def test_backfill_queues_vault_corpus_and_docs():
    text = BACKFILL_SH.read_text()
    assert _on_a_live_line(r"CABINET_ROOT/vault", text), (
        "backfill-memory.sh must seed the vault corpus"
    )
    assert _on_a_live_line(r"CABINET_ROOT/product-brain", text), (
        "backfill-memory.sh must keep seeding a legacy product-brain/ checkout"
    )
    assert _on_a_live_line(r"CABINET_ROOT/docs", text), (
        "backfill-memory.sh must seed the docs/ tree (framework_doc)"
    )
    assert _on_a_live_line(r"framework_doc", text), (
        "backfill-memory.sh docs rows must land as source_type=framework_doc"
    )


# ---------------------------------------------------------------------------
# Watch-list parity BY DESIGN — the hook⊆reconcile direction
# ---------------------------------------------------------------------------

# (hook live-line pattern, reconcile live-line pattern) — for every surface
# the HOOK watches, the nightly reconcile must carry the matching walk, so a
# missed hook fire is always netted. The reverse direction is deliberately
# open: reconcile may walk MORE than the hook (e.g. vault/ + docs/ before the
# germline ceremony lands the hook patterns; the schg hooks dir cannot ride a
# normal lane). shared/interfaces/captain-decisions.md is the one documented
# exception (entry-level ingest owns it — see the reconcile header).
_WATCH_PARITY = [
    (r"tech-radar\.md", r"tech-radar\.md"),
    (r"product-specs/\*\.md", r"product-specs"),
    (r"shared/backlog\.md", r"shared/backlog\.md"),
    (r"working-notes\.md", r"working-notes\.md"),
    (r"reflections/\*\.md", r"reflections"),
    (r"memory/skills/\*\.md", r"memory/skills"),
    (r"constitution-base\.md", r"constitution-base\.md"),
    (r"safety-boundaries-base\.md", r"safety-boundaries-base\.md"),
    (r"\*/product-brain/\*\.md", r"CABINET_ROOT/product-brain"),
    (r"\*/vault/\*\.md", r"CABINET_ROOT/vault"),          # post-ceremony
    (r"docs/\*\.md", r"CABINET_ROOT/docs"),               # post-ceremony
]


def test_every_hook_watch_surface_has_a_reconcile_walk():
    hook = PFWM_HOOK.read_text()
    reconcile = RECONCILE_SH.read_text()
    missing = []
    for hook_pat, rec_pat in _WATCH_PARITY:
        if _on_a_live_line(hook_pat, hook) and not _on_a_live_line(rec_pat, reconcile):
            missing.append((hook_pat, rec_pat))
    assert not missing, (
        "watch-list parity broken (hook⊆reconcile): these hook-watched "
        f"surfaces have no reconcile walk: {missing} — a missed hook fire "
        "for them would never be netted; extend memory-reconcile.sh in the "
        "same change that extends the hook"
    )


def test_captain_decisions_exception_stays_documented():
    """The ONE hook-watched surface reconcile deliberately skips must keep
    saying so — silence would read as drift, not design."""
    hook = PFWM_HOOK.read_text()
    reconcile = RECONCILE_SH.read_text()
    assert _on_a_live_line(r"captain-decisions\.md", hook)
    assert "DELIBERATE EXCEPTION" in reconcile and "captain-decisions.md" in reconcile, (
        "memory-reconcile.sh lost the documented captain-decisions.md "
        "exception note — the hook watches it, reconcile deliberately skips "
        "it (append-interface wave owns entry-level ingest)"
    )


# ---------------------------------------------------------------------------
# post-file-write-memory.sh — vault-wave patterns (these locks landed on
# master WITH the hook edit itself in the CG-30 landing commit — master-first;
# patches/germline-vault-hook-watch-2026-07-17.patch stays as the ceremony
# reference, and the LIVE schg inode syncs at the Captain checkout window)
# ---------------------------------------------------------------------------

def test_post_file_write_hook_watches_the_vault_pattern():
    text = PFWM_HOOK.read_text()
    assert _on_a_live_line(r"\*/vault/\*\.md", text), (
        "post-file-write-memory.sh must watch */vault/*.md — the cabinet "
        "vault (renamed from product-brain/) must embed at write time"
    )


def test_post_file_write_hook_watches_rooted_docs():
    text = PFWM_HOOK.read_text()
    assert _on_a_live_line(r'"\$\{CABINET_ROOT[^}"]*\}"/docs/\*\.md', text), (
        "post-file-write-memory.sh must watch the docs/ tree ROOTED under "
        "CABINET_ROOT (an unrooted */docs/*.md would ingest any foreign "
        "repo's docs an officer edits)"
    )
    assert _on_a_live_line(r"framework_doc", text), (
        "docs/ writes must land as source_type=framework_doc"
    )


def test_post_file_write_hook_keeps_the_legacy_corpus_alias():
    text = PFWM_HOOK.read_text()
    assert _on_a_live_line(r"\*/product-brain/\*\.md", text), (
        "the legacy */product-brain/*.md watch arm must stay until "
        "deliberately dropped — un-migrated checkouts and externally "
        "relocated corpora still use the old dir name"
    )
