"""morning_synthesis source — real signals → intake items, filtered to 1:1 non-noise.

find_threads is mocked, so these never touch the brain or Redis.

SRC-3: morning_synthesis reaches the screenpipe signals through
``framework.sources.get_source()`` (the bound Flavor-A adapter), so these tests
patch the bound source's methods (``find_threads`` / ``briefing_commitments`` /
``deploy_health``) instead of the former ``ms.sa`` module handle. get_source()
returns the cached singleton, so the patch on that instance is what
morning_synthesis sees.
"""
from framework.frontdoor import morning_synthesis as ms
from framework.sources import get_source


def _thread(slug, person, text, kind="direct"):
    return {"slug": slug, "person": person,
            "last": {"text": text}, "audience": {"kind": kind}}


def test_keeps_real_1to1(monkeypatch):
    monkeypatch.setattr(get_source(), "find_threads",
                        lambda hours=72: [_thread("dana", "Dana Reed",
                                                  "Following your feedback on the question…")])
    items = ms.awaiting_reply_items()
    assert len(items) == 1
    it = items[0]
    assert it["source"] == "awaiting-reply"
    assert it["kind"] == "thread"
    assert it["urgency_tier"] == "batch"
    assert it["payload"]["summary"].startswith("Dana Reed is awaiting your reply")
    assert it["context"]["why"]
    assert it["context"]["person"] == "Dana Reed"


def test_drops_groups_and_noise(monkeypatch):
    monkeypatch.setattr(get_source(), "find_threads", lambda hours=72: [
        _thread("dana", "Dana Reed", "real 1:1 question that needs an answer"),
        _thread("grp", "Teams Group X", "amen tak for det", kind="group"),     # group → drop
        _thread("ks", "Kundeservice", "Nulstil din adgangskode her"),          # noise → drop
        _thread("ext", "Someone", "You don't often get email from x. …"),      # noise → drop
    ])
    items = ms.awaiting_reply_items()
    assert [i["context"]["person"] for i in items] == ["Dana Reed"]


def test_gather_failure_is_empty(monkeypatch):
    def boom(hours=72):
        raise RuntimeError("brain down")
    monkeypatch.setattr(get_source(), "find_threads", boom)
    assert ms.awaiting_reply_items() == []


def test_limit_respected(monkeypatch):
    monkeypatch.setattr(get_source(), "find_threads", lambda hours=72: [
        _thread(f"p{i}", f"Person{i}", "a genuine question to answer")
        for i in range(10)
    ])
    assert len(ms.awaiting_reply_items(limit=3)) == 3


def _cmt(person, text, due, **kw):
    d = {"person": person, "text": text, "due": due, "status": "open",
         "direction": "owed_by_captain", "slug": person.split()[0].lower(),
         "commitment_id": f"cmt-{person[:4].lower()}"}
    d.update(kw)
    return d


def test_commitment_items_surfaces_overdue_and_today():
    items = ms.commitment_items(
        today="2026-06-23",
        commitments=[
            _cmt("Dana Reed", "create tasks from reviewer feedback", "2026-06-22"),
            _cmt("Morgan", "feedback on the partner comms email", "2026-06-20"),
            _cmt("Casey", "send the deck", "2026-06-23"),
        ],
    )
    # overdue/today only, most-overdue first
    assert [i["context"]["person"] for i in items] == ["Morgan", "Dana Reed", "Casey"]
    it = items[0]
    assert it["source"] == "commitment"
    assert it["kind"] == "owed-by-you"
    assert it["urgency_tier"] == "batch"
    assert it["payload"]["summary"].startswith("You owe Morgan:")
    assert "overdue" in it["payload"]["summary"]
    assert it["context"]["commitment_id"] == "cmt-morg"
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
    def boom(direction="owed_by_captain"):
        raise RuntimeError("ledger down")
    monkeypatch.setattr(get_source(), "briefing_commitments", boom)
    assert ms.commitment_items() == []


def _health(app, failed=0, latest="READY"):
    return {"app": app, "total": 8, "latest_state": latest,
            "failed": [{"state": "ERROR"}] * failed}


def test_deploy_health_silent_when_healthy(monkeypatch):
    monkeypatch.setattr(get_source(), "deploy_health", lambda app, **kw: _health(app, failed=0, latest="READY"))
    assert ms.deploy_health_items(apps=["v0-x"]) == []


