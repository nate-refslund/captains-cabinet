"""The Cabinet acting loop — captain-response router + consequence recorder.

The dry-run CORE of the first acting lane (Phase 1, grand-plan-2026-06-21). It is
PURE: it classifies the captain's reply to a draft proposal and builds the
consequence-ledger events (proposal -> superseding outcome+review). No live I/O —
no Telegram send, no queue_draft, no file writes; those wrap around this core via
injected dispatch in a later slice, so this stays fully unit-testable and safe.

The captain's reply drives the ladder: **approve = proof (climb), edit =
correction, skip = boundary**, plus the two shapes Nate asked for — instance
*instruction* ("also build A and tell them when done") and standing *policy*
("don't reply to these people unless they explicitly await me").

The deterministic router here is a v1 heuristic + fallback; in production the
cabinet officer (an LLM) interprets the captain's message natively and may
override `primary`. The RECORDER is the durable contract: every event it builds
passes ``framework.fidelity.consequence.validate_consequence``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from framework.fidelity.consequence import emit_consequence, validate_consequence

# captain-response -> ledger lifecycle. review.verdict feeds the ladder's
# review_confirmed_rate: ONLY "approve" is proof. "edit"=the draft was wrong
# (his rewrite ships, but the clone's proposal was not what he'd send);
# "skip"=nothing ships, reason varies -> honest "unknown".
_VERDICT = {
    "approve": {"decision": "approved", "status": "ok",      "verdict": "confirmed",
                "evidence": "captain approved the draft as-is"},
    "edit":    {"decision": "edited",   "status": "ok",      "verdict": "wrong",
                "evidence": "captain edited the draft before it shipped"},
    "skip":    {"decision": "rejected", "status": "unknown", "verdict": "unknown"},
}


@dataclass
class RoutedResponse:
    """The structured read of a captain's Telegram reply. `primary` is the
    draft decision (approve/edit/skip/none); a single message may ALSO carry
    instructions (new imperative work) and/or policies (standing rules)."""
    primary: str = "none"          # "approve" | "edit" | "skip" | "none"
    edit_text: str = ""
    skip_why: str = ""
    instructions: list = field(default_factory=list)   # imperative tasks to spawn
    policies: list = field(default_factory=list)        # standing behavior rules
    correction: str = ""           # free-text correction signal (edit/skip -> lesson)
    raw: str = ""


# --- explicit verbs (the existing draft-reply contract) ---
_EDIT_RE = re.compile(r"^\s*edit\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)
_SKIP_RE = re.compile(r"^\s*skip\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)
# emojis are not word chars, so \b after them never matches — match them as a
# separate alternative without the boundary.
_APPROVE_RE = re.compile(r"^\s*((send|ok|okay|approve[d]?|yes|ja)\b|[👍👌🚀✅])",
                         re.IGNORECASE)
_DRAFT_PREFIX = re.compile(r"^\s*draft[-\s]?reply[:,\s]*", re.IGNORECASE)

# --- bilingual (EN + DA) markers. Nate writes Danish; production uses the
#     officer LLM, but the heuristic must handle his common shapes. ---
_INSTR_RE = re.compile(
    r"\b(also|then|and (also )?(build|make|create|do|send|tell|ping|notify|draft|"
    r"fix|add|set up)|go ahead and|once done|when done|afterwards|"
    r"byg|bygge|lav|lave|opret|opretter|s(æ|ae)t op|sig til|giv besked|"
    r"n(å|aa)r det er|bagefter|derefter|og s(å|aa)|g(å|aa) (også |ogsaa )?i gang)\b",
    re.IGNORECASE)
_POLICY_RE = re.compile(
    r"\b(don'?t|do not|never|always|stop|from now on|in general|unless|"
    r"only (reply|respond)|going forward|"
    r"ikke|aldrig|altid|fremover|generelt|medmindre|kun (svar|reply))\b",
    re.IGNORECASE)


def route_captain_response(text: str) -> RoutedResponse:
    """Classify a captain reply into a RoutedResponse (v1 heuristic + fallback)."""
    t = (text or "").strip()
    r = RoutedResponse(raw=t)
    if not t:
        return r

    m = _EDIT_RE.match(t)
    if m:
        r.primary = "edit"
        r.edit_text = m.group(1).strip()
        r.correction = r.edit_text
        return r

    m = _SKIP_RE.match(t)
    if m:
        r.primary = "skip"
        r.skip_why = m.group(1).strip()
        r.correction = r.skip_why
        if _POLICY_RE.search(r.skip_why):
            r.policies.append(r.skip_why)
        return r

    head = _DRAFT_PREFIX.sub("", t)
    if _APPROVE_RE.match(head):
        r.primary = "approve"
        rest = _APPROVE_RE.sub("", head, count=1).strip(" ,.-—\n")
        if rest and _INSTR_RE.search(rest):
            r.instructions.append(rest)
        elif rest and _POLICY_RE.search(rest):
            r.policies.append(rest)
        return r

    # No explicit draft verb — a standalone policy or instruction.
    if _POLICY_RE.search(t):
        r.policies.append(t)
    elif _INSTR_RE.search(t):
        r.instructions.append(t)
    return r


def proposal_event(*, actor: dict, lane: str | None, subject: str, ts: str,
                   action: str = "draft-reply", required: bool = True,
                   refs: list | None = None) -> dict:
    """A PENDING proposal event (decision not yet made). ``required`` defaults
    True: an acting-lane draft requires the captain's decision (nothing ships
    unapproved). Content (the draft) is
    NOT stored here — the ledger records the decision lifecycle, not the message
    (leak-safe). The draft lives in the Telegram prompt / outbox; reference it
    via `refs` if needed."""
    ev = {
        "ts": ts, "actor": actor, "lane": lane, "action": action,
        "subject": subject, "refs": list(refs or []),
        "proposal": {"required": bool(required), "decision": None},
    }
    validate_consequence(ev)
    return ev


def outcome_event(proposal_ev: dict, routed: RoutedResponse, *,
                  evidence: str | None = None,
                  reviewed_at: str | None = None,
                  lesson_ref: str | None = None) -> dict:
    """The SUPERSEDING outcome+review event for a decided draft. Reuses the
    proposal's identity tuple (actor, action, subject, ts) so the ledger reader
    takes this as the final state of that proposal. Raises if the response had
    no draft decision (primary='none' -> caller handles policy/instruction with
    no outcome to record)."""
    if routed.primary not in _VERDICT:
        raise ValueError(
            f"outcome_event needs a draft decision; got primary={routed.primary!r} "
            "(a policy/instruction-only reply has no draft outcome to record)")
    m = _VERDICT[routed.primary]
    decided_at = reviewed_at or proposal_ev["ts"]
    ev = dict(proposal_ev)
    ev["proposal"] = {
        "required": proposal_ev.get("proposal", {}).get("required", False),
        "decision": m["decision"],
        "decided_at": decided_at,
    }
    ev["outcome"] = {"status": m["status"]}
    if m["status"] in ("ok", "failed"):   # ledger requires evidence for these
        ev["outcome"]["evidence"] = evidence or m.get("evidence") or "recorded"
    ev["review"] = {"verdict": m["verdict"]}
    if reviewed_at:
        ev["review"]["reviewed_at"] = reviewed_at
    if lesson_ref:
        ev["review"]["lesson_ref"] = lesson_ref
    validate_consequence(ev)
    return ev


def run_lane(*, thread_ref, subject: str, ts: str, actor: dict,
             gather, draft_fn, present, get_response, dispatch,
             lane: str = "send-1to1-reply", emit=emit_consequence,
             refs: list | None = None) -> dict:
    """Orchestrate ONE pass of the acting lane — fully dependency-injected so it
    runs identically dry (stubs) or live (brain / Telegram / queue_draft). The
    captain stays in the loop: nothing is dispatched until ``get_response``
    returns the captain's decision.

    Injected deps:
      gather(thread_ref) -> context (brain MCP gather, or a stub)
      draft_fn(thread_ref, context) -> draft str | None  (None = gate: no reply)
      present(draft, proposal_event) -> None   (Telegram prompt, or record)
      get_response() -> str                    (captain reply, or simulated)
      dispatch(routed, draft, proposal_event) -> None  (queue_draft/log_lesson/…)
      emit(**event) -> persists the consequence event (default: the real ledger)
    """
    ctx = gather(thread_ref)
    draft = draft_fn(thread_ref, ctx)
    if not draft:
        return {"thread_ref": thread_ref, "status": "gated"}

    prop = proposal_event(actor=actor, lane=lane, subject=subject, ts=ts, refs=refs)
    emit(**prop)
    present(draft, prop)

    routed = route_captain_response(get_response())
    result = {"thread_ref": thread_ref, "status": "decided",
              "primary": routed.primary, "routed": routed, "draft": draft}
    if routed.primary in _VERDICT:
        out = outcome_event(prop, routed)
        emit(**out)
        result["verdict"] = out["review"]["verdict"]
    dispatch(routed, draft, prop)
    return result
