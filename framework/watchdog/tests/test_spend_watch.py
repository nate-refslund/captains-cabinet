"""test_spend_watch — the three rows that replaced the spend caps (2026-07-26).

The Captain removed every dollar cap and then refined the ruling: no
threshold alarm. Money is not the scarce resource; ATTENTION is. So these
rows are tested for two properties in equal measure — that they FIRE on the
shape that deserves a human, and that they are SILENT on everything else,
including on their own ignorance. A money watch that pages on a busy week, or
on an unreachable Redis, trains the reader to ignore it and is worse than no
watch at all.

Per row, four arms: fires correctly · silent on insufficient history · SKIPS
when it cannot observe · never raises.

All I/O goes through the FakeProbe from test_registry (no Redis, no files, no
network). The falsifier series is injected as file TEXT, exactly as the real
probe would read it off disk.

Run: python3.12 -m pytest framework/watchdog/tests/test_spend_watch.py -q
"""
from __future__ import annotations

import datetime as dt
import json

from framework.watchdog import registry as reg
from framework.watchdog.tests.test_registry import FakeProbe

NOW = dt.datetime(2026, 7, 26, 12, 0, tzinfo=dt.timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")


def _line(day_offset: int, *, total=None, lanes=None, output=1,
          spend_present=True) -> dict:
    """One falsifier-series line, shaped exactly like falsifier-report writes.

    `output` seeds the delivered-work numerators; `total` is the day's officer
    spend in microdollars (None = "no figures came back that day").
    """
    date = (NOW - dt.timedelta(days=day_offset)).strftime("%Y-%m-%d")
    doc = {
        "date": date,
        "acted_7d": output,
        "approved_7d": 0,
        "proactive_cards_7d": 0,
        "labels_7d": {"verdict": 0, "outcome_resolved": 0},
    }
    if spend_present:
        doc["spend"] = {"date": date, "total_cost_micro": total,
                        "officers": {"cos": total} if total is not None else None,
                        "lanes": lanes}
    return doc


def _series(docs) -> str:
    return "".join(json.dumps(d, sort_keys=True) + "\n" for d in docs)


def _probe(docs, **kw) -> FakeProbe:
    kw.setdefault("now", NOW)
    files = kw.pop("files", {})
    files[reg.FALSIFIER_SERIES] = _series(docs)
    return FakeProbe(files=files, **kw)


def _history(days=10, *, total=1_000_000, output=3, lanes=None):
    """`days` ordinary DELIVERING days, oldest first, ending yesterday."""
    return [_line(d, total=total, output=output, lanes=lanes)
            for d in range(days, 0, -1)]


# ---------------------------------------------------------------------------
# (a) spend-without-output — the one that matters.
# ---------------------------------------------------------------------------
class TestSpendWithoutOutput:
    def test_fires_when_cost_climbs_and_nothing_ships(self):
        """The runaway shape: a week with nothing acted, approved, carded or
        labelled, while the day costs several times what a delivering day
        costs. This is what removing the caps makes possible."""
        docs = _history(10) + [_line(0, total=8_000_000, output=0)]
        res = reg.verify_spend_without_output(_probe(docs))
        assert res.ok is False and res.skipped is False
        assert "SPEND WITHOUT OUTPUT" in res.detail
        assert "8.0x" in res.detail

    def test_big_but_normal_week_is_silent(self):
        """THE CAPTAIN'S REFINEMENT, asserted directly: spend 8x the median is
        NOT reportable when the work is shipping. Cost with output is the
        system doing its job."""
        docs = _history(10) + [_line(0, total=8_000_000, output=12)]
        res = reg.verify_spend_without_output(_probe(docs))
        assert res.ok is True and res.skipped is False
        assert "system working" in res.detail

    def test_quiet_cabinet_at_normal_spend_is_silent(self):
        """No output but no cost rise either — a quiet week, not a runaway.
        Firing here would page on every holiday."""
        docs = _history(10) + [_line(0, total=1_100_000, output=0)]
        res = reg.verify_spend_without_output(_probe(docs))
        assert res.ok is True and res.skipped is False
        assert "not a runaway" in res.detail

    def test_baseline_is_delivering_days_so_a_sustained_runaway_keeps_firing(self):
        """A runaway in its second week must not have normalised itself.

        The fixture is deliberately lopsided — five delivering days followed by
        NINE runaway days — because that is the only shape that can tell the
        two baselines apart. Over delivering days the median stays at what a
        productive day cost and the row still fires; over ALL days the runaway
        would have become the median and silenced itself, which is precisely
        the failure this arm exists to prevent."""
        docs = ([_line(d, total=1_000_000, output=3) for d in range(14, 9, -1)]
                + [_line(d, total=8_000_000, output=0) for d in range(9, 0, -1)]
                + [_line(0, total=8_000_000, output=0)])
        res = reg.verify_spend_without_output(_probe(docs))
        assert res.ok is False and "8.0x" in res.detail
        assert "5 delivering days" in res.detail

    def test_silent_on_insufficient_history(self):
        """Four delivering days is below the declared floor of five — a fresh
        cabinet must never page about its own first week. Silence, and the
        detail says exactly how much history is missing."""
        docs = _history(4) + [_line(0, total=9_000_000, output=0)]
        res = reg.verify_spend_without_output(_probe(docs))
        assert res.skipped is True and res.ok is True
        assert "delivering day(s) of spend history" in res.detail
        # …and one more day flips it, so the floor is what is doing the work.
        docs5 = _history(5) + [_line(0, total=9_000_000, output=0)]
        assert reg.verify_spend_without_output(_probe(docs5)).ok is False

    def test_skips_when_series_absent_or_stale(self):
        """Unobservable is neither pass nor failure."""
        empty = FakeProbe(now=NOW)          # no series file at all
        assert reg.verify_spend_without_output(empty).skipped is True
        old = [_line(d, total=1_000_000, output=3) for d in range(20, 4, -1)]
        res = reg.verify_spend_without_output(_probe(old))
        assert res.skipped is True and "stale" in res.detail

    def test_skips_when_the_day_has_no_figures(self):
        """`total_cost_micro: null` is NO EVIDENCE, never a zero — a null day
        must not read as "spent nothing" and must not be compared."""
        docs = _history(10) + [_line(0, total=None, output=0)]
        res = reg.verify_spend_without_output(_probe(docs))
        assert res.skipped is True and "no spend figures" in res.detail

    def test_skips_when_output_numerators_are_absent(self):
        """An older line carries no numerators at all. Absent output must not
        be read as zero output — that would page on every legacy line."""
        docs = _history(10)
        latest = _line(0, total=9_000_000, output=0)
        for k in ("acted_7d", "approved_7d", "proactive_cards_7d", "labels_7d"):
            latest.pop(k)
        res = reg.verify_spend_without_output(_probe(docs + [latest]))
        assert res.skipped is True and "no output numerators" in res.detail

    def test_never_raises_on_hostile_input(self):
        for text in ("", "\n\n", "{not json", '{"date": null}\n',
                     '{"date": "2026-07-26", "spend": "nope", "acted_7d": []}\n',
                     '{"date": "2026-07-26", "spend": {"total_cost_micro": "x"}}\n',
                     "null\n[]\n3\n"):
            probe = FakeProbe(now=NOW, files={reg.FALSIFIER_SERIES: text})
            res = reg.verify_spend_without_output(probe)
            assert res.ok is True and res.skipped is True

    def test_never_raises_when_the_probe_itself_explodes(self):
        """The wrapper's real job: a broken READER must report nothing, not
        page the Chair about money on the strength of a bug."""
        class Exploding(FakeProbe):
            def read_text(self, path):
                raise RuntimeError("disk on fire")

        res = reg.verify_spend_without_output(Exploding(now=NOW))
        assert res.ok is True and res.skipped is True
        assert "could not run" in res.detail


# ---------------------------------------------------------------------------
# (b) spend-lane-anomaly.
# ---------------------------------------------------------------------------
def _lanes(**kw) -> dict:
    """{'advisor': (cost_micro|None, calls)} → the lane block's shape."""
    out = {}
    for lane, (cost, calls) in kw.items():
        fig = {"calls": calls, "units": 0}
        if cost is not None:
            fig["cost_micro"] = cost
        out[lane] = fig
    return out


class TestSpendLaneAnomaly:
    def _hist(self, days=10, **lanes):
        return [_line(d, total=1_000_000, output=3, lanes=_lanes(**lanes))
                for d in range(days, 0, -1)]

    def test_fires_on_a_lane_at_20x_its_own_median(self):
        docs = self._hist(advisor=(100_000, 10))
        docs.append(_line(0, total=3_000_000, output=3,
                          lanes=_lanes(advisor=(3_000_000, 300))))
        res = reg.verify_spend_lane_anomaly(_probe(docs))
        assert res.ok is False and res.skipped is False
        assert "advisor" in res.detail and "30x" in res.detail

    def test_silent_at_19x(self):
        """The multiple is the control, so the arm below it must be quiet."""
        docs = self._hist(advisor=(100_000, 10))
        docs.append(_line(0, total=3_000_000, output=3,
                          lanes=_lanes(advisor=(1_900_000, 190))))
        assert reg.verify_spend_lane_anomaly(_probe(docs)).ok is True

    def test_fires_on_a_lane_that_never_billed_before(self):
        """A vendor that was free yesterday and charges today is a fact
        somebody chose and nobody was told."""
        docs = self._hist(embeddings=(None, 500))
        docs.append(_line(0, total=1_000_000, output=3,
                          lanes=_lanes(embeddings=(42_000, 500))))
        res = reg.verify_spend_lane_anomaly(_probe(docs))
        assert res.ok is False
        assert "NO billing history" in res.detail and "embeddings" in res.detail

    def test_unpriced_lane_spike_is_reported_in_CALLS_never_dollars(self):
        """The lanes most able to run away are the ones we cannot price.
        Leaving them unwatched would point the sensor away from the risk —
        and "$0.00" would be a lie."""
        docs = self._hist(tts=(None, 20))
        docs.append(_line(0, total=1_000_000, output=3,
                          lanes=_lanes(tts=(None, 800))))
        res = reg.verify_spend_lane_anomaly(_probe(docs))
        assert res.ok is False
        assert "800 calls (unpriced)" in res.detail and "$" not in res.detail

    def test_silent_on_insufficient_observed_history(self):
        """Six observed days is below the declared floor of seven."""
        docs = self._hist(days=6, advisor=(100_000, 10))
        docs.append(_line(0, total=9_000_000, output=3,
                          lanes=_lanes(advisor=(9_000_000, 900))))
        res = reg.verify_spend_lane_anomaly(_probe(docs))
        assert res.skipped is True and "observed day(s) of lane history" in res.detail

    def test_silent_when_a_lane_has_too_few_billing_days_for_a_median(self):
        """Two billing days is a guess, not a median — and this row does not
        guess. A DEFAULT CONSTANT here would be the bug: silence is the answer."""
        docs = [_line(d, total=1_000_000, output=3,
                      lanes=_lanes(advisor=(100_000 if d in (9, 8) else 0, 10)))
                for d in range(10, 0, -1)]
        docs.append(_line(0, total=5_000_000, output=3,
                          lanes=_lanes(advisor=(5_000_000, 500))))
        res = reg.verify_spend_lane_anomaly(_probe(docs))
        assert res.ok is True and res.skipped is False
        # …and with three billing days the same spike DOES fire, so the floor
        # is what produced the silence above.
        docs3 = [_line(d, total=1_000_000, output=3,
                       lanes=_lanes(advisor=(100_000 if d in (9, 8, 7) else 0, 10)))
                 for d in range(10, 0, -1)]
        docs3.append(_line(0, total=5_000_000, output=3,
                           lanes=_lanes(advisor=(5_000_000, 500))))
        assert reg.verify_spend_lane_anomaly(_probe(docs3)).ok is False

    def test_skips_when_lane_figures_are_unobservable(self):
        assert reg.verify_spend_lane_anomaly(FakeProbe(now=NOW)).skipped is True
        docs = self._hist(advisor=(100_000, 10))
        docs.append(_line(0, total=1_000_000, output=3, lanes=None))
        res = reg.verify_spend_lane_anomaly(_probe(docs))
        assert res.skipped is True and "no lane figures" in res.detail

    def test_never_raises_on_hostile_lane_shapes(self):
        docs = self._hist(advisor=(100_000, 10))
        bad = _line(0, total=1_000_000, output=3, lanes=None)
        bad["spend"]["lanes"] = {"advisor": "not-a-dict", "x": {"cost_micro": "y"},
                                 "z": {"calls": None}}
        res = reg.verify_spend_lane_anomaly(_probe(docs + [bad]))
        assert res.ok is True and res.skipped is False


# ---------------------------------------------------------------------------
# (c) meter-silent — the watch on the watch.
# ---------------------------------------------------------------------------
_LEDGER = reg.COST_TOKENS_DAILY_PREFIX + TODAY


def _worked(*officers, ago_s=3600) -> dict:
    when = (NOW - dt.timedelta(seconds=ago_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {reg.LAST_TOOLCALL_PREFIX + o: when for o in officers}


class TestMeterSilent:
    def test_fires_when_officers_worked_and_the_ledger_is_observed_empty(self):
        """With no cap, nothing else reads this ledger — a dead meter would
        take both spend rows down with it, silently green forever."""
        probe = FakeProbe(now=NOW, redis=_worked("cos"), hashes={_LEDGER: {}})
        res = reg.verify_meter_silent(probe)
        assert res.ok is False and res.skipped is False
        assert "METER SILENT" in res.detail and "cos" in res.detail
        # Names the EMPTY-ledger diagnosis specifically. The zero-cost arm
        # below would also fire here and its message points somewhere else
        # entirely (the meter running but not pricing) — a finding that sends
        # the reader down the wrong path is barely better than none.
        assert "is EMPTY" in res.detail
        assert "ZERO recorded cost" not in res.detail

    def test_fires_when_the_ledger_has_fields_but_zero_cost(self):
        """The degenerate end: token dimensions landing while the cost field
        does not. A non-empty hash is not proof the meter is pricing — and the
        diagnosis must say so rather than reusing the empty-ledger wording."""
        probe = FakeProbe(now=NOW, redis=_worked("cos"),
                          hashes={_LEDGER: {"cos_input": "1200",
                                            "cos_output": "300"}})
        res = reg.verify_meter_silent(probe)
        assert res.ok is False and "ZERO recorded cost" in res.detail
        assert "is EMPTY" not in res.detail

    def test_passes_when_the_ledger_is_recording(self):
        probe = FakeProbe(now=NOW, redis=_worked("cos"),
                          hashes={_LEDGER: {"cos_cost_micro": "2500000",
                                            "cos_input": "1200"}})
        res = reg.verify_meter_silent(probe)
        assert res.ok is True and res.skipped is False
        assert "ledger live" in res.detail

    def test_empty_ledger_with_no_officer_activity_is_correct_not_an_alarm(self):
        """Vacuous truth: nobody worked, so nothing should have been billed."""
        probe = FakeProbe(now=NOW, hashes={_LEDGER: {}})
        res = reg.verify_meter_silent(probe)
        assert res.ok is True and res.skipped is False
        assert "correct outcome" in res.detail

    def test_a_turn_still_in_flight_is_never_the_evidence(self):
        """A toolcall 60s ago has not reached its Stop hook, so it is not yet
        in the ledger and its absence proves nothing. This is also what keeps
        the row quiet across the UTC midnight ledger rollover."""
        probe = FakeProbe(now=NOW, redis=_worked("cos", ago_s=60),
                          hashes={_LEDGER: {}})
        assert reg.verify_meter_silent(probe).ok is True
        # Past the grace, the same officer IS evidence.
        past = FakeProbe(now=NOW,
                         redis=_worked("cos", ago_s=reg.METER_STOP_GRACE_S + 60),
                         hashes={_LEDGER: {}})
        assert reg.verify_meter_silent(past).ok is False

    def test_yesterdays_work_does_not_arm_todays_ledger(self):
        """The ledger key is UTC-daily; work before midnight belongs to the
        previous key and cannot be evidence about this one."""
        probe = FakeProbe(now=NOW, redis=_worked("cos", ago_s=20 * 3600),
                          hashes={_LEDGER: {}})
        assert reg.verify_meter_silent(probe).ok is True

    def test_skips_when_redis_is_unobservable(self):
        """THE LOAD-BEARING DISTINCTION. None (could not look) must skip where
        {} (looked, found nothing) alarms — collapsing them either pages on
        every Redis blip or reads a dead meter as fine."""
        probe = FakeProbe(now=NOW, redis=_worked("cos"))   # no hash surface
        res = reg.verify_meter_silent(probe)
        assert res.skipped is True and res.ok is True
        assert "not observable" in res.detail
        # Same probe, same officers, only the observation differs → alarm.
        seen = FakeProbe(now=NOW, redis=_worked("cos"), hashes={_LEDGER: {}})
        assert reg.verify_meter_silent(seen).ok is False

    def test_an_older_probe_stub_self_disables_instead_of_crashing(self):
        """The degrade-safe default: a Probe that predates redis_hgetall
        returns None from the base class, so the row skips rather than taking
        the sweep down."""
        class OldProbe(reg.Probe):
            def now(self):
                return NOW

            def redis_get(self, key):
                return ""

        assert reg.verify_meter_silent(OldProbe()).skipped is True

    def test_never_raises_on_hostile_ledger_values(self):
        probe = FakeProbe(now=NOW, redis=_worked("cos"),
                          hashes={_LEDGER: {"cos_cost_micro": "not-a-number",
                                            "weird": "x"}})
        res = reg.verify_meter_silent(probe)
        assert res.ok is False and "ZERO recorded cost" in res.detail

    def test_never_raises_when_the_probe_itself_explodes(self):
        class Exploding(FakeProbe):
            def redis_hgetall(self, key):
                raise RuntimeError("redis on fire")

        res = reg.verify_meter_silent(Exploding(now=NOW))
        assert res.ok is True and res.skipped is True
        assert "could not run" in res.detail


# ---------------------------------------------------------------------------
# The REAL probe method, not the fake. The tri-state only protects anything if
# the live implementation actually produces it — a fake that returns None on
# request proves nothing about redis-cli.
# ---------------------------------------------------------------------------
class _Completed:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _real_hgetall(monkeypatch, **kw):
    from framework.watchdog import check
    monkeypatch.setattr(check.subprocess, "run",
                        lambda *a, **k: _Completed(**kw))
    return check.RealProbe(allow_side_effects=False).redis_hgetall("k")


class TestRealProbeHgetall:
    def test_parses_a_hash(self, monkeypatch):
        assert _real_hgetall(monkeypatch,
                             out="cos_cost_micro\n120\ncos_input\n9\n") == {
            "cos_cost_micro": "120", "cos_input": "9"}

    def test_empty_reply_is_an_observed_empty_hash_not_unobservable(self, monkeypatch):
        """{} is the ALARM state for meter-silent; it must be reachable."""
        assert _real_hgetall(monkeypatch, out="") == {}

    def test_unobservable_shapes_all_return_none(self, monkeypatch):
        # non-zero rc
        assert _real_hgetall(monkeypatch, rc=1, out="x\ny\n") is None
        # redis-cli exits 0 while printing "Could not connect" on stderr
        assert _real_hgetall(monkeypatch, out="", err="Could not connect") is None
        # an error reply arrives on STDOUT and still exits 0
        assert _real_hgetall(monkeypatch, out="WRONGTYPE Operation against…") is None
        # a desynced pair stream is not a hash we can honestly read
        assert _real_hgetall(monkeypatch, out="a\nb\nc\n") is None

    def test_a_dead_subprocess_is_unobservable_not_empty(self, monkeypatch):
        from framework.watchdog import check

        def boom(*a, **k):
            raise OSError("no redis-cli")

        monkeypatch.setattr(check.subprocess, "run", boom)
        probe = check.RealProbe(allow_side_effects=False)
        assert probe.redis_hgetall("k") is None

    def test_it_does_not_route_through_the_lossy_redis_helper(self, monkeypatch):
        """check._redis() returns "" on every failure. Routing through it would
        collapse "Redis unreachable" into "hash empty" — and meter-silent
        alarms on empty. Pinned by making _redis explode: the method must not
        touch it."""
        from framework.watchdog import check

        def tripwire(*a, **k):
            raise AssertionError("redis_hgetall must not use _redis()")

        monkeypatch.setattr(check, "_redis", tripwire)
        monkeypatch.setattr(check.subprocess, "run",
                            lambda *a, **k: _Completed(out="a\n1\n"))
        assert check.RealProbe(allow_side_effects=False).redis_hgetall("k") == {"a": "1"}


# ---------------------------------------------------------------------------
# Shared contract: these rows exist to be QUIET.
# ---------------------------------------------------------------------------
def test_no_spend_row_carries_a_dollar_threshold():
    """The Captain's ruling, pinned mechanically: every trigger is relative to
    this cabinet's own history. A constant here would page on a busy week and
    need re-tuning every time the fleet grows."""
    assert reg.SPEND_RISE_FACTOR == 2.0
    assert reg.LANE_SPIKE_FACTOR == 20.0
    for name in ("SPEND_RISE_FACTOR", "LANE_SPIKE_FACTOR",
                 "SPEND_MIN_DELIVERING_DAYS", "LANE_MIN_HISTORY_DAYS",
                 "LANE_MIN_BILLING_DAYS"):
        assert getattr(reg, name)                       # declared, not implicit
    # No row may state a MONEY AMOUNT — not in what it promises, and not in
    # the code that decides. (Formatting a MEASURED figure into a finding is
    # fine and expected; a currency LITERAL in the deciding code would be a
    # threshold in disguise.) The verify bodies are read as real source —
    # _never_raises uses functools.wraps precisely so this cannot silently
    # inspect the wrapper and pass on anything.
    import ast
    import inspect
    import re as _re
    import textwrap
    amount = _re.compile(r"\$\s*[\d.]")
    for eid, fn in (("spend-without-output", reg.verify_spend_without_output),
                    ("spend-lane-anomaly", reg.verify_spend_lane_anomaly),
                    ("meter-silent", reg.verify_meter_silent)):
        assert not amount.search(reg.expectation_by_id(eid).what), \
            f"{eid} promises a money amount"
        src = textwrap.dedent(inspect.getsource(fn))
        assert "SPEND WITHOUT OUTPUT" in src or "lane" in src or "METER" in src, \
            f"{eid}: getsource returned a wrapper, not the verify"
        node = ast.parse(src).body[0]
        # Docstrings explain history ("the gate read $0") and are prose, not a
        # decision; scan only the executable body below it.
        skip_to = node.body[0].end_lineno if ast.get_docstring(node) else 0
        for line in src.splitlines()[skip_to:]:
            code = line.split("#", 1)[0]
            # A finding line divides a MEASURED micro value by 1e6 — that is a
            # rendered observation, not a constant.
            if "1e6" in code:
                continue
            assert not amount.search(code), \
                f"{eid} hardcodes a money amount: {line.strip()}"


def test_every_spend_row_is_silent_on_a_bare_probe():
    """A cabinet with no series, no ledger and no history says NOTHING. The
    default state of a money watch is silence."""
    bare = FakeProbe(now=NOW)
    for verify in (reg.verify_spend_without_output, reg.verify_spend_lane_anomaly,
                   reg.verify_meter_silent):
        res = verify(bare)
        assert res.skipped is True and res.ok is True