def test_deploy_health_surfaces_failures_as_batch(monkeypatch):
    monkeypatch.setattr(get_source(), "deploy_health", lambda app, **kw: _health(app, failed=2, latest="READY"))
    items = ms.deploy_health_items(apps=["v0-x"])
    assert len(items) == 1
    it = items[0]
    assert it["source"] == "deploy-health"
    assert it["urgency_tier"] == "batch"
    assert "2 recent failed" in it["payload"]["summary"]
    assert it["context"]["app"] == "v0-x"


def test_deploy_health_latest_broken_is_ping_now(monkeypatch):
    monkeypatch.setattr(get_source(), "deploy_health", lambda app, **kw: _health(app, failed=1, latest="ERROR"))
    items = ms.deploy_health_items(apps=["v0-x"])
    assert items[0]["urgency_tier"] == "ping-now"
    assert "latest deploy is ERROR" in items[0]["payload"]["summary"]


def test_deploy_health_per_app_failure_skips(monkeypatch):
    def flaky(app, **kw):
        if app == "boom":
            raise RuntimeError("vercel down")
        return _health(app, failed=1, latest="READY")
    monkeypatch.setattr(get_source(), "deploy_health", flaky)
    items = ms.deploy_health_items(apps=["boom", "ok"])
    assert [i["context"]["app"] for i in items] == ["ok"]


def test_deploy_health_no_apps_is_empty(monkeypatch):
    monkeypatch.delenv("CABINET_DEPLOY_HEALTH_APPS", raising=False)
    assert ms.deploy_health_items() == []


def _sentry(issues):
    return {"project": "p", "count": len(issues), "issues": issues}


def test_sentry_health_silent_when_no_issues(monkeypatch):
    monkeypatch.setattr(ms.product_health, "sentry_health", lambda o, p, **kw: _sentry([]))
    assert ms.sentry_health_items(org="step", project="p") == []


def test_sentry_health_batch_for_minor_errors(monkeypatch):
    monkeypatch.setattr(ms.product_health, "sentry_health",
                        lambda o, p, **kw: _sentry([{"title": "TypeError x", "events": 12}]))
    items = ms.sentry_health_items(org="step", project="p")
    assert len(items) == 1
    it = items[0]
    assert it["source"] == "sentry-health"
    assert it["urgency_tier"] == "batch"
    assert "1 unresolved error" in it["payload"]["summary"]


def test_sentry_health_ping_now_for_incident(monkeypatch):
    monkeypatch.setattr(ms.product_health, "sentry_health",
                        lambda o, p, **kw: _sentry([{"title": "SyntaxError", "events": 13084}]))
    items = ms.sentry_health_items(org="step", project="p")
    assert items[0]["urgency_tier"] == "ping-now"
    assert items[0]["context"]["top_events"] == 13084


def test_sentry_health_no_config_is_empty(monkeypatch):
    monkeypatch.delenv("CABINET_SENTRY_ORG", raising=False)
    monkeypatch.delenv("CABINET_SENTRY_PROJECT", raising=False)
    assert ms.sentry_health_items() == []


def test_sentry_health_injected_overrides_network():
    items = ms.sentry_health_items(org="step", project="p",
                                   health=_sentry([{"title": "E", "events": 5}]))
    assert items[0]["urgency_tier"] == "batch"


def test_gather_items_includes_all_sources(monkeypatch):
    monkeypatch.setattr(get_source(), "find_threads",
                        lambda hours=72: [_thread("dana", "Dana Reed", "a real question")])
    monkeypatch.setattr(get_source(), "briefing_commitments",
                        lambda direction="owed_by_captain": [_cmt("Kim", "x", "2000-01-01")])
    monkeypatch.setattr(get_source(), "deploy_health",
                        lambda app, **kw: _health(app, failed=1, latest="READY"))
    monkeypatch.setattr(ms.product_health, "sentry_health",
                        lambda o, p, **kw: _sentry([{"title": "E", "events": 9}]))
    # follow-up reader mocked so the source list is deterministic regardless of
    # what the real register holds today.
    monkeypatch.setattr(ms, "_due_followups",
                        lambda script=None: [{"id": "f1", "check_from": "2000-01-01",
                                              "entry": "f1 | deadline 2000-01-02 | check_from 2000-01-01 | Subj | gather: g | nudge_if: n | status: open"}])
    monkeypatch.setenv("CABINET_DEPLOY_HEALTH_APPS", "v0-x")
    monkeypatch.setenv("CABINET_SENTRY_ORG", "step")
    monkeypatch.setenv("CABINET_SENTRY_PROJECT", "p")
    sources = sorted({it["source"] for it in ms.gather_items()})
    assert sources == ["awaiting-reply", "commitment", "deploy-health", "follow-up", "sentry-health"]


