"""Shared fixtures for the COG-2 unit-2 gate sims (§8 sim 2 + sim 3).

PURE, no DB: builds valid v2 envelopes (validate_any-passing) carrying the
observations/observation@1 payload and writes them to a JSONL the production
envelope-file adapter (§5.2a) reads. Sims 2 and 3 therefore traverse the SAME
fold + query code as any envelope-durable source — no test-only ingest seam
(C-F4/C-F9 discipline). The two clocks are independent here: occurred_at is the
valid time (source axis), recorded_at the transaction time (observation axis).

Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §5.2a.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Crockford base32 (ULID_RE-legal: no I/L/O/U) and lowercase hex (uuid4-hex).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_HEX = "0123456789abcdef"

# The seam's declared producers (mirror cortex-source-trust.v1.yml / the enum).
# Component identities, never officer identities (the G-F4 never-a-score latch).
PRIMARY = "observations/primary"
SECONDARY = "observations/secondary"

# Inline versioned trust table — the sims never read the outbox file; this
# mirrors the extended cortex-source-trust.v1.yml producers at table_version 1.
TRUST_TABLE = {"table_version": 1, "producers": {
    "officer_tasks/outbox-relay": 900000,
    PRIMARY: 800000,
    SECONDARY: 500000,
}}

_OBS_SCHEMA = "observations/observation@1"


def make_ulid(seed: int) -> str:
    """A deterministic 26-char Crockford-base32 id (fixtures are pinned, so
    ids must be stable across runs — never a random ULID)."""
    v = (seed & 0xFFFFFFFF) or 1
    out = []
    for _ in range(26):
        v = (v * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(_CROCKFORD[(v >> 7) % 32])
    return "".join(out)


def make_cid(seed: int) -> str:
    """A deterministic 32-char lowercase-hex correlation id."""
    v = (seed * 40503 + 7) & 0xFFFFFFFF or 1
    out = []
    for _ in range(32):
        v = (v * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(_HEX[(v >> 7) % 16])
    return "".join(out)


def envelope(*, seed: int, producer: str, subject: str, state: str,
             occurred_at: str, recorded_at: str, cabinet_id: str = "main",
             correlation_seed: int | None = None, scope_kind: str = "cabinet",
             classification: str = "system",
             payload_schema: str = _OBS_SCHEMA) -> dict:
    """A valid v2 envelope carrying an observations/observation@1 payload.

    occurred_at (source/valid time) and recorded_at (observation/transaction
    time) are set INDEPENDENTLY — that independence is the whole point of the
    two-axis proof (the outbox stream is single-clock)."""
    return {
        "schema_version": "cabinet-envelope/v2",
        "event_id": make_ulid(seed),
        "event_type": "observations.recorded",
        "occurred_at": occurred_at,
        "recorded_at": recorded_at,
        "cabinet_id": cabinet_id,
        "scope_kind": scope_kind,
        "producer": producer,
        "correlation_id": make_cid(seed if correlation_seed is None else correlation_seed),
        "idempotency_key": f"obs:{subject}:{seed}",
        "classification": classification,
        "payload_schema": payload_schema,
        "payload": {"subject": subject, "state": state},
    }


def write_jsonl(path: Path, envelopes: list[dict]) -> Path:
    """Write envelopes as one canonical JSONL line each (the adapter's input)."""
    path = Path(path)
    path.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in envelopes),
        encoding="utf-8")
    return path
