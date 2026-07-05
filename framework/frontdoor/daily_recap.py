"""framework.frontdoor.daily_recap — the PM (evening) front-door INTAKE SOURCE.

The merge of the three overlapping screenpipe daily pipes (monday-daily-summary +
monday-daily-insights + monday-daily-improvements) into ONE richer pass, run from
the Chair's 19:30 briefing. It:

  1. pulls today's half-hourly entries off the Captain's Monday Activity board (the rich
     System-1 feeder — the same board the three daily pipes read);
  2. LLM-synthesizes ONE comprehensive daily recap (narrative + key findings +
     actions/improvement-ideas + productivity/energy metrics) in a single pass,
     instead of three fragmented passes over the same data;
  3. writes that recap to BOTH durable surfaces — the Monday Reflections board
     (a "Daily Summary" item, same board/group/schema as
     monday-daily-summary/commit.py) AND the canonical vault daily note
     `1-Daily/YYYY-MM-DD.md` (byte-identical to obsidian-sync's
     sync_daily_summaries, so obsidian-sync's next run hash-matches + skips);
  4. returns a `batch`-tier intake item carrying the long-form recap, so the
     PM send path (composer → channel) folds it into the ONE unified Telegram
     briefing alongside the morning_synthesis signals.

ARCHITECTURE FIT. This mirrors morning_synthesis's shape (gather real signal →
return canonical intake items) but adds the durable Monday+vault side-effects the
retired pipes used to own. Per the cohesive architecture (docs/cabinet-
architecture-cohesive-2026-06-22.md §5): screenpipe is System 1 (the half-hourly
feeder + the vault it persists to), the cabinet is System 2 (this synthesis + the
single voice). The three screenpipe daily pipes are retired CONSERVATIVELY, in a
separate step, only after this proves — NOT here.

IDEMPOTENCY. Re-running on the same day UPDATES, never duplicates: the Monday item
is found-or-created by date; the vault note is written-if-changed (sha256). So the
PM briefing can fire (or be re-run) repeatedly without churn.

SAFETY.
  * NOTHING here sends. It only enqueues to the durable intake and writes to the Captain's
    OWN Monday board + his OWN local vault. The single live send stays in
    channel.send (allow_sends-gated).
  * ``dry=True`` synthesizes + returns the item + a preview of what WOULD be
    written, but performs ZERO side-effects (no Monday write, no vault write) — for
    a developer to inspect the recap before trusting the live path.
  * LEAK-SAFE: this module only handles the Captain's activity-summary text. It NEVER
    reads or emits nate_model / voice-profile content (.claude/rules/brain-
    bridge.md) — none is loaded here, so none can leak into the recap, the Monday
    item, the vault note, or the intake payload.
  * Best-effort gather: a Monday/LLM hiccup yields a thinner (or no) item, never a
    crash — the rest of the PM briefing still goes out.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from framework.env import captain_name
from framework.frontdoor import intake

# screenpipe libs live outside the cabinet tree. We reach them on sys.path the
# same way framework.acting.screenpipe_adapter does — sp_lib (Monday GraphQL
# helpers + board CONFIG) and commitments_lib (the battle-tested curl-to-
# Anthropic LLM helper the screenpipe pipes already use). Imported lazily inside
# the functions so the cabinet's own unit suite (which mocks these seams) need
# not have screenpipe installed.
_PIPES = os.path.expanduser("~/.screenpipe/pipes")
_SHARED = os.path.join(_PIPES, "_shared")
for _p in (_PIPES, _SHARED):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# --- timestamps -------------------------------------------------------------
def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    """Today's local date as YYYY-MM-DD.

    The Activity board's date column + the vault daily-note filename are both in
    the Captain's local day (a half-hour slot at 23:30 belongs to that local date), so we
    use the local calendar date, NOT UTC — matching how the screenpipe pipes
    (which run on the Captain's Mac in local time) stamp the slots.
    """
    return datetime.date.today().isoformat()


# --- screenpipe seams (lazy) ------------------------------------------------
def _sp():
    """sp_lib with its env loaded (Monday token, board CONFIG). Loading env is
    idempotent + cheap; we do it on every access so a long-lived officer session
    re-reads a rotated token."""
    import sp_lib  # noqa: PLC0415 — lazy screenpipe-only dep
    sp_lib.load_env(_SHARED)
    return sp_lib


def _cl():
    import commitments_lib as cl  # noqa: PLC0415 — lazy screenpipe-only dep
    return cl


# ---------------------------------------------------------------------------
# 1. Pull today's half-hourly entries off the Activity board.
#    Reuses monday-daily-summary/prepare.py's cursor pagination + cv helpers.
# ---------------------------------------------------------------------------
def _cv(item: dict, col_id: str) -> str:
    """Text of one column on a Monday item (empty string if absent)."""
    for c in item.get("column_values", []):
        if c.get("id") == col_id:
            return c.get("text") or ""
    return ""


def fetch_today_halfhourly(*, today: str | None = None, max_pages: int = 20) -> list[dict]:
    """Today's unchecked half-hourly Activity entries, oldest-first.

    Paginates the Activity board's half-hourly group (board id + group id are an
    integer + a constant from sp_lib.CONFIG — never user input), keeps entries
    whose entry_type is Hourly/Half-Hourly and whose date is ``today``, then sorts
    by hour:minute so the recap reads chronologically. Best-effort: a Monday
    hiccup mid-pagination returns whatever was fetched so far.

    ``today`` is injectable for tests.
    """
    sp = _sp()
    C = sp.CONFIG
    act = C["activity_board"]
    board = act["id"]
    group = act["groups"]["halfhourly"]
    col = act["columns"]
    today = today or _today()

    # --- paginate (mirror prepare.py.fetch_all_hourly) ---
    items: list[dict] = []
    cursor = None
    fields = "id name column_values { id text value }"
    for _ in range(max_pages):
        if cursor:
            q = f'{{ next_items_page(limit:100, cursor:"{cursor}") {{ cursor items {{ {fields} }} }} }}'
            r = sp.monday(q)
            try:
                data = r["data"]["next_items_page"]
            except Exception:
                break
        else:
            q = (f'{{ boards(ids:[{board}]) {{ groups(ids:["{group}"]) {{ '
                 f'items_page(limit:100) {{ cursor items {{ {fields} }} }} }} }} }}')
            r = sp.monday(q)
            try:
                data = r["data"]["boards"][0]["groups"][0]["items_page"]
            except Exception:
                break
        items.extend(data.get("items", []))
        cursor = data.get("cursor")
        if not cursor:
            break

    # --- filter to today's half-hourly slots ---
    todays: list[dict] = []
    for it in items:
        if _cv(it, col["entry_type"]) not in ("Hourly", "Half-Hourly"):
            continue
        if _cv(it, col["date"])[:10] != today:
            continue
        todays.append(it)

    # --- chronological order (hour, then minute) ---
    def _slot_key(it: dict) -> tuple[int, int]:
        h = _cv(it, col["hour"]).split(".")[0]
        m = _cv(it, col["minute"]) or "0"
        try:
            return (int(h or 0), int(m or 0))
        except ValueError:
            return (0, 0)

    todays.sort(key=_slot_key)
    return todays


def _compact_slots(entries: list[dict]) -> list[dict]:
    """Reduce raw Monday items to the lean fields the LLM needs (one dict per
    half-hour slot). Keeps the human-readable activity content, drops board
    plumbing. Pure — no I/O — so it is trivially testable."""
    sp = _sp()
    col = sp.CONFIG["activity_board"]["columns"]
    slots: list[dict] = []
    for it in entries:
        h = _cv(it, col["hour"]).split(".")[0] or "?"
        m = (_cv(it, col["minute"]) or "0").zfill(2)
        slots.append({
            "time": f"{h}:{m}",
            "title": it.get("name", "")[:160],
            "summary": _cv(it, col["activity_summary"]),
            "tasks_actions": _cv(it, col["tasks_actions"]),
            "focus_type": _cv(it, col["focus_type"]),
            "productivity": _cv(it, col["productivity"]),
            "energy": _cv(it, col["energy"]),
            "apps": _cv(it, col["apps"]),
        })
    return slots


# ---------------------------------------------------------------------------
# 2. LLM synthesis — ONE comprehensive recap from all of today's slots.
#    Covers what monday-daily-summary + -insights + -improvements did, in one
#    richer pass.
#
#    OUTPUT FORMAT — LABELED SECTIONS, NOT INLINE JSON (deliberate). The Captain wants
#    the recap "very comprehensive and detailed", so the SUMMARY/FINDINGS fields
#    are long multi-paragraph free text. Asking the model to RETURN a single
#    inline JSON object with that text crammed into string values is fragile two
#    ways: (a) the model intermittently emits literal newlines / unescaped quotes
#    inside the JSON strings → json.loads fails AND commitments_lib's balanced-
#    brace fallback fails too; (b) a long "comprehensive" answer can exceed
#    max_tokens → the JSON is truncated mid-string → unrecoverable. Either way the
#    WHOLE recap was being discarded (observed 2026-06-23: good prose generated,
#    then dropped). The proven screenpipe pipe (monday-daily-summary/pipe.md)
#    sidesteps this by never parsing model-returned inline JSON — its agent writes
#    the file via heredoc, controlling escaping at write time. We can't do that in
#    a one-shot call, so we use the same spirit: PLAIN-TEXT labeled sections parsed
#    by splitting on the labels. Section-splitting is immune to embedded newlines /
#    quotes, and a truncated tail merely shortens the LAST section instead of
#    nuking the recap. See _parse_sections + _raw_llm below.
# ---------------------------------------------------------------------------
def _recap_system() -> str:
    """The daily-recap synthesizer system prompt, addressed to the deployment's
    Captain (``captain_name``). A function — not a module constant — so the
    Captain's display name is interpolated at call time; renders byte-identical
    to the prior literal on a deployment whose ``captain_name`` is unchanged."""
    cap = captain_name()
    return f"""\
