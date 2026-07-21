"""COG-1 W4 — parity monitor: predicate + freshness floor + escalation
(§8.3, §12.2 item 7).

Tests-first (foundry.md:137). The relay WRITES per-cycle liveness samples to
cabinet/logs/cog1-parity.jsonl (W3); the extended task-sync-drift-falsifier
READS them, applies the floor + the asymmetric predicate, and escalates via its
EXISTING second-date captain-card path. This file owns:

  * parity predicate — asymmetric, EFFECTIVE-mapped transitions grounded in
        officer_task_history: legacy stream ⊆ outbox (asymmetric — dashboard
        rows are outbox-only, by design); every non-suppressed history
        transition has exactly one outbox row (coverage); no outbox row lacks a
        history row (no phantom). actor-'cpo-etl' history is EXCLUDED
        (suppression). Ledger `outbox_*` vocabulary is EXCLUDED (the predicate
        keys on rows/stream/history only — no double-count across the three
        outbox_* writer families).
        mutants: raw-column matching false-breaches a blocked transition; no
        suppression exclusion false-breaches the ETL; a symmetric predicate
        false-breaches a dashboard-only row.
  * freshness floor — a soak day with < 1,000 of 1,440 nominal @60s samples, or
        an ABSENT day, is a BREACH window (a dead/never-armed relay cannot pass
        vacuously). control: a floor that never breaches passes a short day.
  * escalation — two consecutive breach windows → ONE captain card via the
        attention gateway (second-date semantics); a single breach self-heals.
  * legacy-stream comparand + §8.3 WINDOW — the runtime data source
        (_cog1_window_from_postgres) reads the legacy authoritative stream
        cabinet:tasks:events read-only (redis-cli --json XRANGE) so ALL THREE
        §8.3 clauses evaluate at runtime, not just coverage/phantom; all three
        planes share ONE window bound (the earliest outbox occurred_at = the
        moment 047's capture trigger went live) so a real work store's PRE-047
        history + pre-047 legacy stream can never false-breach. pure gates for
        the parser/floor/argv; a PG17+redis-gated integration gate proves a
        pre-pilot event is windowed out (no false breach) and a post-pilot loss
        breaches (the M1 legacy⊆outbox instrument actually fires).

Interpreter python3.12. The predicate/floor/escalation gates are PURE (no
DB/redis). The legacy-read integration gate is PG17+redis-gated (skips without
the toolchain, same pattern as the sibling W3/W4 relay/replay-hash suites).
"""
from __future__ import annotations

import datetime as _dt
import importlib.util as _ilu
import json
import os
import stat
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_SCRIPT = _HERE.parent / "task-sync-drift-falsifier.py"
_spec = _ilu.spec_from_file_location("task_sync_drift_falsifier", _SCRIPT)
tsd = _ilu.module_from_spec(_spec)
sys.modules["task_sync_drift_falsifier"] = tsd
assert _spec and _spec.loader
_spec.loader.exec_module(tsd)


# ===========================================================================
# asymmetric effective-mapped predicate
# ===========================================================================

def _ob(task_id, old_status, new_status, *, old_blocked=None, new_blocked=False,
        actor="cos"):
    return {"task_id": task_id, "old_status": old_status, "new_status": new_status,
            "old_blocked": old_blocked, "new_blocked": new_blocked, "actor": actor}


def _hist(task_id, from_status, to_status, *, from_blocked=None, to_blocked=False,
          actor="cos"):
    return {"task_id": task_id, "from_status": from_status, "to_status": to_status,
            "from_blocked": from_blocked, "to_blocked": to_blocked, "actor": actor}


def _leg(task_id, old_status, new_status):
    return {"task_id": task_id, "old_status": old_status, "new_status": new_status}


