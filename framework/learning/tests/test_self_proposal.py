"""Tests for the MCP/plugin self-proposal (prepare + surface).

Non-negotiable properties under test:
  1. NEVER writes mcp-scope.yml — compute_scope_diff is pure read; the module
     has no file-write path. (We assert the scope file is byte-identical after.)
  2. The computed diff is the EXACT line(s) to add, against the real file shape.
  3. Ceiling touches force captain_required + a ceiling flag in the card.
  4. Surfacing is best-effort: an enqueue/emit failure never raises; the
     proposal dict is still returned.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.learning.self_proposal import (  # noqa: E402
    compute_scope_diff, prepare_mcp_proposal, render_proposal, _ceiling_touches,
)
from framework.learning.capability_gaps import HARD_CEILING_TOUCHES  # noqa: E402


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    # Route emit() to a tmp log; never a real store/db.
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.setenv("CABINET_PRODUCT_SLUG", "testprod")
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _write_scope(tmp_path, body: str) -> Path:
    root = tmp_path / "cab"
    (root / "cabinet").mkdir(parents=True)
    p = root / "cabinet" / "mcp-scope.yml"
    p.write_text(body)
    return root


_SCOPE_BODY = """cabinet: main
agents:
  cos:
    mcps: [notion, library, telegram, brain]
    rationale: coordination
  bakery-ceo:
    mcps: [neon, vercel, brain]