# ── dated follow-ups source (followup_items) ────────────────────────────────
# _due_followups (the subprocess→reader call) is injectable via the `due=` arg
# so these never shell out; the reader's own date/status parsing is tested
# separately by the shell harness.

def _fu(fid, subject, *, status="open", tier_marker=""):
    """Build a reader-shaped due object (id / check_from / entry)."""
    rule = "gather: did it resolve? | nudge_if: still open → ping the captain"
    if tier_marker:
        rule += f" {tier_marker}"
    entry = (f"{fid} | deadline 2026-08-07 | check_from 2026-08-04 | "
             f"{subject} | {rule} | status: {status}")
    return {"id": fid, "check_from": "2026-08-04", "entry": entry}


def test_followup_item_shape_and_rule_inline():
    items = ms.followup_items(due=[_fu("vendor-dpa", "Vendor — accept the new DPA")])
    assert len(items) == 1
    it = items[0]
    assert it["source"] == "follow-up"
    assert it["kind"] == "dated-register"
    assert it["urgency_tier"] == "batch"            # default tier
    assert it["context"]["followup_id"] == "vendor-dpa"
    assert it["context"]["subject"] == "Vendor — accept the new DPA"
    assert it["context"]["why"]
    s = it["payload"]["summary"]
    assert "Vendor — accept the new DPA" in s       # subject surfaced
    assert "gather:" in s and "nudge_if:" in s      # gather-then-decide rule carried inline


def test_followup_ping_now_when_marked():
    items = ms.followup_items(due=[_fu("urgent", "deadline today", tier_marker="ping-now")])
    assert items[0]["urgency_tier"] == "ping-now"


def test_followup_empty_when_nothing_due():
    assert ms.followup_items(due=[]) == []


def test_followup_skips_malformed_entries():
    # An entry with no text, and a non-dict, are both skipped without crashing.
    due = [{"id": "x", "entry": ""}, "not-a-dict", _fu("ok", "Real one")]
    items = ms.followup_items(due=due)
    assert [i["context"]["followup_id"] for i in items] == ["ok"]


def test_due_followups_swallows_subprocess_failure(tmp_path):
    # The real _due_followups must never raise: a missing/failing reader script
    # → []. Point it at a nonexistent path (FileNotFoundError inside subprocess).
    missing = str(tmp_path / "no-such-due-followups.sh")
    assert ms._due_followups(script=missing) == []


def test_due_followups_swallows_bad_json(tmp_path, monkeypatch):
    # A reader that exits 0 but prints non-JSON → [] (never raises).
    fake = tmp_path / "fake-reader.sh"
    fake.write_text("#!/bin/bash\necho 'not json at all'\n")
    fake.chmod(0o755)
    assert ms._due_followups(script=str(fake)) == []


def test_followup_items_default_reads_register():
    # No injection → calls the real reader on the real register (live, un-mocked
    # path). Asserts it returns a list and never raises; if anything IS due today
    # every item must carry the follow-up source + an id (no brittle exact match
    # on register contents, which change over time).
    items = ms.followup_items()
    assert isinstance(items, list)
    for it in items:
        assert it["source"] == "follow-up"
        assert "followup_id" in it["context"]


# ── split routing: operational → Chair, captain-facing → intake (2026-06-26) ──
# The Captain's standing directive: Sentry + deploy health are operational/monitoring
# noise that must route to the Chair (cabinet:triggers:cos) for triage, NOT into
# the captain-bound briefing intake. These lock that split so it can't regress.

