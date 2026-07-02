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


# Token preflight (once, at import): the live audio/OCR tier (_fetch_screen →
# sp_lib) needs SCREENPIPE_API_AUTH_KEY. Without it that tier silently returns
# nothing — so log ONCE to stderr that it's disabled, but NEVER raise: the vault
# + Sent tiers still work, and a missing key must not break drafting.
if not os.environ.get("SCREENPIPE_API_AUTH_KEY"):
    print(
        "[screenpipe_adapter] SCREENPIPE_API_AUTH_KEY unset — live audio/OCR "
        "context tier disabled (vault + Sent still active).",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Chrome/relevance gate for the live (raw audio / on-screen) context tier.
# context_lib._fetch_screen returns OCR lines from whatever app was on screen;
# many are pure UI chrome ("Collapse app bar", menu labels, keystroke hints)
# rather than substance. We drop those before merging into the brain context so
# the drafter sees on-topic lines, not app furniture.
# ---------------------------------------------------------------------------
_CHROME_SUBSTRINGS = (
    "collapse app bar", "expand app bar", "view more apps", "show more apps",
    "app launcher", "navigation rail", "skip to main", "skip to content",
    "⌘", "ctrl+", "alt+", "shift+", "⌥", "⇧", "⌃",
)


def _is_chrome(text: str) -> bool:
    """True when an OCR/audio line is pure app-chrome (UI furniture) and should
    be dropped before merging into context. Drops: known chrome substrings
    (case-insensitive) and very short lines (< ~40 chars), which on screen are
    almost always button/menu labels rather than substance. Never raises."""
    s = (text or "").strip()
    if len(s) < 40:
        return True
    low = s.lower()
    return any(sub in low for sub in _CHROME_SUBSTRINGS)


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


def _norm(s: str) -> str:
    """Lowercase + collapse every run of non-alphanumeric chars to a single
    space (and strip). Makes the skip-match robust to punctuation/spacing
    variants between the captain's skip-list entry and the live group name:
    'O-town power (check up)' and 'O town power check up' both normalize to
    'o town power check up'. Danish letters (å/ø/æ) are alnum, so preserved."""
    out = []
    prev_space = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev_space = False
        elif not prev_space:
            out.append(" ")
            prev_space = True
    return "".join(out).strip()


def _load_skip_groups() -> list:
    """Read the skip-list file fresh, returning NORMALIZED entries (blank and
    '#'-comment lines dropped). Any error (missing/unreadable file) → []."""
    try:
        with open(_SKIP_GROUPS_FILE, encoding="utf-8") as f:
            out = []
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                n = _norm(s)
                if n:
                    out.append(n)
            return out
    except Exception:
        return []


def is_skipped_group(thread: dict, skip: list | None = None) -> bool:
    """True when this thread's group/person display name (or slug) matches a
    skip-list entry as a punctuation-NORMALIZED substring → the lane must NOT
    draft for it (and so never surfaces it to the Captain at all, not even a
    'skip' notification). `skip` is injectable (loaded once per run); when None
    it is loaded fresh. Empty skip-list → always False (no exclusions)."""
    skip = _load_skip_groups() if skip is None else skip
    if not skip:
        return False
    hay = _norm(f"{thread.get('person', '')} {thread.get('slug', '')}")
    return any(entry in hay for entry in skip)


# ---------------------------------------------------------------------------
# Calendar-invite exclusion. A meeting invitation / organizer-update mail
# (e.g. Lisa Stentoft's recurring "Ugentlig Planlægning – Agenda") arrives as
# an ordinary `received` email, so draft_lib.find_awaiting_threads surfaces it
# as an awaiting-reply thread and the lane drafts a *prose reply* to it — which
# is wrong twice over: a calendar invite is answered by Accept/Decline (a
# calendar action), never by an email reply, AND it is not a thread that "needs
# Nate's reply" at all. Calendar handling is a SEPARATE capability (the comms
# officer's calendar read + auto-accept course, designed alongside this).
#
# We classify calendar items here, from the captured message itself, with a
# no-LLM heuristic (the same tier as is_skipped_group), and drop them in
# find_threads BEFORE the gate/drafter — so an invite never becomes a reply
# draft. This is a pure classification filter: it reads, it never mutates a
# message, sends nothing, and declines nothing. Best-effort: any error → False
# (fail open to the existing noise-filter + should_nate_reply gate, never crash
# the lane).
#
# Detection signals (any ONE is sufficient; ordered cheap→specific):
#   1. iCalendar payload markers — the .ics body Outlook embeds in invites.
#   2. Outlook/Teams invite skeleton — the "When:/Where:" (EN) or
#      "Hvornår:/Hvor:" (DA) header block + the Teams join-meeting block.
#      Both EN and DA because Nate's tenant is bilingual.
#   3. Organizer/room-resource sender or response-token signals — RSVP /
#      "Accepteret/Afvist/Foreløbig" status lines, room-mailbox senders.
# Each marker is anchored enough that a normal human email about an unrelated
# topic that merely mentions the word "meeting" does NOT match (we require the
# structured invite scaffolding or an explicit calendar payload, not a bare
# keyword). Danish + English both covered.
_CAL_ICS_RE = re.compile(
    r"\bBEGIN:VCALENDAR\b|\bBEGIN:VEVENT\b|\bMETHOD:REQUEST\b|"
    r"\bMETHOD:CANCEL\b|\bMETHOD:REPLY\b|"
    r"text/calendar|application/ics|\.ics\b|name=\"meeting\.ics\"",
    re.I,
)
# The invite header skeleton: a "when" line AND a "where/organizer" line, in
# EN or DA, is the structural fingerprint of an Outlook/Teams invitation body.
_CAL_WHEN_RE = re.compile(
    r"(?im)^\s*(?:when|w?hen|hvornår|tid|dato|time)\s*[:：]",
)
_CAL_WHERE_RE = re.compile(
    r"(?im)^\s*(?:where|hvor|sted|location|organi[sz]er|arrangør|"
    r"required attendees|påkrævede deltagere|microsoft teams meeting|"
    r"join microsoft teams meeting|deltag i (?:møde|teams-møde))\s*[:：]?",
)
# Standalone strong signals — Teams join block / explicit RSVP-response lines /
# recurrence header that Outlook stamps onto a series invite.
_CAL_STRONG_RE = re.compile(
    r"join microsoft teams meeting|microsoft teams-?møde|"
    r"_____+\s*\n?\s*microsoft teams|"          # the Teams join separator block
    r"\boccurs every\b|\bgentages hver\b|\bukentlig\b|\bevery week on\b|"
    r"\baccepted on behalf\b|\baccepteret\b|\bafvist\b|\bforeløbig accepteret\b|"
    r"\btentatively accepted\b|\bdeclined the\b|\bafslog\b",
    re.I,
)
# Room / meeting-resource mailbox senders — these are calendar resources, not
# people (mirrors the room-account patterns already in email_lib's noise set).
_CAL_ROOM_SENDER_RE = re.compile(
    r"\bODE-?SN-?mode\d*@|^tusn-[a-z0-9]*@|-warroom\d*@|^kbh-facility@|"
    r"^ode-tusn|-facility@|^room-|^moede-?\d*@|^mode\d*@",
    re.I,
)


def is_calendar_invite(thread: dict) -> bool:
    """True when this awaiting-reply thread's latest message is a calendar
    invitation / meeting-organizer update (not a prose message that needs a
    reply). Such items are handled by the calendar course (Accept/Decline),
    never by a drafted email reply, so the lane must NOT surface them as
    awaiting-reply. Read-only, no-LLM, best-effort (any error → False)."""
    try:
        last = thread.get("last") or {}
        text = last.get("text") or ""
        who = last.get("who") or ""
        if not text and not who:
            return False
        # Cheapest first: an embedded iCalendar payload is unambiguous.
        if _CAL_ICS_RE.search(text):
            return True
        # A room/resource mailbox as the counterparty → calendar resource.
        if _CAL_ROOM_SENDER_RE.search(who):
            return True
        # Standalone strong signal (Teams join block / RSVP status / recurrence).
        if _CAL_STRONG_RE.search(text):
            return True
        # Structural invite skeleton: a "when" line together with a
        # "where/organizer/attendees" line — the Outlook/Teams invite shape.
        if _CAL_WHEN_RE.search(text) and _CAL_WHERE_RE.search(text):
            return True
        return False
    except Exception:
        return False


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


def open_subject_ts(rows: list | None = None) -> dict:
    """Map subject -> NEWEST open-proposal creation time (tz-aware UTC) across the
    consequence ledger's still-PENDING proposals (decision is None, no outcome).

    The OPEN-proposal companion to ``decided_subjects``. The propose loop dedups a
    thread that already has an open proposal awaiting Nate's decision — but a blunt
    'subject in open set' check silently swallows a GENUINELY NEW inbound that
    arrives while the prior draft is still undecided (the reported Kristoffer
    Round-2 bug: a Round-1 draft sat open since the night before, so the 11h-newer
    Round-2 message was dropped). Keyed on each open proposal's ``ts`` (when it was
    proposed) so the loop can compare it against the live last-inbound time and
    re-present only when something newer actually arrived. ``rows`` is injectable
    for tests."""
    from framework.fidelity.consequence import read_ledger
    rows = rows if rows is not None else read_ledger()
    out: dict = {}
    for e in rows:
        if not isinstance(e, dict):
            continue
        prop = e.get("proposal") or {}
        if prop.get("decision") is not None or "outcome" in e:
            continue  # decided/superseded — handled by decided_subjects()
        subj = e.get("subject")
        if not subj:
            continue
        when = parse_dt(e.get("ts"))
        if when is None:
            continue
        prev = out.get(subj)
        if prev is None or when > prev:
            out[subj] = when
    return out


def subject_has_open_proposal(slug: str, rows: list | None = None) -> bool:
    """True when an OPEN (undecided, no-outcome) proposal currently exists for
    ``slug`` in the ledger. A LIVE re-check, read at the moment of use — distinct
    from the once-per-run ``open_subject_ts`` snapshot.

    Why this exists (duplicate-draft fix): the lane reads open_subject_ts() ONCE
    at the start of main(), then spends tens of seconds in the LLM gather/draft
    before it emits its own proposal. Two concurrent lane runs (a manual run + the
    5-min cron overlapping) therefore both snapshot 'no open proposal for Maria'
    before either has emitted, both draft, and Nate gets the SAME draft twice.
    Re-reading the ledger immediately before emit/present closes that window: a
    proposal that landed DURING our draft is now visible and we skip. Cheap (one
    ledger read) and called at most MAX times per run. ``rows`` injectable for
    tests."""
    return slug in open_subject_ts(rows=rows)


def open_proposal_blocks_live(thread: dict, rows: list | None = None) -> bool:
    """RECENCY-AWARE live re-check of the open-proposal dedup, for the Layer-2
    pre-emit guard. True == an OPEN proposal exists for this thread AND the
    inbound we just drafted is NOT strictly newer than it -> skip (a genuine
    duplicate). False == either no open proposal, or the inbound is strictly
    newer than every open proposal (a real new message that legitimately
    re-presents even while an older draft is still undecided).

    This is the LIVE (re-read at moment of use) counterpart of
    ``open_proposal_blocks``, which runs at the TOP of the loop off a once-per-run
    snapshot. Both MUST apply the same ``last_dt <= when`` recency test, or the
    two checkpoints disagree: the blunt predecessor ``subject_has_open_proposal``
    skipped on ANY open proposal, so a thread that correctly passed the
    recency-aware top-of-loop gate (because a newer message arrived) was then
    killed here by a STALE older open proposal — the Morten-Stagaard 17:05 DPA
    failure (an earlier draft for the 14:53 message sat open and undecided, so the
    legitimately-new 17:05 reply was silently suppressed). Reading the ledger live
    still closes the concurrent-duplicate window the Layer-2 guard exists for: a
    proposal that landed DURING our draft for the SAME (or newer-than-our-inbound)
    message is caught, because that proposal's ts is >= our inbound and the
    ``last_dt <= when`` test holds. ``rows`` injectable for tests.

    Fail-safe is identical to ``open_proposal_blocks``: no open proposal -> not
    blocked; open proposal but an unparseable inbound date -> block (don't risk a
    duplicate for a thread already awaiting a decision)."""
    return open_proposal_blocks(thread, open_subject_ts(rows=rows))


def still_awaiting(slug: str, hours: int = 72) -> "bool | None":
    """LIVE freshness re-check: is ``slug``'s latest message STILL inbound
    (awaiting Nate), as of right now?

    Returns True if the slug is still an awaiting-reply thread, False if it is
    NOT (Nate has since replied — his message is now the latest — or it dropped
    out for another reason), and None if undeterminable (the brain query failed).

    Why: a backlog draft can surface AFTER Nate already replied himself (he is
    faster than the 5-min lane). find_threads() ran at the TOP of the run; by the
    time a later draft in the batch reaches present(), the live state may have a
    Nate reply as the newest message. We must DROP such a draft. The authority is
    the same as find-time — ``find_awaiting_threads`` only returns a thread whose
    LAST message direction is 'received' — so a slug no longer in a FRESH call has
    a non-inbound latest message (Nate replied) and must not be drafted. Fail-safe:
    any error → None (caller surfaces; never silently suppress a real reply on a
    transient brain hiccup)."""
    try:
        live = {t.get("slug") for t in _dl().find_awaiting_threads(hours=hours)}
    except Exception:
        return None
    return slug in live


def nate_replied_since(slug: str, when: "_dt.datetime | None") -> "bool | None":
    """FIX 2 detection: has Nate sent an OUTBOUND message on ``slug``'s thread
    that is STRICTLY NEWER than ``when`` (the open proposal's creation time)?

    The precise signal for stale-open proposal auto-expiry: an open draft
    proposal sits forever when Nate replies to the counterparty HIMSELF (his
    reply bypasses the approve gate, so the proposal is never decided), and that
    dangling proposal then suppresses future genuinely-new inbound on the thread
    (the recency-aware dedup compares against the OLD pending proposal's ts).
    Detecting his own send lets the loop expire the proposal so the thread frees
    up. Note ``still_awaiting`` is the related-but-distinct find-time signal:
    once Nate replies, the thread leaves find_awaiting_threads ENTIRELY (its last
    message is no longer inbound), so the open proposal must be reconciled from
    the stored conversation, not from the awaiting set.

    Returns True if such a newer sent message exists, False if not, and None when
    undeterminable (no parseable ``when``, the conversation is unreadable, or no
    message carries a parseable date) — so the caller can fall back to its
    time-based backstop and NEVER expire on uncertainty. Reads the stored
    conversation only; no sends, no mutations, never raises."""
    if when is None:
        return None
    try:
        msgs = _dl().load_full_conversation(slug, max_messages=40) or []
    except Exception:
        return None
    saw_parseable_date = False  # proves the thread was readable AND time-comparable
    for m in msgs:
        d = parse_dt(m.get("date"))
        if d is None:
            continue
        saw_parseable_date = True  # any datable message (sent OR received)
        if (m.get("direction") or "") == "sent" and d > when:
            return True
    # No sent message newer than `when`. If we could read ANY datable message
    # (sent or received), that is a determinable "Nate has not replied since" ->
    # False; if nothing was datable (empty/unreadable convo) -> None so the caller
    # falls back to the time backstop and never expires on uncertainty.
    return False if saw_parseable_date else None


def open_proposal_blocks(thread: dict, open_ts: dict | None = None) -> bool:
    """True when this thread has an OPEN (undecided) proposal that should still
    suppress it — i.e. NO genuinely-new inbound arrived since that proposal was
    presented, so re-presenting would just duplicate the pending draft.

    Mirror of ``already_handled`` for the open-proposal case. Primary (timestamp):
    the thread is blocked iff its last inbound is NOT strictly newer than the open
    proposal's creation time. A strictly-newer inbound (a real new message while
    the old draft is still pending) returns False -> the loop re-presents it.
    Fail-safe: if the subject has no open proposal, return False (nothing to
    block). If the open proposal's ts is unparseable but the subject IS open, fall
    back to blocking (the conservative direction: don't spam a second draft for a
    thread already awaiting a decision when we cannot prove the inbound is newer).
    A thread with no parseable inbound date but an open proposal is also blocked
    (same reason)."""
    subj = thread.get("slug")
    open_ts = open_subject_ts() if open_ts is None else open_ts
    when = open_ts.get(subj)
    if when is None:
        return False  # no open proposal for this subject — not blocked
    last_dt = last_inbound_dt(thread)
    if last_dt is None:
        return True   # open proposal exists, can't prove a newer inbound -> block
    return last_dt <= when


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


# ---------------------------------------------------------------------------
# FIX 1 — ACTIVE-THREAD LOCK. When the Chair takes ownership of a thread to
# hand-craft a reply itself, it must guarantee the draft-lane never ALSO drafts
# (or even surfaces) that same thread — the race that produced the wrong-Morten
# draft (the lane drafted a thread the Chair was concurrently handling). The
# Chair SETS a redis key `cabinet:chair:active-thread:<slug>` (TTL ~12h,
# refreshable, clearable) via chair-claim-thread.sh when it starts and clears it
# via chair-release-thread.sh when it finishes. find_threads() checks the lock
# and DROPS a locked thread BEFORE the gate/drafter — neither drafting it nor
# notifying Nate about it, exactly like the skip-list exclusion. This is a
# RUNTIME-OWNERSHIP lock (cleared when the Chair is done), distinct from the
# skip-list (a standing never-draft policy) and the calendar filter (a
# classification): a thread can be claimed once, handled, released, then resume
# normal lane flow. Degrade-safe and symmetric with every other gate here: no
# redis / no key / any error -> NOT locked (no exclusion), so a redis outage can
# never silently suppress the only drafter.
# ---------------------------------------------------------------------------
def _active_thread_key(slug: str) -> str:
    """Redis key for the Chair's active-thread (ownership) lock on a thread. The
    slug is a vault folder name; sanitize identically to _handled_key so the key
    stays flat (no spaces/colons that would fracture the keyspace) and the
    Chair-side helper and this reader compute the SAME key for a given slug."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(slug or ""))
    return f"cabinet:chair:active-thread:{safe}"


def chair_holds_thread(slug: str) -> bool:
    """True when the Chair currently holds the active-thread lock for ``slug``
    (the key exists) -> the draft-lane must NOT draft or surface this thread.

    Best-effort + degrade-safe in the SAFE direction (mirrors the skip-list /
    handled-signature checks): any redis failure, a missing key, or an empty
    value returns False (NOT locked) so a redis outage never suppresses the
    drafter. The key carries its own TTL so a crashed/forgetful Chair auto-frees
    the thread; a present non-empty value means the lock is live."""
    try:
        r = subprocess.run(
            ["redis-cli", "-h", _redis_host(), "GET", _active_thread_key(slug)],
            capture_output=True, text=True, timeout=10)
        return bool((r.stdout or "").strip())
    except Exception:
        return False


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

    Three exclusions are applied here, BEFORE the gate / drafter:
      * Skip-list — any thread whose group/person name matches an entry in
        ~/.screenpipe/state/draft-skip-groups.txt (loaded fresh each call); the
        lane NEVER drafts for those groups.
      * Calendar invites — any thread whose latest message is a meeting
        invitation / organizer update (is_calendar_invite); these are answered
        by Accept/Decline via the calendar course, never by a drafted reply, so
        they must not surface as awaiting-reply.
      * Chair active-thread lock (FIX 1) — any thread the Chair currently holds
        (chair_holds_thread); the Chair is hand-crafting that reply itself, so
        the lane must neither draft nor surface it (the race that produced the
        wrong-Morten draft). Degrade-safe: no redis / no lock -> no exclusion.
    All three run alongside the existing noise-filter + should_nate_reply gate
    (downstream), which are unchanged."""
    threads = _dl().find_awaiting_threads(hours=hours)
    skip = _load_skip_groups()
    return [t for t in threads
            if not is_skipped_group(t, skip)
            and not is_calendar_invite(t)
            and not chair_holds_thread(t.get("slug", ""))]


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
    # The thread's latest message text — drives BOTH the search_brain query and
    # (the fix) the topic= anchor for the live audio/OCR/Sent fetch below.
    topic = (thread.get("last", {}).get("text", "") or "")[:400]
    brain = dl.search_brain(f"{person} {topic[:200]}", top_k=4)
    commits = dl.open_commitments_for(slug)

    # THE FIX: search_brain reaches only the vault INDEX. Raw audio / on-screen
    # OCR / recent Sent live in context_lib.gather — and its screen fetcher keys
    # on topic terms, not the person's name. Passing topic= makes _fetch_screen
    # topic-anchored (via extract_topic_terms) so it returns on-topic lines, not
    # app-chrome that merely co-occurred while the person's name was visible.
    # Degrade-safe: any screenpipe outage / import failure contributes nothing
    # and NEVER breaks drafting.
    try:
        import context_lib as _ctx
        live = _ctx.gather(person, sources=["vault", "sent", "screen"],
                            topic=topic, budget_chars=2500)
        live_brief = (live or {}).get("brief", "") or ""
        if live_brief.strip() and live_brief.strip() != "(no context found)":
            # Drop pure app-chrome OCR lines before merging (keep substance).
            kept = [ln for ln in live_brief.splitlines()
                    if ln.strip() and not _is_chrome(ln)]
            live_brief = "\n".join(kept).strip()
            if live_brief:
                heading = ("### live context (raw audio / on-screen / Sent — "
                           "topic-anchored)")
                brain = ((brain + "\n\n" if brain else "")
                         + heading + "\n" + live_brief)
    except Exception:
        pass  # live context tier is best-effort; never break the lane

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


# ---------------------------------------------------------------------------
# Nate-voice character normalize (captain-patterns -> teams-message-voice-
# formatting). Nate's rule (2026-06-25): write only with characters on a normal
# Danish keyboard, PLUS emojis. Enforced as a CHARSET WHITELIST + emoji-safe
# catch-all rather than a substitution list, so unanticipated fancy chars (a CJK
# char, a math symbol, an exotic dash variant) are caught, not leaked:
#   FAST PATH  — common offenders: any dash -> " - ", bullets -> "-", arrows ->
#                "->", ellipsis -> "...", curly quotes -> " / ' ", NBSP -> space.
#   WHITELIST  — a-z A-Z 0-9, ae/oe/aa (DK letters), accented Latin via dead
#                keys, standard punctuation/symbols (incl. EUR), space, newline,
#                and EMOJIS — all kept verbatim.
#   CATCH-ALL  — anything else: NFKD-decompose to its keyboard equivalent, or drop.
# The charset MODEL has ONE implementation: the dependency-free `voice_charset`
# module in screenpipe's _shared/ (E-2 single source of truth). draft_lib.humanize
# re-exports it; this adapter ALSO applies it at the cabinet chokepoint (draft_fn)
# so the lane can NEVER present or persist a non-conforming draft. Primary path:
# draft_lib.humanize (the full screenpipe stack). Fallback (cabinet unit suite,
# no screenpipe deps): import voice_charset DIRECTLY — same one implementation, no
# restated rule, so the table can never drift. Both paths apply the identical
# doubled-space tidy humanize() does. Pure string transform: idempotent
# (keyboard-only + emoji passes through), no I/O, never raises.
# ---------------------------------------------------------------------------
_VOICE_DBLSPACE_RE = re.compile(r"(?<=\S)[ \t]{2,}")


def _vc():
    import voice_charset as vc  # lazy — same _shared/ path as _dl; zero screenpipe deps
    return vc


def _voice_fallback(text):
    """Charset-whitelist normalize without the screenpipe stack: delegates to the
    SAME voice_charset.normalize_charset draft_lib re-exports (no rule restated),
    then applies the doubled-space tidy humanize() applies, so this fallback's
    output matches the draft_lib.humanize primary path exactly."""
    t = _vc().normalize_charset(text)
    return _VOICE_DBLSPACE_RE.sub(" ", t)


def normalize_voice(text):
    """Normalize Nate-voice outbound text to the Danish-keyboard-plus-emoji charset
    (the teams-message-voice-formatting rule). Delegates to draft_lib.humanize when
    available (single source of truth: charset whitelist + emoji-safe catch-all);
    otherwise applies the SAME voice_charset model locally. Idempotent and total —
    any failure or non-str input returns the input as-is; emojis + ae/oe/aa survive."""
    if not text or not isinstance(text, str):
        return text
    try:
        return _dl().humanize(text)
    except Exception:
        pass
    try:
        return _voice_fallback(text)
    except Exception:
        return text


# ---------------------------------------------------------------------------
# "Hej <name>" opener rule (teams-message-voice-formatting (c)). Nate opens with
# a "hej <name>" greeting only on the FIRST message of the day to that person; a
# follow-up later the same day just continues, no re-greeting. This is a judgment
# rule, so it fires ONLY on positive evidence: we strip a leading greeting line
# from the draft *only* when Nate has already SENT this person a message earlier
# TODAY (in his local timezone). Fail-safe in BOTH directions — if we cannot
# prove a same-day prior send (no history, unparseable dates, any error) we keep
# the greeting (the conservative default: a stray greeting is harmless; wrongly
# stripping the first-of-day greeting is the worse error). Read-only, no I/O
# beyond the best-effort history read, never raises.
# ---------------------------------------------------------------------------
def _captain_tz():
    """The captain's local timezone (platform.yml captain_timezone), for the
    'today' boundary. Falls back to Europe/Berlin (CET/CEST) then UTC."""
    name = "Europe/Berlin"
    try:
        path = "/Users/nate/captains-cabinet/instance/config/platform.yml"
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("captain_timezone:"):
                    val = s.split(":", 1)[1].split("#", 1)[0].strip()
                    if val:
                        name = val
                    break
    except Exception:
        pass
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("UTC")
        except Exception:
            return _dt.timezone.utc


# A leading greeting line: "hej/hi/hello/hey/dav/hallo[j] [name][,/ -]" possibly
# followed by the rest on the same physical line. Danish "hej" is the common one.
_GREETING_LINE_RE = re.compile(
    r"^[ \t]*(?:hej|hi|hello|hey|dav|davs|halloj?|goddag)\b"
    r"[ \t]*[\w æøåÆØÅ.'-]*?[,!:–-]*[ \t]*(?:\n+|$)",
    re.IGNORECASE,
)


def messaged_today(thread: dict) -> bool:
    """True when Nate has already SENT a message to this person earlier TODAY
    (captain-local day). Looks at the thread's recent messages and, best-effort,
    the fuller stored conversation. Any uncertainty (no parseable same-day sent
    message, error) returns False — so the greeting is kept by default."""
    try:
        tz = _captain_tz()
        today = _dt.datetime.now(tz).date()
        msgs = list(thread.get("thread") or [])
        # Best-effort: widen to the fuller conversation so an earlier same-day
        # send outside the last-N thread window still counts. Never fatal.
        try:
            slug = thread.get("slug", "")
            if slug:
                msgs = (_dl().load_full_conversation(slug, max_messages=40)
                        or []) + msgs
        except Exception:
            pass
        for m in msgs:
            if (m.get("direction") or "") != "sent":
                continue
            d = parse_dt(m.get("date"))
            if d is None:
                continue
            if d.astimezone(tz).date() == today:
                return True
        return False
    except Exception:
        return False


def strip_greeting_if_not_first_of_day(draft: str, thread: dict) -> str:
    """Drop a leading 'hej <name>' greeting line from `draft` ONLY when Nate has
    already messaged this person earlier today (messaged_today). Otherwise return
    the draft unchanged. Only the FIRST physical line is considered a greeting,
    and only if it matches the greeting shape — body content is never touched."""
    if not draft or not isinstance(draft, str):
        return draft
    try:
        if not messaged_today(thread):
            return draft
        m = _GREETING_LINE_RE.match(draft)
        if not m:
            return draft
        rest = draft[m.end():].lstrip("\n")
        # Never strip the greeting into an EMPTY draft (the greeting was the whole
        # message) — keep the original rather than send nothing.
        return rest if rest.strip() else draft
    except Exception:
        return draft


def draft_fn(thread: dict, ctx: dict, *, min_confidence: float = 0.0):
    """run_lane's draft_fn(thread_ref, ctx) — returns the draft string, or None
    when the gate says no-reply or the draft is missing/low-confidence (None ==
    the lane stays silent on this thread, no proposal made).

    The returned draft is run through normalize_voice() (em/en dashes, bullet
    glyphs and → arrows become Nate's plain forms) and the first-of-day greeting
    rule (a leading 'hej <name>' is dropped when Nate already messaged this
    person earlier today) so the cabinet lane never surfaces — or persists for
    verbatim send — a draft that breaks the teams-message-voice-formatting rules.
    """
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
    draft = normalize_voice(res["draft"].strip())
    return strip_greeting_if_not_first_of_day(draft, thread)


def lane_for(thread: dict) -> str:
    aud = (thread.get("audience") or {}).get("kind", "direct")
    return "send-group-reply" if aud in ("group", "list") else "send-1to1-reply"