You are {cap}'s daily-recap synthesizer. You are given EVERY half-hour activity \
slot captured for {cap} today (titles + summaries + tasks + focus/productivity/\
energy signals), in chronological order. Produce ONE comprehensive, detailed \
end-of-day recap that REPLACES three older overlapping passes (a daily summary, \
a daily insights pass, and a daily improvements pass) — so be RICHER than a plain \
summary: weave the full narrative, surface what was learned, AND surface concrete \
improvement ideas, all grounded in the real evidence. WORK CONTENT ONLY — strip \
anything personal (messaging, social, banking, browsing for entertainment, \
health, ambient home audio).

Output PLAIN TEXT in EXACTLY these labeled sections, each label on its own line, \
in this order. Do NOT use JSON. Do NOT write anything before HEADLINE: or after \
the ENERGY: line.

HEADLINE:
<one tight sentence capturing the day, <= 140 chars>

SUMMARY:
<2-5 short paragraphs — chronological narrative of the day's work: how it \
started, the key arcs, accomplishments (with PR numbers, branch names, decisions \
where present), problems and how they resolved, the energy/focus trajectory. \
Blank lines between paragraphs are fine. Ground every claim in the slots; do not \
invent meetings or outcomes that aren't in the evidence.>

FINDINGS:
- <key finding / thing learned / decision that surfaced today>
- <...>

