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
# A full line carrying an ISO timestamp/date — stripped from static frontmatter
# and read_note output (any such line is content-dated and may be post-cutoff).
_DATED_LINE_RE = re.compile(r"^.*\d{4}-\d{2}-\d{2}.*$", re.MULTILINE)
_NOTES_SECTION_RE = re.compile(r"^##+\s*Notes from replies.*\Z",
                               re.IGNORECASE | re.MULTILINE | re.DOTALL)


def _content_ts(hit: dict) -> str | None:
    """Derive a CONTENT timestamp for a vault hit, in order:
      (a) an ISO-string ``ts`` field (gather_context emits ts.isoformat(),
          brain server.py:209-212);
      (b) a date parsed from the note path / daily-note name
          (e.g. ``1-Daily/2026-05-12.md`` -> ``2026-05-12``).
    If neither yields a content date, return None -> the hit is treated as
    un-fenceable and EXCLUDED. There is NO ``mtime`` fallback, ever: mtime is
    file-EDIT time (the wrong clock) and a raw float never matches _ISO_RE, so
    the guard would silently pass every such hit through (design §2.3, B3)."""
    if not isinstance(hit, dict):
        return None
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
    section AND any individual line carrying an ISO date — only timeless
    attribute lines survive."""
    if not person_intel_md:
        return ""
    text = str(person_intel_md)
    # Drop the dated "Notes from replies" section (to end of document).
    text = _NOTES_SECTION_RE.sub("", text)
    # Drop any remaining line that carries an ISO date (could be post-cutoff).
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
      - reject 0-Self/ (the private Nate Model);
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
        raise PermissionError("refused: 0-Self/ is the private Nate Model")
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
    """Drop any line of read_note output carrying an ISO date (a post-cutoff
    date line would leak). Conservative: a daily note can still carry a future
    follow-up line even when its own filename is pre-cutoff."""
    if not text:
        return ""
    return "\n".join(ln for ln in str(text).splitlines()
                     if not _DATE_RE.search(ln)).strip()


class BrainAdapter:
    """Thin, injectable adapter over the brain bridge. Defaults to the real
    brain MCP surface; tests inject a fake. The ONLY retrieval entry points are
    the four leak-eligible tools (design §2.1) — there is deliberately NO
    Tier-2 / search_brain method, so no code path can reach "now".

    ``gather_vault`` MUST scope to ``sources=["vault"]`` so context_lib never
    fans out to the live _fetch_sent / _fetch_screen / _fetch_monday tiers."""

    def __init__(self, context_lib=None, server=None):
        self._context_lib = context_lib
        self._server = server

    def _ctx(self):
        if self._context_lib is None:
            import context_lib  # brain bridge dep (resolved on sys.path)
            self._context_lib = context_lib
        return self._context_lib

    def _srv(self):
        if self._server is None:
            import server  # brain MCP server module
            self._server = server
        return self._server

    def gather_vault(self, handle: str) -> dict:
        # sources=["vault"] EXACTLY — Tier-1 only; brief is discarded upstream.
        return self._ctx().gather(handle, sources=["vault"])

    def person_intel(self, slug: str) -> str:
        return self._srv().person_intel(slug)

    def open_commitments(self, direction: str) -> list:
        return self._srv().open_commitments(direction)

    def read_note(self, path: str) -> str:
        return self._srv().read_note(path)


def gather_cutoff_context(case: Case, *, brain=None,
                          read_paths: list | None = None) -> dict:
    """Assemble the officer's as-of-cutoff context (design §2.2). Returns a
    structured, ts-keyed dict — NEVER free-text prose. Every admitted source
    is content-timestamped before the cutoff and passed through
    leakguard.filter_mcp_result; every un-fenceable source is excluded and
    surfaced in ``excluded``.

    ``brain`` is an injectable adapter (defaults to BrainAdapter over the live
    brain bridge); ``read_paths`` is an optional list of explicit, pre-cutoff,
    vault-relative note paths to admit (each validated by _validate_read_path).
    """
    if brain is None:
        brain = BrainAdapter()
    cutoff = case.cutoff_ts

    # --- vault hits (Tier-1 only; brief DROPPED) ---------------------------
    vault = brain.gather_vault(case.slug or case.person) or {}
    raw_hits = vault.get("hits", []) or []
    # Pre-filter on a real CONTENT timestamp strictly before the cutoff; a hit
    # with no derivable content ts is un-fenceable -> excluded.
    pre = []
    for h in raw_hits:
        cts = _content_ts(h)
        if cts is not None and cts < cutoff:
            pre.append(h)
    vault_hits = leakguard.filter_mcp_result(pre, cutoff)

    # --- commitments (both directions; genuinely ts-keyed) -----------------
    commitments = leakguard.filter_mcp_result(
        list(brain.open_commitments("owed_by_nate") or [])
        + list(brain.open_commitments("owed_to_nate") or []),
        cutoff,
    )

    # --- person_intel -> static frontmatter (dated sections stripped) ------
    person_static = _static_frontmatter(brain.person_intel(case.slug or case.person))

    out = {
        "thread": case.thread_before,            # already pre-cutoff (asserted)
        "commitments": commitments,
        "vault_hits": vault_hits,
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
