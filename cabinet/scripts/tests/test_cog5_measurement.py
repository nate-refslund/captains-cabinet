"""COG-5 §12.1 — the DECLARED REGRESSION BOUND armed-twin battery (the
COG-4 §10/N6 shape cloned, phase-5 keyed: COG5_ENFORCE_BOUND).

Contract: docs/plans/cognitive-core-phase-5-contract-2026-07-24.md §12.1 —
foundry L146's first sentence discharged mechanically:
  1. S0 fresh baselines — LANDED as the tracked dated artifact
     docs/plans/cog5-s0-baseline-2026-07-24.md (the §12.1.1 baseline of
     record; wall-clock backfilled to n=5, FINAL bound 228.4 s).
  2. Declared tolerances (BEFORE measurement): pass-state metrics ZERO
     regression; sweep violations stay 0; files-swept moves ONLY by the
     phase's own added files (exact-integer accounting); wall-clock bound =
     max(p95*1.25, p95+5s) (floor-aware).
  3. ANTI-PHANTOM: the bound artifact + arming flag must have >=1 REAL
     consumer — keyed on `verify-cognitive-phase5.sh` (the twin, a W6/W7
     surface) with THIS FILE as a designated call-time consumer from the
     corpus commit onward (the COG-4 designated-consumer precedent).
  4. Seeded-regression mutants RED when armed (a seeded battery RED / an
     inflated wall-clock stub) — proven live on fixtures below.

WHAT RUNS LIVE NOW:
  - the LANDED baseline artifact exists, parses fail-loud, and its numbers
    RECONCILE: p95 recomputed from the pooled samples matches the recorded
    182.76 s (linear interpolation, the method of record); the bound
    formula reproduces the recorded FINAL 228.4 s and both recorded arms;
    the recorded bound is never LOOSER than the exact formula; the
    pass-state baselines are all-green as recorded; sweep violations
    baseline = 0;
  - the declared tolerance table is pinned and complete over the four
    §12.1.1 metric families;
  - the anti-phantom consumer scanner finds >=1 REAL consumer of
    COG5_ENFORCE_BOUND (this file), with scratch-tree bite controls
    (doc-mention-only trees count ZERO);
  - the seeded-regression mutants RED when armed via monkeypatch on the
    SAME env seam the future twin will export (battery RED, vanished test,
    inflated wall-clock, unexplained sweep growth, nonzero violations).

VACUITY ARMS (the mergeability pattern — RETIREMENT CONDITION here + a
COMPANION absence assertion that REDs the moment the path lands):
  - THE ARMED TWIN — retire when cabinet/scripts/verify-cognitive-phase5.sh
    lands (W6/W7, the §12.1.3 same-commit anti-phantom law): keep exactly
    the twin-consumes-the-flag and twin-reads-the-baseline-artifact
    assertions from the skipped arm below (the COG-4 RETIRED-LIVE
    precedent, test_cog4_measurement.py leg 2).

Posture skip (NOT vacuity — the COG-4 §10.5 idiom): the measured wall-clock
tripwire arm asserts only under COG5_ENFORCE_BOUND=1 with a DECLARED
measure-only skip otherwise; it STAYS after the twin lands (armed runs
execute it).

S0: python3.12, no DB, no network, file-seeded, deterministic (no clock in
any assertion). Provenance: authored per the 2026-07-07 full-autonomy grant
+ the 2026-07-20 cognitive-masterplan continuous grant (COG-5 W2 corpus,
unit T3).
"""
from __future__ import annotations

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

import lib_cog5_boundary_fixtures as B  # noqa: E402

_FLAG = "COG5_ENFORCE_BOUND"
_TWIN_REL = "cabinet/scripts/verify-cognitive-phase5.sh"
_ARTIFACT = _REPO / B.S0_BASELINE_ARTIFACT_REL


def _enforced() -> bool:
    """THE designated call-time consumption of the arming flag in this file
    (the §12.1.3 anti-phantom law: an exported bound nobody reads is the
    named phantom class) — read at call time so the armed twin and the
    monkeypatch-armed mutants exercise the same seam."""
    return os.environ.get("COG5_ENFORCE_BOUND") == "1"


