"""morning_synthesis source — real signals → intake items, filtered to 1:1 non-noise.

find_threads is mocked, so these never touch the brain or Redis.
"""
from framework.frontdoor import morning_synthesis as ms


def _thread(slug, person, text, kind="direct"):
    return {"slug": slug, "person": person,
            "last": {"text": text}, "audience": {"kind": kind}}


def test_keeps_real_1to1(monkeypatch):
    monkeypatch.setattr(ms.sa, "find_threads",
                        lambda hours=72: [_thread("lisa", "Lisa Stentoft",
                                                  "Following your feedback on the question…")])
    items = ms.awaiting_reply_items()
    assert len(items) == 1
    it = items[0]
    assert it["source"] == "awaiting-reply"
    assert it["kind"] == "thread"
    assert it["urgency_tier"] == "batch"
    assert it["payload"]["summary"].startswith("Lisa Stentoft is awaiting your reply")
    assert it["context"]["why"]
    assert it["context"]["person"] == "Lisa Stentoft"


def test_drops_groups_and_noise(monkeypatch):
    monkeypatch.setattr(ms.sa, "find_threads", lambda hours=72: [
        _thread("lisa", "Lisa Stentoft", "real 1:1 question that needs an answer"),
        _thread("grp", "Teams Group X", "amen tak for det", kind="group"),     # group → drop
        _thread("ks", "Kundeservice", "Nulstil din adgangskode her"),          # noise → drop
        _thread("ext", "Someone", "You don't often get email from x. …"),      # noise → drop
    ])
    items = ms.awaiting_reply_items()
    assert [i["context"]["person"] for i in items] == ["Lisa Stentoft"]


def test_gather_failure_is_empty(monkeypatch):
    def boom(hours=72):
        raise RuntimeError("brain down")
    monkeypatch.setattr(ms.sa, "find_threads", boom)
    assert ms.awaiting_reply_items() == []


def test_limit_respected(monkeypatch):
    monkeypatch.setattr(ms.sa, "find_threads", lambda hours=72: [
        _thread(f"p{i}", f"Person{i}", "a genuine question to answer")
        for i in range(10)
    ])
    assert len(ms.awaiting_reply_items(limit=3)) == 3
