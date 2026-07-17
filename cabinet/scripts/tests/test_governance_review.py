"""governance-review.py — the RAMP-2 Captain labeling ritual (evidence Phase 3).

Pins the phase invariants:
  * read_only_held: the no-token, forged-token, non-TTY, and --dry-run paths
    leave the evidence store BYTE-IDENTICAL and create no journal/transcript;
  * the ONE designed write: a Captain verdict lands as verification(+outcome)
    events on THE SAME trial via the recorder API, actor kind captain,
    detail.source verdict_human, detail.action governance_review_label,
    result_code confirmed|wrong|unclear, basis-at-label-time, jid link;
  * MAX_LABELS_PER_SESSION is a code constant (8), not a flag, and the loop
    hard-stops at it;
  * fail-closed display: a tampered trial renders as explicit UNVERIFIED and
    can never be labeled;
  * blind labeling: machine-verdict events are hidden from the presentation;
  * per-label digests are content-free (no note text) and a session marker
    lands for the RAMP-5 flip condition.

Hermetic: every store is a tmp-dir EvidenceRecorder store; journal and
transcript paths are always tmp; the Captain token is minted from the tmp
store's own signing key (the real derivation, no mocks of the auth path).
Synthetic Testburg vocabulary only.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence.recorder import EvidenceRecorder  # noqa: E402

_SCRIPT = Path(__file__).resolve().parents[1] / "governance-review.py"
_spec = importlib.util.spec_from_file_location("governance_review", _SCRIPT)
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)

_OFFICER = {"kind": "officer", "id": "cos"}
_EXEC_COMPONENT = {"name": "testburg-exec", "version": "1"}
_SWEEP = {"kind": "system", "id": "undo-sweep"}
_SWEEP_COMPONENT = {"name": "undo-sweep", "version": "1"}


# ---------------------------------------------------------------------------
# fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch):
    monkeypatch.delenv("CABINET_CAPTAIN_TOKEN_FILE", raising=False)
    yield


def _seed_trial(rec, trial_id, *, kind="self", action="write_testburg_note",
                jid="j-tb-1"):
    """One synthetic trial per evidence-basis class."""
    ctx = rec.trace(trial_id, surface="system")
    base = {"action": action, "jid": jid}
    rec.append(ctx, phase="intent", status="started", actor=_OFFICER,
               component=_EXEC_COMPONENT, detail=base)
    rec.append(ctx, phase="execution", status="succeeded", actor=_OFFICER,
               component=_EXEC_COMPONENT, detail=base)
    if kind == "persistence":
        detail = {**base, "action": "undo_sweep_reconcile",
                  "result_code": "ttl_ok"}
        rec.append(ctx, phase="verification", status="verified", actor=_SWEEP,
                   component=_SWEEP_COMPONENT, detail=detail)
        rec.append(ctx, phase="outcome", status="succeeded", actor=_SWEEP,
                   component=_SWEEP_COMPONENT, detail=detail)
    elif kind == "machine":
        detail = {**base, "action": "undo_sweep_reconcile",
                  "result_code": "silent_revert", "source": "verdict_judge"}
        rec.append(ctx, phase="verification", status="unverified",
                   actor=_SWEEP, component=_SWEEP_COMPONENT, detail=detail)
        rec.append(ctx, phase="outcome", status="failed", actor=_SWEEP,
                   component=_SWEEP_COMPONENT, detail=detail)
    elif kind == "human":
        detail = {**base, "action": gr.LABEL_ACTION,
                  "source": "verdict_human", "result_code": "confirmed"}
        rec.append(ctx, phase="verification", status="verified",
                   actor={"kind": "captain", "id": "captain"},
                   component={"name": "governance-review", "version": "1"},
                   detail=detail)
    return trial_id


def _store(tmp_path, name="evidence"):
    store = tmp_path / name
    return store, EvidenceRecorder(store)


def _mint_token(store: Path, path: Path) -> Path:
    """The REAL token derivation (HMAC(store signing key, purpose)) — no
    mock; forged-token tests flip a byte of this."""
    key = (store / ".signing-key").read_bytes()
    token = hmac.new(key, gr.evidence_cli.CAPTAIN_TOKEN_PURPOSE.encode("utf-8"),
                     hashlib.sha256).hexdigest()
    path.write_text(token + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _tree_digest(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    return out


class _Script:
    """Scripted Captain input; exhaustion quits (mirrors EOF behavior)."""

    def __init__(self, answers):
        self.answers = list(answers)

    def __call__(self, prompt):
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


def _run(store, tmp_path, answers, *, token=None, extra=None, isatty=True):
    argv = ["--store", str(store), "--skip-stations", "--seed", "7",
            "--labels-journal", str(tmp_path / "out" / "labels.jsonl"),
            "--transcript-dir", str(tmp_path / "out" / "reviews")]
    if token is not None:
        argv += ["--captain-token-file", str(token)]
    argv += list(extra or [])
    import io
    out = io.StringIO()
    rc = gr.main(argv, input_fn=_Script(answers), isatty=isatty, out=out)
    return rc, out.getvalue(), tmp_path / "out"


def _journal_rows(outdir: Path):
    path = outdir / "labels.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# the read-only invariant: refused paths mutate NOTHING
# ---------------------------------------------------------------------------

def test_no_token_refused_before_any_store_access(tmp_path):
    store, rec = _store(tmp_path)
    _seed_trial(rec, "trial-tb-selfassert-1")
    before = _tree_digest(store)
    rc, text, outdir = _run(store, tmp_path, ["r", ""], token=None)
    assert rc == 3
    assert "captain_capability_required" in text
    assert _tree_digest(store) == before          # store byte-identical
    assert not (outdir / "labels.jsonl").exists()
    assert not (outdir / "reviews").exists()


def test_forged_token_refused_and_mutates_nothing(tmp_path):
    store, rec = _store(tmp_path)
    _seed_trial(rec, "trial-tb-selfassert-1")
    forged = tmp_path / "forged.token"
    forged.write_text("0" * 64 + "\n", encoding="utf-8")
    forged.chmod(0o600)
    before = _tree_digest(store)
    rc, text, outdir = _run(store, tmp_path, ["r", ""], token=forged)
    assert rc == 3
    assert "captain_capability_invalid" in text
    assert _tree_digest(store) == before
    assert not (outdir / "labels.jsonl").exists()


def test_non_tty_labeling_refused(tmp_path):
    store, rec = _store(tmp_path)
    _seed_trial(rec, "trial-tb-selfassert-1")
    token = _mint_token(store, tmp_path / "captain.token")
    before = _tree_digest(store)
    rc, text, outdir = _run(store, tmp_path, ["r", ""], token=token,
                            isatty=False)
    assert rc == 2
    assert "not a TTY" in text
    assert _tree_digest(store) == before
    assert not (outdir / "labels.jsonl").exists()


def test_dry_run_is_inert_and_lists_the_plan(tmp_path):
    store, rec = _store(tmp_path)
    _seed_trial(rec, "trial-tb-selfassert-1")
    _seed_trial(rec, "trial-tb-persist-1", kind="persistence")
    token = _mint_token(store, tmp_path / "captain.token")
    before = _tree_digest(store)
    rc, text, outdir = _run(store, tmp_path, [], token=token,
                            extra=["--dry-run"], isatty=False)
    assert rc == 0
    assert "DRY RUN" in text and "trial-tb-selfassert-1" in text
    assert "UNVERIFIED plan" in text              # honest fail-closed marking
    assert _tree_digest(store) == before          # no verify, no watermarks
    assert not (outdir / "labels.jsonl").exists()
    assert not (outdir / "reviews").exists()


def test_missing_store_is_an_honest_no_op(tmp_path):
    rc, text, outdir = _run(tmp_path / "nowhere", tmp_path, [])
    assert rc == 0
    assert "No evidence store" in text
    assert not (outdir / "labels.jsonl").exists()


# ---------------------------------------------------------------------------
# the ONE designed write: label events + exports
# ---------------------------------------------------------------------------

def test_right_label_lands_verification_and_outcome_on_same_trial(tmp_path):
    store, rec = _store(tmp_path)
    tid = _seed_trial(rec, "trial-tb-selfassert-1")
    token = _mint_token(store, tmp_path / "captain.token")
    rc, text, outdir = _run(store, tmp_path, ["r", "solid Testburg work"],
                            token=token)
    assert rc == 0
    events = EvidenceRecorder(store).read_events(tid)
    labels = [e for e in events
              if e["detail"].get("action") == gr.LABEL_ACTION]
    assert [e["phase"] for e in labels] == ["verification", "outcome"]
    assert [e["status"] for e in labels] == ["verified", "succeeded"]
    for event in labels:
        assert event["actor"] == {"kind": "captain", "id": "captain"}
        assert event["surface"] == "cli"
        detail = event["detail"]
        assert detail["source"] == "verdict_human"
        assert detail["result_code"] == "confirmed"
        assert detail["basis"] == "self_asserted"   # basis at label time
        assert detail["jid"] == "j-tb-1"
        assert detail["note"] == "solid Testburg work"
        assert event["links"] == ["undo-journal:j-tb-1"]
    # journal: one CONTENT-FREE digest + one session marker
    rows = _journal_rows(outdir)
    assert len(rows) == 2
    digest, marker = rows
    assert digest["schema"] == "cabinet.governance-label-digest/v1"
    assert digest["trial_id"] == tid
    assert digest["verdict"] == "confirmed"
    assert digest["basis"] == "self_asserted"
    assert digest["event_ids"] == [e["event_id"] for e in labels]
    assert digest["event_hashes"] == [e["event_hash"] for e in labels]
    raw = (outdir / "labels.jsonl").read_text(encoding="utf-8")
    assert "solid Testburg work" not in raw        # digests carry no content
    assert marker["kind"] == "session_complete" and marker["labels"] == 1
    # transcript: Captain-owned, OUTSIDE the store, carries the note
    transcripts = list((outdir / "reviews").glob("gr-*.md"))
    assert len(transcripts) == 1
    body = transcripts[0].read_text(encoding="utf-8")
    assert "solid Testburg work" in body and tid in body
    assert str(store) not in str(transcripts[0])   # not inside the store


def test_wrong_and_unclear_shapes(tmp_path):
    store, rec = _store(tmp_path)
    tid_w = _seed_trial(rec, "trial-tb-wrong-1")
    token = _mint_token(store, tmp_path / "captain.token")
    rc, _, _ = _run(store, tmp_path, ["w", ""], token=token)
    assert rc == 0
    labels = [e for e in EvidenceRecorder(store).read_events(tid_w)
              if e["detail"].get("action") == gr.LABEL_ACTION]
    assert [(e["phase"], e["status"]) for e in labels] == [
        ("verification", "unverified"), ("outcome", "failed")]
    assert all(e["detail"]["result_code"] == "wrong" for e in labels)

    store2, rec2 = _store(tmp_path, "evidence2")
    tid_u = _seed_trial(rec2, "trial-tb-unclear-1")
    token2 = _mint_token(store2, tmp_path / "captain2.token")
    rc, _, _ = _run(store2, tmp_path / "u", ["u", ""], token=token2)
    assert rc == 0
    labels = [e for e in EvidenceRecorder(store2).read_events(tid_u)
              if e["detail"].get("action") == gr.LABEL_ACTION]
    # unclear: recorded, never scoreable — verification/skipped, NO outcome
    assert [(e["phase"], e["status"]) for e in labels] == [
        ("verification", "skipped")]
    assert labels[0]["detail"]["result_code"] == "unclear"


def test_skip_and_quit_write_nothing(tmp_path):
    store, rec = _store(tmp_path)
    tid = _seed_trial(rec, "trial-tb-selfassert-1")
    _seed_trial(rec, "trial-tb-selfassert-2")
    token = _mint_token(store, tmp_path / "captain.token")
    rc, _, outdir = _run(store, tmp_path, ["s", "q"], token=token)
    assert rc == 0
    events = EvidenceRecorder(store).read_events(tid)
    assert not [e for e in events
                if e["detail"].get("action") == gr.LABEL_ACTION]
    rows = _journal_rows(outdir)
    assert len(rows) == 1                          # session marker only
    assert rows[0]["kind"] == "session_complete"
    assert rows[0]["labels"] == 0 and rows[0]["completed"] is False


def test_hard_cap_is_a_code_constant_and_the_loop_stops_at_it(tmp_path):
    assert gr.MAX_LABELS_PER_SESSION == 8
    # Pin the EXACT flag vocabulary: a bar someone can lower from argv is not
    # a bar, so any new flag — a cap override above all — must consciously
    # re-ratify this list.
    options = {opt for act in gr._build_parser()._actions
               for opt in act.option_strings}
    assert options == {"-h", "--help", "--store", "--captain-token-file",
                       "--seed", "--scan-cap", "--relabel", "--dry-run",
                       "--skip-stations", "--labels-journal",
                       "--transcript-dir"}
    store, rec = _store(tmp_path)
    for i in range(12):
        _seed_trial(rec, f"trial-tb-cap-{i:02d}")
    token = _mint_token(store, tmp_path / "captain.token")
    rc, text, outdir = _run(store, tmp_path, ["r", ""] * 16, token=token)
    assert rc == 0
    assert "label cap reached" in text
    digests = [r for r in _journal_rows(outdir)
               if r.get("schema") == "cabinet.governance-label-digest/v1"]
    assert len(digests) == gr.MAX_LABELS_PER_SESSION


# ---------------------------------------------------------------------------
# fail-closed display + blind presentation
# ---------------------------------------------------------------------------

def test_tampered_trial_renders_unverified_and_is_never_labeled(tmp_path):
    store, rec = _store(tmp_path)
    good = _seed_trial(rec, "trial-tb-good-1")
    bad = _seed_trial(rec, "trial-tb-tampered-1")
    ledger = store / "trials" / bad / "events.jsonl"
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            '"succeeded"', '"falsified"', 1), encoding="utf-8")
    token = _mint_token(store, tmp_path / "captain.token")
    rc, text, outdir = _run(store, tmp_path, ["s", "s"], token=token)
    assert rc == 0
    assert f"UNVERIFIED: {bad}" in text
    assert "excluded from labeling" in text
    # zero content from the tampered trial is served
    assert "falsified" not in text
    # and no label ever lands on it — the pool was skip-only for the good one
    raw = (store / "trials" / bad / "events.jsonl").read_text(encoding="utf-8")
    assert gr.LABEL_ACTION not in raw
    assert not [r for r in _journal_rows(outdir)
                if r.get("schema") == "cabinet.governance-label-digest/v1"]
    assert good  # good trial stayed presentable (skipped by script)


def test_presentation_hides_machine_verdicts_and_keeps_banner(tmp_path):
    store, rec = _store(tmp_path)
    tid = _seed_trial(rec, "trial-tb-machine-1", kind="machine",
                      action="external_email_send")
    raw = gr._read_raw_events(store, tid)
    cand = gr.classify_trial(raw)
    cand["trial_id"] = tid
    assert cand["basis"] == "machine_labeled" and cand["risk"] == "high"
    projection = EvidenceRecorder(store).cabinet_projection(tid)
    text = gr.present_trial(projection, cand)
    # the judge's verdict direction never reaches the Captain's eyes
    assert "silent_revert" not in text
    assert "verdict_judge" not in text
    assert "failed" not in text and "unverified" not in text
    assert "2 machine-verdict event(s) HIDDEN" in text
    # the untrusted-observations boundary stays on the served view
    assert "UNTRUSTED OBSERVATIONS ONLY" in text
    # the producer's own events remain visible
    assert "external_email_send" in text


# ---------------------------------------------------------------------------
# classification + sampling (pure functions)
# ---------------------------------------------------------------------------

def _ev(phase, status, *, actor_kind="system", detail=None, event_id="e-1"):
    return {"phase": phase, "status": status, "event_id": event_id,
            "actor": {"kind": actor_kind, "id": "x"},
            "component": {"name": "testburg-exec"},
            "detail": detail or {}}


def test_classify_trial_basis_ladder():
    execution = _ev("execution", "succeeded",
                    detail={"action": "write_testburg_note", "jid": "j-1"})
    assert gr.classify_trial([execution])["basis"] == "self_asserted"
    producer_verify = _ev("verification", "verified",
                          detail={"verification": "receipt_present"})
    assert gr.classify_trial(
        [execution, producer_verify])["basis"] == "self_asserted"
    ttl = _ev("verification", "verified",
              detail={"action": "undo_sweep_reconcile", "result_code": "ttl_ok"})
    assert gr.classify_trial([execution, ttl])["basis"] == "persistence_only"
    judged = _ev("verification", "unverified",
                 detail={"action": "undo_sweep_reconcile",
                         "result_code": "silent_revert",
                         "source": "verdict_judge"})
    assert gr.classify_trial(
        [execution, ttl, judged])["basis"] == "machine_labeled"
    captain = _ev("verification", "verified", actor_kind="captain",
                  detail={"source": "verdict_human"})
    assert gr.classify_trial(
        [execution, ttl, judged, captain])["basis"] == "human_verified"
    got = gr.classify_trial([execution, judged])
    assert got["jid"] == "j-1"
    assert got["machine_event_ids"] == {"e-1"}


def test_classify_trial_flags_high_risk():
    ev = _ev("execution", "succeeded", detail={"action": "external_email_send"})
    assert gr.classify_trial([ev])["risk"] == "high"
    ev = _ev("execution", "succeeded", detail={"action": "write_note"})
    assert gr.classify_trial([ev])["risk"] == "normal"


def test_stratified_sample_leans_weakest_and_pulls_high_risk_first():
    import random
    candidates = (
        [{"trial_id": f"sa-{i}", "basis": "self_asserted",
          "risk": "high" if i < 2 else "normal"} for i in range(10)]
        + [{"trial_id": f"po-{i}", "basis": "persistence_only",
            "risk": "normal"} for i in range(10)]
        + [{"trial_id": f"ml-{i}", "basis": "machine_labeled",
            "risk": "normal"} for i in range(10)]
    )
    sample = gr.stratified_sample(candidates, 8, random.Random(7))
    assert len(sample) == 8
    by_basis = {}
    for cand in sample:
        by_basis[cand["basis"]] = by_basis.get(cand["basis"], 0) + 1
    # weakest stratum gets the largest allocation; every stratum represented
    assert by_basis["self_asserted"] >= by_basis["persistence_only"] \
        >= by_basis["machine_labeled"] >= 1
    # the high-risk tail is drawn before normal rows of its stratum
    picked_sa = {c["trial_id"] for c in sample if c["basis"] == "self_asserted"}
    assert {"sa-0", "sa-1"} <= picked_sa
    # deterministic under a fixed seed
    again = gr.stratified_sample(candidates, 8, random.Random(7))
    assert [c["trial_id"] for c in again] == [c["trial_id"] for c in sample]


def test_human_verified_trials_excluded_unless_relabel(tmp_path):
    store, rec = _store(tmp_path)
    _seed_trial(rec, "trial-tb-human-1", kind="human")
    _seed_trial(rec, "trial-tb-fresh-1")
    fresh = gr.collect_candidates(store, scan_cap=50, relabel=False)
    assert [c["trial_id"] for c in fresh] == ["trial-tb-fresh-1"]
    everything = gr.collect_candidates(store, scan_cap=50, relabel=True)
    assert {c["trial_id"] for c in everything} == {
        "trial-tb-human-1", "trial-tb-fresh-1"}
