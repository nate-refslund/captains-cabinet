"""HP-3 — authenticated label channel + anchor re-count (whole-cabinet
evidence design 2026-07-16 §2.3 HP-3, §2.8 B1, §8 D1).

Pins, across the three HP-3 surfaces:
  * channel-provenance attestation on every label write: the TTY path
    records ``label_channel="captain-token+tty"`` in the signed event
    detail + the journal digest mirror; an unattestable context REFUSES
    fail-closed (typed, zero store bytes written);
  * the telegram channel is RESERVED: its resolver attests only against
    the platform.yml ``captain_telegram_chat_id`` allowlist and refuses
    when unconfigured (dark default — the TTY ritual always works), and
    the chat id never rides any recorded value or error text;
  * calibration pairing is fail-closed: legacy pre-HP-3 rows and unknown
    channel values are excluded + tallied honestly (never silently), an
    unattested newer label cannot shadow an attested older one, and the
    journal claim is re-verified against the STORE's hash-covered copy;
  * byte-identity (the dark-default proof): a corpus with zero unattested
    labels measures and renders byte-identically with every HP-3 seam
    disabled;
  * anchor re-count: the label journal proves append-only against the
    FULL anchor history; forged/altered/removed rows, unjournaled
    in-store labels, and channel divergence are named findings; the CLI
    verb is opt-in (unused = the daily anchor run untouched);
  * back-compat: legacy (pre-HP-3) store labels still VERIFY — the
    attestation key is additive detail; legacy rows are excluded from NEW
    pairing only, with an honest count.

Hermetic: tmp stores + scratch journals only; the Captain token is minted
from the tmp store's own signing key (the real derivation, no mocks).
Synthetic Testburg vocabulary only.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework import evidence_anchor as ea  # noqa: E402
from framework import evidence_calibration as ec  # noqa: E402
from framework.evidence import redaction  # noqa: E402
from framework.evidence.recorder import (  # noqa: E402
    EvidenceError,
    EvidenceRecorder,
)
from framework.evidence.verifier import verify_trial  # noqa: E402

_SCRIPT = Path(__file__).resolve().parents[1] / "governance-review.py"
_spec = importlib.util.spec_from_file_location("governance_review_hp3", _SCRIPT)
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)

_OFFICER = {"kind": "officer", "id": "tb-cos"}
_COMPONENT = {"name": "testburg-exec", "version": "1"}
_CAPTAIN = {"kind": "captain", "id": "captain"}
_GR_COMPONENT = {"name": "governance-review", "version": "1"}
_NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# helpers (the sibling suites' harness, trimmed)
# ---------------------------------------------------------------------------

def _seed_trial(rec: EvidenceRecorder, trial_id: str) -> str:
    ctx = rec.trace(trial_id, surface="system")
    detail = {"action": "write_testburg_note", "jid": "j-tb-hp3"}
    rec.append(ctx, phase="intent", status="started", actor=_OFFICER,
               component=_COMPONENT, detail=detail)
    rec.append(ctx, phase="execution", status="succeeded", actor=_OFFICER,
               component=_COMPONENT, detail=detail)
    return trial_id


def _mint_token(store: Path, path: Path) -> Path:
    key = (store / ".signing-key").read_bytes()
    token = hmac.new(key, gr.evidence_cli.CAPTAIN_TOKEN_PURPOSE.encode("utf-8"),
                     hashlib.sha256).hexdigest()
    path.write_text(token + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _tree_digest(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class _Script:
    def __init__(self, answers):
        self.answers = list(answers)

    def __call__(self, prompt):
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


def _run_cli(store, tmp_path, answers, *, token):
    out = io.StringIO()
    rc = gr.main(
        ["--store", str(store), "--skip-stations", "--seed", "7",
         "--captain-token-file", str(token),
         "--labels-journal", str(tmp_path / "out" / "labels.jsonl"),
         "--transcript-dir", str(tmp_path / "out" / "reviews")],
        input_fn=_Script(answers), isatty=True, out=out)
    return rc, out.getvalue(), tmp_path / "out"


def _journal_rows(path: Path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _attested_label(store, rec, journal, trial_id, verdict, *, ts=None,
                    store_channel=None, digest_channel=None):
    """The production write path, attested. ``store_channel`` /
    ``digest_channel`` let a test simulate a divergent forged claim."""
    cand = gr.classify_trial(gr._read_raw_events(store, trial_id))
    cand["trial_id"] = trial_id
    events = gr.write_label(rec, trial_id, verdict, "", cand,
                            session="hp3-test",
                            channel=store_channel or gr.CHANNEL_TTY)
    digest = gr.label_digest_record("hp3-test", trial_id, verdict, cand,
                                    events,
                                    channel=digest_channel or gr.CHANNEL_TTY)
    if ts is not None:
        digest["ts"] = ts
    gr._append_journal_line(journal, digest)
    return events, digest


def _legacy_label(rec, trial_id, verdict="wrong"):
    """A pre-HP-3 label shape: verdict_human events WITHOUT label_channel
    (what governance-review wrote before this wave)."""
    status = {"wrong": ("unverified", "failed"),
              "right": ("verified", "succeeded")}[verdict]
    detail = {"action": gr.LABEL_ACTION, "source": "verdict_human",
              "result_code": {"wrong": "wrong", "right": "confirmed"}[verdict],
              "basis": "self_asserted", "session": "hp3-legacy"}
    ctx = rec.trace(trial_id, surface="cli")
    events = [rec.append(ctx, phase="verification", status=status[0],
                         actor=dict(_CAPTAIN), component=dict(_GR_COMPONENT),
                         detail=detail)]
    events.append(rec.append(ctx, phase="outcome", status=status[1],
                             actor=dict(_CAPTAIN),
                             component=dict(_GR_COMPONENT), detail=detail))
    return events


def _legacy_digest_row(journal, trial_id, verdict, events,
                       ts="2026-07-17T10:00:00.000000Z"):
    """A pre-HP-3 journal row: NO channel key at all."""
    gr._append_journal_line(journal, {
        "schema": "cabinet.governance-label-digest/v1",
        "ts": ts, "session": "hp3-legacy", "trial_id": trial_id,
        "verdict": {"wrong": "wrong", "right": "confirmed"}[verdict],
        "basis": "self_asserted",
        "event_ids": [e["event_id"] for e in events],
        "event_hashes": [e["event_hash"] for e in events],
    })


def _flag(flags: Path, trial_id, failure_class="hp3-fail", verdict=None,
          component="testburg-exec", ts="2026-07-17T11:00:00.000000Z"):
    row = {"ts": ts, "component": component, "failure_class": failure_class}
    if trial_id is not None:
        row["trial_id"] = trial_id
    if verdict is not None:
        row["verdict"] = verdict
    flags.parent.mkdir(parents=True, exist_ok=True)
    with flags.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# vocabulary pins across the three surfaces (the repeated-literal law)
# ---------------------------------------------------------------------------

def test_vocabulary_pins_across_surfaces():
    assert gr.ATTESTED_LABEL_CHANNELS == ec.ATTESTED_LABEL_CHANNELS
    assert gr.CHANNEL_TTY == "captain-token+tty"
    assert gr.CHANNEL_TELEGRAM == "telegram-captain-dm"
    assert (gr.LABEL_CHANNEL_KEY == ec.LABEL_CHANNEL_DETAIL_KEY
            == ea.LABEL_CHANNEL_DETAIL_KEY == "label_channel")
    assert (gr.LABEL_CHANNEL_JOURNAL_KEY == ec.LABEL_CHANNEL_JOURNAL_KEY
            == ea.LABEL_CHANNEL_JOURNAL_KEY == "channel")
    assert ea.LABEL_DIGEST_SCHEMA == ec.LABEL_DIGEST_SCHEMA
    assert ea.LABELS_JOURNAL_BASENAME == Path(gr.LABELS_JOURNAL_REL).name
    assert ea.LABEL_ACTION_MARKER == gr.LABEL_ACTION
    # Redaction safety: neither key matches the secret-key family, so the
    # attestation survives sanitize verbatim (the v1.1 naming rule).
    assert redaction.SECRET_KEY_RE.search(gr.LABEL_CHANNEL_KEY) is None
    assert redaction.SECRET_KEY_RE.search(gr.LABEL_CHANNEL_JOURNAL_KEY) is None
    # No chat id can ever hide inside a channel value: the vocabulary is
    # digit-free by construction (no-secrets-in-detail).
    for value in gr.ATTESTED_LABEL_CHANNELS:
        assert not any(ch.isdigit() for ch in value), value


# ---------------------------------------------------------------------------
# the TTY channel end-to-end + fail-closed refusals
# ---------------------------------------------------------------------------

def test_tty_attestation_rides_label_and_digest(tmp_path):
    store = tmp_path / "evidence"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "trial-tb-hp3-tty-1")
    token = _mint_token(store, tmp_path / "captain.token")
    rc, text, outdir = _run_cli(store, tmp_path, ["r", ""], token=token)
    assert rc == 0
    labels = [e for e in EvidenceRecorder(store).read_events(tid)
              if e["detail"].get("action") == gr.LABEL_ACTION]
    assert len(labels) == 2
    for event in labels:
        # Hash-covered, survives sanitize verbatim, never redacted.
        assert event["detail"]["label_channel"] == "captain-token+tty"
        assert event["redactions"] == []
    rows = _journal_rows(outdir / "labels.jsonl")
    digest = next(r for r in rows
                  if r.get("schema") == "cabinet.governance-label-digest/v1")
    assert digest["channel"] == "captain-token+tty"
    marker = next(r for r in rows if r.get("kind") == "session_complete")
    assert "channel" not in marker           # markers are not labels


def test_write_label_refuses_unattested_context_before_any_byte(tmp_path):
    store = tmp_path / "evidence"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "trial-tb-hp3-refuse-1")
    cand = gr.classify_trial(gr._read_raw_events(store, tid))
    cand["trial_id"] = tid
    before = _tree_digest(store)
    for channel in (None, "", "bogus-channel", "captain-token"):
        with pytest.raises(EvidenceError) as err:
            gr.write_label(rec, tid, "right", "", cand, "hp3-s",
                           channel=channel)
        assert err.value.code == "label_channel_unattested"
        with pytest.raises(EvidenceError) as err:
            gr.label_digest_record("hp3-s", tid, "right", cand, [],
                                   channel=channel)
        assert err.value.code == "label_channel_unattested"
    # Fail-closed means fail-CLOSED: zero store bytes on every refusal.
    assert _tree_digest(store) == before


def test_attest_tty_channel_fail_closed():
    assert gr.attest_tty_channel(token_ok=True,
                                 stdin_tty=True) == gr.CHANNEL_TTY
    for token_ok, stdin_tty in ((False, True), (True, False), (False, False)):
        with pytest.raises(EvidenceError) as err:
            gr.attest_tty_channel(token_ok=token_ok, stdin_tty=stdin_tty)
        assert err.value.code == "label_channel_unattested"


# ---------------------------------------------------------------------------
# the RESERVED telegram channel: allowlist-gated, dark by default
# ---------------------------------------------------------------------------

def test_attest_telegram_channel_allowlist(tmp_path):
    cfg = tmp_path / "platform.yml"
    cfg.write_text("captain_telegram_chat_id: 8123456789\n", encoding="utf-8")
    assert gr.attest_telegram_channel(8123456789,
                                      cfg) == gr.CHANNEL_TELEGRAM
    assert gr.attest_telegram_channel("8123456789",
                                      cfg) == gr.CHANNEL_TELEGRAM
    with pytest.raises(EvidenceError) as err:
        gr.attest_telegram_channel(999, cfg)
    assert err.value.code == "label_channel_mismatch"
    # The configured id never leaks into error text (no-secrets law).
    assert "8123456789" not in str(err.value)
    with pytest.raises(EvidenceError) as err:
        gr.attest_telegram_channel("not-an-id", cfg)
    assert err.value.code == "label_channel_unattested"
    assert "8123456789" not in str(err.value)


def test_telegram_dark_default_refuses_unconfigured(tmp_path):
    # Absent config file — the shipped default — refuses.
    with pytest.raises(EvidenceError) as err:
        gr.attest_telegram_channel(8123456789, tmp_path / "absent.yml")
    assert err.value.code == "label_channel_unconfigured"
    # Placeholder and zero values (the committed .example / scrubbed
    # instances) refuse identically.
    for body in ('captain_telegram_chat_id: "<YOUR-TELEGRAM-CHAT-ID>"\n',
                 "captain_telegram_chat_id: 0\n",
                 "captain_telegram_chat_id:\n",
                 "- not\n- a\n- dict\n"):
        cfg = tmp_path / "platform.yml"
        cfg.write_text(body, encoding="utf-8")
        with pytest.raises(EvidenceError) as err:
            gr.attest_telegram_channel(8123456789, cfg)
        assert err.value.code == "label_channel_unconfigured"
        cfg.unlink()
    # A symlinked config never attests.
    real = tmp_path / "real.yml"
    real.write_text("captain_telegram_chat_id: 8123456789\n", encoding="utf-8")
    link = tmp_path / "platform.yml"
    link.symlink_to(real)
    with pytest.raises(EvidenceError) as err:
        gr.attest_telegram_channel(8123456789, link)
    assert err.value.code == "label_channel_unconfigured"


def test_officer_projection_redacts_the_channel(tmp_path):
    store = tmp_path / "evidence"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "trial-tb-hp3-proj-1")
    token = _mint_token(store, tmp_path / "captain.token")
    rc, _, _ = _run_cli(store, tmp_path, ["r", ""], token=token)
    assert rc == 0
    projection = EvidenceRecorder(store).cabinet_projection(tid)
    served = [r for r in projection["records"]
              if r.get("detail", {}).get("action") == gr.LABEL_ACTION]
    assert served
    for record in served:
        assert "label_channel" not in record["detail"]
        assert "action" in record["detail"]


# ---------------------------------------------------------------------------
# calibration: fail-closed pairing + honest tallies
# ---------------------------------------------------------------------------

def test_calibration_excludes_legacy_and_invalid_tallied_honestly(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)
    t_ok = _seed_trial(rec, "evt-tb-hp3-ok-1")
    t_legacy = _seed_trial(rec, "evt-tb-hp3-legacy-1")
    t_bad = _seed_trial(rec, "evt-tb-hp3-badchan-1")

    _attested_label(store, rec, journal, t_ok, "wrong")
    legacy_events = _legacy_label(rec, t_legacy, "wrong")
    _legacy_digest_row(journal, t_legacy, "wrong", legacy_events)
    # Present-but-unknown channel value: fail-closed, its own bucket.
    events, _ = _attested_label(store, rec, journal, t_bad, "wrong")
    bad_row = _journal_rows(journal)[-1] | {"channel": "bogus-channel"}
    journal.write_text("\n".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True)
        for r in _journal_rows(journal)[:-1] + [bad_row]) + "\n",
        encoding="utf-8")

    for tid in (t_ok, t_legacy, t_bad):
        _flag(flags, tid)

    # Back-compat: the legacy store label still VERIFIES (additive key —
    # old events are legal v1 rows); it is only excluded from NEW pairing.
    assert verify_trial(store, t_legacy)["ok"] is True

    status = ec.measure(store_root=store, labels_journal=journal,
                        flags_paths=[flags], now=_NOW)
    totals = status["totals"]
    assert totals["labels"]["rows"] == 3
    assert totals["labels"][ec.BUCKET_LEGACY] == 1
    assert totals["labels"][ec.BUCKET_UNAUTHENTICATED] == 1
    assert totals["candidate_pairs"] == 1
    assert totals["counted_pairs"] == 1
    report = ec.render_report(status)
    assert "2 label(s) excluded: unauthenticated channel" in report
    assert "legacy pre-HP-3 1" in report
    assert "never silently dropped" in report


def test_unattested_newer_never_shadows_attested_older(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "evt-tb-hp3-shadow-1")

    # Attested OLDER label says confirmed…
    _attested_label(store, rec, journal, tid, "right",
                    ts="2026-07-17T10:00:00.000000Z")
    # …then an unattested NEWER row claims wrong. Fail-closed: it may
    # neither pair nor supersede.
    legacy_events = _legacy_label(rec, tid, "wrong")
    _legacy_digest_row(journal, tid, "wrong", legacy_events,
                       ts="2026-07-17T11:30:00.000000Z")
    _flag(flags, tid)

    labels = ec.read_label_digests(journal)
    flag_rows, _ = ec.read_detector_flags([flags])
    pairs, totals = ec.collect_stratum_pairs(labels, flag_rows)
    assert len(pairs) == 1
    assert pairs[0]["human"] == "confirmed"      # the attested older won
    assert totals["labels"][ec.BUCKET_LEGACY] == 1


def test_store_side_channel_reverification_catches_forged_claim(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "evt-tb-hp3-forged-1")

    # Legacy store events (no label_channel), but the journal row CLAIMS
    # attestation over their real hashes — the store re-check must refuse.
    legacy_events = _legacy_label(rec, tid, "wrong")
    gr._append_journal_line(journal, {
        "schema": ec.LABEL_DIGEST_SCHEMA, "ts": "2026-07-17T10:00:00.000000Z",
        "session": "hp3-forge", "trial_id": tid, "verdict": "wrong",
        "basis": "self_asserted", "channel": gr.CHANNEL_TTY,
        "event_ids": [e["event_id"] for e in legacy_events],
        "event_hashes": [e["event_hash"] for e in legacy_events],
    })
    _flag(flags, tid)

    status = ec.measure(store_root=store, labels_journal=journal,
                        flags_paths=[flags], now=_NOW)
    totals = status["totals"]
    assert totals["candidate_pairs"] == 1
    assert totals["counted_pairs"] == 0
    assert totals["excluded"][ec.BUCKET_CHANNEL_UNVERIFIED] == 1
    assert "channel_unverified 1" in ec.render_report(status)


def test_divergent_channel_value_is_channel_unverified(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "evt-tb-hp3-diverge-1")
    # Store says telegram, journal claims tty — both vocabulary values,
    # still refused: the store's hash-covered copy is authoritative.
    _attested_label(store, rec, journal, tid, "wrong",
                    store_channel=gr.CHANNEL_TELEGRAM,
                    digest_channel=gr.CHANNEL_TTY)
    _flag(flags, tid)
    status = ec.measure(store_root=store, labels_journal=journal,
                        flags_paths=[flags], now=_NOW)
    assert status["totals"]["counted_pairs"] == 0
    assert status["totals"]["excluded"][ec.BUCKET_CHANNEL_UNVERIFIED] == 1


def test_byte_identical_when_zero_unattested(tmp_path, monkeypatch):
    """THE dark-default proof: on a corpus with zero unattested labels the
    full HP-3 seam set contributes ZERO bytes — status JSON and Captain
    report are byte-identical with every seam disabled."""
    store = tmp_path / "evidence"
    journal = tmp_path / "labels.jsonl"
    flags = tmp_path / "flags.jsonl"
    rec = EvidenceRecorder(store)
    for index, verdict in enumerate(("wrong", "right")):
        tid = _seed_trial(rec, "evt-tb-hp3-clean-%d" % index)
        _attested_label(store, rec, journal, tid, verdict)
        _flag(flags, tid)

    status_on = ec.measure(store_root=store, labels_journal=journal,
                           flags_paths=[flags], now=_NOW)
    report_on = ec.render_report(status_on)

    monkeypatch.setattr(ec, "_label_attestation", lambda row: None)
    monkeypatch.setattr(ec, "_channel_backed", lambda *a, **k: True)
    status_off = ec.measure(store_root=store, labels_journal=journal,
                            flags_paths=[flags], now=_NOW)
    report_off = ec.render_report(status_off)

    assert (json.dumps(status_on, sort_keys=True)
            == json.dumps(status_off, sort_keys=True))
    assert report_on == report_off
    # The conditional counters really are absent at zero.
    assert set(status_on["totals"]["labels"]) == {
        "rows", "scoreable", "unscoreable", "windowed_out"}
    assert set(status_on["totals"]["excluded"]) == {
        "store_unavailable", "unverified", "purged", "digest_hashes_missing"}
    assert "unauthenticated" not in report_on
    assert status_on["totals"]["counted_pairs"] == 2


# ---------------------------------------------------------------------------
# anchor re-count: append-only proof + store cross-join
# ---------------------------------------------------------------------------

def _label_files(journal: Path) -> dict:
    return {ea.LABELS_JOURNAL_BASENAME: journal}


def test_recount_clean_and_append_only_growth(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "governance-labels.jsonl"
    rec = EvidenceRecorder(store)
    # An anchor taken before the journal existed contributes nothing.
    r0 = ea.collect_anchor(store, label_files=_label_files(journal))
    assert r0["captain_labels"][ea.LABELS_JOURNAL_BASENAME] is None

    t1 = _seed_trial(rec, "evt-tb-hp3-rc-1")
    t2 = _seed_trial(rec, "evt-tb-hp3-rc-2")
    _attested_label(store, rec, journal, t1, "wrong")
    r1 = ea.collect_anchor(store, label_files=_label_files(journal))
    _attested_label(store, rec, journal, t2, "right")
    r2 = ea.collect_anchor(store, label_files=_label_files(journal))

    result = ea.recount_labels(journal, [r0, r1, r2], store_root=store)
    assert result["ok"] is True, result
    assert result["findings"] == []
    counts = result["counts"]
    assert counts["anchored_digests"] == 2       # r0 carried no digest
    assert counts["prefix_matched"] == 2
    assert counts["digest_rows"] == 2
    assert counts["rows_store_backed"] == 2
    assert counts["legacy_rows"] == 0
    assert counts["store_labels_seen"] == 4      # 2 labels × 2 events
    assert counts["store_labels_journaled"] == 4


def test_recount_catches_rewrite_removal_regression_and_missing(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "governance-labels.jsonl"
    rec = EvidenceRecorder(store)
    for index in range(3):
        tid = _seed_trial(rec, "evt-tb-hp3-rw-%d" % index)
        _attested_label(store, rec, journal, tid, "wrong")
    anchored = ea.collect_anchor(store, label_files=_label_files(journal))
    original = journal.read_bytes()

    # (a) A flipped byte inside an anchored row = rewritten.
    journal.write_bytes(original.replace(b'"wrong"', b'"right"', 1))
    result = ea.recount_labels(journal, [anchored], store_root=store)
    kinds = {f["kind"] for f in result["findings"]}
    assert "label_journal_rewritten" in kinds

    # (b) A removed anchored row = rewritten (no prefix matches).
    lines = original.split(b"\n")
    journal.write_bytes(b"\n".join(lines[:2]) + b"\n")
    result = ea.recount_labels(journal, [anchored], store_root=store)
    assert {"label_journal_rewritten"} <= {
        f["kind"] for f in result["findings"]}

    # (c) A LATER anchor matching a SHORTER prefix than an earlier one =
    # prefix regression (synthetic records over the restored journal).
    journal.write_bytes(original)
    boundary_short = hashlib.sha256(
        original[:original.find(b"\n") + 1]).hexdigest()
    boundary_full = hashlib.sha256(original).hexdigest()
    rec_long = {"generated_at": "2026-07-01T00:00:00.000000Z",
                "captain_labels": {ea.LABELS_JOURNAL_BASENAME: boundary_full}}
    rec_short = {"generated_at": "2026-07-02T00:00:00.000000Z",
                 "captain_labels": {ea.LABELS_JOURNAL_BASENAME: boundary_short}}
    result = ea.recount_labels(journal, [rec_long, rec_short])
    assert {"label_journal_prefix_regression"} == {
        f["kind"] for f in result["findings"]}

    # (d) Journal gone while anchors carry digests = missing.
    journal.unlink()
    result = ea.recount_labels(journal, [anchored])
    assert {"label_journal_missing"} == {f["kind"] for f in result["findings"]}
    assert "journal_absent" in result["notes"]


def test_recount_store_cross_join_findings(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "governance-labels.jsonl"
    rec = EvidenceRecorder(store)

    # Clean attested label (backed) + a purged trial (excused).
    t_ok = _seed_trial(rec, "evt-tb-hp3-x-ok")
    _attested_label(store, rec, journal, t_ok, "wrong")
    t_purge = _seed_trial(rec, "evt-tb-hp3-x-purge")
    _attested_label(store, rec, journal, t_purge, "wrong")
    rec.purge_trial(t_purge, confirmation="PURGE " + t_purge,
                    actor="captain")

    # Forged journal rows: fake hashes on a real trial; a ghost trial.
    gr._append_journal_line(journal, {
        "schema": ec.LABEL_DIGEST_SCHEMA, "ts": "2026-07-17T10:00:00.000000Z",
        "session": "hp3-x", "trial_id": t_ok, "verdict": "wrong",
        "basis": "self_asserted", "channel": gr.CHANNEL_TTY,
        "event_ids": ["evd-fake"], "event_hashes": ["ab" * 32]})
    gr._append_journal_line(journal, {
        "schema": ec.LABEL_DIGEST_SCHEMA, "ts": "2026-07-17T10:00:00.000000Z",
        "session": "hp3-x", "trial_id": "evt-tb-hp3-x-ghost", "verdict":
        "wrong", "basis": "self_asserted", "channel": gr.CHANNEL_TTY,
        "event_ids": ["evd-fake"], "event_hashes": ["cd" * 32]})

    # An in-store label with NO journal row at all.
    t_dark = _seed_trial(rec, "evt-tb-hp3-x-dark")
    _legacy_label(rec, t_dark, "wrong")

    result = ea.recount_labels(journal, [], store_root=store)
    kinds = sorted(f["kind"] for f in result["findings"])
    unbacked = [f for f in result["findings"]
                if f["kind"] == "label_journal_row_unbacked"]
    assert {f["reason"] for f in unbacked} == {"event_hashes_missing",
                                               "trial_missing"}
    assert "store_label_unjournaled" in kinds
    assert result["counts"]["rows_excused_purged"] == 1
    assert result["counts"]["rows_store_backed"] == 1
    # The clean row and the purge stayed finding-free.
    assert not [f for f in result["findings"]
                if f.get("trial_id") == t_purge]


def test_recount_channel_mismatch_is_a_named_finding(tmp_path):
    store = tmp_path / "evidence"
    journal = tmp_path / "governance-labels.jsonl"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "evt-tb-hp3-x-chan")
    _attested_label(store, rec, journal, tid, "wrong",
                    store_channel=gr.CHANNEL_TELEGRAM,
                    digest_channel=gr.CHANNEL_TTY)
    result = ea.recount_labels(journal, [], store_root=store)
    assert {"label_channel_mismatch"} == {
        f["kind"] for f in result["findings"]}
    # A legacy journal row (no channel key) is honest, never a mismatch.
    legacy_events = _legacy_label(rec, _seed_trial(rec, "evt-tb-hp3-x-leg"),
                                  "wrong")
    _legacy_digest_row(journal, "evt-tb-hp3-x-leg", "wrong", legacy_events)
    result = ea.recount_labels(journal, [], store_root=store)
    assert result["counts"]["legacy_rows"] == 1
    assert {"label_channel_mismatch"} == {
        f["kind"] for f in result["findings"]}


def test_recount_cli_verb_and_dark_default(tmp_path, capsys, monkeypatch):
    cli_path = _REPO_ROOT / "cabinet" / "scripts" / "evidence-anchor.py"
    spec = importlib.util.spec_from_file_location("evidence_anchor_cli_hp3",
                                                  cli_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    store = tmp_path / "evidence"
    journal = tmp_path / "governance-labels.jsonl"
    rec = EvidenceRecorder(store)
    tid = _seed_trial(rec, "evt-tb-hp3-cli-1")
    _attested_label(store, rec, journal, tid, "wrong")
    anchors = tmp_path / "evidence-anchors.jsonl"
    record = ea.collect_anchor(store, label_files=_label_files(journal))
    anchors.write_text(json.dumps(record, sort_keys=True) + "\n",
                       encoding="utf-8")
    monkeypatch.setattr(cli, "_label_files",
                        lambda repo_root, config: _label_files(journal))

    code = cli.main(["--store", str(store), "--recount-labels", str(anchors)])
    out = json.loads(capsys.readouterr().out.strip())
    assert code == 0 and out["ok"] is True
    assert out["schema"] == ea.RECOUNT_SCHEMA

    # Tamper → exit 2 with the named finding.
    data = journal.read_bytes()
    journal.write_bytes(data.replace(b'"wrong"', b'"right"', 1))
    code = cli.main(["--store", str(store), "--recount-labels", str(anchors)])
    out = json.loads(capsys.readouterr().out.strip())
    assert code == 2 and out["ok"] is False
    assert {f["kind"] for f in out["findings"]} >= {"label_journal_rewritten"}

    # DARK DEFAULT: without the flag the daily run never touches the
    # re-count path (byte-identical current behavior by construction).
    def _boom(*args, **kwargs):  # pragma: no cover — must never run
        raise AssertionError("recount_labels ran without --recount-labels")

    monkeypatch.setattr(cli, "recount_labels", _boom)
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_COS_TOKEN",
                 "CAPTAIN_TELEGRAM_ID"):
        monkeypatch.delenv(name, raising=False)
    journal.write_bytes(data)
    code = cli.main(["--store", str(store), "--dry-run", "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    assert code == 0 and out["digest_event"] == "skipped-dry-run"
