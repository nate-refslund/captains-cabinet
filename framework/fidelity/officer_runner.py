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
redactor) was not called on the F1 path — F1's live guards are the pre-thread
assertion + the post-output scan. F4 (this module's gather_cutoff_context)
wires the live brain chain: it admits ONLY structured, per-record,
content-timestamped-before-cutoff sources (exclusion-by-default) and runs each
through leakguard.filter_mcp_result. run_case with gather=None still reproduces
F1 byte-for-byte (no gathering); gather=gather_cutoff_context is the F4 path.
"""

from __future__ import annotations

import hashlib
import re

from framework.env import captain_name
from framework.sources import get_source
from framework.sources.base import PersonalSource
from framework.fidelity import leakguard
from framework.fidelity.fidelity_events import emit_case_evaluated, emit_case_leaked
from framework.fidelity.oauth_llm import oauth_raw_llm
from framework.fidelity.officer_prompt import (
    build_agent_eval_system, build_clone_eval_system, build_eval_system,
    format_situation)
from framework.fidelity.types import Case, OfficerDecision

# Captain display name, resolved once per process (env.py caches). Renders
# BYTE-IDENTICAL to the prior hardcoded captain name here; baked into the EVAL_MODE
# prompt constants below so their sole .format() placeholder stays {cutoff_ts}
# (3 tests call EVAL_MODE_RULES.format(cutoff_ts=...) with no other key).
_CAP = captain_name()

# ---------------------------------------------------------------------------
# EVAL_MODE_RULES — conditional on whether context-gathering ran (design §4).
#
# F1 had a single block that BOTH said "you have NO knowledge / do not consult"
# AND "return ONLY the reply text". F4 makes it conditional so the A/B arms
# never contradict each other:
#   - The STRICT cutoff boundary is ALWAYS applied (both arms). It is the
#     sacred fence; it holds whether or not context was gathered.
#   - The "use the gathered context / propose options (incl. options IN the
#     reply text)" permission + a reconciled output line are appended ONLY when
#     gather is set.
#
# EVAL_MODE_RULES is kept BYTE-IDENTICAL to F1 (= strict body + F1's original
# "Return ONLY the reply text" line) so run_case(..., gather=None) reproduces
# the F1 prompt exactly. The gather arm is built from the shared strict body
# (_EVAL_MODE_STRICT) + the gather permission + the reconciled output line.
# ---------------------------------------------------------------------------

# Shared strict body — the cutoff boundary, WITHOUT any output-format line. Both
# arms start from this. {cutoff_ts} is .format()-substituted at call time.
_EVAL_MODE_STRICT = """

# EVALUATION MODE (held-out blind test)
You are in EVALUATION MODE. Your drafts, board updates, and commitments will be
reviewed, not executed — proceed as if they will be sent, but they are NOT. The
Cabinet will grade your decision. Your actions are captured, not executed. Do
NOT call queue_draft, do NOT write to any board, do NOT send anything.

You have NO knowledge of events at or after {cutoff_ts}. Do not consult or
reference anything timestamped at or after that moment (search results, vault
notes, commitments, decisions). This is a blind evaluation."""

# F1's output-format line (context-starved arm): return only the reply text.
_F1_OUTPUT_LINE = f"""

Return ONLY the reply text {_CAP} would have sent at that moment — no JSON, no
commentary, no subject line."""

# EVAL_MODE_RULES — the gather=None (F1) block. Byte-identical to F1's original.
EVAL_MODE_RULES = _EVAL_MODE_STRICT + _F1_OUTPUT_LINE

# Gather-arm permission (design §4): the context block was gathered as-of the
# cutoff and is safe to use; reason about the real goal and propose the fitting
# course of action — including options — IN the reply text. No new system
# authority is granted over the cutoff fence above; this only permits use of
# the already-leak-guarded context appended to the USER message.
_EVAL_MODE_GATHER_PERMISSION = """

The CONTEXT block below was gathered as-of the cutoff and is safe to use. You
may reason about the situation's real goal and propose the fitting course of action
— including options — in your reply. Serve the intent, not just the literal
ask."""

# Reconciled output line (gather arm): replaces F1's "Return ONLY the reply
# text" so proposing options does not invite JSON/scaffolding — options go IN
# the message text.
_EVAL_MODE_GATHER_OUTPUT_LINE = f"""

Return only the message you would send {_CAP}'s counterparty — no JSON, no meta-commentary,
no subject line. If the best response proposes options, put them in that message."""

# EVAL_MODE_RULES_GATHER — the gather!=None block: strict boundary + permission
# + reconciled output line. {cutoff_ts} substituted at call time.
EVAL_MODE_RULES_GATHER = (
    _EVAL_MODE_STRICT
    + _EVAL_MODE_GATHER_PERMISSION
    + _EVAL_MODE_GATHER_OUTPUT_LINE
)


# ===========================================================================
# F4 §2: leak-guarded as-of-cutoff context gathering.
#
# EXCLUSION-BY-DEFAULT. gather_cutoff_context admits ONLY structured,
# per-record, content-timestamped-before-cutoff sources. Every un-fenceable
# source is dropped and SURFACED in the "excluded" audit list, never passed
# through:
#   - gather_context.brief  -> un-fenceable prose (already summarized post-
#                              cutoff facts); DROPPED. Tier-1 hits ONLY, via
#                              sources=["vault"] (Tier-2 sent/screen/monday is
#                              "now", and _fetch_sent IS the held-out reply).
#   - search_brain          -> EXCLUDED; its only time field is `mtime` (file
#                              EDIT time, an epoch float), the WRONG clock and
#                              not guard-walkable. NO mtime fallback EVER.
#   - person_intel          -> static frontmatter only (dated / "Notes from
#                              replies" sections stripped — those absorb notes
#                              derived from the held-out reply).
#   - open_commitments      -> admitted (genuinely ts-keyed dicts), fenced.
#   - read_note             -> admitted ONLY for explicit, vault-jailed,
#                              pre-cutoff paths; output ISO-scrubbed.
# Every admitted source is then run through leakguard.filter_mcp_result.
# ===========================================================================

# An ISO date (date-only or full datetime) anywhere in a string/path.
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Any common date form anywhere in a line — ISO (2026-05-12), slash
# (2026/05/12), or compact (20260512). Used for stripping dated lines from
# static frontmatter AND read_note bodies; broader than _DATE_RE on purpose (a
# dated line can use any of these forms, and any of them may be post-cutoff).
# The compact \d{8} alternative is anchored to a non-digit boundary so it
# doesn't fire on long id/number runs.
_DATE_FORMS = r"(?:\d{4}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2}|(?<!\d)\d{8}(?!\d))"
# Per-line searcher over the broad date forms (no line anchors) — for scrubbing
# a single line at a time (read_note body). _DATED_LINE_RE below is the
# MULTILINE whole-line variant used for bulk-stripping frontmatter.
_DATE_FORMS_RE = re.compile(_DATE_FORMS)
# A full line carrying a date in any of those forms — stripped from static
# frontmatter (any such line is content-dated and may be post-cutoff).
_DATED_LINE_RE = re.compile(rf"^.*{_DATE_FORMS}.*$", re.MULTILINE)
# The dated "Notes from replies" section: from its heading up to (but NOT
# including) the NEXT ##-level heading — so a legitimate atemporal section that
# happens to follow it survives. \Z is the fallback when it is the last section.
_NOTES_SECTION_RE = re.compile(
    r"^##+\s*Notes from replies.*?(?=^##+\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL)


def _content_ts(hit: dict) -> str | None:
    """Derive a CONTENT timestamp for a vault hit, in order:
      (a) the index's per-chunk ``content_ts`` — when the content was
          authored/occurred, ISO-8601, emitted by the brain embeddings index
          (~62% coverage with honest NULLs). The CORRECT content clock; this is
          the field that lets conversation chunks (no date in their path) be
          fenced + admitted, instead of being silently excluded;
      (b) a legacy ISO-string ``ts`` field, if present (gather_context emits
          ts.isoformat());
      (c) a date parsed from the note path / daily-note name
          (e.g. ``1-Daily/2026-05-12.md`` -> ``2026-05-12``).
    If none yields a content date, return None -> the hit is treated as
    un-fenceable and EXCLUDED. There is NO ``mtime`` fallback, ever: mtime is
    file-EDIT time (the wrong clock) and a raw float never matches _ISO_RE, so
    the guard would silently pass every such hit through (design §2.3, B3)."""
    if not isinstance(hit, dict):
        return None
    cts = hit.get("content_ts")
    if isinstance(cts, str) and leakguard._ISO_RE.match(cts):
        return cts
    ts = hit.get("ts")
    if isinstance(ts, str) and leakguard._ISO_RE.match(ts):
        return ts
    for key in ("path", "ref", "heading"):
        m = _DATE_RE.search(str(hit.get(key) or ""))
        if m:
            return m.group(0)
    return None


def _static_frontmatter(person_intel_md) -> str:
    """Strip every dated/leak-prone section from a person dossier, returning
    only the atemporal frontmatter (role, relationship, primary_email, ...).

    Defends Blocker 4: the live dossier absorbs ``## Notes from replies``
    derived from the held-out reply (a case-specific leak). We drop that whole
    section AND any individual line carrying a date (ISO / slash / compact) —
    only timeless attribute lines survive."""
    if not person_intel_md:
        return ""
    text = str(person_intel_md)
    # Drop the dated "Notes from replies" section, anchored to the NEXT ##-level
    # heading (not end-of-doc) so a legitimate atemporal section placed after it
    # survives the strip.
    text = _NOTES_SECTION_RE.sub("", text)
    # Drop any remaining line that carries a date in any common form (could be
    # post-cutoff).
    text = _DATED_LINE_RE.sub("", text)
    # Collapse the blank lines the strips leave behind.
    lines = [ln.rstrip() for ln in text.splitlines()]
    out = "\n".join(ln for ln in lines if ln.strip() != "" or False)
    return out.strip()


def _validate_read_path(path: str, cutoff_ts: str) -> str:
    """Vault-jail + pre-cutoff validation for an explicit read_note path
    (design §2.1 read_note row; Corridor vault-jail). Raises ValueError /
    PermissionError on any unsafe path BEFORE the brain tool is touched
    (defense in depth on the brain server's own realpath jail):
      - reject empty, absolute, leading-slash, null-byte, or backslash paths;
      - reject ANY '..' traversal segment;
      - reject 0-Self/ (the Captain's private self-model);
      - if the path embeds an ISO date (a daily note), require it strictly
        BEFORE the cutoff date — a future-dated note is a leak.
    Returns the normalized vault-relative path."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("read_note path is required (vault-relative)")
    if "\x00" in path:
        raise ValueError("read_note path contains a null byte")
    if "\\" in path:
        raise ValueError("read_note path must use forward slashes")
    rel = path.strip()
    if rel.startswith("/"):
        raise PermissionError(f"refused absolute/leading-slash path: {path!r}")
    segments = [s for s in rel.split("/") if s not in ("", ".")]
    if any(s == ".." for s in segments):
        raise PermissionError(f"refused path traversal ('..'): {path!r}")
    if not segments:
        raise ValueError(f"refused empty path: {path!r}")
    if segments[0].casefold() == "0-self":
        raise PermissionError(f"refused: 0-Self/ is the private {_CAP} Model")
    norm = "/".join(segments)
    # Pre-cutoff gate: a date embedded in the path must be strictly < cutoff.
    m = _DATE_RE.search(norm)
    if m:
        cutoff_date = (cutoff_ts or "")[:10]
        if m.group(0) >= cutoff_date:
            raise PermissionError(
                f"refused post-cutoff note path {path!r} "
                f"(date {m.group(0)} >= cutoff {cutoff_date})")
    return norm


def _scrub_iso_lines(text: str) -> str:
    """Drop any line of read_note output carrying a date in ANY common form —
    ISO (2026-05-12), slash (2026/05/12), or compact (20260512) — since a
    post-cutoff date line would leak. Conservative: a daily note can still carry
    a future follow-up line even when its own filename is pre-cutoff, and that
    future line can be written in any of these forms.

    Uses the SAME broad date matching as _static_frontmatter (audit finding
    #2b): an ISO-only scrub here let a slash/compact post-cutoff line through
    while the frontmatter path already caught it."""
    if not text:
        return ""
    return "\n".join(ln for ln in str(text).splitlines()
                     if not _DATE_FORMS_RE.search(ln)).strip()


def _reply_topic(case: Case) -> str | None:
    """The inbound message being replied to — the topic for topic-aware vault
    retrieval. A reply case answers the most recent INBOUND (received) message;
    its text is what the conversation is about. Falls back to the last
    text-bearing thread message. Pre-cutoff by construction (thread_before is
    asserted pre-cutoff). NEVER reads real_reply (the held-out ground truth)."""
    thread = getattr(case, "thread_before", None) or []
    _inbound = ("received", "incoming", "in", "inbound")
    for m in reversed(thread):
        if isinstance(m, dict) and m.get("direction") in _inbound:
            t = (m.get("text") or "").strip()
            if t:
                return t
    for m in reversed(thread):
        if isinstance(m, dict) and (m.get("text") or "").strip():
            return m["text"].strip()
    return None


def gather_cutoff_context(case: Case, *, brain=None,
                          read_paths: list | None = None) -> dict:
    """Assemble the officer's as-of-cutoff context (design §2.2). Returns a
    structured, ts-keyed dict — NEVER free-text prose. Every admitted source
    is content-timestamped before the cutoff and passed through
    leakguard.filter_mcp_result; every un-fenceable source is excluded and
    surfaced in ``excluded``.

    ``brain`` is an injectable ``framework.sources.PersonalSource`` (defaults to
    ``get_source()`` — the bound personal source; on this deployment the Flavor-A
    adapter, byte-identical to the prior ``BrainAdapter()`` default);
    ``read_paths`` is an optional list of explicit, pre-cutoff, vault-relative
    note paths to admit (each validated by _validate_read_path).
    """
    if brain is None:
        brain = get_source()
    cutoff = case.cutoff_ts

    # --- vault hits (Tier-1 only; brief DROPPED; TOPIC-AWARE) --------------
    # The topic = the inbound message being replied to, so retrieval is driven
    # by what the conversation is ABOUT (the workshop budget, the house), not the
    # bare person slug. Pre-cutoff by construction (thread_before is asserted
    # pre-cutoff). gather's 0.4 relevance floor returns 0 (not noise) when
    # nothing on-topic is indexed — correct + leak-safe.
    topic = _reply_topic(case)
    vault = brain.search(case.slug or case.person, topic=topic) or {}
    raw_hits = vault.get("hits", []) or []
    # Pre-filter on a real CONTENT timestamp strictly before the cutoff; a hit
    # with no derivable content ts is un-fenceable -> excluded.
    #
    # A real vault hit carries ``ts`` as an mtime-derived DATETIME (the WRONG
    # clock — context_lib._fetch_vault). _content_ts ignores that mtime and
    # derives the authoritative content ts (content_ts / legacy ISO ts /
    # path-date). Now that leakguard._item_ts coerces datetime values, an
    # admitted hit whose mtime ts is post-cutoff would be falsely DROPPED by the
    # downstream fence. So we STAMP the authoritative content ts onto a COPY of
    # the hit (overwriting the wrong-clock mtime) before fencing — the fence
    # then operates on the correct, pre-cutoff content clock. (_content_ts has
    # already proven cts < cutoff for everything in ``pre``.)
    pre = []
    for h in raw_hits:
        cts = _content_ts(h)
        if cts is not None and cts < cutoff:
            stamped = dict(h)
            stamped["ts"] = cts
            pre.append(stamped)
    vault_hits = leakguard.filter_mcp_result(pre, cutoff)

    # --- commitments (both directions; genuinely ts-keyed) -----------------
    # CONTRACT direction values (base.PersonalSource) — the Flavor-A adapter
    # maps them to/from its own internal storage values.
    commitments = leakguard.filter_mcp_result(
        list(brain.open_commitments("owed_by_captain") or [])
        + list(brain.open_commitments("owed_to_captain") or []),
        cutoff,
    )

    # --- person_intel -> static frontmatter (dated sections stripped) ------
    person_static = _static_frontmatter(brain.person_intel(case.slug or case.person))

    out = {
        "thread": case.thread_before,            # already pre-cutoff (asserted)
        "commitments": commitments,
        "vault_hits": vault_hits,
        "topic_terms": vault.get("topic_terms"),  # what drove retrieval (observability)
        "person_static": person_static,
        "excluded": [
            "search_brain (mtime != content-ts; no mtime fallback)",
            "gather_context.brief (un-fenceable prose)",
            "gather_context Tier-2 sent/audio/ocr/monday (live = now)",
        ],
    }

    # --- read_note: explicit, vault-jailed, pre-cutoff paths only ----------
    if read_paths:
        notes = []
        for p in read_paths:
            # Validate BEFORE touching the brain (defense in depth). A bad path
            # raises and aborts gathering — we never silently skip a leak.
            norm = _validate_read_path(p, cutoff)
            body = _scrub_iso_lines(brain.read_note(norm))
            notes.append({"path": norm, "text": body})
        out["notes"] = notes

    return out


def _decision_evidence(decision: OfficerDecision) -> str:
    h = hashlib.sha1(str(decision.decision).encode("utf-8", "replace")).hexdigest()[:16]
    return f"chainhash:{h}"


# Per-record cap for rendered context lines (design §2.4: the context block is
# appended OUTSIDE format_situation's body caps, with its own per-record cap).
_CTX_RECORD_CAP = 400


def _render_context_block(ctx: dict) -> str:
    """Render the already-leak-guarded gather_cutoff_context dict (design §2.2)
    to a compact, ts-tagged context block for the USER message (design §2.4).

    This adds NO new source and reads NO new field — it is a pure deterministic
    render of the structured, fenced dict gather_cutoff_context returned (whose
    every admitted record was content-timestamped before the cutoff and passed
    through leakguard.filter_mcp_result upstream). ``thread`` is not re-rendered
    here — format_situation already carries it. Empty/thinned sections render an
    explicit "(no admissible pre-cutoff context for X)" line, so the officer
    sees the thinness rather than a silent gap."""
    lines = ["", "# CONTEXT (gathered as-of cutoff, leak-guarded — safe to use)"]

    vault_hits = ctx.get("vault_hits") or []
    lines.append("\n## Vault (pre-cutoff content only)")
    if vault_hits:
        for h in vault_hits:
            ts = str(h.get("ts") or "")[:16]
            ref = h.get("path") or h.get("ref") or h.get("heading") or ""
            text = str(h.get("text") or "").strip()[:_CTX_RECORD_CAP]
            lines.append(f"[{ts} {ref}] {text}")
    else:
        lines.append("(no admissible pre-cutoff context for vault)")

    commitments = ctx.get("commitments") or []
    lines.append("\n## Open commitments (fenced)")
    if commitments:
        for c in commitments:
            sd = str(c.get("source_date") or "")[:16]
            due = c.get("due") or ""
            text = str(c.get("text") or "").strip()[:_CTX_RECORD_CAP]
            due_s = f" due:{due}" if due else ""
            lines.append(f"[{sd}{due_s}] {text}")
    else:
        lines.append("(no admissible pre-cutoff context for commitments)")

    notes = ctx.get("notes") or []
    if notes:
        lines.append("\n## Pre-cutoff notes")
        for n in notes:
            body = str(n.get("text") or "").strip()[:_CTX_RECORD_CAP]
            lines.append(f"[{n.get('path', '')}] {body}")

    person_static = (ctx.get("person_static") or "").strip()
    lines.append("\n## Counterparty (atemporal frontmatter)")
    lines.append(person_static if person_static
                 else "(no admissible pre-cutoff context for counterparty)")

    excluded = ctx.get("excluded") or []
    if excluded:
        lines.append("\n## Excluded (un-fenceable; not gathered)")
        lines.append("; ".join(str(e) for e in excluded))

    return "\n".join(lines)


def _gather_clone_identity(case: Case, brain: "PersonalSource",
                           person_static: str = "") -> dict:
    """Gather the current-state identity priors that drive the clone draft
    (design §1.6; ground brain-identity-sources), leak-safe.

    Returns ``{voice, patterns, lessons, person_static}`` for
    build_clone_eval_system:
      - ``voice``   = voice.md (accepted current-state prior — live, not
                      as-of-then; fine to inject, mirrors retrodiction).
      - ``patterns``= nate_model('patterns') (accepted current-state prior,
                      PRIVATE-fenced by me_signal).
      - ``lessons`` = drafting lessons date-filtered STRICTLY BEFORE the case
                      cutoff (the ONLY hard cutoff here — a lesson logged at/
                      after the reply moment could postdate it and leak; the
                      whole same-day block is dropped, conservative).
      - ``person_static`` = the atemporal frontmatter already fenced upstream
                      (gather_cutoff_context strips dated/Notes sections). Reuse
                      it if present; otherwise derive it the same way.

    PRIVACY FENCE: these inform the SYSTEM prompt (HOW the clone writes/decides)
    only — build_clone_eval_system fences them, and run_case's post-output
    scan_for_leaks ensures none echo into the captured decision. This function
    never reads case.real_reply (the held-out ground truth)."""
    ps = (person_static or "").strip()
    if not ps:
        ps = _static_frontmatter(brain.person_intel(case.slug or case.person))
    return {
        "voice": brain.voice_profile(),
        "patterns": brain.model_patterns(),
        # before_ts is the case cutoff — STRICTLY pre-cutoff lessons only.
        "lessons": brain.drafting_lessons(case.cutoff_ts),
        "person_static": ps,
    }


# D17/INT-3 — the identity the gather arm drafts under. 'clone' (default,
# diagnostic arm: draft AS the Captain) stays the shard-output default until the
# first AGB baseline is cut; 'agent' (act ON THE CAPTAIN'S BEHALF, outcome-first) is
# an explicit opt-in. Kept as a module constant so measure_intent and tests
# share one vocabulary.
IDENTITY_MODES = ("clone", "agent")


def run_case(case: Case, officer_role: str, llm=oauth_raw_llm,
             emit_events: bool = True, gather=None,
             brain: "PersonalSource" = None,
             identity_mode: str = "clone") -> OfficerDecision:
    """Drive the officer blind on one Case; return the captured OfficerDecision.
    Hard-fails (LeakageDetectedError) + emits a leak event on any cutoff
    breach.

    ``gather`` is the A/B context-lift control (design §1.3, §8):
      - ``gather=None`` (default) reproduces F1 BYTE-FOR-BYTE — context-starved
        officer drafting from a GENERIC system prompt (no clone identity),
        strict EVAL_MODE_RULES, payload == format_situation(case). ``brain`` is
        never touched on this arm.
      - ``gather=gather_cutoff_context`` (the F4 clone arm) calls ``gather(case)``,
        renders the already-leak-guarded dict to a context block appended AFTER
        format_situation in the USER message (no new system authority), AND
        builds the officer system via ``build_clone_eval_system`` so the officer
        drafts AS THE CAPTAIN'S CLONE: the current-state identity priors (voice.md,
        nate_model('patterns'), drafting lessons date-filtered STRICTLY BEFORE
        the cutoff, and the atemporal person frontmatter) are gathered leak-safe
        (``_gather_clone_identity``) and injected into the SYSTEM prompt. The
        conditional EVAL_MODE_RULES_GATHER (strict boundary + permission to use
        the context / propose options + reconciled output line) still rides on.

    ``identity_mode`` (D17/INT-3) selects WHICH identity the gather arm drafts
    under: ``'clone'`` (default — draft AS the Captain, the diagnostic arm, exact
    prior behavior) or ``'agent'`` (act ON THE CAPTAIN'S BEHALF, outcome-first, via
    ``build_agent_eval_system``). The default stays 'clone' until the first
    AGB baseline is cut (A/A invariant); an unknown mode raises ValueError
    (loud — a typo must never silently change what a shard measured). The F1
    arm (``gather=None``) carries no identity, so the mode is inert there.

    PRIVACY FENCE (paramount): the identity informs the SYSTEM prompt ONLY —
    build_clone_eval_system / build_agent_eval_system fence it, and the
    post-output scan_for_leaks (always run, both arms and both identities)
    ensures none of it (nor any post-cutoff signal) echoes into the captured
    decision. ``brain`` is an injectable ``framework.sources.PersonalSource``
    (defaults to ``get_source()`` — the bound personal source); tests inject a
    fake."""
    if identity_mode not in IDENTITY_MODES:
        raise ValueError(
            f"unknown identity_mode {identity_mode!r} — expected one of "
            f"{IDENTITY_MODES}")
    # 1. PRE-execution guard: reconstructed thread must be strictly pre-cutoff.
    try:
        leakguard.assert_thread_pre_cutoff(case.thread_before, case.cutoff_ts)
    except leakguard.LeakageDetectedError as e:
        if emit_events:
            emit_case_leaked(case.case_id, officer_role, case.lane, [str(e)])
        raise

    # 2. Build the eval prompt (role def + eval rules + cutoff); drive blind.
    #    EVAL_MODE_RULES is conditional on whether gathering ran (design §4):
    #    the gather=None arm is byte-identical to F1.
    rules = EVAL_MODE_RULES if gather is None else EVAL_MODE_RULES_GATHER
    if gather is None:
        # F1 arm: generic system prompt, NO identity. Byte-for-byte unchanged.
        system = build_eval_system(case, officer_role) + \
            rules.format(cutoff_ts=case.cutoff_ts)
        user_msg = format_situation(case)
    else:
        # F4 clone arm. Gather + render the leak-guarded context, appended AFTER
        # the situation (design §2.4) so it inherits no new system-prompt
        # authority. This adds no new source — gather already enforced
        # exclusion-by-default + fencing.
        ctx = gather(case)
        user_msg = format_situation(case) + "\n" + _render_context_block(ctx)
        # Build the system from the gathered identity. Identity is gathered
        # leak-safe (lessons date-filtered STRICTLY before the cutoff);
        # person_static is reused from the gathered ctx. identity_mode picks
        # the framing: 'clone' drafts AS the Captain (default, byte-identical prior
        # path); 'agent' acts ON THE CAPTAIN'S BEHALF (D17 opt-in).
        if brain is None:
            brain = get_source()
        identity = _gather_clone_identity(
            case, brain, person_static=ctx.get("person_static", ""))
        build_system = (build_agent_eval_system if identity_mode == "agent"
                        else build_clone_eval_system)
        system = build_system(case, officer_role, identity) + \
            rules.format(cutoff_ts=case.cutoff_ts)
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