# ---------------------------------------------------------------------------
# anti-phantom — consumption patterns, never mentions (COG-4 leg 1 cloned)
# ---------------------------------------------------------------------------
_PY_CONSUME = re.compile(
    r"environ(?:\.get\(|\[)\s*['\"]" + _FLAG + r"['\"]"
    r"|getenv\(\s*['\"]" + _FLAG + r"['\"]")
_SH_CONSUME = re.compile(r"(?:export\s+" + _FLAG + r"=|\$\{?" + _FLAG + r"\b)")


def _consuming_files(root: Path) -> list[str]:
    """Repo-relative paths of every REAL consumer of the flag under the
    consumer surfaces (cabinet/scripts/**.py|.sh); comment mentions are
    stripped (a doc is not a consumer)."""
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
                continue
            if pat.search(line):
                hits.append(str(path.relative_to(root)))
                break
    return hits


class TestAntiPhantomConsumer:
    def test_flag_has_a_real_consumer_now(self):
        """§12.1.3: >=1 REAL consumer of the flag exists — live, no skip.
        THIS FILE is the designated corpus-commit consumer (the `_enforced`
        call-time environ read), so the invariant holds from the corpus
        commit until the twin takes over as the primary consumer.
        HONESTY (W2 posture): this assertion is therefore SELF-SATISFYING
        today — the corpus CARRIES the invariant rather than proving an
        external surface reads the bound. The real guarantee is the twin-arm
        pair below (absence companion + vacuity arm), which forces
        verify-cognitive-phase5.sh to consume the flag AND read the baseline
        artifact in the same commit that introduces it."""
        hits = _consuming_files(_REPO)
        assert hits, (
            f"{_FLAG} has NO real consumer under cabinet/scripts — the phantom "
            f"class §12.1.3 names (a bound nobody reads is decoration)")
        assert "cabinet/scripts/tests/test_cog5_measurement.py" in hits, (
            f"this battery must itself consume {_FLAG} (designated consumer); "
            f"found: {hits}")

    def test_scanner_bites_doc_mention_vs_consumer(self, tmp_path):
        """Scratch-tree bite controls: doc-mention-only trees count ZERO; a
        python environ read and a shell export each count ONE."""
        scripts = tmp_path / "cabinet" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "notes.py").write_text(
            "# COG5_ENFORCE_BOUND documented here but never read\nx = 1\n",
            encoding="utf-8")
        (scripts / "README.sh").write_text(
            "# mentions COG5_ENFORCE_BOUND in a comment only\n", encoding="utf-8")
        assert _consuming_files(tmp_path) == []
        (scripts / "consumer.py").write_text(
            "import os\nARMED = os.environ.get('COG5_ENFORCE_BOUND') == '1'\n",
            encoding="utf-8")
        assert _consuming_files(tmp_path) == ["cabinet/scripts/consumer.py"]
        (scripts / "twin.sh").write_text(
            "export COG5_ENFORCE_BOUND=1\n", encoding="utf-8")
        assert set(_consuming_files(tmp_path)) == {
            "cabinet/scripts/consumer.py", "cabinet/scripts/twin.sh"}

    def test_twin_absent_companion(self):
        """COMPANION absence assertion: REDs the moment the phase twin
        lands, forcing the docstring RETIREMENT CONDITION (keep the
        twin-consumes-flag + twin-reads-artifact assertions live)."""
        assert not (_REPO / _TWIN_REL).exists(), (
            f"{_TWIN_REL} LANDED — retire this vacuity arm per the docstring "
            f"RETIREMENT CONDITION: keep exactly the twin-consumes-"
            f"{_FLAG} and twin-reads-the-baseline-artifact assertions "
            f"(the §12.1.3 same-commit anti-phantom law).")

    def test_twin_consumes_flag_and_artifact_arm_vacuity(self):
        """VACUITY SKIP — retire when cabinet/scripts/
        verify-cognitive-phase5.sh lands (W6/W7): the twin must CONSUME
        COG5_ENFORCE_BOUND (a real shell export/expansion, not a comment)
        AND read the tracked §12.1.1 baseline artifact in the same commit
        that introduces them (the anti-phantom law)."""
        twin = _REPO / _TWIN_REL
        if not twin.exists():
            pytest.skip(
                f"vacuity: {_TWIN_REL} not yet landed (W6/W7) — retire when it "
                f"lands; the absence companion above REDs then.")
        text = twin.read_text(encoding="utf-8")
        real_lines = [ln for ln in text.splitlines()
                      if not ln.lstrip().startswith("#")]
        assert any(_SH_CONSUME.search(ln) for ln in real_lines), (
            f"{_TWIN_REL} landed WITHOUT consuming {_FLAG}")
        assert B.S0_BASELINE_ARTIFACT_REL in text, (
            f"{_TWIN_REL} landed WITHOUT reading the §12.1.1 baseline artifact")


