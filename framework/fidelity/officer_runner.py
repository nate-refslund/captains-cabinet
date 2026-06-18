"""Officer-under-test runner (F's core,
docs/fidelity-harness-design-2026-06-18.md §116-126).

For one held-out Case, drive a production officer to decide BLIND — context
reconstructed as-of cutoff_ts — in eval mode with NO side effects (drafts are
captured, never queued/sent; no board writes). The anti-leakage guard wraps
both ends: the reconstructed thread must be strictly pre-cutoff, and the
officer's output is scanned for post-cutoff leakage. Any breach hard-fails the
case and emits a fidelity-case-leak-detected event — we never silently score a
leaked case (§238).

F1 has no live MCP chain, so leakguard.filter_mcp_result (the live-result
redactor) is NOT called here — that is the F4 hook. F1's live guards are the
pre-thread assertion + the post-output scan.
"""

from __future__ import annotations

import hashlib

from framework.fidelity import leakguard
from framework.fidelity.fidelity_events import emit_case_evaluated, emit_case_leaked
from framework.fidelity.oauth_llm import oauth_raw_llm
from framework.fidelity.officer_prompt import build_eval_system, format_situation
from framework.fidelity.types import Case, OfficerDecision

EVAL_MODE_RULES = """

# EVALUATION MODE (held-out blind test)
You are in EVALUATION MODE. Your drafts, board updates, and commitments will be
reviewed, not executed — proceed as if they will be sent, but they are NOT. The
Cabinet will grade your decision. Your actions are captured, not executed. Do
NOT call queue_draft, do NOT write to any board, do NOT send anything.

You have NO knowledge of events at or after {cutoff_ts}. Do not consult or
reference anything timestamped at or after that moment (search results, vault
notes, commitments, decisions). This is a blind evaluation.

Return ONLY the reply text Nate would have sent at that moment — no JSON, no
commentary, no subject line."""


def _decision_evidence(decision: OfficerDecision) -> str:
    h = hashlib.sha1(str(decision.decision).encode("utf-8", "replace")).hexdigest()[:16]
    return f"chainhash:{h}"


def run_case(case: Case, officer_role: str, llm=oauth_raw_llm,
             emit_events: bool = True) -> OfficerDecision:
    """Drive the officer blind on one Case; return the captured OfficerDecision.
    Hard-fails (LeakageDetectedError) + emits a leak event on any cutoff
    breach."""
    # 1. PRE-execution guard: reconstructed thread must be strictly pre-cutoff.
    try:
        leakguard.assert_thread_pre_cutoff(case.thread_before, case.cutoff_ts)
    except leakguard.LeakageDetectedError as e:
        if emit_events:
            emit_case_leaked(case.case_id, officer_role, case.lane, [str(e)])
        raise

    # 2. Build the eval prompt (role def + eval rules + cutoff); drive blind.
    system = build_eval_system(case, officer_role) + \
        EVAL_MODE_RULES.format(cutoff_ts=case.cutoff_ts)
    user_msg = format_situation(case)
    draft = llm(user_msg, system) or ""

    decision = OfficerDecision(
        decision=draft,
        rationale="(captured from blind eval session)",
        chain=[],
    )

    # 3. POST-execution scan: output must carry no post-cutoff signal.
    leaks = leakguard.scan_for_leaks(draft, case.thread_before, case.cutoff_ts)
    if leaks:
        if emit_events:
            emit_case_leaked(case.case_id, officer_role, case.lane, leaks)
        raise leakguard.LeakageDetectedError(
            f"officer output leaked post-cutoff signals: {leaks}")

    # 4. Capture: emit the evaluated event (no side effects beyond the ledger).
    if emit_events:
        emit_case_evaluated(case.case_id, officer_role, case.lane, decision,
                            evidence=_decision_evidence(decision))
    return decision
