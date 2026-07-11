"""Eval-mode prompt assembly for the officer-under-test.

Builds the system prompt (officer role definition + decision-type context) and
the cutoff-safe situation text from a Case's thread_before. The held-out reply
(case.real_reply) is NEVER included anywhere in the prompt — that is the ground
truth the officer must reconstruct blind."""

from __future__ import annotations

import os
import re
from pathlib import Path

from framework.env import captain_name
from framework.fidelity.types import Case

_REPO_ROOT = Path(
    os.environ.get("CABINET_ROOT", str(Path(__file__).resolve().parents[2]))
)
_AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"


def role_definition(officer_role: str) -> str:
    """Read .claude/agents/<role>.md (the runtime-populated officer charter dir,
    set by load-preset.sh as $CABINET_ROOT/.claude/agents). If absent (eval
    running before the preset is loaded), return a minimal header — never crash
    the eval."""
    f = _AGENTS_DIR / f"{officer_role}.md"
    if f.exists():
        return f.read_text(errors="replace")
    return (f"# Officer: {officer_role}\n"
            "You are a Cabinet officer making a decision under the "
            "courses-of-action rule. (Role definition file not found; deciding "
            "from charter conventions.)")


def build_eval_system(case: Case, officer_role: str) -> str:
    """Role definition + a decision-type context block. No held-out reply."""
    ctx = (f"\n\n# DECISION CONTEXT\nlane: {case.lane}\n"
           f"decision_type: {case.decision_type}\n"
           f"counterparty: {case.person} (channel: {case.channel}, "
           f"language: {case.language})")
    return role_definition(officer_role) + ctx


# ---------------------------------------------------------------------------
# Clone-identity eval prompt (design §1.6; ground retrodiction-clone-draft-
# reference + brain-identity-sources). The REPLY cell drives the officer to
# draft AS THE CAPTAIN'S CLONE — mirroring retrodiction's draft_case: the IDENTITY
# (voice + nate_model patterns + date-filtered drafting lessons + person
# frontmatter) is what shapes the draft; the role charter stays as light role
# context. Assembly order mirrors draft_case's CLONE_PAYLOAD: CAPTAIN MODEL
# (patterns) -> VOICE -> DRAFTING LESSONS -> COUNTERPARTY.
#
# PRIVACY FENCE (paramount). The priors INFORM how the officer writes and
# decides — they are the Captain's private model. They must NEVER be quoted, pasted,
# or referenced into the reply, a captured decision, a consequence event, a
# commit, or any artifact (brain-bridge rule; mirrors me_signal's PRIVATE
# fence). The fence here is the in-prompt instruction; scan_for_leaks + the
# capture layer enforce that nothing emits them. NOTE: this function assembles
# ONLY the system prompt — date-filtering of lessons strictly BEFORE the case
# cutoff is the caller's job (BrainAdapter.drafting_lessons -> retro
# .lessons_before); whatever lands in identity["lessons"] is injected verbatim.
# ---------------------------------------------------------------------------
def _clone_privacy_fence(cap: str) -> str:
    return (
        f"Use the following to shape HOW you write and decide — they are {cap}'s "
        "PRIVATE model. NEVER quote, paste, or reference them in your reply, in a "
        "decision, in an event, or in any artifact. They inform your style and "
        "judgment only; they never appear in anything you produce.")


def build_clone_eval_system(case: Case, officer_role: str,
                            identity: dict) -> str:
    """Assemble the REPLY-cell system prompt that drives the officer to draft
    AS THE CAPTAIN'S CLONE.

    ``identity`` is ``{voice, patterns, lessons, person_static}`` — the
    current-state priors BrainAdapter hands over (voice.md, nate_model
    ('patterns'), date-filtered drafting lessons, static person frontmatter).
    The IDENTITY drives the draft; ``build_eval_system`` supplies the light
    role + decision-type context so role framing rides along.

    The prompt carries an explicit privacy fence (``_CLONE_PRIVACY_FENCE``):
    the priors shape HOW the clone writes/decides but must never be quoted,
    pasted, or referenced into anything the officer produces. The held-out
    reply (``case.real_reply``) is NEVER included — same guarantee as
    ``build_eval_system``.

    A missing/empty identity key degrades to "(unavailable)" — the prompt
    still assembles and still fences; it never KeyErrors."""
    identity = identity or {}
    cap = captain_name()

    def _val(key: str) -> str:
        v = (identity.get(key) or "").strip()
        return v if v else "(unavailable)"

    block = (
        f"\n\n# CLONE IDENTITY — draft AS {cap.upper()}\n"
        f"You are drafting the reply {cap} himself would send. Become {cap}'s "
        "clone: write in his voice and decide the way he decides.\n\n"
        f"{_clone_privacy_fence(cap)}\n\n"
        f"## How {cap} decides (nate_model patterns)\n{_val('patterns')}\n\n"
        f"## How {cap} writes (voice profile)\n{_val('voice')}\n\n"
        f"## Drafting lessons (date-filtered before the cutoff)\n"
        f"{_val('lessons')}\n\n"
        f"## Counterparty (atemporal frontmatter)\n{_val('person_static')}"
    )
    # role + decision-type context (light) first, then the identity that drives.
    return build_eval_system(case, officer_role) + block


