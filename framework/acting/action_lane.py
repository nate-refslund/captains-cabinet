"""Capture→action lane — PURE proposal core (the Captain-ruled pivot, 2026-07-03).

Nate handles all communication himself; the cabinet acts on what the captured
world implies: create/update tasks, set reminders, close what's already done.
This module is the DECISION core of that lane: a pure function from gathered
signals to carded ActionProposals. It does no I/O — every source (signals,
decided subjects, budget, clock, LLM) is injected — so the SAME code serves the
live lane and the retrodiction/simulation harness (replay a historical `as_of`
with point-in-time-fenced signals and compare against what Nate actually did).

Design anchors:
  - captain-decisions.md 2026-07-03 "PIVOT: away from draft-replies, toward
    proactive actions" + 2026-07-02 "Cabinet = PO over the backlog".
  - Nate's graduated-autonomy model verbatim: propose-first per category;
    auto only once a cell's confidence is earned (the graduation engine now
    reads live — verdicts on these very cards are what feed it).
  - courses-of-action germline rule: ONE card per situation carrying the whole
    step chain; gather-then-decide; never re-ask an answered question.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

# Action vocabulary. Captain ruling 2026-07-03 ("not just PM/PO — do actual
# work that would solve the tasks"): delegate_work dispatches an implementation
# brief to an officer lane, so an approved card can SOLVE, not just track.
# reminder_create lands on the Captain's CALENDAR by default (Apple Reminders
# is an optional per-instance plugin — his ruling: good for personal, not work).
ACTION_KINDS = ("monday_task_create", "monday_task_update", "reminder_create",
                "delegate_work")
URGENCIES = ("ping-now", "batch")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Stable situation slug for dedup across runs (subject identity)."""
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")[:80]


@dataclass(frozen=True)
class ActionStep:
    kind: str                 # one of ACTION_KINDS
    title: str                # short imperative, shown on the card
    payload: dict = field(default_factory=dict)   # kind-specific fields


@dataclass(frozen=True)
class ActionProposal:
    subject: str              # stable slug — the dedup + ledger identity
    situation: str            # one-line human summary of WHY
    steps: tuple              # tuple[ActionStep] — the full chain, ONE card
    lane: str                 # e.g. "polads" (PolAds-first per the ruling)
    evidence: tuple           # source refs (vault paths / note ids), audit trail
    confidence: float         # model's own 0..1 — recorded, never auto-acts in v1
    urgency: str = "batch"    # ping-now | batch


# ---------------------------------------------------------------------------
# LLM contract — the proposer prompt returns strict JSON; parse defensively.
# ---------------------------------------------------------------------------

PROPOSER_SYSTEM = """You are the action-proposal core of Nate's cabinet.
Nate handles ALL communication himself. You propose ACTIONS the captured world
implies — never reply drafts. Allowed action kinds (nothing else):
- monday_task_create: {board_hint, title, description, priority?, due?}
- monday_task_update: {monday_id, set: {status?|priority?|due?|description?}, why}
- reminder_create: {title, due_iso, notes?} — lands as a CALENDAR event/block on
  Nate's calendar (never a personal to-do app)
- delegate_work: {officer: "polads-ceo"|"stephie-ceo"|"comms-officer"|"cos",
  brief: str} — dispatches a precise implementation brief to that officer's
  lane so the work actually gets DONE on approval

Rules:
- SOLVE, don't just track (Captain ruling): when the situation has a concrete
  fix, the chain must carry the steps that COMPLETE it — investigation,
  delegate_work with an exact brief, the tracking task — so approving the card
  solves the situation, not merely files it. A bare create-task chain is only
  right when the work genuinely needs Nate himself.
- ONE proposal per SITUATION, carrying ALL steps that situation needs, in order.
- Only propose what the evidence supports. Cite evidence refs you were given.
- Skip anything already decided, already tracked, or already done.
- Propose EVERY situation that genuinely needs handling — there is no quota;
  the bar is genuine need, not count.
- situation: complete sentences, self-contained (it is shown to Nate in full).
- Confidence = your honest probability Nate approves unchanged.
- Urgency "ping-now" ONLY if it would be wrong or worthless by tomorrow.
Return STRICT JSON: {"proposals": [{"situation": str, "subject_hint": str,
"lane": str, "urgency": "ping-now"|"batch", "confidence": float,
"evidence": [str], "steps": [{"kind": str, "title": str, "payload": {}}]}]}
Return {"proposals": []} when nothing clears the bar."""


def _parse_llm(raw: str) -> list[dict]:
    """Strict-ish parse: accept the JSON object anywhere in the reply."""
    if not raw:
        return []
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    props = data.get("proposals")
    return props if isinstance(props, list) else []


def _valid_step(s: Any) -> bool:
    return (isinstance(s, dict) and s.get("kind") in ACTION_KINDS
            and isinstance(s.get("title"), str) and s["title"].strip() != ""
            and isinstance(s.get("payload", {}), dict))


