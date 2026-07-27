#!/usr/bin/env python3.12
"""ask_mint.py — SAME-SOURCE ask batching, producer-side.

WHY THIS EXISTS (paid 2026-07-26, Captain-seat dry run): eleven
near-identical memory-supersession asks sat a week as ELEVEN separate
Captain cards at identical dwell. The Captain's own verdict: "I never gave
ten answers, I gave zero." N pending asks cued by ONE source are ONE
decision; splitting them into N cards does not gather N answers, it
gathers none.

WHERE THE FIX MAY LIVE. The attention plane (``framework/attention/*``)
and the needs ledger (``framework/authority/needs.py``) are germline —
physically unwritable, by design. So batching is a PRODUCER-SIDE grouping:
this module decides how many asks get FILED, never how a filed ask is
rendered, ruled on, or recorded. ``needs.file_need`` is CALLED, never
edited, and the ruling verbs stay exactly the ones the Captain already
has (``grant NEED-<hex8>`` = approve all, ``deny NEED-<hex8>`` = skip
all) — a batched card is an ordinary needs-ledger decision card, so it
inherits fingerprint dedup, guardian-dark no-op, deny-suppression and the
one-tap surface with zero new grammar and zero new authority.

MEMBERSHIP IS WHAT THE CAPTAIN SAW. The card body lists every member id it
covers, and ``batch_members()`` parses that same body back at fan-out
time. Re-deriving the group from live producer state instead would let one
approval reach members he never saw listed — an authority widening by
accident. Everything that can go wrong with the body (a torn line, a count
that disagrees with the list, a token that is not an id) resolves to the
EMPTY tuple: a batch whose membership cannot be read fans out to nobody.

TWO PROPERTIES A CALLER MUST KEEP:
  * The degenerate end is not a batch. One member ⇒ ``batched: False`` and
    the caller mints its normal per-item card. A "batch of one" would be a
    second, differently-worded card class for the identical decision.
  * The fan-out is mechanical, not a new authority. Approve-all must route
    each member through the SAME per-item path (same guards, same
    per-member record); silence still resolves nothing, because a batched
    card that is never answered stays open exactly like the N it replaced.

No U+00B7 anywhere in the body: it is the binder's bindable marker char,
``needs._clean`` strips it, and a stripped separator would silently mangle
the membership list.

Never raises. Every entry point degrades to "not batched" / empty rather
than breaking a producer's pass.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

#: The action_type infix that makes a batched card recognisable to its
#: producer's own reader. ``<producer>:batch:<source_key>`` — the producer
#: prefix keeps two organs' batches from ever sharing a fingerprint.
BATCH_INFIX = ":batch:"

#: Blast-radius bound on ONE decision. Above this the card covers the first
#: MAX_BATCH_MEMBERS (sorted, deterministic) and the caller keeps the rest
#: pending for the next window — never a truncated list presented as whole.
MAX_BATCH_MEMBERS = 100

#: Ids are engine-minted handles, never free text: dots, dashes, colons and
#: underscores only, so the comma-separated body can be parsed back exactly.
_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")

#: The one machine-readable line in an otherwise human body.
_MEMBERS_RE = re.compile(r"^members \((\d+)\): (.+)$", re.MULTILINE)


def _valid_id(value: Any) -> Optional[str]:
    """The token if it is a usable engine-minted handle, else None."""
    text = str(value or "").strip()
    return text if _ID_RE.match(text) else None


def batch_action_type(producer: str, source_key: str) -> str:
    """The needs fingerprint input for one group. Deterministic and stable:
    re-filing the same group is a count bump, never a second card."""
    return f"{producer}{BATCH_INFIX}{source_key}"


def is_batch_action(action_type: Any, producer: Optional[str] = None) -> bool:
    """True for a batched card's action_type (optionally of one producer)."""
    text = str(action_type or "")
    if producer is not None:
        return text.startswith(f"{producer}{BATCH_INFIX}")
    return BATCH_INFIX in text


def batch_source_key(action_type: Any) -> Optional[str]:
    """The source key a batched action_type carries, else None."""
    text = str(action_type or "")
    if BATCH_INFIX not in text:
        return None
    return text.split(BATCH_INFIX, 1)[1] or None