ACTIONS:
- <concrete next-action OR improvement idea implied by today — what to do next, \
what to do better>
- <...>

NOTES:
- <any other salient context: people, blockers, follow-ups, metrics (active \
hours, deep-work hours, top tools)>

PRODUCTIVITY: <integer 1-10, weighted by hours worked>
ENERGY: <integer 1-10, weighted by hours worked>

If a bullet section is genuinely empty, write a single line "- (none)". Write in \
plain, direct prose — {cap}'s recap, for {cap}. Never echo these labels or any \
instruction text inside the prose."""


def _build_user_content(date: str, slots: list[dict]) -> str:
    """The LLM user payload: the date + every slot rendered compactly. Pure."""
    lines = [f"Date: {date}", f"Half-hour slots captured today: {len(slots)}", ""]
    for s in slots:
        lines.append(f"### {s['time']} — {s['title']}")
        if s.get("focus_type"):
            lines.append(f"focus: {s['focus_type']}"
                         + (f" · productivity {s['productivity']}" if s.get("productivity") else "")
                         + (f" · energy {s['energy']}" if s.get("energy") else ""))
        if s.get("summary"):
            lines.append(s["summary"])
        if s.get("tasks_actions"):
            lines.append(f"tasks/actions: {s['tasks_actions']}")
        if s.get("apps"):
            lines.append(f"apps: {s['apps']}")
        lines.append("")
    return "\n".join(lines)


