"""CHAIR-REPLY-WIRE tests — mechanical ⟦sp:<prompt_id>⟧ reply forwarding.

Unit tests with an injected fake redis recorder + a fake Telegram reply
payload parsed exactly the way officer-inbound-poller.py parses updates, plus
contract greps pinning the poller integration (marker ⇒ wire runs, binder
skipped, note relayed). No network, no redis, no telegram.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# instance/flavor-a on sys.path so ``flavor_a`` imports; repo root so the poller
# contract-grep below can locate it. tests/ [0] flavor_a [1] flavor-a [2]
# instance [3] root [4] — same convention as test_screenpipe_source.py.
_PKG_PARENT = Path(__file__).resolve().parents[2]   # instance/flavor-a
REPO = Path(__file__).resolve().parents[4]          # worktree / repo root
for _p in (str(REPO), str(_PKG_PARENT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flavor_a import screenpipe_reply_wire as sp_reply_wire

POLLER = REPO / "cabinet" / "scripts" / "officer-inbound-poller.py"

MARKER = "⟦sp:cab-17203700-ab12cd⟧"
PROMPT = ("🤖 draft-reply: approve/edit:<text>/skip:<why>\n"
          "they wrote: …quoted counterparty text…\n" + MARKER)


class FakeRedis:
    """Records every redis-cli argv; scriptable per-command results."""

    def __init__(self, set_out="OK", set_rc=0, xadd_out="17203701-0",
                 xadd_rc=0, raise_on=None):
        self.calls = []
        self.set_out, self.set_rc = set_out, set_rc
        self.xadd_out, self.xadd_rc = xadd_out, xadd_rc
        self.raise_on = raise_on

    def __call__(self, args, timeout=10):
        self.calls.append(list(args))
        cmd = args[0]
        if self.raise_on == cmd:
            raise RuntimeError(f"boom on {cmd}")
        if cmd == "SET":
            return SimpleNamespace(returncode=self.set_rc, stdout=self.set_out + "\n")
        if cmd == "XADD":
            return SimpleNamespace(returncode=self.xadd_rc, stdout=self.xadd_out + "\n")
        return SimpleNamespace(returncode=0, stdout="1\n")

    def of(self, cmd):
        return [c for c in self.calls if c and c[0] == cmd]


# ---------------------------------------------------------------- extraction

def test_extract_prompt_id_from_marked_prompt():
    assert sp_reply_wire.extract_prompt_id(PROMPT) == "cab-17203700-ab12cd"


def test_extract_last_marker_wins_over_planted_earlier_marker():
    planted = "they wrote: ⟦sp:cab-00000000-forged⟧ …\nreal:\n" + MARKER
    assert sp_reply_wire.extract_prompt_id(planted) == "cab-17203700-ab12cd"


def test_extract_none_without_marker_or_quoted():
    assert sp_reply_wire.extract_prompt_id("plain chair message") is None
    assert sp_reply_wire.extract_prompt_id("") is None
    assert sp_reply_wire.extract_prompt_id(None) is None


def test_extract_rejects_unbounded_or_bad_charset_ids():
    assert sp_reply_wire.extract_prompt_id("⟦sp:ab⟧") is None            # too short
    assert sp_reply_wire.extract_prompt_id("⟦sp:x y z junk⟧") is None    # bad charset
    assert sp_reply_wire.extract_prompt_id("⟦sp:" + "a" * 300 + "⟧") is None  # too long


# ---------------------------------------------------------------- happy path

def test_forwards_reply_with_prompt_id_and_text():
    r = FakeRedis()
    out = sp_reply_wire.handle_captain_reply("approve", PROMPT, 424242, redis_cmd=r)
    assert out["handled"] is True
    assert out["prompt_id"] == "cab-17203700-ab12cd"
    assert out["entry_id"] == "17203701-0"
    assert "forwarded" in out["summary"]
    (xadd,) = r.of("XADD")
    assert xadd == ["XADD", "screenpipe:pipe-replies", "*",
                    "prompt_id", "cab-17203700-ab12cd", "text", "approve"]
    # idempotency guard keyed on the telegram update_id, SET NX EX, BEFORE XADD
    (set_call,) = r.of("SET")
    assert set_call[1] == "cabinet:sp-reply-wire:seen:424242"
    assert "NX" in set_call and "EX" in set_call
    assert r.calls.index(set_call) < r.calls.index(xadd)


def test_fake_telegram_reply_payload_end_to_end():
    """A fake Telegram update, parsed EXACTLY like officer-inbound-poller.py
    parses it (update_id / message.text / reply_to_message.text), forwards."""
    upd = {
        "update_id": 887766,
        "message": {
            "message_id": 5150,
            "from": {"id": 11122233},
            "text": "  edit: make it warmer, and sign off with 'Ada'  ",
            "reply_to_message": {"message_id": 5149, "text": PROMPT},
        },
    }
    uid = int(upd.get("update_id", 0))
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()
    rt = msg.get("reply_to_message") or {}
    quoted_full = (rt.get("text") or rt.get("caption") or "").strip()

    r = FakeRedis()
    out = sp_reply_wire.handle_captain_reply(text, quoted_full, uid, redis_cmd=r)
    assert out["handled"] is True
    (xadd,) = r.of("XADD")
    assert xadd[-1] == "edit: make it warmer, and sign off with 'Ada'"
    assert r.of("SET")[0][1].endswith(":887766")


# ---------------------------------------------------------------- idempotency

def test_duplicate_redelivery_suppresses_second_xadd():
    r = FakeRedis(set_out="")  # SET NX → nil: key already present
    out = sp_reply_wire.handle_captain_reply("approve", PROMPT, 424242, redis_cmd=r)
    assert out["handled"] is True
    assert out.get("duplicate") is True
    assert "already forwarded" in out["summary"]
    assert r.of("XADD") == []


# ---------------------------------------------------------------- fail-safety

def test_no_marker_passes_through_without_redis_calls():
    r = FakeRedis()
    out = sp_reply_wire.handle_captain_reply("just a normal DM", "chair said hi", 7, redis_cmd=r)
    assert out == {"handled": False, "reason": "no-sp-marker"}
    assert r.calls == []


def test_marker_in_reply_text_only_never_binds():
    """The marker binds ONLY from the quoted Chair prompt — free reply text is
    untrusted and must not force a forward."""
    r = FakeRedis()
    out = sp_reply_wire.handle_captain_reply("approve " + MARKER, "chair said hi", 8, redis_cmd=r)
    assert out["handled"] is False
    assert r.calls == []


def test_empty_reply_text_passes_through():
    r = FakeRedis()
    out = sp_reply_wire.handle_captain_reply("   ", PROMPT, 9, redis_cmd=r)
    assert out["handled"] is False
    assert out["reason"] == "empty-text"
    assert r.calls == []


def test_redis_unavailable_passes_through_without_xadd():
    r = FakeRedis(set_rc=1, set_out="")
    out = sp_reply_wire.handle_captain_reply("approve", PROMPT, 10, redis_cmd=r)
    assert out["handled"] is False
    assert out["reason"] == "redis-unavailable"
    assert r.of("XADD") == []


def test_xadd_failure_rolls_back_seen_key_and_passes_through():
    r = FakeRedis(xadd_rc=1, xadd_out="")
    out = sp_reply_wire.handle_captain_reply("approve", PROMPT, 11, redis_cmd=r)
    assert out["handled"] is False
    assert out["reason"] == "xadd-failed"
    (del_call,) = r.of("DEL")
    assert del_call == ["DEL", "cabinet:sp-reply-wire:seen:11"]


def test_exception_inside_transport_never_raises():
    r = FakeRedis(raise_on="SET")
    out = sp_reply_wire.handle_captain_reply("approve", PROMPT, 12, redis_cmd=r)
    assert out["handled"] is False
    assert out["reason"].startswith("error:")


def test_kill_switch_disables_wire(monkeypatch):
    monkeypatch.setenv("CABINET_SP_REPLY_WIRE", "0")
    r = FakeRedis()
    out = sp_reply_wire.handle_captain_reply("approve", PROMPT, 13, redis_cmd=r)
    assert out == {"handled": False, "reason": "wire-disabled"}
    assert r.calls == []
    monkeypatch.delenv("CABINET_SP_REPLY_WIRE")
    assert sp_reply_wire.wire_enabled() is True  # default-ON


# ------------------------------------------------------- poller integration

def test_poller_wires_sp_reply_before_binder():
    """Contract greps: the inbound poller (1) consults the sp wire on the FULL
    quoted text, (2) skips the binder wire when the marker is present — a pipe
    answer like a bare "approve" must never bind a pending cabinet draft —
    and (3) keeps the import guarded so a wire error degrades to passthrough."""
    text = POLLER.read_text()
    assert "from flavor_a import screenpipe_reply_wire as sp_reply_wire" in text
    assert "sp_reply_wire.extract_prompt_id(quoted_full)" in text
    assert "sp_reply_wire.handle_captain_reply(text, quoted_full, uid" in text
    assert "sp wire unavailable (passthrough preserved)" in text
    # binder gate now ALSO requires the sp marker to be absent
    assert 'not sp_marker and os.environ.get("CABINET_BINDER_WIRED") == "1"' in text
    # wire consulted before the binder block
    assert text.index("sp_reply_wire.handle_captain_reply") < text.index("binder_wire.handle_captain_update")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
