"""Tests for cabinet/scripts/cog2-parity-falsifier.py — the COG-2 cortex shadow-parity
FALSIFIER (§8 sim 6).

Tests-first. Pins the falsifier's contract AND drives every negative-control
mutant the §8 sim-6 row names — each MUST fail (bite):

  * store-sampled frame (sampling_frame="store") — samples cortex's OWN belief
    store, so a subject deleted from the store but still present on the
    AUTHORITATIVE side is never sampled: it structurally cannot fail the
    deleted-subject seed (the tell). The correct authoritative frame flags it.
  * adapter-derived ground truth (ground_truth_source="adapter") — reads ground
    truth THROUGH cortex's own answer, so f(x)==f(x): the equal-ts
    mis-translation seed can never disagree with itself. The domain reader
    (authoritative side) catches the mistranslation.
  * a falsifier that imports a cortex adapter — the import ban (C-F17): an AST
    import-graph walk over the script proves ZERO framework.cortex.* imports;
    a source copy with an injected `from framework.cortex import adapters` is
    caught (the mutant bites). grep backstop included.
  * memoryless re-sampler (resample="memoryless") — drops the sticky
    force-include, so a breach that is NOT naturally sampled the next cycle
    reads ok and RESETS the second-consecutive-breach counter: the
    breach -> unsampled -> breach escalation seed never fires a captain card.
    Sticky re-sampling force-includes the open breach and DOES escalate.

Plus the honesty contract: agreeing sides -> ok; per-day sample floor (absent
day is a breach); unconfigured -> honest no-op exit 0; --probe tokens; captain
card ONLY on a persisted (second consecutive) breach date; hostile subject text
lands SCRUBBED in the ledger and NEVER in the captain-card argv.

Seam-driven + hermetic (no live DB): the pure core is exercised directly and
run() is driven through the COG2_PARITY_DATA_JSON seam, exactly the COG-1
task-sync-drift falsifier test idiom.
"""
from __future__ import annotations

import ast
import datetime as dt
import importlib.util as _ilu
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "cog2-parity-falsifier.py"
_REPO = Path(__file__).resolve().parents[3]

# hyphenated filename -> importlib (the falsifier-test idiom, test_task_sync_drift)
spec = _ilu.spec_from_file_location("cog2_parity", _SCRIPT)
cp = _ilu.module_from_spec(spec)
sys.modules["cog2_parity"] = cp
spec.loader.exec_module(cp)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "cabroot"
    (root / "cabinet" / "logs").mkdir(parents=True)
    monkeypatch.setenv("CABINET_ROOT", str(root))
    for var in ("NEON_CONNECTION_STRING", "COG2_PARITY_DATA_JSON",
                "COG2_PARITY_CORTEX_CMD", "COG2_PARITY_ATTENTION_SUBMIT",
                "COG2_PARITY_SAMPLE_N", "COG2_PARITY_SAMPLE_FLOOR",
                "CABINET_EVENT_LOG_DIR"):
        monkeypatch.delenv(var, raising=False)
    return root


def _seam(tmp_path, monkeypatch, authoritative: dict, cortex: dict) -> None:
    seam = tmp_path / "parity-data.json"
    seam.write_text(json.dumps({"authoritative": authoritative, "cortex": cortex}))
    monkeypatch.setenv("COG2_PARITY_DATA_JSON", str(seam))


def _ledger(root: Path) -> list[dict]:
    path = root / "cabinet" / "logs" / "cog2-parity.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _stub_attention(tmp_path, monkeypatch) -> Path:
    """A fake attention-submit.sh that records its full argv (one JSON line per
    call) so a test can assert a card was/was not filed AND that no raw subject
    text reached the argv."""
    rec = tmp_path / "cards.log"
    script = tmp_path / "attn.sh"
    script.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n" "$*" >> "$REC"\n'
        'exit 0\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("COG2_PARITY_ATTENTION_SUBMIT", str(script))
    monkeypatch.setenv("REC", str(rec))
    return rec


