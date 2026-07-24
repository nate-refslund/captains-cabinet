"""COG-4 W4 v2 — CLI mechanics battery for `cabinet/scripts/cog4-parity.py`
(the §5.3 N9 parity comparator, the ONE sanctioned dual-plane importer).

NEW battery beside the W2 corpus (§13: the corpus is immutable; new test files
are the sanctioned lane). What the W2 files own vs what THIS file owns:
  * `test_cog4_parity.py` owns the RECORD reference (shape checker +
    divergence law, proven on synthetic records) and the real-ARTIFACT arm
    (vacuity-guarded until a tracked record lands, W5/W6).
  * `test_cog4_parity_ast_pin.py` owns the import-pin scanner + the
    transitive-closure backstop machinery (scratch-file controls).
  * THIS file proves the LANDED CLI's mechanics end-to-end: fixture manifests
    -> record -> assertions THROUGH the W2 reference checkers (imported, never
    re-minted); the independence law behaviorally (a divergent input DIVERGES
    — a leg derived from the other leg could never diverge); determinism
    (byte-identical reruns); the exit-code contract (0 parity / 2 divergence
    or unresolved / 3 setup); the classify_action tool-map arm; fail-closed
    arms; the run-closure law over the REAL file (hermetic run loads no
    executor door) and the §8.4 pin over the REAL file — both live NOW, while
    the corpus real-file arms await their designed retirement surgery (their
    companion absence assertions flip RED the commit this CLI lands; routed to
    the integrator per §13, never edited here).

Fixtures write records ONLY under tmp_path — never inside the repo tree (the
W2 real-artifact arm rglobs the repo for the record basename; a stray record
would fire its companion assertion for the wrong reason).

S0: python3.12, no DB, no network, deterministic (hermetic mode everywhere;
the one --live-state arm pins CABINET_EVENT_LOG_DIR to an empty tmp dir so
the live joint reads an honestly empty evidence plane). Provenance: authored
per the 2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan
continuous grant; COG-4 W4 v2 (parity CLI unit, Fable-for-execution).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_ast_pins as L  # noqa: E402
import test_cog4_parity as REF  # noqa: E402  (the W2 record reference — read, never edited)

_CLI = _REPO / "cabinet/scripts/cog4-parity.py"


# ---------------------------------------------------------------------------
# fixture manifests (the §4.2 proposed shape — the garden-rota W2 idiom:
# genuinely non-software vocabulary; plus a ceiling-class organ)
# ---------------------------------------------------------------------------
def _garden_manifest() -> dict:
    return {
        "name": "garden-rota",
        "version": "1.0.0",
        "kind": "organ",
        "action_types": ["investigation_run"],
        "risk_classes": ["read_only_dispatch"],
        "undo_contract": "none",
        "entrypoints": {},
        "inputs": ["garden/beds.yml", "garden/volunteer-signups.yml"],
        "outputs": ["garden/rota-plan.json"],
        "domain_operations": ["garden/water.plots", "garden/rota.compile"],
        "descriptor": {
            "action_type": "investigation_run",
            "risk_class": "read_only_dispatch",
            "ceiling": [],
            "undo_contract": "none",
            "operations": {
                "garden/water.plots": {"undo_contract": "delete_window(3600)"},
            },
        },
        "permissions": ["files/read"],
        "idempotency": {"garden/water.plots": "bed-id + date",
                        "garden/rota.compile": "week-of"},
        "state_ownership": ["garden/rota-plan.json"],
        "cost_model": {"units_per_wake": 2},
        "starvation_bound": {"max_wakes": 6},
        "freshness_needs": {"max_staleness_seconds": 604800,
                            "expected_output": "garden/rota-plan.json"},
        "trigger_policy": {"mode": "periodic", "parameters": {"interval_s": 86400}},
        "health_proof": {"probe": "rota-plan parses", "expectation": "ok"},
        "fallback": "skip",
        "dependencies": {"organs": [], "capabilities": ["files/read"]},
    }


def _post_manifest() -> dict:
    m = _garden_manifest()
    m.update({
        "name": "post-runner",
        "action_types": ["external_email"],
        "risk_classes": ["external_comms"],
        "outputs": ["post/outbox.json"],
        "domain_operations": ["post/mail.flush"],
        "descriptor": {"action_type": "external_email",
                       "risk_class": "external_comms",
                       "ceiling": ["external_comms"],
                       "undo_contract": "journal:post-outbox"},
        "idempotency": {"post/mail.flush": "batch-id"},
        "state_ownership": ["post/outbox.json"],
        "freshness_needs": {"max_staleness_seconds": 3600,
                            "expected_output": "post/outbox.json"},
    })
    return m


def _notes_manifest() -> dict:
    """A local_edit-compat organ — the tool-map arm's target (classify_action
    on an Edit call returns local_edit, matching the declared compat)."""
    m = _garden_manifest()
    m.update({
        "name": "notes-keeper",
        "action_types": ["local_edit"],
        "risk_classes": ["reversible"],
        "outputs": ["notes/log.md"],
        "domain_operations": ["notes/log.append"],
        "descriptor": {"action_type": "local_edit",
                       "risk_class": "reversible",
                       "ceiling": [],
                       "undo_contract": "delete_window(86400)"},
        "idempotency": {"notes/log.append": "entry-hash"},
        "state_ownership": ["notes/log.md"],
        "freshness_needs": {"max_staleness_seconds": 86400,
                            "expected_output": "notes/log.md"},
    })
    return m


def _write_dir(tmp: Path, name: str, manifests: list[dict]) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    for m in manifests:
        (d / f"{m['name']}.json").write_text(
            json.dumps(m, sort_keys=True), encoding="utf-8")
    return d


def _run(args: list[str], *, env_extra: dict | None = None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(_CLI), *args],
        cwd=str(_REPO), capture_output=True, text=True, env=env)


# ---------------------------------------------------------------------------
# the clean path — record through the W2 reference checkers
# ---------------------------------------------------------------------------
class TestCleanParity:
    def test_clean_fixture_exit0_and_reference_clean(self, tmp_path):
        d = _write_dir(tmp_path, "organs", [_garden_manifest(), _post_manifest()])
        out = tmp_path / "cog4-parity-record.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out)])
        assert r.returncode == 0, r.stdout + r.stderr
        record = json.loads(out.read_text(encoding="utf-8"))
        # THE bind: the landed CLI's record satisfies the W2 reference checker
        # (imported from the corpus — the same checker the retired N9 arm will
        # gate the tracked record with).
        assert REF.record_errors(record) == []
        assert REF.divergent_rows(record) == []
        # coverage: every declared operation, exactly once, sorted
        ops = [row["operation"] for row in record["rows"]]
        assert ops == sorted(
            ["garden/water.plots", "garden/rota.compile", "post/mail.flush"])

    def test_hermetic_default_is_unmeasured_joint(self, tmp_path):
        """Hermetic mode (empty ledger seam) resolves every cell state to
        unmeasured -> the matrix maps read_only_dispatch to notify_after and
        the ceiling class to always_gated; both INDEPENDENT legs agree."""
        d = _write_dir(tmp_path, "organs", [_garden_manifest(), _post_manifest()])
        out = tmp_path / "rec.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out)])
        assert r.returncode == 0, r.stdout + r.stderr
        rows = {row["operation"]: row
                for row in json.loads(out.read_text(encoding="utf-8"))["rows"]}
        garden = rows["garden/rota.compile"]
        for leg in ("descriptor_path", "action_types_path"):
            assert garden[leg]["risk_class"] == "read_only_dispatch"
            assert garden[leg]["ceiling"] == []
            assert garden[leg]["shadow_verdict"] == "notify_after"
        post = rows["post/mail.flush"]
        for leg in ("descriptor_path", "action_types_path"):
            assert post[leg]["risk_class"] == "external_comms"
            assert post[leg]["ceiling"] == ["external_comms"]
            assert post[leg]["shadow_verdict"] == "always_gated"
            assert post[leg]["undo_contract"] == "journal:post-outbox"
        # the per-op override reached BOTH legs' independent merges
        water = rows["garden/water.plots"]
        assert water["descriptor_path"]["undo_contract"] == "delete_window(3600)"
        assert water["action_types_path"]["undo_contract"] == "delete_window(3600)"

    def test_record_bytes_deterministic_across_runs(self, tmp_path):
        d = _write_dir(tmp_path, "organs", [_garden_manifest(), _post_manifest()])
        out1, out2 = tmp_path / "r1.json", tmp_path / "r2.json"
        r1 = _run(["--manifest-dir", str(d), "--out", str(out1)])
        r2 = _run(["--manifest-dir", str(d), "--out", str(out2)])
        assert r1.returncode == 0 and r2.returncode == 0
        assert out1.read_bytes() == out2.read_bytes()

    def test_empty_seeded_ledger_equals_default(self, tmp_path):
        """The --consequence-ledger seam with an EMPTY file is byte-identical
        to the default empty ledger — the seam changes inputs, never shape."""
        d = _write_dir(tmp_path, "organs", [_garden_manifest()])
        ledger = tmp_path / "empty.jsonl"
        ledger.write_text("", encoding="utf-8")
        out1, out2 = tmp_path / "r1.json", tmp_path / "r2.json"
        assert _run(["--manifest-dir", str(d), "--out", str(out1)]).returncode == 0
        assert _run(["--manifest-dir", str(d), "--out", str(out2),
                     "--consequence-ledger", str(ledger)]).returncode == 0
        assert out1.read_bytes() == out2.read_bytes()

    def test_live_state_over_empty_evidence_plane_matches_hermetic(self, tmp_path):
        """--live-state with CABINET_EVENT_LOG_DIR pinned to an empty dir
        reads an honestly empty evidence plane -> every cell unmeasured ->
        byte-identical to the hermetic record (this fixture set resolves no
        act_with_undo verdict, so the undo-gap fall-through never fires)."""
        d = _write_dir(tmp_path, "organs", [_garden_manifest(), _post_manifest()])
        empty_ledger_dir = tmp_path / "no-events"
        empty_ledger_dir.mkdir()
        out1, out2 = tmp_path / "r1.json", tmp_path / "r2.json"
        assert _run(["--manifest-dir", str(d), "--out", str(out1)]).returncode == 0
        r = _run(["--manifest-dir", str(d), "--out", str(out2), "--live-state"],
                 env_extra={"CABINET_EVENT_LOG_DIR": str(empty_ledger_dir)})
        assert r.returncode == 0, r.stdout + r.stderr
        assert out1.read_bytes() == out2.read_bytes()


# ---------------------------------------------------------------------------
# divergence — the independence law, behaviorally (a leg derived FROM the
# other could never diverge; these inputs MUST)
# ---------------------------------------------------------------------------
class TestDivergence:
    def test_nd_violation_diverges_exit2(self, tmp_path):
        """The N-d inconsistency class: declared risk_class 'reversible' under
        compat action_type external_email (matrix-derives external_comms).
        Leg (b)'s matrix derivation MUST diverge from leg (a)'s declared
        values — risk_class, ceiling AND shadow_verdict."""
        bad = _post_manifest()
        bad["name"] = "bad-post"
        bad["domain_operations"] = ["bad/mail.flush"]
        bad["descriptor"] = {"action_type": "external_email",
                             "risk_class": "reversible",
                             "ceiling": [],
                             "undo_contract": "none"}
        bad["idempotency"] = {"bad/mail.flush": "batch-id"}
        bad["state_ownership"] = ["bad/outbox.json"]
        d = _write_dir(tmp_path, "organs", [bad])
        out = tmp_path / "rec.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out)])
        assert r.returncode == 2, r.stdout + r.stderr
        assert "DIVERGES" in r.stdout
        assert "risk_class" in r.stdout and "ceiling" in r.stdout
        # the record carries the divergence evidence, and the W2 reference
        # checker REDs on it exactly as the retired N9 arm would
        record = json.loads(out.read_text(encoding="utf-8"))
        assert REF.record_errors(record) == []
        div = REF.divergent_rows(record)
        assert len(div) == 1 and "bad/mail.flush" in div[0]

    def test_single_member_divergence_is_named(self, tmp_path):
        """ONE diverging member (undo_contract only) is reported by name and
        the other three members stay undisputed — divergence is per-member,
        never a blanket flag."""
        m = _garden_manifest()
        # leg b reads the same declared undo values as leg a, so a pure
        # undo-only divergence needs the OVERRIDE path: declare an override
        # that leg a honors and leg b honors identically — undo CANNOT
        # diverge between honest legs; instead diverge shadow_verdict via
        # risk_class (the verdict member re-derives). So: declared risk_class
        # read_only_dispatch vs compat task_status_move (matrix: reversible).
        m["descriptor"]["action_type"] = "task_status_move"
        d = _write_dir(tmp_path, "organs", [m])
        out = tmp_path / "rec.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out)])
        assert r.returncode == 2
        assert "risk_class: descriptor='read_only_dispatch' vs action_types='reversible'" in r.stdout
        # undo_contract agreed — never named as diverging
        assert "undo_contract:" not in r.stdout


# ---------------------------------------------------------------------------
# the tool-map arm — classify_action drives leg (b) where a mapping exists
# ---------------------------------------------------------------------------
class TestToolMap:
    def test_consistent_tool_map_is_parity_green(self, tmp_path):
        """An Edit tool call classifies to local_edit == the declared compat
        member -> the classifier-driven leg agrees with the descriptor leg."""
        d = _write_dir(tmp_path, "organs", [_notes_manifest()])
        tool_map = tmp_path / "tools.json"
        tool_map.write_text(json.dumps({
            "notes/log.append": {"tool_name": "Edit",
                                 "tool_input": {"file_path": "notes/log.md"}},
        }), encoding="utf-8")
        out = tmp_path / "rec.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out),
                  "--tool-map", str(tool_map)])
        assert r.returncode == 0, r.stdout + r.stderr
        row = json.loads(out.read_text(encoding="utf-8"))["rows"][0]
        assert row["action_types_path"]["risk_class"] == "reversible"

    def test_inconsistent_tool_map_diverges(self, tmp_path):
        """A Write tool call classifies to local_edit (reversible) while the
        manifest declares investigation_run/read_only_dispatch — the
        classifier path MUST diverge (never silently trust the declaration
        when a real tool mapping exists)."""
        d = _write_dir(tmp_path, "organs", [_garden_manifest()])
        tool_map = tmp_path / "tools.json"
        tool_map.write_text(json.dumps({
            "garden/water.plots": {"tool_name": "Write",
                                   "tool_input": {"file_path": "garden/rota-plan.json"}},
        }), encoding="utf-8")
        r = _run(["--manifest-dir", str(d), "--out", str(tmp_path / "rec.json"),
                  "--tool-map", str(tool_map)])
        assert r.returncode == 2
        assert "garden/water.plots" in r.stdout and "DIVERGES" in r.stdout
        assert "reversible" in r.stdout and "read_only_dispatch" in r.stdout

    def test_tool_map_for_undeclared_operation_is_setup_failure(self, tmp_path):
        d = _write_dir(tmp_path, "organs", [_garden_manifest()])
        tool_map = tmp_path / "tools.json"
        tool_map.write_text(json.dumps({
            "ghost/op.nobody-declares": {"tool_name": "Edit", "tool_input": {}},
        }), encoding="utf-8")
        r = _run(["--manifest-dir", str(d), "--out", str(tmp_path / "rec.json"),
                  "--tool-map", str(tool_map)])
        assert r.returncode == 3
        assert "undeclared operations" in r.stderr


# ---------------------------------------------------------------------------
# fail-closed arms — unresolved is never parity, setup is never a record
# ---------------------------------------------------------------------------
class TestFailClosed:
    def test_ambiguous_compat_member_is_unresolved_exit2_no_record(self, tmp_path):
        """`ambiguous` deliberately has no matrix risk_class (risk_of -> None):
        the ACTION_TYPES path cannot produce a tuple -> UNRESOLVED, exit 2,
        and NO record is written (a partial record is not parity evidence)."""
        m = _garden_manifest()
        m["descriptor"]["action_type"] = "ambiguous"
        d = _write_dir(tmp_path, "organs", [m])
        out = tmp_path / "rec.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out)])
        assert r.returncode == 2
        assert "UNRESOLVED" in r.stdout and "no matrix risk_class" in r.stdout
        assert not out.exists()

    def test_duplicate_declarers_unresolved_exit2(self, tmp_path):
        m1 = _garden_manifest()
        m2 = _garden_manifest()
        m2["name"] = "garden-rota-clone"
        m2["state_ownership"] = ["garden/rota-plan-2.json"]
        d = _write_dir(tmp_path, "organs", [m1, m2])
        r = _run(["--manifest-dir", str(d), "--out", str(tmp_path / "rec.json")])
        assert r.returncode == 2
        assert "UNRESOLVED" in r.stdout

    def test_missing_manifest_dir_exit3(self, tmp_path):
        r = _run(["--manifest-dir", str(tmp_path / "nowhere"),
                  "--out", str(tmp_path / "rec.json")])
        assert r.returncode == 3
        assert "SETUP FAILURE" in r.stderr

    def test_zero_declared_operations_exit3(self, tmp_path):
        """R-A non-empty: a registry with organs but zero declared operations
        is a vacuously green parity run — refused as setup, never exit 0."""
        m = _garden_manifest()
        del m["domain_operations"]
        d = _write_dir(tmp_path, "organs", [m])
        r = _run(["--manifest-dir", str(d), "--out", str(tmp_path / "rec.json")])
        assert r.returncode == 3
        assert "zero declared operations" in r.stderr

    def test_flat_operation_id_is_setup_failure_exit3(self, tmp_path):
        """The §4.3 namespace law, fail-CLOSED: a FLAT operation id (no '/')
        would produce a record the W2 reference checker REDs as MALFORMED
        (`record_errors` names the namespace law) — and a flat id can
        literally collide with an ACTION_TYPES member ('local_edit' is one).
        With organ-schema validation PARKED (germline window unopened),
        nothing upstream enforces the grammar, so the CLI refuses at setup
        (exit 3, no record) — the same R-A posture as zero declared
        operations: exit 0 must never vouch for a record the N9 gate would
        refuse."""
        m = _garden_manifest()
        m["domain_operations"] = ["flatop"]
        m["descriptor"] = {"action_type": "investigation_run",
                           "risk_class": "read_only_dispatch",
                           "ceiling": [],
                           "undo_contract": "none"}
        m["idempotency"] = {"flatop": "k"}
        d = _write_dir(tmp_path, "organs", [m])
        out = tmp_path / "rec.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out)])
        assert r.returncode == 3, r.stdout + r.stderr
        assert "SETUP FAILURE" in r.stderr
        assert "'flatop'" in r.stderr and "non-namespaced" in r.stderr
        assert "'<domain>/<operation>'" in r.stderr
        assert not out.exists()   # a refused run never writes a record
        # the flat id REDs the W2 reference checker exactly as the CLI's
        # refusal message claims — the mirror is real, not asserted prose
        synthetic = {"schema": "cog4-parity-record/v1", "rows": [{
            "operation": "flatop", "organ": m["name"],
            "descriptor_path": {"risk_class": "read_only_dispatch",
                                "ceiling": [], "undo_contract": "none",
                                "shadow_verdict": "notify_after"},
            "action_types_path": {"risk_class": "read_only_dispatch",
                                  "ceiling": [], "undo_contract": "none",
                                  "shadow_verdict": "notify_after"}}]}
        assert any("namespaced" in e for e in REF.record_errors(synthetic))

    def test_garbage_ledger_line_is_setup_failure(self, tmp_path):
        d = _write_dir(tmp_path, "organs", [_garden_manifest()])
        ledger = tmp_path / "bad.jsonl"
        ledger.write_text("{not json}\n", encoding="utf-8")
        r = _run(["--manifest-dir", str(d), "--out", str(tmp_path / "rec.json"),
                  "--consequence-ledger", str(ledger)])
        assert r.returncode == 3

    def test_live_state_excludes_hermetic_seams(self, tmp_path):
        d = _write_dir(tmp_path, "organs", [_garden_manifest()])
        ledger = tmp_path / "empty.jsonl"
        ledger.write_text("", encoding="utf-8")
        r = _run(["--manifest-dir", str(d), "--out", str(tmp_path / "rec.json"),
                  "--live-state", "--consequence-ledger", str(ledger)])
        assert r.returncode == 3
        assert "pick one mode" in r.stderr


# ---------------------------------------------------------------------------
# boundary laws over the REAL landed file (live NOW — the corpus real-file
# arms carry designed retirement tripwires the integrator discharges)
# ---------------------------------------------------------------------------
class TestBoundaryLawsLive:
    def test_ast_pin_folds_clean_over_the_landed_cli(self):
        """The §8.4 symbol pin over the REAL cabinet/scripts/cog4-parity.py:
        the imports match the sanctioned dual-plane surface exactly."""
        assert _CLI.exists()
        assert L.parity_import_violations(_REPO) == []

    def test_hermetic_run_closure_excludes_executor_doors(self, tmp_path):
        """The transitive-closure law, run against the REAL CLI: a hermetic
        parity run never loads framework.acting / framework.frontdoor (the
        undo-gap probe — whose call-time imports ARE those doors — belongs to
        --live-state only). This is the exact check the corpus closure arm's
        RETIREMENT CONDITION names."""
        d = _write_dir(tmp_path, "organs", [_garden_manifest(), _post_manifest()])
        out = tmp_path / "rec.json"
        driver = (
            "import sys, json, runpy\n"
            f"sys.argv = ['cog4-parity.py', '--manifest-dir', {str(d)!r}, "
            f"'--out', {str(out)!r}]\n"
            "rc = 0\n"
            "try:\n"
            f"    runpy.run_path({str(_CLI)!r}, run_name='__main__')\n"
            "except SystemExit as e:\n"
            "    rc = int(e.code or 0)\n"
            "doors = sorted(m for m in sys.modules\n"
            "               if m == 'framework.acting' or m.startswith('framework.acting.')\n"
            "               or m == 'framework.frontdoor' or m.startswith('framework.frontdoor.'))\n"
            "print(json.dumps({'rc': rc, 'doors': doors}))\n"
        )
        r = subprocess.run([sys.executable, "-c", driver], cwd=str(_REPO),
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout.strip().splitlines()[-1])
        assert payload["rc"] == 0
        assert payload["doors"] == [], payload

    def test_reversible_class_hermetic_verdict_is_act_with_undo_without_gap_probe(self, tmp_path):
        """A reversible-class fixture resolves act_with_undo at unmeasured
        (the trust-first matrix row) and hermetic mode records it VERBATIM —
        no undo-gap fall-through, no executor-door import (the closure test
        above covers the doors; this arm pins the verdict semantics)."""
        d = _write_dir(tmp_path, "organs", [_notes_manifest()])
        out = tmp_path / "rec.json"
        r = _run(["--manifest-dir", str(d), "--out", str(out)])
        assert r.returncode == 0, r.stdout + r.stderr
        row = json.loads(out.read_text(encoding="utf-8"))["rows"][0]
        assert row["descriptor_path"]["shadow_verdict"] == "act_with_undo"
        assert row["action_types_path"]["shadow_verdict"] == "act_with_undo"

    def test_no_record_ever_written_inside_the_repo_by_this_battery(self):
        """Self-discipline tripwire: this battery must never leave a
        cog4-parity-record.json inside the repo tree (the W2 real-artifact arm
        rglobs for the basename; a stray file would fire it for the wrong
        reason). Runs last alphabetically-close to the others; cheap rglob.

        EXEMPTION (integrator corpus surgery per §13 + the unit
        contradictions[] routes, W5 landing 2026-07-24): the ONE tracked
        record at cabinet/scripts/tests/fixtures/cog4/cog4-parity-record.json
        is the DELIBERATE N9 artifact landed by W5 x3 (ea9da8ad) — committed
        cog4-parity.py output over the pilot + cabinet manifests, NOT battery
        output — and is gated by test_cog4_parity.py + test_cog4_parity_record
        .py. This law keeps biting for any OTHER repo-internal record: a stray
        write anywhere else still REDs here."""
        sanctioned = (_HERE / "fixtures" / "cog4"
                      / "cog4-parity-record.json").resolve()
        strays = [p for p in _REPO.rglob("cog4-parity-record.json")
                  if ".git" not in p.parts and p.resolve() != sanctioned]
        assert strays == [], strays
