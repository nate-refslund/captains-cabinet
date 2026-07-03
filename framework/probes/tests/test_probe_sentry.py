"""B2.5 Sentry probe — FIXTURED only (zero live Sentry/git). Mirrors the
reference GitHub-probe tests: pure classify truth-table + injected-fake client,
never touches Nate's Sentry org."""
from __future__ import annotations

from datetime import datetime, timezone

from framework.acting import loop
from framework.probes import correlation as c
from framework.probes import lib
from framework.probes import probe_sentry as ps

_NOW = datetime(2026, 7, 3, 4, 0, 0, tzinfo=timezone.utc)   # fixed cycle clock


# --- pure time helpers -------------------------------------------------------

def test_within_window():
    # 2h-old deploy is within the 6h window; 8h-old is not; unparseable/absent no.
    assert ps._within_window("2026-07-03T02:00:00Z", _NOW) is True
    assert ps._within_window("2026-07-02T20:00:00Z", _NOW) is False
    assert ps._within_window(None, _NOW) is False
    assert ps._within_window("not-a-time", _NOW) is False
    # future deploy (clock skew) is not within the window
    assert ps._within_window("2026-07-03T05:00:00Z", _NOW) is False


def test_advanced_requires_strictly_newer_with_a_prior():
    assert ps._advanced("2026-07-03T03:00:00Z", "2026-07-03T03:30:00Z") is True
    assert ps._advanced("2026-07-03T03:30:00Z", "2026-07-03T03:30:00Z") is False  # frozen
    assert ps._advanced(None, "2026-07-03T03:30:00Z") is False   # first sighting
    assert ps._advanced("2026-07-03T03:30:00Z", None) is False   # no current read
    assert ps._advanced("2026-07-03T03:30:00Z", "2026-07-03T03:00:00Z") is False  # went back


# --- pure classify truth table ----------------------------------------------

def test_classify_regressed():
    st = {"burn_rate": 3.0, "baseline": 1.0, "new_issues": 4}
    status, probe_status, ev = ps.classify(st, within_window=True, last_event_advanced=True)
    assert (status, probe_status) == ("failed", "regressed")
    assert "4 new issue(s)" in ev
    # a spike emits regardless of feed freshness (a spike is not silence)
    assert ps.classify(st, within_window=True, last_event_advanced=False)[:2] == ("failed", "regressed")


def test_classify_within_budget_ok_only_when_feed_live():
    st = {"burn_rate": 0.5, "baseline": 1.0}
    assert ps.classify(st, within_window=True, last_event_advanced=True)[:2] == ("ok", "within_budget")
    # same numbers, frozen feed → NOT ok; honest could_not_observe
    assert ps.classify(st, within_window=True, last_event_advanced=False)[:2] == ("unknown", "could_not_observe")


def test_classify_unknown_branches():
    # no baseline yet
    assert ps.classify({"burn_rate": 5.0, "baseline": None},
                       within_window=True, last_event_advanced=True)[:2] == ("unknown", "held")
    assert ps.classify({"burn_rate": 5.0, "baseline": 0},
                       within_window=True, last_event_advanced=True)[:2] == ("unknown", "held")
    # outside the 6h window → cannot attribute even a big spike
    assert ps.classify({"burn_rate": 9.0, "baseline": 1.0},
                       within_window=False, last_event_advanced=True)[:2] == ("unknown", "held")
    # no burn reading at all
    assert ps.classify({"burn_rate": None, "baseline": 1.0},
                       within_window=True, last_event_advanced=True)[:2] == ("unknown", "could_not_observe")
    # elevated but below the regression factor (baseline < burn < 1.5×) → dead-band
    assert ps.classify({"burn_rate": 1.2, "baseline": 1.0},
                       within_window=True, last_event_advanced=True)[:2] == ("unknown", "held")


# --- fixtured client ---------------------------------------------------------

class FakeSentry:
    def __init__(self, stats, baseline=1.0, commits=("sha1",)):
        self._stats, self._baseline, self._commits = stats, baseline, list(commits)

    def release_stats(self, org, project):
        return self._stats

    def baseline(self, org, project):
        return self._baseline

    def local_commits_since(self, window="1 hour ago"):
        return self._commits


def _decided(cid, subject="sentry-release"):
    p = loop.proposal_event(actor={"kind": "officer", "id": "polads-ceo"},
                            lane="feature-impl", subject=subject,
                            ts="2026-07-03T01:00:00Z", refs=[c.ref_for(cid)])
    p["proposal"]["decision"] = "approved"
    p["proposal"]["decided_at"] = "2026-07-03T01:00:00Z"
    return p


