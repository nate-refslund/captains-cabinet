#!/usr/bin/env python3.12
"""Propose-half of the live acting lane (run on a trigger/cron).

Finds awaiting-reply threads, drafts each via the brain (gate-filtered), and
PRESENTS the draft to the captain's Telegram (Send / Edit: / Skip:), emitting a
pending proposal to the consequence ledger. NOTHING is sent to any recipient —
the recipient-send is the handle-half (approve -> queue_draft), gated separately
and behind framework.env.allow_sends(). This half only surfaces a draft TO the
captain, which is fully reversible.

Dedup: skips a thread that already has an OPEN pending proposal (the ledger is
the dedup store). Env: TELEGRAM_COS_TOKEN, CAPTAIN_TELEGRAM_ID, DRAFT_LANE_MAX.
"""
from __future__ import annotations

import os
import sys
import json
import fcntl
import atexit
import datetime
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

# Repo root on sys.path so `from framework...` resolves when this script is run
# directly (launchd/cron pass a bare path, not `-m`). Derive it from THIS file
# (parents[2] = the tree that contains framework/), NEVER a hardcoded absolute.
# WHY [lane-supply 2026-07-05, adversarial-review fix]: framework/ is a
# namespace package (no __init__.py), so a literal absolute repo path
# front-loaded the MAIN checkout onto framework's namespace __path__. A test run
# from a git worktree then imported main's STALE framework/* (e.g.
# watchdog/registry.py, which lacks this lane's monthly floor) instead of the
# worktree's — a full worktree sweep failed 3 registry tests purely from import
# order. parents[2] resolves to the identical path in production (run from main),
# so this is byte-for-byte equivalent there; it only differs — correctly — when
# the code under test lives in a worktree. Matches run_action_lane.py:49.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.acting import loop, lane_dedup as ld
from framework.acting.loop import proposal_id
from framework.fidelity.consequence import emit_consequence
from framework.env import captain_name
from framework.sources import get_source

MAX = int(os.environ.get("DRAFT_LANE_MAX", "1"))
TOKEN = os.environ["TELEGRAM_COS_TOKEN"]
CHAT = os.environ["CAPTAIN_TELEGRAM_ID"]
# FIX 2 time-based backstop: an open proposal older than this with no decision
# and no detectable self-reply is auto-expired anyway, so a stale draft never
# dangles forever (and never suppresses future inbound) even when the precise
# self-reply detector can't read the conversation. Default 36h; override via
# DRAFT_PROPOSAL_MAX_AGE_H. Set <= 0 to disable the backstop (precise-only).
PROPOSAL_MAX_AGE_H = float(os.environ.get("DRAFT_PROPOSAL_MAX_AGE_H", "36"))

_LOCK_PATH = "/tmp/cabinet-draft-lane.lock"
_lock_fh = None  # kept at module scope so the fd lives for the whole process


def _acquire_singleton_lock() -> bool:
    """Take a non-blocking, process-lifetime flock so two draft-lane runs can
    NEVER overlap. This is the root-cause fix for the duplicate-draft race: the
    5-min cron and an ad-hoc/manual run could run concurrently, both snapshot the
    open-proposal set BEFORE either emitted its proposal, and both draft the same
    thread. With a mutual-exclusion lock, the second run exits at once and there
    is structurally no concurrent window. Returns True if WE hold the lock (run),
    False if another run holds it (skip this tick). Fail-safe: if locking itself
    errors, return True (run) — a missing lock must never block the only drafter.
    The lock auto-releases when the process exits (fd closed by the OS / atexit)."""
    global _lock_fh
    try:
        _lock_fh = open(_LOCK_PATH, "w")
        fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        atexit.register(_release_singleton_lock)
        return True
    except BlockingIOError:
        return False  # another lane run holds it — skip this tick
    except Exception:
        return True   # lock unavailable for an unexpected reason — never block


def _release_singleton_lock() -> None:
    global _lock_fh
    try:
        if _lock_fh is not None:
            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_UN)
            _lock_fh.close()
    except Exception:
        pass


