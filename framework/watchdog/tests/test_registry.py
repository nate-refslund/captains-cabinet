"""test_registry — the OUTCOME-expectation verifies + tiered routing.

All I/O goes through a FakeProbe (no real Redis, no real files, no network), so
the whole evaluation + routing is exercised deterministically. The headline case
is the bug-of-record: a briefing log whose process ran but whose send 400'd must
verify FALSE and route to the auto-fix (Chair re-trigger).

Run: /opt/homebrew/bin/python3.12 -m pytest framework/watchdog/tests/ -q
"""
from __future__ import annotations

import datetime as dt
import json

from framework.watchdog import registry as reg
from framework.watchdog.registry import CheckResult, Probe, Tier


# ─────────────────────────────────────────────────────────────────────────────
# FakeProbe — in-memory stand-in for the real Probe. Files/Redis/clock are dicts.
# It also records side-effects (chair triggers, drift proposals, cooldowns) so a
# test can assert the router did the right thing.
# ─────────────────────────────────────────────────────────────────────────────
class FakeProbe(Probe):
    def __init__(self, *, now=None, local=None, files=None, mtimes=None, redis=None):
        self._now = now or dt.datetime(2026, 6, 29, 16, 0, tzinfo=dt.timezone.utc)
        # default local = Europe/Berlin ~= UTC+2 in summer
        self._local = local or self._now.astimezone(
            dt.timezone(dt.timedelta(hours=2)))
        self._files = files or {}
        self._mtimes = mtimes or {}
        self._redis = redis or {}
        # side-effect capture
        self.triggers: list[str] = []
        self.drift: list[tuple[str, str]] = []
        self.cooldowns: dict[str, str] = {}
        self.heartbeats: int = 0
        self.trigger_returns = True  # let a test force enqueue-failure

    # read surface
    def now(self):
        return self._now

    def local_now(self):
        return self._local

    def read_text(self, path):
        return self._files.get(path, "")

    def file_mtime(self, path):
        return self._mtimes.get(path)

    def redis_get(self, key):
        return self._redis.get(key, "")

    def redis_keys(self, pattern):
        return list(self._redis.keys())

    def launchd_loaded(self, label):
        return True

    # side-effecting surface (used by the router via the real probe; FakeProbe
    # implements the same names so route_failure works unchanged)
    def trigger_chair(self, message):
        self.triggers.append(message)
        return self.trigger_returns

    def cooldown_active(self, eid, action):
        return f"{eid}:{action}" in self.cooldowns

    def set_cooldown(self, eid, action):
        self.cooldowns[f"{eid}:{action}"] = "set"

    def emit_drift_proposal(self, title, body):
        self.drift.append((title, body))
        return True

    def stamp_heartbeat(self):
        self.heartbeats += 1


# ─────────────────────────────────────────────────────────────────────────────
# Briefing-delivered verify — the bug-of-record.
# ─────────────────────────────────────────────────────────────────────────────
def _briefing_log(send_dict: dict) -> str:
    """Build a briefing log whose newest record carries the given run_send_path
    result (the real shape: outer 'send' with the nested channel result)."""
    rec = {"synthesis": {"enqueued": 1}, "recap": None, "send": send_dict}
    return json.dumps(rec, indent=2) + "\n"


def test_briefing_send_failed_verifies_false_and_autofixes():
    # The exact production failure: process ran (fresh log), send 400'd.
    log = _briefing_log({
        "drained": 83, "sent": False, "recovered": 77, "acked": 0,
        "send": {"status": "error", "sent": False, "error": "telegram HTTP 400"},
    })
    # local 08:30 (after the 07:30 AM slot+grace); run mtime == now (fresh).
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    probe = FakeProbe(now=now, local=local,
                      files={reg.BRIEFING_LOG: log},
                      mtimes={reg.BRIEFING_LOG: now.timestamp()})
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is False
    assert "send FAILED" in res.detail
    assert res.fix_hint.get("cause") == "send-failed"
    # routing: AUTO_FIX → auto_fix fires → Chair re-trigger
    exp = reg.expectation_by_id("briefing-delivered")
    from framework.watchdog.check import route_failure  # imported lazily
    # route_failure expects the RealProbe surface; FakeProbe provides the same
    # method names, so it works directly.
    action = route_failure(probe, exp, res)
    assert "AUTO-FIX fired" in action
    assert len(probe.triggers) == 1
    assert "RE-RUN the briefing" in probe.triggers[0]
    # the re-trigger must NOT instruct DMing Nate
    assert "Do NOT DM Nate" in probe.triggers[0]


