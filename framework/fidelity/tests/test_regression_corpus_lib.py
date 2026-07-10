"""Tests — framework/fidelity/regression_corpus_lib.py (flywheel step 1).

Synthetic-ledger based; the repo-root conftest.py fence already sandboxes
CABINET_EVENT_LOG_DIR/CABINET_UNDO_DIR for the whole session, and every test
that touches the ledger additionally points CABINET_EVENT_LOG_DIR at its own
tmp_path (per-test isolation on top of the session fence). The live ledger is
never read or written.

Covers: correction classification (edit/skip/veto/undo/human_wrong + every
exclusion class), case shape ({situation, human_verdict, cell} with the
UNSTAMPED sentinel), case-id determinism, frozen-write idempotency, the
frozen-conflict alarm, deterministic manifest, and the CLI subprocess smoke.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from framework.fidelity.consequence import UNSTAMPED_ACTION_TYPE
from framework.fidelity.regression_corpus_lib import (
    CORRECTION_KINDS,
    CorpusWriteConflict,
    case_id_for,
    corpus_fingerprint,
    extract_corrections,
    write_corpus,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / "cabinet" / "scripts" / "build-regression-corpus.py"


# ---------------------------------------------------------------------------
# row builders — mirror the REAL emitter shapes (loop.py / binder_wire.py)
# ---------------------------------------------------------------------------

def _row(**over):
    base = {
        "ts": "2026-07-03T20:43:15Z",
        "actor": {"kind": "officer", "id": "officer:cos"},
        "lane": "ada",
        "action": "action-card",
        "subject": "subj-default",
        "refs": [],
    }
    base.update(over)
    return base


def _edited_row(subject="edited-1"):
    # loop.py::_VERDICT "edit" -> decision=edited, review wrong verdict_human
    return _row(
        subject=subject,
        proposal={"required": True, "decision": "edited",
                  "decided_at": "2026-07-03T21:07:40Z"},
        outcome={"status": "ok",
                 "evidence": "captain edited the draft before it shipped"},
        review={"verdict": "wrong", "source": "verdict_human"},
    )


def _rejected_row(subject="skipped-1"):
    # loop.py::_VERDICT "skip" -> decision=rejected, verdict unknown (FIX D)
    return _row(
        subject=subject,
        proposal={"required": True, "decision": "rejected",
                  "decided_at": "2026-07-03T21:07:57Z"},
        outcome={"status": "unknown"},
        review={"verdict": "unknown"},
    )


def _acted_human_wrong(subject, evidence):
    # binder_wire.py::_ACTED_VERDICTS undo/edit/never — acted cards carry
    # decision=None (never proposed) + review wrong verdict_human.
    return _row(
        subject=subject,
        action_type="pm_write",
        proposal={"required": False, "decision": None},
        outcome={"status": "failed" if evidence.startswith("captain-undo") else "ok",
                 "evidence": evidence},
        review={"verdict": "wrong", "source": "verdict_human"},
    )


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def test_kind_vocabulary_is_closed():
    assert CORRECTION_KINDS == ("edit", "skip", "veto", "undo", "human_wrong")


def test_extracts_all_five_kinds():
    rows = [
        _edited_row("s-edit"),
        _rejected_row("s-skip"),
        _acted_human_wrong("s-undo", "captain-undo: bad calendar block"),
        _acted_human_wrong("s-veto", "captain veto (never); artifact stands, cell demoted"),
        _acted_human_wrong("s-wrong", "some other human wrong evidence"),
    ]
    cases = extract_corrections(ledger=rows)
    kinds = {c["situation"]["subject"]: c["human_verdict"]["kind"] for c in cases}
    assert kinds == {
        "s-edit": "edit",
        "s-skip": "skip",
        "s-undo": "undo",
        "s-veto": "veto",
        "s-wrong": "human_wrong",
    }


def test_acted_edit_prefix_classifies_as_edit():
    # binder edit: decision=None so the evidence prefix carries the kind.
    rows = [_acted_human_wrong(
        "s-acted-edit", "captain edited (re-card); acted artifact stands")]
    cases = extract_corrections(ledger=rows)
    assert cases[0]["human_verdict"]["kind"] == "edit"


@pytest.mark.parametrize("row", [
    # approved: a confirmation, not a correction.
    _row(subject="x-appr",
         proposal={"required": True, "decision": "approved",
                   "decided_at": "2026-07-03T21:08:55Z"},
         outcome={"status": "ok", "evidence": "captain approved"},
         review={"verdict": "confirmed", "source": "verdict_human"}),
    # expired: no human judgment was rendered.
    _row(subject="x-exp",
         proposal={"required": True, "decision": "expired",
                   "decided_at": "2026-07-03T21:08:55Z"}),
    # pending proposal: nothing decided yet.
    _row(subject="x-pend", proposal={"required": True, "decision": None}),
    # machine wrong (verdict_judge): NEVER human ground truth (fail-closed).
    _row(subject="x-judge",
         outcome={"status": "failed", "evidence": "silent revert"},
         review={"verdict": "wrong", "source": "verdict_judge"}),
    # unattributed wrong: excluded, mirrors promotion math's posture.
    _row(subject="x-noattr",
         outcome={"status": "failed", "evidence": "legacy wrong"},
         review={"verdict": "wrong"}),
    # system source: non-judgment closure.
    _row(subject="x-system",
         outcome={"status": "ok", "evidence": "auto-expiry"},
         review={"verdict": "wrong", "source": "system"}),
    # bare row: no proposal, no review.
    _row(subject="x-bare"),
])
def test_non_corrections_are_excluded(row):
    assert extract_corrections(ledger=[row]) == []


def test_sim_rows_never_seed_cases():
    row = _edited_row("s-sim")
    row["sim"] = True
    assert extract_corrections(ledger=[row]) == []


def test_junk_rows_never_crash():
    assert extract_corrections(ledger=["not-a-dict", None, 42]) == []


# ---------------------------------------------------------------------------
# case shape + determinism
# ---------------------------------------------------------------------------

def test_case_shape_situation_verdict_cell():
    row = _edited_row("s-shape")
    row["refs"] = ["6-Commitments/owed_by_nate/cmt-abc.md"]
    case = extract_corrections(ledger=[row])[0]

    # cell keys exactly like compute_ratios (actor flattened, unstamped
    # sentinel for the missing action_type).
    assert case["cell"] == {
        "actor": "officer:officer:cos",
        "lane": "ada",
        "action_type": UNSTAMPED_ACTION_TYPE,
    }
    # situation is a replay REFERENCE — no draft content fields exist.
    sit = case["situation"]
    assert sit["subject"] == "s-shape"
    assert sit["refs"] == ["6-Commitments/owed_by_nate/cmt-abc.md"]
    assert sit["ts"] == row["ts"]
    assert sit["action_type"] is None  # raw (unstamped) value preserved here
    # human verdict carries the raw decision/review fields + evidence.
    hv = case["human_verdict"]
    assert hv["kind"] == "edit"
    assert hv["proposal_decision"] == "edited"
    assert hv["review_verdict"] == "wrong"
    assert hv["review_source"] == "verdict_human"
    assert "captain edited" in hv["evidence"]


def test_stamped_action_type_flows_into_cell():
    row = _acted_human_wrong("s-cell", "captain-undo")
    case = extract_corrections(ledger=[row])[0]
    assert case["cell"]["action_type"] == "pm_write"
    assert case["situation"]["action_type"] == "pm_write"


def test_case_id_is_deterministic_and_kind_sensitive():
    row = _edited_row("s-det")
    a = case_id_for(row, "edit")
    b = case_id_for(row, "edit")
    c = case_id_for(row, "skip")
    assert a == b
    assert a != c
    assert a.startswith("case-") and len(a) == len("case-") + 16


def test_case_id_delimiter_smuggling_cannot_collide():
    # Checkpoint review 2026-07-05: the hash input is a JSON list, so a field
    # containing a would-be delimiter can never realign the identity tuple.
    # Under a naive 'actor|action|subject|ts|kind' join these two would both
    # serialize to '...|a|b|c|...' and collide; the JSON framing keeps them apart.
    row_a = _edited_row("b|c")
    row_a["action"] = "a"
    row_b = _edited_row("c")
    row_b["action"] = "a|b"
    assert case_id_for(row_a, "edit") != case_id_for(row_b, "edit")


def test_extract_output_is_sorted_and_deduped():
    row = _edited_row("s-dup")
    cases = extract_corrections(ledger=[row, dict(row)])  # same identity twice
    assert len(cases) == 1
    many = extract_corrections(
        ledger=[_edited_row(f"s-{i}") for i in range(5)])
    assert [c["case_id"] for c in many] == sorted(c["case_id"] for c in many)


# ---------------------------------------------------------------------------
# frozen corpus IO
# ---------------------------------------------------------------------------

def test_write_corpus_roundtrip_and_idempotency(tmp_path):
    cases = extract_corrections(ledger=[_edited_row("s-a"), _rejected_row("s-b")])
    first = write_corpus(cases, corpus_dir=tmp_path)
    assert len(first["written"]) == 2 and first["conflicts"] == []

    # Snapshot every byte, re-run, prove byte-identical (idempotent).
    snap = {p.name: p.read_bytes() for p in (tmp_path / "cases").iterdir()}
    manifest_snap = (tmp_path / "manifest.json").read_bytes()
    second = write_corpus(cases, corpus_dir=tmp_path)
    assert second["written"] == [] and len(second["unchanged"]) == 2
    assert {p.name: p.read_bytes()
            for p in (tmp_path / "cases").iterdir()} == snap
    assert (tmp_path / "manifest.json").read_bytes() == manifest_snap


def test_frozen_file_never_rewritten_on_conflict(tmp_path):
    cases = extract_corrections(ledger=[_edited_row("s-frozen")])
    write_corpus(cases, corpus_dir=tmp_path)
    cid = cases[0]["case_id"]
    frozen_path = tmp_path / "cases" / f"{cid}.json"
    frozen_bytes = frozen_path.read_bytes()

    # Mutate the regenerated case (simulates upstream append-only violation).
    mutated = json.loads(json.dumps(cases[0]))
    mutated["human_verdict"]["evidence"] = "TAMPERED"
    summary = write_corpus([mutated], corpus_dir=tmp_path)
    assert summary["conflicts"] == [cid]
    assert frozen_path.read_bytes() == frozen_bytes  # frozen WINS

    with pytest.raises(CorpusWriteConflict):
        write_corpus([mutated], corpus_dir=tmp_path, strict=True)


def test_manifest_indexes_full_corpus_across_partial_harvests(tmp_path):
    write_corpus(extract_corrections(ledger=[_edited_row("s-1")]),
                 corpus_dir=tmp_path)
    summary = write_corpus(extract_corrections(ledger=[_rejected_row("s-2")]),
                           corpus_dir=tmp_path)
    # Second (partial) harvest must not shrink the manifest.
    assert summary["total_on_disk"] == 2
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert m["case_count"] == 2
    assert m["kinds"] == {"edit": 1, "skip": 1}
    assert m["fingerprint"] == corpus_fingerprint(m["case_ids"])
    assert m["case_ids"] == sorted(m["case_ids"])
    assert "computed_at" not in m and "generated_at" not in m  # no timestamps


# ---------------------------------------------------------------------------
# CLI smoke (subprocess, explicitly fenced env)
# ---------------------------------------------------------------------------

def _fenced_env(ledger_dir: Path) -> dict:
    env = dict(os.environ)
    env["CABINET_EVENT_LOG_DIR"] = str(ledger_dir)
    return env


def test_cli_harvests_from_fenced_ledger(tmp_path):
    ledger_dir = tmp_path / "events"
    ledger_dir.mkdir()
    rows = [_edited_row("cli-edit"), _rejected_row("cli-skip"),
            _row(subject="cli-appr",
                 proposal={"required": True, "decision": "approved",
                           "decided_at": "2026-07-03T21:08:55Z"},
                 outcome={"status": "ok", "evidence": "ok"},
                 review={"verdict": "confirmed", "source": "verdict_human"})]
    with open(ledger_dir / "consequence-events-2026-07-03.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    corpus_dir = tmp_path / "corpus"
    proc = subprocess.run(
        [sys.executable, str(CLI), "--corpus-dir", str(corpus_dir), "--json"],
        env=_fenced_env(ledger_dir), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["total_on_disk"] == 2          # approved row NOT harvested
    assert out["kinds"] == {"edit": 1, "skip": 1}
    assert len(list((corpus_dir / "cases").glob("case-*.json"))) == 2

    # Re-run: idempotent, still exit 0, nothing new.
    proc2 = subprocess.run(
        [sys.executable, str(CLI), "--corpus-dir", str(corpus_dir), "--json"],
        env=_fenced_env(ledger_dir), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc2.returncode == 0, proc2.stderr
    assert json.loads(proc2.stdout)["written"] == []


def test_cli_exits_3_on_frozen_conflict(tmp_path):
    ledger_dir = tmp_path / "events"
    ledger_dir.mkdir()
    row = _edited_row("cli-frozen")
    with open(ledger_dir / "consequence-events-2026-07-03.jsonl", "w") as f:
        f.write(json.dumps(row) + "\n")
    corpus_dir = tmp_path / "corpus"

    proc = subprocess.run(
        [sys.executable, str(CLI), "--corpus-dir", str(corpus_dir)],
        env=_fenced_env(ledger_dir), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr

    # Mutate the LEDGER row in place (append-only violation) -> regenerated
    # case now disagrees with the frozen file -> exit 3, frozen file kept.
    row["outcome"]["evidence"] = "history rewritten"
    with open(ledger_dir / "consequence-events-2026-07-03.jsonl", "w") as f:
        f.write(json.dumps(row) + "\n")
    frozen = next((corpus_dir / "cases").glob("case-*.json")).read_bytes()
    proc2 = subprocess.run(
        [sys.executable, str(CLI), "--corpus-dir", str(corpus_dir)],
        env=_fenced_env(ledger_dir), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc2.returncode == 3
    assert "FROZEN-CONFLICT" in proc2.stderr
    assert next((corpus_dir / "cases").glob("case-*.json")).read_bytes() == frozen
