"""Endorsement-aware scorer (docs/fidelity-harness-design-2026-06-18.md §127-141).

Wraps retrodiction's three-channel score_case: STYLE (Voyage cosine vs the
recency-weighted voice centroid - text decisions only), DECISION-MATCH (the
tone-blind judge, run here via OAuth `claude -p` keeping JUDGE_SYSTEM intact),
MECHANICS (deterministic flags). F1 covers the reply cell with endorsement
'unknown' => scored vs the actual reply; F4 wires the endorsed-direction
adjustment. The privacy fence holds: nate_model/voice inform the centroid +
clone draft but are never emitted into a score row."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from framework.env import captain_name
from framework.fidelity import retro
from framework.fidelity.oauth_llm import oauth_json_llm
from framework.fidelity.types import Case, OfficerDecision

# Captain display name, resolved once per process (env.py caches). Renders
# BYTE-IDENTICAL to the prior hardcoded captain name here. INTENT_RUBRIC must stay a
# module constant (test_f4_judge pins its identity via `in`), so the name is
# baked into the f-string at import rather than a call-time .format() placeholder.
_CAP = captain_name()

_COMPOSITE = {"match": 1.0, "partial": 0.5, "divergent": 0.0, "error": 0.0,
              "skipped": 0.0}
# Design §3.4 names the decision table `_DEC`; it is the same table (the
# decision verdict -> baseline score). Alias so both the design's name and the
# original F1 name resolve to one source of truth.
_DEC = _COMPOSITE

# Design §3.4 — the intent axis score table. `intent-divergent` and `error`
# both map to 0.0, but they are handled by SEPARATE branches in composite():
# `intent-divergent` ZEROS the row (hollow/off-intent), while `error`/"" falls
# back to the decision-only score (== F1).
_INTENT = {"intent-aligned": 1.0, "intent-partial": 0.5,
           "intent-divergent": 0.0, "error": 0.0}


def composite(dec_verdict: str, intent_verdict: str) -> float:
    """Decision-dominant, intent-penalizing blend (design §3.4).

    - intent layer unavailable (``error`` or ``""``) -> decision-only score,
      which reproduces F1 exactly.
    - ``intent-divergent`` -> 0.0: a hollow surface-match or an off-intent
      action is gated to zero regardless of the decision verdict. This is the
      branch that makes the §3.2/§3.3b deterministic guards load-bearing.
    - otherwise the intent serves the mission: credit the BETTER of the
      literal-match score and the intent score, so on-intent divergence
      (``divergent × intent-aligned``) earns 1.0 (the F4 credit path).
    """
    dec = _DEC.get(dec_verdict, 0.0)
    if intent_verdict in ("error", ""):     # intent layer unavailable
        return dec                          # decision-only fallback (== F1)
    if intent_verdict == "intent-divergent":
        return 0.0                          # hollow surface-match / off-intent
    return max(dec, _INTENT[intent_verdict])

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

INTENT_RUBRIC = f"""Now ALSO judge INTENT-ALIGNMENT, a SEPARATE axis from the decision verdict above.

The officer must serve {_CAP}'s as-of-cutoff intent — `mission/goal × core` (what {_CAP} is pursuing here, blended through who {_CAP} is). A draft that diverges from the literal reply but serves the SAME intent equally well or better earns credit; a draft that hits the surface but misses the intent, or that hallucinates / goes off-topic, is gated to zero.

You are given two extra sections below the conversation: `# RECONSTRUCTED INTENT (before reply)` and `# FULL CUTOFF-SAFE CONTEXT`. Judge `mission × core` alignment of the MODEL DRAFT against the reconstructed intent, grounded ONLY in the conversation + the cutoff-safe context. You do NOT see {_CAP}'s real reply — do not assume one.

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
{{"intent_verdict":"intent-aligned|intent-partial|intent-divergent",
 "intent_rationale":"one line, <=140 chars",
 "intent_what_diverged":"<=120 chars, empty string if intent-aligned",
 "intent_grounded_fact":"From [person] at [date]: [excerpt] — mandatory"}}"""

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


# ---------------------------------------------------------------------------
# D17 (sovereign spec §2, INT-1) — OUTCOME RUBRIC, the THIRD judge pass. The
# personal-agent reframe: the headline question is no longer "did the clone
# match the Captain's reply?" but "did it serve the Captain's intent AS GOOD OR BETTER than
# what the Captain actually sent?" (AGB). The judge sees TWO ANONYMIZED candidates —
# clone_draft and the held-out real_reply, labeled A/B by sha256(case_id)
# parity so the assignment is deterministic per case and balanced across the
# corpus — and judges ONLY against the reconstructed intent + the fenced
# cutoff context. It is never told which candidate is real. This pass is
# judge-side only (the officer has already drafted; real_reply reaches the
# judge exactly as it always has via retro.judge_decision), so it adds no leak
# surface. STANDALONE system prompt: retro.JUDGE_SYSTEM stays PRISTINE and is
# not part of this pass (it names MODEL DRAFT / REAL REPLY, which would
# de-anonymize the candidates).
# ---------------------------------------------------------------------------
OUTCOME_RUBRIC = """You are judging OUTCOMES for a held-out reply situation.

