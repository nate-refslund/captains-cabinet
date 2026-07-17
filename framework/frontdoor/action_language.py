"""Receipt grammar (Wave B RECEIPTS, 2026-07-09) — WHAT / WHY / COST / UNDO.

Every acted receipt the Captain reads should answer four questions: WHAT was
done (a plain-language phrase, not an enum slug), WHY it was done (the
proposing card's rationale — never invented), what it COST (attributed only
when the acting path measured it — never fabricated), and how to UNDO it (the
existing 48h handle, untouched here). This module owns the language layer of
that grammar:

  * ``HUMAN_PHRASES`` / ``human_phrase`` — slug → human phrase for every
    classifier action_type AND every executor step kind, with a safe
    de-underscore fallback for unknown slugs (never a KeyError, never a bare
    enum leaking to the Captain).
  * ``why_of`` / ``cost_of`` / ``cost_line`` — the additive ``why`` / ``cost``
    journal-row fields, read honestly (absent ⇒ None / "cost: unattributed").
  * ``render_receipt`` / ``receipt`` — thin wrappers over the germline
    ``tell_surface`` formatters that insert the why + cost lines into a
    receipt (before the undo line, before the ONE trusted ``·pid·`` marker).
  * ``digest_with_why`` — the compact ``— why`` clause on the digest's ACTED
    item headlines (called from the unlocked ``tell_digest`` orchestrator).
  * ``stamp_journal_why`` — the unlocked write seam: append why/cost
    ENRICHMENT rows (same jid, last-write-wins) onto a pid's executed journal
    rows, for dispatch orchestrators that hold the card rationale.

WHY THIS MODULE EXISTS SEPARATELY (germline etiquette): the natural homes —
``action_undo.new_row`` / ``action_exec.deliver_action`` (stamping why/cost at
write time) and ``tell_surface.render_receipt`` / ``build_digest`` (rendering
them) — are germline-locked (cabinet/scripts/germline-lock.sh). Until a
Captain unlock window lands those additive diffs, this module carries the
grammar from the unlocked side, exactly as ``tell_digest`` carries the 📈 LOOP
readout because ``tell_surface`` is locked. The wrappers are drop-in: when the
germline edit lands, ``tell_surface`` can call ``receipt_grammar_lines`` /
``human_phrase`` directly and the wrappers become byte-identical pass-throughs
(decoration is idempotent — already-present lines are never doubled).

WHY — the additive ``why`` journal field
  The proposing card's rationale (the ActionProposal ``situation`` line, or a
  step payload's own ``why`` leg) carried through the act/approve paths onto
  the journal row. When genuinely absent the FIELD IS OMITTED and no why line
  renders — the grammar never invents a rationale (honesty doctrine).

COST — attribution semantics (documented per the Wave-B contract)
  A journal row MAY carry an additive ``cost`` dict stamped AT WRITE TIME by
  an acting path that measured its own spend for THIS act, shape::

      {"usd": 0.0123, "tokens_in": 900, "tokens_out": 120,
       "model": "...", "source": "lane-metered"}

  (any subset; at least one non-negative numeric of usd/tokens_in/tokens_out;
  ``source`` names the meter). Only such a stamped row renders an attributed
  cost line. The estate's per-officer daily counters — the Redis hash
  ``cabinet:cost:tokens:daily:<date>`` with ``{officer}_input`` /
  ``{officer}_output`` / ``{officer}_cache_write`` / ``{officer}_cache_read``
  / ``{officer}_cost_micro`` fields written by the stop-hook and read by
  ``cabinet/scripts/cost-report.sh`` — are DAY + OFFICER aggregates spanning
  every activity in a session; apportioning them to one act after the fact
  would be a fabricated number, so this module NEVER reads them for a receipt.
  Absent or malformed cost renders the honest ``cost: unattributed`` — never
  an invented figure, and a malformed dict fails closed to unattributed
  rather than rendering a number we cannot trust.

MARKER HYGIENE [SEC-4 / RT-A9]: every string this module inserts into a
Captain-facing message is run through the ONE marker-stripping source
(``action_lane._no_marker``), whitespace-collapsed to ONE true line, and
length-clipped (``_WHY_CAP_RECEIPT`` / ``_WHY_CAP_DIGEST``) — a why sourced
from captured text can never forge a bindable ``·fakepid·`` marker, smuggle
a line break into the receipt structure, nor blow the Telegram chunking
budget. The
reserved U+00B7 ``·`` char never appears in any phrase or line built here;
the trailing trusted pid marker is preserved LAST, byte-identical. The undo
grammar lines ("⏱ Undo within …", "undo: `undo N` …") are never modified.

BACK-COMPAT: an old journal row carrying neither ``why`` nor ``cost`` (nor a
payload/content why) renders BYTE-IDENTICALLY to today through every wrapper
here — asserted in framework/frontdoor/tests/test_action_language.py.

Stdlib-only; ``from __future__ import annotations`` keeps it importable under
the system 3.9.6 interpreter like its tell_surface/tell_digest neighbours.
Pure formatting throughout except the ONE explicit journal-append seam
(``stamp_journal_why``), which lazy-imports the journal owner and never
raises. No Redis, no subprocess, no network, no sends.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# The ONE source of pid-marker stripping (SEC-4) — imported, never
# re-implemented, so this layer and the proposer card can never diverge on
# what "strip an injected marker" means (same rule as tell_surface).
from framework.acting.action_lane import _no_marker
from framework.frontdoor import tell_surface

__all__ = [
    "HUMAN_PHRASES",
    "human_phrase",
    "why_of",
    "cost_of",
    "cost_line",
    "receipt_grammar_lines",
    "render_receipt",
    "receipt",
    "digest_with_why",
    "digest_with_evidence",
    "stamp_journal_why",
]

# --- tuning constants ---------------------------------------------------------

# Receipt why-line cap — parity with tell_surface._VALUE_CAP so a receipt's
# why never outweighs the exact content it explains.
_WHY_CAP_RECEIPT = 400
# Digest clause cap — parity with tell_surface._NEED_WHY_CAP: the clause is
# CONTEXT on a scannable line, never the authority text.
_WHY_CAP_DIGEST = 160
# Journal storage cap for a stamped why (subject caps at 300; the why may
# carry a sentence more, but the journal is not a prose store).
_WHY_STORE_CAP = 600

# --- WHAT: slug → human phrase --------------------------------------------------

# Every classifier action_type (framework/authority/classifier.py ACTION_TYPES
# — the single enum source) AND every executor step kind
# (framework/frontdoor/action_exec.py _PAYLOAD_KEYS / the proposer's
# ACTION_TYPE_MAP keys) gets an explicit past-tense phrase. Coverage is
# parametrized against BOTH live registries in test_action_language.py, so a
# new enum member fails the suite until it gets a phrase here. Unknown slugs
# fall back to ``human_phrase``'s de-underscore — visible, never a crash.
HUMAN_PHRASES: Dict[str, str] = {
    # -- classifier action_types: reversible class --
    "task_status_move": "moved a task's status",
    "label": "changed a label",
    "tier2_note": "wrote a note",
    "draft_only": "prepared a draft",
    "local_edit": "edited a local file",
    "investigation_run": "ran a read-only investigation",
    # -- pm_write / calendar_write (reversible-with-undo) --
    "task_create": "created a task",
    "board_status": "updated a board column",
    "calendar_event_create": "scheduled a calendar event",
    # -- internal comms --
    "internal_message": "sent an internal message",
    "internal_email": "sent an internal email",
    "officer_dispatch": "dispatched work to an officer",
    # -- external comms (hard ceiling — phrases exist for honest telling only) --
    "external_message": "sent an external message",
    "external_email": "sent an external email",
    # -- deploy --
    "vercel_deploy_preview": "deployed a preview build",
    "git_push_nonmain": "pushed to a non-main branch",
    "vercel_deploy_prod": "deployed to production",
    "git_push_main": "pushed to the main branch",
    # -- spend (ceiling) --
    "purchase": "made a purchase",
    "provision_paid": "provisioned a paid service",
    "billing": "changed a billing setting",
    # -- secrets (ceiling) --
    "secret_read": "read a secret",
    "secret_write": "wrote a secret",
    "env_write": "changed an environment variable",
    # -- network_write (ceiling) --
    "mcp_post": "sent a network write (POST)",
    "mcp_put": "sent a network write (PUT)",
    "mcp_delete": "sent a network delete",
    # -- credentials_grant (ceiling) --
    "oauth_grant": "granted an OAuth authorization",
    "token_grant": "granted a token",
    # -- the visible propose-defaulting backstop --
    "ambiguous": "performed an unclassified action",
    # -- executor step kinds (action_exec._PAYLOAD_KEYS / ACTION_TYPE_MAP keys;
    #    investigation_run doubles as both and is covered above) --
    "monday_task_create": "created a task",
    "monday_task_update": "updated a task",
    "reminder_create": "scheduled an event",
    "delegate_work": "dispatched work to an officer",
    "mission_propose": "proposed a mission",
    # -- the acted-event fallback kind (action_undo.acted_event) --
    "action": "performed an action",
}


def human_phrase(slug: Optional[str]) -> str:
    """The human phrase for an action slug. Explicit map first; unknown slugs
    de-underscore/de-hyphen to lowercase words (marker-stripped) — a safe,
    visible fallback so a future enum member reads as words, never as a raw
    ``some_new_slug`` token or a KeyError. Empty/None ⇒ ``"acted"``."""
    s = str(slug or "").strip()
    if not s:
        return "acted"
    phrase = HUMAN_PHRASES.get(s)
    if phrase:
        return phrase
    return _no_marker(re.sub(r"[_\-]+", " ", s).strip().lower()) or "acted"


# --- WHY: honest extraction ------------------------------------------------------

def why_of(row: Optional[Dict[str, Any]]) -> Optional[str]:
    """The row's rationale, or None — NEVER invented. Precedence: the additive
    journal ``why`` field (the proposing card's rationale carried through the
    act/approve paths), then an orchestrator-joined ``content.why``, then the
    executed ``payload.why`` (the monday_task_update note leg some cards carry
    today). Whitespace-only counts as absent."""
    if not isinstance(row, dict):
        return None
    candidates = [row.get("why")]
    for key in ("content", "payload"):
        src = row.get(key)
        if isinstance(src, dict):
            candidates.append(src.get("why"))
    for cand in candidates:
        if isinstance(cand, str) and cand.strip():
            return cand.strip()
    return None


# --- COST: honest attribution ------------------------------------------------------

_COST_NUMERIC_KEYS = ("usd", "tokens_in", "tokens_out")
_COST_KEYS = frozenset(_COST_NUMERIC_KEYS) | {"model", "source"}


def _valid_cost(cost: Any) -> Optional[Dict[str, Any]]:
    """A validated copy of a stamped cost dict, or None. Fail-closed on ANY
    malformation (unknown key, negative/boolean/non-numeric figure, non-string
    model/source, no numeric at all): a cost we cannot trust renders as
    ``unattributed``, never as a number."""
    if not isinstance(cost, dict) or not cost:
        return None
    if any(k not in _COST_KEYS for k in cost):
        return None
    has_numeric = False
    for k in _COST_NUMERIC_KEYS:
        if k in cost:
            v = cost[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                return None
            has_numeric = True
    for k in ("model", "source"):
        if k in cost and not isinstance(cost[k], str):
            return None
    return dict(cost) if has_numeric else None


def cost_of(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The row's write-time-stamped cost dict (validated), or None. See the
    module docstring for the attribution semantics — the per-officer daily
    counters are aggregates and are deliberately never read here."""
    if not isinstance(row, dict):
        return None
    return _valid_cost(row.get("cost"))


