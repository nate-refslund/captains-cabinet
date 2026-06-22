"""run_briefing — enqueues a synthesis, then runs the send path. All seams mocked
(no brain, no Redis, no network)."""
from framework.frontdoor import run_briefing as rb


def test_enqueues_then_sends_unified():
    calls = {}

    def fake_enqueue(*, hours, limit):
        calls["enqueue_kw"] = (hours, limit)
        return {"enqueued": 2, "ids": ["1", "2"], "sources": ["awaiting-reply"]}

    def fake_drain(*, since=None, stream_key=None, count=100, consumer="chair"):
        return [
            {"id": "1", "source": "awaiting-reply", "kind": "thread", "ts": "t1",
             "urgency_tier": "batch", "payload": {"summary": "Lisa awaits reply"}},
            {"id": "2", "source": "awaiting-reply", "kind": "thread", "ts": "t2",
             "urgency_tier": "batch", "payload": {"summary": "Oliver awaits reply"}},
        ]

    def fake_send(text, *, http_post=None):
        calls["text"] = text
        return {"status": "sent", "sent": True}

    def fake_ack(ids, *, stream_key=None):
        calls["acked"] = ids
        return len(ids)

    out = rb.run_briefing(enqueue_fn=fake_enqueue, send_fn=fake_send,
                          drain_fn=fake_drain, ack_fn=fake_ack)

    assert out["synthesis"]["enqueued"] == 2
    assert out["send"]["sent"] is True
    # the two synthesis items are woven into the ONE sent message
    assert "Lisa awaits reply" in calls["text"]
    assert "Oliver awaits reply" in calls["text"]
    # acked only after the confirmed send
    assert calls["acked"] == ["1", "2"]


def test_nothing_to_send_is_safe():
    out = rb.run_briefing(
        enqueue_fn=lambda *, hours, limit: {"enqueued": 0, "ids": [], "sources": []},
        drain_fn=lambda **kw: [],
        send_fn=lambda text, *, http_post=None: {"status": "sent", "sent": True},
        ack_fn=lambda ids, *, stream_key=None: len(ids),
    )
    assert out["send"]["drained"] == 0
    assert out["send"]["sent"] is False  # empty compose → nothing sent