def group_by_source(asks: Iterable[Any], *,
                    source_of: Callable[[Any], Any],
                    member_of: Callable[[Any], Any],
                    ) -> List[Tuple[str, Tuple[str, ...]]]:
    """Pending asks → deterministic ``(source_key, members)`` groups.

    Sorted by source key, members sorted and de-duplicated, unusable ids and
    sourceless asks dropped — two runs over the same pending set must
    produce byte-identical groups or the fingerprint dedup stops working.
    """
    buckets: dict = {}
    try:
        for ask in asks:
            try:
                key = _valid_id(source_of(ask))
                member = _valid_id(member_of(ask))
            except Exception:  # noqa: BLE001 — one bad ask never breaks the group
                continue
            if not key or not member:
                continue
            buckets.setdefault(key, set()).add(member)
    except Exception:  # noqa: BLE001
        return []
    return [(key, tuple(sorted(buckets[key]))) for key in sorted(buckets)]


def render_batch_body(source_key: str, members: Sequence[str], *,
                      noun: str, source_noun: str = "row",
                      detail: str = "") -> str:
    """The batched card's body: the headline decision, then the machine-
    readable membership line, then the producer's own honest detail.

    The count is printed TWICE on purpose — once in prose and once in the
    membership line — so a truncated or tampered body disagrees with itself
    and ``batch_members`` can refuse it instead of fanning out a guess.
    """
    n = len(members)
    head = (f"{n} {noun} cued by {source_noun} {source_key} — "
            "approve all / list / skip all.")
    listing = f"members ({n}): " + ", ".join(members)
    body = f"{head}\n{listing}"
    if detail:
        body = f"{body}\n{detail}"
    return body


def batch_members(row_or_why: Any) -> Tuple[str, ...]:
    """The member ids a batched card covers — the ONLY membership authority
    at fan-out time (a needs row dict or its ``why`` text).

    Fail-closed to ``()``: no membership line, more than one such line, a
    declared count that disagrees with the parsed list, or any token that is
    not an engine-minted id. An approval whose membership cannot be read
    must reach nobody.
    """
    try:
        why = (row_or_why.get("why") if isinstance(row_or_why, dict)
               else row_or_why)
        text = str(why or "")
        found = _MEMBERS_RE.findall(text)
        if len(found) != 1:
            return ()
        declared, listing = found[0]
        members: List[str] = []
        for token in listing.split(","):
            member = _valid_id(token)
            if not member:
                return ()
            members.append(member)
        if len(members) != int(declared) or len(set(members)) != len(members):
            return ()
        return tuple(members)
    except Exception:  # noqa: BLE001
        return ()


def _default_file_need(kind: str, **kw):
    """Late import of the germline needs API — CALLED, never edited."""
    from framework.authority import needs  # noqa: PLC0415 — deliberate
    return needs.file_need(kind, **kw)


def group_pending_asks(source_key: Any, members: Iterable[Any], *,
                       producer: str,
                       noun: str,
                       filed_by: str,
                       detail: str = "",
                       source_noun: str = "row",
                       unblocks: str = "",
                       cost_of_delay: str = "low",
                       kind: str = "decision",
                       max_members: int = MAX_BATCH_MEMBERS,
                       file_need_fn: Optional[Callable] = None) -> dict:
    """Mint ONE Captain card for the asks one source cued.

    Returns ``{batched, source_key, members, deferred, action_type, why,
    need_id}``. ``batched`` is False at the degenerate end (fewer than two
    usable members) or on an unusable source key — the caller then mints its
    normal per-item card and nothing here has any effect. ``deferred``
    carries members beyond ``max_members``: they stay the caller's pending
    problem for the next window, never silently folded into a decision whose
    body does not list them.

    ``need_id`` is None whenever the ledger no-opped (guardian-dark posture,
    denied-and-suppressed, a transient failure) — exactly the contract
    ``needs.file_need`` already has, so a caller that retries per-item
    retries this the same way. Never raises.
    """
    key = _valid_id(source_key)
    seen: dict = {}
    for raw in members or ():
        member = _valid_id(raw)
        if member is not None:
            seen[member] = True
    usable = tuple(sorted(seen))
    out = {"batched": False, "source_key": key or "", "members": usable,
           "deferred": (), "action_type": None, "why": None, "need_id": None}
    if not key or len(usable) < 2:
        return out

    covered, deferred = usable[:max_members], usable[max_members:]
    if len(covered) < 2:
        return out
    action_type = batch_action_type(producer, key)
    why = render_batch_body(key, covered, noun=noun,
                            source_noun=source_noun, detail=detail)
    out.update({"batched": True, "members": covered, "deferred": deferred,
                "action_type": action_type, "why": why})
    try:
        filer = file_need_fn or _default_file_need
        out["need_id"] = filer(kind, action_type=action_type, why=why,
                               unblocks=unblocks,
                               cost_of_delay=cost_of_delay,
                               filed_by=filed_by, cid=key)
    except Exception:  # noqa: BLE001 — a card must never break a producer
        out["need_id"] = None
    return out
