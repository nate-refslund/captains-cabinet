"""framework.comms.surface — the Captain-surface TG engine (captain-surface-v2, ARM B).

The comms-MCP-native presentation layer over the attention census: one card =
one decision, paced (3–5 active, ask-first), pin lifecycle with engagement
auto-advance, briefing-as-card, FYI→digest. Every delivery goes through
``framework.comms.tools`` (send_card / edit_card / pin / unpin) so the
attention gateway — charter class, standing-card dedup, quiet hours, the one
door — governs this engine exactly as it governs every officer. No module
here imports a channel or the front-door transport directly.

Foundation-pure: launcher-neutral, channel-neutral, axis-free. Instance
bindings (cap, mode, dashboard URL) come from env /
``instance/config/comms-surface.yml`` via ``surface.config`` — absent config
resolves to safe defaults (ask-first, cap 5, no deep links).

Spec of record: the Chair's master prompt (Captain-forwarded 2026-07-10) —
§3 principles, §4 pacing, §5 pin lifecycle, §6 foundation/instance split.
"""
from __future__ import annotations

__all__ = [
    "config", "links", "decision_card", "digest",
    "pacing", "pin_lifecycle", "briefing_card", "engine",
]
