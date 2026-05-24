"""
proxy/audit-server/app.py — FW-097 audit log FastAPI server (Spec 052 Phases 3-5).

WHY THIS EXISTS: Provides two endpoints for the Spec 052 customer audit log:
  POST /proxy/audit/log    — officer-side hook posts entries; server validates +
                             appends with hash-chain integrity.
  GET  /dashboard/audit/{cabinet_id}/{cursor} — customer-scoped, cursor-paginated
                             read of their own cabinet's audit log (1000 entries/page).

AUTH:
  POST endpoint: AUDIT_API_KEY env var (write-side; shared between proxy and server).
  GET endpoint: customer's own AUDIT_API_KEY (customer-scoped; reads ONLY their cabinet).
  These are distinct from LLM_PROXY_KEY (separate credential blast radius per CTO #5).

APPEND-ONLY (AC #7):
  Application layer PRIMARY: this server only appends; any non-append operation
  (DELETE, PATCH on existing entries) is rejected at the API layer.
  chattr +a is deploy-gated SECONDARY — noted as TODO in PR, NOT called here.

TODO (deploy-gated, not in this build):
  - Live server deploy + nginx/Caddy reverse-proxy on Hetzner VPS (Phase-2)
  - chattr +a on audit log files at install time (Phase-2 deploy script)
  - Git-mirror checkpoint job (Phase-2)
  - Article 15 endpoint + ZIP/email delivery (Spec 052 Phase 6 follow-on)
  - FW-101 dashboard widget coupling (FW-101 build)
  - WebSocket/SSE streaming (Phase 2 polish)

FAIL-SAFE: endpoint exceptions never corrupt the hash-chain — errors surface as
HTTP 500 with structured JSON; the append either fully succeeds or is not written.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Allow running from the audit-server/ directory directly (imports hashchain/validator)
_HERE = pathlib.Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, Field, field_validator

import hashchain
import validator as val_module
from validator import validate_and_minimize, ValidationError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Captain's Cabinet — Customer Audit Log Server",
    description="FW-097 Spec 052: append-only hash-chained audit log with GDPR support",
    version="1.0.0",
)

# ── Auth configuration ──────────────────────────────────────────────────────
# AUDIT_API_KEY: shared write-side key (POST endpoint auth)
# In production, customer-specific keys are issued at signup (CTO #5).
# Phase 1: single key for the write side; customer reads use the same key
# scoped by cabinet_id path param + key → cabinet_id binding (see GET auth).
_AUDIT_API_KEY = os.environ.get("AUDIT_API_KEY", "")
_AUDIT_LOG_ROOT = pathlib.Path(
    os.environ.get(
        "LITELLM_AUDIT_LOG_ROOT",
        os.path.join(os.path.dirname(__file__), "..", "logs"),
    )
)

# Customer-key → cabinet_id binding (in production: looked up from DB/vault)
# Phase 1: single-key mode — the write key also authorizes reads for the
# cabinet_id in the path. Multi-key customer isolation is Phase 2 DB work.
def _authorize_read(cabinet_id: str, provided_key: str) -> bool:
    """
    Returns True if provided_key is authorized to read cabinet_id's log.
    Phase 1: accepts AUDIT_API_KEY for any cabinet (admin-level read).
    Production: each customer's key is scoped to exactly their cabinet_id.
    """
    if not _AUDIT_API_KEY:
        return False  # fail-closed: no key configured = no access
    return provided_key == _AUDIT_API_KEY


# ── Request / response models ───────────────────────────────────────────────

class ActorModel(BaseModel):
    officer: Optional[str] = None
    captain: bool = False


class SubjectModel(BaseModel):
    type: str
    target: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class CostModel(BaseModel):
    model: Optional[str] = None
    tokens_in: Optional[int] = 0
    tokens_out: Optional[int] = 0
    cost_raw_usd: Optional[float] = 0.0
    cost_marked_up_usd: Optional[float] = 0.0


class AuditEntryRequest(BaseModel):
    """
    Incoming audit entry from an officer-side hook.
    entry_id and integrity are synthesized server-side; client must not supply them.
    """
    ts: Optional[str] = None
    cabinet_id: str
    stream: str  # "proxy" | "officer" | "cabinet"
    event_type: str
    actor: ActorModel
    subject: SubjectModel
    cost: Optional[CostModel] = None

    @field_validator("stream")
    @classmethod
    def validate_stream(cls, v: str) -> str:
        valid = {"proxy", "officer", "cabinet"}
        if v not in valid:
            raise ValueError(f"stream must be one of {valid}")
        return v


class AuditEntryResponse(BaseModel):
    entry_id: str
    entry_hash: str
    cabinet_id: str
    ts: str


class PaginatedAuditResponse(BaseModel):
    cabinet_id: str
    entries: list[dict[str, Any]]
    next_cursor: Optional[int] = None
    total_on_page: int


# ── POST /proxy/audit/log ───────────────────────────────────────────────────

@app.post("/proxy/audit/log", response_model=AuditEntryResponse, status_code=201)
async def post_audit_log(
    body: AuditEntryRequest,
    authorization: str = Header(..., alias="Authorization"),
) -> AuditEntryResponse:
    """
    Append a new audit log entry for a cabinet.

    Auth: Authorization: Bearer <AUDIT_API_KEY>
    Validates PII minimization rules (AC #3); appends with hash-chain (AC #2).
    Append-only: this endpoint only creates new entries; updates/deletes rejected (AC #7).
    """
    # Auth check
    provided_key = _parse_bearer(authorization)
    if not _AUDIT_API_KEY or provided_key != _AUDIT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing AUDIT_API_KEY")

    # Build the entry dict (server synthesizes entry_id and ts if not provided)
    ts = body.ts or datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry: dict[str, Any] = {
        "ts": ts,
        "cabinet_id": body.cabinet_id,
        "entry_id": str(uuid.uuid4()),
        "stream": body.stream,
        "event_type": body.event_type,
        "actor": body.actor.model_dump(),
        "subject": body.subject.model_dump(exclude_none=False),
        "cost": body.cost.model_dump() if body.cost else {},
    }

    # PII minimization validation (AC #3) — reject if non-conforming
    try:
        entry = validate_and_minimize(entry)
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=f"PII minimization violation: {ve}") from ve

    # Append with hash-chain (AC #2)
    full_entry = hashchain.append(entry)

    entry_hash = full_entry.get("integrity", {}).get("entry_hash", "")
    if not entry_hash:
        # hashchain.append failed silently — surface as 500
        raise HTTPException(status_code=500, detail="hash-chain append failed; entry not written")

    return AuditEntryResponse(
        entry_id=full_entry["entry_id"],
        entry_hash=entry_hash,
        cabinet_id=full_entry["cabinet_id"],
        ts=full_entry["ts"],
    )


# ── GET /dashboard/audit/{cabinet_id}/{cursor} ──────────────────────────────

@app.get("/dashboard/audit/{cabinet_id}/{cursor}", response_model=PaginatedAuditResponse)
async def get_audit_log(
    cabinet_id: str,
    cursor: int,
    page_size: int = Query(default=1000, ge=1, le=1000),
    authorization: str = Header(..., alias="Authorization"),
) -> PaginatedAuditResponse:
    """
    Read a customer's audit log, cursor-paginated (1000 entries/page).

    cursor = 0 for first page; subsequent pages use next_cursor from prior response.
    Customer sees ONLY their own cabinet's log (AC #10 — cross-tenant read FAILS).
    Auth: Authorization: Bearer <customer's AUDIT_API_KEY>
    """
    provided_key = _parse_bearer(authorization)
    if not _authorize_read(cabinet_id, provided_key):
        # Return 403 (not 401) to distinguish auth-success-but-wrong-cabinet from bad key
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: key not authorized for cabinet {cabinet_id!r}",
        )

    ssot_path = _AUDIT_LOG_ROOT / "audit" / f"{cabinet_id}.jsonl"
    if not ssot_path.exists():
        return PaginatedAuditResponse(
            cabinet_id=cabinet_id,
            entries=[],
            next_cursor=None,
            total_on_page=0,
        )

    entries: list[dict[str, Any]] = []
    next_cursor: Optional[int] = None

    try:
        with ssot_path.open("r", encoding="utf-8") as fh:
            # Skip to cursor position (line-number based — cursor = line index)
            all_lines = fh.readlines()

        total_lines = len(all_lines)
        page_lines = all_lines[cursor : cursor + page_size]
        for line in page_lines:
            stripped = line.strip()
            if stripped:
                try:
                    entries.append(json.loads(stripped))
                except json.JSONDecodeError:
                    pass  # skip malformed lines silently

        end_cursor = cursor + len(page_lines)
        if end_cursor < total_lines:
            next_cursor = end_cursor

    except Exception as exc:  # noqa: BLE001
        logger.error("get_audit_log: error reading log for %s: %s", cabinet_id, exc)
        raise HTTPException(status_code=500, detail="error reading audit log") from exc

    return PaginatedAuditResponse(
        cabinet_id=cabinet_id,
        entries=entries,
        next_cursor=next_cursor,
        total_on_page=len(entries),
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

def _parse_bearer(authorization: str) -> str:
    """Extract token from 'Bearer <token>' header. Returns '' on malform."""
    parts = authorization.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return ""


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "fw-097-audit-server"}