def propose_actions(
    signals_text: str,
    *,
    as_of: str,
    llm: Callable[[str, str], str],
    decided_subjects: set,
    open_subjects: set,
    budget_left: int,
    lane_default: str = "polads",
    covered_evidence: frozenset = frozenset(),
) -> list[ActionProposal]:
    """The pure decision step: signals in, ≤budget carded proposals out.

    signals_text: the gathered, ALREADY point-in-time-fenced evidence bundle
      (the caller owns fencing; in replay mode it must contain nothing newer
      than `as_of`).
    llm(system, user) -> raw text. Injected: live model or replay stub.
    decided_subjects / open_subjects: slugs the ledger says are settled or
      currently pending — both are skipped (never re-ask an answered question;
      never double-card an open one).
    covered_evidence: evidence refs already carried by ANY prior action card
      (open or decided). Slug dedup alone is insufficient — the LLM re-words
      subjects between runs (the 5-cards-for-2-situations incident, 2026-07-03),
      but the underlying evidence refs (commitment ids, note paths) are stable.
      A proposal citing ANY covered ref is dropped: same evidence = same
      situation, no matter how it is phrased.
    budget_left: hard cap on proposals returned this run (daily ask budget).
    """
    if budget_left <= 0 or not (signals_text or "").strip():
        return []

    user = (f"as_of: {as_of}\n\nCaptured signals (fenced; cite refs):\n"
            f"{signals_text}\n\nPropose at most {budget_left} action cards.")
    out: list[ActionProposal] = []
    seen: set = set()
    for p in _parse_llm(llm(PROPOSER_SYSTEM, user)):
        if len(out) >= budget_left:
            break
        if not isinstance(p, dict):
            continue
        steps = [s for s in (p.get("steps") or []) if _valid_step(s)]
        if not steps:
            continue
        subject = slugify(p.get("subject_hint") or p.get("situation") or "")
        if not subject or subject in seen:
            continue
        if subject in decided_subjects or subject in open_subjects:
            continue
        evidence_refs = {str(e)[:200] for e in (p.get("evidence") or [])[:8]}
        if evidence_refs & set(covered_evidence):
            continue   # same underlying evidence as an existing card — dedup
        try:
            confidence = max(0.0, min(1.0, float(p.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        urgency = p.get("urgency") if p.get("urgency") in URGENCIES else "batch"
        seen.add(subject)
        out.append(ActionProposal(
            subject=subject,
            situation=str(p.get("situation") or "")[:800],
            steps=tuple(ActionStep(kind=s["kind"], title=s["title"].strip()[:200],
                                   payload=dict(s.get("payload") or {}))
                        for s in steps[:6]),
            lane=str(p.get("lane") or lane_default)[:40],
            evidence=tuple(str(e)[:200] for e in (p.get("evidence") or [])[:8]),
            confidence=confidence,
            urgency=urgency,
        ))
    return out


# card kind -> classifier action_type. Only semantically-true mappings; a
# target absent from the classifier enum is simply never stamped (guarded in
# chain_action_type), so this map can lead the germline amendment safely.
ACTION_TYPE_MAP = {
    "monday_task_update": "board_status",   # exists today: status/label/due on a board item
    "monday_task_create": "task_create",    # pending germline amendment (2026-07-03)
}


def chain_action_type(prop: "ActionProposal"):
    """The single classifier action_type for a card, or None. Stamps only when
    every step maps to the SAME valid enum value — a mixed chain stays
    unstamped rather than mis-bucketing a graduation cell."""
    try:
        from framework.authority.classifier import ACTION_TYPES
    except Exception:
        return None
    mapped = {ACTION_TYPE_MAP.get(s.kind) for s in prop.steps}
    if len(mapped) == 1:
        at = mapped.pop()
        if at and at in ACTION_TYPES:
            return at
    return None


def _no_marker(s: str) -> str:
    """Strip the pid-marker char (U+00B7) from model/vault-derived text so a
    correspondent (or the model itself) can never inject a fake ·pid· into the
    card the binder parses — same defense as the draft lane's card."""
    return (s or "").replace("·", "")


def render_card(prop: ActionProposal, pid: str) -> str:
    """The Telegram card. ONE situation, the whole chain, per-step lines, the
    ·pid· marker LAST (the binder binds the last marker that is a real open
    proposal). Every proposal-derived field is marker-stripped here."""
    steps = "\n".join(f"  {i}. [{s.kind}] {_no_marker(s.title)}"
                      for i, s in enumerate(prop.steps, 1))
    return (
        f"⚡ Action proposal — {_no_marker(prop.lane)}\n\n"
        f"Situation: {_no_marker(prop.situation)}\n\n"
        f"Steps:\n{steps}\n\n"
        f"evidence: {_no_marker(', '.join(prop.evidence[:3])) or '—'}\n"
        f"confidence: {prop.confidence:.2f}   urgency: {prop.urgency}\n\n"
        f"Reply:  approve  /  edit: <changes>  /  skip: <why>\n"
        f"·{pid}·"
    )
