"""framework.scheduler.serve — the ONE kernel-bound schedule loader (COG-4
§6.3/§7.3; the F1 law). EVERY public read of the schedule store routes through
`serve_schedule` — there is exactly ONE public entry point in this module and
it binds through kernel.verified_single_read, so no serve path can return rows
it did not hash in the same read (F4 no-window) and no manifest-absent key can
skip a limb.

REFUSE limbs, in order (each raises ScheduleRefused — denial never
masquerades as an empty success):
  1. manifest unreadable/unparseable                       (kernel limb)
  2. `schedule_rows_hash` ABSENT or empty — MANDATORY-PRESENT (§6.3): the
     objectives `is not None and` skip-hole is CLOSED for this store; a
     manifest omitting its rows-hash can never serve unbound rows
                                                            (kernel limb)
  3. store unreadable/malformed                             (kernel limb)
  4. rows-hash mismatch over the RE-PARSED rows in FILE ORDER (A-m11) —
     tampered, partial, or REORDERED rows all refuse        (kernel limb)
  5. decision-row shape: every row carries the full §7.2 tuple with a legal
     decision                                               (domain limb)
  6. epoch completeness: every §7.2 epoch key present, the wake-input-hash
     key set exactly the §7.1 seven, the cutoff canonical   (domain limb)
  7. counts honesty: manifest counts match the served rows  (domain limb)
  8. snapshot-record binding: epoch.snapshot_hash == sha256 of the
     snapshot.json record bytes read ONCE here, and the record's
     wake_input_hashes echo the epoch's — a schedule cannot serve detached
     from the snapshot that produced it                     (domain limb)

The dispatcher (§7.3, W5) layers its LIVE checks (stale wake-inputs, authority
recheck, budget, freshness, idempotency) ON TOP of this loader — it serves
through here first, never around it.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u2.
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.projection.kernel import (is_canonical_cutoff,
                                         verified_single_read)
from framework.scheduler import model


class ScheduleRefused(Exception):
    """The schedule store refused to serve (a failed REFUSE limb): rebuild
    from the snapshot to recover — never serve unverified rows."""


def _limb_row_shape(manifest: dict, rows: list):
    for row in rows:
        if not isinstance(row, dict):
            return "schedule row is not an object"
        missing = [f for f in model.ROW_FIELDS if f not in row]
        if missing:
            return f"schedule row missing fields {missing}"
        if row["decision"] not in model.DECISIONS:
            return f"schedule row carries an unknown decision {row['decision']!r}"
    return None


def _limb_epoch(manifest: dict, rows: list):
    epoch = manifest.get("epoch")
    if not isinstance(epoch, dict):
        return "manifest epoch missing/not an object"
    missing = [k for k in model.EPOCH_KEYS if k not in epoch]
    if missing:
        return f"manifest epoch missing {missing}"
    wih = epoch.get("wake_input_hashes")
    if not isinstance(wih, dict) or set(wih) != set(model.WAKE_INPUT_HASH_KEYS):
        return ("manifest epoch wake_input_hashes keys != the §7.1 seven — "
                "refuse a partial epoch")
    if not is_canonical_cutoff(epoch.get("cutoff")):
        return (f"manifest epoch cutoff {epoch.get('cutoff')!r} is not "
                "canonical (a non-canonical cutoff fences open)")
    return None


def _limb_counts(manifest: dict, rows: list):
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        return "manifest counts missing/not an object"
    selected = sum(1 for r in rows
                   if r.get("decision") == model.DECISION_SELECT)
    expected = {"rows": len(rows), "selected": selected,
                "deferred": len(rows) - selected,
                "conflicts": len(manifest.get("conflicts") or [])}
    for key, value in expected.items():
        if counts.get(key) != value:
            return (f"manifest counts.{key}={counts.get(key)!r} does not "
                    f"match the served rows ({value}) — a forged count "
                    "cannot ride a valid rows-hash")
    return None


def _snapshot_binding_limb(cache_dir: Path, holder: dict):
    """Closure limb: read the snapshot RECORD exactly once, bind its hash to
    epoch.snapshot_hash and its wake_input_hashes to the epoch echo, and stash
    the parsed record for the caller (no second read after verification)."""
    def _limb(manifest: dict, rows: list):
        try:
            record_bytes = (cache_dir
                            / model.SNAPSHOT_RECORD_FILE).read_bytes()
        except OSError as exc:
            return (f"snapshot record unreadable ({type(exc).__name__}) — a "
                    "schedule cannot serve detached from its snapshot")
        epoch = manifest.get("epoch") or {}
        actual = model.sha256_hex(record_bytes)
        if epoch.get("snapshot_hash") != actual:
            return (f"epoch.snapshot_hash {str(epoch.get('snapshot_hash'))[:12]}… "
                    f"!= sha256(snapshot record) {actual[:12]}… — "
                    "stale/foreign snapshot record")
        try:
            record = json.loads(record_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return "snapshot record is not valid JSON"
        if not isinstance(record, dict) or \
                record.get("wake_input_hashes") != epoch.get("wake_input_hashes"):
            return ("snapshot record wake_input_hashes do not echo the "
                    "manifest epoch — mixed provenance refuses")
        holder["snapshot"] = record
        return None
    return _limb


def serve_schedule(cache_dir) -> dict:
    """THE public schedule read (F1 — the one loader). Returns
    {"schedule_rows_hash", "rows", "manifest", "snapshot"} where the rows ARE
    the rows that were hashed (single read, kernel (f)) and the snapshot is
    the hash-bound record. Raises ScheduleRefused on any limb."""
    cache_dir = Path(cache_dir)
    holder: dict = {}
    verified_hash, rows, manifest = verified_single_read(
        cache_dir,
        store_filename=model.SCHEDULE_FILE,
        manifest_filename=model.MANIFEST_FILE,
        store_hash_key=model.MANIFEST_ROWS_HASH_KEY,
        rows_hash=model.schedule_rows_hash,       # FILE-ORDER chain (§6.1(c))
        refuse=ScheduleRefused,
        extra_limbs=(_limb_row_shape, _limb_epoch, _limb_counts,
                     _snapshot_binding_limb(cache_dir, holder)),
    )
    return {"schedule_rows_hash": verified_hash, "rows": rows,
            "manifest": manifest, "snapshot": holder["snapshot"]}
