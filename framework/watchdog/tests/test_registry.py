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
    def __init__(self, *, now=None, local=None, files=None, mtimes=None, redis=None,
                 launchctl=None):
        self._now = now or dt.datetime(2026, 6, 29, 16, 0, tzinfo=dt.timezone.utc)
        # default local = Europe/Berlin ~= UTC+2 in summer
        self._local = local or self._now.astimezone(
            dt.timezone(dt.timedelta(hours=2)))
        self._files = files or {}
        self._mtimes = mtimes or {}
        self._redis = redis or {}
        # launchctl surface (lane-ops 2026-07-04): {} = "not observable" —
        # matches the base-Probe default, so tests that don't care exercise
        # the self-disabled path exactly like a non-Mac host.
        self._launchctl = launchctl or {}
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

    def launchctl_list(self):
        return self._launchctl

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
# Manifest-derived cron coverage (lane-ops 2026-07-04). These encode the two
# incidents-of-record: retro-trigger FATAL'ing hourly outside the hardcoded
# watch list, and memory-worker declared-but-never-scheduled.
# ─────────────────────────────────────────────────────────────────────────────
# A miniature but shape-faithful manifest: flow interval, flow calendar with
# weekday, BLOCK calendar, keepalive, officer, disabled, env/notes noise —
# every construct the real services.yml uses.
_MINI_MANIFEST = """\
# header comment
services:
  - name: officer-cos
    label: com.cabinet.officer.cos
    kind: officer
    command: bash cabinet/scripts/start-officer-mac.sh cos
    schedule: keepalive
    notes: sole Telegram voice
  - name: retro-trigger
    label: com.cabinet.retro-trigger
    kind: cron
    command: bash cabinet/cron/retro-trigger.sh
    schedule: { interval_s: 3600 }
    notes: >-
      adversarial block scalar deliberately mentioning interval_s: 999 and
      weekday — the parser must NOT read a notes continuation as schedule
      fields (the exact-4-space key match clears the schedule-block flag).
  - name: memory-worker
    label: com.cabinet.memory-worker
    kind: daemon
    command: bash cabinet/scripts/memory-worker.sh
    schedule: keepalive
    env:
      SOME_FLAG: "1"
  - name: frontdoor-briefing
    label: com.cabinet.frontdoor-briefing
    kind: daemon
    command: bash cabinet/scripts/run-frontdoor-briefing.sh
    schedule:
      calendar:
        - { hour: 7, minute: 30 }
        - { hour: 19, minute: 30 }
  - name: actfirst-canary
    label: com.cabinet.actfirst-canary
    kind: watchdog
    command: bash cabinet/scripts/run-actfirst-canary.sh
    schedule: { calendar: [{weekday: 1, hour: 7, minute: 15}] }   # Mondays
  - name: draft-lane
    label: com.cabinet.draft-lane
    kind: daemon
    disabled: true
    command: bash cabinet/scripts/run-draft-lane.sh
    schedule: { interval_s: 300 }
"""


def test_manifest_parser_extracts_all_shapes():
    entries = {e["name"]: e for e in reg._parse_services_manifest(_MINI_MANIFEST)}
    assert entries["officer-cos"]["kind"] == "officer"
    assert entries["officer-cos"]["schedule_kind"] == "keepalive"
    rt = entries["retro-trigger"]
    assert rt["kind"] == "cron" and rt["schedule_kind"] == "interval"
    assert rt["interval_s"] == 3600  # the notes block-scalar 999 must NOT win
    assert entries["memory-worker"]["schedule_kind"] == "keepalive"
    fb = entries["frontdoor-briefing"]
    assert fb["schedule_kind"] == "calendar" and fb["weekly"] is False
    ac = entries["actfirst-canary"]
    assert ac["schedule_kind"] == "calendar" and ac["weekly"] is True
    dl = entries["draft-lane"]
    assert dl["disabled"] is True
    assert entries["retro-trigger"]["label"] == "com.cabinet.retro-trigger"


def test_floor_policy_interval_calendar_keepalive():
    assert reg._floor_for_entry({"schedule_kind": "interval", "interval_s": 3600}) == 7800
    # short cadences clamp to the 2h minimum (quiet-run false-alarm guard)
    assert reg._floor_for_entry({"schedule_kind": "interval", "interval_s": 300}) == 7200
    assert reg._floor_for_entry({"schedule_kind": "calendar", "weekly": False}) == 26 * 3600
    assert reg._floor_for_entry({"schedule_kind": "calendar", "weekly": True}) == 8 * 86400
    assert reg._floor_for_entry({"schedule_kind": "keepalive"}) is None
    assert reg._floor_for_entry({"schedule_kind": None}) is None


