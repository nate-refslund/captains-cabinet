#!/usr/bin/env python3.12
"""Capture→action lane runner — the live shell around action_lane's pure core.

Pivot of run_draft_lane.py per the 2026-07-03 Captain ruling: same singleton
lock, same ·pid· card + cabinet:action:<pid> store + consequence-ledger
proposal, ACTION payloads instead of reply drafts. Propose-only: every card
awaits Nate's approve/edit:/skip: through the (fixed) binder; approves execute
via framework.frontdoor.action_exec.

Signals v1 (read-only over the Plan-A vault, newest-first, fenced to a recency
window): open commitments (6-Commitments), fresh meeting notes (2-Meetings),
fresh decisions (5-Reflections/Decisions). The gather step is `as_of`-shaped so
the retrodiction harness can drive the same path with a historical clock.

No attention quota (Captain ruling 2026-07-03): every genuinely-needed action
is sent. MAX_PER_RUN is a technical anti-runaway bound only. The quality bar
lives in the proposer prompt (genuine need + SOLVE-shaped chains).

Run: python3.12 framework/acting/run_action_lane.py [--dry-run]
  --dry-run: gather + propose + print the would-be cards; no Telegram, no
  ledger, no Redis writes. The eyeball gate before the scheduled lane.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.acting import action_lane, screenpipe_adapter as sa  # noqa: E402
from framework.acting.loop import proposal_event, proposal_id, pending_proposals  # noqa: E402
from framework.fidelity.consequence import emit_consequence, read_ledger  # noqa: E402


def covered_evidence_refs() -> frozenset:
    """Evidence refs carried by ANY prior action card (open or decided) — the
    stable dedup identity across runs (LLM subject slugs drift; refs don't)."""
    refs: set = set()
    try:
        for ev in read_ledger():
            if ev.get("action") == "action-card":
                refs.update(r for r in (ev.get("refs") or []) if isinstance(r, str))
    except Exception:
        pass   # fail-open here is safe: slug dedup still applies
    return frozenset(refs)

VAULT = Path.home() / "Obsidian" / "screenpipe-brain"
LOCK_PATH = "/tmp/cabinet-action-lane.lock"
# Captain ruling 2026-07-03: NO attention quota — send every genuinely-needed
# action. MAX_PER_RUN is a technical anti-runaway bound only (a berserk LLM
# must not flood 20 cards in one tick), not a budget.
MAX_PER_RUN = 8
WINDOW_H = 72
LLM_MODEL = "claude-sonnet-4-6"
_lock_fh = None


def _acquire_lock() -> bool:
    global _lock_fh
    _lock_fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _load_env() -> None:
    for env in (Path(__file__).resolve().parents[2] / "cabinet" / ".env",
                Path.home() / ".screenpipe" / "pipes" / "_shared" / ".env"):
        try:
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    # an EMPTY value never claims the key — cabinet/.env ships
                    # ANTHROPIC_API_KEY= blank (officers run on subscription)
                    # and must not shadow the real key in _shared/.env
                    if v:
                        os.environ.setdefault(k.strip(), v)
        except OSError:
            pass


def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, *args],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def _llm(system: str, user: str) -> str:
    """Raw-text Anthropic call (the core parses its own JSON). Key from env;
    never logged."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    body = {"model": LLM_MODEL, "max_tokens": 4096, "system": system,
            "messages": [{"role": "user", "content": user}]}
    r = subprocess.run(
        ["curl", "-s", "--max-time", "180", "https://api.anthropic.com/v1/messages",
         "-H", f"x-api-key: {api_key}",
         "-H", "anthropic-version: 2023-06-01",
         "-H", "content-type: application/json",
         "-d", json.dumps(body)],
        capture_output=True, text=True, timeout=185)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return ""
    return "".join(c.get("text", "") for c in (d.get("content") or [])
                   if c.get("type") == "text")


# ---------------------------------------------------------------------------
# Signals (read-only vault gather; as_of-shaped for future replay)
# ---------------------------------------------------------------------------

def _recent_files(folder: Path, *, as_of: dt.datetime, window_h: int,
                  cap: int) -> list:
    if not folder.exists():
        return []
    lo = as_of - dt.timedelta(hours=window_h)
    hits = []
    for p in folder.rglob("*.md"):
        if "_noise" in p.parts:
            continue
        try:
            m = dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc)
        except OSError:
            continue
        if lo <= m <= as_of:
            hits.append((m, p))
    hits.sort(reverse=True)
    return [p for _, p in hits[:cap]]


def _excerpt(p: Path, chars: int) -> str:
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    # drop our own graph block + fences; the LLM needs prose, not plumbing
    text = re.sub(r"<!-- graph:links -->.*?<!-- /graph:links -->", "", text,
                  flags=re.DOTALL)
    return text.strip()[:chars]


def gather_signals(as_of: dt.datetime, *, window_h: int = WINDOW_H) -> str:
    """The fenced evidence bundle. v1 fencing = file-recency window ending at
    as_of; replay-grade content_ts fencing lands with the sim harness."""
    parts = []
    for label, folder, cap, chars in (
            ("OPEN COMMITMENT", VAULT / "6-Commitments", 8, 700),
            ("MEETING", VAULT / "2-Meetings", 5, 1200),
            ("DECISION", VAULT / "5-Reflections" / "Decisions", 4, 700)):
        for p in _recent_files(folder, as_of=as_of, window_h=window_h, cap=cap):
            body = _excerpt(p, chars)
            if body:
                rel = p.relative_to(VAULT)
                parts.append(f"--- {label} ref={rel} ---\n{body}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Present
# ---------------------------------------------------------------------------

def _tg(text: str) -> None:
    # HQ CHAIR channel ONLY (Captain ruling 2026-07-03: cabinet cards go to the
    # HQ Chair bot, never the Screenpipe bot). TELEGRAM_COS_TOKEN is the Chair's
    # bot — the same one the cos-inbound poller polls, so replies BIND. There is
    # deliberately NO fallback to TELEGRAM_BOT_TOKEN: that is the Screenpipe
    # bot, whose updates never reach the binder (the first 5 live cards landed
    # there and could not be verdicted).
    token = os.environ.get("TELEGRAM_COS_TOKEN", "")
    chat = os.environ.get("CAPTAIN_TELEGRAM_ID", "")
    if not token or not chat:
        raise RuntimeError("telegram env missing (TELEGRAM_COS_TOKEN / CAPTAIN_TELEGRAM_ID)")
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(
        urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                               data=data), timeout=20)


def _store_action(pid: str, prop: action_lane.ActionProposal) -> None:
    rec = {"lane": prop.lane, "subject": prop.subject,
           "situation": prop.situation,
           "steps": [{"kind": s.kind, "title": s.title, "payload": s.payload}
                     for s in prop.steps],
           "evidence": list(prop.evidence),
           "confidence": prop.confidence, "urgency": prop.urgency}
    _redis("SET", f"cabinet:action:{pid}", json.dumps(rec), "EX", "604800")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not _acquire_lock():
        print("done: another action-lane run holds the lock")
        return 0
    _load_env()

    now = dt.datetime.now(dt.timezone.utc)
    budget = MAX_PER_RUN

    signals = gather_signals(now)
    if not signals.strip():
        print("done: no fresh signals in window")
        return 0

    decided = set(sa.decided_subjects().keys())
    open_subjects = {  # any pending proposal's subject, action or draft
        (p.get("subject") or "") for p in pending_proposals() if isinstance(p, dict)}

    proposals = action_lane.propose_actions(
        signals, as_of=now.strftime("%Y-%m-%dT%H:%M:%SZ"), llm=_llm,
        decided_subjects=decided, open_subjects=open_subjects,
        budget_left=budget, covered_evidence=covered_evidence_refs())

    if args.dry_run:
        print(f"DRY RUN — {len(proposals)} card(s) would present:\n")
        for p in proposals:
            prop_ev = proposal_event(actor={"kind": "officer", "id": "officer:cos"},
                                     lane=p.lane, subject=p.subject,
                                     ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     action="action-card")
            print(action_lane.render_card(p, proposal_id(prop_ev)))
            print("\n" + "=" * 60 + "\n")
        return 0

    presented = 0
    actor = {"kind": "officer", "id": "officer:cos"}
    for p in proposals:
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prop_ev = proposal_event(actor=actor, lane=p.lane, subject=p.subject,
                                 ts=ts, action="action-card",
                                 refs=list(p.evidence))   # evidence = dedup identity
        pid = proposal_id(prop_ev)
        card = action_lane.render_card(p, pid)   # marker-stripped inside
        emit_consequence(**prop_ev)              # ledger FIRST (fail-closed order)
        _store_action(pid, p)
        _tg(card)
        presented += 1
        print(f"presented action card -> {p.subject} ({p.lane}, conf={p.confidence:.2f})")
    print(f"done: presented {presented} action card(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
