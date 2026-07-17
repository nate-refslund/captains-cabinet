"""framework.attention.plain — the plain-language layer (PLAIN-LANGUAGE LAW).

Captain-decisions 2026-07-10 (Ruling B): every captain-facing card carries a
plain one-sentence summary + plain buttons; org vocabulary is BANNED in UI
copy; technical detail lives behind a "Details" disclosure — disclosed, never
deleted (SEC-4 exact-render law kept). Enforced as a TEST, not a style hope:
``lint()`` below is the law's teeth, wired into pytest AND (via the exported
JSON tables) the dashboard's vitest.

Design (spec §2, captain-surface-v2):
  * Pure data + rule-based templates. NO LLM at render, no I/O at import.
  * One source of truth: the dashboard's ``plain.json`` is GENERATED from
    these tables (``python3.12 -m framework.attention.plain --export``) and a
    drift test pins the committed copy to this module.
  * Consumers: the /queue dashboard rewrite (Arm A), the TG renderer and the
    briefing card (Arm B/C) — all surfaces speak from the same tables.

This module is FOUNDATION: launcher-neutral, instance-free, imports nothing
outside the stdlib.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Kind / state names — the enum-soup killers (jargon-audit §1.5 / §1.21)
# ---------------------------------------------------------------------------

KIND_NAMES: dict[str, str] = {
    "action-proposal": "Suggestion",
    "draft-outbound": "Draft message",
    "escalation": "Escalated to you",
    "need": "Permission request",
    "germline-handback": "Rule change — needs your sign-off",
    "outcome-ratification": "Goal sign-off",
    "pipe-prompt": "Automation question",
    "founder-action": "Your to-do",
}
KIND_NAME_DEFAULT = "Needs you"

STATE_NAMES: dict[str, str] = {
    "open": "New",
    "pending": "Waiting for you",
    "surfaced": "Shown to you",
    "decided": "You decided",
    "acted": "Done",
    "dormant": "Parked",
}
STATE_NAME_DEFAULT = "Waiting for you"

#: Card states that mean "no decision possible any more".
DECIDED_STATES: frozenset[str] = frozenset({"decided", "acted"})

# ---------------------------------------------------------------------------
# Risk sentences — the blast_worst_case rewrites (jargon-audit §6), rendered
# as "If you approve: …". Keys are the EXACT producer strings (they contain
# org vocabulary by design — the linter checks VALUES, never keys).
# ---------------------------------------------------------------------------

RISK_SENTENCES: dict[str, str] = {
    "a wrong approve amends the germline plane":
        "This changes the cabinet's own core rules — hardest to undo.",
    "money leaves the org":
        "This spends money.",
    "a message reaches a human outside the machine":
        "This sends a message to a real person outside.",
    "a ceiling-class artifact ships (prod/secret/net)":
        "This touches production or secrets — highest caution.",
    "a reversible internal artifact needs undoing":
        "Worst case: an internal change gets undone. Low risk.",
    "unclassified chain — treated as low, gated":
        "I couldn't sort this one, so it waits for you. Low risk.",
    "a standing grant widens org authority":
        "This gives the cabinet a lasting new permission.",
    "a capability/resource is granted":
        "This gives the cabinet a new tool or access.",
    "a Chair judgment lands without you":
        "If you don't answer, the First Mate will decide this one.",
    "the Chair is holding a judgment open":
        "The First Mate is waiting on you for this.",
}
#: Fallbacks when the producer string is unknown (never echo it raw — it is
#: org vocabulary; the exact text stays available behind Details).
RISK_DEFAULT_CEILING = "This is a high-caution change — double-check before saying yes."
RISK_DEFAULT = "If you approve, I go ahead with it."

#: Per-kind risk fallbacks — kinds where "I go ahead with it" is absurd
#: (a question has no approve; a ratification runs nothing). Checked before
#: RISK_DEFAULT, after the exact producer-string and ceiling checks.
KIND_RISK_DEFAULTS: dict[str, str] = {
    "pipe-prompt": "I'll follow whatever you answer.",
    "outcome-ratification":
        "This sets the goal your team steers by — nothing runs by itself.",
}

#: Worst-case strings with NO undo path once fired — money out the door,
#: a message in a human's inbox. The undo line must never promise a pull-back
#: on these (single source: the dashboard reads this list from plain.json).
NO_RETURN_WORST_CASES: frozenset[str] = frozenset({
    "money leaves the org",
    "a message reaches a human outside the machine",
})


def no_return(reach: "str | None", worst_case: "str | None") -> bool:
    """True when the action, once fired, cannot be pulled back from a
    receipt: it left the machine (external reach) or is a known no-return
    worst case (money / an outside human read it)."""
    if str(reach or "").lower() == "external":
        return True
    return str(worst_case or "") in NO_RETURN_WORST_CASES

# ---------------------------------------------------------------------------
# Buttons (spec §2.1) — full per-kind sets for the TG renderer, plus the
# three-verb door set the dashboard uses. Labels only; verbs are fixed.
# ---------------------------------------------------------------------------

BUTTON_LABELS: dict[str, list[str]] = {
    "action-proposal": ["✓ Approve", "✎ Change…", "✗ No"],
    "draft-outbound": ["Send it", "✎ Change…", "Don't send"],
    "need": ["Yes, allow", "Not now", "Never"],
    "escalation": ["I'll decide", "Ask the First Mate"],
    "nudge": ["Triage now", "At next briefing", "Snooze 2h"],
    "acted": ["↩ Undo", "👍 Fine"],
}

#: Dashboard door buttons: verb -> label, per kind ("" = default).
DOOR_BUTTONS: dict[str, dict[str, str]] = {
    "": {"approve": "✓ Approve", "later": "Later", "no": "✗ No"},
    "draft-outbound": {"approve": "Send it", "later": "Later", "no": "Don't send"},
    "need": {"approve": "Yes, allow", "later": "Not now", "no": "Never"},
    "escalation": {"approve": "I'll decide", "later": "Later",
                   "no": "Ask the First Mate"},
}

#: Kinds whose approve is a sign-off ritual — never a dashboard tap.
RITUAL_KINDS: frozenset[str] = frozenset({"germline-handback", "outcome-ratification"})

# ---------------------------------------------------------------------------
# Door copy — every message the verdict door can show the Captain.
# ---------------------------------------------------------------------------

MESSAGES: dict[str, str] = {
    "no_session": "You're not signed in — open the dashboard sign-in page first.",
    "csrf": "That request didn't come from your own dashboard page — reload and try again.",
    "rate_limited": "Too many decisions too fast — wait a moment and try again.",
    "stale": "This one changed since you loaded the page — here's the fresh version.",
    "stale_census": "My list is out of date right now — try again in a minute, or answer in Telegram.",
    "gone": "This one is no longer waiting — it may already be decided.",
    "decided": "Already decided — nothing more to do here.",
    "bad_verb": "That choice isn't available for this item.",
    "ritual": "This one needs the sign-off ritual in Telegram — tap 'Open in Telegram'.",
    "not_here": "This one can't be decided from here right now — answer on its Telegram message.",
    "replay": "That confirmation was already used — start again from the card.",
    "expired_token": "That confirmation expired — start again from the card.",
    "bad_request": "I couldn't read that request — reload the page and try again.",
    "bridge_fail": "Something went wrong recording your decision — nothing was done. Try again, or answer in Telegram.",
    "journal_warn": "Heads up: this attempt may be missing from the journal.",
}

#: Results shown on the card after a decision lands (✅ edit-in-place).
RESULTS: dict[str, str] = {
    "approved": "Approved — done.",
    "approved_underway": "Approved — under way.",
    "approved_delivery_failed":
        "Your approval is recorded, but the follow-through hit an error — the First Mate will finish it.",
    "declined": "Noted — I won't do it.",
    "denied": "Okay — I won't do that without asking.",
    "deferred": "Parked — it comes back at the next briefing.",
}

#: Two-step confirm templates ({what} / {risk} filled by the renderer).
CONSEQUENCE_TEMPLATES: dict[str, str] = {
    "approve": "{risk} If you confirm, I go ahead: {what}",
    "approve:draft-outbound":
        "{risk} If you confirm, the message goes out exactly as drafted. "
        "Haven't read it? It's on this item's Telegram card — open that first.",
    "approve:need": "{risk} If you confirm, the cabinet gets this permission.",
    "approve:escalation":
        "Nothing runs yet — this marks it as yours to decide. The First Mate "
        "brings it to you in Telegram to settle.",
    "no": "Nothing happens — I record the no and stop suggesting it.",
    "no:draft-outbound": "The message is not sent.",
    "no:need": "The cabinet does not get this permission.",
    "no:escalation": "The First Mate settles it and tells you what it chose.",
    "later": "Nothing happens now — it comes back at the next briefing.",
}
UNDO_TEMPLATES: dict[str, str] = {
    "approve": "Undo: most changes can be pulled back from the receipt — tap ↩ Undo there.",
    "approve:ceiling": "Hard to undo once done — double-check before you confirm.",
    "approve:no-return":
        "Once this is done it can't be pulled back from here — read it "
        "once more before you confirm.",
    "no": "You can always re-open it from its Telegram message.",
    "later": "It comes back on its own — nothing to undo.",
}

#: The escalation exhaustion proof, in plain words (spec §5.3) — rendered on
#: every captain-bound escalation card that carries a proof; a lint tooth
#: asserts the three lines appear.
ESCALATION_PROOF_TEMPLATE = ("Your team tried: {lane}. The Chair tried: "
                             "{chair}. It needs you because: {captain}.")

#: Static surface copy shared with the dashboard (single source of truth).
COPY: dict[str, str] = {
    "masthead_need_one": "needs you",
    "masthead_need_many": "need you",
    "masthead_dark": "Nothing needs you.",
    "masthead_dark_sub": "All clear — your team is handling the rest. ✅",
    "updated_prefix": "Updated",
    "decisions_header": "Needs a decision",
    "decisions_empty": "Nothing here.",
    "overflow_note": "more waiting — I've asked the First Mate to sort them out.",
    "directions_header": "This week — no rush",
    "directions_empty": "Nothing here.",
    "confirm_yes": "Yes, do it",
    "confirm_no": "Yes, I'm sure",
    "confirm_back": "Back",
    "later_briefing": "At the next briefing",
    "ritual_hint": "To say yes, sign it off in Telegram — tap 'Open in Telegram'.",
    "details_label": "Details",
    "details_sources": "Where this comes from",
    "details_typing": "Prefer typing? Send this in Telegram:",
    "open_telegram": "Open in Telegram ↗",
    "answer_telegram": "Answer in Telegram (First Mate).",
    "no_buttons": "To decide this one, answer on its Telegram message.",
    "footer_hint": "Tap a button to decide — or answer on the item's Telegram message.",
    "working": "Working…",
    "no_title": "(no title)",
}

# ---------------------------------------------------------------------------
# Plain time — ages and deadlines as sentences, never raw ISO on the surface.
# ---------------------------------------------------------------------------


def age_plain(age_h: "float | None") -> str:
    """'waiting under an hour' / 'waiting 5 hours' / 'waiting 3 days'."""
    if age_h is None or age_h < 0:
        return ""
    if age_h < 1:
        return "waiting under an hour"
    if age_h < 48:
        n = int(round(age_h))
        return f"waiting {n} hour{'s' if n != 1 else ''}"
    d = int(round(age_h / 24.0))
    return f"waiting {d} days"


def due_plain(deadline_iso: "str | None", now: "datetime | None" = None) -> str:
    """'overdue' / 'due in 26 hours' / 'due 2026-07-19'."""
    if not deadline_iso:
        return ""
    try:
        dl = datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dl.tzinfo is None:
        dl = dl.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    hours = (dl - now).total_seconds() / 3600.0
    if hours < 0:
        return "overdue"
    if hours < 48:
        n = max(1, int(round(hours)))
        return f"due in {n} hour{'s' if n != 1 else ''}"
    return f"due {dl.date().isoformat()}"


_DECAY_RE = re.compile(r"waiting\s+(\d+)h;\s*(\d+)\s+demotions?", re.IGNORECASE)


def decay_plain(decay: "str | None") -> str:
    """Rewrite the producer's decay line ('waiting 47h; 2 demotions') into
    plain words. Unknown shapes are DROPPED (never echoed — producer strings
    carry org vocabulary; the raw line stays visible behind Details)."""
    if not decay:
        return ""
    if decay.strip() == "the Chair is holding a judgment open":
        return RISK_SENTENCES["the Chair is holding a judgment open"]
    m = _DECAY_RE.search(decay)
    if not m:
        return ""
    age = age_plain(float(m.group(1)))
    n = int(m.group(2))
    if n <= 0:
        return age.capitalize() + "." if age else ""
    return (f"{age.capitalize()} — I've quietly bumped this down "
            f"{n} time{'s' if n != 1 else ''}.")


# ---------------------------------------------------------------------------
# The one-sentence summary (spec §2.1 plain_summary) — card fields ONLY.
# ---------------------------------------------------------------------------


def kind_name(kind: "str | None") -> str:
    return KIND_NAMES.get(str(kind or ""), KIND_NAME_DEFAULT)


def state_name(state: "str | None") -> str:
    return STATE_NAMES.get(str(state or ""), STATE_NAME_DEFAULT)


def risk_sentence(card: dict) -> str:
    """The 'If you approve:' sentence from the producer's worst-case string
    (rewritten — never echoed raw)."""
    raw = card.get("blast_worst_case")
    if isinstance(raw, str) and raw in RISK_SENTENCES:
        return RISK_SENTENCES[raw]
    blast = card.get("blast") or {}
    if isinstance(blast, dict) and blast.get("class") == "ceiling":
        return RISK_DEFAULT_CEILING
    kind_default = KIND_RISK_DEFAULTS.get(str(card.get("kind") or ""))
    if kind_default:
        return kind_default
    return RISK_DEFAULT


def plain_summary(card: dict, *, now: "datetime | None" = None) -> str:
    """Deterministic one-sentence summary from card fields only.

    'Suggestion — acme: Reply to TV2 counsel. This sends a message to a
    real person outside. Waiting 2 days — due in 20 hours.'
    """
    what = str(card.get("what") or "").strip() or COPY["no_title"]
    lane = str(card.get("lane") or "").strip()
    head = kind_name(card.get("kind"))
    if lane:
        head = f"{head} — {lane}"
    parts = [f"{head}: {what.rstrip('.')}."]
    parts.append(risk_sentence(card))
    clock_bits = [b for b in (age_plain(card.get("age_h")),
                              due_plain(card.get("deadline_iso"), now)) if b]
    if clock_bits:
        parts.append((" — ".join(clock_bits)).capitalize() + ".")
    return " ".join(p for p in parts if p)


def door_buttons(kind: "str | None") -> dict[str, str]:
    return dict(DOOR_BUTTONS.get(str(kind or ""), DOOR_BUTTONS[""]))


def _fill(template: str, card: dict) -> str:
    what = str(card.get("what") or "").strip() or COPY["no_title"]
    return (template
            .replace("{risk}", risk_sentence(card))
            .replace("{what}", what.rstrip(".") + "."))


def consequence_for(card: dict, verb: str) -> str:
    """The consequence sentence shown at the two-step confirm (deck steal #3:
    every mutating verb shows consequence + undo BEFORE firing)."""
    kind = str(card.get("kind") or "")
    tpl = (CONSEQUENCE_TEMPLATES.get(f"{verb}:{kind}")
           or CONSEQUENCE_TEMPLATES.get(verb)
           or CONSEQUENCE_TEMPLATES["later"])
    return _fill(tpl, card)


def undo_for(card: dict, verb: str) -> str:
    blast = card.get("blast") or {}
    blast = blast if isinstance(blast, dict) else {}
    if verb == "approve":
        # No-return actions FIRST: an undo line must never promise a
        # pull-back on money out the door or a message a human already read.
        if no_return(blast.get("reach"), card.get("blast_worst_case")):
            return UNDO_TEMPLATES["approve:no-return"]
        if blast.get("class") == "ceiling":
            return UNDO_TEMPLATES["approve:ceiling"]
    return _fill(UNDO_TEMPLATES.get(verb) or UNDO_TEMPLATES["later"], card)


# ---------------------------------------------------------------------------
# The jargon linter — the law's teeth (Ruling B: "enforced as a test").
# ---------------------------------------------------------------------------

#: term -> the plain replacement (jargon-audit §8). Matched case-insensitive
#: on word boundaries. Keys never render; values must themselves be plain.
BANNED: dict[str, str] = {
    "binder": "Telegram",
    "verdict": "your decision",
    "verdicts": "your decisions",
    "pid": "(never shown)",
    "pids": "(never shown)",
    "situation_key": "(never shown)",
    "blast": "'If you approve: …' sentence",
    "ceiling": "highest caution",
    "canonical": "(drop it)",
    "census": "the list",
    "admission": "(hide it)",
    "shelf": "this week",
    "demotion": "bumped down",
    "demotions": "bumped down",
    "demote": "bump down",
    "demoted": "bumped down",
    "decay": "bumped down",
    "dormant": "parked",
    "standing card": "this message",
    "standing message": "this message",
    "charter": "(hide it)",
    "germline": "the cabinet's core rules",
    "founder-action": "your to-do",
    "graduated cell": "standing approval",
    "needs ledger": "permission ask",
    "consolidation need": "(hide it)",
    "lane": "the product's name",
    "wardroom": "the map",
    "act-then-tell": "done — here's what I did",
    "injection-suspect": "came from an untrusted outside message",
    "falsifier": "(hide it)",
    "undo-rate": "(hide it)",
    "opaque handle": "(never shown)",
    "untitled situation": "(no title)",
    "t2": "the First Mate asked you",
}

_BANNED_RES: list[tuple[str, "re.Pattern[str]"]] = [
    (term, re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])",
                      re.IGNORECASE))
    for term in BANNED
]


def lint(text: "str | None") -> list[dict]:
    """Scan captain-facing text for banned org vocabulary.

    Returns one violation dict per hit: {term, index, plain}. Callers lint
    ONLY surface copy — content behind a Details disclosure is allowlisted by
    construction (it is never passed here)."""
    if not text:
        return []
    out: list[dict] = []
    for term, rx in _BANNED_RES:
        for m in rx.finditer(text):
            out.append({"term": term, "index": m.start(), "plain": BANNED[term]})
    return sorted(out, key=lambda v: (v["index"], v["term"]))


def lint_many(texts: "list[str] | tuple[str, ...]") -> list[dict]:
    out: list[dict] = []
    for t in texts:
        out.extend(lint(t))
    return out


# ---------------------------------------------------------------------------
# Export — the dashboard's tables (one source of truth, committed as
# cabinet/dashboard/src/lib/attention/plain.json; drift-pinned by pytest).
# ---------------------------------------------------------------------------


def export_plain_json() -> dict:
    return {
        "v": 1,
        "banned": dict(BANNED),
        "kind_names": dict(KIND_NAMES),
        "kind_name_default": KIND_NAME_DEFAULT,
        "state_names": dict(STATE_NAMES),
        "state_name_default": STATE_NAME_DEFAULT,
        "decided_states": sorted(DECIDED_STATES),
        "risk_sentences": dict(RISK_SENTENCES),
        "risk_default": RISK_DEFAULT,
        "risk_default_ceiling": RISK_DEFAULT_CEILING,
        "kind_risk_defaults": dict(KIND_RISK_DEFAULTS),
        "no_return_worst_cases": sorted(NO_RETURN_WORST_CASES),
        "button_labels": {k: list(v) for k, v in BUTTON_LABELS.items()},
        "door_buttons": {k: dict(v) for k, v in DOOR_BUTTONS.items()},
        "ritual_kinds": sorted(RITUAL_KINDS),
        "messages": dict(MESSAGES),
        "results": dict(RESULTS),
        "consequence_templates": dict(CONSEQUENCE_TEMPLATES),
        "undo_templates": dict(UNDO_TEMPLATES),
        "copy": dict(COPY),
    }


def main(argv: "list[str] | None" = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="framework.attention.plain")
    ap.add_argument("--export", action="store_true",
                    help="print the dashboard plain.json tables to stdout")
    args = ap.parse_args(argv)
    if args.export:
        print(json.dumps(export_plain_json(), ensure_ascii=False, indent=2,
                         sort_keys=True))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