def cost_line(row: Optional[Dict[str, Any]]) -> str:
    """The receipt's cost line. Attributed ONLY from a write-time-stamped cost
    dict; anything else is the honest ``cost: unattributed`` — NEVER a
    fabricated number."""
    c = cost_of(row)
    if c is None:
        return "cost: unattributed"
    bits: List[str] = []
    if "usd" in c:
        bits.append("~$%.4f" % float(c["usd"]))
    tokens: List[str] = []
    if "tokens_in" in c:
        tokens.append("%d in" % int(c["tokens_in"]))
    if "tokens_out" in c:
        tokens.append("%d out" % int(c["tokens_out"]))
    if tokens:
        bits.append(" / ".join(tokens) + " tokens")
    src = c.get("source") or c.get("model")
    label = " — ".join(bits)
    if src:
        # _compact, not bare _no_marker: a newline-bearing source string must
        # never break the ONE-line form the receipt structure (and
        # _insert_grammar's exact-line dedup) relies on.
        label += " (" + _compact(str(src))[:60] + ")"
    return "cost: " + label


# --- receipt decoration (why + cost lines) --------------------------------------

def receipt_grammar_lines(row: Optional[Dict[str, Any]]) -> List[str]:
    """The why/cost lines a receipt gains for this row. BACK-COMPAT RULE: a
    row carrying NEITHER field (an old-world row) gains NOTHING — it renders
    exactly as today. A row in the new grammar (a why is present, or a cost
    was stamped) always gains the cost line — attributed when stamped, the
    honest ``cost: unattributed`` when not. Every line built here is ONE true
    line (whitespace-collapsed) — the exact-line idempotency dedup in
    ``_insert_grammar`` is sound only over single-line forms."""
    why = why_of(row)
    cost = cost_of(row)
    if why is None and cost is None:
        return []
    lines: List[str] = []
    if why is not None:
        lines.append("why: " + tell_surface._clip(_compact(why),
                                                  _WHY_CAP_RECEIPT))
    lines.append(cost_line(row))
    return lines


