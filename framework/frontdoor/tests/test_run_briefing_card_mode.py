"""Briefing-as-card (ONE-VOICE-RESET, 2026-07-11) — run_briefing card mode.

All seams mocked (no brain, no Redis, no network). The archive leg writes to
a tmp CABINET_ROOT so nothing touches the live instance/ tree. The invariant
under test is the wall-kill contract:

  * card mode archives the composed body (ACK only after the write) and
    sends ONE briefing card — never the chunked text wall;
  * the result's ONLY ``"sent"`` key is the CARD's, so the launchd wrapper's
    delivered-marker grep ('"sent": true') can never be satisfied by the
    archive leg;
  * the card headline carries counts, never item payload text (untrusted
    pipe content stays off the card surface);
  * knob off → the classic path is untouched (shape-identical result).
"""
import json

from framework.frontdoor import run_briefing as rb


def _no_digest():
    return {"digest": False, "skipped": "stubbed in test"}


def _syn_zero(*, hours, limit):
    return {"enqueued": 0, "ids": [], "sources": []}


def _two_items(**kw):
    return [
        {"id": "1", "source": "morning-brief", "kind": "pipe-dm", "ts": "t1",
         "urgency_tier": "batch", "payload": {"summary": "Overdue: chase EC connection details"}},
        {"id": "2", "source": "commitment-ledger", "kind": "pipe-prompt", "ts": "t2",
         "urgency_tier": "batch", "payload": {"summary": "Waiting on Morten Stagaard (due 2026-08-07)"}},
    ]


