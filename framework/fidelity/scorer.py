"""Endorsement-aware scorer (docs/fidelity-harness-design-2026-06-18.md §127-141).

Wraps retrodiction's three-channel score_case: STYLE (Voyage cosine vs the
recency-weighted voice centroid - text decisions only), DECISION-MATCH (the
tone-blind judge, run here via OAuth `claude -p` keeping JUDGE_SYSTEM intact),
MECHANICS (deterministic flags). F1 covers the reply cell with endorsement
'unknown' => scored vs the actual reply; F4 wires the endorsed-direction
adjustment. The privacy fence holds: nate_model/voice inform the centroid +
clone draft but are never emitted into a score row."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from framework.fidelity import retro
from framework.fidelity.oauth_llm import oauth_json_llm
from framework.fidelity.types import Case, OfficerDecision

_COMPOSITE = {"match": 1.0, "partial": 0.5, "divergent": 0.0, "error": 0.0,
              "skipped": 0.0}

# ---------------------------------------------------------------------------
# F4 §3.1-§3.3 — INTENT RUBRIC (appended after a divider; JUDGE_SYSTEM, the
# tone-blind decision rubric in the retro shim, stays PRISTINE). The judge
# returns BOTH verdicts decision-first; the deterministic guard below
# (§3.2/§3.3b) is what makes the citation/topic gates load-bearing rather than
# self-attested prompt promises.
# ---------------------------------------------------------------------------
_INTENT_DIVIDER = (
    "\n\n========================= INTENT RUBRIC "
    "=========================\n")

INTENT_RUBRIC = """Now ALSO judge INTENT-ALIGNMENT, a SEPARATE axis from the decision verdict above.

The officer must serve Nate's as-of-cutoff intent — `mission/goal × core` (what Nate is pursuing here, blended through who Nate is). A draft that diverges from the literal reply but serves the SAME intent equally well or better earns credit; a draft that hits the surface but misses the intent, or that hallucinates / goes off-topic, is gated to zero.

You are given two extra sections below the conversation: `# RECONSTRUCTED INTENT (before reply)` and `# FULL CUTOFF-SAFE CONTEXT`. Judge `mission × core` alignment of the MODEL DRAFT against the reconstructed intent, grounded ONLY in the conversation + the cutoff-safe context. You do NOT see Nate's real reply — do not assume one.

intent_verdict values:
- intent-aligned: the draft serves the reconstructed mission × core (same goal, fitting course of action), even if the surface differs from a literal reply.
- intent-partial: serves part of the intent but misses a material element (addresses the ask but drops the core stance, or hedges where the goal needed a decision).
- intent-divergent: wrong intent. FORCE intent-divergent if ANY of:
  (a) Hallucination — the draft asserts a fact not present in the conversation/context.
  (b) Off-topic — the draft changes the subject away from the reconstructed intent.
  (c) Ignored ask — the draft does not address the counterparty's actual request.
  (d) Ungrounded — you cannot cite a real ground for your intent reading.

intent_grounded_fact is MANDATORY: cite the ground for your intent reading in the form `From [person] at [date]: [excerpt]`, drawn verbatim-enough from the supplied conversation/context. A fabricated citation will be rejected by a deterministic post-check.

