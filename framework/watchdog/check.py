#!/usr/bin/env python3
"""framework.watchdog.check — the independent OUTCOME-monitoring checker.

Evaluates every `Expectation` in `framework.watchdog.registry` against a real
`Probe` (files + Redis-via-redis-cli + clock), then routes each FAILED outcome
by its declared tier:

  AUTO_FIX        → run the expectation's deterministic-safe `auto_fix` (the
                    canonical safe action re-triggers the Chair with full
                    context; it NEVER sends outbound itself), then log.
  ESCALATE_CHAIR  → push ONE consolidated trigger to cabinet:triggers:cos
                    (matching triggers.sh::trigger_send), so the Chair triages.
                    Per P-Alerts-To-Chair, operational alerts go to the Chair —
                    NEVER to the Captain. The Chair escalates to the Captain only if stuck.
  DRIFT           → append a proposal to shared/interfaces/meta-cognition-
                    proposals.md via the meta-cognition lib's `mc_emit_proposal`
                    (proposal-only, Captain-gated; not an alert).

Independence is the whole point: STDLIB ONLY, and it imports NOTHING it watches
(no framework.frontdoor, no personal-source libs, no org_runtime). When a watched
system breaks, the checker keeps running. It is cheap — it reads logs + Redis +
file mtimes; it never polls Graph/Vercel/an LLM.

Anti-thrash: every routed action is deduped on (expectation_id, action) within
a cooldown window via a Redis marker, so a persistently-broken outcome fires its
fix/escalation ONCE per cooldown, not every 30-min cycle.

Dead-man's-switch: on every run (pass or fail) the checker stamps its own
heartbeat `cabinet:watchdog:outcome:heartbeat` = now (ISO). A SEPARATE, even
simpler survivor (the personal-source adapter's pipe-watchdog, calendar-scheduled
+ already proven immune to the StartInterval throttle) checks that heartbeat and
pings the Chair if it goes stale. Who-watches-the-watchman.

Usage:
  python3 -m framework.watchdog.check            # evaluate + route + heartbeat
  python3 -m framework.watchdog.check --dry-run  # evaluate + print, NO side-effects
  python3 -m framework.watchdog.check --json     # machine-readable result
Exit code is always 0 when the checker itself ran (a failed OUTCOME is data, not
a checker error) — so launchd never marks the watchdog "failed" for doing its job.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Make the repo importable when run as a file (launchd uses `-m`, but tests and
# manual runs may invoke the path directly).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.env import captain_name, captain_timezone  # noqa: E402
from framework import env  # noqa: E402  # roster-resolved chair role
from framework.watchdog import registry  # noqa: E402
from framework.watchdog.registry import CheckResult, Probe, Tier  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Config — resolved from env with Mac-native defaults. NO secrets read here; the
# only outbound is a Redis trigger (localhost), which the Chair turns into a
# gated send. The bot token never enters this process.
# ─────────────────────────────────────────────────────────────────────────────
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
CHAIR_OFFICER = os.environ.get("CABINET_CHAIR_OFFICER") or env.chair_officer()
HEARTBEAT_KEY = "cabinet:watchdog:outcome:heartbeat"
COOLDOWN_KEY_PREFIX = "cabinet:watchdog:outcome:cooldown:"
# Don't re-fire the same (expectation, action) within this many seconds. Long
# enough that a persistently-broken outcome pings the Chair a few times a day,
# not every cycle.
COOLDOWN_S = int(os.environ.get("WATCHDOG_COOLDOWN_S", str(3 * 3600)))
# Env wins (the run-outcome-watchdog.sh wrapper exports it); else THE one
# resolver over instance platform.yml `captain_timezone` (LOUD UTC fallback) —
# TZ unification 2026-07-18: this used to fall to Europe/Berlin while the
# gate/engine fell to UTC.
CAPTAIN_TZ = os.environ.get("CABINET_CAPTAIN_TZ") or captain_timezone()
# Path to the meta-cognition lib (sourced for DRIFT-tier proposals).
MC_LIB = str(_REPO_ROOT / "cabinet/scripts/meta-cognition/lib.sh")
TRIGGERS_LIB = str(_REPO_ROOT / "cabinet/scripts/lib/triggers.sh")


def _redis(*args: str) -> str:
    """Run a redis-cli command, return stripped stdout, "" on any failure."""
    try:
        r = subprocess.run(
            ["redis-cli", "-h", REDIS_HOST, "-p", REDIS_PORT, *args],
            capture_output=True, text=True, timeout=10,
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# The real Probe — the only place that touches the OS / Redis. Mirrors the
# abstract Probe in registry.py; every method degrades to a benign empty value.
# ─────────────────────────────────────────────────────────────────────────────
class RealProbe(Probe):
    def __init__(self, *, allow_side_effects: bool = True):
        self._allow = allow_side_effects
        # Track whether the Captain timezone resolved. If it did NOT (bad TZ name
        # or stripped tzdata), local_now() would silently fall back to UTC and the
        # briefing slot math (07:30/19:30 LOCAL) would be off by the UTC offset,
        # false-failing every cycle all day (review MEDIUM 2026-06-29). We expose
        # tz_ok() so the briefing verify can SKIP instead of computing wrong.
        self._tz_ok = True
        try:
            from zoneinfo import ZoneInfo
            self._tz = ZoneInfo(CAPTAIN_TZ)
        except Exception:
            self._tz = _dt.timezone.utc
            self._tz_ok = False

    def now(self) -> _dt.datetime:
        return _dt.datetime.now(_dt.timezone.utc)

    def local_now(self) -> _dt.datetime:
        return self.now().astimezone(self._tz)

    def tz_ok(self) -> bool:
        return self._tz_ok

    def read_text(self, path: str) -> str:
        try:
            return Path(path).read_text(errors="replace")
        except OSError:
            return ""

    def file_mtime(self, path: str) -> Optional[float]:
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    def listdir(self, path: str) -> Optional[list[str]]:
        # None = not observable (missing dir / permission), [] = exists and
        # empty — the tri-state the evidence-store facts verify needs to
        # distinguish "plane absent" (skip) from an affirmative observation.
        try:
            return sorted(os.listdir(path))
        except OSError:
            return None

    def redis_get(self, key: str) -> str:
        v = _redis("GET", key)
        return "" if v in ("", "(nil)") else v

    def redis_keys(self, pattern: str) -> list[str]:
        out = _redis("KEYS", pattern)
        return [k for k in out.splitlines() if k]

    def launchd_loaded(self, label: str) -> Optional[bool]:
        try:
            uid = os.getuid()
            r = subprocess.run(
                ["launchctl", "print", f"gui/{uid}/{label}"],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except Exception:
            return None

    # WHY None AND {} ARE DIFFERENT (2026-07-30). Collapsing them into {} is
    # what let the 2026-07-25 teardown pass as a launchd blind spot for five
    # days: with every label disabled, booted out and its plist removed,
    # `launchctl list` answered perfectly well with zero cabinet rows, and the
    # registry read that as "cannot see launchd" and switched off BOTH launchd
    # arms — including declared-but-not-loaded, the one check written for
    # exactly that event. An answered scan holding nothing is a measurement,
    # and a very loud one: every declared service is unloaded.
    #
    # THE MIRROR-IMAGE FAILURE, closed at the same time: `launchctl list`
    # reports the CALLER'S domain. The fleet lives in `gui/$(id -u)` (every
    # plist under cabinet/launchd is a user agent), so the same command run as
    # root — a LaunchDaemon, a sudo invocation, a root cron — answers cleanly
    # with zero cabinet labels on a perfectly healthy box. Under the new
    # contract that would page "declared in services.yml but not loaded" for
    # every row: a false alarm with a false reason, which is how a real one
    # stops being read. Root therefore reports NOT OBSERVABLE, because from
    # root's domain it genuinely is not.
    def launchctl_list(self) -> Optional[dict]:
        """ONE `launchctl list` call → every com.cabinet.* label with its pid +
        last exit status (lane-ops 2026-07-04, feeds the no-silent-cron exit-
        status + declared-but-not-loaded checks). Output rows are
        `PID\\tStatus\\tLabel`. None = launchd could not be asked; {} = it
        answered and knows no com.cabinet.* label at all."""
        try:
            if os.geteuid() == 0:
                return None
            r = subprocess.run(["launchctl", "list"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                return None
            out: dict = {}
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) != 3 or not parts[2].startswith("com.cabinet."):
                    continue
                pid_s, status_s, label = parts
                try:
                    status: Optional[int] = int(status_s)
                except ValueError:
                    status = None  # '-' / unparseable → unknown, never flagged
                pid = int(pid_s) if pid_s.isdigit() else None  # '-' = not running
                out[label] = {"pid": pid, "status": status}
            return out
        except Exception:
            return None

    def trigger_chair(self, message: str) -> bool:
        """Push a trigger to the Chair's stream via the SAME mechanism as
        triggers.sh::trigger_send (XADD to cabinet:triggers:<chair>, group
        officer-<chair>). We shell to bash + source triggers.sh so we reuse its
        exact key derivation, consumer-group creation, and the control-plane
        wake — rather than re-implementing XADD here and drifting from it.

        Also records, on ``self._last_chair_delivery``, whether the Chair had a
        LIVE consumer session at send time ("live" / "absent" / "unknown", from
        triggers.sh::trigger_consumer_state). The return value keeps its old
        meaning — "the trigger is durably on the stream" — because that is a real
        and separate fact; the router reads the side channel to decide whether
        the page can actually be READ. Two facts, two signals: collapsing them is
        exactly the enqueued-is-delivered laundering this closes.

        In --dry-run (allow_side_effects=False) this is a no-op returning True so
        the routing logic is fully exercised without perturbing the live stream."""
        if not self._allow:
            self._last_chair_delivery = "unknown"
            return True
        self._last_chair_delivery = "unknown"
        try:
            # OFFICER_NAME labels the trigger sender in the envelope. The trailing
            # printf reports the consumer state on STDOUT (trigger_send leaves
            # stdout clean, so this is unambiguous) without disturbing the
            # stderr-means-failure contract every other caller relies on.
            script = (
                f'. "{TRIGGERS_LIB}" && '
                f'OFFICER_NAME=outcome-watchdog trigger_send "{CHAIR_OFFICER}" "$WATCHDOG_MSG" && '
                f'printf "CHAIR_DELIVERY=%s\\n" "${{TRIGGER_SEND_DELIVERY:-unknown}}"'
            )
            env = dict(os.environ)
            env["WATCHDOG_MSG"] = message
            env.setdefault("REDIS_HOST", REDIS_HOST)
            env.setdefault("REDIS_PORT", REDIS_PORT)
            # Ensure redis-cli resolves under launchd's minimal PATH.
            env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
            r = subprocess.run(["/bin/bash", "-c", script],
                               capture_output=True, text=True, timeout=20, env=env)
            for line in (r.stdout or "").splitlines():
                if line.startswith("CHAIR_DELIVERY="):
                    state = line.split("=", 1)[1].strip()
                    if state in ("live", "absent", "unknown"):
                        self._last_chair_delivery = state
            # trigger_send writes to STDERR only on XADD failure; clean stderr =
            # success. A non-zero rc or any stderr → treat as not-enqueued.
            return r.returncode == 0 and not (r.stderr or "").strip()
        except Exception:
            return False

    # ── side-effecting helpers used by the router (not part of the abstract
    #    Probe surface, but live on the real probe so tests' stubs don't need
    #    them) ──────────────────────────────────────────────────────────────
    def stamp_heartbeat(self) -> None:
        if self._allow:
            _redis("SET", HEARTBEAT_KEY, self.now().strftime("%Y-%m-%dT%H:%M:%SZ"))

    def cooldown_active(self, eid: str, action: str) -> bool:
        return bool(self.redis_get(f"{COOLDOWN_KEY_PREFIX}{eid}:{action}"))

    def set_cooldown(self, eid: str, action: str) -> None:
        if self._allow:
            _redis("SET", f"{COOLDOWN_KEY_PREFIX}{eid}:{action}",
                   self.now().strftime("%Y-%m-%dT%H:%M:%SZ"), "EX", str(COOLDOWN_S))

    def emit_drift_proposal(self, title: str, body: str) -> bool:
        """Append a DRIFT-tier proposal via the meta-cognition lib's gated sink
        (mc_emit_proposal). Proposal-only, Captain-gated — never an alert."""
        if not self._allow:
            return True
        try:
            script = (
                f'. "{MC_LIB}" && mc_emit_proposal detect "$WD_TITLE" "$WD_BODY"'
            )
            env = dict(os.environ)
            env["WD_TITLE"] = title
            env["WD_BODY"] = body
            env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
            r = subprocess.run(["/bin/bash", "-c", script],
                               capture_output=True, text=True, timeout=20, env=env)
            return r.returncode == 0
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Evidence receipt for ROUTED failures (evidence program Phase 2 Batch B —
# receipt-class: the failure + routing already happened). The checker's
# independence law (stdlib-only, imports NOTHING it watches) holds: the
# receipt is a subprocess MODULE-exec of the typed lens emitter
# (framework/watchdog/receipts.py) from the repo root, so the org→evidence
# mirror signs it inside the child process (path-exec never mirrors —
# repo root off sys.path silently skips the mirror). Emitted ONLY when a
# routed action actually FIRED: cooldown-skipped repeats, all-green sweeps,
# and the heartbeat stamp are exhaust and never recorded, so volume is
# bounded by the same 3h cooldown that bounds triggers (typ. 0-5/day).
# Best-effort by contract: never raises, never blocks routing — a broken
# evidence plane must not stop the Chair escalation.
# ─────────────────────────────────────────────────────────────────────────────
OUTCOME_RECEIPT_EVENT = "watchdog_outcome_failed"


def _emit_outcome_receipt(eid: str, tier: str, action: str, detail: str) -> None:
    try:
        payload = json.dumps({
            "expectation_id": eid,
            "tier": tier,
            "action": action,
            "detail": str(detail)[:200],
        }, ensure_ascii=False)
        subprocess.run(
            [sys.executable, "-m", "framework.watchdog.receipts",
             OUTCOME_RECEIPT_EVENT, payload],
            capture_output=True, text=True, timeout=15, cwd=str(_REPO_ROOT),
        )
    except Exception:
        pass  # receipt is best-effort; the routed action already happened


def _receipts_allowed(probe) -> bool:
    """True only for a live probe with side effects enabled. RealProbe sets
    ``_allow`` (False under --dry-run); test stubs without the attribute get
    False, so no test ever spawns an emit subprocess by accident."""
    return getattr(probe, "_allow", False) is True


# ─────────────────────────────────────────────────────────────────────────────
# Router — given a CheckResult + its Expectation, take the tier's action with
# anti-thrash dedup. Returns a one-line "what I did" string for the run report.
# ─────────────────────────────────────────────────────────────────────────────
def _chair_read_it(probe) -> bool:
    """Was the Chair escalation delivered to something that can actually READ it?

    ``trigger_chair`` returning True means the trigger is durably on the stream —
    NOT that anyone is there. A cooldown burnt on an unread page is how a live
    outage goes quiet for hours: the finding is suppressed for the cooldown
    window while the only recipient is gone.

    "absent" is the ONLY state that withholds the cooldown. "unknown" (no tmux to
    observe with — Docker, CI, a remote box) keeps the pre-change behaviour,
    because a detector that cannot see must not invent a verdict; and a stub
    probe without the attribute reads as "unknown" via getattr, so every existing
    test double is unaffected by construction."""
    return getattr(probe, "_last_chair_delivery", "unknown") != "absent"


_UNDELIVERED_NOTE = ("queued to the Chair's stream but NO live Chair consumer "
                     "(enqueued is not delivered — cooldown deliberately NOT set, "
                     "so this re-escalates next sweep)")


def route_failure(probe: RealProbe, exp, result: CheckResult) -> str:
    tier = exp.tier
    cap = captain_name()  # launcher-agnostic: the Captain's display name for alert copy
    # Per-slot dedup scope: when a verify reports a slot_id (the briefing does),
    # scope the cooldown to THAT slot — so a handled AM-slot failure never
    # suppresses a fresh PM-slot failure, and a flagged+handled slot never
    # re-alerts on later cycles. Expectations without a slot_id dedup per-id.
    scope = result.fix_hint.get("slot_id", "")
    af = "autofix:" + scope if scope else "autofix"
    esc = "escalate:" + scope if scope else "escalate"
    dr = "drift:" + scope if scope else "drift"

    if tier is Tier.AUTO_FIX:
        if probe.cooldown_active(exp.id, af):
            return f"auto-fix SKIPPED (cooldown active, slot={scope or 'n/a'}) — {result.detail}"
        did = exp.auto_fix(probe, result) if exp.auto_fix else None
        if did:
            probe.set_cooldown(exp.id, af)
            # Also suppress the escalation fallback for this window — otherwise the
            # NEXT cycle (autofix on cooldown) falls through and double-pings the
            # Chair with a second message for the same failure (review MINOR).
            probe.set_cooldown(exp.id, esc)
            if _receipts_allowed(probe):
                _emit_outcome_receipt(exp.id, tier.value, "auto_fix_fired",
                                      result.detail)
            return f"AUTO-FIX fired → Chair re-trigger: {result.detail}"
        # Auto-fix declined/failed → fall back to a plain Chair escalation so the
        # failure is never silently dropped.
        if not probe.cooldown_active(exp.id, esc):
            ok = probe.trigger_chair(
                f"OUTCOME-WATCHDOG: auto-fix for '{exp.id}' could not run — "
                f"{result.detail}. Please handle (gather-then-decide; do not DM {cap}).")
            if ok and not _chair_read_it(probe):
                return f"auto-fix declined → escalation {_UNDELIVERED_NOTE}: {result.detail}"
            if ok:
                probe.set_cooldown(exp.id, esc)
                if _receipts_allowed(probe):
                    _emit_outcome_receipt(exp.id, tier.value,
                                          "auto_fix_declined_escalated",
                                          result.detail)
                return f"auto-fix declined → ESCALATED to Chair: {result.detail}"
        return f"auto-fix declined, escalation on cooldown — {result.detail}"

    if tier is Tier.ESCALATE_CHAIR:
        if probe.cooldown_active(exp.id, esc):
            return f"escalation SKIPPED (cooldown active) — {result.detail}"
        msg = (
            f"OUTCOME-WATCHDOG — a watched outcome FAILED its verification:\n"
            f"• Expectation: {exp.what}\n"
            f"• Finding: {result.detail}\n"
            f"This is operational — triage it (gather-then-decide), fix the root "
            f"cause, and escalate to {cap} ONLY if you are genuinely stuck. The "
            f"process may be 'green' while the OUTCOME did not happen."
        )
        ok = probe.trigger_chair(msg)
        if ok and not _chair_read_it(probe):
            return f"escalation {_UNDELIVERED_NOTE}: {result.detail}"
        if ok:
            probe.set_cooldown(exp.id, esc)
            if _receipts_allowed(probe):
                _emit_outcome_receipt(exp.id, tier.value, "escalated",
                                      result.detail)
            return f"ESCALATED to Chair: {result.detail}"
        return f"escalation FAILED to enqueue — {result.detail}"

    if tier is Tier.DRIFT:
        if probe.cooldown_active(exp.id, dr):
            return f"drift-note SKIPPED (cooldown active) — {result.detail}"
        title = f"Outcome-watchdog drift: {exp.id}"
        body = (
            f"The outcome-monitoring watchdog flagged a soft drift signal "
            f"(DRIFT tier — note, not an alert):\n\n"
            f"- **Expectation:** {exp.what}\n"
            f"- **Finding:** {result.detail}\n\n"
            f"Verify whether the underlying discipline (e.g. real-time "
            f"decision-logging) silently lapsed, and if so why the hard "
            f"enforcement (post-tool-use hook) did not catch it."
        )
        ok = probe.emit_drift_proposal(title, body)
        if ok:
            probe.set_cooldown(exp.id, dr)
            if _receipts_allowed(probe):
                _emit_outcome_receipt(exp.id, tier.value, "drift_note",
                                      result.detail)
            return f"DRIFT note → meta-cognition-proposals.md: {result.detail}"
        return f"drift-note FAILED to write — {result.detail}"

    return f"UNKNOWN tier {tier!r} — {result.detail}"


# ─────────────────────────────────────────────────────────────────────────────
# Main sweep
# ─────────────────────────────────────────────────────────────────────────────
def run(probe: Optional[RealProbe] = None, *, dry_run: bool = False) -> dict:
    probe = probe or RealProbe(allow_side_effects=not dry_run)
    results = []
    actions = []
    for exp in registry.EXPECTATIONS:
        try:
            res = exp.verify(probe)
        except Exception as e:  # a broken verify must not kill the whole sweep
            res = CheckResult(exp.id, False,
                             f"verify raised {type(e).__name__}: {str(e)[:160]}")
        record = {
            "id": res.expectation_id, "ok": res.ok, "skipped": res.skipped,
            "tier": exp.tier.value, "detail": res.detail,
        }
        if not res.ok and not res.skipped:
            action = route_failure(probe, exp, res)
            record["action"] = action
            actions.append(action)
        results.append(record)

    # Dead-man's-switch heartbeat — stamp AFTER the sweep so a hung verify that
    # never returns also never stamps (the heartbeat going stale is exactly what
    # the survivor catches). In dry-run we don't stamp.
    if not dry_run:
        probe.stamp_heartbeat()
        # FILE pulse for the out-of-fleet fleetwatch dead-man. Deliberately a
        # SECOND store rather than a second reader of the Redis key above: Redis
        # is a live service on this box, and a watcher that reads it cannot tell
        # "the fleet is gone" from "Redis is gone". A file survives both. Wrapped
        # because a heartbeat must never cost the sweep that earned it.
        try:
            from framework.liveness import deadman as _dm

            _dm.pulse("outcome-watchdog")
        except Exception:
            pass

    return {
        "ts": probe.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": dry_run,
        "checked": len(results),
        "failed": sum(1 for r in results if not r["ok"] and not r["skipped"]),
        "skipped": sum(1 for r in results if r["skipped"]),
        "results": results,
        "actions": actions,
    }


def _human(report: dict) -> str:
    L = [f"[{report['ts']}] outcome-watchdog "
         f"(checked={report['checked']} failed={report['failed']} "
         f"skipped={report['skipped']}{' DRY-RUN' if report['dry_run'] else ''})"]
    for r in report["results"]:
        if r["skipped"]:
            mark = "skip"
        elif r["ok"]:
            mark = "OK"
        else:
            mark = "FAIL"
        line = f"  [{mark}] {r['id']} ({r['tier']}): {r['detail']}"
        if r.get("action"):
            line += f"\n        → {r['action']}"
        L.append(line)
    return "\n".join(L)


# Hard wall-clock deadline for one whole sweep. A verify shouldn't hang (it only
# reads files/Redis/mtimes), but a stalled NFS path or a blocked redis-cli could
# wedge it. If the sweep exceeds this, we exit cleanly so launchd's slot frees
# (a wedged process makes launchd skip subsequent fires) and the next cycle +
# the dead-man's switch recover. Override via WATCHDOG_DEADLINE_S.
SWEEP_DEADLINE_S = int(os.environ.get("WATCHDOG_DEADLINE_S", "240"))


def _install_deadline(seconds: int) -> None:
    """Arm a SIGALRM that aborts a hung sweep. Best-effort + main-thread-only
    (launchd runs us on the main thread); a platform without SIGALRM is a no-op."""
    try:
        import signal

        def _bail(signum, frame):
            sys.stderr.write(
                f"outcome-watchdog: sweep exceeded {seconds}s deadline — "
                f"aborting so the launchd slot frees (dead-man's switch + next "
                f"cycle recover)\n")
            os._exit(0)  # clean exit code; never leave a wedged process holding the slot

        signal.signal(signal.SIGALRM, _bail)
        signal.alarm(seconds)
    except (ImportError, ValueError, AttributeError):
        pass  # no SIGALRM (or not main thread) — rely on the dead-man's switch


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Cabinet outcome-monitoring watchdog")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate + print, take NO side-effects (no triggers, "
                         "no proposals, no heartbeat stamp)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    _install_deadline(SWEEP_DEADLINE_S)
    report = run(dry_run=args.dry_run)
    try:  # sweep finished — disarm the deadline before printing/exiting
        import signal
        signal.alarm(0)
    except (ImportError, ValueError, AttributeError):
        pass
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_human(report), flush=True)
    return 0  # always 0 when the checker ran — a failed outcome is data


if __name__ == "__main__":
    sys.exit(main())
