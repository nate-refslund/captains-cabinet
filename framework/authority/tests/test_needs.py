"""SOV-1 — the ONE needs-ledger [FI-3]: O_APPEND JSONL, fingerprint ids,
lifecycle verbs, never-raises, filing-seam short-circuit.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework import evidence_mirror as EM
from framework.authority import needs as N
from framework.authority import posture as P

NOW = "2026-07-10T12:00:00Z"

# Samples taken by the hook-latency arms below; the budget is asserted against
# the MINIMUM (see test_filing_latency_smoke for why).
_LATENCY_SAMPLES = 15
# Depth the deep samples are taken at. The evidence mirror caps a trial at
# MAX_MIRROR_EVENTS_PER_TRIAL (500) before rolling to a fresh day segment, so
# this is the deepest trial that exists in production, not a hypothetical one;
# the samples land at 480..494 and stay under the cap.
_DEEP_TRIAL_EVENTS = 480
# Trial depth may eat at most this much of the 50ms hook budget (20%).
_DEPTH_BUDGET_S = 0.010
# Frozen so the mirror's day-bounded trial id cannot roll mid-measurement.
_MIRROR_DAY = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("CABINET_POSTURE", "CABINET_ID", "CABINET_ROOT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    # Most tests exercise the WIRED seam; the no-op test clears this.
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    # The lifecycle assertions use the fixed NOW timeline below. Freeze
    # implicit writes to that same clock so the 30/90-day boundary tests do
    # not decay as the real calendar advances.
    real_now = N._now
    monkeypatch.setattr(
        N, "_now", lambda value=None: real_now(NOW if value is None else value)
    )


def file_need(root, **over):
    kw = dict(kind="standing_grant", risk_class="external_comms",
              action_type="external_email", lane="bakery",
              why="blocked step needs a grant", filed_by="test", root=root)
    kw.update(over)
    return N.file_need(kw.pop("kind"), **kw)


# ---------------------------------------------------------------------------
# Ids: deterministic content fingerprints
# ---------------------------------------------------------------------------

def test_need_id_deterministic_and_hex8():
    a = N.need_id("standing_grant", "external_comms", "external_email", "bakery")
    b = N.need_id("standing_grant", "external_comms", "external_email", "bakery")
    assert a == b
    assert re.fullmatch(r"NEED-[0-9a-f]{8}", a)
    assert a != N.need_id("standing_grant", "external_comms", "external_email", "newsletter")


def test_need_id_varies_with_cabinet_id(monkeypatch):
    a = N.need_id("access")
    monkeypatch.setenv("CABINET_ID", "mini-bakery")
    assert N.need_id("access") != a


# ---------------------------------------------------------------------------
# Filing seam: needs_enabled short-circuit (bit-identical default)
# ---------------------------------------------------------------------------

def test_disabled_seam_is_a_total_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    # The enforcing disjunct is an ENABLING condition too — this test's
    # premise is "no enabling condition present", so it must be cleared
    # explicitly rather than assumed absent from the ambient environment.
    monkeypatch.delenv("CABINET_AUTHORITY_ENFORCING", raising=False)
    assert N.needs_enabled(tmp_path) is False
    assert file_need(tmp_path) is None
    assert not N.ledger_path(tmp_path).exists()


def test_enabled_by_live_authority_enforcement(tmp_path, monkeypatch):
    """Live enforcement wires the needs plane (2026-07-27 direction gate).

    The guardian no-op existed so the DEFAULT world stays bit-identical, and
    the default world is enforcement OFF — where the matrix is skipped
    entirely and there are no refusals to record. Once the Captain flips
    enforcement on, refusals happen in volume and leaving the ledger a no-op
    is what made a withheld step leave no trace at all.
    """
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.setenv("CABINET_AUTHORITY_ENFORCING", "1")
    assert N.needs_enabled(tmp_path) is True


def test_authority_enforcing_FILE_does_not_wire_needs(tmp_path, monkeypatch):
    """The `authority-enforcing` FILE must NOT wire this seam.

    It is a different, already-true switch (Captain 2026-07-03): its scope is
    the typed STATELESS policy set, which EXCLUDES `authority_matrix`. Every
    deployment carries the file, so treating it as the matrix trigger turns
    filing on everywhere and the guardian default world stops being
    bit-identical — six digest/gate parity tests red when it did.
    """
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.delenv("CABINET_AUTHORITY_ENFORCING", raising=False)
    flag = tmp_path / "instance" / "config" / "authority-enforcing"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("flipped: 2026-07-03\nscope: typed STATELESS policy set\n")
    assert N.needs_enabled(tmp_path) is False


def test_enabled_by_flag_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    flag = tmp_path / "instance" / "config" / "needs-wired"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("")
    assert N.needs_enabled(tmp_path) is True


def test_enabled_by_sovereign_posture(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    d = tmp_path / "instance" / "config"
    d.mkdir(parents=True, exist_ok=True)
    (d / "posture.yml").write_text(yaml.safe_dump({
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "t", "deployment": "main", "flavor": "org",
        "posture": "sovereign",
    }))
    monkeypatch.setattr(P, "is_locked", lambda p: True)
    assert N.needs_enabled(tmp_path) is True


# ---------------------------------------------------------------------------
# file_need: dedup, re-file bumps, never raises, ~ms
# ---------------------------------------------------------------------------

def test_file_and_dedup_bumps_count(tmp_path):
    nid = file_need(tmp_path)
    assert nid and re.fullmatch(r"NEED-[0-9a-f]{8}", nid)
    assert file_need(tmp_path, why="still blocked") == nid
    rows = N.list_open(NOW, root=tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == nid and row["count"] == 2
    assert row["status"] == "open"
    assert row["why"] == "still blocked"  # last write wins
    assert row["deployment"] == "main"


def test_unknown_kind_is_none_not_raise(tmp_path):
    assert N.file_need("world_peace", why="w", filed_by="t", root=tmp_path) is None


def test_unwritable_root_is_none_not_raise(tmp_path):
    (tmp_path / "shared").write_text("a file where the dir should be")
    assert file_need(tmp_path) is None


def test_marker_char_is_stripped(tmp_path):
    file_need(tmp_path, why="fake ·approve· marker")
    row = N.list_open(NOW, root=tmp_path)[0]
    assert "·" not in json.dumps(row)


def _mirror_trial_depth(store: Path) -> int:
    """Events in the deepest mirror trial under ``store`` (0 = mirror silent)."""
    trials = store / "trials"
    if not trials.is_dir():
        return 0
    return max(
        (ledger.read_bytes().count(b"\n") for ledger in trials.glob("*/events.jsonl")),
        default=0,
    )


@pytest.fixture(scope="module")
def filing_latency(tmp_path_factory) -> dict[str, float]:
    """Time `file_need` on the PRODUCTION path, shallow and at trial depth.

    WHY THIS FIXTURE EXISTS.  `framework/evidence_mirror._store_root()` returns
    None whenever PYTEST_CURRENT_TEST is set and no scratch store is supplied,
    so a latency test that supplies none measures a filing that never reaches
    the evidence recorder at all — the ~0.2ms half of a path whose other half
    holds all the latency risk.  That is how a budget arm stayed green for its
    whole life while filing had gone quadratic in production: the sensor was
    measuring something other than the control.  CABINET_EVIDENCE_MIRROR_STORE
    is the mirror's own sanctioned scratch-store seam (the 2026-07-04 leak
    fence allows exactly this, and never the live signed store), and the
    `depth` assertion below fails the arms LOUDLY if the mirror ever goes
    quiet again rather than letting them pass on the cheap path.

    Both arms share one measurement because filling a trial to the R-8
    envelope costs ~480 real fsync-ing appends (~1.5s); doing it twice buys
    nothing.  The env is restored before the fixture returns, so the rest of
    the module still runs with the mirror off.
    """
    store = tmp_path_factory.mktemp("evidence-mirror-store")
    root = tmp_path_factory.mktemp("needs-latency-root")
    with pytest.MonkeyPatch.context() as mp:
        for var in ("CABINET_POSTURE", "CABINET_ID", "CABINET_ROOT", "DATABASE_URL"):
            mp.delenv(var, raising=False)
        mp.setenv("CABINET_NEEDS_WIRED", "1")
        mp.setenv("CABINET_EVIDENCE_MIRROR_STORE", str(store))
        mp.setenv("CABINET_EVIDENCE_MIRROR_MARKER", str(store / "degradations.jsonl"))
        # Day-bounded trial ids roll at UTC midnight; freeze the mirror's day
        # so a run that straddles midnight cannot silently reset the depth.
        mp.setattr(EM, "_utc_now", lambda: _MIRROR_DAY)
        EM._reset_state()
        try:
            file_need(root)  # warm the ledger, the imports and the page cache
            shallow = []
            for _ in range(_LATENCY_SAMPLES):
                start = time.perf_counter()
                file_need(root)
                shallow.append(time.perf_counter() - start)
            shallow_depth = _mirror_trial_depth(store)
            # BOUNDED, not `while depth < target`.  The `deep_depth` assertion
            # below is this fixture's anti-vacuity guard, and an unbounded fill
            # is what stops it ever being reached: with the mirror silent the
            # depth stays 0 and the loop spins forever.  MEASURED 2026-07-28 by
            # deleting CABINET_EVIDENCE_MIRROR_STORE from this fixture — it was
            # still running at 120s instead of failing, which in CI is a
            # 30-minute job timeout reading as infrastructure rather than as the
            # named defect.  The ceiling is twice the fill a healthy run needs,
            # so it cannot trip on one; exhausting it drops through to that
            # assert, which says what actually went wrong (re-probed with the
            # same deletion: both arms now ERROR in 1.4s).
            for _ in range(_DEEP_TRIAL_EVENTS * 2):
                if _mirror_trial_depth(store) >= _DEEP_TRIAL_EVENTS:
                    break
                file_need(root)
            deep = []
            for _ in range(_LATENCY_SAMPLES):
                start = time.perf_counter()
                file_need(root)
                deep.append(time.perf_counter() - start)
            deep_depth = _mirror_trial_depth(store)
        finally:
            EM._reset_state()
    assert deep_depth >= _DEEP_TRIAL_EVENTS, (
        f"the evidence mirror never filled a trial (depth {deep_depth}) — these arms "
        "would be measuring the disabled-mirror short-circuit, not the production path"
    )
    return {
        "shallow": shallow, "deep": deep,
        "shallow_best": min(shallow), "deep_best": min(deep),
        "shallow_depth": shallow_depth, "deep_depth": deep_depth,
    }


def test_filing_latency_does_not_grow_with_trial_depth(filing_latency):
    """Filing must cost the same at the deepest live evidence trial as at a
    fresh one — the sensor for the defect the budget arm below cannot see.

    THE DEFECT IT CATCHES.  `file_need` -> `_emit` -> the evidence mirror ->
    `EvidenceRecorder.append`, and append verifies the trial before extending
    it.  Re-verifying the WHOLE trial per append is O(n) per filing and
    O(n^2) per trial; measured on the pre-fix code at the depths this fixture
    actually samples, filing cost 1.5ms at depth 16 and 35.9ms at depth 495 —
    34ms of pure depth against a 50ms budget.

    WHY A DIFFERENCE AND NOT AN ABSOLUTE.  The absolute number is dominated by
    fsync, which varies ~10x across the machines this runs on, so an absolute
    bound is red on a slow disk and green on a fast one for the SAME code.
    Subtracting the shallow measurement cancels that constant and leaves only
    the part that scales with trial depth, which is the actual defect.  Both
    terms are best-of-N minima, so scheduler noise (one-sided: it can only
    inflate) cannot manufacture growth.

    Mutation-proven 2026-07-28 against the pre-fix code: 34.4ms of growth
    against this 10ms allowance, RED by 3.4x. After the fix: 1.7ms, green by
    5.9x. Two-sided margins on purpose — a bound that only one side clears is
    a bound that will flake or never fire.
    """
    growth = filing_latency["deep_best"] - filing_latency["shallow_best"]
    assert growth < _DEPTH_BUDGET_S, (
        f"filing costs {growth * 1e3:.1f}ms MORE at trial depth "
        f"{filing_latency['deep_depth']} than at depth "
        f"{filing_latency['shallow_depth']}, over the {_DEPTH_BUDGET_S * 1e3:.0f}ms "
        "depth allowance: the evidence append is scaling with trial length again. "
        f"shallow={filing_latency['shallow_best'] * 1e3:.2f}ms "
        f"deep={filing_latency['deep_best'] * 1e3:.2f}ms"
    )


def test_filing_latency_smoke(filing_latency):
    """The `<50ms` hook-latency budget — best of N, not a single sample.

    THE BUDGET IS REAL AND IS NOT RELAXED HERE. `file_need` sits on the gate's
    hook path (`frontdoor/action_exec.py`, `policy_engine`'s sovereign ceiling
    branch), so a filing that stalls stalls the acting chain; the `<50ms`
    number is the SOV-1 lane's own test contract in
    `docs/plans/sovereign-build-spec-2026-07-04.md`, not a number picked here.
    It stays 50ms.

    WHAT CHANGED (2026-07-28) IS THE STATISTIC. Filing costs ~0.2ms, so a
    single wall-clock sample against a 50ms bound is not measuring this code —
    it is measuring whether the OS descheduled the process once. The 06:03Z
    scheduled run 30333546103 recorded 73ms on commit 8ffeae51, a ~300x
    outlier, on an UNCHANGED commit that was green on its own push run
    30314036148 — and green in the same run's `framework-tests` job minutes
    earlier. Scheduling noise is strictly ONE-SIDED: it can inflate a sample,
    never deflate one. So the MINIMUM over N samples is the estimator of what
    the operation actually costs, and that is what the budget is asserted
    against. (The `timeit` doctrine, for the same reason.)

    It still FAILS for its named reason: genuinely slow code is slow in EVERY
    sample, so the minimum moves with it. Mutation-proven 2026-07-28, each
    reverted to green afterwards — a 60ms `sleep` in `_file_need` turns it red
    at 61.1ms; a quadratic re-read injected into `_read_rows` turns it red at
    x5000 (61.7ms) and x20000 (245.6ms). Conversely a ONE-SHOT 200ms stall on
    a single sample leaves it green, while the single-sample form it replaced
    goes red on that same stall — which is exactly the CI failure above.

    WHAT CHANGED (2026-07-28, second edit of the day) IS THE PATH MEASURED.
    This arm used to run with the evidence mirror short-circuited to None by
    its own pytest fence, so it measured a filing that never reached the
    evidence recorder — the cheap half of the path, ~0.2ms, forever green
    while the expensive half went quadratic in production. It now measures the
    real thing, at the deepest trial the R-8 envelope allows. See the
    `filing_latency` fixture.

    KNOWN INSENSITIVITY, stated rather than papered over: even on the
    production path filing costs ~3ms against a 50ms budget, so this arm alone
    still only trips on a ~16x regression, and how much of the budget fsync
    eats varies ~10x by machine — it passes at 35.9ms against the very code
    whose depth cost this branch removed. That is precisely why
    test_filing_latency_does_not_grow_with_trial_depth exists beside it: this
    arm holds the SPEC's number, that arm is the sensitive sensor. And a
    regression that is slow only OCCASIONALLY — a periodic compaction, an
    every-Nth fsync — hides under a minimum by construction. This is the
    spec's hook-latency SMOKE; a percentile SLO on this path would be a NEW
    requirement, not a bug fix, and is not smuggled in here.
    """
    samples = filing_latency["deep"]
    best = filing_latency["deep_best"]
    assert best < 0.050, (  # <50ms hook budget
        f"filing latency {best * 1e3:.1f}ms at trial depth "
        f"{filing_latency['deep_depth']} blows the 50ms hook budget in the "
        f"BEST of {_LATENCY_SAMPLES} samples, so this is the code and not the "
        f"runner; all samples (ms): {[round(s * 1e3, 2) for s in samples]}"
    )


def test_concurrent_appends_tolerated(tmp_path):
    N.ledger_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)

    def worker():
        for _ in range(25):
            file_need(tmp_path)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Every line is intact JSON; the merged view is exactly one row.
    lines = N.ledger_path(tmp_path).read_text().splitlines()
    assert len(lines) == 200
    for line in lines:
        assert json.loads(line)["id"]
    assert len(N.list_open(NOW, root=tmp_path)) == 1


# ---------------------------------------------------------------------------
# Narrowest proposed grant line (kind=standing_grant auto-compose)
# ---------------------------------------------------------------------------

def test_standing_grant_composes_narrowest_line(tmp_path):
    nid = file_need(tmp_path, scope_hint={"recipient": "ida@testburg.example"})
    row = N.list_open(NOW, root=tmp_path)[0]
    line = row["proposed_grant_line"]
    parsed = yaml.safe_load(line)
    assert isinstance(parsed, list) and len(parsed) == 1
    g = parsed[0]
    assert g["id"] == "GRANT-" + nid[len("NEED-"):]
    assert g["action_types"] == ["external_email"]  # never empty
    assert g["lanes"] == ["bakery"]                 # never '*'
    assert g["rate"] == {"max_per_day": 1}
    assert g["scope"]["recipient_allowlist"] == ["ida@testburg.example"]
    assert g["basis"] == nid
    assert g["revoked"] is False


def test_compose_without_lane_leaves_empty_lanes(tmp_path):
    file_need(tmp_path, lane=None)
    row = N.list_open(NOW, root=tmp_path)[0]
    g = yaml.safe_load(row["proposed_grant_line"])[0]
    assert g["lanes"] == []


def test_non_grant_kinds_do_not_compose(tmp_path):
    N.file_need("credential", why="need a token", filed_by="t", root=tmp_path)
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["proposed_grant_line"] is None


# ---------------------------------------------------------------------------
# Lifecycle verbs
# ---------------------------------------------------------------------------

def test_lifecycle_open_approved_granted(tmp_path):
    nid = file_need(tmp_path)
    row = N.mark(nid, "approved_pending_apply", by="captain", root=tmp_path, now=NOW)
    assert row["status"] == "approved_pending_apply"
    assert [r["id"] for r in N.list_open(NOW, root=tmp_path)] == [nid]
    N.mark(nid, "granted", by="grant-apply.sh", root=tmp_path, now=NOW)
    assert N.list_open(NOW, root=tmp_path) == []


def test_refile_keeps_pending_apply_sticky(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "approved_pending_apply", by="captain", root=tmp_path, now=NOW)
    file_need(tmp_path)
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["status"] == "approved_pending_apply" and row["count"] == 2


def test_deny_suppresses_refile_for_90d(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "denied", by="captain", reason="not now", root=tmp_path, now=NOW)
    assert N.list_open(NOW, root=tmp_path) == []
    assert file_need(tmp_path) is None  # suppressed ⇒ no-op
    assert file_need(tmp_path, why="again") is None  # still suppressed


def test_deny_suppression_lapses(tmp_path, monkeypatch):
    nid = file_need(tmp_path)
    N.mark(nid, "denied", by="captain", root=tmp_path, now="2026-01-01T00:00:00Z")
    # 90d from 2026-01-01 is 2026-04-01; by NOW (July) the suppression lapsed.
    assert file_need(tmp_path) == nid
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["status"] == "open" and row["count"] == 2


def test_snooze_hides_then_reopens(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "snoozed", by="captain", root=tmp_path, now=NOW)
    assert N.list_open(NOW, root=tmp_path) == []
    week_later = "2026-07-18T00:00:00Z"
    rows = N.list_open(week_later, root=tmp_path)
    assert [r["id"] for r in rows] == [nid]
    assert rows[0]["status"] == "open"


def test_refile_does_not_unsnooze(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "snoozed", by="captain", root=tmp_path, now=NOW)
    assert file_need(tmp_path) == nid  # bump is recorded…
    assert N.list_open("2026-07-11T00:00:00Z", root=tmp_path) == []  # …still snoozed


def test_mark_unknown_or_bad_is_none(tmp_path):
    assert N.mark("NEED-ffffffff", "granted", by="x", root=tmp_path) is None
    nid = file_need(tmp_path)
    assert N.mark(nid, "vaporized", by="x", root=tmp_path) is None


# ---------------------------------------------------------------------------
# 30d expiry sweep on read
# ---------------------------------------------------------------------------

def test_stale_open_need_expires_on_read(tmp_path):
    file_need(tmp_path)
    much_later = "2026-08-15T00:00:00Z"  # >30d past last_seen
    assert N.list_open(much_later, root=tmp_path) == []
    merged = N._merged(N.ledger_path(tmp_path))
    assert list(merged.values())[0]["status"] == "expired"
    # Re-filing after expiry reopens with a bumped count (read at a window
    # that has not lapsed relative to the fresh last_seen).
    nid = file_need(tmp_path)
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["id"] == nid and row["status"] == "open" and row["count"] == 2


def test_pending_apply_survives_the_sweep(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "approved_pending_apply", by="captain", root=tmp_path, now=NOW)
    much_later = "2026-09-01T00:00:00Z"
    rows = N.list_open(much_later, root=tmp_path)
    assert [r["id"] for r in rows] == [nid]  # an explicit approval never rots away


# ---------------------------------------------------------------------------
# Blocking escalation + events
# ---------------------------------------------------------------------------

def test_blocking_rides_intake_at_ping_now(tmp_path, monkeypatch):
    from framework.frontdoor import intake
    seen = []
    monkeypatch.setattr(intake, "enqueue", lambda item, **kw: seen.append(item) or "1-1")
    file_need(tmp_path, cost_of_delay="blocking")
    assert len(seen) == 1
    assert seen[0]["urgency_tier"] == "ping-now"
    assert "BLOCKING need NEED-" in seen[0]["payload"]["summary"]


def test_events_emitted_to_ledger(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "granted", by="captain", root=tmp_path, now=NOW)
    events = []
    for f in (tmp_path / "events").glob("events-*.jsonl"):
        events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    types = [e["event_type"] for e in events]
    assert "need_filed" in types and "need_granted" in types


# ---------------------------------------------------------------------------
# cross_check_grants
# ---------------------------------------------------------------------------

def test_cross_check_closes_covered_grant_needs(tmp_path):
    nid = file_need(tmp_path)
    N.file_need("decision", why="unrelated", filed_by="t", root=tmp_path)

    def covers(rc, at, *, lane):
        granted = (rc, at, lane) == ("external_comms", "external_email", "bakery")
        return {"granted": granted, "grant_id": "GRANT-test1" if granted else None}

    closed = N.cross_check_grants(covers, root=tmp_path, now=NOW)
    assert closed == [nid]
    rows = N.list_open(NOW, root=tmp_path)
    assert [r["kind"] for r in rows] == ["decision"]  # the grant need closed


def test_cross_check_tolerates_broken_check_fn(tmp_path):
    file_need(tmp_path)

    def boom(rc, at, *, lane):
        raise RuntimeError("no grants table")

    assert N.cross_check_grants(boom, root=tmp_path, now=NOW) == []
    assert len(N.list_open(NOW, root=tmp_path)) == 1
