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
  * the post-file-write memory hook watches the product-brain corpus so org
    knowledge written by officers is embedded as it lands.

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
# post-file-write-memory.sh — the hook watches the product-brain corpus
# ---------------------------------------------------------------------------

def test_post_file_write_hook_watches_product_brain():
    text = PFWM_HOOK.read_text()
    assert _on_a_live_line(r"product[-_]brain", text), (
        "post-file-write-memory.sh watch list must mention product-brain — "
        "org corpus writes would otherwise never be embedded (day-1 org "
        "knowledge stays unrecallable until the nightly reconcile)"
    )
