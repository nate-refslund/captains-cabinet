"""Tests for the A2 mechanical coverage reconciler (evidence-coverage.py).

Pins the drift-catch teeth (design §2.4 A2 / §3 Ph2 gate): the reconciler
reports honest KNOWN-GAP rows for uncovered action surfaces (exit 0), but
fails (exit 1) on an UNENUMERATED action-taking surface — a producer that maps
to no enumerated row.  ``--strict`` is the Phase-2-end gate that turns any gap
into a failure.  Every case runs against a synthetic ``--root`` tree so the
teeth are proven independently of the real repo's evolving coverage; two cases
also pin the real repo's honest output at this pin.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "cabinet" / "scripts" / "evidence-coverage.py"

spec = importlib.util.spec_from_file_location("evidence_coverage", SCRIPT)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        text=True,
        capture_output=True,
    )


# --- fake-tree teeth: unenumerated surfaces are drift (exit 1) --------------

def test_unenumerated_consequence_writer_is_drift(tmp_path):
    _write(
        tmp_path, "framework/newlane/act.py",
        "from framework.fidelity.consequence import emit_consequence\n"
        "def go():\n    emit_consequence({})\n",
    )
    report = coverage.reconcile(tmp_path)
    assert report["unenumerated"], "rogue consequence writer not flagged"
    assert report["unenumerated"][0]["file"] == "framework/newlane/act.py"

    result = _run(tmp_path)
    assert result.returncode == 1
    assert "framework/newlane/act.py" in result.stderr
    assert "UNENUMERATED" in result.stderr


def test_unenumerated_evidence_importer_is_drift(tmp_path):
    _write(
        tmp_path, "framework/newlane/producer.py",
        "from framework.evidence import EvidenceRecorder\n"
        "recorder = EvidenceRecorder()\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "framework/newlane/producer.py" in result.stderr


def test_unenumerated_script_producer_is_drift(tmp_path):
    _write(
        tmp_path, "cabinet/scripts/rogue-runner.py",
        "import framework.evidence.recorder\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "cabinet/scripts/rogue-runner.py" in result.stderr


# --- fake-tree: enumerated surfaces, gaps allowed by default ---------------

def test_enumerated_gaps_pass_by_default_and_fail_strict(tmp_path):
    # An enumerated action surface (onboarding) present but UNWIRED = a gap.
    _write(
        tmp_path, "framework/onboarding/journey.py",
        "def act():\n    return None\n",
    )
    default = _run(tmp_path)
    assert default.returncode == 0, default.stderr
    assert "named gaps:" in default.stdout

    strict = _run(tmp_path, "--strict")
    assert strict.returncode == 2
    assert "STRICT GATE" in strict.stderr
    assert "onboarding-journey" in strict.stderr


def test_wired_enumerated_surface_counts_as_covered(tmp_path):
    _write(
        tmp_path, "framework/onboarding/journey.py",
        "from framework.evidence import EvidenceRecorder\n"
        "def act():\n    return EvidenceRecorder()\n",
    )
    report = coverage.reconcile(tmp_path)
    onboarding = next(
        row for row in report["surfaces"] if row["id"] == "onboarding-journey"
    )
    assert onboarding["status"] == "WIRED"
    assert onboarding["producers"] == ["framework/onboarding/journey.py"]
    assert "onboarding-journey" not in report["gaps"]
    # The enumeration is STATIC: the other action surfaces have no files in
    # this sparse tree, so they are gaps and --strict fails on them — but the
    # wired surface is never named as a gap.
    strict = _run(tmp_path, "--strict")
    assert strict.returncode == 2
    assert "onboarding-journey" not in strict.stderr


# --- detection precision ----------------------------------------------------

def test_test_files_are_not_producers(tmp_path):
    # A test that imports the recorder must NOT count as a producer/drift.
    _write(
        tmp_path, "framework/newlane/tests/test_x.py",
        "from framework.evidence import EvidenceRecorder\n",
    )
    _write(
        tmp_path, "framework/newlane/test_inline.py",
        "import framework.evidence.recorder\n",
    )
    report = coverage.reconcile(tmp_path)
    assert report["unenumerated"] == []
    assert _run(tmp_path).returncode == 0


def test_enforcement_hook_prose_is_not_a_producer(tmp_path):
    # A shell file that merely NAMES the module tokens in guard prose (as the
    # real pre-tool-use.sh does) must not read as wired.
    _write(
        tmp_path, "cabinet/scripts/hooks/pre-tool-use.sh",
        "# BLOCKED: framework.evidence access via python is refused\n"
        "echo guard\n",
    )
    report = coverage.reconcile(tmp_path)
    hooks = next(
        row for row in report["surfaces"]
        if row["id"] == "officer-session-lifecycle"
    )
    assert hooks["status"] == "KNOWN-GAP"
    assert report["unenumerated"] == []


def test_shell_cli_invocation_is_enumerated_but_never_wired(tmp_path):
    """A shell invocation of the evidence CLI (the doctor's read-only chain
    spot-check) is drift bait that must be enumerated, but it is NEVER
    producer wiring — there is no emit CLI by law, so a read-only probe must
    not flip its act surface to WIRED."""
    _write(
        tmp_path, "cabinet/scripts/cabinet-doctor.sh",
        '#!/bin/bash\n$PY -m framework.evidence verify --store "$STORE" --json\n',
    )
    report = coverage.reconcile(tmp_path)
    doctor = next(
        row for row in report["surfaces"] if row["id"] == "watchdog-doctor"
    )
    assert doctor["status"] == "KNOWN-GAP"
    assert doctor["producers"] == []
    # ...but the file IS an enumerated detector hit (no drift, evidence_cli).
    assert report["unenumerated"] == []
    assert report["detector_hits"]["cabinet/scripts/cabinet-doctor.sh"] == [
        "evidence_cli"
    ]
    # An UNenumerated shell CLI invocation is still drift (the catch works).
    _write(
        tmp_path, "cabinet/scripts/lib/rogue-helper.sh",
        '#!/bin/bash\npython3.12 -m framework.evidence export --trial x\n',
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "rogue-helper.sh" in result.stderr


def test_chokepoint_mirror_seam_counts_as_wired(tmp_path):
    """The Batch-A chokepoint seam (``from framework import evidence_mirror``)
    is producer wiring for the mirror surfaces (G1's producers are LIVE)."""
    _write(
        tmp_path, "framework/events/emitter.py",
        "def emit(event_type, payload):\n"
        "    from framework import evidence_mirror\n"
        "    return evidence_mirror.reserve_org(event_type)\n",
    )
    _write(
        tmp_path, "framework/fidelity/consequence.py",
        "def emit_consequence(**kw):\n"
        "    from framework import evidence_mirror\n"
        "    return evidence_mirror.reserve_consequence(kw)\n",
    )
    report = coverage.reconcile(tmp_path)
    by_id = {row["id"]: row for row in report["surfaces"]}
    assert by_id["org-event-mirror"]["status"] == "WIRED"
    assert by_id["org-event-mirror"]["producers"] == ["framework/events/emitter.py"]
    assert by_id["consequence-mirror"]["status"] == "WIRED"
    assert report["unenumerated"] == []


# --- real repo: honest output at this pin ----------------------------------

def test_real_repo_reconciles_clean_with_reported_gaps():
    result = _run(REPO_ROOT)
    # At the Batch-A pin the act surfaces are honest KNOWN-GAP rows: exit 0,
    # no drift.  (If this ever exits 1, an un-enumerated producer landed.)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("evidence covers ")
    assert "action-taking surfaces; named gaps:" in result.stdout


def test_real_repo_json_shape_stable():
    result = _run(REPO_ROOT, "--json")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["schema"] == "cabinet.evidence-coverage/v1"
    for key in ("line", "covered", "total", "gaps", "surfaces",
                "unenumerated", "detector_hits"):
        assert key in report, key
    assert report["unenumerated"] == []
    assert report["total"] >= 1
    # Every surface row carries the stable shape the Captain line derives from.
    for row in report["surfaces"]:
        assert set(row) == {"id", "kind", "design", "status", "producers"}
        assert row["status"] in {"WIRED", "KNOWN-GAP", "INFRA"}
    # Post-Batch-B truth: the two Phase-1 producers, the two chokepoint
    # mirrors AND the five Batch B act surfaces are wired (design §3 Phase 2
    # items 2a–2d + §7 R-1).  The doctor's read-only chain spot-check is
    # still not a producer — watchdog-doctor's wiring is the typed lens
    # seam (framework/watchdog/receipts.py).  The four remaining act
    # surfaces stay honest KNOWN-GAP rows (future waves — the Captain line
    # must SAY so, never imply completeness).
    by_id = {row["id"]: row for row in report["surfaces"]}
    assert by_id["onboarding-journey"]["status"] == "WIRED"
    assert by_id["digest-anchor"]["status"] == "WIRED"
    assert by_id["org-event-mirror"]["status"] == "WIRED"
    assert by_id["org-event-mirror"]["producers"] == ["framework/events/emitter.py"]
    assert by_id["consequence-mirror"]["status"] == "WIRED"
    assert by_id["consequence-mirror"]["producers"] == [
        "framework/fidelity/consequence.py"
    ]
    batch_b_producers = {
        "act-first-lane": [
            "framework/acting/run_action_lane.py",
            "framework/frontdoor/action_exec.py",
            "framework/frontdoor/action_reconcile.py",
        ],
        "learning-gate": [
            "framework/learning/apply_watch.py",
            "framework/learning/gate.py",
        ],
        "authority-control-plane": [
            "cabinet/scripts/emit-authority-transitions.py",
        ],
        "watchdog-doctor": [
            "framework/watchdog/receipts.py",
        ],
        "officer-session-lifecycle": [
            "cabinet/scripts/emit-officer-lifecycle-transitions.py",
        ],
    }
    for act_surface, producers in batch_b_producers.items():
        assert by_id[act_surface]["status"] == "WIRED", act_surface
        assert by_id[act_surface]["producers"] == producers, act_surface
        assert act_surface not in report["gaps"]
    for gap_surface in ("attention-hygiene", "probes-verification",
                        "roles-missions-lifecycle", "ops-consequence-scripts"):
        assert by_id[gap_surface]["status"] == "KNOWN-GAP", gap_surface
        assert gap_surface in report["gaps"]
    # The mirror engine itself is enumerated infra, never counted in N-of-M.
    assert by_id["evidence-plane-tooling"]["status"] == "INFRA"
    assert (
        "framework/evidence_mirror.py"
        in by_id["evidence-plane-tooling"]["producers"]
    )


def test_reconciler_reads_no_evidence_store_and_writes_nothing(tmp_path):
    # Contract: the reconciler never opens the evidence store and never
    # writes.  Reconcile a tree containing an instance/evidence dir and assert
    # it is neither scanned (only framework/ + cabinet/scripts/ are) nor
    # mutated.
    _write(tmp_path, "instance/evidence/v1/trials/x/events.jsonl", "{}\n")
    _write(tmp_path, "framework/onboarding/journey.py", "def act():\n    pass\n")
    before = sorted(p.relative_to(tmp_path).as_posix()
                    for p in tmp_path.rglob("*") if p.is_file())
    report = coverage.reconcile(tmp_path)
    after = sorted(p.relative_to(tmp_path).as_posix()
                   for p in tmp_path.rglob("*") if p.is_file())
    assert before == after, "reconciler mutated the tree"
    assert all("instance/evidence" not in rel
               for rel in report["detector_hits"])