def _coerce_rating(v, default: int = 5) -> int:
    """Clamp an LLM rating into Monday's 1-10 integer range, fail-soft.

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


# Generous output budget. The model writes ~1.6-2k tokens for a busy 30-slot day
# at end_turn; this ceiling leaves wide headroom so a "very comprehensive" recap
# is never truncated mid-section. Even if it ever WERE clipped, the labeled-
# section parser degrades gracefully (the last section is just shorter) rather
# than discarding the whole recap the way a truncated inline-JSON object did.
_RECAP_MAX_TOKENS = 6000


def _raw_llm(user_content: str, system: str,
             max_tokens: int = _RECAP_MAX_TOKENS) -> str | None:
    """Plain-TEXT Claude call — mirrors commitments_lib.call_llm's curl exactly
    (same model, same x-api-key header, same anthropic-version, same --max-time),
    but returns the RAW assistant text instead of force-parsing JSON. That's the
    whole point: the recap is labeled-section plain text, not JSON, so a JSON
    parser is the wrong tool. No ANTHROPIC_API_KEY → None (caller stays quiet).

    Reads the key from the env that sp_lib.load_env populated (screenpipe's
    _shared/.env). NEVER logs or echoes the key.
    """
    cl = _cl()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    body = {
        "model": cl.LLM_MODEL, "max_tokens": max_tokens, "system": system,
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
    else the body verbatim. Keeps the vault/Monday '_(none)_' convention."""
    b = (body or "").strip()
    if not b:
        return "_(none)_"
    stripped = b.lstrip("-*• \t").strip().lower()
    if stripped in ("(none)", "none", "n/a"):
        return "_(none)_"
    return b