def test_card_mode_archives_body_and_sends_one_card(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    calls = {}

    def fake_card(headline):
        calls["headline"] = headline
        return {"status": "sent", "sent": True, "message_ids": [777]}

    def fake_ack(ids, *, stream_key=None):
        calls["acked"] = ids
        return len(ids)

    out = rb.run_briefing(
        enqueue_fn=_syn_zero, drain_fn=_two_items, pending_fn=lambda **kw: [],
        ack_fn=fake_ack, digest_fn=_no_digest,
        card_mode=True, card_send_fn=fake_card)

    # ONE card went out and the send leg reports THE CARD's delivery.
    assert out["send"]["mode"] == "briefing-card"
    assert out["send"]["sent"] is True
    assert out["send"]["card_message_ids"] == [777]
    assert out["send"]["gathered"] == 2

    # The composed body landed in the archive — content preserved as data...
    path = out["send"]["archive_path"]
    assert path and str(tmp_path) in path
    body = open(path, encoding="utf-8").read()
    assert "Overdue: chase EC connection details" in body
    assert "Waiting on Morten Stagaard" in body
    # ...and the items were ACKed only against that durable write.
    assert calls["acked"] == ["1", "2"]

    # The headline carries counts, NEVER item payload text.
    assert "2 updates" in calls["headline"]
    assert "Morten" not in calls["headline"]
    assert "EC connection" not in calls["headline"]


def test_card_mode_result_has_no_other_sent_true(tmp_path, monkeypatch):
    """Wrapper-grep honesty: when the CARD fails, no '"sent": true' appears
    anywhere in the result — the archive leg cannot stamp a delivered
    briefing."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))

    out = rb.run_briefing(
        enqueue_fn=_syn_zero, drain_fn=_two_items, pending_fn=lambda **kw: [],
        ack_fn=lambda ids, *, stream_key=None: len(ids), digest_fn=_no_digest,
        card_mode=True,
        card_send_fn=lambda headline: {"status": "error", "sent": False})

    assert out["send"]["sent"] is False
    # the archive still happened (content safe) and items were acked...
    assert out["send"]["archive_path"]
    assert out["send"]["acked"] == 2
    # ...but NOTHING in the serialized result can satisfy the delivered grep.
    assert '"sent": true' not in json.dumps(out, indent=2, default=str)


def test_card_mode_archive_failure_keeps_items_pending(tmp_path, monkeypatch):
    """A failed archive write returns sent=False from the seam, so
    run_send_path never ACKs — the content stays on the stream. The card
    headline says so honestly instead of claiming the notes were kept."""
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the root dir should be", encoding="utf-8")
    monkeypatch.setenv("CABINET_ROOT", str(blocker))  # mkdir under a file fails
    calls = {"acked": None, "headline": None}

    def fake_ack(ids, *, stream_key=None):
        calls["acked"] = ids
        return len(ids)

    def fake_card(headline):
        calls["headline"] = headline
        return {"status": "sent", "sent": True, "message_ids": [778]}

    out = rb.run_briefing(
        enqueue_fn=_syn_zero, drain_fn=_two_items, pending_fn=lambda **kw: [],
        ack_fn=fake_ack, digest_fn=_no_digest,
        card_mode=True, card_send_fn=fake_card)

    assert calls["acked"] is None                     # nothing ACKed
    assert out["send"]["archive_path"] is None
    assert out["send"]["acked"] == 0
    assert "stay queued" in calls["headline"]         # honest headline
    assert "kept on file" not in calls["headline"]


def test_card_mode_skips_needs_you_enqueue(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))

    def exploding_needs_you():
        raise AssertionError("needs-you must not be enqueued in card mode")

    out = rb.run_briefing(
        enqueue_fn=_syn_zero, drain_fn=lambda **kw: [], pending_fn=lambda **kw: [],
        ack_fn=lambda ids, *, stream_key=None: len(ids), digest_fn=_no_digest,
        needs_you_fn=exploding_needs_you,
        card_mode=True, card_send_fn=lambda h: {"status": "sent", "sent": True})

    assert out["needs_you"]["needs_you"] is False
    assert "briefing-card mode" in out["needs_you"]["skipped"]


def test_card_mode_acted_count_rides_headline(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    calls = {}

    out = rb.run_briefing(
        enqueue_fn=_syn_zero, drain_fn=_two_items, pending_fn=lambda **kw: [],
        ack_fn=lambda ids, *, stream_key=None: len(ids),
        digest_fn=lambda: {"digest": True, "acted": 3, "awaiting": 5},
        card_mode=True,
        card_send_fn=lambda h: calls.setdefault("headline", h) and
        {"status": "sent", "sent": True} or {"status": "sent", "sent": True})

    assert "3 things were done for you" in calls["headline"]
    assert "`undo <n>`" in calls["headline"]
    assert out["digest"]["acted"] == 3


def test_card_headline_is_plain_language(tmp_path, monkeypatch):
    """The headline obeys the plain-language law (Ruling B): zero banned
    org-vocabulary terms, in every branch of the copy."""
    from framework.attention import plain

    empty = rb._plain_headline({"drained": 0, "sent": False}, None)
    kept = rb._plain_headline({"drained": 7, "sent": True}, {"acted": 2})
    failed = rb._plain_headline({"drained": 7, "sent": False}, None)
    for text in (empty, kept, failed):
        assert plain.lint(text) == [], text


def test_classic_mode_is_unchanged(tmp_path, monkeypatch):
    """Knob off → the pre-reset result shape and the text send path, exactly
    as the existing test_run_briefing.py suite pins them."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    calls = {}

    def fake_send(text, *, http_post=None):
        calls["text"] = text
        return {"status": "sent", "sent": True}

    out = rb.run_briefing(
        enqueue_fn=_syn_zero, drain_fn=_two_items, pending_fn=lambda **kw: [],
        send_fn=fake_send, ack_fn=lambda ids, *, stream_key=None: len(ids),
        digest_fn=_no_digest, needs_you_fn=lambda: None,
        card_mode=False)

    assert "gather" not in out                       # classic shape
    assert out["send"]["sent"] is True               # the text wall path
    assert "Waiting on Morten Stagaard" in calls["text"]
