"""External evidence anchoring + daily digest-anchor logic (Phase 1).

The evidence store under ``instance/evidence/v1`` is hash-chained, signed,
and anti-rollback watermarked — but every one of those protections lives
INSIDE the store: restoring an old copy of the whole store (events, tip
anchors, and watermark sidecar together) resets protection, because absence
is not provable locally. This module closes that documented residual by
exporting a content-free snapshot of the store's tamper-evidence surface to
Captain-owned surfaces OUTSIDE the store, and by recording daily checksums
of the weaker breadth ledgers (org events, consequence ledger, trigger
archive) INTO the evidence store, so those become tamper-evident too.

Design rules (whole-cabinet evidence design 2026-07-16, Phase 1 items 5+6):

* Read-only over the store. Collection reads ``trials/*/anchor.json``,
  ``trials/*/events.jsonl`` (bytes for digesting only — never parsed, never
  exported), ``.verify-watermarks.json``, ``control.json``, and
  ``purge-receipts/*.json``. It NEVER opens ``.signing-key`` and never runs
  the verifier (verification advances watermarks — a side effect a read-only
  anchor job must not have).
* The HP-3 label re-count (:func:`recount_labels`) additionally PARSES
  event rows — read-only, for hash-membership joins only; payloads are
  never exported, ``.signing-key`` is never opened, and the verifier is
  still never run (the VERIFIED leg over the same join belongs to the
  Phase-4 calibration shadow, which sanctions the watermark side effect).
* Content-free export. Anchor records carry trial ids, sequence numbers,
  hashes, HMAC signatures' file digests, and counts — no event payloads.
* No environment coupling. Every path is an explicit argument; this module
  never consults env vars, so no officer-influenceable variable can steer
  what gets anchored (A10 posture).
* The single write path — the daily digest-anchor trial — rides the
  sanctioned ``EvidenceRecorder`` import seam (lazy import below). There is
  deliberately no generic emit surface here.

This module is intentionally NOT part of the germline ``framework/evidence``
package: it is an external observer of the store. Its read side shares no
code with the writer (constants duplicated on purpose, verifier-style).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ANCHOR_RECORD_SCHEMA = "cabinet.evidence-external-anchor/v1"
WATERMARK_NAME = ".verify-watermarks.json"  # deliberate duplicate of verifier.WATERMARK_NAME
# Deliberate duplicate of the store's TRIAL_ID_RE: the external observer
# shares no code path with the germline package on its read side.
_TRIAL_DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class AnchorError(RuntimeError):
    """A typed external-anchoring failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    """Digest a file's bytes; ``None`` when absent/unreadable (recorded, not fatal)."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 16), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


# ---------------------------------------------------------------------------
# Collection — the content-free external anchor record
# ---------------------------------------------------------------------------

def collect_anchor(
    store_root: Path | str,
    *,
    label_files: dict[str, Path | str] | None = None,
) -> dict[str, Any]:
    """Read-only snapshot of the store's tamper-evidence surface.

    ``label_files`` maps a short display name to a Captain-label ledger path
    (e.g. captain-vetoes.yml); absent files are recorded as ``None`` digests
    so "the surface did not exist that day" is itself on the record.
    """
    root = Path(store_root)
    if root.is_symlink():
        raise AnchorError("The evidence store must not be a symbolic link.")
    record: dict[str, Any] = {
        "schema": ANCHOR_RECORD_SCHEMA,
        "generated_at": _utc_now(),
        "store_present": root.is_dir(),
        "trials": {},
        "watermarks": {"present": False, "sha256": None, "rows": {}},
        "control": {"present": False, "sha256": None, "updated_at": None, "updated_by": None},
        "purge_receipts": {"count": 0, "files": {}},
        "captain_labels": {},
    }

    trials_dir = root / "trials"
    if trials_dir.is_dir():
        for path in sorted(trials_dir.iterdir()):
            if path.is_symlink() or not path.is_dir():
                continue
            if not _TRIAL_DIR_RE.fullmatch(path.name):
                continue
            entry: dict[str, Any] = {
                "sequence": None,
                "event_hash": None,
                "anchor_sha256": _sha256_file(path / "anchor.json"),
                "events_sha256": _sha256_file(path / "events.jsonl"),
            }
            anchor = _load_json(path / "anchor.json")
            if anchor is not None:
                sequence = anchor.get("sequence")
                event_hash = anchor.get("event_hash")
                if isinstance(sequence, int) and not isinstance(sequence, bool):
                    entry["sequence"] = sequence
                if isinstance(event_hash, str):
                    entry["event_hash"] = event_hash
            record["trials"][path.name] = entry

    watermark_path = root / WATERMARK_NAME
    if watermark_path.is_file() and not watermark_path.is_symlink():
        rows: dict[str, Any] = {}
        sidecar = _load_json(watermark_path)
        if sidecar is not None and isinstance(sidecar.get("trials"), dict):
            for trial_hash, item in sidecar["trials"].items():
                if not isinstance(trial_hash, str) or not isinstance(item, dict):
                    continue
                sequence = item.get("sequence")
                event_hash = item.get("event_hash")
                if (
                    isinstance(sequence, int)
                    and not isinstance(sequence, bool)
                    and isinstance(event_hash, str)
                ):
                    rows[trial_hash] = {"sequence": sequence, "event_hash": event_hash}
        record["watermarks"] = {
            "present": True,
            "sha256": _sha256_file(watermark_path),
            "rows": rows,
        }

    control_path = root / "control.json"
    control = _load_json(control_path)
    if control is not None:
        record["control"] = {
            "present": True,
            "sha256": _sha256_file(control_path),
            "updated_at": control.get("updated_at"),
            "updated_by": control.get("updated_by"),
        }

    receipts_dir = root / "purge-receipts"
    if receipts_dir.is_dir():
        files: dict[str, str] = {}
        for path in sorted(receipts_dir.glob("purge-*.json")):
            if path.is_symlink() or not path.is_file():
                continue
            digest = _sha256_file(path)
            if digest is not None:
                files[path.name] = digest
        record["purge_receipts"] = {"count": len(files), "files": files}

    for name, path in sorted((label_files or {}).items()):
        record["captain_labels"][str(name)] = _sha256_file(Path(path))

    payload = {key: value for key, value in record.items() if key != "record_digest"}
    record["record_digest"] = _sha256_bytes(_canonical(payload))
    return record


# ---------------------------------------------------------------------------
# Check — the restore-drill teeth
# ---------------------------------------------------------------------------

def _purge_receipt_covers(current: dict[str, Any], trial_id: str) -> bool:
    prefix = "purge-" + hashlib.sha256(trial_id.encode("utf-8")).hexdigest()[:16] + "-"
    files = (current.get("purge_receipts") or {}).get("files") or {}
    return any(name.startswith(prefix) for name in files)


def check_anchor(
    store_root: Path | str,
    previous: dict[str, Any] | None,
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare the store's CURRENT surface against a previously exported record.

    Catches exactly the class the local verifier cannot: a store copy
    restored to an earlier state (trial tip sequence regression), a
    same-length divergent tip, a deleted trial with no purge receipt, a
    deleted/regressed watermark sidecar, and removed purge receipts.
    Control/label digest changes are legitimate operations and are reported
    separately by :func:`informational_changes`, never as findings.
    """
    if current is None:
        current = collect_anchor(store_root)
    findings: list[dict[str, Any]] = []
    if not previous:
        return {"ok": True, "first_run": True, "findings": [], "checked_trials": 0}

    cur_trials = current.get("trials") or {}
    prev_trials = previous.get("trials") or {}
    for trial_id, prev_entry in sorted(prev_trials.items()):
        prev_sequence = prev_entry.get("sequence")
        prev_hash = prev_entry.get("event_hash")
        if prev_sequence is None:
            continue  # never anchored a tip for it; nothing to enforce
        cur_entry = cur_trials.get(trial_id)
        if cur_entry is None:
            if _purge_receipt_covers(current, trial_id):
                continue  # legitimately purged — receipt survives, by design
            findings.append({"kind": "trial_missing", "trial_id": trial_id})
            continue
        cur_sequence = cur_entry.get("sequence")
        if cur_sequence is None:
            findings.append({"kind": "trial_anchor_unreadable", "trial_id": trial_id})
        elif cur_sequence < prev_sequence:
            findings.append({
                "kind": "trial_rollback",
                "trial_id": trial_id,
                "anchored_sequence": prev_sequence,
                "current_sequence": cur_sequence,
            })
        elif cur_sequence == prev_sequence and cur_entry.get("event_hash") != prev_hash:
            findings.append({
                "kind": "trial_tip_divergence",
                "trial_id": trial_id,
                "sequence": prev_sequence,
            })

    prev_marks = previous.get("watermarks") or {}
    cur_marks = current.get("watermarks") or {}
    if prev_marks.get("present"):
        if not cur_marks.get("present"):
            findings.append({"kind": "watermark_sidecar_missing"})
        else:
            cur_rows = cur_marks.get("rows") or {}
            for trial_hash, prev_row in sorted((prev_marks.get("rows") or {}).items()):
                cur_row = cur_rows.get(trial_hash)
                if cur_row is None:
                    findings.append({"kind": "watermark_row_missing", "trial_hash": trial_hash})
                elif cur_row.get("sequence") < prev_row.get("sequence"):
                    findings.append({
                        "kind": "watermark_regression",
                        "trial_hash": trial_hash,
                        "anchored_sequence": prev_row.get("sequence"),
                        "current_sequence": cur_row.get("sequence"),
                    })
                elif (
                    cur_row.get("sequence") == prev_row.get("sequence")
                    and cur_row.get("event_hash") != prev_row.get("event_hash")
                ):
                    findings.append({"kind": "watermark_divergence", "trial_hash": trial_hash})

    cur_receipts = (current.get("purge_receipts") or {}).get("files") or {}
    for name, digest in sorted(((previous.get("purge_receipts") or {}).get("files") or {}).items()):
        if name not in cur_receipts:
            findings.append({"kind": "purge_receipt_missing", "file": name})
        elif cur_receipts[name] != digest:
            findings.append({"kind": "purge_receipt_altered", "file": name})

    return {
        "ok": not findings,
        "first_run": False,
        "findings": findings,
        "checked_trials": len(prev_trials),
    }