class TestParityPredicate:
    def test_ok_when_outbox_matches_history_and_legacy(self):
        v = tsd.cog1_parity_predicate(
            outbox_rows=[_ob(1, None, "wip")],
            history_transitions=[_hist(1, None, "wip")],
            legacy_stream=[_leg(1, "", "wip")])
        assert v["status"] == "ok", v

    def test_effective_mapping_blocked_transition_matches(self):
        # raw columns say wip->wip (+blocked flag); EFFECTIVE says wip->blocked,
        # which is exactly what the legacy stream and history overlay carry.
        v = tsd.cog1_parity_predicate(
            outbox_rows=[_ob(1, "wip", "wip", old_blocked=False, new_blocked=True)],
            history_transitions=[_hist(1, "wip", "wip", from_blocked=False,
                                       to_blocked=True)],
            legacy_stream=[_leg(1, "wip", "blocked")])
        assert v["status"] == "ok", v

    def test_mutant_raw_column_matching_false_breaches_blocked(self):
        """Control: WITHOUT the effective mapping, a blocked transition's raw
        'wip' never matches the legacy 'blocked' → false breach (detected)."""
        from collections import Counter
        outbox = [_ob(1, "wip", "wip", new_blocked=True)]
        legacy = [_leg(1, "wip", "blocked")]
        raw_o = Counter((r["task_id"], r["old_status"] or "", r["new_status"])
                        for r in outbox)
        raw_l = Counter((e["task_id"], e["old_status"] or "", e["new_status"])
                        for e in legacy)
        assert (raw_l - raw_o), "raw matching leaves the legacy event uncovered"
        # the real predicate, using the effective mapping, does NOT breach:
        assert tsd.cog1_parity_predicate(
            outbox_rows=outbox,
            history_transitions=[_hist(1, "wip", "wip", to_blocked=True)],
            legacy_stream=legacy)["status"] == "ok"

    def test_suppression_excludes_cpo_etl_history(self):
        # an ETL (suppressed) history transition has NO outbox row by design;
        # it must NOT breach because actor-'cpo-etl' is excluded from coverage.
        v = tsd.cog1_parity_predicate(
            outbox_rows=[],
            history_transitions=[_hist(9, None, "wip", actor="cpo-etl")],
            legacy_stream=[])
        assert v["status"] == "ok", v

    def test_control_non_etl_history_without_outbox_row_breaches(self):
        # the SAME shape but a normal actor DOES breach — proving the exclusion
        # is actor-scoped, not a blanket "ignore uncovered history".
        v = tsd.cog1_parity_predicate(
            outbox_rows=[],
            history_transitions=[_hist(9, None, "wip", actor="cos")],
            legacy_stream=[])
        assert v["status"] == "breach"
        assert any(c[0] == "history_not_covered" for c in v["breaches"]), v

    def test_asymmetric_dashboard_only_outbox_row_is_ok(self):
        # a dashboard-origin transition exists only on the new path (no legacy
        # event). Asymmetric predicate (legacy ⊆ outbox) → ok.
        v = tsd.cog1_parity_predicate(
            outbox_rows=[_ob(3, None, "wip"), _ob(4, None, "queue")],
            history_transitions=[_hist(3, None, "wip"), _hist(4, None, "queue")],
            legacy_stream=[_leg(3, "", "wip")])  # task 4 never hit the legacy path
        assert v["status"] == "ok", v

    def test_legacy_event_without_outbox_row_breaches(self):
        v = tsd.cog1_parity_predicate(
            outbox_rows=[],
            history_transitions=[],
            legacy_stream=[_leg(5, "", "wip")])
        assert v["status"] == "breach"
        assert any(c[0] == "legacy_not_covered" for c in v["breaches"]), v

    def test_phantom_outbox_row_without_history_breaches(self):
        v = tsd.cog1_parity_predicate(
            outbox_rows=[_ob(6, None, "wip")],
            history_transitions=[],
            legacy_stream=[])
        assert v["status"] == "breach"
        assert any(c[0] == "phantom_outbox" for c in v["breaches"]), v

    def test_mutant_symmetric_predicate_would_false_breach_dashboard(self):
        """Control: a SYMMETRIC predicate (require outbox ⊆ legacy too) breaches
        on the legitimate dashboard-only row — which the asymmetric one passes."""
        from collections import Counter
        outbox = [_ob(4, None, "queue")]
        legacy: list = []
        o = Counter((r["task_id"], "", r["new_status"]) for r in outbox)
        ll = Counter((e["task_id"], e["old_status"] or "", e["new_status"])
                     for e in legacy)
        assert (o - ll), "a symmetric check flags the dashboard row"
        assert tsd.cog1_parity_predicate(
            outbox_rows=outbox, history_transitions=[_hist(4, None, "queue")],
            legacy_stream=legacy)["status"] == "ok"

    def test_predicate_keys_on_rows_stream_history_only(self):
        # ledger-vocabulary exclusion: the predicate has no ledger parameter and
        # its verdict depends only on the three data planes (no double-count).
        import inspect
        params = set(inspect.signature(tsd.cog1_parity_predicate).parameters)
        assert params == {"outbox_rows", "history_transitions", "legacy_stream"}

    def test_legacy_stream_optional_when_shadow_only(self):
        # during shadow soak the legacy comparand may be unavailable; the
        # coverage/no-phantom clauses still evaluate against history.
        v = tsd.cog1_parity_predicate(
            outbox_rows=[_ob(1, None, "wip")],
            history_transitions=[_hist(1, None, "wip")])
        assert v["status"] == "ok", v