def _find_start_date(exclude_on_plus1: str, include_on_plus2: str,
                     universe: list[str]) -> dt.date:
    """A contiguous (S, S+1, S+2) window where an n=1 natural sample EXCLUDES the
    given subject on S+1 and INCLUDES it on S+2 — so the escalation seed's
    'unsampled' middle cycle is deterministic (no reliance on magic dates), and
    the days are adjacent so per-day floor sees no absent day."""
    uni = sorted(universe)
    day = dt.date(2026, 1, 1)
    for _ in range(1000):
        d1 = (day + dt.timedelta(days=1)).isoformat()
        d2 = (day + dt.timedelta(days=2)).isoformat()
        if (exclude_on_plus1 not in cp._rotate_sample(uni, 1, d1)
                and include_on_plus2 in cp._rotate_sample(uni, 1, d2)):
            return day
        day += dt.timedelta(days=1)
    raise AssertionError("no suitable contiguous escalation window found")


# ===========================================================================
# pure core — the parity verdict
# ===========================================================================

class TestPureCore:
    def test_agreeing_sides_are_ok(self):
        auth = {"t1": {"status": "done"}, "t2": {"status": "wip"}}
        cortex = {"t1": {"status": "done"}, "t2": {"status": "wip"}}
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date="2026-07-22",
                           floor=1)
        assert v["status"] == "ok"
        assert v["breaches"] == []
        assert v["open_breaches"] == []

    def test_deleted_subject_is_a_breach_on_the_authoritative_frame(self):
        # the subject exists on the AUTHORITATIVE side but cortex's store has no
        # belief for it (deleted-subject seed, C-F16) -> cortex cannot answer.
        auth = {"t1": {"status": "done"}, "gone": {"status": "wip"}}
        cortex = {"t1": {"status": "done"}}  # 'gone' removed from the store
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date="2026-07-22",
                           sample_n=10, floor=1)
        assert v["status"] == "breach"
        reasons = {b["subject"]: b["reason"] for b in v["breaches"]}
        assert reasons.get("gone") == "unanswered"
        assert "gone" in v["open_breaches"]

    def test_MUTANT_store_frame_misses_the_deleted_subject(self):
        # sampling_frame="store" draws the universe from cortex's beliefs, which
        # no longer contain 'gone' -> it is never sampled -> false ok. The tell.
        auth = {"t1": {"status": "done"}, "gone": {"status": "wip"}}
        cortex = {"t1": {"status": "done"}}
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date="2026-07-22",
                           sample_n=10, floor=1, sampling_frame="store")
        assert v["status"] == "ok"          # mutant is blind — MUST bite
        assert v["open_breaches"] == []

    def test_mistranslation_is_a_breach_via_the_domain_reader(self):
        # equal-ts enrichment order flipped (C-F17): the domain's own reader says
        # 'blocked', cortex's adapter mistranslated it to 'wip'.
        auth = {"t1": {"status": "blocked"}}
        cortex = {"t1": {"status": "wip"}}
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date="2026-07-22",
                           floor=1)
        assert v["status"] == "breach"
        assert v["breaches"][0]["reason"] == "mismatch"

    def test_MUTANT_adapter_ground_truth_misses_the_mistranslation(self):
        # ground_truth_source="adapter" reads ground truth THROUGH cortex's own
        # answer -> f(x)==f(x) -> can never disagree with the mistranslation.
        auth = {"t1": {"status": "blocked"}}
        cortex = {"t1": {"status": "wip"}}
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date="2026-07-22",
                           floor=1, ground_truth_source="adapter")
        assert v["status"] == "ok"          # tautology hides it — MUST bite


class TestStickyResampling:
    def test_sticky_force_includes_a_prior_open_breach_not_naturally_sampled(self):
        # a large frame where the natural n=1 sample does NOT land on the open
        # breach; sticky must force it back in and re-flag it.
        auth = {f"s{i}": {"status": "done"} for i in range(8)}
        auth["bad"] = {"status": "wip"}
        cortex = {k: v for k, v in auth.items() if k != "bad"}  # 'bad' deleted
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date="2026-07-22",
                           sample_n=1, floor=1, prior_open_breaches=["bad"])
        assert "bad" in v["sampled_subjects"]
        assert v["status"] == "breach"
        assert "bad" in v["open_breaches"]

    def test_MUTANT_memoryless_drops_the_prior_open_breach(self):
        auth = {f"s{i}": {"status": "done"} for i in range(8)}
        auth["bad"] = {"status": "wip"}
        cortex = {k: v for k, v in auth.items() if k != "bad"}
        # pick a date whose n=1 natural sample is NOT 'bad'
        uni = sorted(auth)
        date = next(d for d in (f"2026-07-{i:02d}" for i in range(1, 29))
                    if "bad" not in cp._rotate_sample(uni, 1, d))
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date=date,
                           sample_n=1, floor=1, prior_open_breaches=["bad"],
                           resample="memoryless")
        assert "bad" not in v["sampled_subjects"]   # memoryless forgot it
        assert v["status"] == "ok"                  # MUST bite


