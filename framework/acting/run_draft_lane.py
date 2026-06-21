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
import os
import sys
import json
import datetime
import urllib.request
import urllib.parse

sys.path.insert(0, "/Users/nate/captains-cabinet")
sys.path.insert(0, os.path.expanduser("~/.screenpipe/pipes/_shared"))

from framework.acting import loop, screenpipe_adapter as sa
from framework.acting.loop import proposal_id, pending_proposals
from framework.fidelity.consequence import emit_consequence

MAX = int(os.environ.get("DRAFT_LANE_MAX", "1"))
TOKEN = os.environ["TELEGRAM_COS_TOKEN"]
CHAT = os.environ["CAPTAIN_TELEGRAM_ID"]


def _tg(text: str) -> dict:
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data)
    return json.load(urllib.request.urlopen(req, timeout=20))


def _present(thread: dict, draft: str, prop: dict) -> None:
    last = thread.get("last", {})
    chan = "Teams" if last.get("source") == "teams" else "email"
    their = (last.get("text", "") or "").strip()[:400]
    pid = proposal_id(prop)
    _tg(
        f"📝 Draft reply to {thread['person']} ({chan})\n\n"
        f"— they wrote:\n{their}\n\n"
        f"— my draft (your voice):\n{draft}\n\n"
        f"Reply:  send  /  edit: <your version>  /  skip: <why>\n"
        f"·{pid}·"
    )


def main() -> None:
    actor = {"kind": "officer", "id": "cos"}
    open_subjects = {p.get("subject") for p in pending_proposals()}
    threads = sa.find_threads(hours=72)
    presented = 0
    for t in threads:
        if presented >= MAX:
            break
        if t["slug"] in open_subjects:
            continue  # already awaiting your decision
        ctx = sa.gather(t)
        draft = sa.draft_fn(t, ctx)
        if not draft:
            continue
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        loop.propose(
            thread_ref=t, subject=t["slug"], ts=ts, actor=actor,
            lane=sa.lane_for(t),
            gather=lambda _t, _ctx=ctx: _ctx,
            draft_fn=lambda _t, _c, _d=draft: _d,
            present=lambda d, p, _t=t: _present(_t, d, p),
            emit=lambda **ev: emit_consequence(**ev),
        )
        presented += 1
        print(f"presented draft -> {t['person']} ({sa.lane_for(t)})")
    print(f"done: presented {presented} draft(s)")


if __name__ == "__main__":
    main()
