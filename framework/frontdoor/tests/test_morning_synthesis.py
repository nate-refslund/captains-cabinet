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


def _cmt(person, text, due, **kw):
    d = {"person": person, "text": text, "due": due, "status": "open",
         "direction": "owed_by_nate", "slug": person.split()[0].lower(),
         "commitment_id": f"cmt-{person[:4].lower()}"}
    d.update(kw)
    return d


def test_commitment_items_surfaces_overdue_and_today():
    items = ms.commitment_items(
        today="2026-06-23",
        commitments=[
            _cmt("Lisa Stentoft", "create tasks from Anna feedback", "2026-06-22"),
            _cmt("Kristoffer", "feedback on publisher comms email", "2026-06-20"),
            _cmt("Maria", "send the deck", "2026-06-23"),
        ],
    )
    # overdue/today only, most-overdue first
    assert [i["context"]["person"] for i in items] == ["Kristoffer", "Lisa Stentoft", "Maria"]
    it = items[0]
    assert it["source"] == "commitment"
    assert it["kind"] == "owed-by-you"
    assert it["urgency_tier"] == "batch"
    assert it["payload"]["summary"].startswith("You owe Kristoffer:")
    assert "overdue" in it["payload"]["summary"]
    assert it["context"]["commitment_id"] == "cmt-kris"
    assert items[2]["payload"]["summary"].endswith("due today (was due 2026-06-23)")


def test_commitment_items_skips_undated_and_future():
    items = ms.commitment_items(
        today="2026-06-23",
        commitments=[
            _cmt("A", "no due date", ""),                 # undated → skip
            _cmt("B", "future promise", "2026-07-10"),    # future → skip
            _cmt("C", "overdue thing", "2026-06-01"),     # overdue → keep
        ],
    )
    assert [i["context"]["person"] for i in items] == ["C"]


def test_commitment_items_respects_limit():
    # Direction filtering is the ADAPTER's job (sa.open_commitments); commitment_items
    # shapes whatever it is handed. This pins only the cap.
    cs = [_cmt(f"P{i}", "owed thing", "2026-06-10") for i in range(8)]
    items = ms.commitment_items(today="2026-06-23", commitments=cs, limit=3)
    assert len(items) == 3


def test_commitment_items_gather_failure_is_empty(monkeypatch):
    def boom(direction="owed_by_nate"):
        raise RuntimeError("ledger down")
    monkeypatch.setattr(ms.sa, "open_commitments", boom)
    assert ms.commitment_items() == []


def _health(app, failed=0, latest="READY"):
    return {"app": app, "total": 8, "latest_state": latest,
            "failed": [{"state": "ERROR"}] * failed}


def test_deploy_health_silent_when_healthy(monkeypatch):
    monkeypatch.setattr(ms.sa, "deploy_health", lambda app, **kw: _health(app, failed=0, latest="READY"))
    assert ms.deploy_health_items(apps=["v0-x"]) == []


def test_deploy_health_surfaces_failures_as_batch(monkeypatch):
    monkeypatch.setattr(ms.sa, "deploy_health", lambda app, **kw: _health(app, failed=2, latest="READY"))
    items = ms.deploy_health_items(apps=["v0-x"])
    assert len(items) == 1
    it = items[0]
    assert it["source"] == "deploy-health"
    assert it["urgency_tier"] == "batch"
    assert "2 recent failed" in it["payload"]["summary"]
    assert it["context"]["app"] == "v0-x"


def test_deploy_health_latest_broken_is_ping_now(monkeypatch):
    monkeypatch.setattr(ms.sa, "deploy_health", lambda app, **kw: _health(app, failed=1, latest="ERROR"))
    items = ms.deploy_health_items(apps=["v0-x"])
    assert items[0]["urgency_tier"] == "ping-now"
    assert "latest deploy is ERROR" in items[0]["payload"]["summary"]


def test_deploy_health_per_app_failure_skips(monkeypatch):
    def flaky(app, **kw):
        if app == "boom":
            raise RuntimeError("vercel down")
        return _health(app, failed=1, latest="READY")
    monkeypatch.setattr(ms.sa, "deploy_health", flaky)
    items = ms.deploy_health_items(apps=["boom", "ok"])
    assert [i["context"]["app"] for i in items] == ["ok"]


def test_deploy_health_no_apps_is_empty(monkeypatch):
    monkeypatch.delenv("CABINET_DEPLOY_HEALTH_APPS", raising=False)
    assert ms.deploy_health_items() == []


def test_gather_items_includes_all_sources(monkeypatch):
    monkeypatch.setattr(ms.sa, "find_threads",
                        lambda hours=72: [_thread("lisa", "Lisa Stentoft", "a real question")])
    monkeypatch.setattr(ms.sa, "open_commitments",
                        lambda direction="owed_by_nate": [_cmt("Kris", "x", "2000-01-01")])
    monkeypatch.setattr(ms.sa, "deploy_health",
                        lambda app, **kw: _health(app, failed=1, latest="READY"))
    monkeypatch.setenv("CABINET_DEPLOY_HEALTH_APPS", "v0-x")
    sources = sorted({it["source"] for it in ms.gather_items()})
    assert sources == ["awaiting-reply", "commitment", "deploy-health"]
