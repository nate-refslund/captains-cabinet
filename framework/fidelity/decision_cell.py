"""Decision cell (F3-intent) — measure intent-fidelity on real Captain
DECISIONS, not replies (docs/fidelity-decision-cell-design-2026-06-20.md).

The reply cell measures VOICE; "replace the Captain" is judgment calls with a WHY.
This cell drives the clone on a held-out DILEMMA (the Captain's choice removed) and
judges its proposed decision + rationale against the Captain's actual decision + WHY.

Three pieces, all reusing the reply-cell machinery (oauth LLMs, the clone
privacy fence + identity, the verdict vocab + composite()):
  1. extract_decision_cases — parse 5-Reflections/Decisions notes, LLM-split
     each into {dilemma, decision, why}, leak-scan the dilemma (it must NOT
     reveal the Captain's choice), cache. A bleeding dilemma is DROPPED, never scored.
  2. run_decision_case — clone proposes {decision, why} from the dilemma +
     values-identity (voice + nate_model patterns + lessons date-filtered
     strictly before detected_at). Privacy-fenced; never sees the ground truth.
  3. score_decision_case — the judge compares clone vs the Captain's actual
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
from framework.env import captain_name, captain_role, state_dir, vault_dir
from framework.fidelity.officer_prompt import _clone_privacy_fence
from framework.sources import get_source
from framework.fidelity.scorer import composite
from framework.fidelity.types import DecisionCase

# Captain display name, resolved once per process (env.py caches; a restart
# re-reads). Renders BYTE-IDENTICAL to the prior hardcoded captain name on this
# deployment. Baked into the raw LLM-prompt constants below and used at the
# call sites that address the Captain in a payload/label.
_CAP = captain_name()
# Captain role/title, resolved once per process (env.py caches). Renders
# BYTE-IDENTICAL to the prior hardcoded "Head-of-Tech" on this deployment.
# Injected into the runtime clone prompt below via .format(role=_ROLE).
_ROLE = captain_role()

_DECISIONS_REL = "5-Reflections/Decisions"


def _vault_dir() -> Path:
    """The Decisions corpus dir, realpath-jailed to the vault (Corridor path-
    traversal mitigation). The vault base is ``framework.env.vault_dir()``
    (instance config; env ``CABINET_VAULT_DIR`` overrides) — on this deployment
    the brain vault, byte-identical to the removed hardcode. A deployment with no
    vault configured resolves to a generic dir whose Decisions subdir does not
    exist, so the corpus is simply empty (``extract_decision_cases`` returns
    [])."""
    vault = vault_dir() or str(Path.home() / "vault")
    vreal = os.path.realpath(vault)
    resolved = os.path.realpath(os.path.join(vreal, _DECISIONS_REL))
    if resolved != vreal and not resolved.startswith(vreal + os.sep):
        raise PermissionError("Decisions dir escaped the vault jail")
    return Path(resolved)


def _state_base() -> Path:
    """The state dir the extraction caches live in (personal data — kept OUT of
    the repo). ``framework.env.state_dir()`` (instance config; env
    ``CABINET_STATE_DIR`` overrides) or a generic ``~/.cabinet/state`` fallback
    when unconfigured. Byte-identical to the removed state hardcode on this
    deployment (alongside the autonomy_outcomes ledger)."""
    return Path(state_dir() or str(Path.home() / ".cabinet" / "state"))


def _cache_path() -> Path:
    """Extraction cache path. ``CABINET_DECISION_CACHE`` env override else the
    deployment state dir (``_state_base()``)."""
    p = os.environ.get("CABINET_DECISION_CACHE")
    if p:
        return Path(p).expanduser()
    return _state_base() / "cabinet_decision_cases.json"


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


# --- leak-scan: the dilemma must not reveal the Captain's choice ------------
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
         "you", "your", "that", "this", "it", "is", "was", "had", "has",
         "he", "his", "she", "her", "they", "them", "at", "by", "as", "be"}


def _content_tokens(s: str) -> set:
    # The Captain's own name is a non-distinctive stopword — folded in
    # dynamically so it tracks the deployment. _CAP.lower() == "nate" here, so
    # the effective stop set is byte-identical to the prior literal.
    stop = _STOP | {_CAP.lower()}
    toks = re.findall(r"\b\w+\b", (s or "").lower())
    return {t for t in toks if len(t) > 3 and t not in stop}


def _dilemma_leaks(dilemma: str, decision: str, why: str) -> bool:
    """True iff the dilemma reveals the Captain's choice — a backstop for the
    extractor prompt (the primary guard), catching EGREGIOUS copy-paste of the
    decision into the dilemma.

    Heuristic: the fraction of the DECISION's distinctive content tokens that
    surface in the dilemma. A neutral question legitimately SHARES the action
    verb ("should the Captain proceed?" vs decision "proceed") without revealing the
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