_MARKER_LINE_RE = re.compile(r"·[^·\n]+·\Z")
# The receipt's undo/attention line heads (tell_surface._undo_line) — the
# grammar lines are inserted immediately ABOVE this line (WHAT/WHY/COST/UNDO
# order); the line itself is never modified.
_UNDO_LINE_HEADS = ("⏱ Undo within ", "⚠ Needs your attention")


def _insert_grammar(text: str, row: Dict[str, Any]) -> str:
    """``text`` (a rendered receipt) with the row's why/cost lines inserted
    before the undo line, keeping the ONE trusted trailing ``·pid·`` marker
    LAST and byte-identical. Idempotent, anchored to EXACT line forms: a
    grammar line is skipped only when the identical (stripped) line already
    exists — a prior decoration, or the germline body's own rendering of the
    same content/payload why (the forms coincide for ordinary single-spaced
    text; a whitespace-exotic content why may render alongside the grammar
    line — real text twice, never fabrication). Receipt CONTENT that merely
    shares a ``why:``/``cost:`` prefix (e.g. a captured payload string
    rendering ``cost: 1200``) can no longer false-suppress the honest
    grammar lines — the exact-line match is sound because grammar lines are
    single-line by construction. Empty grammar ⇒ ``text`` unchanged."""
    lines_to_add = receipt_grammar_lines(row)
    if not text or not lines_to_add:
        return text
    body = text.split("\n")
    marker: Optional[str] = None
    if body and _MARKER_LINE_RE.fullmatch(body[-1]):
        marker = body.pop()
    present = {ln.strip() for ln in body}
    lines_to_add = [ln for ln in lines_to_add if ln.strip() not in present]
    if lines_to_add:
        at = len(body)
        for i, ln in enumerate(body):
            if any(ln.startswith(h) for h in _UNDO_LINE_HEADS):
                at = i                       # first undo/attention line wins
                break
        body[at:at] = lines_to_add
    if marker is not None:
        body.append(marker)
    return "\n".join(body)


