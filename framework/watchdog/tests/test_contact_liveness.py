"""test_contact_liveness — can this cabinet notice it stopped talking to its Captain?

Three properties, each asserted as an OUTCOME rather than as an internal shape:

  * the inbound-silence check FIRES when Captain contact stops, and stays quiet
    when it has not;
  * a broad outage's truncated finding list still NAMES THE CAUSE (severity
    before truncation) instead of showing eight downstream symptoms;
  * an escalation that reached nobody does NOT burn a multi-hour cooldown —
    enqueued is not delivered.

All I/O goes through the FakeProbe from test_registry (no Redis, no files, no
network).
"""
from __future__ import annotations

import datetime as dt

from framework.watchdog import registry as reg
from framework.watchdog.check import route_failure
from framework.watchdog.tests.test_registry import FakeProbe, _MINI_MANIFEST

NOW = dt.datetime(2026, 7, 25, 12, 0, tzinfo=dt.timezone.utc)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# The inbound leg: does the alarm fire when the Captain stops reaching us?
# ---------------------------------------------------------------------------
class TestInboundContact:
    def test_fires_when_captain_contact_has_stopped(self):
        """THE POINT OF THE WHOLE CHANGE. Before the timestamped sibling key
        existed this was unanswerable: the only inbound key held a message ID,
        which cannot express staleness no matter who reads it."""
        stale = NOW - dt.timedelta(days=11)
        probe = FakeProbe(now=NOW,
                          redis={reg.LAST_CAPTAIN_MSG_AT_KEY: _iso(stale)})
        res = reg.verify_captain_inbound_contact(probe)
        assert res.ok is False
        assert res.skipped is False
        assert "11.0 days" in res.detail

    def test_quiet_within_the_floor_is_not_an_alarm(self):
        """The Captain is allowed to be quiet — six days is not an incident."""
        recent = NOW - dt.timedelta(days=6)
        probe = FakeProbe(now=NOW,
                          redis={reg.LAST_CAPTAIN_MSG_AT_KEY: _iso(recent)})
        assert reg.verify_captain_inbound_contact(probe).ok is True

    def test_fires_exactly_past_the_declared_floor(self):
        just_over = NOW - dt.timedelta(seconds=reg.CAPTAIN_INBOUND_SILENCE_S + 60)
        just_under = NOW - dt.timedelta(seconds=reg.CAPTAIN_INBOUND_SILENCE_S - 60)
        assert reg.verify_captain_inbound_contact(
            FakeProbe(now=NOW, redis={reg.LAST_CAPTAIN_MSG_AT_KEY: _iso(just_over)})
        ).ok is False
        assert reg.verify_captain_inbound_contact(
            FakeProbe(now=NOW, redis={reg.LAST_CAPTAIN_MSG_AT_KEY: _iso(just_under)})
        ).ok is True

    def test_absent_stamp_skips_rather_than_pages(self):
        """A fresh cabinet has genuinely never been written to. Paging on its
        first sweep would train the reader to ignore this row."""
        res = reg.verify_captain_inbound_contact(FakeProbe(now=NOW, redis={}))
        assert res.ok is True and res.skipped is True

    def test_unparseable_stamp_skips_rather_than_pages(self):
        probe = FakeProbe(now=NOW,
                          redis={reg.LAST_CAPTAIN_MSG_AT_KEY: "not-a-timestamp"})
        res = reg.verify_captain_inbound_contact(probe)
        assert res.ok is True and res.skipped is True

    def test_detail_refuses_to_guess_between_quiet_captain_and_dead_lane(self):
        """The check genuinely cannot distinguish the two, so it must not imply
        it can — over-claiming here is what sends someone down the wrong path."""
        stale = NOW - dt.timedelta(days=30)
        probe = FakeProbe(now=NOW,
                          redis={reg.LAST_CAPTAIN_MSG_AT_KEY: _iso(stale)})
        detail = reg.verify_captain_inbound_contact(probe).detail
        assert "cannot tell the two apart" in detail

    def test_row_is_in_the_catalog_and_ships_dark(self):
        """Built and available, deliberately not enabled — arming is one line in
        instance/config/watchdog.yml, recorded there."""
        assert any(e.id == "captain-inbound-contact" for e in reg._CATALOG)
        assert not any(e.id == "captain-inbound-contact" for e in reg.EXPECTATIONS)