Return ONLY JSON (keep the decision keys from before AND add):
{"intent_verdict":"intent-aligned|intent-partial|intent-divergent",
 "intent_rationale":"one line, <=140 chars",
 "intent_what_diverged":"<=120 chars, empty string if intent-aligned",
 "intent_grounded_fact":"From [person] at [date]: [excerpt] — mandatory"}"""

# Deterministic guard thresholds (design §3.2, §3.3b).
_GROUNDING_JACCARD_MIN = 0.6
_TOPIC_FLOOR_MIN = 0.15
_FORCED_GROUND = "FORCED: cited ground absent from cutoff context"
_FORCED_TOPIC = "FORCED: off-topic — draft vs reconstructed_intent below floor"
_INTENT_CREDIT = ("intent-aligned", "intent-partial")


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation to spaces, collapse whitespace. Pure,
    over in-memory strings only — no IO."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> set:
    return set(_normalize(s).split())


def _token_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard of two strings (0.0 when either is empty)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _topic_overlap(a: str, b: str) -> float:
    """Symmetric content-token Jaccard used for the §3.3b topic floor. Strips
    the citation scaffold, dates, and short filler tokens so framing words
    (Goal:/Core:/on/the) don't dilute the topic signal — a concise on-topic
    draft must not be punished against a verbose intent, while a disjoint-topic
    draft (mower→vacuum) still scores ~0."""
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# The mandated citation form is `From [person] at [date]: [excerpt]`. The
# `From/at` scaffold + dates are framing, not the cited ground — strip them so
# overlap is measured on the EXCERPT content, not the boilerplate. Short tokens
# (<=2 chars) are dropped as filler/stopwords on both sides.
_CITE_SCAFFOLD = re.compile(r"\bfrom\b|\bat\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\S*")


def _content_tokens(s: str) -> set:
    """Tokens carrying content: scaffold words + dates removed, short tokens
    (<=2 chars) dropped, then normalized to a token set."""
    s = _DATE_RE.sub(" ", s or "")
    s = _CITE_SCAFFOLD.sub(" ", s)
    return {t for t in _normalize(s).split() if len(t) > 2}


def _grounding_ok(intent_grounded_fact: str, ctx_text: str,
                  thread_text: str) -> bool:
    """DETERMINISTIC §3.2 check: the cited ground must actually exist in the
    supplied pre-cutoff material (thread_before + fenced full_cutoff_context),
    NEVER real_reply. True iff the normalized fact is a substring of the
    normalized haystack OR the fraction of the citation's content tokens found
    in the haystack is >= 0.6 (high overlap). The `From [person] at [date]:`
    scaffold + dates are stripped first so overlap is measured on the excerpt,
    not the boilerplate. An empty fact never passes (an empty citation is not a
    citation)."""
    fact = _normalize(intent_grounded_fact)
    if not fact:
        return False
    hay = _normalize((thread_text or "") + " " + (ctx_text or ""))
    if not hay:
        return False
    if fact in hay:
        return True
    # content-overlap fallback: fraction of the citation's EXCERPT content
    # tokens present in the haystack must clear the bar (asymmetric — the cited
    # ground is the small set; a fabricated ground shares few/no content words).
    ft = _content_tokens(intent_grounded_fact)
    ht = _content_tokens(hay)
    if not ft:
        return False
    return (len(ft & ht) / len(ft)) >= _GROUNDING_JACCARD_MIN


@dataclass
class CaseScore:
    case_id: str
    style_win: bool
    decision_verdict: str
    mechanics_flags: list[str]
    endorsement_adjusted: bool
    composite: float
    raw: dict[str, Any] = field(default_factory=dict)


def _fmt_thread(thread_before: list[dict]) -> str:
    """Compact oldest-first thread text for the intent payload (mirrors the
    retro judge's last-12 window). Never includes real_reply."""
    lines = []
    for m in thread_before[-12:]:
        who = "Nate" if m.get("direction") == "sent" else \
            (m.get("who") or "").split("<")[0].strip() or m.get("person", "")
        body = (m.get("text") or "").strip()
        lines.append(f"[{(m.get('date') or '')[:16]}] {who}: {body[:1200]}")
    return "\n".join(lines)


def _render_context(full_cutoff_context: Any) -> str:
    """Flatten the already-fenced gathered context dict to text for the judge
    payload + the deterministic grounding haystack. Reads only the admitted
    structured sources; never carries real_reply (it is not in the dict)."""
    if not full_cutoff_context:
        return ""
    if isinstance(full_cutoff_context, str):
        return full_cutoff_context
    parts: list[str] = []

    def _walk(v: Any) -> None:
        if isinstance(v, dict):
            for vv in v.values():
                _walk(vv)
        elif isinstance(v, (list, tuple)):
            for vv in v:
                _walk(vv)
        elif isinstance(v, str):
            parts.append(v)
        elif v is not None:
            parts.append(str(v))

    _walk(full_cutoff_context)
    return "\n".join(parts)


def judge_with_oauth(case_dict: dict, clone_draft: str,
                     reconstructed_intent: str = "",
                     full_cutoff_context: Any = None) -> dict:
    """Run the decision judge first (retrodiction's tone-blind rubric via OAuth
    `claude -p`, JUDGE_SYSTEM kept pristine), then — when an intent is supplied
    — append INTENT_RUBRIC at call-time and run a SECOND intent pass over
    `thread_before[-12:]` + `reconstructed_intent` + the fenced
    `full_cutoff_context` ONLY (NEVER real_reply).

    Returns ONE dual-verdict dict, decision-first. The DETERMINISTIC
    anti-rubber-stamp guard (§3.2 grounding + §3.3b topic-overlap floor) runs
    BEFORE crediting any intent-aligned/intent-partial verdict on a divergent
    decision; on failure it FORCES intent_verdict='intent-divergent' and stamps
    intent_grounded_fact. The guard reads only the fenced cutoff material —
    never real_reply — so it adds no leak. Both LLM passes go through
    oauth_json_llm, which strips ANTHROPIC_API_KEY from the child env."""
    # 1. Decision verdict — reused verbatim, decision-first.
    decision = retro.judge_decision(case_dict, clone_draft, llm=oauth_json_llm)

    # Backward-compatible: no intent supplied → decision-only (F1/T-prior shape).
    if not reconstructed_intent:
        return decision

    # 2. Intent pass — extended system (pristine JUDGE_SYSTEM + divider +
    #    INTENT_RUBRIC) and an extended payload with the two new sections. The
    #    payload reads the thread + intent + fenced context; NEVER real_reply.
    thread_text = _fmt_thread(case_dict.get("thread_before", []))
    ctx_text = _render_context(full_cutoff_context)
    intent_system = retro.JUDGE_SYSTEM + _INTENT_DIVIDER + INTENT_RUBRIC
    intent_payload = (
        f"# CONVERSATION (everything before Nate's reply)\n{thread_text}\n\n"
        f"# MODEL DRAFT\n{(clone_draft or '')[:2500]}\n\n"
        f"# RECONSTRUCTED INTENT (before reply)\n"
        f"{reconstructed_intent[:2000]}\n\n"
        f"# FULL CUTOFF-SAFE CONTEXT\n{ctx_text[:4000] or '(none)'}"
    )
    res = oauth_json_llm(intent_payload, intent_system, max_tokens=400)

    out = dict(decision)
    valid = ("intent-aligned", "intent-partial", "intent-divergent")
    if not res or res.get("intent_verdict") not in valid:
        out.update({
            "intent_verdict": "error",
            "intent_rationale": "intent judge unavailable/unparseable",
            "intent_what_diverged": "",
            "intent_grounded_fact": "",
        })
        return out

    intent_verdict = res["intent_verdict"]
    grounded_fact = res.get("intent_grounded_fact", "") or ""

    # 3. DETERMINISTIC anti-rubber-stamp guard — only when the LLM credits
    #    intent on a DIVERGENT decision (the F4 credit path is the only place a
    #    hollow/hallucinated alignment can sneak credit). Runs over the fenced
    #    cutoff material ONLY.
    if (decision.get("verdict") == "divergent"
            and intent_verdict in _INTENT_CREDIT):
        # §3.3b topic-overlap floor first (cheap, decisive).
        if _topic_overlap(clone_draft, reconstructed_intent) < _TOPIC_FLOOR_MIN:
            intent_verdict = "intent-divergent"
            grounded_fact = _FORCED_TOPIC
        # §3.2 grounding check on the cited ground.
        elif not _grounding_ok(grounded_fact, ctx_text, thread_text):
            intent_verdict = "intent-divergent"
            grounded_fact = _FORCED_GROUND

    out.update({
        "intent_verdict": intent_verdict,
        "intent_rationale": res.get("intent_rationale", ""),
        "intent_what_diverged": res.get("intent_what_diverged", ""),
        "intent_grounded_fact": grounded_fact,
    })
    return out


def score(case: Case, officer_decision: OfficerDecision, baseline_draft: str,
          centroids: dict, embedder=None, judge=None) -> CaseScore:
    """Score one officer decision vs ground truth across the three channels."""
    judge = judge or judge_with_oauth
    clone_draft = officer_decision.decision if isinstance(
        officer_decision.decision, str) else str(officer_decision.decision)
    rc = case.to_retro_case()

    # DECISION via OAuth judge; inject as judge_result so score_case does no
    # ANTHROPIC_API_KEY call.
    verdict = judge(rc, clone_draft)
    row = retro.score_case(rc, clone_draft, baseline_draft, centroids,
                           judge=False, embedder=embedder, judge_result=verdict)

    decision_verdict = row["judge"]["verdict"]
    # F1: endorsement 'unknown' -> score vs actual, no adjustment.
    endorsement_adjusted = case.endorsement in ("regretted", "constrained")
    return CaseScore(
        case_id=case.case_id,
        style_win=bool(row["style_win"]),
        decision_verdict=decision_verdict,
        mechanics_flags=row["mechanics"],
        endorsement_adjusted=endorsement_adjusted,
        composite=_COMPOSITE.get(decision_verdict, 0.0),
        raw=row,
    )