class TestSampleFloor:
    def test_current_cycle_below_floor_is_a_breach(self):
        auth = {f"s{i}": {"status": "done"} for i in range(10)}
        cortex = dict(auth)
        v = cp.parity_scan(authoritative=auth, cortex=cortex, date="2026-07-22",
                           sample_n=2, floor=5)
        assert v["floor_ok"] is False
        assert v["status"] == "breach"

    def test_absent_day_in_the_observed_range_is_a_breach(self):
        # two present days three days apart -> the missing days between are a
        # per-day floor breach (a dead falsifier cannot pass the soak vacuously).
        lines = [{"date": "2026-07-10", "sampled": 6},
                 {"date": "2026-07-13", "sampled": 6}]
        f = cp.per_day_floor(lines, today="2026-07-14", floor=3)
        assert f["breach"] is True

    def test_contiguous_full_days_meet_the_floor(self):
        lines = [{"date": "2026-07-10", "sampled": 6},
                 {"date": "2026-07-11", "sampled": 6},
                 {"date": "2026-07-12", "sampled": 6}]
        f = cp.per_day_floor(lines, today="2026-07-13", floor=3)
        assert f["breach"] is False

    def test_F1_stale_old_day_does_not_poison_a_later_clean_day(self):
        # F1: an old below-floor (asleep/stale) day is a diagnostic `breach`, but
        # run() judges `latest_breach` (yesterday) — a clean recent day is NOT
        # poisoned. Before the fix run() folded any(windows) -> permanent red.
        lines = [{"date": "2026-07-10", "sampled": 0, "frame_size": 5},  # asleep
                 {"date": "2026-07-11", "sampled": 6, "frame_size": 6},
                 {"date": "2026-07-12", "sampled": 6, "frame_size": 6}]
        f = cp.per_day_floor(lines, today="2026-07-13", floor=3)
        assert f["breach"] is True            # the old 07-10 gap (diagnostic only)
        assert f["latest_breach"] is False    # yesterday (07-12) clean -> recovers

    def test_F4_below_frame_size_day_is_not_a_count_shortfall_breach(self):
        # F4: a day whose authoritative universe was smaller than the floor
        # sampled everything available -> NOT a breach by count-shortfall.
        lines = [{"date": "2026-07-10", "sampled": 2, "frame_size": 2},
                 {"date": "2026-07-11", "sampled": 2, "frame_size": 2}]
        f = cp.per_day_floor(lines, today="2026-07-12", floor=3)
        assert f["breach"] is False
        assert f["latest_breach"] is False

    def test_dark_sampler_with_a_real_universe_still_breaches(self):
        # anti-regression on the frame cap: a day that had a real (>= floor)
        # universe but sampled below floor IS a breach — the cap exempts only a
        # genuinely small universe, never a dark/dead sampler.
        lines = [{"date": "2026-07-10", "sampled": 0, "frame_size": 9}]
        f = cp.per_day_floor(lines, today="2026-07-11", floor=3)
        assert f["latest_breach"] is True

    def test_F7_unconfigured_days_are_exempt_from_the_floor(self):
        # F7: a stretch of honest `unconfigured` days (the cycle RAN with no
        # parity source — sampled=0/frame_size=0) is NOT a dark day and must not
        # floor-breach. Before the fix, sampled=0 read as a full-floor miss, so
        # the most-recent unconfigured day set latest_breach True and the first
        # CONFIGURED run after the stretch opened on a false red.
        lines = [{"date": d, "status": "unconfigured", "sampled": 0,
                  "frame_size": 0}
                 for d in ("2026-07-18", "2026-07-19", "2026-07-20")]
        f = cp.per_day_floor(lines, today="2026-07-21", floor=3)
        assert f["breach"] is False
        assert f["latest_breach"] is False

    def test_F7_error_day_is_not_exempt_and_still_breaches(self):
        # the exemption is unconfigured-ONLY: an `error` day (a CONFIGURED reader
        # broke — sampled=0/frame_size=0 too) keeps the FULL floor and breaches.
        # Guards against an over-broad "any zero-frame day is exempt" fix.
        lines = [{"date": "2026-07-20", "status": "error", "sampled": 0,
                  "frame_size": 0}]
        f = cp.per_day_floor(lines, today="2026-07-21", floor=3)
        assert f["latest_breach"] is True


