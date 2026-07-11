"""Tests — Design C v0: the judge-calibration human-side writer.

Covers the contract from judge-calibration-pairing-proposal-2026-07-11 §3:
  * build_case_labeled mirrors build_case_scored's shape, rides the DEDICATED
    judge-calibration lane (hard-coded — promotion-fuel isolation), stamps
    review.source=verdict_human, and is never sim.
  * THE POINT: collect_pairs() pairs a verdict_judge scored row with a
    verdict_human labeled row on the same case_id — the stream that was
    structurally 0-pairs before this writer existed.
  * Anti-anchoring: the CLI presentation never contains a judge-derived field.
  * Inert by construction: --dry-run writes nothing; non-TTY interactive is
    refused; labels land only on an explicit c/w answer.

Ledger-writing tests point CABINET_EVENT_LOG_DIR at a per-test tmp dir
(monkeypatch) on top of the repo-root session fence; the live ledger is never
touched. No retro/vault dependency: the CLI's content loader is stubbed out.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from framework.fidelity.consequence import validate_consequence
from framework.fidelity.fidelity_events import (
    LABEL_ACTION,
    LABEL_LANE,
    build_case_labeled,
    build_case_scored,
    emit_case_labeled,
    emit_case_scored,
)
from framework.fidelity.judge_calibration import collect_pairs, iter_raw_rows

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / "cabinet" / "scripts" / "label-fidelity-cases.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("label_fidelity_cases", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeScore:
    """Minimal CaseScore stand-in for build_case_scored (duck-typed)."""

    def __init__(self, case_id, intent_verdict="intent-divergent",
                 decision_verdict="divergent"):
        self.case_id = case_id
        self.intent_verdict = intent_verdict
        self.decision_verdict = decision_verdict
        self.intent_composite = 0.4
        self.intent_grounded_fact = "From X at 2026-06-20: excerpt"
        self.endorsement_adjusted = False


# ---------------------------------------------------------------------------
# builder shape / lane / no-sim
# ---------------------------------------------------------------------------

def test_build_case_labeled_shape_mirrors_scored():
    ev = build_case_labeled("4916e1d0d2", "wrong", "cos")
    assert ev["action"] == LABEL_ACTION == "fidelity-case-labeled"
    assert ev["subject"] == "4916e1d0d2"
    assert ev["refs"] == ["4916e1d0d2"]
    assert ev["lane"] == LABEL_LANE == "judge-calibration"
    assert ev["actor"] == {"kind": "officer", "id": "cos"}
    assert ev["review"] == {"verdict": "wrong", "source": "verdict_human"}
    assert ev["proposal"] == {"required": False}
    assert ev["outcome"]["status"] == "ok" and ev["outcome"]["evidence"]
    assert "sim" not in ev  # NEVER sim
    validate_consequence(ev)  # schema-legal, would emit cleanly

    # Same top-level shape family as the judge-side builder (minus the
    # scorer-axis extras) — the two sides of a pair are structurally kin.
    scored = build_case_scored(_FakeScore("4916e1d0d2"), "cos",
                               "send-1to1-reply")
    assert set(ev) <= set(scored)
    assert ev["subject"] == scored["subject"]  # the native pairing key


def test_build_case_labeled_reviewed_at_and_evidence():
    ev = build_case_labeled("abc123", "confirmed", "cos",
                            evidence="labeled in session 2026-07-11",
                            reviewed_at="2026-07-11T10:00:00Z")
    assert ev["review"]["reviewed_at"] == "2026-07-11T10:00:00Z"
    assert ev["outcome"]["evidence"] == "labeled in session 2026-07-11"
    validate_consequence(ev)


@pytest.mark.parametrize("bad", ["unknown", "", "ok", "skip", None])
def test_build_case_labeled_rejects_non_label_verdicts(bad):
    with pytest.raises(ValueError):
        build_case_labeled("abc123", bad, "cos")


def test_label_lane_is_hardcoded_not_a_parameter():
    # Mitigation 1 (promotion-fuel isolation) is structural: no caller can
    # aim a label's confirmed-fuel at an acting lane's cell.
    assert "lane" not in inspect.signature(build_case_labeled).parameters
    assert "lane" not in inspect.signature(emit_case_labeled).parameters


def test_emit_case_labeled_refuses_sim_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_SIM_MODE", "1")
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="sim"):
        emit_case_labeled("abc123", "confirmed", "cos")
    assert list(tmp_path.iterdir()) == []  # refused BEFORE any write


# ---------------------------------------------------------------------------
# THE POINT — pairing: a judge row + a label row on the same case_id
# ---------------------------------------------------------------------------

def test_pairing_fixture_in_memory_scored_plus_labeled():
    judge_row = build_case_scored(_FakeScore("4916e1d0d2"), "cos",
                                  "send-1to1-reply")
    # The frozen-flywheel state this build fixes: judge rows alone = 0 pairs.
    assert collect_pairs(rows=[judge_row]) == []
    label_row = build_case_labeled("4916e1d0d2", "wrong", "cos")
    pairs = collect_pairs(rows=[judge_row, label_row])
    assert len(pairs) == 1
    p = pairs[0]
    assert p["subject"] == "4916e1d0d2"
    assert p["judge"] == "wrong"      # intent-divergent -> wrong
    assert p["human"] == "wrong"
    assert p["agree"] is True


def test_pairing_disagreement_measured_not_manufactured():
    judge_row = build_case_scored(_FakeScore("c-dis"), "cos",
                                  "send-1to1-reply")
    label_row = build_case_labeled("c-dis", "confirmed", "cos")
    pairs = collect_pairs(rows=[judge_row, label_row])
    assert len(pairs) == 1 and pairs[0]["agree"] is False


def test_pairing_end_to_end_through_the_ledger(tmp_path, monkeypatch):
    """Full loop on disk: emit a scored (judge) row + a labeled (human) row
    through the real emitters into a fenced ledger dir, then collect_pairs()
    reads pairs>0 where the judge row alone gave 0 — the 17 banked judge rows
    become pairable exactly this way."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    emit_case_scored(_FakeScore("e2e-case-1"), "cos", "send-1to1-reply")
    assert collect_pairs() == []          # judge side only: still frozen
    emit_case_labeled("e2e-case-1", "wrong", "cos")
    pairs = collect_pairs()
    assert len(pairs) == 1
    assert pairs[0]["subject"] == "e2e-case-1" and pairs[0]["agree"] is True
    # Both rows really live on the consequence ledger (raw reader sees 2).
    raws = [r for r in iter_raw_rows() if r["subject"] == "e2e-case-1"]
    assert {r["action"] for r in raws} == {"fidelity-case-scored",
                                           "fidelity-case-labeled"}
    # The label row rides the dedicated lane; the judge row keeps its own.
    lanes = {r["action"]: r["lane"] for r in raws}
    assert lanes["fidelity-case-labeled"] == LABEL_LANE
    assert lanes["fidelity-case-scored"] == "send-1to1-reply"


