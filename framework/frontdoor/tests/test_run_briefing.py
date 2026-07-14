"""run_briefing — enqueues a synthesis, then runs the send path. All seams mocked
(no brain, no Redis, no network). Every call pins ``card_mode=False``: these tests
are the CLASSIC text-path contract, and the briefing-card knob is deployment
data (instance/config/comms-surface.yml) that must not leak into a hermetic
suite. Card mode has its own suite (test_run_briefing_card_mode.py).

The briefing runs the send path with ``recover_pending=True`` (the fix for the
single-voice comms-awareness gap), so every test mocks ``pending_fn`` too — else
the real ``intake.drain_pending`` would reach Redis. ``pending_fn`` returns the
items surface.py left delivered-but-unacked in the PEL for the briefing to clear.
"""
from framework.frontdoor import run_briefing as rb


def _no_digest():
    """A stub for the TI-5 digest seam — these tests exercise the synthesis/send
    plumbing; the digest leg has its own tests (test_tell_digest.py + the
    dedicated riders below). Without a stub the DEFAULT would gather from the
    real journal/ledger and write real Redis."""
    return {"digest": False, "skipped": "stubbed in test"}


def test_enqueues_then_sends_unified():
    calls = {}

    def fake_enqueue(*, hours, limit):
        calls["enqueue_kw"] = (hours, limit)
        return {"enqueued": 2, "ids": ["1", "2"], "sources": ["awaiting-reply"]}

    def fake_drain(*, since=None, stream_key=None, count=100, consumer="chair"):
        return [
            {"id": "1", "source": "awaiting-reply", "kind": "thread", "ts": "t1",
             "urgency_tier": "batch", "payload": {"summary": "Dana awaits reply"}},
            {"id": "2", "source": "awaiting-reply", "kind": "thread", "ts": "t2",
             "urgency_tier": "batch", "payload": {"summary": "Sam awaits reply"}},
        ]

    def fake_send(text, *, http_post=None):
        calls["text"] = text
        return {"status": "sent", "sent": True}

    def fake_ack(ids, *, stream_key=None):
        calls["acked"] = ids
        return len(ids)

    out = rb.run_briefing(enqueue_fn=fake_enqueue, send_fn=fake_send,
                          drain_fn=fake_drain, ack_fn=fake_ack,
                          pending_fn=lambda **kw: [], digest_fn=_no_digest, card_mode=False)

    assert out["synthesis"]["enqueued"] == 2
    assert out["send"]["sent"] is True
    # the two synthesis items are woven into the ONE sent message
    assert "Dana awaits reply" in calls["text"]
    assert "Sam awaits reply" in calls["text"]
    # acked only after the confirmed send
    assert calls["acked"] == ["1", "2"]


def test_nothing_to_send_is_safe():
    out = rb.run_briefing(
        enqueue_fn=lambda *, hours, limit: {"enqueued": 0, "ids": [], "sources": []},
        drain_fn=lambda **kw: [],
        send_fn=lambda text, *, http_post=None: {"status": "sent", "sent": True},
        ack_fn=lambda ids, *, stream_key=None: len(ids),
        pending_fn=lambda **kw: [],
        digest_fn=_no_digest,
        card_mode=False,
    )
    assert out["send"]["drained"] == 0
    assert out["send"]["sent"] is False  # empty compose → nothing sent


def test_briefing_recovers_pending_backlog_left_by_surface():
    """The gap fix: a batch/fyi item surface.py delivered-but-left-pending (e.g. a
    comms-officer relevant-no-reply FYI) is recovered + sent by the briefing even
    when the fresh ``>`` drain is empty (surface.py already consumed it)."""
    calls = {}

    # The fresh ">" drain returns NOTHING — surface.py already delivered everything
    # into the PEL. The ONLY way these items reach the Captain is pending recovery.
    def fake_drain(**kw):
        return []

    def fake_pending(*, stream_key=None, consumer="chair"):
        return [
            {"id": "p1", "source": "comms-officer", "kind": "fyi", "ts": "t1",
             "urgency_tier": "batch",
             "payload": {"summary": "Morgan messaged on Teams — no reply needed, FYI"}},
            {"id": "p2", "source": "comms-officer", "kind": "fyi", "ts": "t2",
             "urgency_tier": "fyi",
             "payload": {"summary": "Vendor DPA escalation update"}},
        ]

    def fake_send(text, *, http_post=None):
        calls["text"] = text
        return {"status": "sent", "sent": True}

    def fake_ack(ids, *, stream_key=None):
        calls["acked"] = ids
        return len(ids)

    out = rb.run_briefing(
        enqueue_fn=lambda *, hours, limit: {"enqueued": 0, "ids": [], "sources": []},
        drain_fn=fake_drain, pending_fn=fake_pending,
        send_fn=fake_send, ack_fn=fake_ack, digest_fn=_no_digest, card_mode=False)

    # Both pending (comms-officer) items are recovered, composed into ONE message,
    # and surfaced to the Captain — the relevant-no-reply case no longer vanishes.
    assert out["send"]["recovered"] == 2
    assert out["send"]["drained"] == 2
    assert out["send"]["sent"] is True
    assert "Morgan messaged on Teams" in calls["text"]
    assert "Vendor DPA escalation update" in calls["text"]
    # acked only after the confirmed send, covering the recovered ids
    assert set(calls["acked"]) == {"p1", "p2"}