def _mini_probe(now, *, files=None, mtimes=None, launchctl=None):
    """Probe pre-loaded with the mini manifest + healthy logs for every floored
    service; tests then break exactly one thing."""
    files = dict(files or {})
    mtimes = dict(mtimes or {})
    files.setdefault(reg.SERVICES_MANIFEST, _MINI_MANIFEST)
    for name in ("retro-trigger", "frontdoor-briefing", "actfirst-canary"):
        p = f"{reg.CABINET_LOG_DIR}/{name}.log"
        files.setdefault(p, "[ok]\n")
        mtimes.setdefault(p, now.timestamp())
    return FakeProbe(now=now, files=files, mtimes=mtimes, launchctl=launchctl)


def test_cron_manifest_all_healthy_passes():
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    probe = _mini_probe(now)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True
    # launchd not observable → floors-only wording, never a failure
    assert "launchd scan unavailable" in res.detail


def test_cron_retro_trigger_fatal_marker_caught():
    """Incident-of-record #1: retro-trigger logged FATAL hourly (redis-cli not
    found under launchd's minimal PATH) but only status-sweep was watched. With
    manifest-derived coverage the FATAL tail pages on the first sweep."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    p = f"{reg.CABINET_LOG_DIR}/retro-trigger.log"
    probe = _mini_probe(now, files={
        p: "[2026-07-04] FATAL: triggers lib not found\n"})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "retro-trigger" in res.detail and "FATAL" in res.detail


def test_cron_command_not_found_marker_caught():
    """The launchd-minimal-PATH class itself ('redis-cli: command not found')
    is a first-class marker now."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    p = f"{reg.CABINET_LOG_DIR}/retro-trigger.log"
    probe = _mini_probe(now, files={
        p: "cabinet/cron/retro-trigger.sh: line 12: redis-cli: command not found\n"})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "command not found" in res.detail


def test_cron_interval_stale_fails_and_calendar_generous():
    """A 3h-silent hourly job breaches its 2.17h floor; a 3h-silent DAILY
    calendar job is fine (26h floor) — cadence-aware, not one-size."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    old = (now - dt.timedelta(hours=3)).timestamp()
    probe = _mini_probe(now, mtimes={
        f"{reg.CABINET_LOG_DIR}/retro-trigger.log": old,
        f"{reg.CABINET_LOG_DIR}/frontdoor-briefing.log": old,
    })
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "retro-trigger" in res.detail and "silent" in res.detail
    assert "frontdoor-briefing" not in res.detail


def test_cron_keepalive_has_no_freshness_floor():
    """memory-worker (keepalive) with NO log at all must not freshness-flag:
    long-runners log on events; their liveness is the launchd scan's job."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    probe = _mini_probe(now)  # no memory-worker log anywhere
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True


def test_cron_keepalive_error_marker_in_err_log_caught():
    """A fresh NOGROUP in memory-worker's .err (generated-plist convention)
    pages even though keepalive rows have no freshness floor."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    p = f"{reg.GENERATED_LOG_DIR}/memory-worker.err"
    probe = _mini_probe(now,
                        files={p: "NOGROUP No such key 'cabinet:memory:embed_queue'\n"},
                        mtimes={p: now.timestamp()})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "memory-worker" in res.detail and "NOGROUP" in res.detail


def test_cron_old_error_marker_ages_out():
    """A marker in a log older than the scan window (keepalive → 24h) is
    archaeology, not a live failure — must NOT page forever."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    p = f"{reg.GENERATED_LOG_DIR}/memory-worker.err"
    probe = _mini_probe(now,
                        files={p: "NOGROUP No such key\n"},
                        mtimes={p: (now - dt.timedelta(hours=30)).timestamp()})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True