# ===========================================================================
# import ban (C-F17) — the falsifier imports NO framework.cortex.*
# ===========================================================================

def _cortex_imports(source: str) -> list[str]:
    """Every framework.cortex[.*] module name reached by a real import statement
    (AST — string literals do not count). The spec's gate is exactly this
    import-graph walk; a matching grep backstop is asserted separately."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "framework.cortex" or alias.name.startswith(
                        "framework.cortex."):
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "framework.cortex" or mod.startswith("framework.cortex."):
                hits.append(mod)
    return hits


class TestImportBan:
    def test_script_imports_no_framework_cortex_module(self):
        assert _cortex_imports(_SCRIPT.read_text()) == []

    def test_MUTANT_injected_cortex_adapter_import_is_caught(self):
        mutant = _SCRIPT.read_text().replace(
            "import json\n",
            "import json\nfrom framework.cortex import adapters  # MUTANT\n", 1)
        assert _cortex_imports(mutant) == ["framework.cortex"]  # bites

    def test_grep_backstop_finds_no_cortex_import_line(self):
        # the grep backstop the spec pairs with the AST walk: no import LINE
        # names framework.cortex (and no bare literal either, belt-and-suspenders).
        rc = subprocess.run(
            ["grep", "-nE", r"^[[:space:]]*(import|from)[[:space:]]+framework\.cortex",
             str(_SCRIPT)], capture_output=True, text=True)
        assert rc.returncode == 1, f"unexpected cortex import line: {rc.stdout}"


# ===========================================================================
# run() — seam-driven end to end
# ===========================================================================

class TestRun:
    def test_seam_agreeing_writes_ok_and_exit_0(self, tmp_path, monkeypatch, capsys):
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        _seam(tmp_path, monkeypatch, {"t1": {"status": "done"}},
              {"t1": {"status": "done"}})
        rc = cp.run(today="2026-07-22")
        assert rc == 0
        line = _ledger(root)[-1]
        assert line["status"] == "ok"

    def test_seam_breach_writes_breach_and_exit_1(self, tmp_path, monkeypatch):
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        _seam(tmp_path, monkeypatch, {"t1": {"status": "blocked"}},
              {"t1": {"status": "wip"}})
        rc = cp.run(today="2026-07-22")
        assert rc == 1
        assert _ledger(root)[-1]["status"] == "breach"

    def test_unconfigured_is_an_honest_no_op(self, tmp_path, monkeypatch, capsys):
        root = _root(tmp_path, monkeypatch)   # no seam, no pg, no cortex cmd
        rc = cp.run(today="2026-07-22")
        assert rc == 0
        assert _ledger(root)[-1]["status"] == "unconfigured"

    def test_F1_stale_day_does_not_poison_a_later_clean_run(
            self, tmp_path, monkeypatch):
        # F1 end-to-end: seed an old below-floor (asleep) day + a clean yesterday,
        # then run a clean today -> ok / exit 0. Before the fix the any()-fold
        # over the 07-10 gap forced a permanent red on every later clean run.
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "3")
        path = root / "cabinet" / "logs" / "cog2-parity.jsonl"
        path.write_text(
            json.dumps({"ts": "2026-07-10T00:00:00Z", "date": "2026-07-10",
                        "status": "breach", "sampled": 0, "frame_size": 5}) + "\n"
            + json.dumps({"ts": "2026-07-11T00:00:00Z", "date": "2026-07-11",
                          "status": "ok", "sampled": 6, "frame_size": 6}) + "\n")
        auth = {f"t{i}": {"status": "done"} for i in range(6)}
        _seam(tmp_path, monkeypatch, auth, dict(auth))
        rc = cp.run(today="2026-07-12", sample_n=6)
        assert rc == 0                                    # NOT poisoned by 07-10
        line = _ledger(root)[-1]
        assert line["status"] == "ok"
        assert line["day_floor_breach"] is False

    def test_F6_malformed_seam_is_a_loud_error_exit_1(
            self, tmp_path, monkeypatch, capsys):
        # F6: a configured-but-unreadable data source -> status:"error", exit 1
        # (NEVER a silent green). Drives run()'s ValueError/JSONDecodeError arm,
        # and the doctor --probe reads the ERROR token loudly.
        root = _root(tmp_path, monkeypatch)
        seam = tmp_path / "bad.json"
        seam.write_text("{ this is not valid json")
        monkeypatch.setenv("COG2_PARITY_DATA_JSON", str(seam))
        rc = cp.run(today="2026-07-22")
        assert rc == 1
        assert _ledger(root)[-1]["status"] == "error"
        capsys.readouterr()                       # drain run()'s stderr
        assert cp.probe() == 0
        assert capsys.readouterr().out.strip().startswith("ERROR ")

    def test_F6_seam_missing_authoritative_is_a_loud_error(
            self, tmp_path, monkeypatch):
        # F6: a well-formed but mis-shaped seam (no 'authoritative' map) is a
        # CONFIGURED failure -> _ConfiguredButFailing -> status:"error", exit 1
        # (the other run() error arm; a configured reader must never fall to ok).
        root = _root(tmp_path, monkeypatch)
        seam = tmp_path / "noauth.json"
        seam.write_text(json.dumps({"cortex": {"t1": {"status": "done"}}}))
        monkeypatch.setenv("COG2_PARITY_DATA_JSON", str(seam))
        rc = cp.run(today="2026-07-22")
        assert rc == 1
        assert _ledger(root)[-1]["status"] == "error"

    def test_F7_unconfigured_streak_then_clean_configured_is_ok(
            self, tmp_path, monkeypatch):
        # F7 end-to-end: a box that logged honest `unconfigured` no-ops for
        # several days, then gets a parity source configured and runs a CLEAN
        # cycle -> ok / exit 0. Before the fix the per-day floor treated the
        # prior unconfigured days as full-floor dark days, so the FIRST real
        # configured run opened on a guaranteed false BREACH (doctor AMBER).
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        path = root / "cabinet" / "logs" / "cog2-parity.jsonl"
        path.write_text("".join(
            json.dumps({"ts": f"2026-07-{d}T00:00:00Z", "date": f"2026-07-{d}",
                        "status": "unconfigured", "sampled": 0,
                        "frame_size": 0}) + "\n"
            for d in ("18", "19", "20", "21")))     # contiguous honest no-ops
        _seam(tmp_path, monkeypatch, {"t1": {"status": "done"}},
              {"t1": {"status": "done"}})
        rc = cp.run(today="2026-07-22")
        assert rc == 0                                    # NOT a false breach
        line = _ledger(root)[-1]
        assert line["status"] == "ok"
        assert line["day_floor_breach"] is False


class TestEscalationLadder:
    def _seed(self, tmp_path, monkeypatch):
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        # X missing from cortex (persistent breach); Y agrees.
        _seam(tmp_path, monkeypatch,
              {"s-x": {"status": "wip"}, "s-y": {"status": "done"}},
              {"s-y": {"status": "done"}})
        rec = _stub_attention(tmp_path, monkeypatch)
        return root, rec

    def test_sticky_escalates_on_second_consecutive_breach_date(
            self, tmp_path, monkeypatch):
        root, rec = self._seed(tmp_path, monkeypatch)
        start = _find_start_date("s-x", "s-x", ["s-x", "s-y"])
        d1 = start.isoformat()
        d2 = (start + dt.timedelta(days=1)).isoformat()
        # day 1: sample both -> X breaches, open=[s-x], no prior date -> no card
        assert cp.run(today=d1, sample_n=2) == 1
        assert _ledger(root)[-1]["escalated"] is None
        # day 2: natural n=1 sample is s-y (ok); sticky forces s-x back -> breach,
        # prior date breached -> ONE captain card.
        assert cp.run(today=d2, sample_n=1) == 1
        last = _ledger(root)[-1]
        assert last["status"] == "breach"
        assert "s-x" in last["open_breaches"]
        assert last["escalated"] == "card-filed"
        assert rec.read_text().count("\n") == 1     # exactly one card

    def test_MUTANT_memoryless_never_escalates_the_seed(
            self, tmp_path, monkeypatch):
        root, rec = self._seed(tmp_path, monkeypatch)
        start = _find_start_date("s-x", "s-x", ["s-x", "s-y"])
        d1 = start.isoformat()
        d2 = (start + dt.timedelta(days=1)).isoformat()
        d3 = (start + dt.timedelta(days=2)).isoformat()
        assert cp.run(today=d1, sample_n=2, resample="memoryless") == 1
        # day 2: natural sample is s-y (ok); memoryless does NOT force s-x -> ok,
        # so the second-consecutive counter RESETS.
        assert cp.run(today=d2, sample_n=1, resample="memoryless") == 0
        assert _ledger(root)[-1]["status"] == "ok"
        # day 3: s-x naturally sampled again -> breach, but prior date (d2) was ok
        # -> not a second consecutive -> no card. The escalation seed is gamed.
        assert cp.run(today=d3, sample_n=1, resample="memoryless") == 1
        assert _ledger(root)[-1]["escalated"] is None
        assert not rec.exists() or rec.read_text().strip() == ""  # zero cards

    def test_F2_latest_open_breaches_skips_reader_outage_lines(self):
        # F2 (C-F18): error/unconfigured skeletons carry open_breaches:[] — they
        # must NOT wipe the sticky set from the last real breach verdict.
        lines = [{"status": "breach", "open_breaches": ["s-x"]},
                 {"status": "error", "open_breaches": []},
                 {"status": "unconfigured", "open_breaches": []}]
        assert cp._latest_open_breaches(lines) == ["s-x"]   # outages skipped

    def test_F2_error_date_does_not_reset_the_breach_ladder(self):
        # F2 (C-F18): a reader outage on the middle date neither escalates nor
        # RESETS the ladder — d1's breach still counts across the d2 outage.
        lines = [{"date": "2026-03-01", "status": "breach"},
                 {"date": "2026-03-02", "status": "error"}]
        prev, consecutive = cp._previous_date_breached(lines, "2026-03-03")
        assert prev is True
        assert consecutive == 1

    def test_F2_breach_then_error_then_recovered_still_files_one_card(
            self, tmp_path, monkeypatch):
        # F2 end-to-end: an adversary kills the reader on the middle day
        # (breach -> error -> breach). The outage must not wipe the sticky set or
        # reset the ladder — the 2nd real breach date still fires exactly ONE
        # captain card and re-flags the open breach.
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        rec = _stub_attention(tmp_path, monkeypatch)
        good = tmp_path / "good.json"
        good.write_text(json.dumps({
            "authoritative": {"s-x": {"status": "wip"}, "s-y": {"status": "done"}},
            "cortex": {"s-y": {"status": "done"}}}))        # s-x missing -> breach
        bad = tmp_path / "bad.json"
        bad.write_text("{ this is not valid json")          # reader outage
        d1, d2, d3 = "2026-03-01", "2026-03-02", "2026-03-03"   # contiguous
        monkeypatch.setenv("COG2_PARITY_DATA_JSON", str(good))
        assert cp.run(today=d1, sample_n=2) == 1
        assert _ledger(root)[-1]["escalated"] is None       # no prior date yet
        monkeypatch.setenv("COG2_PARITY_DATA_JSON", str(bad))
        assert cp.run(today=d2) == 1
        assert _ledger(root)[-1]["status"] == "error"       # loud outage
        monkeypatch.setenv("COG2_PARITY_DATA_JSON", str(good))
        assert cp.run(today=d3, sample_n=2) == 1
        last = _ledger(root)[-1]
        assert last["status"] == "breach"
        assert "s-x" in last["open_breaches"]               # re-flagged after outage
        assert last["escalated"] == "card-filed"            # ladder survived outage
        assert rec.read_text().count("\n") == 1             # exactly one card


# ===========================================================================
# --probe (cabinet-doctor): pure file inspection
# ===========================================================================

class TestProbe:
    def test_nofile(self, tmp_path, monkeypatch, capsys):
        _root(tmp_path, monkeypatch)
        assert cp.probe() == 0
        assert capsys.readouterr().out.strip() == "NOFILE"

    def test_ok_token(self, tmp_path, monkeypatch, capsys):
        _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        _seam(tmp_path, monkeypatch, {"t1": {"status": "done"}},
              {"t1": {"status": "done"}})
        cp.run(today="2026-07-22")
        capsys.readouterr()                 # drain run()'s stdout
        cp.probe()
        assert capsys.readouterr().out.strip().startswith("OK ")

    def test_breach_token(self, tmp_path, monkeypatch, capsys):
        _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        _seam(tmp_path, monkeypatch, {"t1": {"status": "blocked"}},
              {"t1": {"status": "wip"}})
        cp.run(today="2026-07-22")
        capsys.readouterr()                 # drain run()'s stdout
        cp.probe()
        assert capsys.readouterr().out.strip().startswith("BREACH ")

    def test_stale_token(self, tmp_path, monkeypatch, capsys):
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_STALE_S", "1")
        path = root / "cabinet" / "logs" / "cog2-parity.jsonl"
        path.write_text(json.dumps({"ts": "2000-01-01T00:00:00Z",
                                    "date": "2000-01-01", "status": "ok",
                                    "sampled": 3}) + "\n")
        cp.probe()
        assert capsys.readouterr().out.strip().startswith("STALE ")


# ===========================================================================
# security — untrusted subject/answer text
# ===========================================================================

class TestUntrustedText:
    def test_hostile_answer_is_scrubbed_and_never_reaches_the_card_argv(
            self, tmp_path, monkeypatch):
        root = _root(tmp_path, monkeypatch)
        monkeypatch.setenv("COG2_PARITY_SAMPLE_FLOOR", "1")
        rec = _stub_attention(tmp_path, monkeypatch)
        hostile = "wip\n$(rm -rf /)\t evil"
        _seam(tmp_path, monkeypatch, {"t1": {"status": "done"}},
              {"t1": {"status": hostile}})
        # two consecutive breach days so the card is actually filed on day 2
        cp.run(today="2026-07-21")
        cp.run(today="2026-07-22")
        # ledger: the answer may appear as INERT text but NO RAW control char
        # (newline/tab/etc.) survives into the JSONL display fields.
        for b in _ledger(root)[-1]["breaches"]:
            for field in ("subject", "reason", "domain", "cortex"):
                val = str(b.get(field, ""))
                assert all(ord(c) >= 32 for c in val), \
                    f"raw control char leaked into {field!r}: {val!r}"
        # captain card argv is FIXED-SHAPE (counts only) — the raw answer text,
        # scrubbed or not, never reaches it.
        assert rec.exists()
        assert "rm -rf" not in rec.read_text()


# ===========================================================================
# F3 — a CONFIGURED consequence reader that fails is a LOUD error, not {}
# ===========================================================================

class TestConfiguredConsequenceReader:
    def _inject_failing_consequence(self, monkeypatch):
        """Register a fake framework.fidelity.consequence whose read_ledger
        RAISES, so `from framework.fidelity import consequence` resolves to it
        (credential/format rot, deterministic — no live event dir needed)."""
        import types
        fk_root = types.ModuleType("framework")
        fk_fid = types.ModuleType("framework.fidelity")
        fk_con = types.ModuleType("framework.fidelity.consequence")
        fk_root.fidelity = fk_fid
        fk_fid.consequence = fk_con

        def _boom():
            raise RuntimeError("consequence ledger unreadable (rot)")

        fk_con.read_ledger = _boom
        monkeypatch.setitem(sys.modules, "framework", fk_root)
        monkeypatch.setitem(sys.modules, "framework.fidelity", fk_fid)
        monkeypatch.setitem(sys.modules, "framework.fidelity.consequence", fk_con)

    def test_F3_configured_reader_failure_raises_loud(self, tmp_path, monkeypatch):
        _root(tmp_path, monkeypatch)
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        self._inject_failing_consequence(monkeypatch)
        with pytest.raises(cp._ConfiguredButFailing) as exc:
            cp._authoritative_from_consequence()
        # the reason is INERT (exception class name only) — never a path/stderr.
        assert "RuntimeError" in str(exc.value)

    def test_F3_unconfigured_reader_is_silent_empty(self, tmp_path, monkeypatch):
        _root(tmp_path, monkeypatch)   # CABINET_EVENT_LOG_DIR unset by _root
        # env unset -> genuinely no consequence source -> honest {}, never raises
        self._inject_failing_consequence(monkeypatch)   # even if a reader exists
        assert cp._authoritative_from_consequence() == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