# ---------------------------------------------------------------------------
# the LANDED baseline artifact — parsed live, numbers reconciled
# ---------------------------------------------------------------------------
class TestS0BaselineArtifact:
    def test_artifact_exists_and_parses(self):
        """No borrowed numbers (§12.1.1): the tracked dated baseline
        artifact is present and every load-bearing anchor parses."""
        assert _ARTIFACT.exists(), (
            "the §12.1.1 baseline artifact vanished — freshly measured "
            "baselines only, never borrowed")
        parsed = B.lib_cog5_boundary_parse_s0_baseline(
            _ARTIFACT.read_text(encoding="utf-8"))
        assert parsed["pooled_n"] >= 5, "the ≥5-run requirement (B-2) regressed"
        assert len(parsed["wall_clock_samples"]) == parsed["pooled_n"]

    def test_p95_recomputes_from_the_pooled_samples(self):
        """The recorded p95 is an EXACT function of the recorded samples
        under the method of record (linear interpolation) — the artifact
        cannot quietly carry a p95 its own samples do not produce."""
        parsed = B.lib_cog5_boundary_parse_s0_baseline(
            _ARTIFACT.read_text(encoding="utf-8"))
        p95 = B.lib_cog5_boundary_percentile_linear(
            parsed["wall_clock_samples"], 0.95)
        assert p95 == pytest.approx(parsed["p95_recorded"], abs=0.005)

    def test_bound_formula_reproduces_the_recorded_final_bound(self):
        """The declared formula max(p95*1.25, p95+5s) reproduces BOTH
        recorded arms and the FINAL bound; the recorded bound is never
        LOOSER than the exact formula value (1-decimal recording may only
        round DOWN — a conservative record)."""
        parsed = B.lib_cog5_boundary_parse_s0_baseline(
            _ARTIFACT.read_text(encoding="utf-8"))
        p95 = parsed["p95_recorded"]
        assert p95 * 1.25 == pytest.approx(parsed["bound_arm_x125"], abs=0.005)
        assert p95 + 5.0 == pytest.approx(parsed["bound_arm_plus5"], abs=0.005)
        exact = B.lib_cog5_boundary_wall_clock_bound(p95)
        assert exact == pytest.approx(max(parsed["bound_arm_x125"],
                                          parsed["bound_arm_plus5"]), abs=0.005)
        recorded = parsed["final_bound_recorded"]
        assert recorded == pytest.approx(exact, abs=0.06)
        assert recorded <= exact + 1e-9, (
            "the recorded FINAL bound is LOOSER than the formula — a bound "
            "may round conservative (down), never permissive")

    def test_pass_state_baselines_are_green_and_violations_zero(self):
        """§12.1.1(a)/(b)/(d) as recorded: the armed battery is all-green,
        the golden vector is all-pass, and the sweep-violations baseline is
        ZERO (the §12.1.2 zero-tolerance anchor)."""
        parsed = B.lib_cog5_boundary_parse_s0_baseline(
            _ARTIFACT.read_text(encoding="utf-8"))
        assert parsed["battery_green_count"] > 0
        assert parsed["golden_pass"] == parsed["golden_total"]
        assert parsed["sweep_violations"] == 0
        assert B.lib_cog5_boundary_sweep_violation_findings(
            0, parsed["sweep_violations"]) == []
        assert parsed["files_swept"] > 0 and parsed["sweep_trees"] > 0

    def test_parser_fails_loud_on_a_gutted_artifact(self):
        """A bound artifact that stops parsing is a BROKEN baseline, never a
        silent default (fail-loud, both directions)."""
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_parse_s0_baseline("# not a baseline artifact\n")
        text = _ARTIFACT.read_text(encoding="utf-8")
        gutted = text.replace("FINAL BOUND (non-provisional)", "REDACTED")
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_parse_s0_baseline(gutted)


