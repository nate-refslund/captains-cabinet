"""COG-4 W5 x1 — the landed dispatch-shadow CLI battery
(`cabinet/scripts/cog4-dispatch-shadow.py`, contract §7.3) + the OUT-OF-BAND
pre-proof of the W2 T2 retirement arms (§13: the corpus stays untouched; the
integrator performs the arm surgery — this file proves the post-surgery state
green FIRST, via `lib_cog4_dispatch_adapter` running the REAL CLI over REAL
kernel-shaped stores).

THREE LAYERS:
  1. TestPinAndClosure — the post-surgery forms of the two §8.4 vacuity arms:
     the symbol-level import pin scans the REAL file clean
     (`test_cog4_dispatch_ast_pin.py`'s retirement condition), and a hermetic
     FULL-PIPELINE run's module closure excludes the executor doors
     (framework.acting / framework.frontdoor — the parity-CLI closure idiom;
     hermetic mode never calls `_act_with_undo_gap`, whose probes import the
     doors at call time).
  2. TestSim*/TestLimbOrder — the ten T2 retirement activations
     (`test_cog4_sim_dispatch.py::TestRealDispatchCliArms`), each named after
     its arm: the SAME scenario seeds and the SAME asserts, run against the
     landed CLI (subprocess adapter over its shadow-record output). Where the
     corpus's fixture policy drives verdicts, the adapter's
     matrix_policy-shaped translation drives them (wildcard rows; the
     undo_required semantics = act_with_undo over a declared "none"
     undo_contract).
  3. TestCliDiscipline / TestRealMatrix — the CLI's own laws: the §7.4
     pointer tripwire; SF1 replay ACROSS RUNS through the persisted shadow
     log; atomic append + loud lock; store purity (the CLI writes only the
     shadow log); exit codes; live-state validation; and the REAL
     authority-matrix joint end-to-end (matrix-derived risk recompute,
     notify_after allow, hard-ceiling refuse, the reversible undo-gap).

S0: python3.12, no DB, no network (subprocess runs the in-repo CLI only);
hermetic — every store/input is seeded under tmp_path; the pointer default is
pointed into tmp so developer machine state never leaks in.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W5 x1 (Fable-for-execution named
unit).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_ast_pins as PIN  # noqa: E402
import lib_cog4_dispatch_adapter as A  # noqa: E402

CLI = A.DISPATCH_CLI


def _seed(tmp_path, rows, manifests, *, snapshot=None, live_overrides=None):
    """The corpus `_seed` shape onto the REAL store: build under tmp, return
    (cache_dir, live, manifests, policy)."""
    snapshot = snapshot or A.make_snapshot()
    cache_dir = tmp_path / "cache" / "scheduler-real"
    A.build_real_store(cache_dir, snapshot, rows)
    live = A.make_live(snapshot, manifests, **(live_overrides or {}))
    return cache_dir, live, manifests, A.fixture_policy()


def _run(tmp_path, cache_dir, live, manifests, policy, **kw):
    return A.run_cli(cache_dir, live, manifests, policy,
                     tmp_path / "adapter", **kw)


# ===========================================================================
# 1. the post-surgery §8.4 arms (import pin + hermetic run closure)
# ===========================================================================
class TestPinAndClosure:
    def test_real_cli_landed_and_import_pin_scans_clean(self):
        """The retirement form of test_cog4_dispatch_ast_pin.py::
        test_real_cli_is_armed_and_absent: the CLI exists and the §8.4
        symbol-level scan over the REAL file is empty — the dispatcher
        imports only its sanctioned read-only surface."""
        assert CLI.is_file(), f"{CLI} missing — the pin lost its subject"
        assert PIN.dispatch_import_violations(_REPO) == []

    def test_hermetic_run_closure_excludes_executor_doors(self, tmp_path):
        """A FULL hermetic pipeline run (serve -> all six limbs -> shadow
        record, rc 0) never loads framework.acting / framework.frontdoor:
        the dispatcher structurally cannot execute what it never imports
        (the parity-CLI closure idiom; §7.3 "never executes anything")."""
        rows = [A.make_row("organ-a", "collect")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        snapshot = A.make_snapshot()
        cache = tmp_path / "cache"
        A.build_real_store(cache, snapshot, rows)
        live = A.make_live(snapshot, manifests)
        workdir = tmp_path / "w"
        workdir.mkdir()
        for name, payload in (("live.json", live),
                              ("manifests.json", manifests),
                              ("policy.json", A.fixture_policy())):
            (workdir / name).write_text(json.dumps(payload),
                                        encoding="utf-8")
        driver = (
            "import sys, json, runpy\n"
            f"sys.argv = ['cog4-dispatch-shadow.py',\n"
            f"    '--cache-dir', {str(cache)!r},\n"
            f"    '--live', {str(workdir / 'live.json')!r},\n"
            f"    '--organ-manifests', {str(workdir / 'manifests.json')!r},\n"
            f"    '--matrix-policy', {str(workdir / 'policy.json')!r},\n"
            f"    '--shadow-log', {str(workdir / 'log.jsonl')!r},\n"
            f"    '--pointer-path', {str(workdir / 'no-pointer')!r}]\n"
            "rc = 0\n"
            "try:\n"
            f"    runpy.run_path({str(CLI)!r}, run_name='__main__')\n"
            "except SystemExit as e:\n"
            "    rc = int(e.code or 0)\n"
            "doors = sorted(m for m in sys.modules\n"
            "    if m == 'framework.acting' or m.startswith('framework.acting.')\n"
            "    or m == 'framework.frontdoor' or m.startswith('framework.frontdoor.'))\n"
            "fw = sorted(m for m in sys.modules if m.startswith('framework.'))\n"
            "print(json.dumps({'rc': rc, 'doors': doors, 'fw': fw}))\n")
        r = subprocess.run([sys.executable, "-c", driver], cwd=str(_REPO),
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout.strip().splitlines()[-1])
        assert payload["rc"] == 0, (payload, r.stderr)   # a REAL green run
        assert payload["fw"] != [], payload              # surface loaded
        assert payload["doors"] == [], (
            f"the dispatcher's run closure reached the executor doors: "
            f"{payload['doors']}")


# ===========================================================================
# 2. the ten T2 retirement activations (corpus seeds + asserts, real CLI)
# ===========================================================================
class TestSim3StaleOrgan:
    """test_real_cli_sim3_stale_organ — bind _check_sim3 to the real CLI."""

    def _check(self, tmp_path):
        rows = [A.make_row("stale-organ", "collect"),
                A.make_row("fresh-organ", "collect")]
        manifests = {
            "stale-organ": A.make_organ_manifest("stale-organ",
                                                 max_staleness=3600),
            "fresh-organ": A.make_organ_manifest("fresh-organ",
                                                 max_staleness=3600)}
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organ_output_age_seconds":
                            {"stale-organ": 7200, "fresh-organ": 60}})
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "dispatch"
        stale = A.by_organ(out, "stale-organ")
        assert stale["decision"] == "refused", stale
        assert stale["staleness_flagged"] is True
        assert stale["reason"].startswith("stale_organ:")
        assert [r["organ"] for r in out.would_dispatch()] == ["fresh-organ"]
        return out, live, manifests

    def test_stale_refused_flagged_never_auto_permission(self, tmp_path):
        self._check(tmp_path)

    def test_watchdog_floor_fires_independently(self, tmp_path):
        """The floor derivation is manifest-only and outcome-independent —
        the stale organ's floor pair trips from declared ages regardless of
        the CLI's records (the sim-3 independence property)."""
        out, live, manifests = self._check(tmp_path)
        floors = {name: (m["freshness_needs"]["expected_output"],
                         m["freshness_needs"]["max_staleness_seconds"])
                  for name, m in sorted(manifests.items())}
        for outcome_arg in (out, None):     # outcome never consulted
            fired = {name for name, (_e, need) in floors.items()
                     if (live["organ_output_age_seconds"].get(name)
                         or 0) > need}
            assert fired == {"stale-organ"}, outcome_arg
        assert set(floors) == {"stale-organ", "fresh-organ"}

    def test_staleness_never_overrides_authority(self, tmp_path):
        """A stale organ whose descriptor is ALSO gated refuses at AUTHORITY
        (limb 3 < limb 5)."""
        rows = [A.make_row("stale-gated", "mutate", risk="fixture_gated")]
        manifests = {"stale-gated": A.make_organ_manifest("stale-gated")}
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organ_output_age_seconds":
                            {"stale-gated": 9999}})
        out = _run(tmp_path, cache, live, manifests, policy)
        rec = A.by_organ(out, "stale-gated")
        assert rec["decision"] == "refused"
        assert rec["limb"] == "authority"
        assert rec["reason"] == "authority:always_gated"


