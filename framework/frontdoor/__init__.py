"""framework.frontdoor — the cabinet's send-path front-door (Phase 1 foundation).

The one structure through which everything reaching the Captain, and everything the Captain
sends, passes (docs/cabinet-architecture-cohesive-2026-06-22.md §3). Four
modules, one direction of dependency:

    intake.py      durable Redis-backed queue (pipes/triggers write here, not Telegram)
        ↓
    composer.py    PURE: intake items -> grouped by urgency tier -> ONE unified message
        ↓
    channel.py     send(text) -> CAPTAIN_TELEGRAM_ID, gated by framework.env.allow_sends()
        ↓
    reply_binder.py  bind(reply, items) -> framework.acting.loop -> consequence ledger

This package is the genuinely-new build; everything below it (the acting loop,
the consequence ledger, the brain bridge, draft_lib) is reused/rewired.

Public API
----------
The four modules plus the send-path runner are re-exported here so callers
import the front-door surface from one place::

    from framework.frontdoor import enqueue, drain, compose, send, bind
    from framework.frontdoor import run_send_path   # drain -> compose -> send

`run_send_path` is gated by ``framework.env.allow_sends()`` end-to-end: in dev
it composes (and returns the composed text) but ``channel.send`` returns
``blocked-dev`` with zero network call.
"""
from __future__ import annotations

# Sub-modules (kept importable as `frontdoor.intake`, etc.).
from framework.frontdoor import channel, composer, intake, reply_binder

# Flat public surface (the contract names callers use directly).
from framework.frontdoor.channel import receive, send
from framework.frontdoor.composer import (
    compose,
    forward_judge,
    group_by_tier,
    render_item,
)
from framework.frontdoor.intake import (
    ack,
    drain,
    drain_pending,
    enqueue,
    validate_item,
)
from framework.frontdoor.reply_binder import bind
from framework.frontdoor.run_frontdoor import run_send_path

__all__ = [
    # sub-modules
    "intake",
    "composer",
    "channel",
    "reply_binder",
    # intake
    "enqueue",
    "drain",
    "drain_pending",
    "ack",
    "validate_item",
    # composer
    "compose",
    "group_by_tier",
    "render_item",
    "forward_judge",
    # channel
    "send",
    "receive",
    # reply_binder
    "bind",
    # runner
    "run_send_path",
]
