"""COG-5 §12 SIM 7 — credential/network escape (+ the X5 exit arm) and
SIM 11 — cost explosion.

Contract: docs/plans/cognitive-core-phase-5-contract-2026-07-24.md §12:
  row 7 seeds   — candidate code probing env/credential files/network/
                  out-of-workdir writes
        asserts — scrubbed env observed; egress blocked; outside-workdir
                  diff empty (X5); euid/hooksPath laws hold
        mutants — harness passes live env through; hook execution not
                  disabled
  row 11 seeds  — a candidate/league round exceeding declared ceilings
        asserts — halt/defer with recorded reason; per-candidate cost in
                  the archive; ceilings are snapshot inputs, never
                  league-tunable
        mutant  — cost-ignoring league loop keeps spending
plus §1 X5 ("arena has no live credentials or writes") and the §8.4 arena
credential boundary: the candidate sees NO live credentials — the HARNESS
holds model access (the officer_runner blind-drive + oauth_llm
harness-holds-credentials precedent, cited in §3/§8.4).

WHAT RUNS LIVE NOW (fixture machinery, the §12 sanction — every instrument
proven to BITE on scratch fixtures):
  - the §4.4 ALLOWLIST env-scrub + the credential-marker leak detector: a
    scrubbed candidate env observes ZERO credential-shaped names; the
    ENV-PASSTHROUGH mutant (planted fake credentials passed through) is
    caught by the same probe+detector pair;
  - the both-ways hooksPath law (gate.py:372-410 replicated): a hostile
    pre-commit hook does NOT execute under argv+env pinning; the
    HOOK-EXECUTION-NOT-DISABLED mutant executes it and the evidence
    detector REDs;
  - the euid law: euid==0 REFUSES (pure predicate, provable unprivileged);
  - the X5 outside-workdir fence: an inside-only candidate leaves the
    outside tree byte-identical (diff EMPTY); the outside-write mutant
    yields a named non-empty diff;
  - the loopback egress-probe INSTRUMENT distinguishes open vs refused
    (127.0.0.1 only — the instrument the W3 harness-level egress block will
    be proven with);
  - the X5 STATIC leg: the W1 sandbox AST pin + the archive-row deliberate
    absences are present in-tree;
  - sim 11 complete on the reference loop fixture: lawful loop halts/defers
    with a RECORDED reason and stamps per-candidate cost into every archive
    row; the COST-IGNORING mutant keeps spending and the overrun oracle
    REDs; the CEILING-TAMPER mutant REDs the snapshot-digest tripwire; a
    missing-cost row REDs; every league-ish fixture row carries
    `fitness_claim: 'none'` (§6.3) and synthetic provenance (§6.2 — counts
    ZERO toward any league minimum).

VACUITY ARMS (the mergeability pattern — RETIREMENT CONDITIONS here, each
with a COMPANION absence assertion that REDs the moment the path lands):
  - REAL-HARNESS escape arm — retire when framework/evolution/sandbox.py
    lands (W3): run the sim-7 probes THROUGH the real harness (scrubbed env
    observed, egress blocked at the harness layer, workdir confinement,
    euid/hooksPath laws) instead of against the reference instruments.
  - ARENA-RUN arm — retire when framework/evolution/arena.py lands (W6):
    drive a candidate through the real arena and assert the X5 fence +
    harness-holds-credentials custody end to end.
  - REAL-LEAGUE cost arm — retire when framework/evolution/league.py lands
    (W6): a real league round exceeding declared ceilings halts/defers with
    the recorded reason and archives per-candidate cost.
  - LEAGUE CLI arm — retire when cabinet/scripts/cog5-league.py lands (W6):
    the CLI accepts ceilings as SNAPSHOT INPUTS only (no tunable-ceiling
    surface).

S0: python3.12, no DB, no network beyond the 127.0.0.1 loopback probe pair,
file-seeded, deterministic. Provenance: authored per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant
(COG-5 W2 corpus, unit T3).
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog5_boundary_fixtures as B  # noqa: E402

SANDBOX_REL = "framework/evolution/sandbox.py"
ARENA_REL = "framework/evolution/arena.py"
LEAGUE_REL = "framework/evolution/league.py"
LEAGUE_CLI_REL = "cabinet/scripts/cog5-league.py"


# ===========================================================================
# sim 7 — the env-scrub law + the ENV-PASSTHROUGH mutant
# ===========================================================================
class TestEnvScrub:
    def test_scrubbed_env_observed_by_candidate_probe(self):
        """sim-7 assert 1: under the §4.4 ALLOWLIST scrub, the candidate
        probe observes ONLY allowlisted names — zero credential-shaped
        findings (planted 'live' credentials do not survive the scrub)."""
        live = B.lib_cog5_boundary_planted_live_env(
            {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C"})
        scrubbed = B.lib_cog5_boundary_scrub_env(
            live, allowlist=("PATH", "LANG"),
            overrides={"ARENA_WORKDIR_MARKER": "fixture"})
        observed = B.lib_cog5_boundary_observe_env_via_subprocess(scrubbed)
        assert B.lib_cog5_boundary_env_leak_findings(observed) == []
        assert observed.get("ARENA_WORKDIR_MARKER") == "fixture"
        # the scrub is an allowlist, never a denylist: none of the planted
        # 'live' names survives it (the platform may inject benign locale
        # vars into children — the invariant is credential absence, and the
        # leak detector above already swept every observed name)
        planted_names = set(B.lib_cog5_boundary_planted_live_env({}))
        assert planted_names, "fixture must plant credential-shaped names"
        assert not (planted_names & set(observed)), observed

    def test_mutant_env_passthrough_reds(self):
        """NEGATIVE CONTROL (§12 row 7 mutant 1 — 'harness passes live env
        through'): the passthrough mutant hands the candidate the harness
        env unscrubbed; the SAME probe+detector pair catches every planted
        credential-shaped name (values are explicit fixture fakes)."""
        live = B.lib_cog5_boundary_planted_live_env(
            {"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
        observed = B.lib_cog5_boundary_observe_env_via_subprocess(live)
        findings = B.lib_cog5_boundary_env_leak_findings(observed)
        assert len(findings) >= 4, findings
        joined = "\n".join(findings)
        for part in ("API", "SECRET", "OAUTH", "PASSWORD"):
            assert part in joined.upper(), (part, findings)

    def test_detector_is_name_keyed_and_quiet_on_clean_envs(self):
        """Anti-over-fencing: a clean allowlisted env yields ZERO findings —
        the detector keys on credential-shaped NAMES, not values."""
        assert B.lib_cog5_boundary_env_leak_findings(
            {"PATH": "/usr/bin", "LANG": "C", "ARENA_ROUND": "3"}) == []


# ===========================================================================
# sim 7 — the hooksPath law + the HOOK-EXECUTION mutant, and the euid law
# ===========================================================================
class TestHookAndEuidLaws:
    def test_hooks_disabled_both_ways_hook_never_runs(self, tmp_path):
        """sim-7 assert 4 (hooksPath): with the both-ways pinning (argv
        `-c core.hooksPath=/dev/null` AND the env GIT_CONFIG pins — the
        gate-runner law replicated), a hostile pre-commit hook does NOT
        execute; the commit itself succeeds."""
        home = tmp_path / "home"
        home.mkdir()
        env = B.lib_cog5_boundary_git_env(home, pin_hooks=True)
        repo = B.lib_cog5_boundary_init_repo_with_hostile_hook(tmp_path, env)
        cp = B.lib_cog5_boundary_commit(repo, env, pin_argv=True)
        assert cp.returncode == 0
        assert B.lib_cog5_boundary_hook_execution_evidence(repo) is False

    def test_mutant_hook_execution_not_disabled_reds(self, tmp_path):
        """NEGATIVE CONTROL (§12 row 7 mutant 2 — 'hook execution not
        disabled'): the mutant drops BOTH pinning arms; the hostile hook
        RUNS and the evidence detector REDs (sentinel present)."""
        home = tmp_path / "home"
        home.mkdir()
        env = B.lib_cog5_boundary_git_env(home, pin_hooks=False)
        repo = B.lib_cog5_boundary_init_repo_with_hostile_hook(tmp_path, env)
        cp = B.lib_cog5_boundary_commit(repo, env, pin_argv=False)
        assert cp.returncode == 0
        assert B.lib_cog5_boundary_hook_execution_evidence(repo) is True, (
            "the mutant's hook did not run — this negative control must "
            "demonstrate the exact escape it names")

    def test_euid_law_refuses_root_and_admits_unprivileged(self):
        """sim-7 assert 4 (euid): euid==0 REFUSES fail-closed (the gate
        law, parameterized so it is provable without ever being root); the
        suite itself runs unprivileged."""
        assert os.geteuid() != 0, "the corpus suite must never run as root"
        refused = B.lib_cog5_boundary_refuse_privileged(0)
        assert refused["ok"] is False and "root" in refused["detail"]
        admitted = B.lib_cog5_boundary_refuse_privileged(os.geteuid())
        assert admitted["ok"] is True
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_refuse_privileged(True)  # bool is not an euid


# ===========================================================================
# sim 7 / X5 — outside-workdir diff EMPTY + the outside-write mutant
# ===========================================================================
class TestOutsideWorkdirFence:
    def _arena(self, tmp_path: Path) -> tuple[Path, Path]:
        outside = tmp_path / "outside"
        (outside / "live").mkdir(parents=True)
        (outside / "live" / "champion.cfg").write_text("pinned\n", encoding="utf-8")
        (outside / "live" / "ledger.jsonl").write_text("{}\n", encoding="utf-8")
        workdir = tmp_path / "arena-workdir"
        workdir.mkdir()
        return outside, workdir

    def test_inside_only_candidate_leaves_outside_diff_empty(self, tmp_path):
        """X5: a candidate that writes ONLY inside its arena workdir leaves
        the outside tree byte-identical — the post-run diff is EMPTY."""
        outside, workdir = self._arena(tmp_path)
        before = B.lib_cog5_boundary_tree_fingerprint(outside)
        (workdir / "scratch.txt").write_text("candidate output\n", encoding="utf-8")
        (workdir / "sub").mkdir()
        (workdir / "sub" / "more.txt").write_text("more\n", encoding="utf-8")
        after = B.lib_cog5_boundary_tree_fingerprint(outside)
        assert B.lib_cog5_boundary_outside_workdir_diff(before, after) == []

    def test_mutant_outside_write_reds(self, tmp_path):
        """NEGATIVE CONTROL (sim-7 seed: out-of-workdir writes): a candidate
        that writes/modifies OUTSIDE its workdir yields a named non-empty
        diff — add, modify, and delete each detected."""
        outside, _workdir = self._arena(tmp_path)
        before = B.lib_cog5_boundary_tree_fingerprint(outside)
        (outside / "live" / "champion.cfg").write_text("tampered\n", encoding="utf-8")
        (outside / "live" / "planted.txt").write_text("exfil\n", encoding="utf-8")
        (outside / "live" / "ledger.jsonl").unlink()
        diff = B.lib_cog5_boundary_outside_workdir_diff(
            before, B.lib_cog5_boundary_tree_fingerprint(outside))
        assert any(d.startswith("modified") and "champion.cfg" in d for d in diff), diff
        assert any(d.startswith("added") and "planted.txt" in d for d in diff), diff
        assert any(d.startswith("removed") and "ledger.jsonl" in d for d in diff), diff

    def test_x5_static_leg_is_in_tree(self):
        """X5's STATIC half (§8.4 layer 2): the W1 sandbox AST pin file is
        present and the archive-row candidate/generator/arena deliberate
        absences hold (no candidate write path — asserted here as the
        exit-arm cross-check; the full row battery lives in
        test_cog5_boundary_rows.py)."""
        assert (_HERE / "test_cog5_sandbox_ast_pin.py").exists(), (
            "X5 static leg missing: the sandbox forbidden-import pin")
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "cog2_import_gate_cog5_x5", _HERE.parents[0] / "cog2-import-gate.py")
        gate = _ilu.module_from_spec(spec)
        sys.modules["cog2_import_gate_cog5_x5"] = gate
        spec.loader.exec_module(gate)
        rows = [r for r in gate.load_config().data_plane_rows()
                if r.internal_prefix == "framework/evolution/archive/"]
        assert len(rows) == 1
        for name in ("candidate", "generator", "arena"):
            assert f"framework/evolution/{name}.py" in rows[0].deliberately_absent


# ===========================================================================
# sim 7 — the loopback egress-probe instrument (detector proof only; the
# harness-level BLOCK is the W3 vacuity arm below)
# ===========================================================================
class TestEgressProbeInstrument:
    def test_probe_detects_open_egress(self, tmp_path):
        """With a live loopback listener the candidate probe reports
        'connected' and the oracle REDs — an egress-open harness would be
        caught by exactly this instrument."""
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            result = B.lib_cog5_boundary_egress_probe_via_subprocess(port, env)
        finally:
            listener.close()
        assert result == "connected"
        findings = B.lib_cog5_boundary_egress_findings(result)
        assert findings and "egress open" in findings[0]

    def test_probe_reports_refused_when_no_endpoint(self):
        """Against a closed loopback port the probe reports 'refused' and
        the oracle is quiet — the blocked posture the real harness must
        produce for EVERY candidate connect attempt."""
        probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe_sock.bind(("127.0.0.1", 0))
            port = probe_sock.getsockname()[1]
        finally:
            probe_sock.close()  # closed: nothing listens here now
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        result = B.lib_cog5_boundary_egress_probe_via_subprocess(port, env)
        assert result == "refused"
        assert B.lib_cog5_boundary_egress_findings(result) == []

    def test_oracle_rejects_garbage_probe_output(self):
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_egress_findings("maybe")


# ===========================================================================
# sim 11 — cost explosion (reference loop + the three mutants)
# ===========================================================================
def _ceilings() -> dict[str, int]:
    return B.lib_cog5_boundary_ceiling_snapshot(
        max_rounds=3, max_total_cost_units=100, max_candidate_cost_units=40)


_ROUNDS = [
    {"cand-a": 20, "cand-b": 25},   # spend 45
    {"cand-c": 30, "cand-d": 20},   # spend 95
    {"cand-e": 35},                 # would project 130 > 100 -> HALT here
    {"cand-f": 35},
]


class TestCostCeilings:
    def test_lawful_loop_halts_with_recorded_reason(self):
        """sim-11 asserts: the lawful loop stops BEFORE breaching the total
        ceiling, the halt carries a RECORDED reason, every archived row
        carries its per-candidate cost, and the overrun oracle is quiet."""
        ceilings = _ceilings()
        run = B.lib_cog5_boundary_run_league_rounds(ceilings, _ROUNDS)
        assert run["rounds_run"] == 2 and run["spent_total"] == 95
        assert run["halt"] is not None and run["halt"]["action"] == "halt"
        assert "exceeds ceiling" in run["halt"]["reason"]
        assert B.lib_cog5_boundary_halt_findings(run["halt"]) == []
        assert len(run["archive_rows"]) == 4
        assert all(isinstance(r["cost_units"], int) for r in run["archive_rows"])
        assert B.lib_cog5_boundary_cost_overrun_findings(
            run["archive_rows"], ceilings) == []
        # ceilings stayed the declared snapshot
        assert B.lib_cog5_boundary_ceiling_drift_findings(
            run["declared_ceiling_digest"], run["ceilings_after"]) == []

    def test_per_candidate_breach_defers_with_reason(self):
        ceilings = _ceilings()
        run = B.lib_cog5_boundary_run_league_rounds(
            ceilings, [{"cand-huge": 55}])
        assert run["halt"] is not None and run["halt"]["action"] == "defer"
        assert "per-candidate ceiling" in run["halt"]["reason"]
        assert run["archive_rows"] == []  # nothing spent past the guard

    def test_round_budget_exhaustion_halts(self):
        ceilings = B.lib_cog5_boundary_ceiling_snapshot(
            max_rounds=1, max_total_cost_units=1000,
            max_candidate_cost_units=1000)
        run = B.lib_cog5_boundary_run_league_rounds(
            ceilings, [{"a": 1}, {"b": 1}])
        assert run["rounds_run"] == 1
        assert run["halt"] is not None
        assert "round budget exhausted" in run["halt"]["reason"]

    def test_mutant_cost_ignoring_loop_reds(self):
        """NEGATIVE CONTROL (§12 row 11 mutant — 'cost-ignoring league loop
        keeps spending'): the guard-ignoring mutant spends through every
        round (165 > 100) with NO halt; the overrun oracle REDs it on the
        exact escape (total-ceiling breach), and the archive rows prove the
        overspend is visible (per-candidate cost still recorded)."""
        ceilings = _ceilings()
        run = B.lib_cog5_boundary_run_league_rounds(
            ceilings, _ROUNDS, obey_guard=False)
        assert run["halt"] is None and run["spent_total"] == 165
        findings = B.lib_cog5_boundary_cost_overrun_findings(
            run["archive_rows"], ceilings)
        assert any("kept spending" in f for f in findings), findings

    def test_mutant_league_tunable_ceilings_reds(self):
        """NEGATIVE CONTROL (sim-11 assert 3 — 'ceilings are snapshot
        inputs, never league-tunable'): the self-service mid-run ceiling
        raise diverges from the declared snapshot digest and the drift
        tripwire REDs."""
        ceilings = _ceilings()
        run = B.lib_cog5_boundary_run_league_rounds(
            ceilings, _ROUNDS, tamper_ceilings=True)
        findings = B.lib_cog5_boundary_ceiling_drift_findings(
            run["declared_ceiling_digest"], run["ceilings_after"])
        assert findings and "league-tunable" in findings[0]

    def test_mutant_missing_per_candidate_cost_reds(self):
        """NEGATIVE CONTROL (sim-11 assert 2): an archive row WITHOUT its
        per-candidate cost is a named finding — cost lives in the archive,
        per candidate, always."""
        ceilings = _ceilings()
        rows = [{"candidate_id": "cand-a", "cost_units": 10,
                 "provenance": "sim_replay", "source_class": "arena",
                 "fitness_claim": "none"},
                {"candidate_id": "cand-b",
                 "provenance": "sim_replay", "source_class": "arena",
                 "fitness_claim": "none"}]
        findings = B.lib_cog5_boundary_cost_overrun_findings(rows, ceilings)
        assert any("missing per-candidate cost_units" in f for f in findings)

    def test_halt_without_recorded_reason_is_a_violation(self):
        assert B.lib_cog5_boundary_halt_findings({"action": "halt", "reason": ""})
        assert B.lib_cog5_boundary_halt_findings({"action": "defer"})
        assert B.lib_cog5_boundary_halt_findings(None) == []

    def test_league_fixture_rows_are_structurally_non_fitness(self):
        """§6.3/§17: every league-ish fixture row carries `fitness_claim:
        'none'` and synthetic provenance — ZERO of them count toward any
        league-opening minimum (§6.2; the synthetic-never-opens law at this
        family's league touchpoint)."""
        run = B.lib_cog5_boundary_run_league_rounds(_ceilings(), _ROUNDS)
        assert run["archive_rows"], "fixture must produce rows"
        assert all(r["fitness_claim"] == "none" for r in run["archive_rows"])
        assert B.lib_cog5_boundary_provenance_violations(run["archive_rows"]) == []
        assert B.lib_cog5_boundary_count_toward_minimums(run["archive_rows"]) == 0


# ===========================================================================
# vacuity arms — the real harness/arena/league surfaces (W3/W6)
# ===========================================================================
class TestVacuityArms:
    def test_sandbox_absent_companion(self):
        """COMPANION absence assertion: REDs the moment sandbox.py lands
        (W3), forcing the docstring RETIREMENT CONDITION (run the sim-7
        probes THROUGH the real harness)."""
        assert not (_REPO / SANDBOX_REL).exists(), (
            "sandbox.py LANDED — retire this vacuity arm: point the sim-7 "
            "escape battery at the real harness (scrubbed env observed, egress "
            "blocked, workdir confinement, euid/hooksPath laws) per the "
            "docstring RETIREMENT CONDITION.")

    def test_real_harness_escape_arm_vacuity(self):
        """VACUITY SKIP — retire when framework/evolution/sandbox.py lands
        (W3): the live arm drives the env/egress/workdir probes through the
        real harness and asserts every probe REFUSES."""
        if not (_REPO / SANDBOX_REL).exists():
            pytest.skip(
                "vacuity: framework/evolution/sandbox.py not yet landed (W3) — "
                "retire when it lands; the absence companion above REDs then.")
        pytest.fail("unreachable while the absence companion holds")

    def test_arena_absent_companion(self):
        """COMPANION absence assertion for the arena driver (W6)."""
        assert not (_REPO / ARENA_REL).exists(), (
            "arena.py LANDED — retire this vacuity arm: drive a candidate "
            "through the real arena and assert the X5 fence + "
            "harness-holds-credentials custody end to end (docstring "
            "RETIREMENT CONDITION).")

    def test_arena_run_arm_vacuity(self):
        """VACUITY SKIP — retire when framework/evolution/arena.py lands
        (W6): the live arena run must show the candidate NEVER sees a
        credential (the harness holds model access and passes results in —
        the oauth_llm/officer_runner custody pattern, §8.4)."""
        if not (_REPO / ARENA_REL).exists():
            pytest.skip(
                "vacuity: framework/evolution/arena.py not yet landed (W6) — "
                "retire when it lands; the absence companion above REDs then.")
        pytest.fail("unreachable while the absence companion holds")

    def test_league_absent_companion(self):
        """COMPANION absence assertion for the league loop (W6)."""
        assert not (_REPO / LEAGUE_REL).exists(), (
            "league.py LANDED — retire this vacuity arm: a REAL league round "
            "exceeding declared ceilings must halt/defer with the recorded "
            "reason and archive per-candidate cost (docstring RETIREMENT "
            "CONDITION).")

    def test_real_league_cost_arm_vacuity(self):
        """VACUITY SKIP — retire when framework/evolution/league.py lands
        (W6): sim 11 against the real loop — ceilings as snapshot inputs,
        halt/defer recorded, per-candidate cost archived."""
        if not (_REPO / LEAGUE_REL).exists():
            pytest.skip(
                "vacuity: framework/evolution/league.py not yet landed (W6) — "
                "retire when it lands; the absence companion above REDs then.")
        pytest.fail("unreachable while the absence companion holds")

    def test_league_cli_absent_companion(self):
        """COMPANION absence assertion for the league CLI (W6)."""
        assert not (_REPO / LEAGUE_CLI_REL).exists(), (
            "cog5-league.py LANDED — retire this vacuity arm: the CLI accepts "
            "ceilings as SNAPSHOT INPUTS only — no flag, config, or env may "
            "raise a ceiling mid-run (docstring RETIREMENT CONDITION).")

    def test_league_cli_snapshot_ceilings_arm_vacuity(self):
        """VACUITY SKIP — retire when cabinet/scripts/cog5-league.py lands
        (W6): drive the CLI with a declared ceilings snapshot and assert no
        league-side surface can rewrite it."""
        if not (_REPO / LEAGUE_CLI_REL).exists():
            pytest.skip(
                "vacuity: cog5-league.py not yet landed (W6) — retire when it "
                "lands; the absence companion above REDs then.")
        pytest.fail("unreachable while the absence companion holds")