def render_receipt(acted_row: Optional[Dict[str, Any]], *,
                   now: Any = None) -> str:
    """``tell_surface.render_receipt`` + the receipt grammar's why/cost lines.
    Drop-in signature; rows without the new fields render byte-identically."""
    base = tell_surface.render_receipt(acted_row, now=now)
    if not base:
        return base
    return _insert_grammar(base, acted_row or {})


def receipt(acted_row: Optional[Dict[str, Any]], *, now: Any = None) -> str:
    """``tell_surface.receipt`` + the receipt grammar. The gating (instant-tell
    rules, canary silence, batch-eligibility ⇒ "") is entirely the germline
    formatter's — this only decorates a receipt that would have been told."""
    base = tell_surface.receipt(acted_row, now=now)
    if not base:
        return ""
    return _insert_grammar(base, acted_row or {})


# --- digest decoration: the compact "— why" clause -------------------------------

_ACTED_ITEM_HEAD_RE = re.compile(r"^ (\d+)\. ")
_ACTED_SECTION_HEAD = "✅ ACTED ("


def _compact(text: str) -> str:
    """One marker-stripped, whitespace-collapsed line — the clause form."""
    return re.sub(r"\s+", " ", _no_marker(text)).strip()


def digest_with_why(text: Optional[str],
                    acted_rows: Optional[List[Dict[str, Any]]]) -> str:
    """``text`` (a rendered act-then-tell digest) with each ACTED item whose
    row carries a stamped ``why`` gaining a compact ``— why: …`` clause on its
    numbered headline line. Called by the unlocked ``tell_digest`` orchestrator
    (tell_surface._acted_section is germline-locked — same decoration pattern
    as the 📈 LOOP readout).

    Discipline: surgery is scoped to the ✅ ACTED section only; ONLY the
    numbered headline lines are appended to — undo lines, indexes, the
    manifest, and the footer are byte-identical; only the journal-stamped
    ``why`` field is used here (a payload/content why already renders as a
    content line, and any item block already showing a why line is skipped —
    no duplication when the germline renderer learns the grammar). Rows
    without a why — and any internal error — leave the text unchanged.

    Rows without a server-minted ``undo_index`` gain no clause BY DESIGN:
    matching by list position could attach a rationale to the WRONG numbered
    line whenever ``build_digest``'s positional fallback and this row list
    diverge — omission is the safe failure direction. The shipped
    ``enqueue_digest`` path always stamps stable indexes (``assign_undo_
    indexes``) before rendering, so its rows always qualify; any other
    orchestrator adopting this helper must stamp indexes first too."""
    if not text or not acted_rows:
        return text or ""
    try:
        why_map: Dict[int, str] = {}
        for r in acted_rows:
            if not isinstance(r, dict) or r.get("quiet"):
                continue
            idx = r.get("undo_index")
            why = r.get("why")
            if isinstance(idx, int) and idx > 0 \
                    and isinstance(why, str) and why.strip():
                why_map[idx] = why
        if not why_map:
            return text
        lines = text.split("\n")
        start = next((i for i, ln in enumerate(lines)
                      if ln.startswith(_ACTED_SECTION_HEAD)), None)
        if start is None:
            return text
        end = start + 1
        while end < len(lines) and lines[end] != "":
            end += 1
        # First pass: item blocks already rendering a why line (a content-dict
        # why today, or the germline grammar tomorrow) must not gain a clause.
        has_why_line: set = set()
        cur: Optional[int] = None
        for i in range(start + 1, end):
            m = _ACTED_ITEM_HEAD_RE.match(lines[i])
            if m:
                cur = int(m.group(1))
                continue
            if cur is not None and lines[i].strip().lower().startswith("why:"):
                has_why_line.add(cur)
        for i in range(start + 1, end):
            m = _ACTED_ITEM_HEAD_RE.match(lines[i])
            if not m:
                continue
            idx = int(m.group(1))
            if idx not in why_map or idx in has_why_line \
                    or " — why: " in lines[i]:
                continue
            clause = tell_surface._clip(_compact(why_map[idx]), _WHY_CAP_DIGEST)
            if clause:
                lines[i] = lines[i] + " — why: " + clause
        return "\n".join(lines)
    except Exception:
        return text                 # decoration must never cost the digest


