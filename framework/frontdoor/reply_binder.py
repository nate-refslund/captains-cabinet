"""Front-door reply leg — bind the Captain's reply back to its originating proposal.

`bind(reply_text, items)` is the LAST module of the cabinet front-door
(docs/cabinet-architecture-cohesive-2026-06-22.md §3). It closes the loop:

  1. ROUTE the captain's reply via framework.acting.loop.route_captain_response
     (approve / edit / skip / policy / instruction).
  2. MATCH the intake `items` back to their PENDING proposal by
     correlation_id == framework.acting.loop.proposal_id(proposal), using the
     loop's pending_proposals() (last-write-wins, decided rows already excluded).
  3. RECORD the SUPERSEDING outcome (approve→confirmed / edit→wrong / skip→
     unknown) OR expire (policy/instruction-only reply) on the append-only
     consequence ledger via loop.handle_response — which is itself idempotent.
  4. ACK the bound intake ids so they leave the Redis pending set.

IDEMPOTENT by construction: handle_response no-ops an already-decided proposal,
and once a proposal is decided it drops out of pending_proposals(), so a
re-delivered or double reply binds to nothing and records nothing new.

This slice does NOT send. `dispatch` defaults to a gated no-op — the live
recipient-send wiring (queue_draft through framework.env.allow_sends()) lands in
a later slice. The ledger is APPEND-ONLY: enrichment is a new superseding write,
never a mutation/delete of a prior row.
"""
from __future__ import annotations

from typing import Any, Callable

from framework.acting import loop
from framework.fidelity.consequence import emit_consequence
from framework.frontdoor import intake


def _noop_dispatch(routed, draft, proposal) -> None:
    """The gated no-op dispatch for this slice.

    There is NO recipient-send here: nothing leaves the machine. The live
    adapter that wraps this will gate every outbound on
    framework.env.allow_sends() and route ONLY to CAPTAIN_TELEGRAM_ID; until
    that slice lands, dispatch is a deliberate no-op so the binder is safe to
    run dry/test/build. (The loop only ever passes a non-None draft on an
    explicit approve, and even then this no-op ignores it.)
    """
    return None


def _correlation_id(item: Any) -> str | None:
    """The producer's stable key binding an item to its originating proposal.

    Optional on pure-FYI items; absent -> the item cannot be bound."""
    if not isinstance(item, dict):
        return None
    cid = item.get("correlation_id")
    return cid if isinstance(cid, str) and cid else None


def bind(
    reply_text: str,
    items: list[dict],
    *,
    emit: Callable[..., Any] = emit_consequence,
    reviewed_at: str | None = None,
    dispatch: Callable[..., Any] = _noop_dispatch,
    pending_source: Callable[[], list] | None = None,
    ack: Callable[..., Any] = intake.ack,
) -> dict:
    """Bind a captain reply to its proposal, record the outcome, ack the items.

    Args:
      reply_text: the Captain's raw Telegram reply.
      items: the intake item(s) this reply concerns. Each carries a
        `correlation_id` (== loop.proposal_id of its originating proposal) and a
        Redis-assigned stream `id` (the ack key).
      emit: consequence emitter (injectable for tests; default = the real
        append-only ledger emitter, dir env-routed via framework.env).
      reviewed_at: the actual decision time, threaded through to handle_response
        so decided_at reflects when the captain decided, not when proposed.
      dispatch: send seam — default is the gated no-op (NO recipient-send in
        this slice).
      pending_source: open-proposal source (injectable for tests); default reads
        loop.pending_proposals() off the live ledger.
      ack: intake ack callable (injectable); default = intake.ack.

    Returns {'routed': RoutedResponse, 'bound': [ids], 'status': ...} where
    status is one of:
      'decided'        — a draft decision (approve/edit/skip) was recorded;
      'expired'        — policy/instruction-only reply closed the proposal;
      'already-decided'— the matched proposal was already resolved (idempotent);
      'no-match'       — no pending proposal matched any item's correlation_id
                         (nothing recorded, nothing acked).
    """
    routed = loop.route_captain_response(reply_text)

    # Open proposals keyed by their stable correlation id.
    pending = pending_source() if pending_source is not None else loop.pending_proposals()
    by_id = {loop.proposal_id(p): p for p in pending if isinstance(p, dict)}

    # Match items -> the single proposal they correlate to. All matched items
    # for the SAME proposal are acked together; we record ONE outcome.
    #
    # MULTI-PROPOSAL NOTE (verifier finding): a captain reply binds to exactly
    # ONE proposal — the first-encountered match. If a single bind() call is
    # passed items correlating to two DIFFERENT pending proposals, only the
    # first is bound/recorded/acked; items for the second proposal are left
    # UNACKED (they survive in Redis pending and a later bind() re-drains them),
    # so nothing is lost — but a caller must not expect one reply to settle two
    # distinct proposals. A reply is to one situation; pass one proposal's items.
    matched_proposal = None
    bound_ids: list[str] = []
    for item in items:
        cid = _correlation_id(item)
        if cid is None:
            continue
        prop = by_id.get(cid)
        if prop is None:
            continue
        if matched_proposal is None:
            matched_proposal = prop
        # only bind ids that correlate to the proposal we settled on.
        if loop.proposal_id(prop) == loop.proposal_id(matched_proposal):
            item_id = item.get("id") if isinstance(item, dict) else None
            if item_id is not None:
                bound_ids.append(item_id)

    if matched_proposal is None:
        # No pending proposal for any item — clean no-op (idempotent re-delivery
        # of an already-resolved reply, or a stray/FYI item). Record nothing.
        return {"routed": routed, "bound": [], "status": "no-match"}

    # Record the superseding outcome/expire on the proposal's identity tuple.
    # handle_response is idempotent: an already-decided proposal -> no emit.
    result = loop.handle_response(
        proposal=matched_proposal,
        reply_text=reply_text,
        dispatch=dispatch,
        draft=None,           # no draft content carried in this slice
        emit=emit,
        reviewed_at=reviewed_at,
    )
    status = result.get("status", "decided")

    # Ack the bound intake ids only when a decision was actually recorded
    # (decided/expired). An already-decided no-op should not silently consume
    # the items, but a fresh decision should clear them from pending.
    if status in ("decided", "expired") and bound_ids:
        ack(bound_ids)

    return {"routed": routed, "bound": bound_ids, "status": status}