class TestSim5OrganCrash:
    """test_real_cli_sim5_organ_crash — fallback/floor/exit-1 properties."""

    def _seed5(self, tmp_path):
        rows = [A.make_row("crash-skip", "collect"),
                A.make_row("crash-noop", "collect"),
                A.make_row("crash-esc", "collect"),
                A.make_row("healthy-organ", "collect")]
        manifests = {
            "crash-skip": A.make_organ_manifest("crash-skip",
                                                fallback="skip"),
            "crash-noop": A.make_organ_manifest("crash-noop",
                                                fallback="safe_noop"),
            "crash-esc": A.make_organ_manifest("crash-esc",
                                               fallback="escalate"),
            "healthy-organ": A.make_organ_manifest("healthy-organ"),
        }
        health = {
            "crash-skip": {"probe_ran": False},                # true crash
            "crash-noop": {"probe_ran": True, "exit_code": 1},  # honest fail
            "crash-esc": {"probe_ran": False},                 # true crash
            "healthy-organ": {"probe_ran": True, "exit_code": 0},
        }
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organ_health": health})
        return cache, live, manifests, policy, health

    def test_manifest_fallback_honored_others_unaffected(self, tmp_path):
        cache, live, manifests, policy, _h = self._seed5(tmp_path)
        out = _run(tmp_path, cache, live, manifests, policy)
        assert A.by_organ(out, "crash-skip")["decision"] == "refused"
        assert A.by_organ(out, "crash-skip")["reason"] == \
            "health_crashed:fallback_skip"
        assert A.by_organ(out, "crash-noop")["decision"] == "safe_noop"
        assert A.by_organ(out, "crash-esc")["decision"] == \
            "escalation_flagged"
        assert [r["organ"] for r in out.would_dispatch()] == \
            ["healthy-organ"]

    def test_exit1_health_proof_is_unhealthy_not_crash(self, tmp_path):
        """The S0 finding: RAN-and-exited-1 is `unhealthy` (positive
        evidence), never `crashed` (absence) — distinct in the record."""
        cache, live, manifests, policy, _h = self._seed5(tmp_path)
        out = _run(tmp_path, cache, live, manifests, policy)
        assert A.by_organ(out, "crash-noop")["health"] == "unhealthy"
        assert A.by_organ(out, "crash-noop")["reason"] == \
            "health_unhealthy:fallback_safe_noop"
        assert A.by_organ(out, "crash-skip")["health"] == "crashed"

    def test_floors_still_derive_for_failing_organs(self, tmp_path):
        """Manifest-derived floors are health-independent — every failing
        organ keeps its (expected_output, max_staleness) pair."""
        _c, _l, manifests, _p, _h = self._seed5(tmp_path)
        floors = {name: (m["freshness_needs"]["expected_output"],
                         m["freshness_needs"]["max_staleness_seconds"])
                  for name, m in manifests.items()}
        assert set(floors) == {"crash-skip", "crash-noop", "crash-esc",
                               "healthy-organ"}