# --- digest decoration: the evidence-trial citation ------------------------------

# The evidence plane's ONE id alphabet (verifier.TRIAL_ID_RE /
# action_reconcile._MARKER_ID_RE), duplicated as a literal so this module
# stays importable under the system 3.9 interpreter with zero evidence-plane
# imports.  The charset admits no whitespace, no newline, and no reserved
# ``·`` marker char, so a validated id is safe to splice into a Captain-facing
# line by construction; anything else renders NOTHING (never a garbled or
# forged citation).  test_digest_evidence_citation.py pins the two regexes
# against each other.
_EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EVIDENCE_CLAUSE = " — evidence: "


def digest_with_evidence(text: Optional[str],
                         acted_rows: Optional[List[Dict[str, Any]]]) -> str:
    """``text`` (a rendered act-then-tell digest) with each ACTED item whose
    journal row carries the Batch-B ``evidence_trial_id`` stamp gaining a
    compact ``— evidence: <trial-id>`` citation on its numbered headline line
    (evidence design §3 Phase 3 item 4: digests cite the trial the acted
    receipt's evidence lives on). Called by the unlocked ``tell_digest``
    orchestrator right after ``digest_with_why`` — same decoration pattern,
    same discipline, because ``tell_surface._acted_section`` is
    germline-locked.

    Discipline (inherited from ``digest_with_why``, each rule load-bearing):
    surgery is scoped to the ✅ ACTED section; ONLY numbered headline lines
    are appended to; matching keys on the server-minted ``undo_index`` NEVER
    list position (positional matching can bind the citation to the WRONG
    line); a row without the stamp — every pre-evidence journal row — gains
    no clause and renders byte-identically (an honest gap, never a fabricated
    citation); an id that fails the evidence-plane alphabet renders nothing
    (never a garbled id); the decoration is idempotent (a line already
    carrying the clause is skipped, so a future germline renderer can absorb
    the grammar without double-rendering); any internal error returns the
    text unchanged — decoration never costs the digest.

    The citation is a bare trial id — context for the Captain's own
    ``evidence-read.sh <trial-id>`` / dashboard lookup. It is not an
    aggregate, not a score, and carries no evidence CONTENT (never-a-score
    and untrusted-observations doctrines are untouched)."""
    if not text or not acted_rows:
        return text or ""
    try:
        id_map: Dict[int, str] = {}
        for r in acted_rows:
            if not isinstance(r, dict) or r.get("quiet"):
                continue
            idx = r.get("undo_index")
            trial = r.get("evidence_trial_id")
            if isinstance(idx, int) and idx > 0 \
                    and isinstance(trial, str) \
                    and _EVIDENCE_ID_RE.fullmatch(trial):
                id_map[idx] = trial
        if not id_map:
            return text
        lines = text.split("\n")
        start = next((i for i, ln in enumerate(lines)
                      if ln.startswith(_ACTED_SECTION_HEAD)), None)
        if start is None:
            return text
        end = start + 1
        while end < len(lines) and lines[end] != "":
            end += 1
        for i in range(start + 1, end):
            m = _ACTED_ITEM_HEAD_RE.match(lines[i])
            if not m:
                continue
            idx = int(m.group(1))
            if idx not in id_map or _EVIDENCE_CLAUSE in lines[i]:
                continue
            lines[i] = lines[i] + _EVIDENCE_CLAUSE + id_map[idx]
        return "\n".join(lines)
    except Exception:
        return text                 # decoration must never cost the digest


