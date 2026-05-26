"""
proxy/audit-server/ingest.py — FW-097 proxy-audit stream ingestor.

WHY THIS EXISTS: FW-096's audit_logger.py writes per-request records to
  LITELLM_AUDIT_LOG_ROOT/proxy-audit/<slug>.jsonl
FW-097 must read that stream and transform each record into a Spec 052 entry,
then append it (with hash-chain) to the SSOT at
  LITELLM_AUDIT_LOG_ROOT/audit/<slug>.jsonl

This module is called by the scheduled ingest job (cron or direct invocation).
It is NOT the FastAPI server — it's the stream transformer.

TRANSFORM (per Final PINs):
  FW-096 field             → Spec 052 field
  ts                       → ts
  cabinet_id               → cabinet_id
  officer                  → actor.officer
  request_id               → subject.metadata.request_id
  model                    → cost.model
  provider                 → subject.metadata.provider
  tokens_in                → cost.tokens_in
  tokens_out               → cost.tokens_out
  cost_raw_usd             → cost.cost_raw_usd
  cost_marked_up_usd       → cost.cost_marked_up_usd
  request_pct_of_cap       → DROP or subject.metadata (no Spec 052 slot)
  status                   → DROP or subject.metadata (no Spec 052 slot)
  entry_id (synthesized)   → entry_id (UUIDv4 synthesized here)
  stream = "proxy"         → stream
  event_type = "llm_request" → event_type

FAIL-SAFE: ingest errors are logged; the ingestion loop continues on any
single-entry error. Ingest never crashes — it is wrapped with broad except.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Any

from hashchain import append as chain_append
from validator import validate_and_minimize, ValidationError, is_valid_cabinet_id

logger = logging.getLogger(__name__)

# Input stream root — same env var FW-096 writes to (must match)
_AUDIT_LOG_ROOT = pathlib.Path(
    os.environ.get(
        "LITELLM_AUDIT_LOG_ROOT",
        os.path.join(os.path.dirname(__file__), "..", "logs"),
    )
)

# Cursor file: tracks last-processed byte offset per slug so repeated runs
# don't reprocess already-ingested lines (lightweight seek-based dedup)
_CURSOR_DIR = _AUDIT_LOG_ROOT / "audit" / ".cursors"


def _cursor_path(slug: str) -> pathlib.Path:
    return _CURSOR_DIR / f"{slug}.cursor"


def _read_cursor(slug: str) -> int:
    path = _cursor_path(slug)
    if path.exists():
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except Exception:  # noqa: BLE001
            pass
    return 0


def _write_cursor(slug: str, offset: int) -> None:
    _CURSOR_DIR.mkdir(parents=True, exist_ok=True)
    _cursor_path(slug).write_text(str(offset), encoding="utf-8")


def _transform_fw096_to_052(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a single FW-096 proxy-audit record into a Spec 052 entry.

    FW-096 fields request_pct_of_cap + status have no Spec 052 slot —
    they are carried under subject.metadata per Final PINs.
    """
    cabinet_id = str(raw.get("cabinet_id", "unknown"))
    officer = str(raw.get("officer", "unknown"))
    model = str(raw.get("model", "unknown"))
    ts = raw.get("ts") or datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Cost block
    cost: dict[str, Any] = {
        "model": model,
        "tokens_in": int(raw.get("tokens_in", 0)),
        "tokens_out": int(raw.get("tokens_out", 0)),
        "cost_raw_usd": float(raw.get("cost_raw_usd", 0.0)),
        "cost_marked_up_usd": float(raw.get("cost_marked_up_usd", 0.0)),
    }

    # Subject metadata — carries FW-096-only fields that have no Spec 052 slot
    metadata: dict[str, Any] = {
        "request_id": str(raw.get("request_id", "")),
        "provider": str(raw.get("provider", "unknown")),
    }
    # Carry FW-096-only fields as metadata (per Final PINs: drop or carry as metadata)
    if "request_pct_of_cap" in raw:
        metadata["request_pct_of_cap"] = raw["request_pct_of_cap"]
    if "status" in raw:
        metadata["fw096_status"] = raw["status"]

    entry: dict[str, Any] = {
        "ts": ts,
        "cabinet_id": cabinet_id,
        "entry_id": str(uuid.uuid4()),
        "stream": "proxy",
        "event_type": "llm_request",
        "actor": {
            "officer": officer,
            "captain": False,
        },
        "subject": {
            "type": "tool_call",
            "target": model,
            "metadata": metadata,
        },
        "cost": cost,
    }

    return entry