# ---------------------------------------------------------------------------
# INT-3 (sovereign spec D17) — the PERSONAL-AGENT identity. The clone identity
# above is kept VERBATIM as the diagnostic arm (does the officer decide like
# the Captain?); this arm reframes the objective: the officer is the Captain's
# AGENT acting on their behalf, judged by whether the OUTCOME serves the
# Captain's intent as good or better than what the Captain did — mimicry is not
# the goal. Same identity dict,
# same privacy fence; only the framing differs. Default identity stays 'clone'
# until the first AGB baseline is cut (run_case/measure_intent enforce that
# default — flipping silently would breach the A/A shard invariant).
# ---------------------------------------------------------------------------


def build_agent_eval_system(case: Case, officer_role: str,
                            identity: dict) -> str:
    """Assemble the REPLY-cell system prompt that drives the officer to act AS
    THE CAPTAIN'S AGENT (identity_mode='agent').

    Same ``identity`` shape and privacy fence as ``build_clone_eval_system``
    (``{voice, patterns, lessons, person_static}``, missing keys degrade to
    "(unavailable)"), but the mandate is OUTCOME-first: serve the Captain's intent on
    his behalf, free to do better than a literal imitation would. The held-out
    reply (``case.real_reply``) is NEVER included."""
    identity = identity or {}
    cap = captain_name()

    def _val(key: str) -> str:
        v = (identity.get(key) or "").strip()
        return v if v else "(unavailable)"

    block = (
        f"\n\n# AGENT IDENTITY — act ON {cap.upper()}'S BEHALF\n"
        f"You are {cap}'s trusted AI agent handling this thread for him. Your "
        f"objective is the OUTCOME: serve {cap}'s goal in this situation as "
        f"well as — or better than — {cap} himself would. You are NOT required "
        f"to mimic what {cap} would literally have written; you ARE required to "
        "pursue his intent, honor his standing decisions, and stay grounded "
        "in the supplied context (never invent facts).\n\n"
        f"{_clone_privacy_fence(cap)}\n\n"
        f"## How {cap} decides (nate_model patterns)\n{_val('patterns')}\n\n"
        f"## How {cap} writes (voice profile — calibrate tone, do not "
        f"impersonate blindly)\n{_val('voice')}\n\n"
        f"## Drafting lessons (date-filtered before the cutoff)\n"
        f"{_val('lessons')}\n\n"
        f"## Counterparty (atemporal frontmatter)\n{_val('person_static')}"
    )
    # role + decision-type context (light) first, then the identity that drives.
    return build_eval_system(case, officer_role) + block


def _clean(text: str) -> str:
    body = re.sub(r"<!--[^>]*-->", "", text or "")
    return re.sub(r"_\([^)]*\)_", "", body).strip()


def format_situation(case: Case, last_cap: int = 1500, cap: int = 600) -> str:
    """Oldest-first situation text from thread_before only. Sent → the Captain's
    name, received → the sender's display name. Last message keeps more body."""
    who_captain = captain_name()
    msgs = case.thread_before
    lines = [f"# HELD-OUT SITUATION (decide as-of {case.cutoff_ts})",
             f"The conversation below ends just before {who_captain} replied. "
             f"Draft the reply {who_captain} would have sent at that moment.\n"]
    for i, m in enumerate(msgs):
        who = who_captain if m.get("direction") == "sent" else \
            (m.get("who") or "").split("<")[0].strip() or case.person
        body = _clean(m.get("text") or "")
        limit = last_cap if i == len(msgs) - 1 else cap
        lines.append(f"[{(m.get('date') or '')[:16]} {m.get('source', '')}] "
                     f"{who}: {body[:limit]}")
    return "\n".join(lines)


