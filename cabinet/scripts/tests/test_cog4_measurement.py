"""COG-4 N6 — the latency/cost MEASUREMENT gate battery (§10, MR2 — the
phantom-M6 class must not recur; LESSONS L1102).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §10 + §1 N6.
Four legs, at exactly the §10.5 honesty strength:

  1. ANTI-PHANTOM (live): `COG4_ENFORCE_BOUND` must have >= 1 REAL consumer
     file in the SAME commit-class that introduces the flag (§10.3). THIS FILE
     is one of the two designated consumers (verify twin + this test) — it
     reads the flag below — and the grep-style test asserts a CONSUMPTION
     pattern (environ read / shell export), never a doc mention. Scratch-tree
     controls prove the scanner bites.
  2. VERIFY-TWIN ARM (vacuity, W1-u2 idiom) — RETIREMENT CONDITION: retire the
     skip when `cabinet/scripts/verify-cognitive-phase4.sh` lands; the landed
     arm asserts the twin consumes COG4_ENFORCE_BOUND (a twin landing WITHOUT
     the flag REDs immediately — the §10.3 same-commit armed-consumer law; a
     twin landing WITH it REDs the companion so the skip cannot silently
     persist).
  3. DETERMINISTIC PROXIES (live, ALWAYS-ON — §10.5): tool/MCP activation
     counts + budget units are EXACT functions of the schedule artifact
     (§7.2 decision rows). Computed here from a seeded fixture schedule.jsonl;
     exact-compared; the seeded over-activation / inflated-budget regression
     fixture REDs with NO env flag needed (proxies are always-on).
  4. WALL-CLOCK TRIPWIRE (measured, env-armed — §10.5): asserted only under
     COG4_ENFORCE_BOUND=1 with a DECLARED measure-only skip otherwise (the
     COG3_ENFORCE_P95 idiom). The bound formula is the S0 floor-aware note —
     max(p95 x 1.25, p95 + 5s) for sub-10s rows — encoded in
     `lib_cog4_floors.wall_clock_bound` and proven here; the seeded
     inflated-p95 mutant REDs when armed. The REAL pilot baseline arm is
     vacuity-guarded — RETIREMENT CONDITION: retire the skip when
     `cabinet/scripts/cog4-measure.py` + the S0 baseline artifact land; the
     landed arm binds the real pilot p95s to wall_clock_bound and the real
     schedule-artifact proxies to the S0 baseline.

S0: python3.12, no DB, no network, file-seeded, deterministic (no clock in any
assertion). Provenance: authored per the 2026-07-07 full-autonomy grant + the
2026-07-20 cognitive-masterplan continuous grant (COG-4 W2 corpus, unit T3).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_floors as FL  # noqa: E402

_FLAG = "COG4_ENFORCE_BOUND"
_VERIFY_TWIN_REL = "cabinet/scripts/verify-cognitive-phase4.sh"
_MEASURE_CLI_REL = "cabinet/scripts/cog4-measure.py"


def _enforced() -> bool:
    """THE §10.3 designated consumption of COG4_ENFORCE_BOUND in this file —
    read at call time (not import time) so the armed verify twin and the
    monkeypatch-armed mutant tests both exercise the same seam."""
    return os.environ.get("COG4_ENFORCE_BOUND") == "1"


# ---------------------------------------------------------------------------
# 1) anti-phantom — the flag must have a REAL consumer, mechanically
# ---------------------------------------------------------------------------
# Consumption patterns, never mentions: a python environ read or a shell
# export/expansion. Comment lines are stripped first (a mention in a comment
# is a doc, not a consumer).
_PY_CONSUME = re.compile(
    r"environ(?:\.get\(|\[)\s*['\"]" + _FLAG + r"['\"]"
    r"|getenv\(\s*['\"]" + _FLAG + r"['\"]")
_SH_CONSUME = re.compile(r"(?:export\s+" + _FLAG + r"=|\$\{?" + _FLAG + r"\b)")


def _consuming_files(root: Path) -> list[str]:
    """Repo-relative paths of every REAL consumer of the flag under the
    consumer surfaces (cabinet/scripts/**.py|.sh — CLIs, twins, tests).
    Docs and config trees are deliberately NOT consumer surfaces."""
    hits: list[str] = []
    surface = root / "cabinet" / "scripts"
    if not surface.is_dir():
        return hits
    for path in sorted(surface.rglob("*")):
        if path.suffix not in (".py", ".sh") or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pat = _PY_CONSUME if path.suffix == ".py" else _SH_CONSUME
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue  # comment mention != consumption
            if pat.search(line):
                hits.append(str(path.relative_to(root)))
                break
    return hits


class TestAntiPhantomConsumer:
    def test_flag_has_a_real_consumer_now(self):
        """§10.3: the flag name appears in >= 1 REAL consumer file — live, no
        skip. This file itself is a designated consumer (the `_enforced()`
        environ read), so the invariant holds from the corpus commit onward."""
        hits = _consuming_files(_REPO)
        assert hits, (
            f"{_FLAG} has NO real consumer under cabinet/scripts — the phantom-M6 "
            f"class (LESSONS L1102): a flag nothing consumes is decoration")
        assert "cabinet/scripts/tests/test_cog4_measurement.py" in hits, (
            f"this battery must itself consume {_FLAG} (§10.3 names it a designated "
            f"consumer); found consumers: {hits}")

    def test_scanner_bites_doc_mention_vs_consumer(self, tmp_path):
        """Scratch-tree negative controls: a docs-style mention (comment line or
        prose file) counts ZERO; an environ read / shell export counts ONE."""
        scripts = tmp_path / "cabinet" / "scripts"
        scripts.mkdir(parents=True)
        # doc-mention-only tree -> zero consumers
        (scripts / "notes.py").write_text(
            "# COG4_ENFORCE_BOUND is documented here but never read\n"
            "x = 1\n", encoding="utf-8")
        (tmp_path / "cabinet" / "scripts" / "README.sh").write_text(
            "# mentions COG4_ENFORCE_BOUND in a comment only\n", encoding="utf-8")
        assert _consuming_files(tmp_path) == []
        # a real python consumer bites
        (scripts / "consumer.py").write_text(
            "import os\nARMED = os.environ.get('COG4_ENFORCE_BOUND') == '1'\n",
            encoding="utf-8")
        assert _consuming_files(tmp_path) == ["cabinet/scripts/consumer.py"]
        # a real shell consumer bites too
        (scripts / "twin.sh").write_text(
            "export COG4_ENFORCE_BOUND=1\n", encoding="utf-8")
        assert set(_consuming_files(tmp_path)) == {
            "cabinet/scripts/consumer.py", "cabinet/scripts/twin.sh"}

    def test_verify_twin_arm(self):
        """VACUITY GUARD — RETIREMENT CONDITION: retire this skip when
        cabinet/scripts/verify-cognitive-phase4.sh lands; the retired arm keeps
        exactly the first assertion below (the twin consumes COG4_ENFORCE_BOUND,
        §10.3). While the twin is absent the arm skips; the COMPANION failure
        goes RED the instant the twin appears, so the skip cannot silently
        persist (the W1-u2 idiom)."""
        twin = _REPO / _VERIFY_TWIN_REL
        if twin.exists():
            text = twin.read_text(encoding="utf-8")
            assert _FLAG in text, (
                f"{_VERIFY_TWIN_REL} has landed WITHOUT consuming {_FLAG} — the §10.3 "
                f"same-commit armed-consumer law is violated (the phantom-M6 class)")
            pytest.fail(
                f"{_VERIFY_TWIN_REL} has LANDED (and carries {_FLAG}) — retire this "
                f"vacuity skip per the docstring RETIREMENT CONDITION")
        pytest.skip(
            f"VACUITY: {_VERIFY_TWIN_REL} absent this phase — the flag's live consumer "
            f"is this battery itself; retire the skip when the verify twin lands.")


# ---------------------------------------------------------------------------
# 2) deterministic proxies — EXACT from the schedule artifact (always-on)
# ---------------------------------------------------------------------------
# §7.2 decision-row shape (organ, operation, descriptor, reason, budget_units,
# deps, tie_break_key). The proxies are pure folds over those rows:
#   activations           = number of decision rows (one organ activation each)
#   activations_by_capability = row count per descriptor.capability
#   budget_units_total    = sum of row budget_units
def proxies_from_schedule_rows(rows: list[dict]) -> dict:
    by_cap: dict[str, int] = {}
    total_units = 0
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"schedule row {i} is not a mapping")
        units = row.get("budget_units")
        if not isinstance(units, int) or isinstance(units, bool) or units < 0:
            raise ValueError(f"schedule row {i}: budget_units must be an integer >= 0")
        total_units += units
        cap = (row.get("descriptor") or {}).get("capability")
        if not isinstance(cap, str) or "/" not in cap:
            raise ValueError(f"schedule row {i}: descriptor.capability must be a "
                             f"namespaced '<domain>/<operation>' id")
        by_cap[cap] = by_cap.get(cap, 0) + 1
    return {
        "activations": len(rows),
        "activations_by_capability": dict(sorted(by_cap.items())),
        "budget_units_total": total_units,
    }


def proxy_bound_violations(measured: dict, baseline: dict) -> list[str]:
    """EXACT tolerance (§10.2): any measured proxy above its baseline is a
    regression. Below/equal is fine (shrink is welcome)."""
    v: list[str] = []
    if measured["activations"] > baseline["activations"]:
        v.append(f"activations {measured['activations']} > baseline "
                 f"{baseline['activations']} (over-activation)")
    if measured["budget_units_total"] > baseline["budget_units_total"]:
        v.append(f"budget_units_total {measured['budget_units_total']} > baseline "
                 f"{baseline['budget_units_total']} (inflated cost)")
    for cap, n in measured["activations_by_capability"].items():
        base = baseline["activations_by_capability"].get(cap, 0)
        if n > base:
            v.append(f"capability {cap!r} activations {n} > baseline {base}")
    return v


_FIXTURE_ROWS = [
    {"organ": "undo-sweep", "operation": "undo/sweep.expired",
     "descriptor": {"capability": "undo/sweep.expired"},
     "reason": "periodic", "budget_units": 3, "deps": [], "tie_break_key": "a1"},
    {"organ": "undo-sweep", "operation": "undo/sweep.orphans",
     "descriptor": {"capability": "undo/sweep.orphans"},
     "reason": "periodic", "budget_units": 2, "deps": [], "tie_break_key": "a2"},
    {"organ": "world-census", "operation": "census/rooms.count",
     "descriptor": {"capability": "census/rooms.count"},
     "reason": "periodic", "budget_units": 5, "deps": [], "tie_break_key": "b1"},
    {"organ": "prediction-calibration", "operation": "calibration/brier.fold",
     "descriptor": {"capability": "calibration/brier.fold"},
     "reason": "periodic", "budget_units": 8, "deps": [], "tie_break_key": "c1"},
]
_FIXTURE_BASELINE = {
    "activations": 4,
    "activations_by_capability": {
        "calibration/brier.fold": 1, "census/rooms.count": 1,
        "undo/sweep.expired": 1, "undo/sweep.orphans": 1},
    "budget_units_total": 18,
}


class TestDeterministicProxies:
    def _write_artifact(self, tmp_path: Path, rows: list[dict]) -> Path:
        art = tmp_path / "schedule.jsonl"
        art.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                       encoding="utf-8")
        return art

    def test_proxies_exact_from_fixture_artifact(self, tmp_path):
        """The proxies are EXACT functions of the artifact bytes: write the
        seeded schedule.jsonl, re-parse it, and the fold reproduces the pinned
        baseline integers exactly (no tolerance, no clock)."""
        art = self._write_artifact(tmp_path, _FIXTURE_ROWS)
        rows = [json.loads(line) for line in art.read_text(encoding="utf-8").splitlines()]
        assert proxies_from_schedule_rows(rows) == _FIXTURE_BASELINE
        # a rewrite of the re-parsed rows is byte-identical AND reproduces the
        # same proxies (the artifact is the sole input — determinism)
        again = tmp_path / "again"
        again.mkdir()
        art2 = self._write_artifact(again, rows)
        assert art2.read_bytes() == art.read_bytes()
        rows2 = [json.loads(line) for line in art2.read_text(encoding="utf-8").splitlines()]
        assert proxies_from_schedule_rows(rows2) == _FIXTURE_BASELINE

    def test_clean_fixture_has_no_proxy_regression(self):
        measured = proxies_from_schedule_rows(_FIXTURE_ROWS)
        assert proxy_bound_violations(measured, _FIXTURE_BASELINE) == []

    def test_over_activation_mutant_reds(self):
        """NEGATIVE CONTROL (§10.4) — a fold admitting an over-activation plan:
        one extra decision row REDs the always-on proxy battery (no env flag —
        proxies are in the always-on battery per §10.5)."""
        mutant = _FIXTURE_ROWS + [
            {"organ": "undo-sweep", "operation": "undo/sweep.expired",
             "descriptor": {"capability": "undo/sweep.expired"},
             "reason": "make-work", "budget_units": 0, "deps": [], "tie_break_key": "z9"}]
        v = proxy_bound_violations(proxies_from_schedule_rows(mutant), _FIXTURE_BASELINE)
        assert any("over-activation" in x for x in v), v
        assert any("undo/sweep.expired" in x for x in v), v

    def test_inflated_cost_mutant_reds(self):
        """NEGATIVE CONTROL (§10.4) — an organ manifest with an inflated cost
        model: same activations, spiked budget_units REDs on the exact budget
        proxy."""
        mutant = [dict(r) for r in _FIXTURE_ROWS]
        mutant[3] = dict(mutant[3], budget_units=800)
        v = proxy_bound_violations(proxies_from_schedule_rows(mutant), _FIXTURE_BASELINE)
        assert any("inflated cost" in x for x in v), v
        # activations did NOT regress — only the budget leg fires
        assert not any("over-activation" in x for x in v), v

    def test_malformed_rows_fail_loud(self):
        with pytest.raises(ValueError):
            proxies_from_schedule_rows([{"budget_units": "3",
                                         "descriptor": {"capability": "a/b"}}])
        with pytest.raises(ValueError):
            proxies_from_schedule_rows([{"budget_units": 3,
                                         "descriptor": {"capability": "flat_token"}}])


# ---------------------------------------------------------------------------
# 3) wall-clock — the floor-aware bound formula + the env-armed tripwire
# ---------------------------------------------------------------------------
def wall_clock_violations(measured_p95_s: dict[str, float],
                          baseline_p95_s: dict[str, float]) -> list[str]:
    """Per pilot row: measured p95 must stay <= wall_clock_bound(baseline p95)
    (§10.2 + the S0 floor-aware note). A measured row missing its baseline is a
    violation (no borrowed numbers — §10.1)."""
    v: list[str] = []
    for row, measured in sorted(measured_p95_s.items()):
        base = baseline_p95_s.get(row)
        if base is None:
            v.append(f"{row}: no S0 baseline for this row (freshly measured "
                     f"baselines only — §10.1)")
            continue
        bound = FL.wall_clock_bound(base)
        if measured > bound:
            v.append(f"{row}: p95 {measured:.3f}s exceeds bound {bound:.3f}s "
                     f"(baseline {base:.3f}s)")
    return v


class TestWallClockBoundFormula:
    """The S0 floor-aware bound note, encoded and proven (live, pure)."""

    @pytest.mark.parametrize("p95,expected", [
        (0.0, 5.0),          # sub-10s: the +5s absolute floor dominates
        (0.005, 5.005),      # a 5ms row gets a 5.005s bound, not 6.25ms noise
        (2.0, 7.0),          # max(2.5, 7.0)
        (9.99, 14.99),       # max(12.4875, 14.99)
        (10.0, 12.5),        # >= 10s: pure x1.25
        (40.0, 50.0),
    ])
    def test_bound_values(self, p95, expected):
        assert FL.wall_clock_bound(p95) == pytest.approx(expected)

    def test_sub_10s_rows_always_get_the_absolute_floor(self):
        # under 10s, p95 x 0.25 < 5s always, so the +5s arm is the max — the
        # floor-aware note is exactly the anti-noise-width guarantee
        for p95 in (0.001, 0.5, 3.0, 9.999):
            assert FL.wall_clock_bound(p95) == pytest.approx(p95 + 5.0)

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            FL.wall_clock_bound(-1.0)
        with pytest.raises(ValueError):
            FL.wall_clock_bound(True)
        with pytest.raises(ValueError):
            FL.wall_clock_bound("2.0")  # type: ignore[arg-type]


_WALL_FIXTURE_BASELINE = {"undo-sweep": 2.0, "world-census": 12.0}


class TestWallClockTripwire:
    def test_inflated_p95_mutant_reds_when_armed(self, monkeypatch):
        """NEGATIVE CONTROL (§10.4): the seeded regression fixture REDs when
        armed. Armed here via monkeypatch on the SAME env seam the verify twin
        exports — proving the arm bites without needing the twin."""
        monkeypatch.setenv(_FLAG, "1")
        assert _enforced()
        v = wall_clock_violations({"undo-sweep": 8.0, "world-census": 12.5},
                                  _WALL_FIXTURE_BASELINE)
        assert any(x.startswith("undo-sweep:") and "exceeds bound" in x for x in v), v
        # world-census 12.5 <= 15.0 bound — only the seeded regression fires
        assert not any(x.startswith("world-census:") for x in v), v
        # inside the bound -> clean
        assert wall_clock_violations({"undo-sweep": 6.9, "world-census": 14.9},
                                     _WALL_FIXTURE_BASELINE) == []

    def test_missing_baseline_row_is_a_violation(self):
        v = wall_clock_violations({"new-organ": 1.0}, _WALL_FIXTURE_BASELINE)
        assert v and "no S0 baseline" in v[0]

    def test_tripwire_posture_declared_skip_when_unarmed(self):
        """The §10.5 honesty clause, mechanically: wall-clock is a MEASURED
        tripwire — unarmed runs record the posture as a DECLARED skip; the
        armed verify twin runs this same arm live (the fixture bounds hold
        deterministically, so the armed run is green)."""
        if not _enforced():
            pytest.skip(
                "N6 wall-clock measure-only (COG4_ENFORCE_BOUND unset): tripwire not "
                "asserted — DECLARED skip per §10.5; verify-cognitive-phase4.sh arms it. "
                "This is a posture skip, not a vacuity skip: it stays after the twin "
                "lands (armed runs execute the assertion below).")
        assert wall_clock_violations(
            {row: p95 for row, p95 in _WALL_FIXTURE_BASELINE.items()},
            _WALL_FIXTURE_BASELINE) == []

    def test_real_pilot_measurement_arm(self):
        """VACUITY GUARD — RETIREMENT CONDITION: retire this skip when
        cabinet/scripts/cog4-measure.py + the S0 baseline artifact land (§10.1);
        the retired arm loads the REAL pilot baseline, binds each row's measured
        p95 to lib_cog4_floors.wall_clock_bound, and binds the real
        schedule-artifact proxies to the S0 baseline. The COMPANION assertion
        REDs the moment the measure CLI lands, so the skip cannot silently
        persist (the W1-u2 idiom)."""
        cli = _REPO / _MEASURE_CLI_REL
        assert not cli.exists(), (
            f"{_MEASURE_CLI_REL} has LANDED — retire this vacuity skip and bind the "
            f"real pilot baseline per the docstring RETIREMENT CONDITION")
        pytest.skip(
            f"VACUITY: {_MEASURE_CLI_REL} + the S0 baseline artifact absent this "
            f"phase-stage — the bound machinery is proven on fixtures above; retire "
            f"when the measure CLI lands.")
