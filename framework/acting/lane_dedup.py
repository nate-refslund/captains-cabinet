"""framework.acting.lane_dedup — the draft/action-lane loop-plumbing.

The PURE (zero-screenpipe) dedup / recency / handled-signature helpers the acting
lanes use to decide WHICH awaiting thread to (re-)present: timestamp parsing, the
decided/open proposal maps read from the consequence ledger, the recency-aware
open/handled gates, the redis handled-signature, and audience->lane routing.

Extracted from the former ``framework.acting.screenpipe_adapter`` (SRC-3 source-
adapter split): these functions carry NO screenpipe / vault coupling — they read
the framework consequence ledger + redis only — so they stay in ``framework/``
where any captain/flavor can use them, while the screenpipe-coupled acting
surface (find_threads / gather / draft_fn / ...) re-homed to the Flavor-A adapter
(``instance/flavor-a/flavor_a/acting.py``, reached via
``framework.sources.get_source()``). Bodies are byte-identical to the originals.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import re
import subprocess


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
    thread that already has an open proposal awaiting the captain's decision — but a blunt
    'subject in open set' check silently swallows a GENUINELY NEW inbound that
    arrives while the prior draft is still undecided (the reported Casper
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
    5-min cron overlapping) therefore both snapshot 'no open proposal for Lisa'
    before either has emitted, both draft, and the captain gets the SAME draft twice.
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
    suppress — fail toward showing the captain the draft)."""
    try:
        r = subprocess.run(
            ["redis-cli", "-h", _redis_host(), "GET", _handled_key(slug)],
            capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def record_handled(slug: str, signature: str, ttl: int = 1209600) -> None:
    """Persist the last-handled signature for a thread (default TTL 14d). Called
    when a draft is presented AND when the captain decides, so the signature always
    reflects the message the captain has seen. Best-effort (never raises)."""
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


def lane_for(thread: dict) -> str:
    aud = (thread.get("audience") or {}).get("kind", "direct")
    return "send-group-reply" if aud in ("group", "list") else "send-1to1-reply"
