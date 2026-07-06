"""Held-out case builder (the F1 benchmark - design §95-99).

The validation universe is the send-1to1-reply lane in autonomy_outcomes.jsonl
(~266 rows). Those rows are CUT-OFF in their text fields, so F1 does NOT score
their text. It rebuilds full paired cases from 3-People/*/conversations.md via
retrodiction.extract_cases (leak-safe, full thread_before) and uses the
autonomy rows only to SIZE/sanity-check the universe (ground finding: rebuild
from conversations.md, not from the cut-off rows).

F1 supports exactly the reply cell ('send-1to1-reply', 'reply'); other
(lane, decision_type) pairs raise NotImplementedError and land in F3
(Monday activity-log connector for triage, etc.)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from framework.env import state_dir
from framework.fidelity import retro
from framework.fidelity.officer_prompt import intent_and_context
from framework.fidelity.types import Case

_SUPPORTED: set[tuple[str, str]] = {("send-1to1-reply", "reply")}

# --- Scoreable fairness filter (design lever #2,
# docs/first-fidelity-baseline-2026-06-20.md §25-27) --------------------------
# A held-out reply case is only a FAIR benchmark target if it carries enough
# signal that a faithful clone could plausibly align on it. A bare link, a
# pasted credential/JWT, a two-word ack, or a content-free pleasantry can never
# align with intent — scoring against them is noise that drags the un-gamed
# fidelity number around for reasons unrelated to clone quality. This filter
# EXCLUDES those degenerate cases at build time so every eval is clean.
#
# LEAK-SAFETY: this filter only ever REMOVES cases. It admits NO content. It
# reads ``real_reply`` (the held-out ground truth) and ``thread_before`` (the
# pre-cutoff thread) PURELY to decide inclusion — it never copies either into a
# clone-visible field (``intent`` / ``thread_before`` are untouched), so it can
# introduce no post-cutoff leak. (Anti-leak boundary mirrors _enrich_intent.)
#
# Regexes are pre-compiled at module scope and linear (no catastrophic
# backtracking) to keep filtering cheap + ReDoS-safe over the full universe.
_URL_RE = re.compile(r"https?://\S+")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}")
_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)
# Decision-forcing markers: a thread that asks something / requests a call /
# pushes a decision carries enough signal to score even when short. EN + DA
# (the Captain's two reply languages). A bare '?' also counts (handled separately).
_DECISION_MARKERS = (
    # English
    "recommend", "should we", "should i", "can you", "could you", "would you",
    "decide", "decision", "approve", "approval", "sign off", "let me know",
    "what do you think", "thoughts?", "do you want", "are you ok", "is it ok",
    "wdyt", "any chance", "please", "need you to", "can we", "shall we",
    # Danish
    "anbefal", "skal vi", "skal jeg", "kan du", "kan vi", "vil du",
    "beslut", "godkend", "hvad synes", "vil du gerne", "kan I", "må jeg",
    "er det ok", "hvad mener", "lad mig vide", "har du mulighed",
)

# Minimum scoreable thresholds — kept as module constants so they are visible /
# tunable and asserted by tests rather than buried as magic numbers.
_MIN_REPLY_WORDS = 6        # acks shorter than this (after URL/JWT strip) are excluded
_MIN_THREAD_EXCHANGES = 3   # threads with fewer AND no decision signal are out
# build_cases over-fetches by this factor when filtering so the post-filter
# count still approximates the requested ``n`` (the ~5% degenerate share means
# a modest oversample suffices; the floor guards tiny-n requests).
_OVERSAMPLE = 4
_OVERSAMPLE_FLOOR = 16


def _reply_text(case: Case) -> str:
    """The held-out reply text for a case, from either accessor (defensive)."""
    r = getattr(case, "real_reply", "") or ""
    if not r:
        gt = getattr(case, "ground_truth", None) or {}
        r = gt.get("real_reply", "") or ""
    return r


def _has_decision_signal(text: str) -> bool:
    """True iff the text forces/invites a decision (a question or a request).
    Used to keep a SHORT thread that nonetheless asks the Captain to decide something
    — those are legitimate, scoreable judgment cases."""
    t = (text or "").lower()
    if "?" in t:
        return True
    return any(m in t for m in _DECISION_MARKERS)


def _thread_has_signal(case: Case) -> bool:
    """A thread is scoreable on length-signal grounds if it has at least
    ``_MIN_THREAD_EXCHANGES`` text-bearing exchanges (prior messages + the
    reply itself), OR — when shorter — it carries decision-forcing content in
    any pre-cutoff message. Only ``thread_before`` (pre-cutoff) and the reply
    are inspected; nothing post-cutoff is read."""
    thread = getattr(case, "thread_before", None) or []
    exchanges = sum(1 for m in thread
                    if isinstance(m, dict) and (m.get("text") or "").strip())
    # +1 for the held-out reply itself (it is an exchange in the conversation).
    exchanges += 1 if _reply_text(case).strip() else 0
    if exchanges >= _MIN_THREAD_EXCHANGES:
        return True
    # Short thread: keep it only if a pre-cutoff message forces a decision.
    return any(
        isinstance(m, dict) and _has_decision_signal(m.get("text") or "")
        for m in thread
    )


def is_scoreable(case: Case) -> bool:
    """True iff a held-out reply Case is a FAIR benchmark target (design §25-27).

    Excludes (returns False for) degenerate, un-scoreable cases:
      1. JWT / credential dumps in the reply (``eyJ…`` tokens).
      2. Acks / bare-link dumps — fewer than 6 real words once URLs and JWTs
         are stripped (a bare URL strips to 0 words; "se her <url>" to 2). A
         substantive message that merely CONTAINS a long URL is KEPT — the
         byte-share of the URL is not a disqualifier.
      3. Ultra-short low-signal threads — fewer than 3 exchanges AND no
         decision-forcing content anywhere in the pre-cutoff thread.

    LEAK-SAFE: read-only over ``real_reply`` + pre-cutoff ``thread_before``;
    decides inclusion only, never admits or mutates content."""
    reply = _reply_text(case).strip()
    if not reply:
        return False
    if _JWT_RE.search(reply):
        return False
    stripped = _JWT_RE.sub("", _URL_RE.sub("", reply)).strip()
    # Short ack / bare-link dump: too few real words once links/tokens are
    # removed. A bare URL strips to 0 words; a substantive reply that merely
    # CONTAINS a long URL keeps its words and is kept (byte-share of the URL
    # must not disqualify a real message — the old >50%-URL rule wrongly
    # dropped real Danish questions carrying long Sheets/Monday links).
    if len(_WORD_RE.findall(stripped)) < _MIN_REPLY_WORDS:
        return False
    # Ultra-short low-signal thread.
    if not _thread_has_signal(case):
        return False
    return True

def _default_outcomes() -> Path:
    """The autonomy-outcomes ledger path (the F1 validation universe). The
    ``CABINET_AUTONOMY_OUTCOMES`` env override wins; else the deployment state
    dir (``framework.env.state_dir()``, or a generic ``~/.cabinet/state``
    fallback when unconfigured) + the ledger filename. Byte-identical to the
    removed ``~/.screenpipe/state`` hardcode on this deployment."""
    override = os.environ.get("CABINET_AUTONOMY_OUTCOMES")
    if override:
        return Path(override).expanduser()
    base = state_dir() or str(Path.home() / ".cabinet" / "state")
    return Path(base) / "autonomy_outcomes.jsonl"


_DEFAULT_OUTCOMES = _default_outcomes()


def load_autonomy_rows(path: Path | None = None,
                       lane: str = "send-1to1-reply") -> list[dict]:
    """Return the autonomy_outcomes rows for the given lane (metadata only -
    text fields are cut-off and must NOT be scored)."""
    p = path or _DEFAULT_OUTCOMES
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("lane") == lane:
            rows.append(r)
    return rows


def validation_count(path: Path | None = None,
                     lane: str = "send-1to1-reply") -> int:
    """Size of the validation universe for the lane (the ~266-row count)."""
    return len(load_autonomy_rows(path=path, lane=lane))


def build_cases(lane: str = "send-1to1-reply", decision_type: str = "reply",
                n: int = 24, window=None, people_dir: Path | None = None,
                scoreable_only: bool = True) -> list[Case]:
    """Build held-out Cases for the (lane, decision_type) cell.

    F1: reconstructs full threads from conversations.md (leak-safe) via the
    retrodiction extractor, mapped onto the Case model. `window` is accepted
    for design-interface parity (reserved for time-windowed extraction in
    later cells). Unsupported cells raise NotImplementedError.

    ``scoreable_only`` (default True): apply the scoreable fairness filter
    (``is_scoreable``) so every returned case is a fair benchmark target —
    degenerate link/credential/ack/low-signal cases are excluded (design
    lever #2). Because filtering removes a (small) share of the universe, the
    extractor is OVER-FETCHED so the post-filter result still approximates the
    requested ``n``; the result is truncated back to ``n``. Set
    ``scoreable_only=False`` for byte-for-byte legacy behaviour (no over-fetch,
    no filter) — used by mapping/intent unit tests that deliberately feed
    degenerate fixtures."""
    if (lane, decision_type) not in _SUPPORTED:
        raise NotImplementedError(
            f"F1 supports only {sorted(_SUPPORTED)}; "
            f"({lane!r}, {decision_type!r}) lands in F3.")
    fetch_n = (max(n * _OVERSAMPLE, _OVERSAMPLE_FLOOR)
               if scoreable_only and n > 0 else n)
    rcs = retro.extract_cases(n_cases=fetch_n, people_dir=people_dir)
    cases = [Case.from_retro_case(rc, lane=lane, decision_type=decision_type)
             for rc in rcs]
    if scoreable_only:
        cases = [c for c in cases if is_scoreable(c)]
        if n > 0:
            cases = cases[:n]
    return [_enrich_intent(c) for c in cases]


def _enrich_intent(case: Case) -> Case:
    """Cache the reconstructed as-of-cutoff intent on the Case (design §5, §1.6).

    The intent is a PURE function of the pre-cutoff thread: it is computed by
    ``officer_prompt.intent_and_context``, which reads ``case.thread_before``
    ONLY and NEVER ``case.real_reply`` (the held-out ground truth). Real-world
    facts the situation implicates (the house, the lawn size) enter the harness
    only through the leak-guarded ``gather_cutoff_context`` path at officer time
    (§2) — they are NOT baked into the benchmark intent here.

    Enrichment is LAZY/fill-if-empty: an already-populated ``case.intent`` (a
    refreshed benchmark) is preserved, and if it is still empty at score time
    ``scorer.score`` recomputes it the same way. The cached value lives on the
    in-memory Case object only; nothing here writes it to the embeddings/brain
    index, so — like the held-out set — it stays out of the index and the clone
    cannot memorize it (parent §274-276)."""
    if not case.intent:
        case.intent = intent_and_context(case)["reconstructed_intent"]
    return case