# ===========================================================================
# freshness floor
# ===========================================================================

def _samples(per_date: dict[str, int]) -> list[dict]:
    lines = []
    for date, count in per_date.items():
        for i in range(count):
            lines.append({"ts": f"{date}T{i // 60:02d}:{i % 60:02d}:00Z",
                          "samples": 1, "dispatched": 0, "terminal": 0,
                          "transient": 0})
    return lines


class TestFreshnessFloor:
    def test_full_day_meets_floor(self):
        f = tsd.cog1_freshness_floor(_samples({"2026-07-18": 1440}),
                                     today="2026-07-19")
        assert f["latest_breach"] is False
        assert f["windows"][-1][0] == "2026-07-18"

    def test_short_day_is_a_breach(self):
        f = tsd.cog1_freshness_floor(_samples({"2026-07-18": 500}),
                                     today="2026-07-19")
        assert f["latest_breach"] is True

    def test_exactly_at_floor_is_not_a_breach(self):
        f = tsd.cog1_freshness_floor(_samples({"2026-07-18": 1000}),
                                     today="2026-07-19")
        assert f["latest_breach"] is False

    def test_absent_day_between_present_days_is_a_breach(self):
        f = tsd.cog1_freshness_floor(
            _samples({"2026-07-18": 1440, "2026-07-20": 1440}),
            today="2026-07-21")
        by_date = {d: (c, b) for d, c, b in f["windows"]}
        assert by_date["2026-07-19"] == (0, True), f["windows"]

    def test_partial_today_is_not_judged(self):
        # the current UTC day is partial (hasn't accrued 1,440 cycles yet).
        f = tsd.cog1_freshness_floor(_samples({"2026-07-20": 300}),
                                     today="2026-07-20")
        assert f["windows"] == []
        assert f["latest_breach"] is False

    def test_two_consecutive_short_days_both_breach(self):
        f = tsd.cog1_freshness_floor(
            _samples({"2026-07-18": 200, "2026-07-19": 200}),
            today="2026-07-20")
        assert [b for _, _, b in f["windows"][-2:]] == [True, True]

    def test_control_disabled_floor_passes_a_short_day(self):
        """Negative control: a floor of 0 (disabled) never breaches a short day
        — proving the 1,000 floor is what catches a dead/never-armed relay."""
        f = tsd.cog1_freshness_floor(_samples({"2026-07-18": 200}),
                                     today="2026-07-19", floor=0)
        assert f["latest_breach"] is False


# ===========================================================================
# legacy-stream comparand read (§8.3 clause 3) — parser + windowed redis read
# ===========================================================================
# The runtime data source (_cog1_window_from_postgres) MUST feed a real
# legacy-stream plane so the asymmetric legacy⊆outbox loss clause evaluates in
# production (not just under the JSON seam). These pure gates pin the redis-cli
# read contract; the PG+redis integration gate below proves the window is sound.