def _tg(text: str) -> dict:
    # ONE DOOR (P3, attention-gateway spec §4.4/§13): route through the gated
    # front-door channel (killswitch, scrub, chunking, feed journal). Same
    # loud-failure contract: ANY non-sent status raises — including
    # blocked-dev (review cp3 H1/H2: a production process missing
    # CABINET_ENV=runtime must page, never silently blackhole cards while
    # ledger rows record them as presented).
    from framework.frontdoor import channel
    res = channel.send(text, feed_meta={"kind": "draft-card"})
    if res.get("status") == "blocked-dev":
        raise RuntimeError("channel send refused (blocked-dev): set "
                           "CABINET_ENV=runtime for live sends")
    if not res.get("sent"):
        raise RuntimeError(f"channel send failed: {str(res)[:200]}")
    return {"ok": True, "result": res.get("response") or res.get("responses")}


def _store_draft(pid: str, thread: dict, draft: str) -> None:
    """Persist the EXACT presented draft, keyed by proposal id, so the Chair can
    send it VERBATIM via the brain's queue_draft on the captain's 'send' reply.
    loop.propose is leak-safe and stores no content, so without this the Chair
    would have to re-draft (non-deterministic) — this guarantees the captain gets the
    draft he approved. Redis key cabinet:draft:<pid>, TTL 7d. Best-effort."""
    last = thread.get("last", {})
    channel = "teams" if last.get("source") == "teams" else "email"
    rec = {
        "person": thread.get("person"),
        "slug": thread.get("slug"),
        "channel": channel,
        "draft": draft,
        "why": f"draft reply to {thread.get('person')}'s {channel} message (cabinet draft lane)",
    }
    host = os.environ.get("REDIS_HOST", "localhost")
    try:
        subprocess.run(
            ["redis-cli", "-h", host, "SET", f"cabinet:draft:{pid}",
             json.dumps(rec), "EX", "604800"],
            check=False, capture_output=True, timeout=10)
    except Exception:
        pass


def _prep_lines(prep: dict) -> str:
    """Render the '🔎 prep:' block for the present message from gather()'s prep
    dict: (a) what was auto-gathered, (b) what the captain should verify himself. Empty
    string when there is nothing to show (no prep block clutter)."""
    if not prep:
        return ""
    gathered = prep.get("gathered") or []
    check = prep.get("check_yourself") or []
    if not gathered and not check:
        return ""
    lines = ["🔎 prep:"]
    for g in gathered[:4]:
        lines.append(f"  ✓ {g}")
    for c in check[:4]:
        lines.append(f"  ⚠ check yourself: {c}")
    return "\n".join(lines) + "\n\n"


def _present(thread: dict, draft: str, prop: dict, prep: dict | None = None) -> None:
    last = thread.get("last", {})
    chan = "Teams" if last.get("source") == "teams" else "email"
    # B-2 defense-in-depth (cp2 re-review 2026-07-03): strip the pid marker char
    # (U+00B7 ·) from untrusted counterparty text so a correspondent's message
    # cannot inject a `·fake·` proposal marker into the card the binder parses.
    their = (last.get("text", "") or "").replace("·", "").strip()[:400]
    pid = proposal_id(prop)
    _tg(
        f"📝 Draft reply to {thread['person']} ({chan})\n\n"
        f"— they wrote:\n{their}\n\n"
        f"{_prep_lines(prep)}"
        f"— my draft (your voice):\n{draft}\n\n"
        f"Reply:  send  /  edit: <your version>  /  skip: <why>\n"
        f"·{pid}·"
    )
    _store_draft(pid, thread, draft)
    # Fix 1: record the handled signature so a re-run won't re-present this exact
    # inbound message (the redis fallback to the decided-proposal timestamp).
    try:
        ld.record_handled(thread["slug"], ld.last_inbound_sig(thread))
    except Exception:
        pass