def informational_changes(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> list[str]:
    """Legitimate-operation deltas worth a receipt line (never findings)."""
    if not previous:
        return []
    notes: list[str] = []
    if (previous.get("control") or {}).get("sha256") != (current.get("control") or {}).get("sha256"):
        notes.append("control_changed")
    if (previous.get("captain_labels") or {}) != (current.get("captain_labels") or {}):
        notes.append("captain_labels_changed")
    return notes


# ---------------------------------------------------------------------------
# Daily digest-anchor trial — the weaker ledgers become tamper-evident
# ---------------------------------------------------------------------------

def digest_ledger_file(path: Path | str) -> dict[str, Any]:
    """Checksum one JSONL ledger file. Values are redaction-safe by
    construction: basenames only (never absolute paths), hex digests, and
    counts."""
    ledger = Path(path)
    digest = _sha256_file(ledger)
    if digest is None:
        return {"present": False}
    try:
        data = ledger.read_bytes()
    except OSError:
        return {"present": False}
    return {
        "present": True,
        "file": ledger.name,
        "sha256": digest,
        "lines": data.count(b"\n"),
        "bytes": len(data),
    }


def digest_ledger_dir(path: Path | str, pattern: str = "*.jsonl") -> dict[str, Any]:
    """Checksum a directory of ledger files into one bounded manifest digest."""
    directory = Path(path)
    if not directory.is_dir():
        return {"present": False}
    manifest: dict[str, str] = {}
    total_bytes = 0
    for item in sorted(directory.glob(pattern)):
        if item.is_symlink() or not item.is_file():
            continue
        digest = _sha256_file(item)
        if digest is None:
            continue
        manifest[item.name] = digest
        try:
            total_bytes += item.stat().st_size
        except OSError:
            pass
    return {
        "present": True,
        "files": len(manifest),
        "bytes": total_bytes,
        "manifest_sha256": _sha256_bytes(_canonical(manifest)),
    }


def build_digest_detail(
    *,
    ledger_date: str,
    org_events_file: Path | str,
    consequence_file: Path | str,
    trigger_archive_dir: Path | str,
) -> dict[str, Any]:
    """Bounded ``detail`` payload for the daily digest-anchor event.

    Depth stays within the recorder's sanitize envelope (<=5), every value is
    JSON-native and finite, and no key matches the secret-key redaction
    family — asserted by the Phase-1 tests.
    """
    return {
        "action": "digest_anchor",
        "ledger_date": ledger_date,
        "ledgers": {
            "org_events": digest_ledger_file(org_events_file),
            "consequence": digest_ledger_file(consequence_file),
            "trigger_archive": digest_ledger_dir(trigger_archive_dir),
        },
    }


def digest_trial_id(run_date: str) -> str:
    """Day-bounded taxonomy trial id: ``evt-digest-anchor-<yyyymmdd>``."""
    compact = run_date.replace("-", "")
    if not re.fullmatch(r"\d{8}", compact):
        raise AnchorError("The digest-anchor run date must be YYYY-MM-DD.")
    return f"evt-digest-anchor-{compact}"


def append_digest_trial(
    store_root: Path | str,
    detail: dict[str, Any],
    *,
    run_date: str,
) -> dict[str, Any]:
    """Append the day's digest-anchor event via the sanctioned recorder seam.

    The store root is EXPLICIT (never the ``CABINET_EVIDENCE_DIR`` env
    fallback) and the component identity is passed in full so nothing rides
    the env-fed provenance channel. One event per run; the daily schedule
    makes that one event per day (design R-13).
    """
    # Lazy import: the sanctioned producer seam. Collection/checking above
    # must stay importable and usable without touching germline code.
    from framework.evidence.recorder import EvidenceRecorder

    recorder = EvidenceRecorder(Path(store_root))
    context = recorder.trace(digest_trial_id(run_date), surface="system")
    return recorder.append(
        context,
        phase="system",
        status="succeeded",
        actor={"kind": "system", "id": "digest-anchor"},
        component={"name": "digest-anchor", "version": "1", "commit": "unset"},
        detail=detail,
        links=[],
    )


# ---------------------------------------------------------------------------
# Captain receipt — plain English, aggregate-only
# ---------------------------------------------------------------------------

def receipt_text(
    current: dict[str, Any],
    check: dict[str, Any],
    *,
    run_date: str,
    digest_event: str,
    exported: list[str],
    skipped: list[str],
    notes: list[str] | None = None,
) -> str:
    """The daily Telegram receipt. Aggregate counts and digest prefixes only —
    no trial ids, no event content, plain English (no cabinet jargon)."""
    trials = current.get("trials") or {}
    marks = (current.get("watermarks") or {}).get("rows") or {}
    receipts = (current.get("purge_receipts") or {}).get("count") or 0
    labels = current.get("captain_labels") or {}
    tracked_labels = sum(1 for value in labels.values() if value)
    lines = [f"Evidence anchor — {run_date}"]
    lines.append(
        f"Snapshot: {len(trials)} evidence trials, {len(marks)} verifier "
        f"watermarks, {receipts} deletion receipts, {tracked_labels} Captain "
        f"ledgers tracked."
    )
    if check.get("first_run"):
        lines.append("Integrity: first anchor — nothing earlier to compare against.")
    elif check.get("ok"):
        lines.append(
            f"Integrity vs last anchor: OK — nothing rolled back, altered, or "
            f"missing across {check.get('checked_trials', 0)} recorded trials."
        )
    else:
        kinds = ", ".join(sorted({f["kind"] for f in check.get("findings", [])}))
        lines.append(
            f"⚠️ Integrity ALERT: {len(check.get('findings', []))} finding(s) — "
            f"{kinds}. The evidence record no longer matches yesterday's "
            f"anchor; treat the store as tampered until reviewed."
        )
    for note in notes or []:
        if note == "control_changed":
            lines.append("Note: the store's retention/diagnostic settings changed since the last anchor.")
        elif note == "captain_labels_changed":
            lines.append("Note: a tracked Captain ledger changed since the last anchor.")
        else:
            lines.append(f"Note: {note}.")
    lines.append(f"Daily ledger checksums: {digest_event}.")
    digest = str(current.get("record_digest") or "")[:12]
    exported_text = ", ".join(exported) if exported else "none"
    skipped_text = ", ".join(skipped) if skipped else "none"
    lines.append(f"Record {digest}… · stored: {exported_text} · skipped: {skipped_text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HP-3 label re-count — append-only proof + store cross-join (read-only)
# ---------------------------------------------------------------------------

LABELS_JOURNAL_BASENAME = "governance-labels.jsonl"
# Deliberate duplicates of the Captain CLI's literals (this module shares no
# code with cabinet/scripts/governance-review.py by design — verifier-style);
# pinned equal by cabinet/scripts/tests/test_label_channel_auth.py.
LABEL_DIGEST_SCHEMA = "cabinet.governance-label-digest/v1"
LABEL_ACTION_MARKER = "governance_review_label"
LABEL_HUMAN_SOURCE = "verdict_human"
LABEL_CHANNEL_JOURNAL_KEY = "channel"       # journal digest-row mirror key
LABEL_CHANNEL_DETAIL_KEY = "label_channel"  # store-event detail key
RECOUNT_SCHEMA = "cabinet.evidence-label-recount/v1"


def _newline_prefix_digests(data: bytes) -> dict[str, int]:
    """{sha256hex: byte_length} for every newline-boundary prefix of the
    journal, the empty prefix and the whole file included.

    collect_anchor records the journal's whole-file sha256 WITHOUT a byte
    length, so append-only verification must scan candidate prefixes; label
    journals are small and Captain-append-bounded (a hard per-session label
    cap), so the scan is cheap. Journal lines are written newline-terminated
    in one append each, so every historical anchor point is a newline
    boundary; the whole-file digest is included as well so an anchor taken
    against the exact current bytes always matches."""
    digests: dict[str, int] = {hashlib.sha256(b"").hexdigest(): 0}
    running = hashlib.sha256()
    start = 0
    while True:
        cut = data.find(b"\n", start)
        if cut == -1:
            break
        running.update(data[start:cut + 1])
        digests.setdefault(running.copy().hexdigest(), cut + 1)
        start = cut + 1
    if start < len(data):
        running.update(data[start:])
        digests.setdefault(running.hexdigest(), len(data))
    return digests


def _purge_receipt_named(store_root: Path | str, trial_id: str) -> bool:
    """Purge-receipt name check (check_anchor's rule, applied store-side):
    a receipt file ``purge-<sha16(trial)>-*.json`` excuses a missing trial."""
    receipts_dir = Path(store_root) / "purge-receipts"
    if not receipts_dir.is_dir():
        return False
    prefix = ("purge-"
              + hashlib.sha256(trial_id.encode("utf-8")).hexdigest()[:16]
              + "-")
    try:
        return any(
            path.name.startswith(prefix)
            for path in receipts_dir.glob("purge-*.json")
            if not path.is_symlink() and path.is_file())
    except OSError:
        return False


def _parse_jsonl_dicts(data: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _raw_trial_events(store_root: Path | str,
                      trial_id: str) -> list[dict[str, Any]] | None:
    """Raw rows of one trial ledger; ``None`` when the trial dir is absent.

    RAW means hash-membership data only: no signature check, no signing
    key, no verifier (verify advances watermarks — a side effect this
    read-only verb must not have). Detecting a FORGED-but-hash-consistent
    store event is therefore out of scope here; the verified leg over the
    same join is the calibration shadow's verify_pairs."""
    if not _TRIAL_DIR_RE.fullmatch(trial_id):
        return None
    trial_dir = Path(store_root) / "trials" / trial_id
    if trial_dir.is_symlink() or not trial_dir.is_dir():
        return None
    ledger = trial_dir / "events.jsonl"
    try:
        if ledger.is_symlink() or not ledger.is_file():
            return []
        data = ledger.read_bytes()
    except OSError:
        return []
    return _parse_jsonl_dicts(data)


def recount_labels(
    journal_path: Path | str | None,
    anchor_records: list[dict[str, Any]],
    *,
    store_root: Path | str | None = None,
    journal_name: str = LABELS_JOURNAL_BASENAME,
) -> dict[str, Any]:
    """HP-3 re-count: prove the label journal append-only against the FULL
    anchor history and cross-join it with the evidence store. Read-only
    everywhere; returns a drill-style result (never raises on data trouble).

    Two legs:

    * APPEND-ONLY PROOF — every historically anchored sha256 of the journal
      (``record.captain_labels[<journal_name>]`` across ``anchor_records``,
      oldest first) must match some newline-boundary prefix of the CURRENT
      journal, with matched prefix lengths monotonically nondecreasing over
      anchor time. A digest with no matching prefix means rows were forged,
      altered, or removed AFTER anchoring → ``label_journal_rewritten``. A
      later anchor matching a SHORTER prefix than an earlier one →
      ``label_journal_prefix_regression``. Journal gone while anchors carry
      digests → ``label_journal_missing``.
    * STORE CROSS-JOIN (skipped honestly when no store is given) — every
      journal digest row's ``event_hashes`` must exist in its trial's raw
      ledger (else ``label_journal_row_unbacked``; a purge receipt excuses a
      purged trial), a row claiming a channel must match the store's
      hash-covered ``detail.label_channel`` on every digest event (else
      ``label_channel_mismatch``), and every in-store Captain label event
      (``action=governance_review_label`` + ``source=verdict_human``) must
      appear in some journal row (else ``store_label_unjournaled`` — either
      a forged in-store label or the trace of a loudly-degraded journal
      export; match it against that day's session transcript).

    THREAT HONESTY: this is after-the-fact detection, not prevention. The
    journal legs bind to the EXTERNAL anchor history, which a same-OS-user
    forger cannot rewrite once exported off-box; but until HP-1 isolates
    the signing key the same user can forge store events AND the not-yet-
    anchored journal tail together, and root can forge everything
    everywhere. The store leg reads RAW rows (hash membership only — never
    the signing key, never the verifier)."""
    findings: list[dict[str, Any]] = []
    notes: list[str] = []
    counts = {
        "anchored_digests": 0, "prefix_matched": 0,
        "journal_rows": 0, "digest_rows": 0,
        "rows_store_backed": 0, "rows_excused_purged": 0,
        "legacy_rows": 0,
        "store_labels_seen": 0, "store_labels_journaled": 0,
    }

    data: bytes | None = None
    if journal_path is None:
        notes.append("journal_unconfigured")
    else:
        journal = Path(journal_path)
        try:
            if journal.is_symlink():
                notes.append("journal_symlink_refused")
            elif not journal.is_file():
                notes.append("journal_absent")
            else:
                data = journal.read_bytes()
        except OSError:
            notes.append("journal_unreadable")

    anchored: list[tuple[str, str]] = []
    for record in anchor_records:
        if not isinstance(record, dict):
            continue
        labels = record.get("captain_labels") or {}
        digest = labels.get(journal_name) if isinstance(labels, dict) else None
        if isinstance(digest, str) and digest:
            anchored.append((str(record.get("generated_at") or ""), digest))
    counts["anchored_digests"] = len(anchored)

    if anchored and data is None:
        findings.append({"kind": "label_journal_missing",
                         "anchored_digests": len(anchored)})
    elif data is not None:
        boundaries = _newline_prefix_digests(data)
        previous_length = -1
        for generated_at, digest in anchored:
            length = boundaries.get(digest)
            if length is None:
                findings.append({
                    "kind": "label_journal_rewritten",
                    "anchor_generated_at": generated_at,
                    "anchored_sha256": digest,
                })
                continue
            counts["prefix_matched"] += 1
            if length < previous_length:
                findings.append({
                    "kind": "label_journal_prefix_regression",
                    "anchor_generated_at": generated_at,
                    "matched_length": length,
                    "previous_length": previous_length,
                })
            previous_length = max(previous_length, length)

    journal_rows = _parse_jsonl_dicts(data) if data is not None else []
    counts["journal_rows"] = len(journal_rows)
    digest_rows = [row for row in journal_rows
                   if row.get("schema") == LABEL_DIGEST_SCHEMA]
    counts["digest_rows"] = len(digest_rows)

    store = Path(store_root) if store_root is not None else None
    if store is None or store.is_symlink() or not (store / "trials").is_dir():
        notes.append("store_cross_join_skipped")
    else:
        journaled_hashes: set = set()
        for row in digest_rows:
            for value in row.get("event_hashes") or []:
                if isinstance(value, str):
                    journaled_hashes.add(value)
        events_cache: dict[str, Any] = {}
        for row in digest_rows:
            trial_id = str(row.get("trial_id") or "")
            hashes = [h for h in (row.get("event_hashes") or [])
                      if isinstance(h, str)]
            if trial_id not in events_cache:
                events_cache[trial_id] = _raw_trial_events(store, trial_id)
            events = events_cache[trial_id]
            if events is None:
                if _purge_receipt_named(store, trial_id):
                    counts["rows_excused_purged"] += 1
                else:
                    findings.append({"kind": "label_journal_row_unbacked",
                                     "trial_id": trial_id,
                                     "reason": "trial_missing"})
                continue
            trial_hashes = {e.get("event_hash") for e in events
                            if isinstance(e.get("event_hash"), str)}
            if not hashes or not set(hashes) <= trial_hashes:
                findings.append({"kind": "label_journal_row_unbacked",
                                 "trial_id": trial_id,
                                 "reason": "event_hashes_missing"})
                continue
            counts["rows_store_backed"] += 1
            if LABEL_CHANNEL_JOURNAL_KEY not in row:
                counts["legacy_rows"] += 1  # pre-HP-3 row: honest, no claim
            else:
                claimed = row.get(LABEL_CHANNEL_JOURNAL_KEY)
                by_hash = {
                    e.get("event_hash"):
                        (e.get("detail") or {}).get(LABEL_CHANNEL_DETAIL_KEY)
                    for e in events if isinstance(e.get("detail"), dict)}
                if any(by_hash.get(h) != claimed for h in hashes):
                    findings.append({"kind": "label_channel_mismatch",
                                     "trial_id": trial_id})

        trials_dir = store / "trials"
        for path in sorted(trials_dir.iterdir()):
            if path.is_symlink() or not path.is_dir():
                continue
            if not _TRIAL_DIR_RE.fullmatch(path.name):
                continue
            if path.name in events_cache:
                events = events_cache[path.name] or []
            else:
                events = _raw_trial_events(store, path.name) or []
            for event in events:
                detail = (event.get("detail")
                          if isinstance(event.get("detail"), dict) else {})
                if (detail.get("action") != LABEL_ACTION_MARKER
                        or detail.get("source") != LABEL_HUMAN_SOURCE):
                    continue
                counts["store_labels_seen"] += 1
                if event.get("event_hash") in journaled_hashes:
                    counts["store_labels_journaled"] += 1
                else:
                    findings.append({
                        "kind": "store_label_unjournaled",
                        "trial_id": path.name,
                        "sequence": event.get("sequence"),
                    })

    return {
        "schema": RECOUNT_SCHEMA,
        "generated_at": _utc_now(),
        "ok": not findings,
        "findings": findings,
        "counts": counts,
        "notes": notes,
    }