Below are a CONVERSATION (ending just before a reply was sent), a `# RECONSTRUCTED INTENT (before reply)` — mission/goal × core, what the replier is pursuing here — a `# FULL CUTOFF-SAFE CONTEXT`, and TWO anonymized candidate replies: CANDIDATE A and CANDIDATE B. One may be human-written and one machine-written, in shuffled order — you are NOT told which, and it must not matter.

Judge ONLY which candidate better serves the reconstructed intent (mission × core), grounded in the conversation + context. IGNORE style, tone, length, and formatting except where they change the outcome. A candidate that hallucinates facts absent from the conversation/context, goes off-topic, or ignores the counterparty's actual ask serves the intent WORSE.

outcome_winner values:
- A: CANDIDATE A serves the intent materially better.
- B: CANDIDATE B serves the intent materially better.
- tie: both serve the intent about equally well (or equally poorly).

outcome_grounded_fact is MANDATORY: cite the ground for your judgment in the form `From [person] at [date]: [excerpt]`, drawn verbatim-enough from the supplied conversation/context — never from the candidates. A fabricated citation will be rejected by a deterministic post-check.

Return ONLY JSON:
{"outcome_winner":"A|B|tie",
 "outcome_rationale":"one line, <=140 chars",
 "outcome_grounded_fact":"From [person] at [date]: [excerpt] — mandatory"}"""

# Deterministic forced-outcome stamps (mirror _FORCED_GROUND/_FORCED_TOPIC).
# forced-worse: an off-intent clone draft can never be as-good-or-better;
# forced-incomparable: an AGB credit resting on a fabricated citation is not
# revoked into a clone LOSS (that would fabricate a verdict too) — it is
# demoted to "we could not verify the comparison".
_FORCED_OUTCOME_TOPIC = ("FORCED: off-topic — clone draft vs "
                         "reconstructed_intent below floor")
_FORCED_OUTCOME_GROUND = "FORCED: cited ground absent from cutoff context"
# The clone-crediting verdict the deterministic guards police.
_AGB = "as_good_or_better"


def outcome_ab_clone_is_a(case_id: str) -> bool:
    """D17 anonymized A/B assignment: True ⇒ clone_draft is CANDIDATE A (the
    real reply is B); False ⇒ swapped. sha256(case_id) first-byte parity —
    deterministic for a fixed case (re-runs and shards agree) and ~50/50
    balanced across a corpus, so the judge can never learn a fixed slot."""
    digest = hashlib.sha256((case_id or "").encode("utf-8")).digest()
    return digest[0] % 2 == 0


def _outcome_judge(case_dict: dict, clone_draft: str,
                   reconstructed_intent: str, thread_text: str,
                   ctx_text: str) -> dict:
    """Run the D17 pass-3 OUTCOME A/B judge; return the three outcome keys.

    Candidates are the clone draft and the held-out ``real_reply`` (the ONLY
    place this pass reads it — judge-side, post-draft), anonymized per
    ``outcome_ab_clone_is_a``. Verdict vocabulary: ``as_good_or_better``
    (clone won or tied — the AGB headline), ``worse`` (real reply won),
    ``incomparable`` (comparison could not be verified), ``error`` (judge
    unavailable/unparseable), ``""`` (no real reply ⇒ pass did not run).

    DETERMINISTIC guards run only when the LLM credits the clone (the
    anti-rubber-stamp direction), reusing §3.2/§3.3b verbatim:
      - ``_topic_overlap(clone_draft, reconstructed_intent)`` below the floor
        FORCES ``worse`` (an off-intent draft is never as-good-or-better);
      - ``_grounding_ok`` failure on the cited ground FORCES ``incomparable``
        (the credit is unverifiable, not disproven).
    The grounding haystack is thread + fenced ctx only — never real_reply."""
    real_reply = (case_dict.get("real_reply") or "").strip()
    if not real_reply:
        return {"outcome_verdict": "", "outcome_rationale": "",
                "outcome_grounded_fact": ""}

    clone_is_a = outcome_ab_clone_is_a(case_dict.get("case_id", ""))
    clone_text = (clone_draft or "")[:2500]
    real_text = real_reply[:2500]
    cand_a, cand_b = ((clone_text, real_text) if clone_is_a
                      else (real_text, clone_text))
    payload = (
        f"# CONVERSATION (everything before the reply)\n{thread_text}\n\n"
        f"# RECONSTRUCTED INTENT (before reply)\n"
        f"{reconstructed_intent[:2000]}\n\n"
        f"# FULL CUTOFF-SAFE CONTEXT\n{ctx_text[:4000] or '(none)'}\n\n"
        f"# CANDIDATE A\n{cand_a}\n\n"
        f"# CANDIDATE B\n{cand_b}"
    )
    res = oauth_json_llm(payload, OUTCOME_RUBRIC, max_tokens=400)

    winner = (res or {}).get("outcome_winner")
    if winner not in ("A", "B", "tie"):
        return {"outcome_verdict": "error",
                "outcome_rationale": "outcome judge unavailable/unparseable",
                "outcome_grounded_fact": ""}

    clone_label = "A" if clone_is_a else "B"
    verdict = _AGB if winner in (clone_label, "tie") else "worse"
    grounded_fact = res.get("outcome_grounded_fact", "") or ""

    # Anti-rubber-stamp guards — only an AGB credit needs policing ("worse" is
    # already the conservative direction). §3.3b topic floor first (cheap,
    # decisive), then the §3.2 grounding check, both reused verbatim.
    if verdict == _AGB:
        if _topic_overlap(clone_draft, reconstructed_intent) < _TOPIC_FLOOR_MIN:
            verdict = "worse"
            grounded_fact = _FORCED_OUTCOME_TOPIC
        elif not _grounding_ok(grounded_fact, ctx_text, thread_text):
            verdict = "incomparable"
            grounded_fact = _FORCED_OUTCOME_GROUND

    return {"outcome_verdict": verdict,
            "outcome_rationale": res.get("outcome_rationale", ""),
            "outcome_grounded_fact": grounded_fact}


@dataclass
class CaseScore:
    case_id: str
    style_win: bool
    decision_verdict: str
    mechanics_flags: list[str]
    endorsement_adjusted: bool
    composite: float
    raw: dict[str, Any] = field(default_factory=dict)
    # F4 §1.5 — the intent axis on the score row. Empty/0.0 by default so the
    # decision-only (F1) path is unchanged; populated when intent_ctx is scored.
    intent_verdict: str = ""
    intent_grounded_fact: str = ""
    intent_composite: float = 0.0
    # D17 — the outcome axis (AGB headline). "" = pass did not run (no intent
    # supplied / no held-out real reply), keeping the F1 row shape inert.
    outcome_verdict: str = ""
    outcome_grounded_fact: str = ""


def _fmt_thread(thread_before: list[dict]) -> str:
    """Compact oldest-first thread text for the intent payload (mirrors the
    retro judge's last-12 window). Never includes real_reply."""
    lines = []
    for m in thread_before[-12:]:
        who = _CAP if m.get("direction") == "sent" else \
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

    When the intent layer runs, a THIRD pass (D17 OUTCOME_RUBRIC) compares the
    clone draft against the held-out real reply as ANONYMIZED candidates A/B
    (sha256(case_id) parity), judged only against the reconstructed intent —
    the AGB (as-good-or-better) axis. Judge-side only; the officer never sees
    real_reply.

    Returns ONE multi-verdict dict, decision-first. The DETERMINISTIC
    anti-rubber-stamp guard (§3.2 grounding + §3.3b topic-overlap floor) runs
    BEFORE crediting any intent-aligned/intent-partial verdict on a divergent
    decision; on failure it FORCES intent_verdict='intent-divergent' and stamps
    intent_grounded_fact. The same guards police an AGB outcome credit
    (_outcome_judge). The guards read only the fenced cutoff material — never
    real_reply — so they add no leak. All LLM passes go through
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
        f"# CONVERSATION (everything before {_CAP}'s reply)\n{thread_text}\n\n"
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
    else:
        intent_verdict = res["intent_verdict"]
        grounded_fact = res.get("intent_grounded_fact", "") or ""

        # 3. DETERMINISTIC anti-rubber-stamp guard — only when the LLM credits
        #    intent on a DIVERGENT decision (the F4 credit path is the only
        #    place a hollow/hallucinated alignment can sneak credit). Runs over
        #    the fenced cutoff material ONLY.
        if (decision.get("verdict") == "divergent"
                and intent_verdict in _INTENT_CREDIT):
            # §3.3b topic-overlap floor first (cheap, decisive).
            if _topic_overlap(clone_draft,
                              reconstructed_intent) < _TOPIC_FLOOR_MIN:
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

    # 4. D17 pass 3 — OUTCOME A/B vs the held-out real reply (AGB headline).
    #    Runs whenever the intent layer ran (even if it errored — the outcome
    #    question is independent of the intent VERDICT; it only needs the
    #    reconstructed intent text). "" outcome keys when no real reply exists.
    out.update(_outcome_judge(case_dict, clone_draft, reconstructed_intent,
                              thread_text, ctx_text))
    return out


def score(case: Case, officer_decision: OfficerDecision, baseline_draft: str,
          centroids: dict, embedder=None, judge=None,
          intent_ctx: dict | None = None) -> CaseScore:
    """Score one officer decision vs ground truth across the three channels.

    When ``intent_ctx`` is supplied (the F4 path), the reconstructed intent +
    the already-fenced ``full_cutoff_context`` are threaded to the judge for the
    intent pass, and the §3.4 ``composite`` blend is applied ON TOP of the
    decision verdict. The intent dict shape is
    ``{"reconstructed_intent": str, "full_cutoff_context": <fenced dict>}``;
    ``reconstructed_intent`` falls back to ``case.intent`` (cached benchmark
    intent) when omitted. NEVER reads ``real_reply`` — the judge's intent pass
    and its deterministic guards see only the thread + the fenced context.

    On the intent path the judge also runs the D17 OUTCOME pass (anonymized
    clone-vs-real A/B against the reconstructed intent) and the row carries
    ``outcome_verdict`` — the AGB axis intent_report headlines.

    With no ``intent_ctx`` the decision verdict alone drives the composite
    (== F1; ``composite(dec, "")`` returns ``_DEC[dec]``), so the F1 path is
    byte-for-byte unchanged."""
    judge = judge or judge_with_oauth
    clone_draft = officer_decision.decision if isinstance(
        officer_decision.decision, str) else str(officer_decision.decision)
    rc = case.to_retro_case()

    # DECISION via OAuth judge; inject as judge_result so score_case does no
    # ANTHROPIC_API_KEY call. The intent pass rides on the same judge call when
    # intent_ctx is supplied — decision verdict stays first and visible.
    if intent_ctx is not None:
        reconstructed_intent = (intent_ctx.get("reconstructed_intent")
                                or case.intent or "")
        full_cutoff_context = intent_ctx.get("full_cutoff_context")
        verdict = judge(rc, clone_draft,
                        reconstructed_intent=reconstructed_intent,
                        full_cutoff_context=full_cutoff_context)
    else:
        verdict = judge(rc, clone_draft)
    row = retro.score_case(rc, clone_draft, baseline_draft, centroids,
                           judge=False, embedder=embedder, judge_result=verdict)

    decision_verdict = row["judge"]["verdict"]
    # Intent axis: empty when no intent layer ran (== "" -> decision-only blend).
    intent_verdict = verdict.get("intent_verdict", "") if isinstance(
        verdict, dict) else ""
    intent_grounded_fact = verdict.get("intent_grounded_fact", "") if isinstance(
        verdict, dict) else ""
    # D17 outcome axis (AGB): empty when the pass did not run.
    outcome_verdict = verdict.get("outcome_verdict", "") if isinstance(
        verdict, dict) else ""
    outcome_grounded_fact = verdict.get("outcome_grounded_fact", "") if isinstance(
        verdict, dict) else ""
    # F1: endorsement 'unknown' -> score vs actual, no adjustment.
    endorsement_adjusted = case.endorsement in ("regretted", "constrained")
    return CaseScore(
        case_id=case.case_id,
        style_win=bool(row["style_win"]),
        decision_verdict=decision_verdict,
        mechanics_flags=row["mechanics"],
        endorsement_adjusted=endorsement_adjusted,
        composite=_DEC.get(decision_verdict, 0.0),
        raw=row,
        intent_verdict=intent_verdict,
        intent_grounded_fact=intent_grounded_fact,
        intent_composite=composite(decision_verdict, intent_verdict),
        outcome_verdict=outcome_verdict,
        outcome_grounded_fact=outcome_grounded_fact,
    )