def ingest_slug(slug: str) -> dict[str, int]:
    """
    Ingest new lines from the FW-096 proxy-audit stream for one cabinet slug.

    Returns {"ingested": N, "skipped": N, "errors": N}.
    """
    # #237 write-side chokepoint: `slug` reaches THREE path-builds — proxy-audit/<slug>.jsonl
    # (read, below), .cursors/<slug>.cursor (_cursor_path), and audit/<slug>.jsonl (hashchain
    # append). It enters from ingest_all as jsonl_file.stem (filesystem-derived) and bypasses the
    # #236 endpoint validators entirely, so validate it ONCE here — before any path is built — to
    # cover all three builds + any future caller. A non-slug value (separator, "..", uppercase,
    # empty) is a traversal / cross-cabinet-escape surface; skip + log rather than write a bad path.
    if not is_valid_cabinet_id(slug):
        logger.warning("ingest_slug: refusing non-slug cabinet id %r — skipped, no path built", slug)
        return {"ingested": 0, "skipped": 0, "errors": 0}

    proxy_audit_path = _AUDIT_LOG_ROOT / "proxy-audit" / f"{slug}.jsonl"
    if not proxy_audit_path.exists():
        return {"ingested": 0, "skipped": 0, "errors": 0}

    offset = _read_cursor(slug)
    ingested = 0
    skipped = 0
    errors = 0

    try:
        with proxy_audit_path.open("r", encoding="utf-8") as fh:
            fh.seek(offset)
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    offset += len(line.encode("utf-8"))
                    continue
                try:
                    raw = json.loads(stripped)
                    entry = _transform_fw096_to_052(raw)
                    try:
                        entry = validate_and_minimize(entry)
                    except ValidationError as ve:
                        logger.warning("ingest: validation rejected entry for %s: %s", slug, ve)
                        skipped += 1
                        offset += len(line.encode("utf-8"))
                        continue
                    # #237: the SSOT write below (chain_append -> hashchain._ssot_path) is keyed
                    # on entry['cabinet_id'] (from the RAW FW-096 record), NOT the validated
                    # `slug`. Require them to match so the SSOT path is ALWAYS the already-
                    # validated slug — a record whose internal cabinet_id differs is a traversal
                    # attempt or a cross-cabinet/tampered record; skip it (hashchain.append is the
                    # backstop, but skipping here keeps the ingested/skipped counts honest).
                    if entry.get("cabinet_id") != slug:
                        logger.warning("ingest: record cabinet_id %r != file slug %r — skipped",
                                       entry.get("cabinet_id"), slug)
                        skipped += 1
                        offset += len(line.encode("utf-8"))
                        continue
                    appended = chain_append(entry)
                    if appended.get("integrity", {}).get("entry_hash"):
                        ingested += 1
                    else:
                        # append wrote nothing (its own #237 guard refused, or a fail-safe error):
                        # never count it as ingested. Holds the count honest if the upstream
                        # slug==cabinet_id invariant ever weakens.
                        logger.warning("ingest: chain_append wrote nothing for %s — counted as error", slug)
                        errors += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("ingest: error processing line for %s: %s", slug, exc)
                    errors += 1
                offset += len(line.encode("utf-8"))
        _write_cursor(slug, offset)
    except Exception as exc:  # noqa: BLE001
        logger.error("ingest: fatal error for slug %s: %s", slug, exc)
        errors += 1

    return {"ingested": ingested, "skipped": skipped, "errors": errors}


def ingest_all() -> dict[str, Any]:
    """
    Ingest all cabinet slugs found in the proxy-audit directory.
    Returns a summary dict keyed by slug.
    """
    proxy_audit_dir = _AUDIT_LOG_ROOT / "proxy-audit"
    if not proxy_audit_dir.exists():
        logger.info("ingest_all: proxy-audit directory not found at %s", proxy_audit_dir)
        return {}

    results: dict[str, Any] = {}
    for jsonl_file in proxy_audit_dir.glob("*.jsonl"):
        slug = jsonl_file.stem
        try:
            results[slug] = ingest_slug(slug)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest_all: error for slug %s: %s", slug, exc)
            results[slug] = {"ingested": 0, "skipped": 0, "errors": 1}

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = ingest_all()
    print(json.dumps(summary, indent=2))