# ---------------------------------------------------------------------------
# the declared tolerance table + the bound formula (live, pure)
# ---------------------------------------------------------------------------
class TestDeclaredTolerances:
    def test_tolerance_table_is_complete_and_exact(self):
        """The §12.1.2 declarations, pinned: pass-state families ZERO;
        sweep violations ZERO; files-swept exact-integer; wall-clock the
        floor-aware formula. The table covers the four §12.1.1 baseline
        families and nothing is left undeclared."""
        table = B.LIB_COG5_BOUNDARY_DECLARED_TOLERANCES
        assert table["cog4_battery_pass_state"] == "zero"
        assert table["golden_eval_pass_state"] == "zero"
        assert table["sweep_violations"] == "zero"
        assert table["files_swept"] == "exact-integer-accounting"
        assert table["wall_clock"] == "max(p95*1.25, p95+5s)"
        assert set(table) == {
            "cog4_battery_pass_state", "golden_eval_pass_state",
            "sweep_violations", "files_swept", "wall_clock"}

    @pytest.mark.parametrize("p95,expected", [
        (0.0, 5.0),        # floor-aware: a sub-second baseline gets +5s
        (0.8, 5.8),        # the task-named sub-second case
        (2.0, 7.0),
        (20.0, 25.0),      # crossover: both arms equal at p95=20
        (40.0, 50.0),      # x1.25 dominates
        (182.76, 228.45),  # THE recorded S0 point
    ])
    def test_bound_formula_values(self, p95, expected):
        assert B.lib_cog5_boundary_wall_clock_bound(p95) == pytest.approx(expected)

    def test_floor_dominates_below_20s(self):
        """The floor-aware guarantee: below the 20s crossover the +5s arm
        is the max — a fast baseline cannot manufacture noise-width REDs."""
        for p95 in (0.001, 0.5, 3.0, 19.999):
            assert B.lib_cog5_boundary_wall_clock_bound(p95) == pytest.approx(p95 + 5.0)

    def test_bound_rejects_garbage(self):
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_wall_clock_bound(-1.0)
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_wall_clock_bound(True)
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_wall_clock_bound("182.76")  # type: ignore[arg-type]

    def test_percentile_method_of_record(self):
        """The linear-interpolation percentile on a known vector (and the
        S0 vector shape): h=(n-1)q with linear interpolation between
        neighbors — the numpy-'linear' method the artifact names."""
        assert B.lib_cog5_boundary_percentile_linear([1.0, 2.0, 3.0, 4.0, 5.0],
                                                     0.5) == pytest.approx(3.0)
        assert B.lib_cog5_boundary_percentile_linear([10.0], 0.95) == pytest.approx(10.0)
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_percentile_linear([], 0.95)
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_percentile_linear([1.0], 1.5)


# ---------------------------------------------------------------------------
# seeded-regression mutants — RED when ARMED (monkeypatch on the same seam)
# ---------------------------------------------------------------------------
_PASS_BASELINE = {
    "test_cog4_alpha": "pass",
    "test_cog4_beta": "pass",
    "eval-001": "pass",
}


