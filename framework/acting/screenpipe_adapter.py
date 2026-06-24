"""Live adapters wiring the Cabinet acting lane to Nate's screenpipe brain.

These provide the gather / draft_fn deps that framework.acting.loop.run_lane (and
propose()) expect, by calling the existing, battle-tested draft_lib in-process —
the same cross-estate pattern the fidelity BrainAdapter uses. NOTHING here sends:
the present + dispatch (queue_draft / log_lesson / captain-patterns / task) deps
are wired separately and stay gated. This module is the gather→draft front-end of
the acting loop ONLY.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys

_PIPES = os.path.expanduser("~/.screenpipe/pipes")
for _p in (_PIPES, os.path.join(_PIPES, "_shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _dl():
    import draft_lib as dl  # imported lazily so the cabinet test suite needn't have it
    return dl


def _cl():
    import commitments_lib as cl  # lazy — same reason as _dl (screenpipe-only dep)
    return cl


def _pol():
    import product_ops_lib as pol  # lazy — screenpipe-only dep (Vercel REST helpers)
    return pol


# ---------------------------------------------------------------------------
# Skip-list — Teams groups the draft-lane must NEVER draft replies for (Captain
# rule 2026-06-24). The list is a plain text file (one group name per line, '#'
# comments) seeded + appended by Nate OUTSIDE this repo; we load it FRESH every
# run so appends take effect with no restart. Matching is case-insensitive
# substring against the thread's group/person display name AND its slug (the
# vault folder, e.g. "Teams Group LEAD KANALEN" → matches entry "LEAD KANALEN").
# This is a cabinet-lane policy, so it lives here in find_threads (the single
# cabinet-side entry point every thread flows through) rather than in the shared
# screenpipe draft_lib — keeping the rule git-trackable and other pipes
# unaffected. It runs ALONGSIDE (before) the downstream noise-filter /
# should_nate_reply gate, which are untouched. Degrade-safe: a missing / empty /
# all-comment / unreadable file yields no exclusions and NEVER raises.
# ---------------------------------------------------------------------------
_SKIP_GROUPS_FILE = os.path.expanduser("~/.screenpipe/state/draft-skip-groups.txt")


def _load_skip_groups() -> list:
    """Read the skip-list file fresh, returning lowercased entries (blank and
    '#'-comment lines dropped). Any error (missing/unreadable file) → []."""
    try:
        with open(_SKIP_GROUPS_FILE, encoding="utf-8") as f:
            out = []
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                out.append(s.lower())
            return out
    except Exception:
        return []


def is_skipped_group(thread: dict, skip: list | None = None) -> bool:
    """True when this thread's group/person display name (or slug) matches a
    skip-list entry as a case-insensitive substring → the lane must NOT draft
    for it. `skip` is injectable (so the list is loaded once per run); when None
    it is loaded fresh. Empty skip-list → always False (no exclusions)."""
    skip = _load_skip_groups() if skip is None else skip
    if not skip:
        return False
    hay = f"{thread.get('person', '')} {thread.get('slug', '')}".lower()
    return any(entry in hay for entry in skip)


# ---------------------------------------------------------------------------
# Fix 1 — a SKIP (or send/edit) must STICK. The propose loop dedups against
# OPEN proposals; once Nate decides, the proposal resolves and the thread looks
# "free" again -> re-presented 2h later. These helpers let the loop also skip a
# thread that has a DECIDED proposal in the consequence ledger UNLESS a genuinely
# NEW inbound message arrived since that decision. Primary signal: the last
# inbound message time vs the decision time (thread["last"]["date"] is a reliable
# ISO-8601 stamp). Fallback signal: a per-thread sha1 of the last inbound text,
# persisted to redis on every present/decision, for the rare case a timestamp is
# unparseable.
# ---------------------------------------------------------------------------
def parse_dt(value) -> "_dt.datetime | None":
    """Parse an ISO-8601 timestamp into a tz-AWARE UTC datetime, or None.

    Handles the two shapes the brain emits (msgraph '...+00:00' and teams
    '...Z' with fractional seconds) plus naive stamps (assumed UTC). Never
    raises — an unparseable value returns None so the caller falls back to the
    signature path instead of crashing the loop."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        # Last resort: strip fractional seconds / trailing junk and retry the
        # bare 'YYYY-MM-DDTHH:MM:SS' core.
        m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", s)
        if not m:
            return None
        try:
            d = _dt.datetime.fromisoformat(m.group(1))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc)