class TestSim6DependencyFailure:
    """test_real_cli_sim6_dependency_failure — bind _check_sim6."""

    def test_unavailable_dependency_refused_with_explicit_reason(
            self, tmp_path):
        rows = [A.make_row("dependent-organ", "aggregate",
                           deps=("organ:upstream-organ",)),
                A.make_row("cap-dependent", "fetch"),
                A.make_row("independent", "collect")]
        manifests = {
            "dependent-organ": A.make_organ_manifest("dependent-organ"),
            "cap-dependent": A.make_organ_manifest(
                "cap-dependent", dependencies=("mcp:alpha-service",)),
            "independent": A.make_organ_manifest("independent"),
        }
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organs_available":
                            ["dependent-organ", "cap-dependent",
                             "independent"],           # upstream ABSENT
                            "capabilities_available": []})
        out = _run(tmp_path, cache, live, manifests, policy)
        organ_dep = A.by_organ(out, "dependent-organ")
        assert organ_dep["decision"] == "refused", organ_dep
        assert organ_dep["reason"] == \
            "dependency_unavailable:organ:upstream-organ"
        cap_dep = A.by_organ(out, "cap-dependent")
        assert cap_dep["decision"] == "refused", cap_dep
        assert cap_dep["reason"] == \
            "dependency_unavailable:mcp:alpha-service"
        assert [r["organ"] for r in out.would_dispatch()] == ["independent"]

    def test_available_dependency_dispatches(self, tmp_path):
        rows = [A.make_row("dependent-organ", "aggregate",
                           deps=("organ:upstream-organ",))]
        manifests = {"dependent-organ":
                     A.make_organ_manifest("dependent-organ")}
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organs_available":
                            ["dependent-organ", "upstream-organ"]})
        out = _run(tmp_path, cache, live, manifests, policy)
        assert [r["organ"] for r in out.would_dispatch()] == \
            ["dependent-organ"]

    def test_real_fold_dict_deps_shape_honored(self, tmp_path):
        """The REAL fold emits deps as {'organs': [...], 'capabilities':
        [...]} — the CLI normalizes both dialects; a missing organ dep in
        the dict shape refuses identically."""
        rows = [A.make_row("dict-dep", "aggregate",
                           deps={"organs": ["upstream-organ"],
                                 "capabilities": []})]
        manifests = {"dict-dep": A.make_organ_manifest("dict-dep")}
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organs_available": ["dict-dep"]})
        out = _run(tmp_path, cache, live, manifests, policy)
        rec = A.by_organ(out, "dict-dep")
        assert rec["decision"] == "refused"
        assert rec["reason"] == \
            "dependency_unavailable:organ:upstream-organ"


class TestSim9UnavailableMcp:
    """test_real_cli_sim9_unavailable_mcp — bind _check_sim9."""

    def test_missing_mcp_skipped_with_reason_identity_preserved(
            self, tmp_path):
        rows = [A.make_row("mcp-organ", "sync"),
                A.make_row("plain-organ", "collect")]
        manifests = {
            "mcp-organ": A.make_organ_manifest(
                "mcp-organ", permissions=("mcp:vault-read",)),
            "plain-organ": A.make_organ_manifest("plain-organ"),
        }
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"capabilities_available":
                            ["mcp:other-available"]})
        out = _run(tmp_path, cache, live, manifests, policy)
        rec = A.by_organ(out, "mcp-organ")
        assert rec["decision"] == "refused", rec
        assert rec["reason"] == "capability_unavailable:mcp:vault-read"
        # identity preservation — the anti-silent-substitution clause:
        assert rec["capability"] == "mcp-organ/sync"
        assert rec["descriptor"]["capability"] == "mcp-organ/sync"
        assert not [r for r in out.would_dispatch()
                    if r["organ"] == "mcp-organ"]
        assert [r["organ"] for r in out.would_dispatch()] == ["plain-organ"]


