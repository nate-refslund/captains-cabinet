"""End-to-end join: a Captain label lands via the CLI ritual and RENDERS on
every Phase-3 read surface (design §3 Phase 3; seam test for the review
surface batch).

The chain under test, on one scratch store:

  governance-review.py CLI (token-gated, TTY, scripted Captain)
      └─ verdict_human verification(+outcome) events on the judged trial
           ├─ G1 cross-trial query plane: `project by-actor:captain` (and the
           │  by-component / by-status forms) serves the trial with the label
           │  records — verification-gated, redacted, banner intact;
           ├─ G1 single-trial projection serves the same label records; and
           ├─ the officer projection redaction holds: of the label's detail
           │  keys only the allow-listed pair (action, result_code) is
           │  served; source/basis/jid/session/note stay officer-opaque.

  (The dashboard read-model half of this join — the SAME store shape read by
  readEvidence() rendering basis 'human-verified' — is the vitest twin
  cabinet/dashboard/src/lib/evidence/label-join.e2e.test.ts, which drives
  THIS same CLI path via a spawned python3.12 fixture.)

READ-ONLY PROOF (the batch's core invariant): after the one designed write,
the ENTIRE Phase-3 read surface — cross-trial selectors, single-trial
projection, the evidence CLI `project` verb — leaves the store tree
byte-identical.  The only mutation in the whole flow is the Captain-token
label append itself.  Hermetic; synthetic Testburg vocabulary only.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence import __main__ as evidence_cli  # noqa: E402
from framework.evidence import query  # noqa: E402
from framework.evidence.recorder import EvidenceRecorder  # noqa: E402

_SCRIPT = Path(__file__).resolve().parents[1] / "governance-review.py"
_spec = importlib.util.spec_from_file_location("governance_review_join", _SCRIPT)
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)

_OFFICER = {"kind": "officer", "id": "tb-cos"}
_COMPONENT = {"name": "testburg-exec", "version": "1"}

# The label detail keys that ARE in the officer projection allow-list
# (recorder.PROJECTION_ALLOWED_DETAIL) vs the ones that must stay redacted.
_LABEL_DETAIL_SERVED = {"action", "result_code"}
_LABEL_DETAIL_REDACTED = {"source", "basis", "jid", "session", "note"}


def _seed_producer_trial(rec: EvidenceRecorder, trial_id: str) -> str:
    ctx = rec.trace(trial_id, surface="system")
    detail = {"action": "write_testburg_note", "jid": "j-tb-9"}
    rec.append(ctx, phase="intent", status="started", actor=_OFFICER,
               component=_COMPONENT, detail=detail)
    rec.append(ctx, phase="execution", status="succeeded", actor=_OFFICER,
               component=_COMPONENT, detail=detail)
    return trial_id


def _mint_token(store: Path, path: Path) -> Path:
    key = (store / ".signing-key").read_bytes()
    token = hmac.new(
        key, evidence_cli.CAPTAIN_TOKEN_PURPOSE.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    path.write_text(token + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _label_via_cli(store: Path, tmp_path: Path, answers: list[str]) -> str:
    token = _mint_token(store, tmp_path / "captain.token")
    feed = iter(answers)
    out = io.StringIO()
    rc = gr.main(
        ["--store", str(store), "--captain-token-file", str(token),
         "--skip-stations", "--seed", "7",
         "--labels-journal", str(tmp_path / "out" / "labels.jsonl"),
         "--transcript-dir", str(tmp_path / "out" / "reviews")],
        input_fn=lambda prompt: next(feed, "q"), isatty=True, out=out)
    assert rc == 0, out.getvalue()
    return out.getvalue()


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _served_records(result: dict, trial_id: str) -> list[dict]:
    for trial in result["trials"]:
        if trial["trial_id"] == trial_id:
            assert trial["verification"] == "verified"
            return trial["records"]
    raise AssertionError(f"{trial_id} not served: {json.dumps(result['counts'])}")


def _label_records(records: list[dict]) -> list[dict]:
    return [r for r in records
            if r.get("detail", {}).get("action") == gr.LABEL_ACTION]


def test_cli_label_renders_on_every_phase3_read_surface(tmp_path, capsys):
    store = tmp_path / "evidence"
    rec = EvidenceRecorder(store)
    tid = _seed_producer_trial(rec, "trial-tb-join-1")

    _label_via_cli(store, tmp_path, ["r", "clean Testburg join"])

    # A captain-less bystander lands AFTER the session: selectors must serve
    # the labeled trial only, never the bystander.
    _seed_producer_trial(rec, "trial-tb-bystander-1")

    reader = EvidenceRecorder(store)

    # --- G1 cross-trial selectors serve the labeled trial ------------------
    by_actor = query.selector_projection(reader, "by-actor:captain")
    labels = _label_records(_served_records(by_actor, tid))
    assert [(r["phase"], r["status"]) for r in labels] == [
        ("verification", "verified"), ("outcome", "succeeded")]
    # the label matched the selector via VERIFIED rows (actor kind captain),
    # and the bystander trial (no captain leg) is not served
    assert [t["trial_id"] for t in by_actor["trials"]] == [tid]
    assert by_actor["instruction_boundary"].startswith(
        "UNTRUSTED OBSERVATIONS ONLY")

    kind_qualified = query.selector_projection(reader, "by-actor:captain:captain")
    assert [t["trial_id"] for t in kind_qualified["trials"]] == [tid]

    by_component = query.selector_projection(reader, "by-component:governance-review")
    assert _label_records(_served_records(by_component, tid))

    by_status = query.selector_projection(reader, "by-status:verified")
    assert _label_records(_served_records(by_status, tid))

    # --- G1 single-trial projection serves the same records ----------------
    projection = reader.cabinet_projection(tid)
    single = _label_records(projection["records"])
    assert [r["event_id"] for r in single] == [r["event_id"] for r in labels]

    # --- officer-projection redaction of the label detail ------------------
    for record in labels + single:
        detail = record["detail"]
        assert _LABEL_DETAIL_SERVED <= set(detail)
        assert not (_LABEL_DETAIL_REDACTED & set(detail)), (
            "officer projection must never serve the redacted label keys")
        assert detail["result_code"] == "confirmed"
        assert record["trust"] == "untrusted_observation"
    assert "clean Testburg join" not in json.dumps(by_actor)

    # --- the CLI project verb (the doorway's exact entry) ------------------
    rc = evidence_cli.main(["--store", str(store), "project", "by-actor:captain"])
    assert rc == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert [t["trial_id"] for t in cli_payload["trials"]] == [tid]

    # --- READ-ONLY PROOF over the full surface -----------------------------
    # Ledger law first: NO read may ever touch stored event bytes.  The one
    # sanctioned read side effect is the verifier's signed anti-rollback
    # watermark sidecar advancing on a trial's FIRST verify (identical to
    # `python3.12 -m framework.evidence verify`; self-skipping at tip).
    def _full_read_surface() -> None:
        query.selector_projection(reader, "by-actor:captain")
        query.selector_projection(reader, "by-component:governance-review")
        query.selector_projection(reader, "by-status:verified")
        query.selector_projection(reader, "by-time:20200101-20991231")
        reader.cabinet_projection(tid)
        rc = evidence_cli.main(["--store", str(store), "project", tid])
        assert rc == 0
        capsys.readouterr()

    def _ledger_digest(tree: dict[str, str]) -> dict[str, str]:
        watermark_files = {".verify-watermarks.json", ".verify-watermarks.lock"}
        return {k: v for k, v in tree.items()
                if Path(k).name not in watermark_files}

    post_label = _tree_digest(store)
    _full_read_surface()          # covers the never-verified bystander too
    settled = _tree_digest(store)
    assert _ledger_digest(settled) == _ledger_digest(post_label), (
        "a Phase-3 read surface wrote NON-watermark store bytes — the "
        "batch's one designed write is the Captain-token label append")
    _full_read_surface()          # at rest: byte-identical, watermarks included
    assert _tree_digest(store) == settled, (
        "a repeated Phase-3 read pass changed store bytes — reads at tip "
        "must be byte-stable, watermark sidecar included")


def test_unclear_label_still_renders_and_stays_unscoreable(tmp_path):
    store = tmp_path / "evidence"
    rec = EvidenceRecorder(store)
    tid = _seed_producer_trial(rec, "trial-tb-join-unclear-1")

    _label_via_cli(store, tmp_path, ["u", ""])

    reader = EvidenceRecorder(store)
    result = query.selector_projection(reader, "by-actor:captain")
    labels = _label_records(_served_records(result, tid))
    # unclear: verification/skipped only — recorded, never scoreable
    assert [(r["phase"], r["status"]) for r in labels] == [
        ("verification", "skipped")]
    assert labels[0]["detail"]["result_code"] == "unclear"
