"""Phase-1 external anchoring: the restore drill and the digest-anchor trial.

Pins the whole-cabinet evidence design (2026-07-16) Phase-1 items 5+6 and the
phase gate's named drill: "a store copy restored to an earlier state in a
sandbox fails verification against the external anchor". The in-store
verifier cannot prove absence (its documented anti-rollback residual); these
tests prove the exported anchor record catches rollback, tip divergence,
watermark deletion, and unreceipted trial deletion — while legitimate
Captain purges stay clean. Also pins the daily digest-anchor event's
redaction safety and the anchor CLI's credless-safe skips.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from framework import evidence_anchor
from framework.evidence.recorder import EvidenceRecorder
from framework.evidence.verifier import verify_trial

ROOT = Path(__file__).resolve().parents[2]


def _seed(store: Path, trial: str = "evt-demo-20260101", events: int = 2) -> EvidenceRecorder:
    recorder = EvidenceRecorder(store)
    context = recorder.trace(trial, surface="system")
    for index in range(events):
        recorder.append(
            context,
            phase="system",
            status="succeeded",
            actor={"kind": "system", "id": "anchor-test"},
            component={"name": "anchor-test", "version": "1"},
            detail={"action": "seed", "index": index},
        )
    return recorder


def test_collect_anchor_matches_the_store_tip(tmp_path: Path):
    store = tmp_path / "store"
    _seed(store, events=3)
    record = evidence_anchor.collect_anchor(store)
    assert record["schema"] == evidence_anchor.ANCHOR_RECORD_SCHEMA
    assert record["store_present"] is True
    entry = record["trials"]["evt-demo-20260101"]
    anchor = json.loads((store / "trials" / "evt-demo-20260101" / "anchor.json").read_text())
    assert entry["sequence"] == anchor["sequence"] == 3
    assert entry["event_hash"] == anchor["event_hash"]
    assert record["watermarks"]["present"] is True and record["watermarks"]["rows"]
    assert record["control"]["present"] is True and record["control"]["sha256"]
    assert record["record_digest"] and len(record["record_digest"]) == 64
    # Content-free: no event payload text ever rides the export.
    assert "seed" not in json.dumps(record)


def test_restore_drill_rollback_is_caught_by_the_external_anchor(tmp_path: Path):
    """THE Phase-1 gate drill: restore an older copy of the WHOLE store
    (events + tip anchors + watermark sidecar together — locally consistent,
    so the in-store verifier is green) and the external anchor still
    catches it."""
    store = tmp_path / "store"
    recorder = _seed(store, events=2)
    snapshot = tmp_path / "snapshot"
    shutil.copytree(store, snapshot)

    context = recorder.trace("evt-demo-20260101", surface="system")
    for index in range(2):
        recorder.append(
            context,
            phase="system",
            status="succeeded",
            actor={"kind": "system", "id": "anchor-test"},
            component={"name": "anchor-test", "version": "1"},
            detail={"action": "grow", "index": index},
        )
    exported = evidence_anchor.collect_anchor(store)
    assert exported["trials"]["evt-demo-20260101"]["sequence"] == 4

    # The locally-consistent restore the verifier cannot prove:
    shutil.rmtree(store)
    shutil.copytree(snapshot, store)
    assert verify_trial(store, "evt-demo-20260101")["ok"] is True, (
        "sanity: the restored copy must be locally green — that is the residual"
    )

    result = evidence_anchor.check_anchor(store, exported)
    assert result["ok"] is False
    kinds = {finding["kind"] for finding in result["findings"]}
    assert "trial_rollback" in kinds
    rollback = next(f for f in result["findings"] if f["kind"] == "trial_rollback")
    assert rollback["anchored_sequence"] == 4 and rollback["current_sequence"] == 2


def test_watermark_sidecar_deletion_is_caught(tmp_path: Path):
    store = tmp_path / "store"
    _seed(store)
    exported = evidence_anchor.collect_anchor(store)
    assert exported["watermarks"]["present"] is True
    (store / evidence_anchor.WATERMARK_NAME).unlink()
    result = evidence_anchor.check_anchor(store, exported)
    assert result["ok"] is False
    assert {"kind": "watermark_sidecar_missing"} in result["findings"]


def test_legitimate_purge_is_clean_but_unreceipted_deletion_is_not(tmp_path: Path):
    store = tmp_path / "store"
    recorder = _seed(store, trial="evt-purgeme-20260101")
    _seed(store, trial="evt-deleteme-20260102")
    exported = evidence_anchor.collect_anchor(store)

    recorder.purge_trial(
        "evt-purgeme-20260101",
        confirmation="PURGE evt-purgeme-20260101",
        actor="captain",
    )
    result = evidence_anchor.check_anchor(store, exported)
    assert result["ok"] is True, (
        "a Captain purge leaves a signed receipt; the external anchor must "
        "honor it instead of paging"
    )

    shutil.rmtree(store / "trials" / "evt-deleteme-20260102")
    result = evidence_anchor.check_anchor(store, exported)
    kinds = {finding["kind"] for finding in result["findings"]}
    assert "trial_missing" in kinds

    # Purge receipts are forever: removing one is itself a finding.
    exported_after_purge = evidence_anchor.collect_anchor(store)
    receipt = next(iter((store / "purge-receipts").glob("purge-*.json")))
    receipt.unlink()
    result = evidence_anchor.check_anchor(store, exported_after_purge)
    kinds = {finding["kind"] for finding in result["findings"]}
    assert "purge_receipt_missing" in kinds


def test_first_run_without_a_previous_record_is_ok(tmp_path: Path):
    store = tmp_path / "store"
    _seed(store)
    result = evidence_anchor.check_anchor(store, None)
    assert result == {"ok": True, "first_run": True, "findings": [], "checked_trials": 0}


def test_captain_label_digests_ride_the_record(tmp_path: Path):
    store = tmp_path / "store"
    _seed(store)
    label = tmp_path / "captain-vetoes.yml"
    label.write_text("vetoes: []\n", encoding="utf-8")
    record = evidence_anchor.collect_anchor(
        store,
        label_files={"captain-vetoes.yml": label, "captain-decisions.md": tmp_path / "absent.md"},
    )
    digest = hashlib.sha256(label.read_bytes()).hexdigest()
    assert record["captain_labels"]["captain-vetoes.yml"] == digest
    assert record["captain_labels"]["captain-decisions.md"] is None
    changed = evidence_anchor.collect_anchor(
        store, label_files={"captain-vetoes.yml": label}
    )
    label.write_text("vetoes: [one]\n", encoding="utf-8")
    later = evidence_anchor.collect_anchor(store, label_files={"captain-vetoes.yml": label})
    assert evidence_anchor.informational_changes(changed, later) == ["captain_labels_changed"]


def test_digest_anchor_trial_appends_verifies_and_redacts_nothing(tmp_path: Path):
    store = tmp_path / "store"
    ledger_dir = tmp_path / "ledgers"
    ledger_dir.mkdir()
    org = ledger_dir / "events-2026-07-15.jsonl"
    org.write_text('{"event_type":"session_started"}\n{"event_type":"session_ended"}\n')
    consequence = ledger_dir / "consequence-events-2026-07-15.jsonl"
    consequence.write_text('{"action_type":"demo"}\n')
    triggers = tmp_path / "archive" / "triggers"
    triggers.mkdir(parents=True)
    (triggers / "cabinet-triggers-cos.jsonl").write_text('{"verb":"wake"}\n')

    detail = evidence_anchor.build_digest_detail(
        ledger_date="2026-07-15",
        org_events_file=org,
        consequence_file=consequence,
        trigger_archive_dir=triggers,
    )
    assert detail["ledgers"]["org_events"]["lines"] == 2
    assert detail["ledgers"]["org_events"]["file"] == "events-2026-07-15.jsonl"
    assert detail["ledgers"]["consequence"]["sha256"] == hashlib.sha256(
        consequence.read_bytes()
    ).hexdigest()
    assert detail["ledgers"]["trigger_archive"]["files"] == 1

    event = evidence_anchor.append_digest_trial(store, detail, run_date="2026-07-16")
    assert event["trial_id"] == "evt-digest-anchor-20260716"
    assert event["phase"] == "system" and event["status"] == "succeeded"
    assert event["redactions"] == [], (
        "every digest key/value must survive sanitize untouched — a redacted "
        "field here means a key collided with the secret-key family or a "
        "value carried an absolute path"
    )
    assert event["detail"] == detail, "stored detail must be byte-identical to the input"
    assert verify_trial(store, "evt-digest-anchor-20260716")["ok"] is True

    # Absent ledgers are honest absences, not errors (absence != health —
    # the reconciler keys on these rows later).
    sparse = evidence_anchor.build_digest_detail(
        ledger_date="2026-07-14",
        org_events_file=ledger_dir / "events-2026-07-14.jsonl",
        consequence_file=ledger_dir / "consequence-events-2026-07-14.jsonl",
        trigger_archive_dir=tmp_path / "nowhere",
    )
    assert sparse["ledgers"]["org_events"] == {"present": False}
    assert sparse["ledgers"]["trigger_archive"] == {"present": False}


def test_receipt_text_is_aggregate_only_plain_english(tmp_path: Path):
    store = tmp_path / "store"
    _seed(store)
    record = evidence_anchor.collect_anchor(store)
    check = evidence_anchor.check_anchor(store, record)
    text = evidence_anchor.receipt_text(
        record,
        check,
        run_date="2026-07-16",
        digest_event="evt-digest-anchor-20260716",
        exported=["meta-repo"],
        skipped=[],
        notes=["control_changed"],
    )
    assert "2026-07-16" in text and "meta-repo" in text
    assert "evt-demo-20260101" not in text, "receipts carry aggregates, never trial ids"
    for jargon in ("germline", "schg", "FW-", "CG-"):
        assert jargon not in text, "Captain-facing receipts stay plain English"


# --- the CLI (cabinet/scripts/evidence-anchor.py) ---

def _load_cli():
    path = ROOT / "cabinet" / "scripts" / "evidence-anchor.py"
    spec = importlib.util.spec_from_file_location("evidence_anchor_cli", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def _credless(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """No Telegram identity, no anchor config, sandboxed ledger dirs — the
    fresh-deployment posture every surface must skip cleanly under."""
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_COS_TOKEN", "CAPTAIN_TELEGRAM_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "no-ledgers"))
    monkeypatch.setenv("CABINET_EXHAUST_ARCHIVE_DIR", str(tmp_path / "no-archive"))


def test_cli_credless_run_skips_every_surface_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture, _credless
):
    store = tmp_path / "store"
    _seed(store)
    cli = _load_cli()
    code = cli.main(["--store", str(store), "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    assert code == 0
    assert out["digest_event"].startswith("evt-digest-anchor-")
    assert out["exported"] == []
    assert any("anchor_dir unset" in item for item in out["skipped"])
    assert out["telegram"] == "skipped-unconfigured"
    assert out["findings"] == []
    # The digest event really landed in the store.
    assert verify_trial(store, out["digest_event"])["ok"] is True


def test_cli_dry_run_touches_nothing(tmp_path: Path, capsys: pytest.CaptureFixture, _credless):
    store = tmp_path / "store"
    _seed(store)
    before = sorted(p.name for p in (store / "trials").iterdir())
    cli = _load_cli()
    code = cli.main(["--store", str(store), "--dry-run", "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    assert code == 0 and out["digest_event"] == "skipped-dry-run"
    assert sorted(p.name for p in (store / "trials").iterdir()) == before


def test_cli_check_mode_is_the_restore_drill_teeth(
    tmp_path: Path, capsys: pytest.CaptureFixture, _credless
):
    store = tmp_path / "store"
    recorder = _seed(store, events=2)
    snapshot = tmp_path / "snapshot"
    shutil.copytree(store, snapshot)
    context = recorder.trace("evt-demo-20260101", surface="system")
    recorder.append(
        context,
        phase="system",
        status="succeeded",
        actor={"kind": "system", "id": "anchor-test"},
        component={"name": "anchor-test", "version": "1"},
        detail={"action": "grow"},
    )
    exported_file = tmp_path / "evidence-anchors.jsonl"
    record = evidence_anchor.collect_anchor(store)
    exported_file.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    cli = _load_cli()
    code = cli.main(["--store", str(store), "--check", str(exported_file)])
    assert code == 0 and json.loads(capsys.readouterr().out.strip())["ok"] is True

    shutil.rmtree(store)
    shutil.copytree(snapshot, store)
    code = cli.main(["--store", str(store), "--check", str(exported_file)])
    out = json.loads(capsys.readouterr().out.strip())
    assert code == 2 and out["ok"] is False
    assert {f["kind"] for f in out["findings"]} >= {"trial_rollback"}
