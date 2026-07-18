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

import re
from typing import Any, Callable

from framework.acting import loop
from framework.fidelity.consequence import emit_consequence
from framework.frontdoor import intake

# ---------------------------------------------------------------------------
# Plain-verb synonyms (captain-surface spec §3.6): the Captain may TYPE the
# same plain words the buttons show — one authority path either way.
#
#   * verdict synonyms ride the EXISTING verdict grammar: "yes"/"ok" already
#     parse as approve (loop._APPROVE_RE); a bare "no" is normalized to the
#     skip grammar here so it records a real skip verdict instead of falling
#     through as a policy/instruction reply.
#   * throttle synonyms ("pause", "later", "all of them", "top 1") never
#     touch the ledger — they re-pace the surface via pacing.on_control,
#     exactly like the equivalent inline buttons.
#   * charter verbs ("charter: <sentence>", "charter grant/drop CHM-<hex>")
#     ride the §4.7 amend path below (route_charter_amend) — propose-only
#     cards, applied on grant through the schema-validated charter.amend.
#
# Telegram text is UNTRUSTED: every synonym is an EXACT match on the whole
# (whitespace-normalized) reply — free text never widens authority, and an
# unmatched reply flows through the ordinary binder path unchanged.
# ---------------------------------------------------------------------------

_PLAIN_NO_RE = re.compile(r"^\s*(no|nope|nej)\s*[.!]*\s*$", re.IGNORECASE)
_PLAIN_NO_SKIP = "skip: no — typed plain reply"

#: whole-reply throttle phrase -> (pacing verb, arg). Same verbs as the
#: nudge/batch inline buttons (decision_card.CB_VERBS pacing subset).
THROTTLE_SYNONYMS: dict = {
    "pause": ("tri", "snz"),
    "snooze": ("tri", "snz"),
    "later": ("tri", "brief"),
    "all of them": ("all", ""),
    "top 1": ("top1", ""),
    "top1": ("top1", ""),
}


def normalize_plain_reply(reply_text: str) -> str:
    """Map a bare plain 'no' onto the org's skip grammar. Everything else
    passes through byte-identical (yes/ok/approve already parse)."""
    if _PLAIN_NO_RE.match(reply_text or ""):
        return _PLAIN_NO_SKIP
    return reply_text


def throttle_of(reply_text: str) -> "tuple[str, str] | None":
    """(pacing verb, arg) when the WHOLE reply is a throttle phrase."""
    key = " ".join(str(reply_text or "").lower().split()).strip(" .!")
    return THROTTLE_SYNONYMS.get(key)


def route_plain_reply(reply_text: str, *, now=None, state: "dict | None" = None,
                      save: "Callable[[dict], Any] | None" = None) -> "dict | None":
    """Typed throttle verbs → the pacing engine (same effect as the buttons).

    Returns None when the reply is NOT a throttle (caller proceeds to
    ``bind()``); else applies ``pacing.on_control`` to durable pacing state
    and returns ``{"handled": True, "throttle": verb, "routing": …}``.
    ``state``/``save`` are injectable for tests; live default loads and
    persists ``pacing-state.json``."""
    t = throttle_of(reply_text)
    if t is None:
        return None
    from datetime import datetime, timezone

    from framework.comms.surface import pacing
    verb, arg = t
    now = now or datetime.now(timezone.utc)
    st = pacing.load_state() if state is None else state
    new_state, routing = pacing.on_control(st, verb, arg, now)
    if save is not None:
        save(new_state)
    elif state is None:
        pacing.save_state(new_state)
    else:
        state.clear()
        state.update(new_state)
    return {"handled": True, "throttle": verb, "routing": routing}


# ---------------------------------------------------------------------------
# Charter-amend verbs (attention-gateway spec §4.7 — the one-sentence amend
# path charter-default.yml's header promises). Same untrusted-text law as the
# throttle synonyms: whole-message anchored grammars only, free text never
# widens authority, and a matched verb is TERMINAL (even a refusal — the
# refusal card is the answer; the reply must never fall through to bind()
# where e.g. "charter: don't wake me for fyi" would mis-record a policy).
#
# PROPOSE-ONLY (autonomy law): `charter: <sentence>` files a card with the
# rendered yaml diff and writes NO charter bytes; `charter grant CHM-<hex>`
# applies it through charter_amend.grant → charter.amend (schema-validated,
# atomic, §4.10.4 provenance: quieten ⇒ chair; louder ⇒ the grant reply's own
# receipt_message_id IS the Captain provenance); `charter drop CHM-<hex>`
# discards. Callers run route_charter_amend() before bind(), exactly like
# route_plain_reply().
# ---------------------------------------------------------------------------

_CHARTER_REQ_RE = re.compile(r"^\s*charter\s*:\s*(.+?)\s*$",
                             re.IGNORECASE | re.DOTALL)