def _auto_expire_self_replied() -> int:
    """FIX 2 — auto-expire stale-OPEN draft proposals so they stop suppressing
    future genuinely-new inbound.

    Root cause: when the captain replies to the counterparty HIMSELF, his reply bypasses
    the approve gate, so the open proposal is never decided — it dangles pending
    forever, and the recency-aware dedup then suppresses every later message on
    that thread (it compares new inbound against the OLD pending proposal's ts).
    Once the captain replies, the thread also LEAVES find_threads() (its last message is
    no longer inbound), so the proposal can only be reconciled from the ledger +
    stored conversation here, not from the awaiting set.

    For each OPEN proposal (loop.pending_proposals), expire it when EITHER:
      (1) PRECISE — the captain sent an outbound message on that thread strictly newer
          than the proposal (get_source().captain_replied_since == True); the exact fix, or
      (2) BACKSTOP — the proposal is older than PROPOSAL_MAX_AGE_H and the
          precise check did not affirmatively say 'no newer reply' (None/True),
          so a stale draft never dangles even when the conversation is unreadable.
    A precise False (we positively saw NO newer self-reply) keeps the proposal
    open until the age backstop — the captain genuinely hasn't replied yet. Expiry is the
    SAME superseding event run_lane emits for a policy-only reply (loop.expire_event:
    decision='expired', verdict='unknown', no outcome) so graduation math is
    unaffected (expired/unknown are excluded from every denominator). Best-effort:
    any failure (ledger unreadable, redis/brain hiccup) expires nothing and never
    breaks the drafting run. Returns the count expired."""
    cap = captain_name()
    try:
        open_props = loop.pending_proposals()
    except Exception as e:
        print(f"auto-expire: skipped (ledger unreadable: {e})")
        return 0
    if not open_props:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    expired = 0
    for prop in open_props:
        slug = prop.get("subject")
        if not slug:
            continue
        when = ld.parse_dt(prop.get("ts"))
        replied = get_source().captain_replied_since(slug, when)  # True / False / None
        too_old = (
            PROPOSAL_MAX_AGE_H > 0
            and when is not None
            and (now - when).total_seconds() >= PROPOSAL_MAX_AGE_H * 3600
        )
        # Precise self-reply wins outright. The age backstop fires only when the
        # precise check did NOT positively clear the thread (False == the captain has
        # demonstrably not replied yet -> leave it open until truly stale).
        if replied is True:
            reason = f"{cap} replied himself"
        elif too_old and replied is not False:
            reason = f"stale > {PROPOSAL_MAX_AGE_H:g}h, no decision"
        else:
            continue
        try:
            # Suppression clock = the proposal's own ts (when the draft was made),
            # so a later genuinely-new message on this thread is NOT swallowed as
            # already-handled; audit clock (reviewed_at) = the real expiry moment.
            ev = loop.expire_event(prop, reviewed_at=now.isoformat(),
                                   decided_at=prop.get("ts"))
            emit_consequence(**ev)
            expired += 1
            print(f"auto-expired open proposal -> {slug} ({reason})")
        except Exception as e:
            print(f"auto-expire: failed for {slug}: {e}")
    if expired:
        print(f"auto-expire: closed {expired} stale-open proposal(s)")
    return expired


