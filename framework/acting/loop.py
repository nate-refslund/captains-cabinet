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

# --- FIX A: an approve token is FAIL-CLOSED if its remainder HOLDS or NEGATES
#     the send. Two shapes, checked against the post-approve remainder:
#     (1) a hold/cancel word (vent, wait, stop, cancel, undlad, not yet, …);
#     (2) a NEGATED send/reply — EN "don't/never + send/reply/…", or DA
#         post-verb negation "send/svar/skriv/reply + (det) ikke". If either
#         matches, DOWNGRADE primary approve -> none (never auto-send). ---
_HOLD_CANCEL_RE = re.compile(
    r"\b(vent|wait|hold on|hold op|hold|stop|cancel|annuller|undlad|"
    r"glem det|never mind|nevermind|ikke endnu|not yet|"
    r"drop it|drop den|drop det|drop)\b",
    re.IGNORECASE)
_NEGATED_SEND_RE = re.compile(
    # EN/leading negation: don't / do not / aldrig / never  +  a send verb.
    r"\b(don'?t|do not|aldrig|never)\b[^.!?\n]*\b(send|reply|svar|skriv)\b"
    r"|"
    # DA post-verb negation: send/svar/skriv/reply  +  (det) ikke.
    r"\b(send|svar|skriv|reply)\b[^.!?\n]*\b(det )?ikke\b",
    re.IGNORECASE)

# --- FIX F: a standalone (no send/edit/skip verb) reply only records a DURABLE
#     policy when it carries a GENERALIZING marker. A bare one-off refusal
#     ("please dont send this") is NOT a standing rule. ---
_GENERALIZE_RE = re.compile(
    r"\b(in general|always|never|from now on|going forward|unless|"
    r"only reply|these people|these threads|"
    r"generelt|altid|aldrig|fremover|medmindre|disse)\b",
    re.IGNORECASE)


def _holds_or_negates_send(text: str) -> bool:
    """True when `text` (an approve-remainder) holds or negates the send —
    the FIX-A fail-closed condition. Empty/no-signal remainder is safe."""
    if not text:
        return False
    return bool(_HOLD_CANCEL_RE.search(text) or _NEGATED_SEND_RE.search(text))


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
        # FIX A (fail-closed): if the remainder holds or negates the send, the
        # leading "ok/ja/send" is NOT an approval — downgrade to none (never
        # auto-send). The remainder's instruction/policy is still captured.
        if _holds_or_negates_send(rest):
            r.primary = "none"
        # FIX C: capture instruction AND policy INDEPENDENTLY (two ifs, not
        # if/elif) so a compound "send, also build A, and in general suppress
        # marketing threads" keeps BOTH lists non-empty.
        if rest and _INSTR_RE.search(rest):
            r.instructions.append(rest)
        # A durable policy in the remainder needs a GENERALIZING marker (same bar
        # as the standalone branch) — so a one-off contradiction like "but do not
        # send this" is NOT mis-recorded as a standing rule.
        if rest and _GENERALIZE_RE.search(rest):
            r.policies.append(rest)
        return r

    # No explicit draft verb — a standalone policy or instruction.
    # FIX F: a bare refusal becomes a DURABLE policy only with a generalizing
    # marker; otherwise it is a one-off (primary=none, no policy captured).
    if _POLICY_RE.search(t):
        if _GENERALIZE_RE.search(t):
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
    # FIX D: the ledger rejects lesson_ref on confirmed/unknown — only attach it
    # when the mapped verdict is 'wrong' (an edit). A lesson_ref passed for an
    # approve/skip is silently dropped rather than producing an invalid event.
    if lesson_ref and m["verdict"] == "wrong":
        ev["review"]["lesson_ref"] = lesson_ref
    validate_consequence(ev)
    return ev


def expire_event(proposal_ev: dict, *, reviewed_at: str | None = None) -> dict:
    """The SUPERSEDING event that closes a PENDING proposal as 'expired' — the
    captain's reply carried no draft decision (a policy/instruction-only reply),
    so the draft is never sent and the proposal must not dangle pending forever.

    Supersedes on the proposal's identity tuple (actor, action, subject, ts)
    exactly like ``outcome_event`` (dict(proposal_ev) then override). There is
    NO outcome object (nothing shipped); the review verdict is 'unknown' (no
    proof, no correction — the ladder neither climbs nor records a lesson)."""
    decided_at = reviewed_at or proposal_ev["ts"]
    ev = dict(proposal_ev)
    ev["proposal"] = {
        "required": proposal_ev.get("proposal", {}).get("required", False),
        "decision": "expired",
        "decided_at": decided_at,
    }
    ev["review"] = {"verdict": "unknown"}
    if reviewed_at:
        ev["review"]["reviewed_at"] = reviewed_at
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

    # TODO(live-split): the live event-driven split is the NEXT slice, not this
    # one. Break run_lane into propose() (gather/draft/present + emit the pending
    # proposal, return a proposal_id/correlation key) and handle_response() (match
    # a later reply to its pending proposal via that key, route, then
    # outcome_event/expire_event). Needs: a pending_proposals() ledger reader, a
    # proposal_id carried on refs so re-delivered replies are idempotent, and an
    # expire-on-timeout cron firing expire_event for proposals never answered.
    # route_captain_response/proposal_event/outcome_event/expire_event are PURE
    # and drop into handle_response() unchanged (reviewer-confirmed).
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
    else:
        # FIX B: a policy/instruction-only reply (primary='none') made no draft
        # decision — close the pending proposal as 'expired' instead of leaving
        # it dangling forever.
        exp = expire_event(prop)
        emit(**exp)
        result["status"] = "expired"
    # FIX E (fail-closed): the draft physically reaches dispatch ONLY on an
    # explicit approve — every other path (skip/edit/none) passes draft=None, so
    # no non-approve route can send the draft.
    dispatch(routed, draft if routed.primary == "approve" else None, prop)
    return result
