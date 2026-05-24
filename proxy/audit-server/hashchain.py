"""
proxy/audit-server/hashchain.py — FW-097 hash-chain append + verify.

WHY THIS EXISTS: Every audit log entry must be tamper-evident. We achieve this
with a sha256 hash-chain: each entry's integrity.entry_hash covers all entry
fields EXCEPT entry_hash itself; integrity.prev_hash references the prior
entry's entry_hash. Tampering any entry breaks the chain at that point.

DESIGN:
  - sha256 locked per CTO #1 (Web-Crypto browser-verifier compatibility).
  - genesis prev_hash = "0" * 64 (64 zero chars, one hex sha256 worth).
  - canonical JSON = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    with entry_hash excluded before hashing (field removed, not set to null).
  - append() writes the complete entry including integrity{} to the SSOT file.
  - verify() walks the full file; returns (ok: bool, first_bad_index: int|None).

FAIL-SAFE: hashchain operations never crash the caller — exceptions are caught
and surfaced as False/error return (audit must never crash the proxy or server).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
from typing import Any

logger = logging.getLogger(__name__)

# SSOT audit log root — distinct from the FW-096 proxy-audit input stream.
# Input: LITELLM_AUDIT_LOG_ROOT/proxy-audit/<slug>.jsonl  (FW-096 writes)
# Output (SSOT): LITELLM_AUDIT_LOG_ROOT/audit/<slug>.jsonl  (FW-097 writes)
_AUDIT_LOG_ROOT = pathlib.Path(
    os.environ.get(
        "LITELLM_AUDIT_LOG_ROOT",
        os.path.join(os.path.dirname(__file__), "..", "logs"),
    )
)

GENESIS_HASH = "0" * 64  # genesis prev_hash sentinel (64 hex zeroes = valid sha256 placeholder)


def _ssot_path(cabinet_id: str) -> pathlib.Path:
    """Return the SSOT JSONL path for this cabinet's audit log."""
    slug = cabinet_id or "unknown"
    return _AUDIT_LOG_ROOT / "audit" / f"{slug}.jsonl"


def _canonical_json(obj: dict[str, Any]) -> bytes:
    """
    Deterministic JSON encoding for hashing.
    sort_keys=True ensures field order is stable regardless of insertion order.
    entry_hash MUST be excluded by the caller before invoking this.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_entry_hash(entry_without_hash: dict[str, Any]) -> str:
    """sha256 of canonical JSON of entry with entry_hash field absent."""
    return hashlib.sha256(_canonical_json(entry_without_hash)).hexdigest()


def _last_entry_hash(cabinet_id: str) -> str:
    """
    Read the last entry_hash from the SSOT file.
    Returns GENESIS_HASH if no entries exist yet.
    """
    path = _ssot_path(cabinet_id)
    if not path.exists():
        return GENESIS_HASH
    last_hash = GENESIS_HASH
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                last_hash = entry.get("integrity", {}).get("entry_hash", GENESIS_HASH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("hashchain._last_entry_hash: error reading %s: %s", path, exc)
    return last_hash


def append(entry_body: dict[str, Any]) -> dict[str, Any]:
    """
    Attach integrity fields and append entry_body to the SSOT file.

    entry_body must NOT already contain an 'integrity' key — this function
    computes and injects it. Returns the full entry dict (with integrity{}).

    Never raises — failures are logged and the original entry_body returned
    as-is so the caller can choose a fallback path.
    """
    cabinet_id = entry_body.get("cabinet_id", "unknown")
    try:
        prev_hash = _last_entry_hash(cabinet_id)

        # Build integrity block — entry_hash covers everything EXCEPT itself
        entry_for_hash = {**entry_body, "integrity": {"prev_hash": prev_hash}}
        # Remove entry_hash from the to-be-hashed object (it doesn't exist yet,
        # but belt-and-suspenders: ensure the key is absent)
        entry_for_hash.get("integrity", {}).pop("entry_hash", None)
        entry_hash = compute_entry_hash(entry_for_hash)

        full_entry = {
            **entry_body,
            "integrity": {
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            },
        }

        # Write to SSOT — append-only
        path = _ssot_path(cabinet_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(full_entry, separators=(",", ":")) + "\n")

        return full_entry
    except Exception as exc:  # noqa: BLE001 — audit must never crash the server
        logger.warning("hashchain.append: failed for cabinet %s: %s", cabinet_id, exc)
        return entry_body


def verify(cabinet_id: str) -> tuple[bool, int | None]:
    """
    Walk the SSOT log for cabinet_id and verify the hash chain.

    Returns (True, None) if the chain is intact.
    Returns (False, first_bad_index) on the first broken link.

    Pseudonymized entries (those with pseudonym_marker_hash) still carry their
    original entry_hash — the chain is verified using the stored entry_hash
    directly, which was computed before pseudonymization and preserved per AC#8.
    The re-computation for pseudonymized entries is skipped; the chain link uses
    the stored entry_hash as-is (it was already verified at append time).
    """
    path = _ssot_path(cabinet_id)
    if not path.exists():
        return True, None  # empty log = trivially valid

    prev_hash = GENESIS_HASH
    try:
        with path.open("r", encoding="utf-8") as fh:
            for idx, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                integrity = entry.get("integrity", {})
                stored_prev = integrity.get("prev_hash", "")
                stored_entry_hash = integrity.get("entry_hash", "")

                # Check prev_hash linkage
                if stored_prev != prev_hash:
                    logger.warning(
                        "hashchain.verify: prev_hash mismatch at entry %d for %s", idx, cabinet_id
                    )
                    return False, idx

                # Recompute entry_hash (skip for pseudonymized entries — original
                # hash was computed pre-pseudonymization and cannot be reproduced)
                if "pseudonym_marker_hash" not in entry:
                    entry_for_hash = {k: v for k, v in entry.items() if k != "integrity"}
                    entry_for_hash["integrity"] = {"prev_hash": stored_prev}
                    computed = compute_entry_hash(entry_for_hash)
                    if computed != stored_entry_hash:
                        logger.warning(
                            "hashchain.verify: entry_hash mismatch at entry %d for %s", idx, cabinet_id
                        )
                        return False, idx
                else:
                    # Pseudonymized (erased) entry: the original entry_hash can't be
                    # recomputed (content changed post-erasure), so the chain link trusts
                    # the stored entry_hash — BUT the pseudonym_marker_hash MUST match the
                    # current pseudonymized content, else post-erasure tampering goes
                    # undetected (Spec 052 AC#8/#9; CTO review finding #2). marker =
                    # sha256(entry minus pseudonym_marker_hash), same canonical encoding
                    # erasure.py used to compute it.
                    stored_marker = entry.get("pseudonym_marker_hash", "")
                    marker_body = {k: v for k, v in entry.items() if k != "pseudonym_marker_hash"}
                    computed_marker = hashlib.sha256(_canonical_json(marker_body)).hexdigest()
                    if computed_marker != stored_marker:
                        logger.warning(
                            "hashchain.verify: pseudonym_marker_hash mismatch at entry %d for %s", idx, cabinet_id
                        )
                        return False, idx

                prev_hash = stored_entry_hash
    except Exception as exc:  # noqa: BLE001
        logger.warning("hashchain.verify: exception at cabinet %s: %s", cabinet_id, exc)
        return False, None

    return True, None