def test_cron_declared_but_not_loaded_caught():
    """Incident-of-record #2: memory-worker sat in services.yml while five hooks
    fed its queue — never scheduled. With a visible launchctl surface missing
    its label, the manifest row itself now pages."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    ll = {  # everything loaded EXCEPT memory-worker; officer label present
        "com.cabinet.officer.cos": {"pid": 4242, "status": 0},
        "com.cabinet.retro-trigger": {"pid": None, "status": 0},
        "com.cabinet.frontdoor-briefing": {"pid": None, "status": 0},
        "com.cabinet.actfirst-canary": {"pid": None, "status": 0},
    }
    probe = _mini_probe(now, launchctl=ll)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "memory-worker" in res.detail and "not loaded" in res.detail


def test_cron_nonzero_exit_status_caught_officers_excluded():
    """retro-trigger exiting 127 hourly (PATH class) is a page even while its
    log looks quiet; an officer wrapper's non-zero exit is NOT (session
    lifecycle is the supervisor's domain, wrappers exit non-zero by design)."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    ll = {
        "com.cabinet.officer.cos": {"pid": None, "status": 15},   # excluded
        "com.cabinet.retro-trigger": {"pid": None, "status": 127},
        "com.cabinet.memory-worker": {"pid": 777, "status": 0},
        "com.cabinet.frontdoor-briefing": {"pid": None, "status": 0},
        "com.cabinet.actfirst-canary": {"pid": None, "status": 0},
    }
    probe = _mini_probe(now, launchctl=ll)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "com.cabinet.retro-trigger: last exit status 127" in res.detail
    assert "officer.cos" not in res.detail


def test_cron_unrostered_officer_label_not_flagged():
    """Self-review fix: an officer hired after the manifest was written
    (com.cabinet.officer.<slug>, no row) exits non-zero legitimately like any
    session wrapper — must NOT page. The cos-inbound poller (same prefix but a
    WATCHED daemon row) must still be covered."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    ll = {
        "com.cabinet.officer.mari-ceo": {"pid": None, "status": 1},   # unrostered
        "com.cabinet.retro-trigger": {"pid": None, "status": 0},
        "com.cabinet.memory-worker": {"pid": 777, "status": 0},
        "com.cabinet.frontdoor-briefing": {"pid": None, "status": 0},
        "com.cabinet.actfirst-canary": {"pid": None, "status": 0},
    }
    probe = _mini_probe(now, launchctl=ll)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True
    assert "mari-ceo" not in res.detail


def test_cron_watched_daemon_under_officer_prefix_still_flagged():
    """cos-inbound (com.cabinet.officer.cos-inbound, kind daemon) must NOT be
    swallowed by the officer-prefix exclusion — a crash-looping poller pages.
    pid is None here because that IS the crash-looper's steady state: a dying
    keepalive job sits throttled (ThrottleInterval 30) between restarts, and
    only a NOT-running job's `status` describes its most recent completed run
    (see the running-job skip in scan (c))."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    manifest = _MINI_MANIFEST + """\
  - name: cos-inbound
    label: com.cabinet.officer.cos-inbound
    kind: daemon
    command: bash cabinet/scripts/start-inbound-poller.sh cos
    schedule: keepalive
"""
    ll = {
        "com.cabinet.officer.cos-inbound": {"pid": None, "status": 78},
        "com.cabinet.retro-trigger": {"pid": None, "status": 0},
        "com.cabinet.memory-worker": {"pid": 777, "status": 0},
        "com.cabinet.frontdoor-briefing": {"pid": None, "status": 0},
        "com.cabinet.actfirst-canary": {"pid": None, "status": 0},
    }
    probe = _mini_probe(now, files={reg.SERVICES_MANIFEST: manifest}, launchctl=ll)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "com.cabinet.officer.cos-inbound: last exit status 78" in res.detail


def test_cron_running_job_prior_exit_status_ignored():
    """Adversarial-review regression (lane-ops 2026-07-04, incident-of-record):
    the LIVE cos-inbound poller sat healthy at pid 29983 with launchctl status
    -15 — the PREVIOUS incarnation's routine SIGTERM from a reload — and the
    first cut of scan (c) would have paged the Chair on it every sweep forever
    (the pipe-alarm-flood class). A RUNNING job's prior-incarnation exit is
    history, not state: quiet while pid is set; page the moment the same
    label is observed NOT running with that non-zero status (a keepalive
    daemon that stayed down after a SIGTERM genuinely is a failure)."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    manifest = _MINI_MANIFEST + """\
  - name: cos-inbound
    label: com.cabinet.officer.cos-inbound
    kind: daemon
    command: bash cabinet/scripts/start-inbound-poller.sh cos
    schedule: keepalive
