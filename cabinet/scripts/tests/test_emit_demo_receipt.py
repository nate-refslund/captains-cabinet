"""Tests for cabinet/scripts/emit-demo-receipt.sh (Perfect Cabinet Wave B).

The hatch seeds ONE explicitly-labeled DEMO receipt so the Captain sees
receipt anatomy in minute one. These tests pin the honesty contract
(tightened by the 2026-07-10 adversarial fix pass):

  * the row rides the REAL schema path (action_undo.new_row, re-validated
    via action_undo's own validator — never a hand-crafted dict) but is
    NEVER JOURNALED: the live undo journal stays untouched, so the germline
    acted-overlay consistency fence ("journal has rows in-window but the
    ledger returned nothing") can never be tripped by the demo, and no
    digest/sweeper/labeler over the journal can ever offer it as a real act;
  * demo: true, status executed, kind monday_task_create with the REAL
    registry action_type (task_create), a REAL 48h ttl_expires_at, and an
    inverse registered as op "none" (the receipt never claims an undo that
    is not registered);
  * the rendered file is HEADED by the exact DEMO label and lands next to
    the first-briefing file (instance/memory/);
  * re-runs are idempotent by construction (the file is the whole artifact);
    --dry-run writes nothing.

Hermetic: scratch CABINET_ROOT + CABINET_UNDO_DIR + CABINET_EVENT_LOG_DIR —
the live journal, the live ledger, and the live instance/ are never touched.

Run: python3.12 -m pytest cabinet/scripts/tests/test_emit_demo_receipt.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_EMIT = _SCRIPTS_DIR / "emit-demo-receipt.sh"

_LABEL = ("DEMO receipt — seeded at hatch so you can see the receipt anatomy; "
          "reply-to-undo works on real receipts only")
_PID = "demo-hatch-receipt"

# Re-validate the printed row with the REAL schema validator (the acceptance
# contract: schema-valid via action_undo's own validator, the same check
# journal_step runs before a real append), executed in a subprocess exactly as
# production imports it.
_VALIDATOR = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from framework.frontdoor import action_undo\n"
    "action_undo._validate_row(json.loads(sys.argv[2]))\n"
    "print('ROW_VALID')\n"
)

# The fence repro (the must_fix this file guards against regressing): a fresh
# box after hatch = empty ledger + whatever the demo left in the journal.
# load_acted's default-load consistency fence raises RuntimeError when the
# journal has in-window rows but the ledger is empty — the demo must leave the
# journal EMPTY so this never fires.
_FENCE = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from framework.attention import acted_overlay\n"
    "view = acted_overlay.load_acted(since='2000-01-01T00:00:00Z')\n"
    "assert isinstance(view, dict)\n"
    "print('FENCE_CLEAN')\n"
)


def _env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(tmp_path / "root")
    # Defensive: if the script ever regressed to journaling / ledger writes,
    # they would land here (and fail the assertions), never in the live dirs.
    env["CABINET_UNDO_DIR"] = str(tmp_path / "undo")
    env["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "ledger")
    return env


def _run(tmp_path: Path, *args: str):
    return subprocess.run(
        ["bash", str(_EMIT), *args],
        cwd=_REPO_ROOT, env=_env(tmp_path),
        capture_output=True, text=True, timeout=120,
    )


def _printed_row(stdout: str) -> dict:
    lines = [ln for ln in stdout.splitlines() if ln.startswith("DEMO_ROW=")]
    assert len(lines) == 1, stdout
    return json.loads(lines[0].split("=", 1)[1])


def _iso(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The seeded receipt file
# ---------------------------------------------------------------------------

def test_seeds_one_labeled_demo_receipt(tmp_path):
    p = _run(tmp_path)
    assert p.returncode == 0, p.stderr

    # machine-readable landing line (hatch.sh parses this)
    landing = [ln for ln in p.stdout.splitlines() if ln.startswith("DEMO_RECEIPT=")]
    assert len(landing) == 1, p.stdout
    receipt = Path(landing[0].split("=", 1)[1])
    assert receipt == tmp_path / "root" / "instance" / "memory" / "demo-receipt.md"
    assert receipt.is_file()

    body = receipt.read_text(encoding="utf-8")
    assert body.startswith(f"# {_LABEL}"), "receipt file must lead with the DEMO label"
    assert "demo: true" in body
    assert "NEVER journaled" in body               # the honesty line matches reality
    assert "Testburg" in body                      # synthetic vocabulary only
    assert "task_create" in body                   # the real registry action_type
    assert "Undo within 48h" in body               # the real renderer's undo line
    assert f"·{_PID}·" in body                     # the trusted pid marker, last
    assert "undo <n>" in body and "👍 <n>" in body and "never: <why>" in body
    assert "nothing real to reverse" in body

    # stdout carries the label too (the hatch step log shows it)
    assert _LABEL in p.stdout


# ---------------------------------------------------------------------------
# NEVER journaled — the must_fix contract (acted-overlay fence stays quiet)
# ---------------------------------------------------------------------------

def test_never_touches_the_undo_journal(tmp_path):
    assert _run(tmp_path).returncode == 0
    assert _run(tmp_path).returncode == 0          # twice — still nothing
    undo_dir = tmp_path / "undo"
    assert not undo_dir.exists(), "demo emit must never create the undo journal"
    assert not list(tmp_path.rglob("undo-journal-*.jsonl")), \
        "demo emit must never append a journal line anywhere"
    assert not (tmp_path / "ledger").exists(), \
        "demo emit must never write a consequence-ledger event"


def test_fresh_box_acted_overlay_fence_stays_quiet(tmp_path):
    """Post-hatch fresh-box repro: after the demo emit, journal AND ledger are
    both empty, so acted_overlay.load_acted (germline consistency fence) sees
    a legitimately empty world — no 'env drift?' RuntimeError, no act-first
    disarm on the first live acting-lane run."""
    assert _run(tmp_path).returncode == 0
    p = subprocess.run(
        [sys.executable, "-c", _FENCE, str(_REPO_ROOT)],
        env=_env(tmp_path), capture_output=True, text=True, timeout=60,
    )
    assert p.returncode == 0, f"fence tripped on a fresh box: {p.stderr}"
    assert "FENCE_CLEAN" in p.stdout


# ---------------------------------------------------------------------------
# The row itself — real constructor, real registry, real validator
# ---------------------------------------------------------------------------

def test_row_is_schema_valid_via_the_real_validator(tmp_path):
    p = _run(tmp_path, "--print-row")
    assert p.returncode == 0, p.stderr
    row = _printed_row(p.stdout)

    check = subprocess.run(
        [sys.executable, "-c", _VALIDATOR, str(_REPO_ROOT), json.dumps(row)],
        env=_env(tmp_path), capture_output=True, text=True, timeout=60,
    )
    assert check.returncode == 0, check.stderr
    assert "ROW_VALID" in check.stdout

    assert row["demo"] is True
    assert row["status"] == "executed" and row["executed_at"]
    assert row["kind"] == "monday_task_create"
    assert row["action_type"] == "task_create"     # resolved via the real registry
    assert row["inverse"]["op"] == "none"          # never claims an unregistered undo
    assert "demo" in row["inverse"]["args"]["reason"]
    # a REAL 48h undo window, computed by new_row from the row's own ts
    assert (_iso(row["ttl_expires_at"]) - _iso(row["ts"])).total_seconds() == 48 * 3600
    # honest synthetic content — Testburg only
    assert "Testburg" in row["subject"]
    assert row["content"]["notes"].startswith("cost: unattributed")


# ---------------------------------------------------------------------------
# Idempotency — the file is the whole artifact
# ---------------------------------------------------------------------------

def test_rerun_is_idempotent_file_only(tmp_path):
    assert _run(tmp_path).returncode == 0
    receipt = tmp_path / "root" / "instance" / "memory" / "demo-receipt.md"
    assert receipt.is_file()
    p = _run(tmp_path)                             # second run
    assert p.returncode == 0, p.stderr
    assert "re-rendered (idempotent re-run)" in p.stdout
    assert receipt.is_file()
    body = receipt.read_text(encoding="utf-8")
    assert body.startswith(f"# {_LABEL}")
    # still exactly one demo artifact, still no journal
    memory = tmp_path / "root" / "instance" / "memory"
    assert [f.name for f in sorted(memory.iterdir())] == ["demo-receipt.md"]
    assert not (tmp_path / "undo").exists()


def test_rerun_rerenders_a_deleted_receipt_file(tmp_path):
    assert _run(tmp_path).returncode == 0
    receipt = tmp_path / "root" / "instance" / "memory" / "demo-receipt.md"
    receipt.unlink()
    assert _run(tmp_path).returncode == 0
    assert receipt.is_file(), "missing receipt file must be re-rendered"


# ---------------------------------------------------------------------------
# --dry-run + flag discipline
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path):
    p = _run(tmp_path, "--dry-run")
    assert p.returncode == 0, p.stderr
    assert "nothing was written" in p.stdout
    assert "NEVER" in p.stdout                     # the plan states the no-journal contract
    assert not (tmp_path / "undo").exists()
    assert not (tmp_path / "root").exists()


def test_unknown_flag_exits_64(tmp_path):
    p = _run(tmp_path, "--bogus")
    assert p.returncode == 64
    assert "usage" in p.stderr
    assert not (tmp_path / "root").exists()