class TestSeededRegressionMutants:
    def test_mutant_seeded_battery_red_reds_when_armed(self, monkeypatch):
        """NEGATIVE CONTROL (§12.1.4 — 'a seeded battery RED'): armed via
        monkeypatch on the SAME env seam the twin will export, a
        baseline-green test now failing REDs the zero-tolerance checker;
        the clean vector stays green; an ADDED test is free."""
        monkeypatch.setenv(_FLAG, "1")
        assert _enforced()
        red = {**_PASS_BASELINE, "test_cog4_beta": "fail"}
        violations = B.lib_cog5_boundary_pass_state_violations(_PASS_BASELINE, red)
        assert violations and "zero regression tolerance" in violations[0]
        assert B.lib_cog5_boundary_pass_state_violations(
            _PASS_BASELINE, dict(_PASS_BASELINE)) == []
        grown = {**_PASS_BASELINE, "test_cog5_new": "pass"}
        assert B.lib_cog5_boundary_pass_state_violations(_PASS_BASELINE, grown) == []

    def test_mutant_vanished_baseline_test_reds_when_armed(self, monkeypatch):
        """A VANISHED baseline-green test is a violation (absence is not
        green — deleting the failing test is the classic laundering)."""
        monkeypatch.setenv(_FLAG, "1")
        shrunk = {k: v for k, v in _PASS_BASELINE.items() if k != "eval-001"}
        violations = B.lib_cog5_boundary_pass_state_violations(_PASS_BASELINE, shrunk)
        assert violations and "VANISHED" in violations[0]

    def test_mutant_inflated_wall_clock_stub_reds_when_armed(self, monkeypatch):
        """NEGATIVE CONTROL (§12.1.4 — 'an inflated wall-clock stub'): a
        measured wall-clock past the recorded FINAL bound REDs; within the
        bound stays green. The bound is the ARTIFACT's, freshly parsed —
        never a constant borrowed into this test."""
        monkeypatch.setenv(_FLAG, "1")
        assert _enforced()
        parsed = B.lib_cog5_boundary_parse_s0_baseline(
            _ARTIFACT.read_text(encoding="utf-8"))
        p95 = parsed["p95_recorded"]
        bound = B.lib_cog5_boundary_wall_clock_bound(p95)
        # the inflated stub REDs the real tripwire on the exact escape
        violations = B.lib_cog5_boundary_wall_clock_violations(bound + 60.0, p95)
        assert violations and "exceeds bound" in violations[0], violations
        # an honest run inside the bound stays green
        assert B.lib_cog5_boundary_wall_clock_violations(bound - 0.5, p95) == []
        # exactly-at-bound is green (the bound is inclusive)
        assert B.lib_cog5_boundary_wall_clock_violations(bound, p95) == []
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_wall_clock_violations(True, p95)

    def test_mutant_unexplained_sweep_growth_reds(self):
        """§12.1.2(d) exact-integer accounting: files-swept moving by
        anything but the phase's own added files REDs, both directions;
        the exact-accounted move is clean; nonzero violations RED."""
        assert B.lib_cog5_boundary_files_swept_violations(959, 955, 4) == []
        grown = B.lib_cog5_boundary_files_swept_violations(960, 955, 4)
        assert grown and "unaccounted" in grown[0]
        shrunk = B.lib_cog5_boundary_files_swept_violations(958, 955, 4)
        assert shrunk and "unaccounted" in shrunk[0]
        assert B.lib_cog5_boundary_sweep_violation_findings(0, 0) == []
        assert B.lib_cog5_boundary_sweep_violation_findings(2, 0)
        assert B.lib_cog5_boundary_sweep_violation_findings(0, 1)

    def test_measured_tripwire_declared_posture_skip_when_unarmed(self):
        """The COG-4 §10.5 honesty idiom (a POSTURE skip, not a vacuity
        skip — it STAYS after the twin lands): the measured wall-clock
        tripwire asserts only under COG5_ENFORCE_BOUND=1; unarmed runs
        record the posture as a DECLARED skip. Armed runs re-verify the
        recorded S0 point against the formula (deterministic — the artifact
        numbers ARE the fixture; the twin's own fresh p95 measurement is
        the twin's job, not the corpus')."""
        if not _enforced():
            pytest.skip(
                "§12.1 wall-clock measure-only (COG5_ENFORCE_BOUND unset): "
                "tripwire not asserted — DECLARED posture skip per the COG-4 "
                "§10.5 idiom; verify-cognitive-phase5.sh arms it (W6/W7). This "
                "skip stays after the twin lands: armed runs execute the "
                "assertion below.")
        parsed = B.lib_cog5_boundary_parse_s0_baseline(
            _ARTIFACT.read_text(encoding="utf-8"))
        bound = B.lib_cog5_boundary_wall_clock_bound(parsed["p95_recorded"])
        assert parsed["p95_recorded"] <= bound
        assert parsed["final_bound_recorded"] <= bound + 1e-9
