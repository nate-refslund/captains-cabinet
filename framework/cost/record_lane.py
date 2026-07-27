"""The seam every NON-SESSION paid caller uses to count itself.

Two consumers, one definition:

  * PYTHON callers import ``record_anthropic`` / ``record_voyage`` /
    ``record_subscription`` / ``record_units`` directly.
  * SHELL and TYPESCRIPT callers run this module as a CLI
    (``cabinet/scripts/lib/cost-lane.sh`` wraps the invocation):

        printf '%s' "$RESPONSE" | PYTHONPATH=$CABINET_ROOT python3 \
            -m framework.cost.record_lane --lane api_direct \
            --principal cos --response - --response-kind anthropic

The Claude Code Stop hook meters officer SESSIONS only. Everything in
``meter.LANES`` spends outside a session — cron/launchd LLM calls, the advisor
crew, Voyage embeddings and reranks, ElevenLabs speech — and was, until
2026-07-26, entirely invisible: not under-reported, ABSENT.

CONTRACT (every line below exists to hold it):

  * COUNTING ONLY. The Captain removed all spend caps on 2026-07-26. Nothing
    here may gate, block, slow or fail a caller. ``main()`` returns 0 on every
    path including an unhandled exception, prints NOTHING on stdout (callers
    pipe this next to their own stdout contract), and the helper functions
    swallow every exception.
  * NO INVENTED PRICES. Voyage and ElevenLabs have no rate row in
    ``meter.RATES``, so their lanes record CALLS and vendor UNITS and leave
    cost unset. ``units`` is always a unit the VENDOR bills in and that the
    response or the request actually carries — Voyage's own
    ``usage.total_tokens``, ElevenLabs TTS characters — never a proxy dressed
    up as a measurement.
  * PARSING LIVES HERE, NOT IN EACH CALLER. Six shell/python/TS callers would
    otherwise each grow their own jq expression for the Anthropic usage block,
    which is exactly how the 5x cache mispricing got duplicated into two hooks
    and a TypeScript file in the first place.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional, Tuple

from framework.cost import meter


# ─────────────────────────────────────────────────────────────────────────────
# Response parsers
# ─────────────────────────────────────────────────────────────────────────────
def _loads(raw: Any) -> Optional[dict]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return None
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def price_anthropic(raw: Any) -> Tuple[Optional[int], Dict[str, int]]:
    """(cost_micro, token dims) for an Anthropic ``/v1/messages`` response body.

    Returns ``(None, {})`` when the body carries no usage block — an error
    envelope (``{"type":"error",...}``), a truncated read, or a curl failure.
    That is NOT the same as zero: the caller still records the CALL, and the
    lane renders as unpriced for that call rather than as $0.00.

    The TTL split mirrors ``meter.parse_transcript``: when the response reports
    a cache-creation total with no ``cache_creation`` breakdown, the tokens are
    charged at the 5m multiplier — the LOWER of the two — because inventing 1h
    spend that may not have happened is worse than the residual.
    """
    doc = _loads(raw)
    if doc is None:
        return None, {}
    usage = doc.get("usage")
    if not isinstance(usage, dict):
        return None, {}
    try:
        i = int(usage.get("input_tokens") or 0)
        o = int(usage.get("output_tokens") or 0)
        cr = int(usage.get("cache_read_input_tokens") or 0)
        cw_total = int(usage.get("cache_creation_input_tokens") or 0)
        cc = usage.get("cache_creation") or {}
        cw1h = int(cc.get("ephemeral_1h_input_tokens") or 0) if isinstance(cc, dict) else 0
        cw5m = int(cc.get("ephemeral_5m_input_tokens") or 0) if isinstance(cc, dict) else 0
    except (TypeError, ValueError):
        return None, {}
    if cw1h + cw5m == 0 and cw_total:
        cw5m = cw_total
    model = doc.get("model") or ""
    cost = meter.price(model, i, o, cw5m, cw1h, cr)
    return cost, {"input": i, "output": o, "cache_write": cw5m + cw1h, "cache_read": cr}


def voyage_units(raw: Any) -> int:
    """Billable tokens from a Voyage embeddings/rerank response.

    Voyage bills by token and REPORTS the count it billed
    (``usage.total_tokens``), so this is the vendor's own number — not a
    character count standing in for one. An unparseable body yields 0, which
    ``record_lane`` drops rather than writing a false zero.
    """
    doc = _loads(raw)
    if doc is None:
        return 0
    usage = doc.get("usage")
    if not isinstance(usage, dict):
        return 0
    try:
        return max(0, int(usage.get("total_tokens") or 0))
    except (TypeError, ValueError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Recorders — every one best-effort, never raises, returns True iff written.
# ─────────────────────────────────────────────────────────────────────────────
def record_anthropic(raw: Any, lane: str, principal: str, calls: int = 1) -> bool:
    """Price one raw Anthropic response body into ``lane``."""
    try:
        cost, _dims = price_anthropic(raw)
        return meter.record_lane(lane, principal, cost_micro=cost, calls=calls)
    except Exception:  # noqa: BLE001 — a meter fault must never reach the caller
        return False


def record_voyage(raw: Any, lane: str, principal: str, calls: int = 1) -> bool:
    """Count one Voyage call into ``lane`` with the tokens Voyage billed."""
    try:
        return meter.record_lane(lane, principal, cost_micro=None,
                                 units=voyage_units(raw), calls=calls)
    except Exception:  # noqa: BLE001
        return False


def subscription_cost_usd(raw: Any) -> Optional[float]:
    """``total_cost_usd`` from a ``claude -p --output-format json`` envelope.

    None for a text-format call, an error envelope, or unparseable output —
    all of which still spent pool capacity, so the caller records the CALL and
    leaves the dollar figure unset.
    """
    doc = _loads(raw)
    if doc is None:
        return None
    usd = doc.get("total_cost_usd")
    if isinstance(usd, (int, float)) and not isinstance(usd, bool):
        return float(usd)
    return None


def record_subscription(cost_usd: Any, principal: str, calls: int = 1) -> bool:
    """Count one ``claude -p`` headless call (Max pool, no card).

    ``cost_usd`` is the CLI's own ``total_cost_usd`` from the
    ``--output-format json`` envelope — the equivalent API price of a call that
    drew down the subscription instead. ``None`` (a text-format call, which
    reports no cost) records the call unpriced.
    """
    try:
        micro = None
        if isinstance(cost_usd, (int, float)) and not isinstance(cost_usd, bool):
            micro = int(round(float(cost_usd) * 1_000_000))
        return meter.record_lane("subscription", principal,
                                 cost_micro=micro, calls=calls)
    except Exception:  # noqa: BLE001
        return False


def record_units(lane: str, principal: str, units: int = 0, calls: int = 1,
                 cost_micro: Optional[int] = None) -> bool:
    """Count a call whose vendor unit the caller measured itself (TTS chars…)."""
    try:
        return meter.record_lane(lane, principal, cost_micro=cost_micro,
                                 units=int(units or 0), calls=calls)
    except Exception:  # noqa: BLE001
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def _read_response(spec: Optional[str]) -> Optional[str]:
    if not spec:
        return None
    if spec == "-":
        try:
            return sys.stdin.read()
        except Exception:  # noqa: BLE001
            return None
    try:
        with open(spec, "r", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="framework.cost.record_lane", add_help=True)
    ap.add_argument("--lane", required=True, help="one of meter.LANES")
    ap.add_argument("--principal", default="",
                    help="officer slug, or svc:<service> for a scheduled lane")
    ap.add_argument("--calls", type=int, default=1)
    ap.add_argument("--units", type=int, default=0)
    ap.add_argument("--cost-micro", dest="cost_micro", default=None)
    ap.add_argument("--response", default=None,
                    help="'-' for stdin, or a path to the API response body")
    ap.add_argument("--response-kind", dest="response_kind", default="",
                    choices=["", "anthropic", "voyage", "subscription"])
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        # argparse exits 2 on a bad flag. A metering typo must not fail a
        # caller that is only piping money-counting alongside its real work.
        return 0

    raw = _read_response(args.response)
    cost = None
    if args.cost_micro not in (None, ""):
        try:
            cost = int(args.cost_micro)
        except (TypeError, ValueError):
            cost = None
    units = args.units
    kind = args.response_kind

    if kind == "anthropic":
        parsed, _dims = price_anthropic(raw)
        if parsed is not None:
            cost = parsed
    elif kind == "voyage":
        got = voyage_units(raw)
        if got:
            units = got
    elif kind == "subscription":
        usd = subscription_cost_usd(raw)
        if usd is not None:
            cost = int(round(usd * 1_000_000))

    ok = record_units(args.lane, args.principal, units=units,
                      calls=args.calls, cost_micro=cost)
    # STDERR only, and only when asked: several callers pipe this module
    # alongside a stdout contract they must not disturb (transcribe-voice.sh
    # emits the transcript, memory.sh emits the embedding).
    if os.environ.get("CABINET_COST_DEBUG") == "1":
        sys.stderr.write("record_lane: lane=%s principal=%s calls=%s units=%s "
                         "cost_micro=%s written=%s\n"
                         % (args.lane, args.principal, args.calls, units, cost, ok))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — counting must never break a caller
        sys.exit(0)