_CHARTER_GRANT_RE = re.compile(
    r"^\s*charter\s+grant\s+chm[-_ ]?([0-9a-f]{8})\s*[.!]?\s*$", re.IGNORECASE)
_CHARTER_DROP_RE = re.compile(
    r"^\s*charter\s+drop\s+chm[-_ ]?([0-9a-f]{8})\s*(?:[:—-]\s*(.*))?$",
    re.IGNORECASE | re.DOTALL)


def charter_verb_of(reply_text: str) -> "tuple[str, str, str] | None":
    """(verb, arg, tail) when the WHOLE reply is a charter verb, else None.

    verb ∈ {"request", "grant", "drop"}; arg is the sentence (request) or the
    normalized CHM-<hex8> id (grant/drop); tail is drop's optional why."""
    t = str(reply_text or "")
    m = _CHARTER_GRANT_RE.match(t)
    if m:
        return ("grant", "CHM-" + m.group(1).lower(), "")
    m = _CHARTER_DROP_RE.match(t)
    if m:
        return ("drop", "CHM-" + m.group(1).lower(), (m.group(2) or "").strip())
    m = _CHARTER_REQ_RE.match(t)
    if m:
        return ("request", m.group(1).strip(), "")
    return None


def route_charter_amend(reply_text: str, *,
                        receipt_message_id: "int | None" = None,
                        charter_path=None,
                        present: "Callable[[str], Any] | None" = None,
                        log: "Callable[[str], Any]" = lambda m: None) -> "dict | None":
    """The charter-amend verb family → framework.frontdoor.charter_amend.

    Returns None when the reply is NOT a charter verb (caller proceeds to
    ``bind()``); else a TERMINAL result dict {"handled": True, "charter":
    "proposed"|"applied"|"applied-noop"|"dropped"|"refused", "card": …,
    "summary": …}. Refusals are fail-closed: nothing was written, and the
    card carries the refusal reason (schema error / unknown id / missing
    louder-grant receipt). ``receipt_message_id`` is the inbound Telegram id
    of THIS reply — on a louder grant it becomes the Captain provenance.
    ``present`` (injectable) receives the card; a present failure is logged,
    never raised."""
    v = charter_verb_of(reply_text)
    if v is None:
        return None
    verb, arg, tail = v
    from framework.frontdoor import charter_amend
    try:
        if verb == "request":
            res = charter_amend.request(arg, charter_path=charter_path)
            out = {"handled": True, "charter": "proposed",
                   "amend_id": res["amend_id"],
                   "classification": res["classification"],
                   "card": res["card"],
                   "summary": (f"charter {res['amend_id']} proposed "
                               f"({res['classification']}) — propose-only, "
                               f"`charter grant {res['amend_id']}` applies")}
        elif verb == "grant":
            res = charter_amend.grant(arg,
                                      receipt_message_id=receipt_message_id,
                                      charter_path=charter_path)
            if res.get("applied"):
                cls = res.get("classification")
                prov = ("chair provenance (quieten auto-apply)"
                        if cls == "quieten" else
                        f"Captain provenance (grant receipt "
                        f"{receipt_message_id})")
                out = {"handled": True, "charter": "applied",
                       "amend_id": arg, "classification": cls,
                       "version": res.get("version"),
                       "card": (f"✅ Charter amendment {arg} applied — "
                                f"version {res.get('version')}, {prov}."),
                       "summary": (f"charter {arg} applied v{res.get('version')} "
                                   f"({cls}, {prov})")}
            else:
                out = {"handled": True, "charter": "applied-noop",
                       "amend_id": arg,
                       "card": (f"Charter amendment {arg}: "
                                f"{res.get('note', 'already rules')}"),
                       "summary": f"charter {arg} no-op — already rules"}
        else:
            charter_amend.drop(arg, tail, charter_path=charter_path)
            out = {"handled": True, "charter": "dropped", "amend_id": arg,
                   "card": f"🗑 Charter amendment {arg} dropped — nothing applied.",
                   "summary": f"charter {arg} dropped"}
    except (ValueError, OSError) as e:
        # CharterError ⊂ ValueError: refuse honestly, nothing was written.
        out = {"handled": True, "charter": "refused",
               "card": f"⚠️ charter {verb}: refused — {e}",
               "summary": f"charter {verb} refused: {str(e)[:160]}"}
    if present is not None:
        try:
            present(out["card"])
        except Exception as e:
            log(f"reply-binder: charter card present failed: {e!r}")
    return out


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
    # §3.6 plain-verb synonyms: a bare typed "no" rides the skip grammar so
    # tapped and typed replies land on the one authority path. (Throttle
    # phrases and charter verbs never reach bind() — callers run
    # route_plain_reply() and route_charter_amend() first.)
    reply_text = normalize_plain_reply(reply_text)
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