def last_inbound_dt(thread: dict) -> "_dt.datetime | None":
    """The tz-aware UTC time of the thread's last (inbound) message, or None."""
    return parse_dt((thread.get("last") or {}).get("date"))


def last_inbound_sig(thread: dict) -> str:
    """Stable sha1 of the thread's last inbound text — the redis-fallback
    'have I already handled THIS exact message?' signature. A changed last
    message yields a different signature, so a genuinely new inbound re-presents
    even when timestamps are unavailable."""
    text = ((thread.get("last") or {}).get("text") or "").strip()
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def decided_subjects(rows: list | None = None) -> dict:
    """Map subject -> latest decision time (tz-aware UTC datetime) across the
    consequence ledger's DECIDED proposals (decision != None). read_ledger() is
    last-write-wins, so each surviving row is a proposal's final state; we keep
    the newest decided_at per subject. `rows` is injectable for tests."""
    from framework.fidelity.consequence import read_ledger
    rows = rows if rows is not None else read_ledger()
    out: dict = {}
    for e in rows:
        if not isinstance(e, dict):
            continue
        prop = e.get("proposal") or {}
        if prop.get("decision") is None:
            continue  # still pending — handled by the OPEN-proposal dedup
        subj = e.get("subject")
        if not subj:
            continue
        when = parse_dt(prop.get("decided_at")) or parse_dt(e.get("ts"))
        if when is None:
            continue
        prev = out.get(subj)
        if prev is None or when > prev:
            out[subj] = when
    return out


def _redis_host() -> str:
    return os.environ.get("REDIS_HOST", "localhost")


