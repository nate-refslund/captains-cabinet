"""framework.comms.surface.decision_card — one card = one decision (§3.1–3.2).

Pure renderer from a census decision-card (``framework.attention.queue``
shapes: situation_card / need_card / t2_card) to the ``send_card`` kwargs +
inline buttons for ONE Captain decision. Never more than one decision per
card; never a ``(1/N)`` chunk; state changes are edit-in-place re-renders of
the SAME card (identity = the engine-owned ``thread:<item-id>`` evidence ref,
stable under any wording change).

Label-soup kill: an item's state is the card's SHAPE — an open card carries
live buttons; a done card shows the result + an undo control when reversible;
FYI-kind items are not decision cards at all (they fold into the digest —
``surface.digest``).

All Captain-facing vocabulary comes from ``framework.attention.plain`` (the
PLAIN-LANGUAGE LAW's single source of truth — kind names, button labels,
risk sentences, result lines); this module only assembles. The one machine
token allowed through is the ``·…·`` reply marker (reply binding), passed via
``pid_marker`` and appended by the gate's renderer — a decision tapped OR
typed lands on the same item.

No I/O here — delivery belongs to the pacing/pin engines via
``framework.comms.tools``.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from framework.attention import plain as plainlaw
from framework.comms.surface import links as _links

# ---------------------------------------------------------------------------
# Callback grammar — "cv2|<verb>|<arg>" (Telegram callback_data ≤64 bytes).
# Verbs are a strict allowlist; args are engine-minted short handles, never
# free text. Parsing lives in engine.parse_callback.
# ---------------------------------------------------------------------------

CB_PREFIX = "cv2"
CB_VERBS = ("ok", "edit", "skip", "later", "undo",     # per-card decisions
            "tri", "more", "stop", "all", "top1",      # pacing controls
            "ndg", "ndl", "ndd")   # needs-card verbs: grant / later / deny —
                                   # arg is the NEED-<hex8> fingerprint tail
                                   # ONLY (tap_wire re-validates fullmatch
                                   # [0-9a-f]{8}); rides the typed binder
                                   # grammar door (captain-reminder cards)


def handle_of(item_id: str) -> str:
    """A short stable handle for callback data (identity digest, not a
    security boundary). 12 hex chars keeps 'cv2|ok|<h>' at 19 bytes."""
    return hashlib.sha1(str(item_id).encode("utf-8")).hexdigest()[:12]


def cb(verb: str, arg: str = "") -> str:
    if verb not in CB_VERBS:
        raise ValueError(f"unknown callback verb: {verb}")
    data = f"{CB_PREFIX}|{verb}|{arg}" if arg else f"{CB_PREFIX}|{verb}"
    return data[:64]


# ---------------------------------------------------------------------------
# Decision / FYI split (§3.2 — FYI rides the digest, never the decision stream)
# ---------------------------------------------------------------------------

FYI_KINDS = frozenset({"fyi", "digest", "tell-digest", "note", "weekly-rollup"})
_OPEN_STATES = frozenset({"open", "pending"})


def is_decision(card: dict) -> bool:
    """True when this census card warrants a single-decision card. FYI-kind
    or already-resolved items are not decisions."""
    if str(card.get("kind") or "").lower() in FYI_KINDS:
        return False
    return str(card.get("state") or "open").lower() in _OPEN_STATES


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _scrub(text) -> str:
    # marker-hygiene law: free text in a card body never carries U+00B7.
    return str(text or "").replace("·", "")


def _proj(card: dict, now: "datetime | None") -> dict:
    """Adapt a RAW census card to the field names the plain layer speaks
    (the private-census projection keys), without depending on it."""
    why = card.get("why_now") or {}
    blast = card.get("blast_radius") or card.get("blast") or {}
    age_h = card.get("age_h")
    if age_h is None and card.get("created_ts") and now is not None:
        try:
            created = datetime.fromisoformat(
                str(card["created_ts"]).replace("Z", "+00:00"))
            age_h = max(0.0, (now - created).total_seconds() / 3600.0)
        except (ValueError, TypeError):
            age_h = None
    return {
        "what": _scrub(card.get("what")).strip(),
        "lane": card.get("lane"), "kind": card.get("kind"),
        "age_h": age_h,
        "deadline_iso": (card.get("deadline_iso") or why.get("deadline_iso")
                         or card.get("harm_at")),
        "blast": {"class": blast.get("class"), "reach": blast.get("reach")},
        "blast_worst_case": (blast.get("worst_case")
                             or card.get("blast_worst_case")),
    }


def undoable(card: dict) -> bool:
    """Whether a fired approve on this card can honestly offer ↩ Undo.
    False for ceiling class AND for no-return actions (external reach, money
    out, a message an outside human already read) — single source:
    ``plain.no_return``."""
    blast = card.get("blast_radius") or card.get("blast") or {}
    blast = blast if isinstance(blast, dict) else {}
    if str(blast.get("class") or "").lower() == "ceiling":
        return False
    worst = blast.get("worst_case") or card.get("blast_worst_case")
    return not plainlaw.no_return(blast.get("reach"), worst)


def _summary(card: dict) -> str:
    """The plain one-sentence line — what this is, in plain words."""
    return _scrub(card.get("what")).strip()[:200] or plainlaw.COPY["no_title"]


def _context(proj: dict, now: "datetime | None") -> str:
    """Kind + product, the risk sentence, and the clock — all from the plain
    tables (never the producer's org vocabulary)."""
    head = plainlaw.kind_name(proj.get("kind"))
    lane = str(proj.get("lane") or "").strip()
    if lane:
        head = f"{head} — {lane}"
    parts = [head + ".", plainlaw.risk_sentence(proj)]
    clock = [b for b in (plainlaw.age_plain(proj.get("age_h")),
                         plainlaw.due_plain(proj.get("deadline_iso"), now)) if b]
    if clock:
        parts.append((" — ".join(clock)).capitalize() + ".")
    return " ".join(p for p in parts if p)


def proof_lines(card: dict) -> str:
    """The exhaustion proof in plain words (spec §5.3): 'Your team tried: X.
    The Chair tried: Y. It needs you because: Z.' Empty when the card carries
    no complete proof. A lint tooth asserts these render on every
    captain-bound escalation card."""
    esc = card.get("escalation")
    if not isinstance(esc, dict):
        return ""
    lane = _scrub(esc.get("lane_tried")).strip().rstrip(".")
    chair = _scrub(esc.get("chair_tried")).strip().rstrip(".")
    why = _scrub(esc.get("needs_captain_because")
                 or esc.get("why_captain")).strip().rstrip(".")
    if not (lane and chair and why):
        return ""
    return plainlaw.ESCALATION_PROOF_TEMPLATE.format(
        lane=lane, chair=chair, captain=why)


def _marker(card: dict) -> "str | None":
    """The reply-binding marker for this item, when it carries a proposal id.
    The reply wire cross-checks every marker against its server pointer, so a
    marker for an unknown id is refused server-side (fail-closed)."""
    pid = card.get("pid")
    if pid and isinstance(pid, str) and "·" not in pid and "\n" not in pid \
            and 6 <= len(pid) <= 300:
        return f"·{pid}·"
    return None


# Per-kind decision controls: (plain label, engine verb) rows assembled from
# the plain layer's BUTTON_LABELS (single source). Kinds not named use the
# action-proposal set.
_VERBS_BY_KIND = {
    "action-proposal": ("ok", "edit", "skip"),
    "draft-outbound": ("ok", "edit", "skip"),
    "need": ("ok", "later", "skip"),
    "escalation": ("ok", "skip"),
}


def _decision_row(card: dict) -> "list | None":
    kind = str(card.get("kind") or "")
    one_tap = card.get("one_tap") or {}
    approve = one_tap.get("approve")
    semantics = (approve or {}).get("semantics") if isinstance(approve, dict) \
        else approve
    if kind in plainlaw.RITUAL_KINDS or semantics == "ritual-print":
        return None      # a sign-off ritual is typed, never tapped
    labels = plainlaw.BUTTON_LABELS.get(kind) \
        or plainlaw.BUTTON_LABELS["action-proposal"]
    verbs = _VERBS_BY_KIND.get(kind) or _VERBS_BY_KIND["action-proposal"]
    h = handle_of(str(card.get("id") or ""))
    return [{"text": label, "data": cb(verb, h)}
            for label, verb in zip(labels, verbs)]


def buttons_for(card: dict, *, state: str = "open",
                cfg: "dict | None" = None) -> "list | None":
    """The single decision control row for this card's state. Open ⇒ the
    kind's plain decision set (+ an https deep-link when configured); done ⇒
    an undo control when the action is reversible; terminal states ⇒ none."""
    if state == "open":
        row = _decision_row(card)
        if row is None:
            return None
        u = _links.url_button("🔎 Open", _links.queue_item_url(
            str(card.get("id") or ""), cfg))
        if u:
            row.append(u)
        return [row]
    if state == "done":
        # Undo is offered ONLY when it is true: never on ceiling class, never
        # on a no-return action (money out / a message a human outside read).
        if undoable(card):
            h = handle_of(str(card.get("id") or ""))
            return [[{"text": "↩ Undo", "data": cb("undo", h)}]]
    return None


_STATE_LINES = {
    "done": plainlaw.RESULTS["approved"],
    "skipped": plainlaw.RESULTS["declined"],
    "expired": plainlaw.RESULTS["deferred"],
}


def final_line(state: str) -> str:
    """The plain result line for a terminal card state (single source:
    the plain layer's RESULTS table)."""
    return _STATE_LINES.get(state, plainlaw.RESULTS["deferred"])


def render(card: dict, *, state: str = "open", now: "datetime | None" = None,
           cfg: "dict | None" = None) -> dict:
    """The full ``send_card``/``edit_card`` kwargs for ONE decision.

    Returns ``{subject, situation, kind, lane, evidence, deadline_iso,
    state, pid_marker, buttons, escalation}``. ``evidence`` is the
    engine-owned identity anchor ``thread:<item-id>`` — the SAME anchor on
    every re-render, so the gate's standing-card dedup edits this one message
    in place forever. ``escalation`` forwards the producer's exhaustion proof
    (§3.9) untouched, so a paced re-present passes the armed escalation gate
    exactly when its producer did."""
    item_id = str(card.get("id") or "")
    proj = _proj(card, now)
    if state == "open":
        situation_bits = [_context(proj, now)]
        proof = proof_lines(card)
        if proof:
            situation_bits.append(proof)
        if _decision_row(card) is None and is_decision(card):
            situation_bits.append(
                "This one needs your typed sign-off — reply here to do it.")
        url = _links.queue_item_url(item_id, cfg)
        if url and not url.startswith("https://"):
            # http (e.g. a LAN dashboard): no URL button — plain details line.
            situation_bits.append(_links.details_line(url))
    else:
        situation_bits = [_STATE_LINES.get(state, plainlaw.RESULTS["deferred"])]
    return {
        "subject": _summary(card),
        "situation": " ".join(b for b in situation_bits if b).strip(),
        "kind": "action-card",
        "lane": (str(card.get("lane")) if card.get("lane") else None),
        "evidence": [f"thread:{item_id}"],
        "deadline_iso": proj.get("deadline_iso"),
        "state": state,
        "pid_marker": _marker(card),
        "buttons": buttons_for(card, state=state, cfg=cfg),
        "escalation": (card.get("escalation")
                       if isinstance(card.get("escalation"), dict) else None),
    }
