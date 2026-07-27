#!/opt/homebrew/bin/python3.12
"""healthchecks-drill — weekly synthetic-kill drill for the external dead-man.

WHY (F0.13 + the estate's own history): the pipe-watchdog's alarm path was dark
for days because the alarm was never exercised — and the FIRST manual drill
(2026-07-02) caught exactly that class again: API-created checks shipped with
EMPTY alert-channel lists, so DOWN alerts went nowhere. An alarm that is never
fired is not an alarm. This job fires one, weekly, end-to-end:

  1. /fail-ping the drill target check (send-only ping key).
  2. Verify via the management API that the check flipped DOWN and a flip was
     recorded (the alert pipeline engaged — channel assignment verified too).
  3. Recover for real: `launchctl kickstart` the service that owns that check
     so its next cycle sends the genuine alive ping (never a simulated one).
  4. Verify the check returns UP within DRILL_RECOVERY_TIMEOUT_S.
  5. Append one drill record line to ~/Library/Logs/cabinet/healthchecks-drill.log.

DRILL TARGET (re-pointed 2026-07-26, Captain arm-the-cabinet ruling): the
cabinet's OWN hourly dead-man — the `ledger-liveness` check pinged by
com.cabinet.ledger-liveness (cabinet/scripts/ledger-liveness-check.py:39,
services.yml row `ledger-liveness`, interval 3600s). It used to drill the
Captain's PERSONAL screenpipe sensor (`pipe-watchdog-alive` /
com.screenpipe.pipe-watchdog), which is why the row was parked as a
cries-wolf on any box with no personal source bound (#52). Both are
env-overridable (CABINET_DRILL_TARGET_SLUG / CABINET_DRILL_TARGET_LABEL) so a
deployment that DOES bind a personal source can point the drill back at it
without editing framework-adjacent code.

Self-alarming (who drills the drill): a `drill-failed` check (timeout 8d,
grace 1d, all channels) is pinged NORMALLY on drill success — so a drill that
stops running goes visibly late within ~9 days — and pinged /fail on any step
failure, which alerts the Captain immediately.

CREDLESS BOX (2026-07-26): no healthchecks keys in cabinet/.env means this
deployment has no external dead-man to drill. That is an honest absence, not a
failure, so it logs one DRILL_SKIP line and exits 0 — the credless idiom
retrieval-eval-nightly.sh already uses. It used to exit 1, which paged weekly
on every box that never configured healthchecks.

Secrets: keys are read from cabinet/.env at runtime (names-not-values
discipline everywhere else); nothing is rendered into plists or logs.
Requires no officer context; stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CABINET_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = CABINET_ROOT / "cabinet" / ".env"
LOG_FILE = Path.home() / "Library/Logs/cabinet/healthchecks-drill.log"
API = "https://healthchecks.io/api/v3"
TARGET_SLUG = os.environ.get("CABINET_DRILL_TARGET_SLUG", "ledger-liveness")
FAILSAFE_SLUG = "drill-failed"
WATCHDOG_LABEL = os.environ.get("CABINET_DRILL_TARGET_LABEL", "com.cabinet.ledger-liveness")
DOWN_TIMEOUT_S = 120
RECOVERY_TIMEOUT_S = 15 * 60


def _env(key: str) -> str:
    # A missing cabinet/.env is the credless-box case, not a crash: without the
    # guard this raised FileNotFoundError at IMPORT time, before main() could
    # report the honest skip.
    try:
        text = ENV_FILE.read_text()
    except OSError:
        return ""
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


API_KEY = _env("HEALTHCHECKS_API_KEY")
PING_KEY = _env("HEALTHCHECKS_PING_KEY")


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def api(path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"X-Api-Key": API_KEY, "Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def ping(slug: str, fail: bool = False) -> None:
    url = f"https://hc-ping.com/{PING_KEY}/{slug}" + ("/fail" if fail else "")
    urllib.request.urlopen(url, timeout=10).read()


def check_by_slug(slug: str) -> dict | None:
    for c in api("/checks/").get("checks", []):
        if c.get("slug") == slug:
            return c
    return None


def ensure_failsafe() -> None:
    api("/checks/", {
        "name": "cabinet: drill-failed", "slug": FAILSAFE_SLUG,
        "timeout": 8 * 86400, "grace": 86400,
        "desc": "Self-alarm for the weekly healthchecks drill: pinged normally on "
                "drill success (goes late if the drill stops running), /fail on any "
                "drill step failure (immediate alert).",
        "tags": "cabinet f0-13", "channels": "*", "unique": ["slug"],
    })


def wait_status(slug: str, want: str, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        c = check_by_slug(slug)
        if c and c.get("status") == want:
            return True
        time.sleep(10)
    return False


def main() -> int:
    if not API_KEY or not PING_KEY:
        # Honest absence, not a fault: this deployment has no external dead-man
        # to drill. Exit 0 so a never-configured box does not page every Sunday
        # (the #52 cries-wolf class this row was parked for).
        log("DRILL_SKIP: no healthchecks credentials in cabinet/.env — "
            "no external dead-man configured on this deployment")
        return 0
    ensure_failsafe()
    target = check_by_slug(TARGET_SLUG)
    if not target:
        log(f"DRILL FAIL: target check {TARGET_SLUG!r} not found")
        ping(FAILSAFE_SLUG, fail=True)
        return 1
    if not target.get("channels"):
        log(f"DRILL FAIL: {TARGET_SLUG} has NO alert channels — alerts go nowhere")
        ping(FAILSAFE_SLUG, fail=True)
        return 1

    log(f"drill start: /fail-pinging {TARGET_SLUG}")
    ping(TARGET_SLUG, fail=True)
    if not wait_status(TARGET_SLUG, "down", DOWN_TIMEOUT_S):
        log("DRILL FAIL: check did not flip DOWN within timeout")
        ping(FAILSAFE_SLUG, fail=True)
        return 1
    log("down confirmed; alert pipeline engaged — kickstarting real recovery")

    r = subprocess.run(
        ["launchctl", "kickstart", f"gui/{os.getuid()}/{WATCHDOG_LABEL}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log(f"DRILL FAIL: kickstart rc={r.returncode} {r.stderr.strip()[:120]}")
        ping(FAILSAFE_SLUG, fail=True)
        return 1
    if not wait_status(TARGET_SLUG, "up", RECOVERY_TIMEOUT_S):
        log("DRILL FAIL: check did not recover UP within timeout")
        ping(FAILSAFE_SLUG, fail=True)
        return 1

    log("DRILL PASS: down->alert->real-recovery->up, end to end")
    ping(FAILSAFE_SLUG)  # success heartbeat: a stopped drill goes late in ~9d
    return 0


if __name__ == "__main__":
    sys.exit(main())