_EXTRACT_SYSTEM = f"""You split a logged DECISION note into three parts for a held-out evaluation.

The note records a decision {_CAP} already made, fusing the situation with his choice. Split it so an evaluator can pose the decision point to a model WITHOUT revealing what {_CAP} chose.

Return ONLY JSON:
{{"dilemma":"the decision point {_CAP} faced — the situation + the question/options, with ALL situational facts needed to decide, but WITHOUT stating or implying which option {_CAP} picked. Neutral framing. <=600 chars.",
 "decision":"what {_CAP} actually chose/did — the concrete call. <=200 chars.",
 "why":"{_CAP}'s rationale / the intent behind the choice. <=300 chars."}}

CRITICAL: the dilemma must NOT contain {_CAP}'s choice, the chosen action's verb, or wording that gives it away. Someone reading only the dilemma should not be able to tell what {_CAP} decided. Keep every situational fact that is needed to decide well."""


def _llm_split(payload: str, system: str, llm) -> dict | None:
    """Run an LLM split-prompt and parse {dilemma, decision, why}; None if the
    output is unusable. Shared by every source extractor (decisions corpus,
    git, …). Leak-scan is applied by the caller."""
    raw = llm(payload, system) or ""
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


def _extract_one(parsed: dict, llm) -> dict | None:
    """LLM-split one parsed decision NOTE into {dilemma, decision, why}."""
    payload = (f"# SITUATION (as logged, fuses situation + choice)\n"
               f"{parsed['situation']}\n\n# WHY ({_CAP})\n{parsed['why']}")
    return _llm_split(payload, _EXTRACT_SYSTEM, llm)


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


# --- git source: technical decisions (volume; tagged proxy) ----------------
# Git commit bodies on Captain-directed work carry recoverable {dilemma, decision,
# why, timestamp} — but they are AI-authored (the agent's prose, the Captain's
# direction) and technical-domain. So git is a VOLUME source tagged source="git"
# (a technical-decision proxy), never conflated with pure-Captain authenticity.
_GIT_EXTRACT_SYSTEM = """You split a git commit (a logged technical decision) into a held-out evaluation case.

The commit message states a problem and the solution that was implemented. Split it so an evaluator can pose the decision point WITHOUT revealing the chosen solution.

Return ONLY JSON:
{"dilemma":"the technical problem / decision point — symptom, constraint, and what must be decided, with the facts needed to decide, but WITHOUT stating the chosen fix/approach. Neutral. <=600 chars.",
 "decision":"the concrete technical call that was made (the fix/approach). <=200 chars.",
 "why":"the rationale — what it fixes/prevents, the trade-off. <=300 chars."}

CRITICAL: the dilemma must NOT contain the chosen solution — someone reading only the dilemma should not know which fix was picked. Keep the symptom/constraint facts needed to decide."""

# Skip non-judgment commits (releases, version bumps, pure merges).
_GIT_SKIP_RE = re.compile(
    r"^(chore\(release\)|release|bump|merge\b|v?\d+\.\d+\.\d+)", re.IGNORECASE)


def _git_cache_path() -> Path:
    p = os.environ.get("CABINET_DECISION_GIT_CACHE")
    if p:
        return Path(p).expanduser()
    return _state_base() / "cabinet_decision_cases_git.json"