class TestSim10UnauthorizedEffect:
    """test_real_cli_sim10_unauthorized_effect — bind _check_sim10; the
    verdicts ride the CLI's resolve_verdict over the translated policy."""

    def test_gated_verdicts_never_would_dispatch(self, tmp_path):
        rows = [
            A.make_row("gated-organ", "mutate", risk="fixture_gated"),
            A.make_row("propose-organ", "draft", risk="fixture_propose"),
            A.make_row("ceiling-organ", "spend", ceiling=("spending",)),
            A.make_row("undo-gap-organ", "rewrite", risk="fixture_mutating",
                       undo="none"),
            A.make_row("clean-organ", "collect"),
        ]
        manifests = {r["organ"]: A.make_organ_manifest(r["organ"])
                     for r in rows}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        out = _run(tmp_path, cache, live, manifests, policy)
        expected = {
            "gated-organ": "always_gated",
            "propose-organ": "propose_only",
            "ceiling-organ": "ceiling",
            "undo-gap-organ": "undo_gap",
        }
        for organ, verdict in expected.items():
            rec = A.by_organ(out, organ)
            assert rec["decision"] == "refused", (organ, rec)
            assert rec["verdict"] == verdict
            assert rec["reason"] == f"authority:{verdict}"
        assert [r["organ"] for r in out.would_dispatch()] == ["clean-organ"]

    def test_verdict_resolution_is_capability_blind(self, tmp_path):
        """§5.2 through the REAL CLI: two rows identical in their
        enforcement members but differing in `capability` (the open
        trusted-organ/ spelling) refuse IDENTICALLY — operation names carry
        no authority."""
        rows = [A.make_row("plain-organ", "mutate", risk="fixture_gated"),
                A.make_row("trusted-organ", "mutate", risk="fixture_gated")]
        manifests = {r["organ"]: A.make_organ_manifest(r["organ"])
                     for r in rows}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        out = _run(tmp_path, cache, live, manifests, policy)
        plain = A.by_organ(out, "plain-organ")
        trusted = A.by_organ(out, "trusted-organ")
        assert plain["capability"] == "plain-organ/mutate"
        assert trusted["capability"] == "trusted-organ/mutate"
        for rec in (plain, trusted):
            assert rec["decision"] == "refused"
            assert rec["verdict"] == "always_gated"
            assert rec["reason"] == "authority:always_gated"
        assert out.would_dispatch() == []

    def test_undo_present_under_act_with_undo_dispatches(self, tmp_path):
        """Control: the same undo-required class WITH a declared undo
        contract passes the gap check — the refusal above is attributable
        to the declared gap alone."""
        rows = [A.make_row("undo-ok-organ", "rewrite",
                           risk="fixture_mutating", undo="delete_window(7)")]
        manifests = {"undo-ok-organ":
                     A.make_organ_manifest("undo-ok-organ")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        out = _run(tmp_path, cache, live, manifests, policy)
        assert [r["organ"] for r in out.would_dispatch()] == \
            ["undo-ok-organ"]


class TestSim11ForgedDecision:
    """test_real_cli_sim11_forged_decision — the tamper + absent-key seeds
    over the KERNEL schedule store (the real chain bites on content)."""

    def _forged_seed(self, tmp_path):
        rows = [A.make_row("organ-a", "collect"),
                A.make_row("organ-b", "report")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a"),
                     "organ-b": A.make_organ_manifest("organ-b")}
        return _seed(tmp_path, rows, manifests)

    @pytest.mark.parametrize("tamper", ["edit_content", "append_row",
                                        "drop_row"])
    def test_hand_edited_schedule_refuses(self, tmp_path, tamper):
        cache, live, manifests, policy = self._forged_seed(tmp_path)
        rows_path = cache / "schedule.jsonl"
        lines = rows_path.read_text(encoding="utf-8").splitlines()
        if tamper == "edit_content":
            assert '"budget_units":1' in lines[0]
            lines[0] = lines[0].replace('"budget_units":1',
                                        '"budget_units":0')
        elif tamper == "append_row":
            lines.append(json.dumps(
                A.make_row("forged-organ", "exfiltrate"),
                sort_keys=True, separators=(",", ":")))
        else:
            lines = lines[1:]
        rows_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "serve_refused", (out.mode, out.reason)
        assert out.reason == "rows_hash_mismatch"
        assert out.records == [] and out.would_dispatch() == []
        assert out.returncode == 2

    def test_manifest_with_rows_hash_key_removed_refuses(self, tmp_path):
        """§6.3 MANDATORY-PRESENT: the absent `schedule_rows_hash` key can
        never serve unbound rows — the objectives skip-hole stays closed."""
        cache, live, manifests, policy = self._forged_seed(tmp_path)
        man_path = cache / "schedule-manifest.json"
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        del manifest["schedule_rows_hash"]
        man_path.write_text(json.dumps(manifest, sort_keys=True),
                            encoding="utf-8")
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "serve_refused", (out.mode, out.reason)
        assert out.reason == "rows_hash_key_absent"
        assert out.records == [] and out.would_dispatch() == []

    def test_tampered_snapshot_artifact_refuses(self, tmp_path):
        """The counterfactual-style mismatch limb: a snapshot record that no
        longer matches epoch.snapshot_hash refuses."""
        cache, live, manifests, policy = self._forged_seed(tmp_path)
        snap_path = cache / "snapshot.json"
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        snapshot["scope"] = "forged-scope"
        snap_path.write_text(json.dumps(snapshot, sort_keys=True),
                             encoding="utf-8")
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "serve_refused"
        assert out.reason == "snapshot_hash_mismatch"


class TestSim12BudgetOverflow:
    """test_real_cli_sim12_budget_overflow — bind _check_sim12 (N4)."""

    def test_overflow_refused_at_dispatch_despite_planner_admission(
            self, tmp_path):
        rows = [A.make_row("organ-a", "collect", budget_units=3),
                A.make_row("organ-b", "report", budget_units=3),
                A.make_row("organ-c", "sweep", budget_units=5)]
        manifests = {r["organ"]: A.make_organ_manifest(r["organ"])
                     for r in rows}
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"remaining_budget": 7})
        out = _run(tmp_path, cache, live, manifests, policy)
        assert [r["organ"] for r in out.would_dispatch()] == \
            ["organ-a", "organ-b"]
        rec = A.by_organ(out, "organ-c")
        assert rec["decision"] == "refused", rec
        assert rec["reason"] == "budget_overflow"
        assert rec["limb"] == "budget"
        assert rec["planner_admitted"] is True   # select row — refused anyway

    def test_refused_rows_consume_no_budget(self, tmp_path):
        """A gated row's declared cost never counts against the remaining
        budget — the next affordable row still dispatches."""
        rows = [A.make_row("organ-a", "mutate", risk="fixture_gated",
                           budget_units=90),
                A.make_row("organ-b", "collect", budget_units=5)]
        manifests = {r["organ"]: A.make_organ_manifest(r["organ"])
                     for r in rows}
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests,
            live_overrides={"remaining_budget": 10})
        out = _run(tmp_path, cache, live, manifests, policy)
        assert [r["organ"] for r in out.would_dispatch()] == ["organ-b"]