# ---------------------------------------------------------------------------
# The check the watchdog's author wanted and was blocked from writing.
# ---------------------------------------------------------------------------
class TestDecisionsRecencyGate:
    def _files(self, heading_date: str) -> dict:
        return {reg.CAPTAIN_DECISIONS: f"## {heading_date}\n\nsome decision\n"}

    def test_stale_decisions_with_no_contact_since_is_not_a_lapse(self):
        """Nothing was said, so nothing went unlogged. This is the false
        positive the author could not remove without a timestamp."""
        newest = NOW - dt.timedelta(days=30)
        contact = NOW - dt.timedelta(days=40)  # older than the newest entry
        probe = FakeProbe(now=NOW, files=self._files(f"{newest:%Y-%m-%d}"),
                          redis={reg.LAST_CAPTAIN_MSG_AT_KEY: _iso(contact)})
        res = reg.verify_captain_decisions_logged(probe)
        assert res.ok is True and res.skipped is True
        assert "NO Captain contact" in res.detail

    def test_stale_decisions_with_contact_since_is_still_a_lapse(self):
        """The Captain HAS spoken since the last logged decision — that is a
        real logging lapse and must still fire."""
        newest = NOW - dt.timedelta(days=30)
        contact = NOW - dt.timedelta(days=2)  # newer than the newest entry
        probe = FakeProbe(now=NOW, files=self._files(f"{newest:%Y-%m-%d}"),
                          redis={reg.LAST_CAPTAIN_MSG_AT_KEY: _iso(contact)})
        assert reg.verify_captain_decisions_logged(probe).ok is False

    def test_absent_stamp_preserves_the_original_behaviour_exactly(self):
        """Fail direction: no key (fresh cabinet, or a poller predating the
        stamp) must leave the pre-change verdict untouched, so this refinement
        can only remove false positives and never blind the check."""
        newest = NOW - dt.timedelta(days=30)
        probe = FakeProbe(now=NOW, files=self._files(f"{newest:%Y-%m-%d}"),
                          redis={})
        assert reg.verify_captain_decisions_logged(probe).ok is False


# ---------------------------------------------------------------------------
# X — severity before truncation.
# ---------------------------------------------------------------------------
def _broad_outage_manifest(n_noisy: int) -> str:
    """A manifest with many interval services plus one that will be missing from
    launchd — the shape of a broad outage."""
    rows = []
    for i in range(n_noisy):
        rows.append(
            f"  - name: noisy-{i:02d}\n"
            f"    label: com.cabinet.noisy-{i:02d}\n"
            f"    kind: cron\n"
            f"    command: bash noop.sh\n"
            f"    schedule: {{ interval_s: 3600 }}\n")
    rows.append(
        "  - name: the-cause\n"
        "    label: com.cabinet.the-cause\n"
        "    kind: cron\n"
        "    command: bash cause.sh\n"
        "    schedule: { interval_s: 3600 }\n")
    return "services:\n" + "".join(rows)