# --- the unlocked write seam: why/cost enrichment onto journal rows ---------------

def stamp_journal_why(pid: str, why: Any, *,
                      cost: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Append why/cost ENRICHMENT rows onto a pid's still-executed journal
    rows — the interim unlocked carry of the proposing card's rationale onto
    the acted receipt, for dispatch orchestrators that hold the stored record
    (its ``situation``) at delivery time.

    Mechanics: for each executed row of ``pid`` not already carrying the
    field, append ``{**row, "why": …[, "cost": …]}`` via
    ``action_undo.journal_step`` — SAME jid, SAME ts, so ``_read_journal``'s
    last-write-wins collapse surfaces the enriched row while any LATER
    status row (a reversal) still supersedes it. The journal's write-time
    stamp inside the executor is the real fix (germline handback); this seam
    is additive and honest: empty why + no valid cost ⇒ stamps NOTHING
    (never invent), a malformed cost dict is dropped (never a fabricated
    number), and per-row journal trouble is counted, never raised."""
    clean = str(why or "").strip()[:_WHY_STORE_CAP]
    vcost = _valid_cost(cost)
    out: Dict[str, Any] = {"stamped": 0, "jids": [], "errors": []}
    if not clean and vcost is None:
        out["skipped"] = "no why and no valid cost — never invent"
        return out
    try:
        # Lazy import — the journal owner is germline; this module never
        # hard-depends on it at load time (house rule for cross-module seams).
        from framework.frontdoor import action_undo
        rows = action_undo._read_journal(pid=str(pid))
    except Exception as e:  # noqa: BLE001 — a broken journal read stamps nothing
        out["errors"].append(str(e)[:120])
        return out
    for row in rows:
        if row.get("status") != "executed":
            continue                # reversed/dead-letter rows keep their story
        enriched = dict(row)
        changed = False
        if clean and not (isinstance(row.get("why"), str)
                          and row["why"].strip()):
            enriched["why"] = clean
            changed = True
        if vcost is not None and _valid_cost(row.get("cost")) is None:
            enriched["cost"] = vcost
            changed = True
        if not changed:
            continue
        try:
            action_undo.journal_step(enriched)
            out["stamped"] += 1
            out["jids"].append(row.get("jid"))
        except Exception as e:  # noqa: BLE001 — enrichment is best-effort
            out["errors"].append(str(e)[:120])
    return out