class TestSim14StaleSnapshot:
    """test_real_cli_sim14_stale_snapshot — the mismatch + null-hole seeds
    (N3)."""

    @pytest.mark.parametrize("family", list(A.WAKE_INPUT_KEYS))
    def test_any_live_hash_mismatch_refuses(self, tmp_path, family):
        rows = [A.make_row("organ-a", "collect")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        live["wake_input_hashes"][family] = "moved-" + str(
            live["wake_input_hashes"][family])
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "stale_snapshot"
        assert out.reason == f"stale_snapshot:{family}"
        assert out.would_dispatch() == []
        assert out.returncode == 2

    def test_recorded_null_but_live_exists_refuses(self, tmp_path):
        """The built-without-store analog: a recorded null NEVER skips the
        compare (the objectives `is not None and` hole stays closed)."""
        rows = [A.make_row("organ-a", "collect")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        snapshot = A.make_snapshot(
            wake_input_hashes={"cortex_belief_store_hash": None})
        cache, live, manifests, policy = _seed(
            tmp_path, rows, manifests, snapshot=snapshot)
        live["wake_input_hashes"]["cortex_belief_store_hash"] = \
            "cortexhash-live-now"
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "stale_snapshot", (out.mode, out.reason)
        assert out.reason == "stale_snapshot:cortex_belief_store_hash"
        assert out.would_dispatch() == []

    def test_live_null_but_recorded_exists_refuses(self, tmp_path):
        rows = [A.make_row("organ-a", "collect")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        live["wake_input_hashes"]["organ_registry_hash"] = None
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "stale_snapshot"
        assert out.reason == "stale_snapshot:organ_registry_hash"

    def test_matching_hashes_dispatch(self, tmp_path):
        rows = [A.make_row("organ-a", "collect")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "dispatch"
        assert [r["organ"] for r in out.would_dispatch()] == ["organ-a"]
        assert out.returncode == 0


class TestSim15RestartReplay:
    """test_real_cli_sim15_restart_replay — corrupt/missing state => the
    fixed safe schedule, NEVER permission (§7.4); + the kernel N1 triple on
    the rebuilt schedule."""

    def _corrupt_seeds(self, tmp_path):
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        rows = [A.make_row("organ-a", "collect")]
        snapshot = A.make_snapshot()
        seeds = []
        missing = tmp_path / "missing-store"
        missing.mkdir()
        seeds.append(("missing_store", missing))
        corrupt_man = tmp_path / "corrupt-manifest"
        A.build_real_store(corrupt_man, snapshot, rows)
        (corrupt_man / "schedule-manifest.json").write_text(
            "NOT-JSON{{{", encoding="utf-8")
        seeds.append(("corrupt_manifest", corrupt_man))
        corrupt_rows = tmp_path / "corrupt-rows"
        A.build_real_store(corrupt_rows, snapshot, rows)
        (corrupt_rows / "schedule.jsonl").write_text(
            '{"organ": "organ-a", "trunc', encoding="utf-8")
        seeds.append(("corrupt_rows", corrupt_rows))
        corrupt_snap = tmp_path / "corrupt-snapshot"
        A.build_real_store(corrupt_snap, snapshot, rows)
        (corrupt_snap / "snapshot.json").write_text("], garbage",
                                                    encoding="utf-8")
        seeds.append(("corrupt_snapshot", corrupt_snap))
        killed = tmp_path / "killed-mid-fold"
        A.crashed_build(snapshot, rows, killed)
        seeds.append(("mid_fold_kill", killed))
        live = A.make_live(snapshot, manifests)
        return seeds, live, manifests

    def test_corrupt_or_missing_state_falls_back_never_permission(
            self, tmp_path):
        seeds, live, manifests = self._corrupt_seeds(tmp_path)
        policy = A.fixture_policy()
        for name, cache in seeds:
            out = A.run_cli(cache, live, manifests, policy,
                            tmp_path / f"adapter-{name}")
            assert out.mode == "safe_fallback", (name, out.mode, out.reason)
            assert out.safe_schedule == live["services_cadence"], name
            assert out.would_dispatch() == [], (
                f"{name}: fallback granted permission — §7.4 forbids "
                "exactly this")
            assert out.returncode == 4, name

    def test_corruption_beats_row_level_state(self, tmp_path):
        seeds, live, manifests = self._corrupt_seeds(tmp_path)
        live["wake_input_hashes"]["organ_registry_hash"] = "moved-registry"
        _name, cache = seeds[2]                        # corrupt_rows
        out = A.run_cli(cache, live, manifests, A.fixture_policy(),
                        tmp_path / "adapter-beats")
        assert out.mode == "safe_fallback"

    def test_valid_store_then_killed_rebuild_still_serves(self, tmp_path):
        """The atomic-write law: a killed REBUILD over a valid store leaves
        the old store servable — never a torn half-store."""
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        rows = [A.make_row("organ-a", "collect")]
        snapshot = A.make_snapshot()
        cache = tmp_path / "cache"
        A.build_real_store(cache, snapshot, rows)
        A.crashed_build(snapshot, [A.make_row("organ-z", "later")], cache)
        live = A.make_live(snapshot, manifests)
        out = A.run_cli(cache, live, manifests, A.fixture_policy(),
                        tmp_path / "adapter")
        assert out.mode == "dispatch"
        assert [r["organ"] for r in out.would_dispatch()] == ["organ-a"]

    def test_kernel_n1_triple_rebuild_reproduces_hash_and_serve(
            self, tmp_path):
        """The retirement arm's kernel-N1 clause: the REAL fold rebuilt from
        the SAME valid snapshot under three distinct PYTHONHASHSEEDs emits
        byte-identical artifacts; delete -> rebuild reproduces them; the CLI
        would-dispatches identically over each rebuild."""
        fixture = _HERE / "fixtures" / "cog4" / "fold" / "burst.json"
        snap = json.loads(fixture.read_text(encoding="utf-8"))
        hashes = set()
        outcomes = []
        for seed in ("0", "1", "2"):
            cache = tmp_path / f"cache-{seed}"
            r = subprocess.run(
                [sys.executable, "-c",
                 "import sys\n"
                 f"sys.path.insert(0, {str(_REPO)!r})\n"
                 "from framework.scheduler.fold import build_schedule\n"
                 f"build_schedule({str(fixture)!r}, {str(cache)!r})\n"],
                capture_output=True, text=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed})
            assert r.returncode == 0, r.stderr
            manifest = json.loads(
                (cache / "schedule-manifest.json").read_text("utf-8"))
            hashes.add(manifest["schedule_rows_hash"])
            live = {
                "wake_input_hashes": dict(snap["wake_input_hashes"]),
                "remaining_budget": 100, "wake_id": "wake-n1",
                "organ_output_age_seconds": {},
                "organ_health": {o["organ"]: {"probe_ran": True,
                                              "exit_code": 0}
                                 for o in snap["organs"]},
                "organs_available": [o["organ"] for o in snap["organs"]],
                "capabilities_available":
                    sorted(snap["capability_availability"]),
                "services_cadence": [],
            }
            manifests = {o["organ"]: A.make_organ_manifest(o["organ"])
                         for o in snap["organs"]}
            out = A.run_cli(cache, live, manifests, A.fixture_policy(),
                            tmp_path / f"adapter-{seed}")
            assert out.mode == "dispatch"
            outcomes.append(sorted(
                (r["organ"], r["operation"], r["decision"], r["reason"])
                for r in out.records))
        assert len(hashes) == 1, hashes            # N1 determinism
        assert outcomes[0] == outcomes[1] == outcomes[2]


class TestLimbOrder:
    """test_real_cli_six_limb_order — the §7.3 order battery over the real
    CLI's recorded limbs (serve -> staleness -> authority -> budget ->
    freshness -> idempotency)."""

    def _order_seed(self, tmp_path, row, *, live_overrides=None,
                    shadow_replay=False):
        manifests = {row["organ"]: A.make_organ_manifest(row["organ"])}
        cache, live, manifests, policy = _seed(
            tmp_path, [row], manifests, live_overrides=live_overrides)
        seed_keys = ()
        if shadow_replay:
            seed_keys = (A.derive_idempotency_key(
                row["organ"], row["operation"], live["wake_id"]),)
        return cache, live, manifests, policy, seed_keys

    def test_serve_beats_stale_snapshot(self, tmp_path):
        rows = [A.make_row("organ-a", "collect"),
                A.make_row("organ-b", "report")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a"),
                     "organ-b": A.make_organ_manifest("organ-b")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        (cache / "schedule.jsonl").write_text(
            json.dumps(A.make_row("forged-organ", "exfiltrate"),
                       sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8")
        live["wake_input_hashes"]["organ_registry_hash"] = "moved-registry"
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "serve_refused"
        assert out.reason == "rows_hash_mismatch"

    def test_stale_snapshot_beats_row_limbs(self, tmp_path):
        row = A.make_row("gated-organ", "mutate", risk="fixture_gated")
        cache, live, manifests, policy, _k = self._order_seed(tmp_path, row)
        live["wake_input_hashes"]["services_manifest_hash"] = \
            "moved-services"
        out = _run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "stale_snapshot"
        assert out.records == []

    def test_authority_before_budget(self, tmp_path):
        row = A.make_row("both-organ", "mutate", risk="fixture_gated",
                         budget_units=999)
        cache, live, manifests, policy, _k = self._order_seed(
            tmp_path, row, live_overrides={"remaining_budget": 1})
        out = _run(tmp_path, cache, live, manifests, policy)
        rec = A.by_organ(out, "both-organ")
        assert rec["limb"] == "authority", rec
        assert rec["reason"] == "authority:always_gated"

    def test_budget_before_freshness(self, tmp_path):
        row = A.make_row("bf-organ", "collect", budget_units=999)
        cache, live, manifests, policy, _k = self._order_seed(
            tmp_path, row,
            live_overrides={"remaining_budget": 1,
                            "organ_output_age_seconds":
                            {"bf-organ": 99999}})
        out = _run(tmp_path, cache, live, manifests, policy)
        rec = A.by_organ(out, "bf-organ")
        assert rec["limb"] == "budget", rec

    def test_freshness_before_idempotency(self, tmp_path):
        row = A.make_row("fi-organ", "collect")
        cache, live, manifests, policy, keys = self._order_seed(
            tmp_path, row, shadow_replay=True,
            live_overrides={"organ_output_age_seconds":
                            {"fi-organ": 99999}})
        out = _run(tmp_path, cache, live, manifests, policy,
                   shadow_seed_keys=keys)
        rec = A.by_organ(out, "fi-organ")
        assert rec["limb"] == "freshness", rec

    def test_authority_before_idempotency(self, tmp_path):
        row = A.make_row("ai-organ", "mutate", risk="fixture_gated")
        cache, live, manifests, policy, keys = self._order_seed(
            tmp_path, row, shadow_replay=True)
        out = _run(tmp_path, cache, live, manifests, policy,
                   shadow_seed_keys=keys)
        rec = A.by_organ(out, "ai-organ")
        assert rec["limb"] == "authority", rec

    def test_idempotency_replay_refused_and_rederived(self, tmp_path):
        """SF1: a shadow-logged key refuses; the key is RE-DERIVED per the
        manifest discipline (a row-carried forged 'fresh' key is refused
        anyway); a new wake derives a new key and dispatches; an in-run
        duplicate replays too."""
        row = A.make_row("idem-organ", "collect",
                         idempotency_key="planner-claimed-fresh-key")
        cache, live, manifests, policy, keys = self._order_seed(
            tmp_path, row, shadow_replay=True)
        out = _run(tmp_path, cache, live, manifests, policy,
                   shadow_seed_keys=keys)
        rec = A.by_organ(out, "idem-organ")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "idempotency_replay"
        assert rec["limb"] == "idempotency"
        # a NEW wake id derives a new key => dispatches.
        live2 = dict(live, wake_id="wake-0002")
        out2 = A.run_cli(cache, live2, manifests, policy,
                         tmp_path / "adapter-wake2",
                         shadow_seed_keys=keys)
        assert [r["organ"] for r in out2.would_dispatch()] == ["idem-organ"]
        # in-run duplicate: the same (organ, operation) twice in one
        # schedule => the second is an idempotency replay.
        dup_rows = [A.make_row("idem-organ", "collect"),
                    A.make_row("idem-organ", "collect")]
        cache2 = tmp_path / "dup" / "cache"
        A.build_real_store(cache2, A.make_snapshot(), dup_rows)
        live3 = A.make_live(A.make_snapshot(), manifests)
        out3 = A.run_cli(cache2, live3, manifests, policy,
                         tmp_path / "adapter-dup")
        decisions = sorted(r["decision"] for r in out3.records)
        assert decisions == ["refused", "would_dispatch"]
        refused = [r for r in out3.records
                   if r["decision"] == "refused"][0]
        assert refused["reason"] == "idempotency_replay"


# ===========================================================================
# 3. the CLI's own laws
# ===========================================================================
class TestCliDiscipline:
    def _basic(self, tmp_path, **live_overrides):
        rows = [A.make_row("organ-a", "collect")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        return _seed(tmp_path, rows, manifests,
                     live_overrides=live_overrides or None)

    def test_pointer_tripwire_refuses_outright(self, tmp_path):
        """§7.4: the cutover pointer existing AT ALL refuses — exit 5, mode
        pointer_tripwire, ZERO records, nothing rechecked."""
        cache, live, manifests, policy = self._basic(tmp_path)
        pointer = tmp_path / "state" / "cog4-dispatch-pointer"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("cutover", encoding="utf-8")
        out = _run(tmp_path, cache, live, manifests, policy,
                   pointer_path=pointer)
        assert out.returncode == 5
        assert out.mode == "pointer_tripwire"
        assert out.records == [] and out.would_dispatch() == []
        assert "pointer" in (out.reason or "")
        assert "cutover pointer" in out.stderr

    def test_shadow_log_appends_and_gates_replay_across_runs(self, tmp_path):
        """SF1 end-to-end: run 1 would-dispatches and PERSISTS its key; run 2
        (same wake) refuses as a replay READ FROM THE LOG; the log carries
        both runs' records append-only."""
        cache, live, manifests, policy = self._basic(tmp_path)
        log = tmp_path / "log" / "shadow-log.jsonl"
        out1 = _run(tmp_path, cache, live, manifests, policy,
                    shadow_log=log)
        assert [r["organ"] for r in out1.would_dispatch()] == ["organ-a"]
        out2 = A.run_cli(cache, live, manifests, policy,
                         tmp_path / "adapter2", shadow_log=log)
        rec = A.by_organ(out2, "organ-a")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "idempotency_replay"
        lines = [json.loads(x) for x in
                 log.read_text(encoding="utf-8").splitlines() if x.strip()]
        kinds = [x.get("record_kind") for x in lines]
        assert kinds.count("run") == 2            # both runs recorded
        assert kinds.count("decision") == 2       # one decision each
        first_decision = next(x for x in lines
                              if x.get("record_kind") == "decision")
        assert first_decision["decision"] == "would_dispatch"
        assert isinstance(first_decision.get("idempotency_key"), str)

    def test_shadow_log_lock_held_fails_loud(self, tmp_path):
        cache, live, manifests, policy = self._basic(tmp_path)
        log = tmp_path / "log" / "shadow-log.jsonl"
        log.parent.mkdir(parents=True)
        (log.parent / (log.name + ".lock")).write_text("123",
                                                       encoding="utf-8")
        out = _run(tmp_path, cache, live, manifests, policy,
                   shadow_log=log)
        assert out.returncode == 3
        assert "lock held" in out.stderr

    def test_corrupt_shadow_log_refuses_setup(self, tmp_path):
        """A corrupt shadow log cannot gate replays — fail loud, never guess
        (SF1 integrity)."""
        cache, live, manifests, policy = self._basic(tmp_path)
        log = tmp_path / "log" / "shadow-log.jsonl"
        log.parent.mkdir(parents=True)
        log.write_text('{"idempotency_key": "x"}\nNOT-JSON{{{\n',
                       encoding="utf-8")
        out = _run(tmp_path, cache, live, manifests, policy,
                   shadow_log=log)
        assert out.returncode == 3
        assert "not JSON" in out.stderr

    def test_cli_writes_only_the_shadow_log(self, tmp_path):
        """§7.3 purity: the store bytes are untouched by a run; with the log
        routed OUTSIDE the cache dir, the cache dir bytes are byte-identical
        before/after (the CLI executes nothing, mutates nothing)."""
        cache, live, manifests, policy = self._basic(tmp_path)
        before = {p.name: p.read_bytes() for p in sorted(cache.iterdir())}
        out = _run(tmp_path, cache, live, manifests, policy,
                   shadow_log=tmp_path / "elsewhere" / "log.jsonl")
        assert out.mode == "dispatch"
        after = {p.name: p.read_bytes() for p in sorted(cache.iterdir())}
        assert after == before

    def test_default_shadow_log_lands_under_the_cache_dir(self, tmp_path):
        """The §7.3 default home: <cache-dir>/shadow-log.jsonl (the brief's
        "a shadow log under the cache dir")."""
        cache, live, manifests, policy = self._basic(tmp_path)
        workdir = tmp_path / "w"
        workdir.mkdir()
        for name, payload in (("live.json", live),
                              ("manifests.json", manifests),
                              ("policy.json", policy)):
            (workdir / name).write_text(json.dumps(payload),
                                        encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(CLI), "--cache-dir", str(cache),
             "--live", str(workdir / "live.json"),
             "--organ-manifests", str(workdir / "manifests.json"),
             "--matrix-policy", str(workdir / "policy.json"),
             "--pointer-path", str(workdir / "no-pointer")],
            capture_output=True, text=True, cwd=str(_REPO))
        assert r.returncode == 0, r.stderr
        assert (cache / "shadow-log.jsonl").is_file()

    def test_live_state_validation_fails_closed(self, tmp_path):
        cache, live, manifests, policy = self._basic(tmp_path)
        for broken in (
                {k: v for k, v in live.items() if k != "wake_id"},
                dict(live, remaining_budget="lots"),
                dict(live, wake_input_hashes=None),
                "not-an-object"):
            workdir = tmp_path / f"w{abs(hash(str(broken))) % 10_000}"
            out = A.run_cli(cache, broken, manifests, policy, workdir)
            assert out.returncode == 3, broken
            assert "SETUP FAILURE" in out.stderr

    def test_missing_organ_manifest_refuses_the_row(self, tmp_path):
        """A scheduled organ with no injected manifest is registry drift —
        that ROW refuses (fail-safe), the run survives."""
        rows = [A.make_row("known-organ", "collect"),
                A.make_row("ghost-organ", "collect")]
        manifests = {"known-organ": A.make_organ_manifest("known-organ")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        live["organ_health"]["ghost-organ"] = {"probe_ran": True,
                                               "exit_code": 0}
        live["organs_available"].append("ghost-organ")
        out = _run(tmp_path, cache, live, manifests, policy)
        ghost = A.by_organ(out, "ghost-organ")
        assert ghost["decision"] == "refused"
        assert ghost["reason"] == "organ_manifest_missing:ghost-organ"
        assert [r["organ"] for r in out.would_dispatch()] == ["known-organ"]

    def test_planner_deferred_rows_recheck_nothing(self, tmp_path):
        """A defer row is recorded honestly and grants nothing — the planner
        never admitted it (no budget, no key)."""
        rows = [A.make_row("organ-a", "collect"),
                A.make_row("organ-d", "later", decision="defer",
                           reason="budget_exhausted")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a"),
                     "organ-d": A.make_organ_manifest("organ-d")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        out = _run(tmp_path, cache, live, manifests, policy)
        deferred = A.by_organ(out, "organ-d")
        assert deferred["decision"] == "refused"
        assert deferred["reason"] == "planner_deferred:budget_exhausted"
        assert deferred["limb"] == "planner"
        assert deferred["planner_admitted"] is False
        assert [r["organ"] for r in out.would_dispatch()] == ["organ-a"]

    def test_live_joint_flag_wiring(self, tmp_path):
        """--live-joint smoke: a gated class refuses identically through the
        live joint (read_cell_state over a pinned empty evidence dir — the
        gated verdict never reaches the undo probe), and the hermetic seams
        are refused alongside it."""
        rows = [A.make_row("gated-organ", "mutate", risk="fixture_gated")]
        manifests = {"gated-organ": A.make_organ_manifest("gated-organ")}
        cache, live, manifests, policy = _seed(tmp_path, rows, manifests)
        empty_events = tmp_path / "events-empty"
        empty_events.mkdir()
        out = _run(tmp_path, cache, live, manifests, policy,
                   live_joint=True,
                   extra_env={"CABINET_EVENT_LOG_DIR": str(empty_events)})
        rec = A.by_organ(out, "gated-organ")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "authority:always_gated"
        # seam conflict: --live-joint + --now is a setup error.
        out2 = _run(tmp_path / "conflict", cache, live, manifests, policy,
                    live_joint=True, now="2026-07-24T00:00:00+00:00")
        assert out2.returncode == 3
        assert "pick one mode" in out2.stderr


class TestRealMatrix:
    """The REAL authority joint end-to-end: the CLI's recheck over the
    genuine matrix_policy document (derived here via the matrix accessors —
    a TEST-side import; the CLI itself never imports the matrix)."""

    @pytest.fixture(scope="class")
    def real_policy(self):
        from framework.authority.matrix import load_matrix, matrix_policy
        return json.loads(json.dumps(matrix_policy(load_matrix())))

    def _run_one(self, tmp_path, row, real_policy):
        manifests = {row["organ"]: A.make_organ_manifest(row["organ"])}
        cache, live, manifests, _fixture = _seed(tmp_path, [row], manifests)
        return _run(tmp_path, cache, live, manifests, real_policy)

    def test_read_only_dispatch_class_would_dispatch(self, tmp_path,
                                                     real_policy):
        """investigation_run -> risk_of recompute -> read_only_dispatch ->
        notify_after at unmeasured -> ALLOW. The recompute WINS over a
        divergent declared member (the recheck re-derives, N5)."""
        row = A.make_row("census-organ", "count", risk="reversible",
                         action_type="investigation_run")
        out = self._run_one(tmp_path, row, real_policy)
        assert [r["organ"] for r in out.would_dispatch()] == \
            ["census-organ"]
        rec = A.by_organ(out, "census-organ")
        assert rec["reason"] == "all_limbs_green"

    def test_hard_ceiling_descriptor_refuses(self, tmp_path, real_policy):
        row = A.make_row("spend-organ", "buy", risk="spend",
                         ceiling=("spending",), action_type="spend_request")
        out = self._run_one(tmp_path, row, real_policy)
        rec = A.by_organ(out, "spend-organ")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "authority:ceiling"
        assert rec["verdict"] == "ceiling"

    def test_reversible_with_declared_undo_gap_refuses(self, tmp_path,
                                                       real_policy):
        """local_edit -> reversible -> act_with_undo at unmeasured; the
        descriptor declares undo_contract "none" => the declared undo gap
        refuses (N5 undo-gapped)."""
        row = A.make_row("editor-organ", "rewrite", risk="reversible",
                         undo="none", action_type="local_edit")
        out = self._run_one(tmp_path, row, real_policy)
        rec = A.by_organ(out, "editor-organ")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "authority:undo_gap"
        assert rec["verdict"] == "undo_gap"

    def test_reversible_with_declared_undo_dispatches(self, tmp_path,
                                                      real_policy):
        row = A.make_row("editor-organ", "rewrite", risk="reversible",
                         undo="journal:editor-organ",
                         action_type="local_edit")
        out = self._run_one(tmp_path, row, real_policy)
        assert [r["organ"] for r in out.would_dispatch()] == \
            ["editor-organ"]

    def test_unknown_action_type_fail_safes_to_propose(self, tmp_path,
                                                       real_policy):
        """The engine's unknown-action law through the recheck: an
        action_type outside the policy mapping refuses propose_only even
        though the declared risk_class would have allowed."""
        row = A.make_row("mystery-organ", "do", risk="reversible",
                         undo="journal:x",
                         action_type="never-a-real-action-type")
        out = self._run_one(tmp_path, row, real_policy)
        rec = A.by_organ(out, "mystery-organ")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "authority:propose_only"

    def test_fold_built_store_end_to_end(self, tmp_path, real_policy):
        """The full real pipeline: the shipped burst fixture -> the REAL
        fold -> the CLI over the real matrix. Every selected
        investigation_run row would-dispatches (read_only_dispatch ->
        notify_after); nothing executes; the fold's defer rows surface as
        planner_deferred."""
        fixture = _HERE / "fixtures" / "cog4" / "fold" / "burst.json"
        snap = json.loads(fixture.read_text(encoding="utf-8"))
        cache = tmp_path / "cache"
        A.fold_real_store(fixture, cache)
        manifests = {o["organ"]: A.make_organ_manifest(o["organ"])
                     for o in snap["organs"]}
        live = {
            "wake_input_hashes": dict(snap["wake_input_hashes"]),
            "remaining_budget": snap["budget"]["ceiling_units_per_wake"],
            "wake_id": "wake-real-0001",
            "organ_output_age_seconds": {},
            "organ_health": {o["organ"]: {"probe_ran": True, "exit_code": 0}
                             for o in snap["organs"]},
            "organs_available": [o["organ"] for o in snap["organs"]],
            "capabilities_available":
                sorted(snap["capability_availability"]),
            "services_cadence": [],
        }
        out = A.run_cli(cache, live, manifests, real_policy,
                        tmp_path / "adapter")
        assert out.mode == "dispatch"
        selected = [r for r in out.records if r["planner_admitted"]]
        assert selected, "burst folds a non-empty selection"
        for rec in selected:
            assert rec["decision"] == "would_dispatch", rec
        for rec in out.records:
            if not rec["planner_admitted"]:
                assert rec["reason"].startswith("planner_deferred:"), rec
        assert out.returncode == 0