def _handled_key(slug: str) -> str:
    """Redis key for a thread's last-handled signature. The slug is a vault
    folder name; sanitize defensively to keep the key flat (no spaces / colons
    that would fracture the keyspace)."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(slug or ""))
    return f"cabinet:draft-handled:{safe}"


def handled_signature(slug: str) -> str:
    """The last-handled signature recorded for this thread, or '' if none.
    Best-effort: any redis error returns '' (re-present rather than wrongly
    suppress — fail toward showing Nate the draft)."""
    try:
        r = subprocess.run(
            ["redis-cli", "-h", _redis_host(), "GET", _handled_key(slug)],
            capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def record_handled(slug: str, signature: str, ttl: int = 1209600) -> None:
    """Persist the last-handled signature for a thread (default TTL 14d). Called
    when a draft is presented AND when Nate decides, so the signature always
    reflects the message Nate has seen. Best-effort (never raises)."""
    try:
        subprocess.run(
            ["redis-cli", "-h", _redis_host(), "SET", _handled_key(slug),
             signature, "EX", str(ttl)],
            check=False, capture_output=True, timeout=10)
    except Exception:
        pass


def already_handled(thread: dict, decided: dict | None = None) -> bool:
    """Fix 1 core: True when this thread was already decided and NO genuinely new
    inbound message has arrived since — i.e. it must NOT be re-presented.

    Primary (timestamp): if the subject has a decision time AND the thread's last
    inbound message is NOT strictly newer than it -> handled. A last-inbound
    strictly newer than the decision is a NEW message -> re-present (returns
    False). Fallback (signature): if no decision timestamp is parseable but the
    last-inbound signature equals the recorded handled signature -> handled. Both
    fail toward re-presenting (a missing/unknown signal never suppresses)."""
    subj = thread.get("slug")
    decided = decided_subjects() if decided is None else decided
    when = decided.get(subj)
    last_dt = last_inbound_dt(thread)
    if when is not None and last_dt is not None:
        # Decided, and the last inbound is not newer than the decision -> handled.
        return last_dt <= when
    # Timestamp path unavailable on one side — fall back to the text signature.
    sig = last_inbound_sig(thread)
    return bool(sig) and handled_signature(subj) == sig


# ---------------------------------------------------------------------------
# Fix 2 — PREP BEFORE drafting (investigate-then-draft, the courses-of-action
# rule applied to drafts). Before build_draft runs, a one-call planner names the
# 1-3 concrete things a good reply needs; we auto-gather what the brain can
# answer (targeted search_brain + open_commitments_for + person history) and
# attach it to the draft context, then surface a "🔎 prep:" block listing what
# was gathered and what Nate must verify himself. Stays propose-only; the planner
# prompt is built from THREAD CONTENT ONLY — never nate_model / voice.
# ---------------------------------------------------------------------------
PREP_SYSTEM = (
    "You prepare an assistant to draft a reply to ONE message on Nate's behalf. "
    "Before drafting, decide what concrete facts a GOOD reply actually needs — "
    "the courses-of-action rule: gather, then draft. From the message and thread "
    "below, name 1-3 SPECIFIC things to check (e.g. 'compare the OLD vs NEW DPA', "
    "'find the sommerfest date in the July calendar', 'pull the PolAds codebase "
    "for how euEligibilityCategory is set'). For each, give a short brain search "
    "query that would surface it from Nate's notes/vault. Mark whether it is the "
    "kind of thing the vault can answer (searchable) or something only Nate can "
    "confirm (e.g. a private doc, an external fact, his own intent). Respond with "
    "STRICT JSON only:\n"
    '{"needs": [{"item": "<what the reply needs, 1 line>", '
    '"query": "<brain search query, or empty>", "searchable": true|false}]}\n'
    "Keep it to at most 3 items. No prose outside the JSON."
)


def prep(thread: dict, *, max_items: int = 3) -> dict:
    """Run the prep planner + auto-gather for one thread. Returns
    {gathered: [str], check_yourself: [str], enriched: str} where:
      - gathered      = 1-line notes on what WAS auto-pulled from the brain
      - check_yourself = items the planner flagged as not auto-gatherable
      - enriched      = the concatenated gathered text, to fold into the draft's
                        `brain` context so build_draft is INFORMED.
    Best-effort and side-effect-free w.r.t. sending: any failure degrades to an
    empty prep (the lane still drafts, just without the extra prep). NEVER places
    nate_model / voice content into the planner prompt or the returned block."""
    dl = _dl()
    cl = _cl()
    person = thread.get("person", "")
    last = thread.get("last", {})
    topic = (last.get("text", "") or "")
    thread_msgs = thread.get("thread") or []
    try:
        convo = dl.thread_text(thread_msgs) if thread_msgs else topic[:600]
    except Exception:
        convo = topic[:600]

    gathered: list = []
    check_yourself: list = []
    enriched_parts: list = []

    # 1) Always-available, deterministic prep: open commitments with this person.
    try:
        commits = dl.open_commitments_for(thread.get("slug", "")) or []
    except Exception:
        commits = []
    if commits:
        gathered.append(f"open commitments with {person}: {len(commits)}")
        enriched_parts.append("### prep: open commitments\n" + "\n".join(commits))

    # 2) The planner names what the reply needs (one LLM call, thread-only input).
    plan = None
    try:
        payload = (
            f"# PERSON\n{person}\n\n"
            f"# THREAD (oldest-first)\n{convo[:2500]}\n\n"
            f"# MESSAGE TO REPLY TO\n{topic[:1200]}"
        )
        plan = cl.call_llm(payload, PREP_SYSTEM, max_tokens=500)
    except Exception:
        plan = None

    needs = (plan or {}).get("needs") if isinstance(plan, dict) else None
    if not isinstance(needs, list):
        needs = []

    for item in needs[:max_items]:
        if not isinstance(item, dict):
            continue
        label = (item.get("item") or "").strip()
        query = (item.get("query") or "").strip()
        searchable = bool(item.get("searchable", True))
        if not label:
            continue
        if searchable and query:
            try:
                hit = dl.search_brain(query, top_k=3)
            except Exception:
                hit = ""
            if hit and hit.strip():
                gathered.append(f"{label} -> searched: {query}")
                enriched_parts.append(f"### prep: {label} (q: {query})\n{hit.strip()}")
            else:
                check_yourself.append(f"{label} (no vault hit for '{query}')")
        else:
            check_yourself.append(label)

    enriched = "\n\n".join(enriched_parts)
    return {"gathered": gathered, "check_yourself": check_yourself,
            "enriched": enriched}


def find_threads(hours: int = 48) -> list:
    """Awaiting-reply threads from the brain (each: slug, person, last, thread,
    audience). The acting lane proposes a draft for each that passes the gate.

    Skip-list excluded here: any thread whose group/person name matches an entry
    in ~/.screenpipe/state/draft-skip-groups.txt (loaded fresh each call) is
    dropped before it can reach the gate / drafter — the lane NEVER drafts for
    those groups. Runs alongside the existing noise-filter + should_nate_reply
    gate (downstream), which are unchanged."""
    threads = _dl().find_awaiting_threads(hours=hours)
    skip = _load_skip_groups()
    return [t for t in threads if not is_skipped_group(t, skip)]


def open_commitments(direction: str = "owed_by_nate") -> list:
    """Open commitments from the screenpipe ledger (Obsidian 6-Commitments/ — the
    source of truth for promises). Returns the raw frontmatter dicts (text,
    person, slug, due, source, source_date, status, direction) for items still
    open in the requested direction. The briefing surfaces the time-bound /
    overdue ones; the caller wraps this for best-effort behavior."""
    return [c for c in (_cl().load_all() or {}).values()
            if isinstance(c, dict)
            and c.get("status", "open") == "open"
            and c.get("direction") == direction]


def deploy_health(app: str, limit: int = 8) -> dict:
    """Recent Vercel deploy health for one app (read-only, via product_ops_lib's
    REST helper). Returns {app, total, latest_state, failed:[{state,created,creator}]}.
    The caller surfaces a briefing item ONLY when something is wrong (quiet when
    healthy). A missing VERCEL_API_KEY → product_ops_lib returns [] → empty health;
    the caller wraps this for best-effort behavior."""
    deps = _pol().vercel_deployments(app, limit=limit) or []
    failed = [{"state": d.get("state"), "created": d.get("created"),
               "creator": d.get("creator")}
              for d in deps if d.get("state") in ("ERROR", "CANCELED")]
    return {
        "app": app,
        "total": len(deps),
        "latest_state": (deps[0].get("state") if deps else None),
        "failed": failed,
    }


def gather(thread: dict, *, do_prep: bool = True) -> dict:
    """run_lane's gather(thread_ref) — assemble the as-of-now context + the
    should-Nate-reply gate decision for one thread.

    Fix 2: when ``do_prep`` (the default), an investigate-then-draft prep step
    runs FIRST — a one-call planner names the concrete things the reply needs and
    auto-gathers what the brain can answer; the gathered text is folded into the
    ``brain`` context so build_draft is INFORMED, and a structured ``prep`` block
    (gathered / check_yourself) is returned for the present() surface."""
    dl = _dl()
    slug, person = thread["slug"], thread["person"]
    intel = dl.person_intel(slug)
    topic = (thread.get("last", {}).get("text", "") or "")[:200]
    brain = dl.search_brain(f"{person} {topic}", top_k=4)
    commits = dl.open_commitments_for(slug)

    prep_block = {"gathered": [], "check_yourself": [], "enriched": ""}
    if do_prep:
        try:
            prep_block = prep(thread)
        except Exception:
            pass  # prep is best-effort; the lane still drafts without it
    if prep_block.get("enriched"):
        # Fold the prep into the brain context build_draft already consumes, so
        # the extra targeted retrieval actually reaches the drafter.
        brain = (brain + "\n\n" if brain else "") + prep_block["enriched"]

    gate = dl.should_nate_reply(thread["thread"], thread.get("audience", {}),
                                intel, brain, person=person)
    return {"intel": intel, "brain": brain, "commits": commits, "gate": gate,
            "prep": prep_block}


def draft_fn(thread: dict, ctx: dict, *, min_confidence: float = 0.0):
    """run_lane's draft_fn(thread_ref, ctx) — returns the draft string, or None
    when the gate says no-reply or the draft is missing/low-confidence (None ==
    the lane stays silent on this thread, no proposal made)."""
    dl = _dl()
    if not (ctx.get("gate") or {}).get("should_reply"):
        return None
    res = dl.build_draft(thread["thread"], thread["slug"], thread["person"],
                         intel=ctx.get("intel"), commits=ctx.get("commits"),
                         brain=ctx.get("brain"))
    if not res or not res.get("draft"):
        return None
    if float(res.get("confidence", 0) or 0) < min_confidence:
        return None
    return res["draft"].strip()


def lane_for(thread: dict) -> str:
    aud = (thread.get("audience") or {}).get("kind", "direct")
    return "send-group-reply" if aud in ("group", "list") else "send-1to1-reply"
