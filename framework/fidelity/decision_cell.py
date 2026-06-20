"""Decision cell (F3-intent) — measure intent-fidelity on real Head-of-Tech
DECISIONS, not replies (docs/fidelity-decision-cell-design-2026-06-20.md).

The reply cell measures VOICE; "replace Nate" is judgment calls with a WHY.
This cell drives the clone on a held-out DILEMMA (Nate's choice removed) and
judges its proposed decision + rationale against Nate's actual decision + WHY.

Three pieces, all reusing the reply-cell machinery (oauth LLMs, the clone
privacy fence + identity, the verdict vocab + composite()):
  1. extract_decision_cases — parse 5-Reflections/Decisions notes, LLM-split
     each into {dilemma, decision, why}, leak-scan the dilemma (it must NOT
     reveal Nate's choice), cache. A bleeding dilemma is DROPPED, never scored.
  2. run_decision_case — clone proposes {decision, why} from the dilemma +
     values-identity (voice + nate_model patterns + lessons date-filtered
     strictly before detected_at). Privacy-fenced; never sees the ground truth.
  3. score_decision_case — the judge compares clone vs Nate's actual
     {decision, why}: decision_match (same call?) + intent_match (same WHY?).

LEAK MODEL: the clone never receives decision/why (only the dilemma + identity).
The dilemma carries the situational facts but not the choice — the EXTRACTOR is
the leak surface, so its output is leak-scanned before a case is admitted.
detected_at is the cutoff for the date-filtered lessons. NO sends, NO board
writes, NO vault writes — eval only.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from framework.fidelity.oauth_llm import oauth_json_llm, oauth_raw_llm
from framework.fidelity.officer_prompt import _CLONE_PRIVACY_FENCE
from framework.fidelity.officer_runner import BrainAdapter
from framework.fidelity.scorer import composite
from framework.fidelity.types import DecisionCase

_DECISIONS_REL = "5-Reflections/Decisions"


def _vault_dir() -> Path:
    """The Decisions corpus dir, realpath-jailed to the vault (Corridor path-
    traversal mitigation). OBSIDIAN_VAULT_PATH (pinned by the embeddings plist)
    else the TRUE on-disk lowercase casing."""
    vault = (os.environ.get("OBSIDIAN_VAULT_PATH")
             or str(Path.home() / "obsidian" / "screenpipe-brain"))
    vreal = os.path.realpath(vault)
    resolved = os.path.realpath(os.path.join(vreal, _DECISIONS_REL))
    if resolved != vreal and not resolved.startswith(vreal + os.sep):
        raise PermissionError("Decisions dir escaped the vault jail")
    return Path(resolved)


def _cache_path() -> Path:
    """Extraction cache (personal data — kept OUT of the repo). CABINET_DECISION
    _CACHE env else ~/.screenpipe/state/, alongside autonomy_outcomes.jsonl."""
    p = os.environ.get("CABINET_DECISION_CACHE")
    if p:
        return Path(p).expanduser()
    return Path.home() / ".screenpipe" / "state" / "cabinet_decision_cases.json"


# --- note parsing ----------------------------------------------------------
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SIT_RE = re.compile(
    r"^##+\s*Situation.*?\n(.*?)(?=^##+\s|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)
_WHY_RE = re.compile(
    r"^##+\s*Why.*?\n(.*?)(?=^##+\s|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)


def _parse_note(text: str) -> dict:
    """Pull frontmatter (detected_at/date, app, candidate_id) + the Situation
    and Why sections from a decision note. Pure string parse, no IO."""
    fm = {}
    m = _FM_RE.match(text or "")
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("-"):
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip()
    sit = _SIT_RE.search(text or "")
    why = _WHY_RE.search(text or "")
    return {
        "detected_at": fm.get("detected_at") or fm.get("date") or "",
        "app": fm.get("app", ""),
        "candidate_id": fm.get("candidate_id", ""),
        "situation": (sit.group(1).strip() if sit else ""),
        "why": (why.group(1).strip() if why else ""),
    }


# --- leak-scan: the dilemma must not reveal Nate's choice -------------------
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
         "you", "your", "nate", "that", "this", "it", "is", "was", "had", "has",
         "he", "his", "she", "her", "they", "them", "at", "by", "as", "be"}


def _content_tokens(s: str) -> set:
    toks = re.findall(r"\b\w+\b", (s or "").lower())
    return {t for t in toks if len(t) > 3 and t not in _STOP}


def _dilemma_leaks(dilemma: str, decision: str, why: str) -> bool:
    """True iff the dilemma reveals Nate's choice — a backstop for the
    extractor prompt (the primary guard), catching EGREGIOUS copy-paste of the
    decision into the dilemma.

    Heuristic: the fraction of the DECISION's distinctive content tokens that
    surface in the dilemma. A neutral question legitimately SHARES the action
    verb ("should Nate proceed?" vs decision "proceed") without revealing the
    choice, so a short decision (<3 distinctive tokens) is NOT flagged on a
    shared verb alone — the prompt handles those, and over-dropping wastes the
    thin corpus. A decision with >=3 distinctive tokens whose bulk (>=70%) has
    bled into the dilemma means the choice was restated → drop (never silently
    scored, mirrors the reply cell). An empty/unrecoverable decision drops."""
    dec_tok = _content_tokens(decision)
    if not dec_tok:
        return True  # no recoverable decision -> unusable, drop
    if len(dec_tok) < 3:
        return False  # too few distinctive tokens to distinguish leak from a
        #               shared action verb in a neutral question — trust prompt
    dil_tok = _content_tokens(dilemma)
    overlap = len(dec_tok & dil_tok) / len(dec_tok)
    return overlap >= 0.7


_EXTRACT_SYSTEM = """You split a logged DECISION note into three parts for a held-out evaluation.