class _FakeProc:
    """A stand-in for subprocess.CompletedProcess (argv-shape + error gates)."""
    def __init__(self, returncode=0, stdout="[]", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestLegacyStreamParse:
    def test_parse_map_form(self):
        raw = json.dumps([
            ["1700000000000-0", {"task_id": "5", "old_status": "",
                                 "new_status": "wip", "actor": "cos",
                                 "context_slug": "cog1", "ts": "t"}],
            ["1700000000001-0", {"task_id": "5", "old_status": "wip",
                                 "new_status": "blocked"}]])
        assert tsd._parse_legacy_entries(raw) == [
            {"task_id": 5, "old_status": "", "new_status": "wip"},
            {"task_id": 5, "old_status": "wip", "new_status": "blocked"}]

    def test_parse_list_form(self):
        # defensive: some redis-cli builds emit fields as a flat [k,v,...] list
        raw = json.dumps([["1-0", ["task_id", "7", "old_status", "wip",
                                   "new_status", "done"]]])
        assert tsd._parse_legacy_entries(raw) == [
            {"task_id": 7, "old_status": "wip", "new_status": "done"}]

    def test_parse_drops_nonnumeric_or_missing(self):
        raw = json.dumps([
            ["1-0", {"task_id": "abc", "new_status": "wip"}],   # non-numeric id
            ["2-0", {"old_status": "", "new_status": "wip"}],    # no task_id
            ["3-0", {"task_id": "9"}],                           # no new_status
            ["4-0", {"task_id": "9", "new_status": "done"}]])    # good
        assert tsd._parse_legacy_entries(raw) == [
            {"task_id": 9, "old_status": "", "new_status": "done"}]

    def test_parse_empty_and_garbage(self):
        assert tsd._parse_legacy_entries("") == []
        assert tsd._parse_legacy_entries("[]") == []
        assert tsd._parse_legacy_entries("not json at all") == []
        assert tsd._parse_legacy_entries(json.dumps({"not": "a list"})) == []


class TestLegacyStreamRead:
    def test_read_windows_by_floor_and_honors_redis_env(self, monkeypatch):
        seen: dict = {}

        def _fake_run(argv, **kw):
            seen["argv"] = argv
            return _FakeProc(returncode=0, stdout="[]")

        monkeypatch.setattr(tsd.shutil, "which", lambda n: "/usr/bin/redis-cli")
        monkeypatch.setattr(tsd.subprocess, "run", _fake_run)
        monkeypatch.setenv("REDIS_HOST", "10.1.1.9")
        monkeypatch.setenv("REDIS_PORT", "6390")
        assert tsd._cog1_legacy_stream_from_redis("1700000000000") == []
        argv = seen["argv"]
        assert argv[0] == "/usr/bin/redis-cli"
        assert argv[argv.index("-h") + 1] == "10.1.1.9"
        assert argv[argv.index("-p") + 1] == "6390"
        assert "--json" in argv
        # server-side window: XRANGE <stream> <floor-ms> +
        i = argv.index("XRANGE")
        assert tsd._COG1_LEGACY_STREAM == "cabinet:tasks:events"
        assert argv[i + 1] == "cabinet:tasks:events"
        assert argv[i + 2] == "1700000000000"
        assert argv[i + 3] == "+"

    def test_read_raises_on_redis_error_without_leaking_stderr(self, monkeypatch):
        monkeypatch.setattr(tsd.shutil, "which", lambda n: "/usr/bin/redis-cli")
        monkeypatch.setattr(tsd.subprocess, "run",
                            lambda *a, **k: _FakeProc(
                                returncode=1, stdout="",
                                stderr="could not connect to secret-host:6379"))
        with pytest.raises(tsd.CanonicalReadError) as ei:
            tsd._cog1_legacy_stream_from_redis("1")
        assert "secret-host" not in str(ei.value)  # exit code only, never stderr

    def test_read_raises_when_redis_cli_absent(self, monkeypatch):
        monkeypatch.setattr(tsd.shutil, "which", lambda n: None)
        with pytest.raises(tsd.CanonicalReadError):
            tsd._cog1_legacy_stream_from_redis("1")

    def test_read_wraps_subprocess_oserror(self, monkeypatch):
        monkeypatch.setattr(tsd.shutil, "which", lambda n: "/usr/bin/redis-cli")

        def _boom(*a, **k):
            raise OSError("exec failed")
        monkeypatch.setattr(tsd.subprocess, "run", _boom)
        with pytest.raises(tsd.CanonicalReadError):
            tsd._cog1_legacy_stream_from_redis("1")


class TestWindowFloor:
    def test_min_occurred_at_to_epoch_ms(self):
        want = int(_dt.datetime(2026, 7, 20, 8, 0, 0,
                                tzinfo=_dt.timezone.utc).timestamp() * 1000)
        assert tsd._cog1_window_floor_ms(
            [{"occurred_at": "2026-07-20T08:00:00Z"}]) == want

    def test_empty_or_stampless_outbox_is_none(self):
        assert tsd._cog1_window_floor_ms([]) is None
        assert tsd._cog1_window_floor_ms([{"occurred_at": None}]) is None
        assert tsd._cog1_window_floor_ms([{"task_id": 1}]) is None

    def test_picks_earliest_across_rows(self):
        rows = [{"occurred_at": "2026-07-20T09:00:00Z"},
                {"occurred_at": "2026-07-20T08:00:00Z"},
                {"occurred_at": "2026-07-20T10:00:00Z"}]
        want = int(_dt.datetime(2026, 7, 20, 8, 0, 0,
                                tzinfo=_dt.timezone.utc).timestamp() * 1000)
        assert tsd._cog1_window_floor_ms(rows) == want

    def test_z_and_offset_spellings_agree(self):
        # postgres row_to_json emits an ISO 'T' stamp with a +00:00 offset
        a = tsd._cog1_window_floor_ms([{"occurred_at": "2026-07-20T08:00:00+00:00"}])
        b = tsd._cog1_window_floor_ms([{"occurred_at": "2026-07-20T08:00:00Z"}])
        assert a == b and a is not None

    def test_microsecond_precision_survives(self):
        f = tsd._cog1_window_floor_ms([{"occurred_at": "2026-07-20T08:00:00.123456+00:00"}])
        base = int(_dt.datetime(2026, 7, 20, 8, 0, 0,
                                tzinfo=_dt.timezone.utc).timestamp() * 1000)
        assert f == base + 123  # 123.456 ms truncated to ms


# ===========================================================================
# escalation (second-date captain card) via run_cog1_parity
# ===========================================================================

def _seed_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "cabroot"
    (root / "cabinet" / "logs").mkdir(parents=True)
    monkeypatch.setenv("CABINET_ROOT", str(root))
    monkeypatch.delenv("CABINET_COG1_PARITY_LOG", raising=False)
    monkeypatch.delenv("COG1_PARITY_DATA_JSON", raising=False)
    monkeypatch.delenv("TASK_SYNC_DRIFT_ATTENTION_SUBMIT", raising=False)
    monkeypatch.delenv("NEON_CONNECTION_STRING", raising=False)
    return root


def _write_parity_log(root: Path, per_date: dict[str, int]) -> Path:
    p = root / "cabinet" / "logs" / "cog1-parity.jsonl"
    with open(p, "w") as fh:
        for line in _samples(per_date):
            fh.write(json.dumps(line) + "\n")
    return p


def _fake_attention(tmp_path, monkeypatch) -> Path:
    capture = tmp_path / "attention-argv.txt"
    script = tmp_path / "fake-attention-submit.sh"
    script.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "' + str(capture) + '"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("TASK_SYNC_DRIFT_ATTENTION_SUBMIT", str(script))
    return capture


def _verdict_lines(root: Path) -> list[dict]:
    p = root / "cabinet" / "logs" / "cog1-parity-verdict.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


class TestEscalation:
    def test_absent_parity_log_is_a_clean_noop(self, tmp_path, monkeypatch):
        _seed_root(tmp_path, monkeypatch)
        assert tsd.run_cog1_parity() == 0
        assert _verdict_lines(tmp_path / "cabroot") == []

    def test_full_day_is_ok_no_card(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch)
        _write_parity_log(root, {"2026-07-18": 1440})
        capture = _fake_attention(tmp_path, monkeypatch)
        assert tsd.run_cog1_parity(today="2026-07-19") == 0
        line = _verdict_lines(root)[-1]
        assert line["status"] == "ok"
        assert not capture.exists()

    def test_first_breach_flags_but_does_not_escalate(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch)
        _write_parity_log(root, {"2026-07-18": 200})
        capture = _fake_attention(tmp_path, monkeypatch)
        assert tsd.run_cog1_parity(today="2026-07-19") == 1
        line = _verdict_lines(root)[-1]
        assert line["status"] == "breach" and line["floor_breach"] is True
        assert line["escalated"] is None
        assert not capture.exists()

    def test_second_consecutive_breach_files_the_card(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch)
        capture = _fake_attention(tmp_path, monkeypatch)
        # day 1: yesterday (07-18) short → first breach, self-heal, no card
        _write_parity_log(root, {"2026-07-18": 200})
        assert tsd.run_cog1_parity(today="2026-07-19") == 1
        assert not capture.exists()
        # day 2: yesterday (07-19) ALSO short → second consecutive → card
        _write_parity_log(root, {"2026-07-18": 200, "2026-07-19": 200})
        assert tsd.run_cog1_parity(today="2026-07-20") == 1
        assert _verdict_lines(root)[-1]["escalated"] == "card-filed"
        assert capture.exists()

    def test_same_day_rerun_never_escalates(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch)
        capture = _fake_attention(tmp_path, monkeypatch)
        _write_parity_log(root, {"2026-07-18": 200})
        assert tsd.run_cog1_parity(today="2026-07-19") == 1
        assert tsd.run_cog1_parity(today="2026-07-19") == 1  # rerun, same date
        for line in _verdict_lines(root):
            assert line["escalated"] is None

    def test_intervening_ok_day_resets_the_ladder(self, tmp_path, monkeypatch):
        root = _seed_root(tmp_path, monkeypatch)
        capture = _fake_attention(tmp_path, monkeypatch)
        _write_parity_log(root, {"2026-07-17": 200})
        assert tsd.run_cog1_parity(today="2026-07-18") == 1     # breach
        _write_parity_log(root, {"2026-07-17": 200, "2026-07-18": 1440})
        assert tsd.run_cog1_parity(today="2026-07-19") == 0     # ok resets
        _write_parity_log(root, {"2026-07-17": 200, "2026-07-18": 1440,
                                 "2026-07-19": 200})
        assert tsd.run_cog1_parity(today="2026-07-20") == 1     # breach again
        assert _verdict_lines(root)[-1]["escalated"] is None    # not consecutive
        assert not capture.exists()

    def test_predicate_breach_via_json_seam_escalates_on_second(self, tmp_path,
                                                                monkeypatch):
        root = _seed_root(tmp_path, monkeypatch)
        capture = _fake_attention(tmp_path, monkeypatch)
        # a healthy floor (so ONLY the predicate can breach), plus a data seam
        # carrying a phantom outbox row (no history) → predicate breach.
        seam = tmp_path / "window.json"
        seam.write_text(json.dumps({
            "outbox_rows": [_ob(6, None, "wip")],
            "history_transitions": [],
            "legacy_stream": []}))
        monkeypatch.setenv("COG1_PARITY_DATA_JSON", str(seam))
        _write_parity_log(root, {"2026-07-18": 1440})
        assert tsd.run_cog1_parity(today="2026-07-19") == 1
        line = _verdict_lines(root)[-1]
        assert line["predicate_breach"] is True and line["floor_breach"] is False
        assert line["escalated"] is None            # first breach
        _write_parity_log(root, {"2026-07-18": 1440, "2026-07-19": 1440})
        assert tsd.run_cog1_parity(today="2026-07-20") == 1
        assert _verdict_lines(root)[-1]["escalated"] == "card-filed"
        assert capture.exists()


# ===========================================================================
# PG17+redis integration — the runtime data source wires the legacy plane and
# WINDOWS all three planes (§8.3). Skips without a PG17 toolchain + redis.
# ===========================================================================
# This is the direct proof for the conformance P3 fix: on a REAL work store
# (which carries pre-047 history and a pre-047 legacy stream)
# _cog1_window_from_postgres() must (a) return a LIST legacy plane, not None, so
# all three §8.3 clauses evaluate, and (b) window every plane to the pilot span
# so pre-pilot rows never false-breach while a genuine post-pilot loss does.

def _load_relay_harness():
    p = _ROOT + "/framework/outbox/tests/lib_relay_harness.py"
    spec = _ilu.spec_from_file_location("lib_relay_harness_parity", p)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HR = _load_relay_harness()
_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)
_REDIS_SKIP = pytest.mark.skipif(not HR.redis_available(), reason=HR.REDIS_SKIP_REASON)