def test_sim_labels_never_pair_even_if_forged_on_disk(tmp_path, monkeypatch):
    """Defense in depth: even a hand-forged sim label row on the ledger is
    dropped by the raw reader (SIE-7), so it can never manufacture a pair."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    judge = build_case_scored(_FakeScore("c-sim"), "cos", "send-1to1-reply")
    forged = build_case_labeled("c-sim", "confirmed", "cos")
    forged["sim"] = True
    with open(tmp_path / "consequence-events-2026-07-11.jsonl", "w") as f:
        f.write(json.dumps(judge) + "\n")
        f.write(json.dumps(forged) + "\n")
    assert collect_pairs() == []


# ---------------------------------------------------------------------------
# CLI — candidates, sampling, anti-anchoring, inertness
# ---------------------------------------------------------------------------

def _scored_row(case_id, verdict="wrong", ts="2026-07-10T06:45:00Z"):
    iv = "intent-divergent" if verdict == "wrong" else "intent-aligned"
    return {
        "ts": ts,
        "actor": {"kind": "officer", "id": "cos"},
        "lane": "send-1to1-reply",
        "action": "fidelity-case-scored",
        "subject": case_id,
        "refs": [case_id],
        "proposal": {"required": False},
        "outcome": {"status": "ok",
                    "evidence": f"intent={iv} composite=0.4"},
        "review": {"verdict": verdict, "source": "verdict_judge"},
        "decision_verdict": "divergent" if verdict == "wrong" else "match",
        "intent_verdict": iv,
        "intent_composite": 0.4,
        "endorsement": "constrained",
    }


def test_collect_candidates_latest_scored_only_and_labeled_set():
    cli = _load_cli()
    rows = [
        _scored_row("c1", "wrong", ts="2026-07-01T10:00:00Z"),
        _scored_row("c1", "confirmed", ts="2026-07-10T10:00:00Z"),  # latest
        _scored_row("c2", "wrong"),
        _scored_row("old", "wrong", ts="2026-05-01T10:00:00Z"),  # pre-since
        build_case_labeled("c2", "wrong", "cos"),                # human row
    ]
    cands, labeled = cli.collect_candidates(rows=rows, since="2026-06-01")
    assert [c["subject"] for c in cands] == ["c1", "c2"]
    by_id = {c["subject"]: c for c in cands}
    assert by_id["c1"]["review"]["verdict"] == "confirmed"  # latest wins
    assert labeled == {"c2"}


def test_stratified_sample_proportional_on_the_live_shape():
    # The live 2026-07-10 batch shape: 15 wrong / 2 confirmed. A 10-sample
    # must keep both strata (never "disagreements only" — mitigation 3) at
    # proportional weight.
    import random as _random
    cli = _load_cli()
    cands = ([_scored_row(f"w{i}", "wrong") for i in range(15)]
             + [_scored_row(f"k{i}", "confirmed") for i in range(2)])
    sample = cli.stratified_sample(cands, 10, _random.Random(7))
    assert len(sample) == 10
    verdicts = [(c["review"]["verdict"]) for c in sample]
    assert verdicts.count("confirmed") >= 1
    assert verdicts.count("wrong") >= 8


def test_stratified_sample_shuffles_presentation_order():
    # Balanced strata + pinned seed (Random(seed) is stable/deterministic):
    # the presented order must interleave strata, never block them — order
    # itself would otherwise leak the hidden judge verdict (mitigation 2).
    import random as _random
    cli = _load_cli()
    cands = ([_scored_row(f"w{i}", "wrong") for i in range(8)]
             + [_scored_row(f"k{i}", "confirmed") for i in range(8)])
    sample = cli.stratified_sample(cands, 10, _random.Random(3))
    verdicts = [(c["review"]["verdict"]) for c in sample]
    assert verdicts.count("confirmed") == 5 and verdicts.count("wrong") == 5
    assert verdicts != sorted(verdicts) and verdicts != sorted(
        verdicts, reverse=True)


def test_presentation_hides_every_judge_derived_field():
    cli = _load_cli()
    row = _scored_row("c-anchor", "wrong")
    text = cli.present_case(row, content={
        "person": "Tomás", "channel": "email",
        "reply_ts": "2026-03-14T09:22:00Z",
        "thread_before": [{"date": "2026-03-14", "who": "Tomás",
                           "text": "Can we ship it?", "direction": "recv"}],
        "real_reply": "Yes — ship it after the VAT check.",
    })
    lowered = text.lower()
    # The judge's verdict + every derived field stays invisible (mitigation 2).
    assert "wrong" not in lowered
    assert "confirmed" not in lowered
    assert "intent-divergent" not in lowered
    assert "intent" not in lowered.replace("officer decision text", "")
    assert "divergent" not in lowered
    assert "composite" not in lowered
    assert "constrained" not in lowered
    assert "verdict_judge" not in lowered
    # ...while the case substance IS shown.
    assert "c-anchor" in text and "ship it" in text
    # And the metadata-only fallback is equally clean.
    bare = cli.present_case(row, content=None).lower()
    assert "wrong" not in bare and "divergent" not in bare


def test_redaction_set_pins_all_judge_fields():
    cli = _load_cli()
    for f in ("review", "outcome", "intent_verdict", "decision_verdict",
              "intent_composite", "endorsement"):
        assert f in cli.REDACTED_FIELDS


def test_dry_run_writes_nothing_and_leaks_no_verdict(tmp_path):
    ledger = tmp_path / "events"
    ledger.mkdir()
    seed_file = ledger / "consequence-events-2026-07-10.jsonl"
    with open(seed_file, "w") as f:
        for i in range(3):
            f.write(json.dumps(_scored_row(f"case{i}", "wrong")) + "\n")
        f.write(json.dumps(_scored_row("case3", "confirmed")) + "\n")
    before = {p.name: p.read_bytes() for p in ledger.iterdir()}

    env = dict(os.environ, CABINET_EVENT_LOG_DIR=str(ledger))
    env.pop("CABINET_SIM_MODE", None)
    proc = subprocess.run(
        [sys.executable, str(CLI), "--dry-run", "--sample", "3", "--seed", "7"],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "DRY RUN" in out and "case" in out
    assert "may_demote stays False" in out          # deliverable 3: the banner
    assert "HANDBACK #13" in out
    # No judge verdicts leak into the listing (anti-anchoring in dry-run too).
    assert "intent-divergent" not in out and "divergent" not in out
    # Nothing written: same files, same bytes.
    after = {p.name: p.read_bytes() for p in ledger.iterdir()}
    assert after == before


def test_interactive_refused_when_stdin_not_a_tty(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    cli = _load_cli()
    (tmp_path / "consequence-events-2026-07-10.jsonl").write_text(
        json.dumps(_scored_row("c1", "wrong")) + "\n")

    def _never_called(prompt):  # pragma: no cover - the assertion IS the test
        raise AssertionError("prompted despite non-TTY stdin")

    class _Out:
        def __init__(self):
            self.text = ""

        def write(self, s):
            self.text += s

    out = _Out()
    rc = cli.main(argv=[], input_fn=_never_called, isatty=False, out=out)
    assert rc == 2
    assert "REFUSED" in out.text
    assert list(tmp_path.glob("consequence-events-*")) != []  # seed intact
    rows = [r for r in iter_raw_rows() if r["action"] == "fidelity-case-labeled"]
    assert rows == []  # nothing minted


def test_interactive_answers_emit_labels_and_create_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with open(tmp_path / "consequence-events-2026-07-10.jsonl", "w") as f:
        for i in range(3):
            f.write(json.dumps(_scored_row(f"case{i}", "wrong")) + "\n")

    cli = _load_cli()
    cli.load_case_content = lambda ids: {}  # no vault dependency in tests
    answers = iter(["c", "w", "s"])

    class _Out:
        def write(self, s):
            pass

    rc = cli.main(argv=["--sample", "0", "--seed", "1"],
                  input_fn=lambda prompt: next(answers), isatty=True,
                  out=_Out())
    assert rc == 0
    labels = [r for r in iter_raw_rows()
              if r["action"] == "fidelity-case-labeled"]
    assert len(labels) == 2                      # skip wrote nothing
    assert {r["review"]["verdict"] for r in labels} == {"confirmed", "wrong"}
    assert all(r["lane"] == LABEL_LANE for r in labels)
    assert all(r["review"]["source"] == "verdict_human" for r in labels)
    assert all("sim" not in r for r in labels)
    # The labels pair with the seeded judge rows immediately.
    assert len(collect_pairs()) == 2
