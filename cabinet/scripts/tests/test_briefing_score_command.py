"""/score on the phone — the poller half of the briefing-value trial instrument.

The Captain's control must not require a terminal (captain-controls ruling,
2026-07-17), so ``/score 3`` is answered MECHANICALLY by the inbound poller
process, the same shape as ``/killswitch``. Pinned here:

  * routing is anchored — "/score" inside a sentence is conversation for the
    Chair, never a control command;
  * the score is DURABLE BEFORE the confirmation is sent (a confirmation the
    Captain can see must never outrun the row it claims was written);
  * every failure — library missing, disk unwritable, send refused — returns
    False so the caller relays his words instead of swallowing them;
  * the dispatch branch sits behind the captain gate and ahead of the generic
    captain-text relay, and falls through to that relay on failure.

Run: python3.12 -m pytest cabinet/scripts/tests/test_briefing_score_command.py -q
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"

_spec = importlib.util.spec_from_file_location(
    "officer_inbound_poller_score", POLLER)
poller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poller)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_BRIEFING_SCORES_DIR", str(tmp_path / "memory"))
    return tmp_path / "memory"


def _noop_log(*_a, **_k):
    pass


class _Post:
    """Records sendMessage calls; optionally refuses."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, method, payload):
        self.calls.append((method, payload))
        if self.fail:
            raise RuntimeError("telegram refused")
        return {"ok": True}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "/score 0", "/score 3", "/SCORE 2", "  /score 1  ",
    "/score@CabinetChairBot 3", "/score 3 acting on the VIES row",
])
def test_score_command_matches(text):
    assert poller.is_score_command(text) is True


@pytest.mark.parametrize("text", [
    "/score 4", "/score 32", "/score", "please /score 3 when you can",
    "the score is 3", "3", "", "/killswitch",
])
def test_score_command_does_not_match(text):
    """GUARD: anchoring + range. A false positive here EATS a real message."""
    assert poller.is_score_command(text) is False


def test_unavailable_library_never_eats_a_message(monkeypatch):
    """GUARD: the except in is_score_command. If the library cannot import,
    "/score 3" must relay to the Chair, not vanish."""
    monkeypatch.setattr(poller, "_briefing_score_lib",
                        lambda: (_ for _ in ()).throw(ImportError("gone")))
    assert poller.is_score_command("/score 3") is False


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def test_reply_records_then_confirms(_store):
    """GUARD: record-before-send ordering. The row must be on disk and the
    confirmation must quote the number that was written."""
    post = _Post()
    ok = poller.score_command_reply(api_post=post, chat_id=1234,
                                    text="/score 3 act on it", log=_noop_log)
    assert ok is True
    rows = (_store / "briefing-scores.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert row["score"] == 3
    assert row["source"] == "telegram"
    assert row["note"] == "act on it"
    method, payload = post.calls[0]
    assert method == "sendMessage"
    assert "Scored 3" in payload["text"]


def test_a_send_failure_still_kept_the_score(_store):
    """GUARD: record FIRST. Telegram refusing the confirmation must not cost
    the Captain his score — the row stays, the caller relays."""
    post = _Post(fail=True)
    ok = poller.score_command_reply(api_post=post, chat_id=1234,
                                    text="/score 2", log=_noop_log)
    assert ok is False                                    # → Chair relay
    rows = (_store / "briefing-scores.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["score"] == 2


def test_an_unwritable_store_falls_open_and_sends_nothing(monkeypatch):
    """GUARD: the except in score_command_reply. A write failure must NOT
    confirm a score that was never recorded."""
    post = _Post()
    lib = poller._briefing_score_lib()
    monkeypatch.setattr(lib, "record",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    ok = poller.score_command_reply(api_post=post, chat_id=1234,
                                    text="/score 3", log=_noop_log)
    assert ok is False
    assert post.calls == []                               # no false comfort


def test_a_non_command_is_refused_without_a_row(_store):
    post = _Post()
    ok = poller.score_command_reply(api_post=post, chat_id=1234,
                                    text="hello there", log=_noop_log)
    assert ok is False
    assert post.calls == []
    assert not (_store / "briefing-scores.jsonl").exists()


# ---------------------------------------------------------------------------
# The dispatch branch — structural pin (the branch is inside the poll loop,
# which needs a live Telegram; assert its shape instead of running it).
# ---------------------------------------------------------------------------

def test_dispatch_branch_is_captain_gated_and_falls_through():
    src = POLLER.read_text(encoding="utf-8")
    assert "elif frm == str(captain) and is_score_command(text):" in src, \
        "the /score branch must sit behind the captain gate"
    branch = src.split("and is_score_command(text):", 1)[1]
    branch = branch.split("elif frm == str(captain) and text:", 1)[0]
    assert "score_command_reply(" in branch
    assert "if not sent:" in branch and "deliver(text" in branch, \
        "a failed /score must relay to the Chair, never be swallowed"


def test_dispatch_branch_precedes_the_generic_captain_relay():
    """Ordering is the whole routing decision: after the generic branch the
    /score arm would be unreachable."""
    src = POLLER.read_text(encoding="utf-8")
    assert src.index("and is_score_command(text):") < \
        src.index("elif frm == str(captain) and text:")


def test_poller_owns_no_storage():
    """The poller is a door, not a store — recording is the library's
    contract. A second writer is how a ledger loses attribution."""
    src = POLLER.read_text(encoding="utf-8")
    assert "briefing-scores.jsonl" not in src