def main() -> None:
    # Singleton lock FIRST: if another lane run is in flight (manual run vs the
    # 5-min cron), exit immediately. This makes concurrent runs structurally
    # impossible — the root-cause fix for the duplicate-draft race.
    if not _acquire_singleton_lock():
        print("done: another draft-lane run holds the lock — skipping this tick")
        return
    # FIX 2: reconcile stale-OPEN proposals BEFORE reading the open/decided maps
    # below — expire any whose thread the captain already replied to himself (or that
    # have gone stale). This must run first so the just-expired proposals no
    # longer appear in open_subject_ts() and therefore no longer suppress a
    # genuinely-new inbound on the same thread this very tick.
    _auto_expire_self_replied()
    cap = captain_name()
    actor = {"kind": "officer", "id": "cos"}
    # Dedup against OPEN proposals (already awaiting your decision) AND against
    # DECIDED proposals with no genuinely-new inbound since the decision (Fix 1:
    # a skip/send/edit must STICK — don't re-present a thread the captain already ruled
    # on unless a fresh message actually arrived). Both maps are read once so the
    # per-thread check is a dict lookup, not a per-thread ledger scan.
    #
    # Fix 3 (Kristoffer Round-2 bug): the OPEN-proposal dedup is now RECENCY-AWARE
    # — open_proposal_blocks() suppresses a thread only while NO inbound newer than
    # the pending proposal has arrived. Previously a blunt `slug in open_subjects`
    # check swallowed every genuinely-new message on a thread whose prior draft was
    # still undecided (Kristoffer R1 sat open overnight, so R2 — 11h newer — never
    # surfaced). Now a real new message on an open thread re-presents, exactly like
    # the decided path already does.
    src = get_source()  # the bound personal source (Flavor-A screenpipe adapter)
    open_ts = ld.open_subject_ts()
    decided = ld.decided_subjects()
    threads = src.find_threads(hours=72)
    # Newest inbound first, so the per-run budget (MAX) goes to the freshest
    # threads rather than whatever order the brain returned. Threads with an
    # unparseable date sort last (epoch fallback) but are still considered.
    _EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    threads.sort(key=lambda t: ld.last_inbound_dt(t) or _EPOCH, reverse=True)
    presented = 0
    for t in threads:
        if presented >= MAX:
            break
        if ld.open_proposal_blocks(t, open_ts):
            continue  # awaiting your decision, and no newer inbound since
        if ld.already_handled(t, decided):
            continue  # decided already, and no new inbound since -> skip sticks
        ctx = src.gather(t)  # runs the Fix-2 prep step (investigate-then-draft)
        draft = src.draft_fn(t, ctx)
        if not draft:
            continue
        # --- Pre-emit re-checks (Layer 2: defense-in-depth past the singleton
        # lock + the live-freshness guard). gather/draft above spent tens of
        # seconds in the LLM; the world may have moved while we drafted. Re-read
        # the LIVE state right before we emit/present:
        #   (1) DUP guard: a proposal for this slug may have landed during our
        #       draft (residual race if the lock ever no-ops). If one is now open
        #       FOR THIS-OR-A-NEWER inbound, skip — the captain must never get the same
        #       draft twice for an open thread. RECENCY-AWARE (open_proposal_blocks
        #       _live), mirroring the top-of-loop gate: a STALE older open proposal
        #       (an earlier draft the captain hasn't decided) must NOT suppress the
        #       genuinely-new message we just drafted — that blunt check was the
        #       Morten-Stagaard 17:05 DPA miss (older 14:53 draft sat open, so the
        #       newer 17:05 reply was silently dropped here).
        #   (2) FRESHNESS: the captain may have replied himself while we drafted (he is
        #       faster than the 5-min lane), making his message the newest. A
        #       still-awaiting re-check from the same authority as find-time drops
        #       the now-stale draft. Fail-safe: still_awaiting()==None (brain
        #       hiccup) surfaces — we never suppress a real reply on uncertainty.
        if ld.open_proposal_blocks_live(t):
            print(f"skip (now-open proposal during draft) -> {t['person']}")
            continue
        if src.still_awaiting(t["slug"], hours=72) is False:
            print(f"skip ({cap} already replied — latest no longer inbound) -> {t['person']}")
            continue
        prep = ctx.get("prep")
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        loop.propose(
            thread_ref=t, subject=t["slug"], ts=ts, actor=actor,
            lane=ld.lane_for(t),
            gather=lambda _t, _ctx=ctx: _ctx,
            draft_fn=lambda _t, _c, _d=draft: _d,
            present=lambda d, p, _t=t, _pr=prep: _present(_t, d, p, _pr),
            emit=lambda **ev: emit_consequence(**ev),
        )
        presented += 1
        print(f"presented draft -> {t['person']} ({ld.lane_for(t)})")
    print(f"done: presented {presented} draft(s)")


if __name__ == "__main__":
    main()