def test_briefing_dedupes_item_both_pending_and_fresh():
    """An item that is BOTH in the PEL and freshly delivered is composed + acked
    exactly once (recovery prepends, fresh follows, dedup by id)."""
    calls = {}

    def fake_pending(**kw):
        return [{"id": "dup", "source": "comms-officer", "kind": "fyi", "ts": "t1",
                 "urgency_tier": "batch", "payload": {"summary": "only once"}}]

    def fake_drain(**kw):
        return [{"id": "dup", "source": "comms-officer", "kind": "fyi", "ts": "t1",
                 "urgency_tier": "batch", "payload": {"summary": "only once"}}]

    def fake_send(text, *, http_post=None):
        calls["text"] = text
        return {"status": "sent", "sent": True}

    out = rb.run_briefing(
        enqueue_fn=lambda *, hours, limit: {"enqueued": 0, "ids": [], "sources": []},
        drain_fn=fake_drain, pending_fn=fake_pending,
        send_fn=fake_send, ack_fn=lambda ids, *, stream_key=None: len(ids),
        digest_fn=_no_digest, card_mode=False)

    assert out["send"]["drained"] == 1          # deduped
    assert out["send"]["item_ids"] == ["dup"]   # single id
    assert calls["text"].count("only once") == 1


# --- TI-5: the act-then-tell digest rides the twice-daily briefing -------------

def test_digest_enqueued_before_send_and_rides_briefing():
    """The digest leg runs on the briefing path (AM and PM alike): its intake
    item is enqueued BEFORE the send drain so THIS briefing composes it in."""
    calls = {"order": []}
    digest_item = {
        "id": "d1", "source": "tell-digest", "kind": "digest", "ts": "t3",
        "urgency_tier": "batch",
        "payload": {"summary": "🗒 Act-then-tell digest\n\n✅ ACTED (1)\n"
                               " 3. Created task\n      undo: `undo 3` (47h left)"},
    }

    def fake_digest():
        calls["order"].append("digest")
        return {"digest": True, "enqueued": "d1", "acted": 1}

    def fake_drain(**kw):
        calls["order"].append("drain")
        return [digest_item]

    def fake_send(text, *, http_post=None):
        calls["text"] = text
        return {"status": "sent", "sent": True}

    out = rb.run_briefing(
        enqueue_fn=lambda *, hours, limit: {"enqueued": 0, "ids": [], "sources": []},
        drain_fn=fake_drain, pending_fn=lambda **kw: [],
        send_fn=fake_send, ack_fn=lambda ids, *, stream_key=None: len(ids),
        digest_fn=fake_digest, card_mode=False)

    assert calls["order"] == ["digest", "drain"]   # enqueue precedes the drain
    assert out["digest"] == {"digest": True, "enqueued": "d1", "acted": 1}
    # the digest text (with its undo handle) reaches the ONE sent message
    assert "✅ ACTED (1)" in calls["text"]
    assert "`undo 3`" in calls["text"]


def test_digest_failure_never_blocks_briefing():
    def broken_digest():
        raise RuntimeError("journal unreadable")

    out = rb.run_briefing(
        enqueue_fn=lambda *, hours, limit: {"enqueued": 0, "ids": [], "sources": []},
        drain_fn=lambda **kw: [
            {"id": "1", "source": "awaiting-reply", "kind": "thread", "ts": "t1",
             "urgency_tier": "batch", "payload": {"summary": "Dana awaits reply"}}],
        pending_fn=lambda **kw: [],
        send_fn=lambda text, *, http_post=None: {"status": "sent", "sent": True},
        ack_fn=lambda ids, *, stream_key=None: len(ids),
        digest_fn=broken_digest, card_mode=False)

    assert out["digest"]["digest"] is False
    assert "journal unreadable" in out["digest"]["error"]
    assert out["send"]["sent"] is True             # the briefing still went out
