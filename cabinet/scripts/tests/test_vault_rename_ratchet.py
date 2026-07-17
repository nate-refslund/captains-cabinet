"""Vault-rename completeness ratchet (vault wave, 2026-07-17).

Captain-ratified 2026-07-16: product-brain/ became the cabinet's default
VAULT (vault/). This ratchet pins the END STATE of that rename:

  * the rename actually happened — vault/README.md is tracked, no tracked
    path lives under product-brain/ anymore;
  * every REMAINING product-brain / product_brain mention in tracked files
    is a DELIBERATE one — a named back-compat seam (legacy env alias,
    legacy platform key, legacy in-repo dir walk, the deprecated
    framework.env.product_brain_dir() wrapper the schg germline lane still
    imports) or pinned history (docs/plans, docs/proposals, patches, the
    pseudonymized incident replay corpus). Everything else FAILS here.

The allowlist is SHRINK-ONLY: a third test asserts every allowlisted file
still exists AND still carries the token, so a cleaned-up file must be
pruned from the list in the same change (the list can never silently grow
stale) — and any NEW file mentioning product-brain reds the build with the
reason it must not.

Offline, hermetic-ish: one `git ls-files` subprocess (argv list, no shell —
CI runs from a git checkout; the _REAL_POPEN restore mirrors
test_bootstrap_memory_chain's guard against the Popen patch leak).

Run: python3 -m pytest cabinet/scripts/tests/test_vault_rename_ratchet.py -q
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Captured at import (collection) time — see test_bootstrap_memory_chain.py:
# a leaked FakePopen from test_library_mcp_client must not fail these tests.
_REAL_POPEN = subprocess.Popen

_REPO_ROOT = Path(__file__).resolve().parents[3]

TOKEN_RE = re.compile(r"product[-_]brain", re.IGNORECASE)

# Binary-ish payloads: not text surfaces; reading them for tokens is noise.
_SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".sqlite", ".db",
    ".pyc", ".icns",
}

# Pinned history — records of what was true when written; they keep their
# original references by design (same construction as docs-track-code-sweep's
# archived-set exclusion).
HISTORICAL_PREFIXES = (
    "docs/plans/",
    "docs/proposals/",
    "docs/launch/",
    "patches/",
    # FW-019 checkpoint-review artifacts: dated records of a batch as it was
    # reviewed (the vault wave's own reviews necessarily NAME the rename).
    "shared/interfaces/reviews/",
)

# The deliberate survivors: path -> why the token stays. SHRINK-ONLY.
ALLOWED = {
    # --- live back-compat seams -------------------------------------------
    "framework/env.py":
        "org_vault_dir(): legacy CABINET_PRODUCT_BRAIN_DIR env alias, legacy "
        "product_brain_dir platform key, legacy <root>/product-brain arm, and "
        "the deprecated product_brain_dir() wrapper",
    "framework/acting/run_action_lane.py":
        "schg germline — imports the deprecated wrapper; modernize at the "
        "next unlock window (see the 2026-07-17 vault hook-watch ceremony note)",
    "cabinet/scripts/hooks/post-file-write-memory.sh":
        "schg germline — keeps the legacy */product-brain/*.md watch arm; "
        "vault/docs patterns landed on master 2026-07-17 (CG-30; the live "
        "inode syncs at the Captain checkout window)",
    "cabinet/scripts/memory-reconcile.sh":
        "walks the legacy product-brain/ dir for un-migrated checkouts",
    "cabinet/scripts/backfill-memory.sh":
        "walks the legacy product-brain/ dir for un-migrated checkouts",
    "cabinet/scripts/generate-instance.py":
        "legacy product_brain_dir key suppression — a hand-edited legacy "
        "value must keep winning over a fresh org_vault_dir stamp",
    # --- tests that pin the back-compat matrix ----------------------------
    "framework/acting/tests/test_gather_corpus.py":
        "pins the legacy env alias / legacy key / legacy dir matrix",
    "framework/acting/tests/test_gather_via_source.py":
        "monkeypatches the germline lane's product_brain_dir symbol",
    "framework/sources/tests/test_org_decision_recall.py":
        "monkeypatches the germline lane's product_brain_dir symbol",
    "framework/attention/tests/test_p1_acceptance_replay.py":
        "pseudonymized 2026-07-07/08 incident replay corpus — refs are "
        "period data, never modernized",
    "cabinet/scripts/tests/test_bootstrap_memory_chain.py":
        "asserts the legacy watch/walk aliases stay until deliberately dropped",
    "cabinet/scripts/tests/test_generate_instance.py":
        "pins legacy-key stamping suppression",
    "cabinet/scripts/tests/test_cleanroom_org_instance.py":
        "docstring provenance: names the pre-rename key it superseded",
    "cabinet/scripts/tests/test_vault_rename_ratchet.py":
        "this ratchet",
    # --- library-retirement dual-root seams (same wave, landed after the
    # --- rename): the export must also serve un-migrated deployment roots
    # --- whose external corpus still carries the old dir name ------------
    ".gitignore":
        "library-archive ignore rules cover BOTH candidate roots — the "
        "DB-derived archive must never be committed from either tree shape",
    "cabinet/scripts/retire-library-export.py":
        "export target resolves <root>/vault/ first, legacy "
        "<root>/product-brain/ fallback for un-migrated deployment roots",
    "cabinet/scripts/tests/test_retire_library_export.py":
        "pins the vault-then-product-brain target resolution order",
    "cabinet/scripts/tests/test_library_retirement_ratchet.py":
        "pins the dual-root ignore rules + fallback contract",
    "docs/runbooks/library-retirement-2026-07-16.md":
        "documents the dual-root export target contract (living runbook, "
        "not archived history)",
    # --- docs that deliberately document the legacy aliases ----------------
    "vault/README.md":
        "documents the rename, the legacy aliases, and the ref-namespace call",
    "captains-cabinet-guide.md":
        "one formerly-named historical mention in section 6",
    "cabinet/runbooks/org-memory-day1.md":
        "documents the legacy aliases for migrating deployments",
    ".claude/skills/cabinet-init/SKILL.md":
        "documents the legacy key/env aliases the generator must not clobber",
}


def _tracked_files() -> list:
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "ls-files", "-z"],
            capture_output=True, timeout=120,
        )
    finally:
        subprocess.Popen = patched
    assert proc.returncode == 0, (
        f"git ls-files failed: {proc.stderr.decode(errors='replace')[:400]}"
    )
    return [p for p in proc.stdout.decode("utf-8", errors="replace").split("\0") if p]


def test_the_rename_actually_happened():
    files = set(_tracked_files())
    assert "vault/README.md" in files, (
        "vault/README.md is not tracked — the vault scaffold (formerly "
        "product-brain/) must ship in-repo"
    )
    strays = sorted(p for p in files if p.startswith("product-brain/"))
    assert not strays, (
        f"tracked paths still live under product-brain/: {strays} — the "
        f"rename must be complete (git mv, never a copy)"
    )


def test_no_undeclared_product_brain_references():
    offenders = {}
    for rel in _tracked_files():
        if rel.startswith(HISTORICAL_PREFIXES) or rel in ALLOWED:
            continue
        if Path(rel).suffix.lower() in _SKIP_SUFFIXES:
            continue
        p = _REPO_ROOT / rel
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if TOKEN_RE.search(text):
            lines = [i for i, line in enumerate(text.splitlines(), 1)
                     if TOKEN_RE.search(line)][:3]
            offenders[rel] = lines
    assert not offenders, (
        "product-brain references outside the declared back-compat seams / "
        f"pinned history: {offenders} — the corpus is the VAULT now "
        "(Captain-ratified 2026-07-16). Either finish the rename in that "
        "file or, if it is a genuine new back-compat seam, add it to ALLOWED "
        "with its reason (shrink-only list — expect review pushback)."
    )


def test_allowlist_is_shrink_only():
    """Every allowlisted file must still exist AND still carry the token —
    a file that got cleaned up or deleted must leave the list in the same
    change, so the list only ever shrinks toward zero."""
    files = set(_tracked_files())
    stale = []
    for rel in ALLOWED:
        if rel not in files:
            stale.append((rel, "no longer tracked"))
            continue
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        if not TOKEN_RE.search(text):
            stale.append((rel, "no longer mentions product-brain"))
    assert not stale, (
        f"stale ALLOWED entries (prune them — the list is shrink-only): {stale}"
    )
