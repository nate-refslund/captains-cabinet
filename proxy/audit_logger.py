"""
proxy/audit_logger.py — FW-096 LiteLLM custom callback.

WHY THIS EXISTS: Every request through the LiteLLM proxy must emit a JSONL
audit record (Spec 051 AC #6) so FW-097 can surface per-cabinet spend, margin,
and cap status to the customer dashboard. This callback is registered in
proxy/config.yaml under litellm_settings.callbacks.

MARGIN PRIVACY: cost_marked_up_usd is computed here using LITELLM_MARGIN_PCT
from the server-side environment. The VALUE of this variable is private (commercial
differentiation); the CODE is public (captains-cabinet BSL 1.1 repo). Never
hardcode a real margin value in this file.

OUTPUT PATH: proxy/logs/proxy-audit/<cabinet-slug>.jsonl on the VPS.
Retain per FW-100 GDPR baseline (90d hot, 7yr cold archive for billing reconciliation).

SCHEMA (AC #6):
  ts, cabinet_id, officer, request_id, model, provider,
  tokens_in, tokens_out, cost_raw_usd, cost_marked_up_usd, margin_pct, cap_pct_used
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Margin sourced exclusively from env — value is private (Spec 051 AC #5).
# Default 100 means customer pays 2× raw cost (100% markup = 2× multiplier).
_MARGIN_PCT: int = int(os.environ.get("LITELLM_MARGIN_PCT", "100"))

# Daily cap in USD — must match proxy/config.yaml team_settings.max_budget.
# Used for cap_pct_used computation in audit log (informational; enforcement
# is proxy-side via LiteLLM team-budget).
_CAP_USD: float = float(os.environ.get("LITELLM_CAP_USD", "50.0"))

# Log root on the VPS (Spec 051 I5: server-side, not customer-local).
_AUDIT_LOG_ROOT = pathlib.Path(
    os.environ.get(
        "LITELLM_AUDIT_LOG_ROOT",
        os.path.join(os.path.dirname(__file__), "logs", "proxy-audit"),
    )
)


def _emit_record(record: dict[str, Any]) -> None:
    """Append one JSONL record to <audit_root>/<cabinet_slug>.jsonl."""
    slug = record.get("cabinet_id", "unknown")
    log_path = _AUDIT_LOG_ROOT / f"{slug}.jsonl"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception as exc:  # noqa: BLE001 — audit must never crash the proxy
        logger.warning("FW-096 audit_logger: failed to write record: %s", exc)


def compute_markup(cost_raw_usd: float, margin_pct: int) -> float:
    """Return marked-up cost.  margin_pct=100 → 2× raw cost (100% markup)."""
    return round(cost_raw_usd * (1 + margin_pct / 100), 10)


class CabinetAuditLogger:
    """
    LiteLLM custom callback — registered in proxy/config.yaml.

    LiteLLM calls log_success_event / log_failure_event after each request
    with a StandardLoggingPayload. We extract usage, cost, and metadata and
    emit the AC #6 JSONL record.

    SCHEMA NOTE (FW-096 crew): StandardLoggingPayload attributes confirmed
    against LiteLLM v1.x source (proxy/utils.py StandardLoggingPayload).
    Attribute names may shift in future LiteLLM releases — validate at deploy.
    """

    def log_success_event(self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any) -> None:  # noqa: ANN401
        """Called by LiteLLM after a successful completion."""
        self._emit(kwargs, response_obj, status="success")

    def log_failure_event(self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any) -> None:  # noqa: ANN401
        """Called by LiteLLM after a failed completion (still audit-log it)."""
        self._emit(kwargs, response_obj, status="failure")

    # ── async variants (LiteLLM ≥ 1.30 prefers async callbacks) ──
    async def async_log_success_event(self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any) -> None:  # noqa: ANN401
        self._emit(kwargs, response_obj, status="success")

    async def async_log_failure_event(self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any) -> None:  # noqa: ANN401
        self._emit(kwargs, response_obj, status="failure")

    def _emit(self, kwargs: dict, response_obj: Any, status: str) -> None:
        """Build + write the AC #6 JSONL record.  Never raises."""
        try:
            meta = kwargs.get("litellm_params", {}).get("metadata", {}) or {}
            usage = getattr(response_obj, "usage", None) or {}

            # Token counts — LiteLLM usage object or dict fallback
            if hasattr(usage, "prompt_tokens"):
                tokens_in = int(usage.prompt_tokens or 0)
                tokens_out = int(usage.completion_tokens or 0)
            else:
                tokens_in = int(usage.get("prompt_tokens", 0))
                tokens_out = int(usage.get("completion_tokens", 0))

            # Raw cost from LiteLLM's own pricing computation
            cost_raw = float(kwargs.get("response_cost", 0.0) or 0.0)
            margin_pct = _MARGIN_PCT
            cost_marked_up = compute_markup(cost_raw, margin_pct)

            # Cap usage percentage (informational — enforcement is team-budget)
            cap_pct = round((cost_raw / _CAP_USD) * 100, 2) if _CAP_USD > 0 else 0.0

            record: dict[str, Any] = {
                "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "cabinet_id": str(meta.get("cabinet_id", "unknown")),
                "officer": str(meta.get("officer", "unknown")),
                "request_id": str(
                    kwargs.get("litellm_call_id")
                    or meta.get("request_id")
                    or uuid.uuid4()
                ),
                "model": str(kwargs.get("model", "unknown")),
                "provider": _extract_provider(kwargs),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_raw_usd": cost_raw,
                "cost_marked_up_usd": cost_marked_up,
                "margin_pct": margin_pct,
                "cap_pct_used": cap_pct,
                "status": status,
            }
            _emit_record(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FW-096 audit_logger._emit: unexpected error: %s", exc)


def _extract_provider(kwargs: dict) -> str:
    """
    Infer provider string from model name or custom_llm_provider field.
    Returns "anthropic", "openai-fallback", "gemini", or "unknown".
    """
    provider = kwargs.get("custom_llm_provider", "") or ""
    if provider:
        return str(provider)
    model = str(kwargs.get("model", "")).lower()
    if "claude" in model or "anthropic" in model:
        return "anthropic"
    if "gpt" in model or "openai" in model:
        return "openai-fallback"
    if "gemini" in model:
        return "gemini"
    return "unknown"
