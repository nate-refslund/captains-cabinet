"""framework.frontdoor.composer — PURE intake-items -> ONE unified message.

The judge/composer stage of the front-door (docs/cabinet-architecture-cohesive-
2026-06-22.md §3.3, §7). Takes a list of canonical intake items and renders ONE
captain-facing message string, grouped by the three urgency tiers from
``.claude/rules/courses-of-action.md`` (ping-now | batch | fyi), each line
carrying full provenance (source + why).

PURE by contract: NO I/O — no Redis, no env, no network, no clock unless an
explicit ``now`` is injected. Fully unit-testable, deterministic.

CONSERVATIVE FORWARD-JUDGE: ``forward_judge(item)`` defaults True — the job is
to UNIFY + ENRICH, not drop. Tightening (the trust ladder, applied to *what
reaches Nate*) lives in ``forward_judge`` later; today it forwards everything.

SECRET-SAFETY: composer never reads the environment and never emits token or
``nate_model``/voice material. It renders ONLY producer-supplied content
(payload.summary, context.why, source). It cannot leak a secret it never reads.
"""
from __future__ import annotations

from typing import Any

# The three urgency tiers, in display order (most urgent first). Matches
# .claude/rules/courses-of-action.md: ping-now > batch (DEFAULT) > fyi.
_TIER_ORDER = ("ping-now", "batch", "fyi")
_VALID_TIERS = frozenset(_TIER_ORDER)
_DEFAULT_TIER = "batch"

# Human-facing section headers per tier (provenance-bearing message structure).
_TIER_LABELS = {
    "ping-now": "🔴 Ping now",
    "batch": "📋 For your next briefing",
    "fyi": "💡 FYI",
}


def forward_judge(item: dict[str, Any]) -> bool:
    """Conservative forward seam: True = surface this item.

    Defaults True for every item — the composer unifies + enriches, it does not
    drop (arch §3.3, §7 'judge conservative -> tighten'). Filtering tightens
    HERE as trust grows; today nothing is dropped.
    """
    return True


def _tier_of(item: dict[str, Any]) -> str:
    """The item's urgency tier, defaulting to 'batch' (the rule's DEFAULT) when
    missing or not one of the three valid tiers (fail-soft, never drop)."""
    tier = item.get("urgency_tier")
    return tier if tier in _VALID_TIERS else _DEFAULT_TIER


def group_by_tier(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Partition items into the three tier buckets.

    Keys are always the three tiers ('ping-now' | 'batch' | 'fyi'); a missing or
    invalid ``urgency_tier`` lands in 'batch'. Within a bucket, original input
    order is preserved (compose() does the ts ordering).
    """
    grouped: dict[str, list[dict[str, Any]]] = {t: [] for t in _TIER_ORDER}
    for item in items:
        grouped[_tier_of(item)].append(item)
    return grouped


def render_item(item: dict[str, Any]) -> str:
    """Render ONE intake item as a single provenance-bearing line.

    Format: ``• [source] summary — why`` (the ``— why`` clause is dropped when
    there is no why). Pulls only producer content: payload.summary, context.why,
    source. NEVER emits nate_model/voice or token material (it reads none).
    Fail-soft: missing fields render as empty, never the literal 'None'.
    """
    source = str(item.get("source") or "").strip()
    payload = item.get("payload") or {}
    summary = str(payload.get("summary") or "").strip()
    context = item.get("context") or {}
    why = str(context.get("why") or "").strip()

    prefix = f"[{source}] " if source else ""
    line = f"• {prefix}{summary}".rstrip()
    if why:
        line = f"{line} — {why}"
    return line


def _ts_key(item: dict[str, Any]) -> str:
    """Sort key within a tier: ISO-8601 ts (lexicographic == chronological).
    A missing ts sorts first (empty string), keeping ordering total + stable."""
    return str(item.get("ts") or "")


def compose(items: list[dict[str, Any]], *, now: str | None = None) -> str:
    """Render a list of intake items into ONE unified captain-facing message.

    Deterministic: tiers ordered ping-now > batch > fyi; items within a tier
    ordered by ts (stable). Each item is a provenance line (source + why). Only
    forward_judge-passing items are surfaced (conservative: all, today). Tier
    sections with no surviving items are omitted (no empty headers). Returns ''
    for an empty result so the Chair can decide not to send.

    ``now`` is accepted for interface symmetry / future relative-time rendering
    but is not required for the deterministic core — passing it does not change
    output today (keeps the function pure + injectable).
    """
    forwarded = [it for it in items if forward_judge(it)]
    if not forwarded:
        return ""

    grouped = group_by_tier(forwarded)

    sections: list[str] = []
    for tier in _TIER_ORDER:
        bucket = grouped[tier]
        if not bucket:
            continue
        ordered = sorted(bucket, key=_ts_key)
        lines = [_TIER_LABELS[tier]]
        lines.extend(render_item(it) for it in ordered)
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