class TestSeverityBeforeTruncation:
    def _probe(self):
        n = 12
        manifest = _broad_outage_manifest(n)
        files = {reg.SERVICES_MANIFEST: manifest}
        mtimes = {}
        # Every noisy row: a FRESH log carrying an error marker (a downstream
        # SYMPTOM, severity 'marker' — the lowest rank).
        for i in range(n):
            p = f"{reg.CABINET_LOG_DIR}/noisy-{i:02d}.log"
            files[p] = "FATAL: downstream symptom\n"
            mtimes[p] = NOW.timestamp()
        # the-cause has a healthy log but launchd has never heard of it — the
        # CAUSE, severity 'not-loaded' (the highest rank), and appended LAST by
        # construction because the not-loaded scan runs after the per-row loop.
        p = f"{reg.CABINET_LOG_DIR}/the-cause.log"
        files[p] = "[ok]\n"
        mtimes[p] = NOW.timestamp()
        ll = {f"com.cabinet.noisy-{i:02d}": {"pid": None, "status": 0}
              for i in range(n)}
        return FakeProbe(now=NOW, files=files, mtimes=mtimes, launchctl=ll)

    def test_the_cause_survives_truncation(self):
        """In a broad outage the line naming the CAUSE used to be the first
        casualty: findings were truncated to the first eight in APPEND order and
        the not-loaded scan appends last. Eight symptoms survived, the cause did
        not."""
        res = reg.verify_no_silent_cron_failure(self._probe())
        assert res.ok is False
        assert "the-cause" in res.detail
        assert "not loaded in launchd" in res.detail

    def test_truncation_still_caps_at_eight_with_a_more_count(self):
        res = reg.verify_no_silent_cron_failure(self._probe())
        assert res.detail.count(";") >= 8
        assert "more" in res.detail

    def test_sort_is_stable_so_message_text_is_unchanged(self):
        """The sort must reorder findings, never rewrite them."""
        res = reg.verify_no_silent_cron_failure(self._probe())
        assert "error marker 'FATAL' in recent log tail" in res.detail


# ---------------------------------------------------------------------------
# Enqueued is not delivered — the cooldown must not be burnt on an unread page.
# ---------------------------------------------------------------------------
class _RoutingProbe(FakeProbe):
    """FakeProbe plus the delivery side-channel the real probe records."""

    def __init__(self, delivery, **kw):
        super().__init__(**kw)
        self._last_chair_delivery = delivery


def _failing_result(exp_id):
    return reg.CheckResult(exp_id, False, "something is broken")


class TestUndeliveredPageDoesNotBurnCooldown:
    def _exp(self):
        return reg.expectation_by_id("no-silent-cron-failure")

    def test_absent_chair_consumer_sets_no_cooldown(self):
        """The failure that started this: a page enqueued to a stream nobody is
        reading still bought three hours of silence."""
        exp = self._exp()
        probe = _RoutingProbe("absent", now=NOW)
        out = route_failure(probe, exp, _failing_result(exp.id))
        assert probe.triggers, "the trigger is still queued — it is durable"
        assert probe.cooldowns == {}, "an unread page must not suppress the next sweep"
        assert "NO live Chair consumer" in out

    def test_live_chair_consumer_sets_the_cooldown_as_before(self):
        exp = self._exp()
        probe = _RoutingProbe("live", now=NOW)
        out = route_failure(probe, exp, _failing_result(exp.id))
        assert probe.cooldowns, "a delivered page still dedups normally"
        assert "ESCALATED to Chair" in out

    def test_unknown_delivery_preserves_prior_behaviour(self):
        """No tmux to observe with (Docker, CI, a remote box) is NOT evidence of
        death — a detector that cannot see must not invent a verdict."""
        exp = self._exp()
        probe = _RoutingProbe("unknown", now=NOW)
        out = route_failure(probe, exp, _failing_result(exp.id))
        assert probe.cooldowns
        assert "ESCALATED to Chair" in out

    def test_probe_without_the_side_channel_preserves_prior_behaviour(self):
        """Every pre-existing test double lacks the attribute; getattr must make
        them behave exactly as they did."""
        exp = self._exp()
        probe = FakeProbe(now=NOW)
        assert not hasattr(probe, "_last_chair_delivery")
        out = route_failure(probe, exp, _failing_result(exp.id))
        assert probe.cooldowns
        assert "ESCALATED to Chair" in out

    def test_undelivered_page_re_escalates_on_the_next_sweep(self):
        """The property that matters: because no cooldown was set, the very next
        sweep tries again rather than going quiet."""
        exp = self._exp()
        probe = _RoutingProbe("absent", now=NOW)
        route_failure(probe, exp, _failing_result(exp.id))
        route_failure(probe, exp, _failing_result(exp.id))
        assert len(probe.triggers) == 2