"""
    base_ll = {
        "com.cabinet.retro-trigger": {"pid": None, "status": 0},
        "com.cabinet.memory-worker": {"pid": 777, "status": 0},
        "com.cabinet.frontdoor-briefing": {"pid": None, "status": 0},
        "com.cabinet.actfirst-canary": {"pid": None, "status": 0},
    }
    # Running with the previous incarnation's SIGTERM → healthy, no page.
    ll_running = dict(base_ll)
    ll_running["com.cabinet.officer.cos-inbound"] = {"pid": 29983, "status": -15}
    probe = _mini_probe(now, files={reg.SERVICES_MANIFEST: manifest},
                        launchctl=ll_running)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True
    assert "cos-inbound" not in res.detail
    # Same label, same -15, but NOT running → the daemon stayed down: page.
    ll_down = dict(base_ll)
    ll_down["com.cabinet.officer.cos-inbound"] = {"pid": None, "status": -15}
    probe = _mini_probe(now, files={reg.SERVICES_MANIFEST: manifest},
                        launchctl=ll_down)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "com.cabinet.officer.cos-inbound: last exit status -15" in res.detail


def test_cron_disabled_row_fully_excluded():
    """draft-lane is disabled:true (parked by the act-not-draft ruling): no
    freshness floor, no not-loaded page — declared-parked is not a failure."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    ll = {  # draft-lane absent from launchd (its plist is .disabled) — fine
        "com.cabinet.officer.cos": {"pid": 4242, "status": 0},
        "com.cabinet.retro-trigger": {"pid": None, "status": 0},
        "com.cabinet.memory-worker": {"pid": 777, "status": 0},
        "com.cabinet.frontdoor-briefing": {"pid": None, "status": 0},
        "com.cabinet.actfirst-canary": {"pid": None, "status": 0},
    }
    probe = _mini_probe(now, launchctl=ll)
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True
    assert "draft-lane" not in res.detail


def test_cron_generated_and_legacy_log_dirs_both_count():
    """Freshness takes the NEWEST mtime across both plist-era log locations, so
    a service migrated from ~/.cabinet/logs to ~/Library/Logs/cabinet (e.g.
    the regenerated retro-trigger) never false-alarms mid-transition."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    legacy = f"{reg.CABINET_LOG_DIR}/retro-trigger.log"
    gen = f"{reg.GENERATED_LOG_DIR}/retro-trigger.log"
    probe = _mini_probe(now, files={gen: "[ok] No retro yet\n"}, mtimes={
        legacy: (now - dt.timedelta(days=3)).timestamp(),  # old era, stale
        gen: now.timestamp(),                              # new era, fresh
    })
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is True


def test_cron_missing_manifest_falls_back_to_static():
    """No manifest readable → the legacy static status-sweep row still applies
    (the watchdog is never blinded by a manifest move/rewrite). This is also
    the compatibility path the pre-existing status-sweep tests exercise."""
    now = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)
    probe = FakeProbe(now=now, files={}, mtimes={})
    res = reg.verify_no_silent_cron_failure(probe)
    assert res.ok is False
    assert "status-sweep" in res.detail  # fallback row, no log → flagged


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
    # 40h exceeds every cadence-aligned ceiling (max 28h for teams-graph since
    # the 2026-07-03 sleep-aware thresholds; 5h was the pre-change fixture).
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    old = (now - dt.timedelta(hours=40)).timestamp()
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


def test_reflection_toolcall_counts_as_work_signal():
    """HIGH-8 (2026-07-03): last-experience is 2h-TTL and its writer stalled —
    the check read every officer as idle and logged vacuous green. The durable
    last-toolcall stamp now counts as the work signal, so a working officer
    with no reflection goes honestly red."""
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    redis = {"cabinet:last-toolcall:cos":
             (now - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    probe = FakeProbe(now=now, redis=redis)
    res = reg.verify_officer_reflection(probe)
    assert res.ok is False
    assert "cos" in res.detail and "never reflected" in res.detail


def test_reflection_stale_toolcall_is_idle():
    """A toolcall OLDER than the ceiling window is not recent work — the
    officer is idle and not expected to reflect."""
    now = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.timezone.utc)
    redis = {"cabinet:last-toolcall:cos":
             (now - dt.timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    probe = FakeProbe(now=now, redis=redis)
    res = reg.verify_officer_reflection(probe)
    assert res.ok is True