# F4 §1.2 / §5: reconstruct a leak-safe as-of-cutoff intent (mission/goal ×
# core) for the judge to score against. Each field ≤500 chars to keep the
# judge payload lean.
_INTENT_FIELD_CAP = 500
_INTENT_WINDOW = 5  # last ≤5 messages of thread_before ONLY


def intent_and_context(case: Case) -> dict:
    """Reconstruct the as-of-cutoff intent the officer should serve, expressed
    as ``mission/goal × core``, from the **last ≤5 messages of
    ``case.thread_before`` ONLY**.

    PURE function: no MCP calls, no network, no filesystem reads. It NEVER
    reads ``case.real_reply`` — that is the held-out ground truth, and reading
    it would leak the answer into the thing the officer is graded against
    (design §1.2, anti-leak boundary). The latent real-world facts a situation
    implicates (the house, the lawn size) enter the harness ONLY through the
    leak-guarded ``gather_cutoff_context`` path at officer time (§5) — never
    baked in here.

    Returns ``{"reconstructed_intent": str, "mission_or_goal": str}``; both
    fields are capped at ≤500 chars.
    """
    # Window: last ≤5 messages of thread_before ONLY (never real_reply).
    cap = captain_name()
    window = case.thread_before[-_INTENT_WINDOW:]

    # The mission/goal is grounded in the counterparty's most recent ask: the
    # latest received message in the window (what they actually want from the Captain).
    last_received = next(
        (_clean(m.get("text") or "") for m in reversed(window)
         if m.get("direction") == "received" and _clean(m.get("text") or "")),
        "",
    )
    # Thread topic context: the Captain's own latest stated position in the window,
    # so the goal carries the situation's substance, not just the bare ask.
    last_sent = next(
        (_clean(m.get("text") or "") for m in reversed(window)
         if m.get("direction") == "sent" and _clean(m.get("text") or "")),
        "",
    )

    if last_received and last_sent:
        goal = (f"Respond to {case.person}'s request — \"{last_received}\" — "
                f"in light of {cap}'s stated context: \"{last_sent}\".")
    elif last_received:
        goal = f"Respond to {case.person}'s request: \"{last_received}\"."
    elif last_sent:
        goal = (f"Continue the thread with {case.person} from {cap}'s last "
                f"point: \"{last_sent}\".")
    else:
        # Thin/empty thread — name the gap rather than invent intent.
        goal = (f"Reply to {case.person} on a {case.channel} thread with no "
                f"recoverable pre-cutoff content.")
    mission_or_goal = goal[:_INTENT_FIELD_CAP]

    # Core: who the Captain is in this lane — language + channel + standing style.
    # This is the second axis of mission × core; it carries no thread facts
    # of its own, only atemporal style priors, so it never leaks.
    core = (f"decisive, concrete and low-ceremony; replies in {case.language} "
            f"on {case.channel}; gives a direct recommendation over hedging")

    # Compose mission × core so the "Core:" half ALWAYS survives the cap. A naive
    # f"Goal: {goal} Core: {core}"[:CAP] truncates from the RIGHT, which can chop
    # off the entire Core half on a long goal. Instead, budget the goal slice
    # separately: reserve room for the fixed wrapper + the full core, then fit the
    # goal into whatever remains (never negative).
    _wrapper = f"Goal:  Core: {core}"  # fixed overhead incl. the full core text
    goal_budget = max(0, _INTENT_FIELD_CAP - len(_wrapper))
    goal_slice = mission_or_goal[:goal_budget]
    reconstructed_intent = f"Goal: {goal_slice} Core: {core}"
    # Defensive clamp: if `core` alone already exceeds the cap (pathological
    # language/channel), still never exceed CAP — but Core is preserved first.
    reconstructed_intent = reconstructed_intent[:_INTENT_FIELD_CAP]

    return {
        "reconstructed_intent": reconstructed_intent,
        "mission_or_goal": mission_or_goal,
    }