The note records a decision Nate already made, fusing the situation with his choice. Split it so an evaluator can pose the decision point to a model WITHOUT revealing what Nate chose.

Return ONLY JSON:
{"dilemma":"the decision point Nate faced — the situation + the question/options, with ALL situational facts needed to decide, but WITHOUT stating or implying which option Nate picked. Neutral framing. <=600 chars.",
 "decision":"what Nate actually chose/did — the concrete call. <=200 chars.",
 "why":"Nate's rationale / the intent behind the choice. <=300 chars."}

CRITICAL: the dilemma must NOT contain Nate's choice, the chosen action's verb, or wording that gives it away. Someone reading only the dilemma should not be able to tell what Nate decided. Keep every situational fact that is needed to decide well."""


def _extract_one(parsed: dict, llm) -> dict | None:
    """LLM-split one parsed note into {dilemma, decision, why}; None if the LLM
    output is unusable. Leak-scan is applied by the caller."""
    payload = (f"# SITUATION (as logged, fuses situation + choice)\n"
               f"{parsed['situation']}\n\n# WHY (Nate)\n{parsed['why']}")
    raw = llm(payload, _EXTRACT_SYSTEM) or ""
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        obj = json.loads(m.group(0) if m else raw)
    except (ValueError, AttributeError):
        return None
    dilemma = (obj.get("dilemma") or "").strip()
    decision = (obj.get("decision") or "").strip()
    why = (obj.get("why") or "").strip()
    if not dilemma or not decision:
        return None
    return {"dilemma": dilemma, "decision": decision, "why": why}


def extract_decision_cases(decisions_dir: Path | None = None, llm=oauth_raw_llm,
                           cache_path: Path | None = None,
                           use_cache: bool = True) -> list[DecisionCase]:
    """Build held-out DecisionCases from the Decisions corpus. Each note is
    LLM-split into {dilemma, decision, why}; a dilemma that reveals the choice
    (leak-scan) is DROPPED. Results are cached (personal data, outside the repo)
    keyed by note path so re-runs do not re-call the LLM."""
    ddir = decisions_dir or _vault_dir()
    cpath = cache_path or _cache_path()
    cache = {}
    if use_cache and cpath.exists():
        try:
            cache = json.loads(cpath.read_text(errors="replace"))
        except ValueError:
            cache = {}

    cases: list[DecisionCase] = []
    dirty = False
    for f in sorted(ddir.glob("*.md")) if ddir.exists() else []:
        key = f.name
        if use_cache and key in cache:
            rec = cache[key]
            if rec:  # a cached miss (None) is respected — don't re-LLM each run
                cases.append(DecisionCase(**rec))
            continue
        parsed = _parse_note(f.read_text(errors="replace"))
        if not parsed["situation"]:
            cache[key] = None
            dirty = True
            continue
        split = _extract_one(parsed, llm)
        rec = None
        if split and not _dilemma_leaks(split["dilemma"], split["decision"],
                                        split["why"]):
            rec = asdict(DecisionCase(
                case_id=parsed["candidate_id"] or f.stem[:40],
                detected_at=parsed["detected_at"],
                app=parsed["app"],
                dilemma=split["dilemma"],
                decision=split["decision"],
                why=split["why"],
            ))
            cases.append(DecisionCase(**rec))
        cache[key] = rec
        dirty = True

    if use_cache and dirty:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return cases


# --- runner: clone proposes {decision, why} from the dilemma + identity -----
_DECISION_CLONE_SYSTEM = """You are Nate's clone, facing a real Head-of-Tech decision. Make the call Nate would make and give his reasoning. Decide as Nate decides — his values, risk posture, and priorities drive the call.