def _git_log(repo: Path, n: int = 400, runner=None) -> list[dict]:
    """Read commits from a repo (READ-ONLY: git log only). argv list, no shell.
    Returns [{hash, date, subject, body}], newest first. ``runner`` is injectable
    for tests (defaults to subprocess.run)."""
    import subprocess
    run = runner or subprocess.run
    try:
        proc = run(["git", "-C", str(repo), "log", "--no-merges",
                    "--format=%H%x1f%aI%x1f%s%x1f%b%x1e", "-n", str(n)],
                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for rec in (getattr(proc, "stdout", "") or "").split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x1f")
        if len(parts) < 4:
            continue
        out.append({"hash": parts[0].strip(), "date": parts[1].strip(),
                    "subject": parts[2].strip(), "body": parts[3].strip()})
    return out


def extract_git_decision_cases(repos, llm=oauth_raw_llm, cache_path=None,
                               use_cache: bool = True, max_per_repo: int = 40,
                               min_body_chars: int = 120,
                               log_runner=None) -> list[DecisionCase]:
    """Mine judgment-call git commits into DecisionCases (source="git"). Each
    qualifying commit (substantive body, not a release/merge) is LLM-split into
    {dilemma, decision, why}; the dilemma is leak-scanned (the chosen fix must
    not bleed in). Cached by repo:hash outside the repo. READ-ONLY on repos."""
    cpath = cache_path or _git_cache_path()
    cache = {}
    if use_cache and cpath.exists():
        try:
            cache = json.loads(cpath.read_text(errors="replace"))
        except ValueError:
            cache = {}
    cases: list[DecisionCase] = []
    dirty = False
    for repo in repos:
        repo = Path(repo)
        picked = 0
        for c in _git_log(repo, runner=log_runner):
            if picked >= max_per_repo:
                break
            if len(c["body"]) < min_body_chars or _GIT_SKIP_RE.match(c["subject"]):
                continue
            key = f"{repo.name}:{c['hash'][:10]}"
            if use_cache and key in cache:
                rec = cache[key]
                if rec:
                    cases.append(DecisionCase(**rec))
                    picked += 1
                continue
            split = _llm_split(f"# COMMIT\n{c['subject']}\n\n{c['body']}",
                               _GIT_EXTRACT_SYSTEM, llm)
            rec = None
            if split and not _dilemma_leaks(split["dilemma"], split["decision"],
                                            split["why"]):
                rec = asdict(DecisionCase(
                    case_id=key, detected_at=c["date"], app=f"git:{repo.name}",
                    dilemma=split["dilemma"], decision=split["decision"],
                    why=split["why"], source="git"))
                cases.append(DecisionCase(**rec))
                picked += 1
            cache[key] = rec
            dirty = True
    if use_cache and dirty:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return cases


# The Captain's product/infra repos (Captain-directed) — NOT the cabinet harness
# branch (that is this session's own build work, not a Captain product decision).
# NOTE: these default repo names are Flavor-A instance-specific (see deviations);
# a deployment overrides them via build_decision_corpus(repos=...).
_DEFAULT_GIT_REPOS = [Path.home() / "v0-politiske-annoncer",
                      Path.home() / "dev-tasks"]


def build_decision_corpus(sources=("decisions", "git"), repos=None,
                          **kw) -> list[DecisionCase]:
    """Merge the enabled decision sources into one tagged corpus. ``decisions``
    = the pure-Captain hand-captured notes (source="decisions-corpus"); ``git`` =
    technical-decision proxy (source="git"). Each DecisionCase carries .source
    so results can be read per-source (pure-Captain vs proxy)."""
    out: list[DecisionCase] = []
    if "decisions" in sources:
        out += extract_decision_cases()
    if "git" in sources:
        out += extract_git_decision_cases(repos or _DEFAULT_GIT_REPOS, **kw)
    return out


# --- runner: clone proposes {decision, why} from the dilemma + identity -----
_DECISION_CLONE_SYSTEM = """You are {cap}'s clone, facing a real {role} decision. Make the call {cap} would make and give his reasoning. Decide as {cap} decides — his values, risk posture, and priorities drive the call.

{fence}

## How {cap} decides (nate_model patterns)
{patterns}

## How {cap} writes/reasons (voice profile)
{voice}

## Past decision lessons (date-filtered before this moment)
{lessons}

Return ONLY JSON: {{"decision":"the concrete call you make","why":"your reasoning, in {cap}'s frame"}}"""


def _clone_identity(case: DecisionCase, brain) -> dict:
    """Values-identity for the decision clone: voice + nate_model patterns +
    drafting lessons date-filtered STRICTLY before detected_at. No person_static
    (a decision has no single counterparty). Mirrors the reply cell's identity
    gather + privacy fence.

    ``brain`` is a ``framework.sources.PersonalSource`` (the bound personal
    source; default ``get_source()``). ``model_patterns()`` is the launcher-
    neutral method that on Flavor-A maps to ``me_signal.nate_model('patterns')``
    (the brain artifact kept verbatim, DE-NATE §3 — only the METHOD name changed);
    it is byte-identical to the prior ``BrainAdapter.nate_model_patterns()``."""
    def _v(x):
        return (x or "").strip() or "(unavailable)"
    return {
        "voice": _v(brain.voice_profile()),
        "patterns": _v(brain.model_patterns()),
        "lessons": _v(brain.drafting_lessons(case.detected_at)),
    }


def run_decision_case(case: DecisionCase, llm=oauth_raw_llm,
                      brain=None) -> dict:
    """Drive the clone on the dilemma; return its proposed {decision, why}. The
    clone sees the dilemma + values-identity ONLY — NEVER case.decision/why.
    Identity informs HOW it decides and is privacy-fenced (never echoed).

    ``brain`` is an injectable ``framework.sources.PersonalSource``; it defaults
    to ``get_source()`` — the bound personal source (the Flavor-A screenpipe
    adapter on this deployment, byte-identical to the prior ``BrainAdapter()``
    default). Tests inject a fake source in its place."""
    brain = brain or get_source()
    ident = _clone_identity(case, brain)
    system = _DECISION_CLONE_SYSTEM.format(
        cap=_CAP, role=_ROLE, fence=_clone_privacy_fence(_CAP),
        patterns=ident["patterns"], voice=ident["voice"], lessons=ident["lessons"])
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


# --- scorer: judge clone vs the Captain's actual {decision, why} ------------
_DECISION_JUDGE_SYSTEM = f"""You grade whether a MODEL's decision matches {_CAP.upper()}'s actual decision on the same dilemma — on two SEPARATE axes.

You are given the DILEMMA, {_CAP.upper()}'s actual decision + why (ground truth), and the MODEL's decision + why. Judge tone-blind; judge the substance of the call and its reasoning.

decision_verdict (did the MODEL make the same CALL?):
- match: same concrete choice/action.
- partial: overlapping but materially different (right direction, wrong scope/condition).
- divergent: a different call.

intent_verdict (does the MODEL's reasoning serve the SAME intent/WHY as {_CAP}'s?):
- intent-aligned: same underlying goal + values drove it, even if the surface call differs.
- intent-partial: serves part of the WHY but misses a material element.
- intent-divergent: wrong intent — different values/goal, or ungrounded/hallucinated reasoning.

Return ONLY JSON:
{{"decision_verdict":"match|partial|divergent",
 "intent_verdict":"intent-aligned|intent-partial|intent-divergent",
 "rationale":"<=140 chars"}}"""


def score_decision_case(case: DecisionCase, clone_out: dict,
                        judge=oauth_json_llm) -> dict:
    """Judge the clone's {decision, why} against the Captain's actual ground truth.
    Returns {decision_verdict, intent_verdict, composite, rationale}. The judge
    is SUPPOSED to see the ground truth (it grades against it); the leak boundary
    is on the clone (run_decision_case), which never saw it."""
    payload = (
        f"# DILEMMA\n{case.dilemma}\n\n"
        f"# {_CAP.upper()}'S ACTUAL DECISION\n{case.decision}\n"
        f"# {_CAP.upper()}'S WHY\n{case.why}\n\n"
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