def _release(cid, *, version="v-sha-1", burn=None, deployed="2026-07-03T02:00:00Z",
             last_event="2026-07-03T03:30:00Z", new_issues=None, trailer=True):
    body = f"Ship the thing\n\n{c.git_trailer(cid)}" if (trailer and cid) else "no trailer here"
    return {"version": version, "deployed_at": deployed, "last_event": last_event,
            "new_issues": new_issues, "burn_rate": burn, "commit_message": body}


def _record(sink, **kw):
    sink.append(kw)
    return {"emitted": True, "status": kw["status"], "probe_status": kw["probe_status"]}


def test_run_probe_emits_regressed_failed():
    cid = c.mint()
    stats = [_release(cid, burn=3.0, new_issues=5)]
    emitted = []
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry(stats, baseline=1.0), now=_NOW,
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "pinged")
    assert r["fresh"] is True
    assert len(r["emitted"]) == 1 and r["emitted"][0]["status"] == "failed"
    assert emitted[0]["status"] == "failed" and emitted[0]["probe_status"] == "regressed"
    assert emitted[0]["confidence"] == "high" and emitted[0]["source"] == "sentry"


def test_run_probe_within_budget_ok_when_feed_advanced():
    cid = c.mint()
    stats = [_release(cid, version="v9", burn=0.4, last_event="2026-07-03T03:30:00Z")]
    prior = {"v9": "2026-07-03T03:00:00Z"}          # older prior → feed advanced
    emitted = []
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry(stats, baseline=1.0), now=_NOW,
                     prior_seen=prior, rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "ok"
    assert emitted[0]["probe_status"] == "within_budget"
    assert r["seen"]["v9"] == "2026-07-03T03:30:00Z"   # clock advanced for next cycle


def test_run_probe_frozen_feed_refuses_healthy_zero():
    # burn is within budget, but last-event did NOT advance since last cycle →
    # Sentry-silent, NOT a clean zero → unknown/could_not_observe (never ok).
    cid = c.mint()
    frozen = "2026-07-03T03:30:00Z"
    stats = [_release(cid, version="v9", burn=0.1, last_event=frozen)]
    prior = {"v9": frozen}
    emitted = []
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry(stats, baseline=1.0), now=_NOW,
                     prior_seen=prior, rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "unknown"
    assert emitted[0]["probe_status"] == "could_not_observe"


def test_run_probe_first_sighting_within_budget_is_unknown():
    # no prior last-event → cannot prove the feed is live → conservative unknown
    cid = c.mint()
    stats = [_release(cid, version="v9", burn=0.4)]
    emitted = []
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry(stats, baseline=1.0), now=_NOW,
                     prior_seen={}, rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "unknown"
    assert emitted[0]["probe_status"] == "could_not_observe"


def test_run_probe_outside_window_unknown_even_with_spike():
    cid = c.mint()
    stats = [_release(cid, burn=9.0, deployed="2026-07-02T20:00:00Z")]   # 8h old
    emitted = []
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry(stats, baseline=1.0), now=_NOW,
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "unknown"
    assert emitted[0]["probe_status"] == "held"


def test_run_probe_freshness_silent_source_pages_no_emit():
    # empty Sentry feed but local commits landed → not fresh: hc fail, no emit
    pinged = []
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry([], baseline=1.0, commits=["s1", "s2"]),
                     now=_NOW, rows=[],
                     emit=lambda **kw: pinged.append(("emit",)),
                     hc=lambda slug, fail=False: pinged.append(("hc", fail)))
    assert r["fresh"] is False
    assert ("hc", True) in pinged and ("emit",) not in pinged


def test_run_probe_unattributable_cid_skipped():
    cid = c.mint()   # valid trailer, but NO matching decided proposal in rows
    stats = [_release(cid, burn=3.0)]
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry(stats, baseline=1.0), now=_NOW,
                     rows=[],                       # empty ledger
                     emit=lib.emit_outcome, hc=lambda *a, **k: "")
    assert r["emitted"] == [] and r["skipped"][0]["reason"] == "unattributable-cid"


def test_run_probe_no_trailer_skipped_no_cid():
    # a release whose commit carries no Cabinet trailer is skipped, never joined
    stats = [_release(None, version="v-untagged", trailer=False, burn=3.0)]
    emitted = []
    r = ps.run_probe(org="step-network", project="polads",
                     client=FakeSentry(stats, baseline=1.0), now=_NOW,
                     rows=[], emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"] == [] and emitted == []
    assert r["skipped"][0]["reason"] == "no-cid"
    assert r["seen"]["v-untagged"] == "2026-07-03T03:30:00Z"   # clock still tracked
