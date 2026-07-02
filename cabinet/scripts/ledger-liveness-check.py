#!/usr/bin/env python3
"""ledger-liveness-check.py — the F0.7 evidence-starvation dead-man (skeleton).

THE INVARIANT (blueprint §4.2, the twice-paid n=0 lesson made standing): if the
org is PRESENTING proposals and the Captain's channel is ALIVE but zero
superseding decisions are landing on the consequence ledger, evidence capture
has been severed — the exact failure that froze every screenpipe autonomy lane
at n=0 and left the cabinet ledger decision-less for weeks. Staleness is loss
of proof; it must page, never accumulate silently.

Hourly under launchd (com.cabinet.ledger-liveness, services.yml). Pings the
external healthchecks 'ledger-liveness' check: normal ping when healthy,
/fail on starvation (healthchecks emails the Captain independent of
Redis/Telegram/this Mac). Auto-demote wiring joins when graduation goes live
(B2.9+); until then the page IS the response.

STARVATION = all four, together:
  1. pending draft proposals exist on the ledger, and
  2. the oldest pending is > STARVE_H old (fresh pendings are normal), and
  3. the inbound poller process is alive (channel up — so silence is not
     explained by an outage the other dead-men already catch), and
  4. zero superseding decisions (approved/edited/rejected) landed in STARVE_H.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from framework.acting import loop  # noqa: E402

STARVE_H = int(os.environ.get("LEDGER_STARVE_HOURS", "24"))
SLUG = "ledger-liveness"


def _iso_age_h(ts: str) -> float:
    """Age in hours. FAIL-LOUD direction: an unparseable timestamp on a PENDING
    proposal must count as OLD (starvation-triggering), never silently fresh —
    the first live run parsed 4 pendings as 0.0h (fractional-seconds ISO) which
    would have made starvation untriggerable. Handles Z, offsets, fractions."""
    try:
        s = (ts or "").strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        t = datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return float(STARVE_H * 100)  # unparseable ⇒ treat as ancient, not fresh


def _poller_alive() -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", "officer-inbound-poller.py"],
                           capture_output=True, text=True, timeout=10)
        return bool(r.stdout.strip())
    except Exception:
        return False


def _ping(fail: bool) -> str:
    key = os.environ.get("HEALTHCHECKS_PING_KEY", "")
    if not key:
        return "no-ping-key"
    url = f"https://hc-ping.com/{key}/{SLUG}" + ("/fail" if fail else "")
    try:
        urllib.request.urlopen(url, timeout=10).read()
        return "fail-pinged" if fail else "pinged"
    except Exception as e:
        return f"ping-error: {e!r}"


def main() -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=STARVE_H * 2)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = loop.read_ledger(since=since)
    pending = loop.pending_proposals(rows=rows)
    # exclude synthetic verification artifacts from the math
    pending = [p for p in pending
               if "synthetic" not in str(p.get("lane", "")) ]
    oldest_h = max((_iso_age_h(p.get("ts", "")) for p in pending), default=0.0)
    decisions = [
        e for e in rows
        if isinstance(e, dict)
        and (e.get("proposal") or {}).get("decision") in ("approved", "edited", "rejected")
        and "synthetic" not in str(e.get("lane", ""))
        and _iso_age_h((e.get("proposal") or {}).get("decided_at") or e.get("ts", "")) <= STARVE_H
    ]
    alive = _poller_alive()
    starving = bool(pending) and oldest_h > STARVE_H and alive and not decisions
    status = _ping(fail=starving)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] pending={len(pending)} oldest={oldest_h:.1f}h "
          f"decisions_{STARVE_H}h={len(decisions)} poller_alive={alive} "
          f"STARVING={starving} hc={status}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