"""


# --------------------------------------------------------------------------
# 1 + 2. compute_scope_diff is read-only + exact.
# --------------------------------------------------------------------------

def test_scope_diff_is_exact_and_readonly(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)
    scope_file = root / "cabinet" / "mcp-scope.yml"
    before = scope_file.read_bytes()

    diff = compute_scope_diff("make", ["cos"], cabinet_root=root)

    # exactness: it names cos, shows current 4 + make.
    assert diff["needed"] is True
    assert diff["officers_missing"] == ["cos"]
    assert "make" in diff["diff_text"]
    assert "notion, library, telegram, brain, make" in diff["diff_text"]
    assert diff["scope_readable"] is True
    # read-only: the file is untouched.
    assert scope_file.read_bytes() == before


def test_scope_diff_already_in_scope(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)
    diff = compute_scope_diff("brain", ["cos"], cabinet_root=root)
    assert diff["needed"] is False
    assert "already in scope" in diff["diff_text"]


def test_scope_diff_multiple_officers_partial(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)
    # brain present for both; make missing for both -> only make surfaces.
    diff = compute_scope_diff("make", ["cos", "bakery-ceo"], cabinet_root=root)
    assert set(diff["officers_missing"]) == {"cos", "bakery-ceo"}


def test_scope_diff_unreadable_degrades_not_silent(tmp_path):
    # No scope file at all -> generic grant instruction, needed=True (never a
    # silent "no change").
    root = tmp_path / "empty"
    (root).mkdir()
    diff = compute_scope_diff("make", ["cos"], cabinet_root=root)
    assert diff["needed"] is True
    assert diff["scope_readable"] is False
    assert "make" in diff["diff_text"]


# --------------------------------------------------------------------------
# 3. Ceiling touches.
# --------------------------------------------------------------------------

def test_ceiling_inferred_from_text():
    # a write-capable / payment MCP description should infer a ceiling touch.
    touches = _ceiling_touches("stripe-billing", "charge customers and bill", "", None)
    assert "spending" in touches


def test_declared_ceiling_honored():
    touches = _ceiling_touches("custcommitting", "does stuff", "", ["network_write"])
    assert "network_write" in touches
    assert set(touches) <= HARD_CEILING_TOUCHES


def test_no_ceiling_for_readonly_mcp():
    touches = _ceiling_touches("make", "read Make scenarios", "listed rows", None)
    assert touches == []


def test_prepare_flags_ceiling_in_card(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)
    enq = []
    prop = prepare_mcp_proposal(
        "stripe", officers=["cos"],
        why="bill customers and charge for subscriptions",
        test_evidence="created a test charge in sandbox",
        touches=["spending"],
        cabinet_root=root,
        enqueue_fn=lambda item: enq.append(item) or "id-1",
        emit_fn=lambda *a, **k: None,
    )
    assert prop["captain_required"] is True
    assert "spending" in prop["ceiling"]
    assert "Captain-required" in prop["summary"]
    # the card was enqueued with a ping/batch tier + a summary.
    assert enq and enq[0]["payload"]["summary"]


# --------------------------------------------------------------------------
# 4. Surfacing is best-effort; the card shape is correct.
# --------------------------------------------------------------------------

def test_prepare_enqueues_canonical_item(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)
    captured = {}

    def fake_enqueue(item):
        captured.update(item)
        return "stream-1"

    prop = prepare_mcp_proposal(
        "make", officers=["cos"],
        why="Teams flow needs Make",
        test_evidence="read modules return rows",
        cabinet_root=root,
        enqueue_fn=fake_enqueue,
        emit_fn=lambda *a, **k: None,
    )
    assert prop["enqueued_id"] == "stream-1"
    assert captured["source"] == "self-proposal"
    assert captured["kind"] == "mcp-proposal"
    assert captured["urgency_tier"] == "batch"
    assert "summary" in captured["payload"]
    assert captured["payload"]["server"] == "make"


def test_enqueue_failure_does_not_raise(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)

    def boom(item):
        raise RuntimeError("redis down")

    prop = prepare_mcp_proposal(
        "make", officers=["cos"], why="x", test_evidence="y",
        cabinet_root=root, enqueue_fn=boom, emit_fn=lambda *a, **k: None,
    )
    # degrades: enqueued_id None, proposal still returned.
    assert prop["enqueued_id"] is None
    assert prop["server"] == "make"


def test_emit_failure_does_not_raise(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)

    def boom(*a, **k):
        raise RuntimeError("event store down")

    prop = prepare_mcp_proposal(
        "make", officers=["cos"], why="x", test_evidence="y",
        cabinet_root=root, enqueue_fn=lambda i: "id", emit_fn=boom,
    )
    assert prop["server"] == "make"


def test_empty_server_rejected(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)
    with pytest.raises(ValueError):
        prepare_mcp_proposal("  ", officers=["cos"], why="x", test_evidence="y",
                             cabinet_root=root, enqueue_fn=lambda i: "id",
                             emit_fn=lambda *a, **k: None)


def test_invalid_urgency_falls_back_to_batch(tmp_path):
    root = _write_scope(tmp_path, _SCOPE_BODY)
    prop = prepare_mcp_proposal(
        "make", officers=["cos"], why="x", test_evidence="y",
        urgency_tier="whenever", cabinet_root=root,
        enqueue_fn=lambda i: "id", emit_fn=lambda *a, **k: None,
    )
    assert prop["urgency_tier"] == "batch"


def test_render_includes_account_step_when_present():
    diff = {"needed": True, "diff_text": "add make", "officers_missing": ["cos"]}
    body = render_proposal(
        server="make", why="why", scope_diff=diff,
        test_evidence="tested", account_step="create a Make account + API key",
        ceiling=[], kind="mcp",
    )
    assert "create a Make account + API key" in body
    assert "does not self-edit" in body


def test_audit_event_emitted_to_log(tmp_path, monkeypatch):
    # Use the REAL emit (routed to tmp log by the autouse fixture) to prove an
    # audit row is written.
    root = _write_scope(tmp_path, _SCOPE_BODY)
    prepare_mcp_proposal(
        "make", officers=["cos"], why="x", test_evidence="y",
        cabinet_root=root, enqueue_fn=lambda i: "id",  # default emit_fn -> real emit
    )
    log_dir = Path(__import__("os").environ["CABINET_EVENT_LOG_DIR"])
    rows = list(log_dir.rglob("*.jsonl"))
    assert rows, "expected an event log file"
    text = "\n".join(p.read_text() for p in rows)
    assert "self_proposal_prepared" in text