def test_briefing_delivered_success_passes():
    log = _briefing_log({
        "drained": 5, "sent": True, "recovered": 0, "acked": 5,
        "send": {"status": "sent", "sent": True, "response": {"ok": True}},
    })
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    probe = FakeProbe(now=now, local=local,
                      files={reg.BRIEFING_LOG: log},
                      mtimes={reg.BRIEFING_LOG: now.timestamp()})
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is True
    assert "delivered" in res.detail


def test_briefing_stale_success_is_did_not_run():
    # Last record is a SUCCESS but ran yesterday — today's slot never fired.
    log = _briefing_log({
        "drained": 5, "sent": True, "recovered": 0,
        "send": {"status": "sent", "sent": True},
    })
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    # mtime = 26h ago → before today's 07:30 slot
    stale_mtime = (now - dt.timedelta(hours=26)).timestamp()
    probe = FakeProbe(now=now, local=local,
                      files={reg.BRIEFING_LOG: log},
                      mtimes={reg.BRIEFING_LOG: stale_mtime})
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is False
    assert res.fix_hint.get("cause") == "did-not-run"


def test_briefing_before_first_slot_uses_yesterday_pm():
    # At 06:00 local (before the 07:30 AM grace), the due slot is yesterday PM.
    # A fresh successful send from yesterday evening should PASS.
    log = _briefing_log({"sent": True, "send": {"status": "sent", "sent": True}})
    now = dt.datetime(2026, 6, 29, 4, 0, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 6, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    # yesterday 19:30 local == yesterday 17:30 UTC; run at 17:35 UTC yesterday
    y_pm_run = dt.datetime(2026, 6, 28, 17, 35, tzinfo=dt.timezone.utc)
    probe = FakeProbe(now=now, local=local,
                      files={reg.BRIEFING_LOG: log},
                      mtimes={reg.BRIEFING_LOG: y_pm_run.timestamp()})
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is True


def test_briefing_no_log_fails():
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    probe = FakeProbe(now=now, local=local, files={}, mtimes={})
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is False
    assert "no briefing-log records" in res.detail


# ── Refinement (2026-06-29): satisfied-by-ANY-delivery + per-slot dedup ──────
def test_briefing_satisfied_by_manual_delivery_marker():
    """The bug the Chair's first-fire revealed: the cron send FAILED (400), but
    the briefing was MANUALLY delivered (Chair stamped the schedule marker). The
    OUTCOME (Nate got his briefing) is TRUE — must verify OK, NOT false-positive.
    Marker value mirrors production: an ISO ts + trailing human annotation."""
    log = _briefing_log({
        "drained": 83, "sent": False, "recovered": 77,
        "send": {"status": "error", "sent": False, "error": "telegram HTTP 400"},
    })
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    # AM slot = 07:30 Berlin = 05:30Z. Manual delivery at 06:29:35Z is AFTER it.
    probe = FakeProbe(
        now=now, local=local,
        files={reg.BRIEFING_LOG: log},
        mtimes={reg.BRIEFING_LOG: now.timestamp()},
        redis={reg.BRIEF_DELIVERED_MARKER_KEY: "2026-06-29T06:29:35Z (manual — cron miss)"},
    )
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is True
    assert "satisfied by any means" in res.detail


def test_briefing_stale_marker_does_not_satisfy():
    """A delivery marker from BEFORE the due slot (yesterday's briefing) must NOT
    satisfy today's slot — otherwise a stale marker would mask a real miss."""
    log = _briefing_log({
        "sent": False,
        "send": {"status": "error", "sent": False, "error": "telegram HTTP 400"},
    })
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    probe = FakeProbe(
        now=now, local=local,
        files={reg.BRIEFING_LOG: log},
        mtimes={reg.BRIEFING_LOG: now.timestamp()},
        # marker is yesterday → before today's 05:30Z AM slot
        redis={reg.BRIEF_DELIVERED_MARKER_KEY: "2026-06-28T17:30:00Z"},
    )
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is False
    assert res.fix_hint.get("cause") == "send-failed"


def test_briefing_per_slot_dedup_scopes_cooldown():
    """A handled AM-slot failure must NOT suppress a fresh PM-slot failure: the
    cooldown is scoped by slot_id. Two failures with different slot_ids each fire."""
    from framework.watchdog.check import route_failure
    exp = reg.expectation_by_id("briefing-delivered")
    probe = FakeProbe()
    am = CheckResult("briefing-delivered", False, "AM failed",
                     fix_hint={"cause": "send-failed", "slot_id": "2026-06-29-AM"})
    pm = CheckResult("briefing-delivered", False, "PM failed",
                     fix_hint={"cause": "send-failed", "slot_id": "2026-06-29-PM"})
    a1 = route_failure(probe, exp, am)
    assert "AUTO-FIX fired" in a1
    # same AM slot again → suppressed
    a1b = route_failure(probe, exp, am)
    assert "SKIPPED" in a1b
    # DIFFERENT slot (PM) → fires fresh, not suppressed by the AM cooldown
    a2 = route_failure(probe, exp, pm)
    assert "AUTO-FIX fired" in a2
    assert len(probe.triggers) == 2  # AM + PM, but NOT the duplicate AM


def test_leading_iso_parses_annotated_marker():
    from framework.watchdog.registry import _leading_iso
    d = _leading_iso("2026-06-29T06:29:35Z (manual — cron miss)")
    assert d is not None
    assert d.year == 2026 and d.hour == 6 and d.minute == 29
    assert _leading_iso("not a date") is None
    assert _leading_iso("") is None


# ── Review fixes (2026-06-29 adversarial review) ─────────────────────────────
def test_briefing_sent_true_without_status_still_passes():
    """HIGH: a record with send.sent==True but NO/renamed nested status must NOT
    false-FAIL (the old `sent and status=='sent'` AND did). `sent` is canonical."""
    log = _briefing_log({"drained": 3, "sent": True,
                         "send": {"sent": True}})  # no 'status' key at all
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    probe = FakeProbe(now=now, local=local,
                      files={reg.BRIEFING_LOG: log},
                      mtimes={reg.BRIEFING_LOG: now.timestamp()})
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is True


def test_briefing_prefers_record_level_ts_over_mtime():
    """CRITICAL mitigation: when a record carries its own ts, that — not the file
    mtime — is the run time. A stale mtime must not mask a fresh failed record."""
    # Fresh failed send, but mtime is STALE (yesterday). The record-level ts is
    # fresh (today, after slot) → must be treated as ran-but-failed (not did-not-run).
    rec = {"ts": "2026-06-29T06:00:00Z",  # after the 05:30Z AM slot
           "send": {"drained": 9, "sent": False, "recovered": 9,
                    "send": {"status": "error", "sent": False, "error": "telegram HTTP 400"}}}
    import json as _j
    log = _j.dumps(rec, indent=2) + "\n"
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    stale_mtime = (now - dt.timedelta(hours=26)).timestamp()  # mtime says yesterday
    probe = FakeProbe(now=now, local=local,
                      files={reg.BRIEFING_LOG: log},
                      mtimes={reg.BRIEFING_LOG: stale_mtime})
    res = reg.verify_briefing_delivered(probe)
    assert res.ok is False
    # record ts (fresh) wins → classified as send-failed, not did-not-run
    assert res.fix_hint.get("cause") == "send-failed"


def test_briefing_skips_when_tz_unresolved():
    """MEDIUM: if the Captain TZ can't resolve, the briefing check must SKIP, not
    false-fail all day with wrong UTC slot math."""
    class NoTZProbe(FakeProbe):
        def tz_ok(self):
            return False
    probe = NoTZProbe()
    res = reg.verify_briefing_delivered(probe)
    assert res.skipped is True
    assert res.ok is True  # skipped == neither pass nor fail (not routed)


def test_autofix_success_suppresses_escalation_fallback():
    """MINOR: once auto-fix fires, the NEXT cycle (autofix on cooldown) must NOT
    fall through and double-ping the Chair via the escalation fallback."""
    from framework.watchdog.check import route_failure
    exp = reg.expectation_by_id("briefing-delivered")
    res = CheckResult("briefing-delivered", False, "send failed",
                      fix_hint={"cause": "send-failed", "slot_id": "2026-06-29-AM"})
    probe = FakeProbe()
    a1 = route_failure(probe, exp, res)        # cycle 1 → auto-fix fires
    assert "AUTO-FIX fired" in a1
    assert len(probe.triggers) == 1
    a2 = route_failure(probe, exp, res)        # cycle 2 → must be fully suppressed
    assert "SKIPPED" in a2
    assert len(probe.triggers) == 1            # NO second message of any kind


# ─────────────────────────────────────────────────────────────────────────────
# Officer-reflection verify.
# ─────────────────────────────────────────────────────────────────────────────
def test_reflection_overdue_worked_but_stale():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    redis = {
        # cos worked recently but last reflected 50h ago → overdue
        "cabinet:last-experience:cos": (now - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cabinet:schedule:last-run:cos:reflection": (now - dt.timedelta(hours=50)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    probe = FakeProbe(now=now, redis=redis)
    res = reg.verify_officer_reflection(probe)
    assert res.ok is False
    assert "cos" in res.detail


def test_reflection_idle_officer_not_flagged():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    # no last-experience for anyone → all idle → pass
    probe = FakeProbe(now=now, redis={})
    res = reg.verify_officer_reflection(probe)
    assert res.ok is True


def test_reflection_worked_never_reflected_flagged():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    redis = {"cabinet:last-experience:polads-ceo": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    probe = FakeProbe(now=now, redis=redis)
    res = reg.verify_officer_reflection(probe)
    assert res.ok is False
    assert "never reflected" in res.detail


# ─────────────────────────────────────────────────────────────────────────────
# Captain-decisions-logged verify (DRIFT tier).
# ─────────────────────────────────────────────────────────────────────────────
def test_captain_decisions_current_passes():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    md = "# Captain Decisions\n\n## 2026-06-28 — Something\n- Decision: x\n"
    probe = FakeProbe(now=now, files={reg.CAPTAIN_DECISIONS: md})
    res = reg.verify_captain_decisions_logged(probe)
    assert res.ok is True


def test_captain_decisions_stale_fails():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    md = "# Captain Decisions\n\n## 2026-06-10 — Old\n- Decision: x\n"
    probe = FakeProbe(now=now, files={reg.CAPTAIN_DECISIONS: md})
    res = reg.verify_captain_decisions_logged(probe)
    assert res.ok is False
    assert "days old" in res.detail


def test_captain_decisions_parenthesized_date():
    # Headings like "## Paddle VAT/tax — ... (2026-06-29)" should parse.
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    md = "# Captain Decisions\n\n## Paddle VAT/tax — inclusion (2026-06-29)\n- x\n"
    probe = FakeProbe(now=now, files={reg.CAPTAIN_DECISIONS: md})
    res = reg.verify_captain_decisions_logged(probe)
    assert res.ok is True


# ─────────────────────────────────────────────────────────────────────────────
# Silent-cron-failure verify.
# ─────────────────────────────────────────────────────────────────────────────
def test_cron_clean_passes():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    path = f"{reg.CABINET_LOG_DIR}/status-sweep.log"
    probe = FakeProbe(now=now,
                      files={path: "[ok] status-sweep: trigger pushed to cos\n"},
                      mtimes={path: now.timestamp()})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True


def test_cron_error_marker_fails():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    path = f"{reg.CABINET_LOG_DIR}/status-sweep.log"
    probe = FakeProbe(now=now,
                      files={path: "boom\nFATAL: triggers lib not found — trigger NOT pushed\n"},
                      mtimes={path: now.timestamp()})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "status-sweep" in res.detail


def test_cron_stale_fails():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    path = f"{reg.CABINET_LOG_DIR}/status-sweep.log"
    old = (now - dt.timedelta(hours=3)).timestamp()
    probe = FakeProbe(now=now, files={path: "[ok]\n"}, mtimes={path: old})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "silent" in res.detail


# ─────────────────────────────────────────────────────────────────────────────
# Pipes-fresh verify.
# ─────────────────────────────────────────────────────────────────────────────
def test_pipes_fresh_passes():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    mtimes = {f"{reg.SCREENPIPE_STATE_DIR}/{fn}": now.timestamp()
              for (fn, _s) in reg.PIPE_FRESHNESS.values()}
    probe = FakeProbe(now=now, mtimes=mtimes)
    res = reg.verify_pipes_fresh(probe)
    assert res.ok is True


def test_pipes_stale_fails():
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    old = (now - dt.timedelta(hours=5)).timestamp()
    mtimes = {f"{reg.SCREENPIPE_STATE_DIR}/{fn}": old
              for (fn, _s) in reg.PIPE_FRESHNESS.values()}
    probe = FakeProbe(now=now, mtimes=mtimes)
    res = reg.verify_pipes_fresh(probe)
    assert res.ok is False
    assert "stale" in res.detail


# ─────────────────────────────────────────────────────────────────────────────
# Router tiers + anti-thrash cooldown.
# ─────────────────────────────────────────────────────────────────────────────
def test_escalate_tier_pings_chair_once_then_cooldown():
    from framework.watchdog.check import route_failure
    exp = reg.expectation_by_id("pipes-fresh")
    res = CheckResult("pipes-fresh", False, "embeddings 5h stale")
    probe = FakeProbe()
    a1 = route_failure(probe, exp, res)
    assert "ESCALATED to Chair" in a1
    assert len(probe.triggers) == 1
    # second time within cooldown → skipped
    a2 = route_failure(probe, exp, res)
    assert "SKIPPED (cooldown active)" in a2
    assert len(probe.triggers) == 1  # no new trigger


def test_drift_tier_writes_proposal_not_alert():
    from framework.watchdog.check import route_failure
    exp = reg.expectation_by_id("captain-decisions-logged")
    res = CheckResult("captain-decisions-logged", False, "12 days old")
    probe = FakeProbe()
    action = route_failure(probe, exp, res)
    assert "DRIFT note" in action
    assert len(probe.drift) == 1          # proposal written
    assert len(probe.triggers) == 0       # NOT an alert/trigger


def test_autofix_decline_falls_back_to_escalation():
    from framework.watchdog.check import route_failure
    exp = reg.expectation_by_id("briefing-delivered")
    res = CheckResult("briefing-delivered", False, "send failed",
                      fix_hint={"cause": "send-failed", "slot_local": "x"})
    probe = FakeProbe()
    probe.trigger_returns = False  # force the chair-trigger (and thus auto_fix) to fail
    action = route_failure(probe, exp, res)
    # auto_fix returns None (trigger failed) → fall back to escalation, which
    # also fails to enqueue here → reported, never silently dropped
    assert "auto-fix declined" in action or "could not" in action.lower()


def test_full_run_with_fake_probe_routes_only_failures():
    """End-to-end check.run() over the real registry with a FakeProbe whose
    state makes EXACTLY the briefing fail (everything else healthy)."""
    from framework.watchdog import check
    now = dt.datetime(2026, 6, 29, 6, 30, tzinfo=dt.timezone.utc)
    local = dt.datetime(2026, 6, 29, 8, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    # briefing: failed send (fresh)
    blog = _briefing_log({"drained": 9, "sent": False, "recovered": 9,
                          "send": {"status": "error", "sent": False, "error": "telegram HTTP 400"}})
    # decisions: current
    dec = "## 2026-06-29 — x\n"
    # cron: clean + fresh
    cron_path = f"{reg.CABINET_LOG_DIR}/status-sweep.log"
    # pipes: fresh
    pipe_mtimes = {f"{reg.SCREENPIPE_STATE_DIR}/{fn}": now.timestamp()
                   for (fn, _s) in reg.PIPE_FRESHNESS.values()}
    probe = FakeProbe(
        now=now, local=local,
        files={reg.BRIEFING_LOG: blog, reg.CAPTAIN_DECISIONS: dec,
               cron_path: "[ok]\n"},
        mtimes={reg.BRIEFING_LOG: now.timestamp(), cron_path: now.timestamp(),
                **pipe_mtimes},
        redis={},  # no officer worked → reflection passes
    )
    report = check.run(probe=probe, dry_run=False)
    assert report["checked"] == 5
    assert report["failed"] == 1
    assert probe.heartbeats == 1  # heartbeat stamped after sweep
    failed = [r for r in report["results"] if not r["ok"] and not r["skipped"]]
    assert failed[0]["id"] == "briefing-delivered"
    assert "AUTO-FIX fired" in failed[0]["action"]
    # exactly one Chair trigger (the auto-fix re-trigger)
    assert len(probe.triggers) == 1