def synthesize_recap(date: str, entries: list[dict], *, llm=None) -> dict | None:
    """LLM-synthesize ONE recap dict from today's slots, or None if it can't.

    Returns a normalized dict: {headline, summary, findings, actions, notes,
    productivity:int, energy:int, slot_count:int}. None when there are no slots,
    the LLM is unavailable (no ANTHROPIC_API_KEY → ``_raw_llm`` returns None), or
    the response has no usable SUMMARY — in every case the caller stays quiet.

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
    slots = _compact_slots(entries)
    call = llm or _raw_llm
    raw = call(_build_user_content(date, slots), _recap_system(),
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
        "slot_count": len(slots),
    }


# ---------------------------------------------------------------------------
# 3a. Monday Reflections "Daily Summary" item — same board/group/schema as
#     monday-daily-summary/commit.py. Find-or-create by date (idempotent).
# ---------------------------------------------------------------------------
def _find_existing_daily(sp, board_id: int, group_id: str, date_col: str,
                         date: str) -> str | None:
    """Item id of an existing Daily-Summary on this date in the daily group, or
    None. Lets a re-run UPDATE instead of creating a duplicate (the same
    find-or-create discipline prepare.py uses)."""
    q = (f'{{ boards(ids:[{board_id}]) {{ groups(ids:["{group_id}"]) {{ '
         f'items_page(limit:100) {{ items {{ id column_values {{ id text }} }} }} }} }} }}')
    r = sp.monday(q)
    try:
        items = r["data"]["boards"][0]["groups"][0]["items_page"]["items"]
    except Exception:
        return None
    for it in items:
        if _cv(it, date_col)[:10] == date:
            return it["id"]
    return None


def _write_monday(date: str, recap: dict) -> dict:
    """Create or update the Reflections Daily-Summary item for ``date``.

    Same board (5096013783), group (daily), Entry Type ("Daily Summary"), and
    column schema as monday-daily-summary/commit.py — so this is a drop-in for
    the retired pipe's Monday write. Returns {"action": create|update|error,
    "item_id": id|None, "url": ...}. Best-effort: an API error is reported in the
    return, never raised.
    """
    sp = _sp()
    ref = sp.CONFIG["reflections_board"]
    board_id = ref["id"]
    group_id = ref["groups"]["daily"]
    col = ref["columns"]

    col_vals = {
        col["entry_type"]: {"label": "Daily Summary"},
        col["date"]: {"date": date},
        col["summary"]: {"text": recap["summary"][:6000]},
        col["findings"]: {"text": recap["findings"][:4000]},
        col["actions"]: {"text": recap["actions"][:2000]},
        col["notes"]: {"text": recap["notes"][:4000]},
        col["productivity"]: {"rating": recap["productivity"]},
        col["energy"]: {"rating": recap["energy"]},
    }
    name = f"{date} — Daily Summary"[:255]

    existing = _find_existing_daily(sp, board_id, group_id, col["date"], date)
    if existing:
        r = sp.monday_update_item(existing, board_id, col_vals)
        action, item_id = "update", existing
    else:
        r = sp.monday_create_item(board_id, group_id, name, col_vals)
        try:
            item_id = r["data"]["create_item"]["id"]
        except Exception:
            item_id = None
        action = "create"

    url = (f"https://step-network.monday.com/boards/{board_id}/pulses/{item_id}"
           if item_id else "")
    if r.get("errors"):
        return {"action": "error", "item_id": item_id, "url": url,
                "errors": str(r["errors"])[:300]}
    return {"action": action, "item_id": item_id, "url": url}


# ---------------------------------------------------------------------------
# 3b. Canonical vault daily note — BYTE-IDENTICAL to obsidian-sync's
#     sync_daily_summaries, so obsidian-sync's next run hash-matches + skips.
# ---------------------------------------------------------------------------
def _vault_path() -> Path:
    return Path(os.environ.get(
        "OBSIDIAN_VAULT_PATH", str(Path.home() / "Obsidian" / "screenpipe-brain")))


def _fence(s) -> str:
    """Escape a string for a YAML double-quoted scalar — matches obsidian-sync."""
    if s is None:
        return ""
    return str(s).replace('"', '\\"')


def _render_frontmatter(d: dict) -> str:
    """Render a dict to YAML frontmatter — a faithful copy of obsidian-sync's
    render_frontmatter, so the bytes match for the daily-note keys we emit."""
    lines = ["---"]
    for k, v in d.items():
        if v is None or v == "":
            lines.append(f"{k}:")
        elif isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                for x in v:
                    lines.append(f"  - {x}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            sv = str(v)
            if any(ch in sv for ch in ":#\n") or sv.startswith(
                    ("-", "[", "{", "&", "*", "!", "|", ">", "%", "@", "`")):
                lines.append(f'{k}: "{_fence(sv)}"')
            else:
                lines.append(f"{k}: {sv}")
    lines.append("---")
    return "\n".join(lines)


def render_vault_note(date: str, recap: dict, monday_id: str | None) -> str:
    """The canonical `1-Daily/YYYY-MM-DD.md` content.

    Frontmatter + body match obsidian-sync.sync_daily_summaries EXACTLY (same
    keys, same order, same section headers, same dataview block, same
    `source: monday-daily-summary`). That byte-for-byte match is the whole point:
    after we write it, obsidian-sync's next 30-min run renders the identical
    string, its sha256 matches, and it SKIPS — no duplicate, no churn. The only
    field that varies from the retired pipe is monday_id (the item WE just
    wrote); obsidian-sync reads that same item back, so they converge.
    """
    ref_id = _sp().CONFIG["reflections_board"]["id"]
    fm = {
        "type": "daily",
        "date": date,
        "productivity": int(recap["productivity"]),
        "energy": int(recap["energy"]),
        "tags": ["daily", "synced"],
        "source": "monday-daily-summary",
        "monday_id": monday_id or "",
    }
    src_line = (
        f"_Source: [Monday item {monday_id}]"
        f"(https://step-network.monday.com/boards/{ref_id}/pulses/{monday_id})_"
        if monday_id else "_Source: (pending Monday sync)_"
    )
    body = [
        _render_frontmatter(fm), "",
        f"# {date} — Daily Summary",
        "",
        src_line,
        "",
        "## Summary",
        recap["summary"] or "_(no summary)_",
        "",
        "## Key findings",
        recap["findings"] or "_(none)_",
        "",
        "## Actions",
        recap["actions"] or "_(none)_",
        "",
        "## Notes",
        recap["notes"] or "_(none)_",
        "",
        "## Meetings on this day",
        "```dataview",
        "TABLE WITHOUT ID file.link AS Meeting, attendees, project",
        'FROM "2-Meetings"',
        f'WHERE date = date("{date}")',
        "```",
        "",
    ]
    return "\n".join(body)


def _write_vault(date: str, content: str) -> dict:
    """Write the daily note if (and only if) its bytes changed (sha256 compare).

    Returns {"action": written|unchanged|skipped, "path": ...}. Skips (never
    creates a stray note) when the vault isn't present/marked — matching
    obsidian-sync's ABORT_NO_VAULT guard.
    """
    vault = _vault_path()
    if not vault.exists() or not (vault / ".obsidian-vault-marker").exists():
        return {"action": "skipped", "path": str(vault), "reason": "no vault marker"}
    path = vault / "1-Daily" / f"{date}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    old_hash = (hashlib.sha256(path.read_bytes()).hexdigest()
                if path.exists() else None)
    if new_hash == old_hash:
        return {"action": "unchanged", "path": str(path)}
    path.write_text(content)
    return {"action": "written", "path": str(path)}


# ---------------------------------------------------------------------------
# 4. The intake item — long-form recap for the composer's ▸ titled section.
# ---------------------------------------------------------------------------
def _recap_item(date: str, recap: dict) -> dict:
    """A `batch`-tier intake item carrying the long-form recap as payload.summary.

    composer.render_item routes a long (>220-char or multi-line) summary into a
    `▸ daily-recap` titled SECTION preserving this formatting (no composer
    change), so the PM briefing shows the full recap, not a crushed one-liner.
    The payload is producer content only — the Captain's own activity narrative; no
    nate_model/voice material is present to leak.
    """
    headline = recap.get("headline") or f"Daily recap — {date}"
    parts = [f"📓 Daily recap — {date}", "", headline, "", recap["summary"]]
    if recap["findings"] and recap["findings"] != "_(none)_":
        parts += ["", "Key findings:", recap["findings"]]
    if recap["actions"] and recap["actions"] != "_(none)_":
        parts += ["", "Actions & ideas:", recap["actions"]]
    parts += ["", f"_productivity {recap['productivity']}/10 · "
                  f"energy {recap['energy']}/10 · {recap['slot_count']} slots_"]
    summary = "\n".join(parts)
    return {
        "source": "daily-recap",
        "kind": "summary",
        "ts": _now_iso(),
        "urgency_tier": "batch",
        "payload": {"summary": summary},
        "context": {
            "why": f"end-of-day recap from {recap['slot_count']} activity slots",
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
    """Pure-ish recap build: fetch today's slots + synthesize. NO side effects.

    Returns the normalized recap dict (see synthesize_recap) or None when there
    is nothing to recap / the LLM is unavailable. ``entries`` / ``llm`` / ``today``
    are injectable for tests so this needs neither Monday nor a key.
    """
    date = today or _today()
    if entries is None:
        try:
            entries = fetch_today_halfhourly(today=date)
        except Exception:
            entries = []
    if not entries:
        return None
    return synthesize_recap(date, entries, llm=llm)


def enqueue_daily_recap(*, dry: bool = False, today: str | None = None,
                        llm=None, entries=None) -> dict:
    """Build today's recap, persist it (Monday + vault), enqueue the intake item.

    The PM-only front-door source. Steps:
      1. fetch today's half-hourly slots + LLM-synthesize ONE recap;
      2. if ``dry`` is False: write the Monday Reflections Daily-Summary item AND
         the canonical vault daily note (both idempotent — re-run updates, never
         duplicates);
      3. enqueue a `batch`-tier intake item carrying the long-form recap so the
         PM send path folds it into the unified briefing.

    DRY MODE (``dry=True``): synthesize + return the item shape + a ``preview`` of
    what WOULD be written to Monday and the vault, but write NOTHING and enqueue
    NOTHING — for a developer to eyeball the recap before trusting the live path.

    Returns a telemetry dict:
      {"recap": bool, "dry": bool, "enqueued": "<id>"|None,
       "monday": {...}|None, "vault": {...}|None,
       "preview": {...}      # dry only
       "item": {...},        # the intake item that was / would be enqueued
       "skipped": "<reason>" # when there was nothing to recap}

    Best-effort: a failure to build the recap yields {"recap": False,
    "skipped": ...}; the rest of the PM briefing is unaffected.
    """
    date = today or _today()
    recap = build_recap(today=date, llm=llm, entries=entries)
    if not recap:
        return {"recap": False, "dry": dry, "enqueued": None,
                "monday": None, "vault": None,
                "skipped": "no activity slots / LLM unavailable for today"}

    item = _recap_item(date, recap)

    if dry:
        # Compose exactly what WOULD be written, but touch nothing.
        note_preview = render_vault_note(date, recap, monday_id="<pending>")
        return {
            "recap": True,
            "dry": True,
            "enqueued": None,
            "monday": None,
            "vault": None,
            "item": item,
            "preview": {
                "monday": {
                    "board": _sp().CONFIG["reflections_board"]["id"],
                    "group": _sp().CONFIG["reflections_board"]["groups"]["daily"],
                    "name": f"{date} — Daily Summary",
                    "entry_type": "Daily Summary",
                    "productivity": recap["productivity"],
                    "energy": recap["energy"],
                    "summary": recap["summary"],
                    "findings": recap["findings"],
                    "actions": recap["actions"],
                    "notes": recap["notes"],
                },
                "vault": {
                    "path": str(_vault_path() / "1-Daily" / f"{date}.md"),
                    "content": note_preview,
                },
                "intake_item_summary": item["payload"]["summary"],
            },
        }

    # --- live side effects (idempotent) ---
    monday_res = _write_monday(date, recap)
    note = render_vault_note(date, recap, monday_id=monday_res.get("item_id"))
    vault_res = _write_vault(date, note)
    enq_id = intake.enqueue(item)

    return {
        "recap": True,
        "dry": False,
        "enqueued": enq_id,
        "monday": monday_res,
        "vault": vault_res,
        "item": item,
    }


if __name__ == "__main__":  # pragma: no cover — manual dev invocation
    # Default to DRY so a bare run never writes. Pass --live to actually persist.
    import argparse

    ap = argparse.ArgumentParser(description="Build today's daily recap (dry by default).")
    ap.add_argument("--live", action="store_true",
                    help="actually write Monday + vault + enqueue (default: dry preview)")
    ap.add_argument("--date", default=None, help="override the recap date (YYYY-MM-DD)")
    args = ap.parse_args()
    out = enqueue_daily_recap(dry=not args.live, today=args.date)
    print(json.dumps(out, indent=2, default=str))