def _point_reads_at(cluster, sb, monkeypatch):
    """Point the falsifier's read-only psql + redis-cli reads at THIS ephemeral
    cluster / redis sandbox (scratch conninfo only — never a live string)."""
    monkeypatch.setenv("NEON_CONNECTION_STRING", cluster.conninfo())
    monkeypatch.delenv("COG1_PARITY_DATA_JSON", raising=False)
    for k, v in sb.env().items():
        monkeypatch.setenv(k, v)
    bindir = HR.pg17_bindir()          # local mode: make `psql` resolvable
    if bindir is not None:
        monkeypatch.setenv("PATH", f"{bindir}:{os.environ.get('PATH', '')}")


def _legacy_xadd(sb, entry_id, task_id, old_status, new_status):
    r = sb.cli("XADD", "cabinet:tasks:events", entry_id,
               "task_id", str(task_id), "old_status", old_status,
               "new_status", new_status, "actor", "cos",
               "context_slug", "cog1", "ts", "harness")
    assert r.returncode == 0, r.stderr


@_PG_SKIP
@_REDIS_SKIP
class TestPostgresWindowWiresLegacyPlane:
    def _cluster(self, tmp_path):
        c = HR.EphemeralPG17(tmp_path / "cog1parity", cabinet_id=HR.CAB_ID)
        c.start()
        c.apply_base_chain()
        c.apply_identity_guc(HR.CAB_ID)
        c.apply_047()
        return c

    def _floor_ms(self, cluster) -> int:
        return int(cluster.one(
            "SELECT (extract(epoch FROM min(occurred_at)) * 1000)::bigint "
            "FROM officer_tasks_outbox;"))

    def test_legacy_plane_is_wired_and_window_excludes_pre_pilot(self, tmp_path,
                                                                 monkeypatch):
        cluster = self._cluster(tmp_path)
        sb = HR.RedisSandbox().start()
        try:
            # one real transition mints outbox+history for `tid`: eff (tid,'',wip)
            tid = HR.seed_transition(cluster, "start", "cos")
            _point_reads_at(cluster, sb, monkeypatch)
            floor = self._floor_ms(cluster)
            # (a) PRE-pilot legacy event (id far below the floor) with NO outbox
            #     row — an unwindowed read would count it a loss (false breach).
            _legacy_xadd(sb, "1-0", 9999, "wip", "done")
            # (b) POST-pilot legacy event matching the real outbox row (auto id
            #     = now-ms, which is >= floor on this single-host harness).
            _legacy_xadd(sb, "*", tid, "", "wip")

            window = tsd._cog1_window_from_postgres()
            assert window is not None
            outbox, history, legacy = window
            # THE FIX: the legacy plane is a LIST (not None) — clause 3 evaluates.
            assert isinstance(legacy, list), "legacy plane must be wired, not None"
            leg_ids = {e["task_id"] for e in legacy}
            assert tid in leg_ids, "in-window legacy event present"
            assert 9999 not in leg_ids, "pre-pilot legacy event windowed OUT"
            # sanity: outbox/history carry the real transition; floor is sane
            assert any(int(r["task_id"]) == tid for r in outbox)
            assert floor > 10 ** 12  # a real ms epoch, not the 1-0 pre-pilot id
            v = tsd.cog1_parity_predicate(outbox_rows=outbox,
                                          history_transitions=history,
                                          legacy_stream=legacy)
            assert v["status"] == "ok", v          # covered + windowed → ok
        finally:
            sb.stop()
            cluster.stop()

    def test_post_pilot_legacy_loss_breaches(self, tmp_path, monkeypatch):
        cluster = self._cluster(tmp_path)
        sb = HR.RedisSandbox().start()
        try:
            HR.seed_transition(cluster, "start", "cos")
            _point_reads_at(cluster, sb, monkeypatch)
            # a POST-pilot legacy event with NO matching outbox row = a real M1
            # loss the asymmetric legacy⊆outbox clause must catch (negative
            # control: without the wired+windowed legacy plane this is invisible).
            _legacy_xadd(sb, "*", 8888, "wip", "done")
            outbox, history, legacy = tsd._cog1_window_from_postgres()
            assert isinstance(legacy, list)
            assert any(e["task_id"] == 8888 for e in legacy)
            v = tsd.cog1_parity_predicate(outbox_rows=outbox,
                                          history_transitions=history,
                                          legacy_stream=legacy)
            assert v["status"] == "breach"
            assert any(c[0] == "legacy_not_covered" for c in v["breaches"]), v
        finally:
            sb.stop()
            cluster.stop()

    def test_pre_pilot_history_windowed_out_coverage_sound(self, tmp_path,
                                                           monkeypatch):
        cluster = self._cluster(tmp_path)
        sb = HR.RedisSandbox().start()
        try:
            tid = HR.seed_transition(cluster, "start", "cos")
            # a fake PRE-pilot history row (transition_at one day before the
            # outbox floor) with NO outbox row: an unwindowed coverage read
            # breaches; windowed to the pilot span it is correctly excluded.
            cluster.psql(
                "INSERT INTO officer_task_history "
                "(task_id, from_status, to_status, from_blocked, to_blocked, "
                " actor, transition_at) VALUES "
                "(:'tid', 'done', 'queue', false, false, 'cos', "
                " NOW() - INTERVAL '1 day');",
                vars={"tid": tid})
            _point_reads_at(cluster, sb, monkeypatch)
            outbox, history, legacy = tsd._cog1_window_from_postgres()
            hkeys = {(h["task_id"], h.get("from_status"), h["to_status"])
                     for h in history}
            assert (tid, "done", "queue") not in hkeys, "pre-pilot history in-window"
            v = tsd.cog1_parity_predicate(outbox_rows=outbox,
                                          history_transitions=history,
                                          legacy_stream=legacy)
            assert v["status"] == "ok", v
        finally:
            sb.stop()
            cluster.stop()

    def test_run_cog1_parity_end_to_end_evaluates_legacy_clause(self, tmp_path,
                                                                monkeypatch):
        # THE runtime entry point (the nightly that gates the ≥7-day cutover
        # soak) must evaluate the legacy⊆outbox clause over the REAL
        # postgres+redis window, not only under the JSON seam. A healthy
        # freshness floor isolates the predicate so a breach can ONLY come from
        # the legacy clause the fix wires.
        cluster = self._cluster(tmp_path)
        sb = HR.RedisSandbox().start()
        try:
            HR.seed_transition(cluster, "start", "cos")
            root = tmp_path / "cabroot"
            (root / "cabinet" / "logs").mkdir(parents=True)
            plog = root / "cabinet" / "logs" / "cog1-parity.jsonl"
            with open(plog, "w") as fh:                  # a full, healthy day
                for i in range(1440):
                    fh.write(json.dumps(
                        {"ts": f"2026-07-18T{i // 60:02d}:{i % 60:02d}:00Z",
                         "samples": 1}) + "\n")
            monkeypatch.setenv("CABINET_ROOT", str(root))
            monkeypatch.setenv("NEON_CONNECTION_STRING", cluster.conninfo())
            monkeypatch.delenv("COG1_PARITY_DATA_JSON", raising=False)
            monkeypatch.delenv("CABINET_COG1_PARITY_LOG", raising=False)
            for k, v in sb.env().items():
                monkeypatch.setenv(k, v)
            bindir = HR.pg17_bindir()
            if bindir is not None:
                monkeypatch.setenv("PATH", f"{bindir}:{os.environ.get('PATH', '')}")
            # a POST-pilot legacy event with NO outbox row = a real M1 loss
            _legacy_xadd(sb, "*", 7777, "wip", "done")
            rc = tsd.run_cog1_parity(today="2026-07-19")
            verdict = [json.loads(l) for l in
                       (root / "cabinet" / "logs" / "cog1-parity-verdict.jsonl")
                       .read_text().splitlines() if l.strip()][-1]
            assert rc == 1
            assert verdict["predicate_skipped"] is False   # real window flowed
            assert verdict["predicate_breach"] is True
            assert verdict["floor_breach"] is False         # floor healthy
            assert "legacy_not_covered" in verdict["note"]
        finally:
            sb.stop()
            cluster.stop()

    def test_redis_down_degrades_legacy_to_none_keeps_history_grounding(
            self, tmp_path, monkeypatch):
        # a redis blip must skip ONLY the belt-and-suspenders legacy clause; the
        # coverage/phantom clauses (DB-grounded) must still evaluate.
        cluster = self._cluster(tmp_path)
        sb = HR.RedisSandbox().start()
        HR.seed_transition(cluster, "start", "cos")
        _point_reads_at(cluster, sb, monkeypatch)
        sb.stop()                                   # kill redis AFTER wiring env
        try:
            outbox, history, legacy = tsd._cog1_window_from_postgres()
            assert legacy is None                   # clause skipped, not crashed
            assert outbox and history               # DB grounding still read
            v = tsd.cog1_parity_predicate(outbox_rows=outbox,
                                          history_transitions=history,
                                          legacy_stream=legacy)
            assert v["status"] == "ok", v
        finally:
            cluster.stop()
