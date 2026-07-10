"""run_briefing --local-render — the LOCAL-FIRST genesis receipt.

Hermetic: CABINET_ROOT is pointed at tmp_path (genesis.cabinet_root honors the
env), genesis items are injected, and every Redis/send seam is a tripwire that
raises if touched — local render must never reach the intake or channel.py
(a scratch-instance drain would consume the LIVE consumer-group's items).
"""
from datetime import datetime, timezone

from framework.frontdoor import run_briefing as rb
from framework.onboarding.genesis import FIRST_BRIEFING_DIR_REL

_CARD = {
    "source": "onboarding-genesis", "kind": "outcome-proposal",
    "ts": "2026-07-10T00:00:00Z", "urgency_tier": "batch",
    "payload": {"summary": "📜 Proposed outcome: First verifiable improvement\n"
                           "WHAT: one shipped change\nWHY: you staked the lane\n"
                           "PROOF-expected: closed task + receipt\n"
                           "Status: draft — propose-only, captain_ratified: false"},
    "context": {"why": "org-proposed at genesis (ONBOARD-1)"},
}
_BRIEF = {
    "source": "onboarding-genesis", "kind": "genesis-brief",
    "ts": "2026-07-10T00:00:01Z", "urgency_tier": "fyi",
    "payload": {"summary": "📚 research brief queued — will be produced when "
                           "officers wake"},
    "context": {"why": "ONBOARD-2 honest IOU"},
}


def _boom(*a, **kw):
    raise AssertionError("local render must not touch Redis/send seams")


def test_local_render_writes_receipt_and_never_sends(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))

    out = rb.run_briefing(local_render=True,
                          genesis_fn=lambda: [_CARD, _BRIEF],
                          # every non-local seam is a tripwire:
                          enqueue_fn=_boom, send_fn=_boom, drain_fn=_boom,
                          ack_fn=_boom, pending_fn=_boom, recap_fn=_boom,
                          digest_fn=_boom)

    send = out["send"]
    assert send["local_render"] is True
    assert send["sent"] is False and send["send"] is None
    assert send["drained"] == 2

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = tmp_path / FIRST_BRIEFING_DIR_REL / f"first-briefing-{date}.md"
    assert str(path) == send["receipt_path"]
    body = path.read_text()
    assert "LOCAL-FIRST receipt" in body
    assert "Proposed outcome: First verifiable improvement" in body
    assert "research brief queued" in body
    assert "propose-only" in body
    # the synthesis/recap/digest legs were skipped, not attempted
    assert "skipped" in out["synthesis"] and "skipped" in out["digest"]
    assert out["recap"] is None


def test_local_render_honest_empty_still_writes_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    out = rb.run_briefing(local_render=True, genesis_fn=lambda: [])
    send = out["send"]
    assert send["drained"] == 0 and send["sent"] is False
    body = (tmp_path / FIRST_BRIEFING_DIR_REL).glob("first-briefing-*.md")
    text = next(iter(body)).read_text()
    assert "honest empty" in text            # says so plainly, invents nothing


def test_local_render_composes_all_cards_uncapped(tmp_path, monkeypatch):
    """The first briefing shows EVERY proposed card (no per-tier cap) — a
    2-4 card genesis proposal must never fold into a roll-up line."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    cards = []
    for i in range(4):
        c = {**_CARD, "payload": {"summary":
             _CARD["payload"]["summary"].replace("First verifiable",
                                                 f"Card number {i} verifiable")}}
        cards.append(c)
    out = rb.run_briefing(local_render=True, genesis_fn=lambda: cards)
    for i in range(4):
        assert f"Card number {i} verifiable" in out["send"]["text"]


def test_normal_path_unchanged_by_new_kwargs():
    """local_render defaults False: the existing enqueue→drain→send wiring runs
    exactly as before (regression guard for the additive signature)."""
    calls = {}

    def fake_send(text, *, http_post=None):
        calls["text"] = text
        return {"status": "sent", "sent": True}

    out = rb.run_briefing(
        enqueue_fn=lambda *, hours, limit: {"enqueued": 1, "ids": ["1"],
                                            "sources": ["awaiting-reply"]},
        drain_fn=lambda **kw: [
            {"id": "1", "source": "awaiting-reply", "kind": "thread", "ts": "t1",
             "urgency_tier": "batch", "payload": {"summary": "Dana awaits reply"}}],
        pending_fn=lambda **kw: [],
        send_fn=fake_send,
        ack_fn=lambda ids, *, stream_key=None: len(ids),
        digest_fn=lambda: {"digest": False, "skipped": "stubbed in test"})

    assert out["send"]["sent"] is True
    assert "Dana awaits reply" in calls["text"]
    assert "local_render" not in out["send"]      # normal result shape untouched


def test_parse_args_zero_arg_default_matches_wrapper_call():
    args = rb._parse_args([])
    assert args.now is False and args.local_render is False
    both = rb._parse_args(["--now", "--local-render"])
    assert both.now is True and both.local_render is True