def _wire_all_sources(monkeypatch):
    """Mock every source so gather_items yields one of each (incl. both operational)."""
    monkeypatch.setattr(get_source(), "find_threads",
                        lambda hours=72: [_thread("dana", "Dana Reed", "a real question")])
    monkeypatch.setattr(get_source(), "briefing_commitments",
                        lambda direction="owed_by_captain": [_cmt("Kim", "x", "2000-01-01")])
    monkeypatch.setattr(get_source(), "deploy_health",
                        lambda app, **kw: _health(app, failed=1, latest="ERROR"))
    monkeypatch.setattr(ms.product_health, "sentry_health",
                        lambda o, p, **kw: _sentry([{"title": "E", "events": 9}]))
    monkeypatch.setattr(ms, "_due_followups",
                        lambda script=None: [{"id": "f1", "check_from": "2000-01-01",
                                              "entry": "f1 | deadline 2000-01-02 | check_from 2000-01-01 | Subj | gather: g | nudge_if: n | status: open"}])
    monkeypatch.setenv("CABINET_DEPLOY_HEALTH_APPS", "v0-x")
    monkeypatch.setenv("CABINET_SENTRY_ORG", "step")
    monkeypatch.setenv("CABINET_SENTRY_PROJECT", "p")


def test_enqueue_splits_operational_to_chair(monkeypatch):
    _wire_all_sources(monkeypatch)
    enqueued, chair_msgs = [], []
    monkeypatch.setattr(ms.intake, "enqueue", lambda it: (enqueued.append(it), "id-x")[1])
    monkeypatch.setattr(ms, "notify_chair", lambda msg, **kw: (chair_msgs.append(msg), True)[1])

    res = ms.enqueue_synthesis()

    # Captain-bound intake gets ONLY the captain-facing sources — never the operational ones.
    intake_sources = sorted({it["source"] for it in enqueued})
    assert intake_sources == ["awaiting-reply", "commitment", "follow-up"]
    assert "sentry-health" not in intake_sources and "deploy-health" not in intake_sources

    # The Chair got exactly ONE composed operational message, naming both signals.
    assert len(chair_msgs) == 1
    assert "OPERATIONAL HEALTH" in chair_msgs[0]
    assert "Sentry" in chair_msgs[0]            # the sentry summary line
    assert "v0-x" in chair_msgs[0]              # the deploy-health summary names the app

    # The return contract reports the split.
    assert res["enqueued"] == 3
    assert res["sources"] == ["awaiting-reply", "commitment", "follow-up"]
    assert res["chair_routed"] == 2
    assert res["chair_sources"] == ["deploy-health", "sentry-health"]
    assert res["chair_delivered"] is True


def test_enqueue_no_chair_message_when_no_operational(monkeypatch):
    # Only captain-facing sources present → the Chair is NOT pinged at all.
    monkeypatch.setattr(get_source(), "find_threads",
                        lambda hours=72: [_thread("dana", "Dana Reed", "a real question")])
    monkeypatch.setattr(get_source(), "briefing_commitments", lambda direction="owed_by_captain": [])
    monkeypatch.setattr(get_source(), "deploy_health", lambda app, **kw: _health(app, failed=0, latest="READY"))
    monkeypatch.setattr(ms.product_health, "sentry_health", lambda o, p, **kw: _sentry([]))
    monkeypatch.setattr(ms, "_due_followups", lambda script=None: [])
    monkeypatch.setenv("CABINET_DEPLOY_HEALTH_APPS", "v0-x")
    monkeypatch.setenv("CABINET_SENTRY_ORG", "step")
    monkeypatch.setenv("CABINET_SENTRY_PROJECT", "p")

    enqueued, chair_calls = [], []
    monkeypatch.setattr(ms.intake, "enqueue", lambda it: (enqueued.append(it), "id-x")[1])
    monkeypatch.setattr(ms, "notify_chair", lambda msg, **kw: (chair_calls.append(msg), True)[1])

    res = ms.enqueue_synthesis()
    assert chair_calls == []                    # Chair untouched when nothing operational
    assert res["chair_routed"] == 0
    assert res["enqueued"] == 1                 # just the awaiting-reply item


def test_notify_chair_never_raises(monkeypatch):
    # A redis-cli explosion must degrade to False, never bubble into the briefing.
    def boom(*a, **k):
        raise RuntimeError("redis down")
    monkeypatch.setattr(ms.subprocess, "run", boom)
    assert ms.notify_chair("anything") is False