{fence}

## How Nate decides (nate_model patterns)
{patterns}

## How Nate writes/reasons (voice profile)
{voice}

## Past decision lessons (date-filtered before this moment)
{lessons}

Return ONLY JSON: {{"decision":"the concrete call you make","why":"your reasoning, in Nate's frame"}}"""


def _clone_identity(case: DecisionCase, brain: BrainAdapter) -> dict:
    """Values-identity for the decision clone: voice + nate_model patterns +
    drafting lessons date-filtered STRICTLY before detected_at. No person_static
    (a decision has no single counterparty). Mirrors the reply cell's identity
    gather + privacy fence."""
    def _v(x):
        return (x or "").strip() or "(unavailable)"
    return {
        "voice": _v(brain.voice_profile()),
        "patterns": _v(brain.nate_model_patterns()),
        "lessons": _v(brain.drafting_lessons(case.detected_at)),
    }


def run_decision_case(case: DecisionCase, llm=oauth_raw_llm,
                      brain: BrainAdapter | None = None) -> dict:
    """Drive the clone on the dilemma; return its proposed {decision, why}. The
    clone sees the dilemma + values-identity ONLY — NEVER case.decision/why.
    Identity informs HOW it decides and is privacy-fenced (never echoed)."""
    brain = brain or BrainAdapter()
    ident = _clone_identity(case, brain)
    system = _DECISION_CLONE_SYSTEM.format(
        fence=_CLONE_PRIVACY_FENCE, patterns=ident["patterns"],
        voice=ident["voice"], lessons=ident["lessons"])
    user = (f"# DECISION POINT (decide as-of {case.detected_at})\n"
            f"{case.dilemma}\n\nMake the call and give your reasoning.")
    raw = llm(user, system) or ""
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        obj = json.loads(m.group(0) if m else raw)
        return {"decision": (obj.get("decision") or "").strip(),
                "why": (obj.get("why") or "").strip()}
    except (ValueError, AttributeError):
        # Non-JSON fallback: treat the whole text as the decision (still scored).
        return {"decision": raw.strip()[:400], "why": ""}


# --- scorer: judge clone vs Nate's actual {decision, why} -------------------
_DECISION_JUDGE_SYSTEM = """You grade whether a MODEL's decision matches NATE's actual decision on the same dilemma — on two SEPARATE axes.

You are given the DILEMMA, NATE's actual decision + why (ground truth), and the MODEL's decision + why. Judge tone-blind; judge the substance of the call and its reasoning.

decision_verdict (did the MODEL make the same CALL?):
- match: same concrete choice/action.
- partial: overlapping but materially different (right direction, wrong scope/condition).
- divergent: a different call.

intent_verdict (does the MODEL's reasoning serve the SAME intent/WHY as Nate's?):
- intent-aligned: same underlying goal + values drove it, even if the surface call differs.
- intent-partial: serves part of the WHY but misses a material element.
- intent-divergent: wrong intent — different values/goal, or ungrounded/hallucinated reasoning.

Return ONLY JSON:
{"decision_verdict":"match|partial|divergent",
 "intent_verdict":"intent-aligned|intent-partial|intent-divergent",
 "rationale":"<=140 chars"}"""


def score_decision_case(case: DecisionCase, clone_out: dict,
                        judge=oauth_json_llm) -> dict:
    """Judge the clone's {decision, why} against Nate's actual ground truth.
    Returns {decision_verdict, intent_verdict, composite, rationale}. The judge
    is SUPPOSED to see the ground truth (it grades against it); the leak boundary
    is on the clone (run_decision_case), which never saw it."""
    payload = (
        f"# DILEMMA\n{case.dilemma}\n\n"
        f"# NATE'S ACTUAL DECISION\n{case.decision}\n"
        f"# NATE'S WHY\n{case.why}\n\n"
        f"# MODEL DECISION\n{(clone_out.get('decision') or '')[:600]}\n"
        f"# MODEL WHY\n{(clone_out.get('why') or '')[:600]}")
    res = judge(payload, _DECISION_JUDGE_SYSTEM, max_tokens=300) or {}
    dv = res.get("decision_verdict", "")
    iv = res.get("intent_verdict", "")
    valid_d = {"match", "partial", "divergent"}
    valid_i = {"intent-aligned", "intent-partial", "intent-divergent"}
    if dv not in valid_d:
        dv = ""
    if iv not in valid_i:
        iv = ""
    return {
        "case_id": case.case_id,
        "decision_verdict": dv,
        "intent_verdict": iv,
        "composite": composite(dv, iv),
        "rationale": res.get("rationale", ""),
    }
