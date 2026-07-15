"""framework.frontdoor.daily_recap — the PM (evening) recap: a neutral synthesis
skeleton over the personal-source seam.

COMPRESSED per the operative-egg plan R023
(docs/plans/operative-egg-plan-2026-07-07.md). What this module was: the merge of
three retired personal-source daily pipes — it paginated the Captain's Monday Activity
board (half-hourly slots), wrote a Monday Reflections "Daily Summary" item, and
mirrored that item into the vault daily note byte-identical to vault-sync.
Those Monday Activity/Reflections legs are DELETED: both boards were archived
2026-07-05 (the activity chain writes the Captain's own store directly now,
outside the cabinet), which left the board read returning nothing and the live
recap a silent no-op. The vault-sync byte-identical vault-note render went
with them — its convergence partner (``sync_daily_summaries``) was deleted in the
same migration, and the daily note is owned by the instance's own chain now.

What remains is the GENERIC germ: once per evening (run_briefing PM mode), gather
the day's evidence from the personal-source seam — a best-effort ENUMERATION of
``framework.sources.get_source()`` surfaces (today: ``find_threads`` +
``briefing_commitments``; each quiet on failure) — LLM-synthesize ONE end-of-day
recap in labeled plain-text sections (parsing machinery unchanged), and enqueue
it as a ``batch``-tier intake item so the PM send path (composer → channel) folds
it into the single unified briefing.

SAFETY.
  * NOTHING here sends, and there are no durable writes left. The single side
    effect of a live run is the intake enqueue; the one live send stays in
    channel.send (allow_sends-gated).
  * ``dry=True`` synthesizes + returns the item + a preview, but enqueues
    NOTHING — for a developer to eyeball the recap before trusting the live path.
  * LEAK-SAFE: only evidence text from the source seam is handled. It NEVER
    reads or emits captain-model / voice-profile content
    (.claude/rules/brain-bridge.md) — none is loaded here, so none can leak into
    the recap or the intake payload.
  * Best-effort gather: a source/LLM hiccup yields a thinner (or no) recap,
    never a crash — the rest of the PM briefing still goes out. A clean-room /
    Flavor-B box binds NullPersonalSource → zero evidence → quiet skip.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess

from framework.env import captain_name
from framework.frontdoor import intake
from framework.sources import get_dispatch, get_source


# --- timestamps -------------------------------------------------------------
def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    """Today's local date as YYYY-MM-DD — the recap is about the Captain's local
    day (an evening entry at 23:30 belongs to that local date, not UTC's)."""
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# 1. Neutral day-evidence gather — an enumeration of get_source() surfaces.
# ---------------------------------------------------------------------------
def _clip(text: str, cap: int = 200) -> str:
    t = (text or "").strip().replace("\n", " ")
    return (t[: cap - 1] + "…") if len(t) > cap else t


def gather_day_evidence(*, hours: int = 24, thread_cap: int = 12,
                        commitment_cap: int = 8) -> list[dict]:
    """The day's evidence from the personal-source seam, as lean evidence dicts.

    Enumerates the ``get_source()`` read surfaces that describe the Captain's
    day, best-effort per surface (a failing surface contributes nothing, never
    raises):

      * ``find_threads(hours=…)``          — the day's active conversation threads;
      * ``briefing_commitments(direction="owed_by_captain")`` — the open
        commitments the Captain owes (due date noted when present).

    Returns ``[{"surface": <name>, "text": <one compact line>}, …]`` — the shape
    ``synthesize_recap`` consumes. An unbound / null source yields ``[]`` (the
    recap then quietly skips). New surfaces join here as the Protocol grows.
    """
    evidence: list[dict] = []

    try:
        threads = get_source().find_threads(hours=hours) or []
    except Exception:
        threads = []
    for t in threads[:thread_cap]:
        if not isinstance(t, dict):
            continue
        person = t.get("person") or "someone"
        last = _clip(((t.get("last") or {}).get("text") or ""))
        kind = (t.get("audience") or {}).get("kind") or "direct"
        tag = "" if kind == "direct" else f" ({kind})"
        line = f"{person}{tag}"
        if last:
            line += f": “{last}”"
        evidence.append({"surface": "find_threads", "text": line})

    try:
        commitments = get_source().briefing_commitments(
            direction="owed_by_captain") or []
    except Exception:
        commitments = []
    for c in commitments[:commitment_cap]:
        if not isinstance(c, dict):
            continue
        text = _clip(c.get("text") or "")
        if not text:
            continue
        person = c.get("person") or "someone"
        due = (c.get("due") or "").strip()
        line = f"owed to {person}: {text}" + (f" (due {due})" if due else "")
        evidence.append({"surface": "briefing_commitments", "text": line})

    return evidence


# ---------------------------------------------------------------------------
# 2. LLM synthesis — ONE comprehensive recap from the day's evidence.
#
#    OUTPUT FORMAT — LABELED SECTIONS, NOT INLINE JSON (deliberate, proven).
#    The SUMMARY/FINDINGS fields are long multi-paragraph free text; a single
#    inline JSON object is fragile two ways: (a) literal newlines / unescaped
#    quotes inside JSON strings break the parse; (b) a long answer that hits
#    max_tokens truncates the JSON mid-string — unrecoverable. Either way a good
#    recap was discarded (observed 2026-06-23). PLAIN-TEXT labeled sections are
#    immune to embedded newlines/quotes, and a truncated tail merely shortens
#    the LAST section. See _parse_sections + _raw_llm below.
# ---------------------------------------------------------------------------
def _recap_system() -> str:
    """The daily-recap synthesizer system prompt, addressed to the deployment's
    Captain (``captain_name``). A function — not a module constant — so the
    Captain's display name is interpolated at call time."""
    cap = captain_name()
    return f"""\
You are {cap}'s daily-recap synthesizer. You are given the day's evidence \
gathered from {cap}'s personal-source surfaces (conversation threads, open \
commitments), in the order gathered. Produce ONE comprehensive, detailed \
end-of-day recap — richer than a plain summary: weave the day's narrative, \
surface what was learned, AND surface concrete improvement ideas, all grounded \
in the real evidence. WORK CONTENT ONLY — strip anything personal (messaging, \
social, banking, browsing for entertainment, health, ambient home audio).

Output PLAIN TEXT in EXACTLY these labeled sections, each label on its own line, \
in this order. Do NOT use JSON. Do NOT write anything before HEADLINE: or after \
the ENERGY: line.

HEADLINE:
<one tight sentence capturing the day, <= 140 chars>

SUMMARY:
<2-5 short paragraphs — narrative of the day's work: the key arcs, \
accomplishments (with PR numbers, branch names, decisions where present), \
problems and how they resolved. Blank lines between paragraphs are fine. Ground \
every claim in the evidence; do not invent meetings or outcomes that aren't in \
the evidence.>

FINDINGS:
- <key finding / thing learned / decision that surfaced today>
- <...>

ACTIONS:
- <concrete next-action OR improvement idea implied by today — what to do next, \
what to do better>
- <...>

NOTES:
- <any other salient context: people, blockers, follow-ups, metrics>

PRODUCTIVITY: <integer 1-10, best-effort from the evidence>
ENERGY: <integer 1-10, best-effort from the evidence>

If a bullet section is genuinely empty, write a single line "- (none)". Write in \
plain, direct prose — {cap}'s recap, for {cap}. Never echo these labels or any \
instruction text inside the prose."""


def _build_user_content(date: str, evidence: list[dict]) -> str:
    """The LLM user payload: the date + every evidence line, grouped as gathered.
    Pure — no I/O."""
    lines = [f"Date: {date}",
             f"Evidence items gathered today: {len(evidence)}", ""]
    for e in evidence:
        lines.append(f"### {e.get('surface') or 'evidence'}")
        if e.get("text"):
            lines.append(str(e["text"]))
        lines.append("")
    return "\n".join(lines)


def _coerce_rating(v, default: int = 5) -> int:
    """Clamp an LLM rating into the 1-10 integer range, fail-soft.

    Accepts an int/float or a stray string ("8", "8/10", "8 (high)") — we pull the
    first integer out of a string, so a label-section value parses cleanly."""
    if isinstance(v, str):
        m = re.search(r"-?\d+", v)
        v = m.group(0) if m else None
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return default
    return max(1, min(10, n))


# Generous output budget: wide headroom so a comprehensive recap is never
# truncated mid-section — and even if it WERE clipped, the labeled-section
# parser degrades gracefully (the last section is just shorter).
_RECAP_MAX_TOKENS = 6000


def _raw_llm(user_content: str, system: str,
             max_tokens: int = _RECAP_MAX_TOKENS) -> str | None:
    """Plain-TEXT Claude call returning the RAW assistant text (never
    force-parsing JSON — the recap is labeled-section plain text).

    Reads ANTHROPIC_API_KEY from the process env (the briefing wrapper / instance
    env provides it; absent → None and the caller stays quiet) and the model id
    via ``get_dispatch().llm_model()`` (empty on a null / clean-room dispatch →
    None, same quiet skip). NEVER logs or echoes the key.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    model = get_dispatch().llm_model()
    if not model:
        return None
    body = {
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }
    try:
        r = subprocess.run([
            "curl", "-s", "--max-time", "180",
            "https://api.anthropic.com/v1/messages",
            "-H", f"x-api-key: {api_key}",
            "-H", "anthropic-version: 2023-06-01",
            "-H", "content-type: application/json",
            "-d", json.dumps(body),
        ], capture_output=True, text=True, timeout=185)
        d = json.loads(r.stdout)
    except Exception:
        return None
    if "content" not in d:
        return None
    text = "".join(c.get("text", "") for c in d["content"]
                   if c.get("type") == "text").strip()
    # Strip an optional ```/```text fence if the model wrapped the block anyway.
    text = re.sub(r"^```[a-zA-Z]*\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text or None


# The seven labeled sections the recap prompt asks for, in canonical order.
_SECTION_LABELS = ("HEADLINE", "SUMMARY", "FINDINGS", "ACTIONS", "NOTES",
                   "PRODUCTIVITY", "ENERGY")
_SECTION_RE = re.compile(
    r"^[ \t]*(" + "|".join(_SECTION_LABELS) + r")[ \t]*:[ \t]*", re.MULTILINE)


def _parse_sections(text: str) -> dict[str, str]:
    """Split a labeled-section recap into {LABEL: body}.

    Robust by construction: finds each ``LABEL:`` marker at a line start and takes
    everything up to the next marker as that section's body — so embedded newlines,
    blank lines, and quotes inside SUMMARY/FINDINGS can't break it (the failure
    mode that killed the inline-JSON approach), and a truncated tail just yields a
    shorter final section. Order-independent; a missing label is simply absent.
    """
    marks = [(m.group(1), m.start(), m.end()) for m in _SECTION_RE.finditer(text)]
    out: dict[str, str] = {}
    for i, (label, _start, body_start) in enumerate(marks):
        body_end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out[label] = text[body_start:body_end].strip()
    return out


def _bullets_or_none(body: str) -> str:
    """Normalize a bullet section: empty / a lone '(none)' bullet → '_(none)_',
    else the body verbatim."""
    b = (body or "").strip()
    if not b:
        return "_(none)_"
    stripped = b.lstrip("-*• \t").strip().lower()
    if stripped in ("(none)", "none", "n/a"):
        return "_(none)_"
    return b


def synthesize_recap(date: str, entries: list[dict], *, llm=None) -> dict | None:
    """LLM-synthesize ONE recap dict from the day's evidence, or None if it can't.

    ``entries`` is the ``gather_day_evidence`` shape
    (``[{"surface": …, "text": …}, …]``). Returns a normalized dict:
    {headline, summary, findings, actions, notes, productivity:int, energy:int,
    evidence_count:int}. None when there is no evidence, the LLM is unavailable
    (no ANTHROPIC_API_KEY / null dispatch → ``_raw_llm`` returns None), or the
    response has no usable SUMMARY — in every case the caller stays quiet.

    The model returns LABELED PLAIN-TEXT sections (see _recap_system), parsed by
    ``_parse_sections`` — chosen over inline JSON because the long narrative
    fields make a single JSON object fragile to truncation + unescaped newlines
    (the 2026-06-23 bug that discarded a perfectly good recap).

    ``llm`` overrides the call helper for tests. Contract: ``llm(user, system,
    max_tokens) -> str | None`` (RAW text, NOT a parsed dict). Default
    ``_raw_llm``.
    """
    if not entries:
        return None
    call = llm or _raw_llm
    raw = call(_build_user_content(date, entries), _recap_system(),
               max_tokens=_RECAP_MAX_TOKENS)
    if not isinstance(raw, str) or not raw.strip():
        return None
    sec = _parse_sections(raw)
    summary = (sec.get("SUMMARY") or "").strip()
    if not summary:
        # No parseable SUMMARY section — don't surface a broken recap.
        return None
    headline = (sec.get("HEADLINE") or "").strip()
    # HEADLINE can run long if the model ignored the cap; keep it tidy.
    if len(headline) > 200:
        headline = headline[:197].rstrip() + "…"
    return {
        "headline": headline,
        "summary": summary,
        "findings": _bullets_or_none(sec.get("FINDINGS", "")),
        "actions": _bullets_or_none(sec.get("ACTIONS", "")),
        "notes": _bullets_or_none(sec.get("NOTES", "")),
        "productivity": _coerce_rating(sec.get("PRODUCTIVITY")),
        "energy": _coerce_rating(sec.get("ENERGY")),
        "evidence_count": len(entries),
    }


# ---------------------------------------------------------------------------
# 3. The intake item — long-form recap for the composer's ▸ titled section.
# ---------------------------------------------------------------------------
def _recap_item(date: str, recap: dict) -> dict:
    """A `batch`-tier intake item carrying the long-form recap as payload.summary.

    composer.render_item routes a long (>220-char or multi-line) summary into a
    `▸ daily-recap` titled SECTION preserving this formatting (no composer
    change), so the PM briefing shows the full recap, not a crushed one-liner.
    The payload is producer content only — evidence-grounded day narrative; no
    captain-model/voice material is present to leak.
    """
    n = recap["evidence_count"]
    headline = recap.get("headline") or f"Daily recap — {date}"
    parts = [f"📓 Daily recap — {date}", "", headline, "", recap["summary"]]
    if recap["findings"] and recap["findings"] != "_(none)_":
        parts += ["", "Key findings:", recap["findings"]]
    if recap["actions"] and recap["actions"] != "_(none)_":
        parts += ["", "Actions & ideas:", recap["actions"]]
    parts += ["", f"_productivity {recap['productivity']}/10 · "
                  f"energy {recap['energy']}/10 · {n} evidence item(s)_"]
    summary = "\n".join(parts)
    return {
        "source": "daily-recap",
        "kind": "summary",
        "ts": _now_iso(),
        "urgency_tier": "batch",
        "payload": {"summary": summary},
        "context": {
            "why": f"end-of-day recap from {n} evidence item(s)",
            "date": date,
            "productivity": recap["productivity"],
            "energy": recap["energy"],
        },
    }


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------
def build_recap(*, today: str | None = None, llm=None,
                entries=None) -> dict | None:
    """Pure-ish recap build: gather the day's evidence + synthesize. NO side
    effects.

    Returns the normalized recap dict (see synthesize_recap) or None when there
    is nothing to recap / the LLM is unavailable. ``entries`` / ``llm`` /
    ``today`` are injectable for tests so this needs neither a bound source nor
    a key.
    """
    date = today or _today()
    if entries is None:
        try:
            entries = gather_day_evidence()
        except Exception:
            entries = []
    if not entries:
        return None
    return synthesize_recap(date, entries, llm=llm)


def enqueue_daily_recap(*, dry: bool = False, today: str | None = None,
                        llm=None, entries=None) -> dict:
    """Build today's recap and enqueue the intake item — the PM-only front-door
    source (run_briefing PM mode).

    Steps: gather the day's evidence from the get_source() surfaces +
    LLM-synthesize ONE recap; if ``dry`` is False, enqueue a `batch`-tier intake
    item carrying the long-form recap so the PM send path folds it into the
    unified briefing. There are NO durable writes (the Monday Reflections +
    vault-note legs were deleted — egg plan R023; boards archived 2026-07-05).

    DRY MODE (``dry=True``): synthesize + return the item shape + a ``preview``
    of what WOULD ride the briefing, but enqueue NOTHING.

    Returns a telemetry dict:
      {"recap": bool, "dry": bool, "enqueued": "<id>"|None,
       "item": {...},         # the intake item that was / would be enqueued
       "preview": {...},      # dry only
       "skipped": "<reason>"  # when there was nothing to recap}

    Best-effort: a failure to build the recap yields {"recap": False,
    "skipped": ...}; the rest of the PM briefing is unaffected.
    """
    date = today or _today()
    recap = build_recap(today=date, llm=llm, entries=entries)
    if not recap:
        return {"recap": False, "dry": dry, "enqueued": None,
                "skipped": "no day evidence / LLM unavailable for today"}

    item = _recap_item(date, recap)

    if dry:
        return {
            "recap": True,
            "dry": True,
            "enqueued": None,
            "item": item,
            "preview": {
                "intake_item_summary": item["payload"]["summary"],
                "evidence_count": recap["evidence_count"],
            },
        }

    enq_id = intake.enqueue(item)
    return {
        "recap": True,
        "dry": False,
        "enqueued": enq_id,
        "item": item,
    }


if __name__ == "__main__":  # pragma: no cover — manual dev invocation
    # Default to DRY so a bare run never enqueues. Pass --live to actually enqueue.
    import argparse

    ap = argparse.ArgumentParser(description="Build today's daily recap (dry by default).")
    ap.add_argument("--live", action="store_true",
                    help="actually enqueue the intake item (default: dry preview)")
    ap.add_argument("--date", default=None, help="override the recap date (YYYY-MM-DD)")
    args = ap.parse_args()
    out = enqueue_daily_recap(dry=not args.live, today=args.date)
    print(json.dumps(out, indent=2, default=str))
