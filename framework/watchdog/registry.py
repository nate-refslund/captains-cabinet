"""framework.watchdog.registry — the OUTCOME-expectations registry.

The declarative heart of the outcome-monitoring watchdog. An *expectation* is a
statement of what should be TRUE in the world ("the briefing was DELIVERED to
the Captain twice today"), NOT a statement that a process ran. This is the structural
answer to the silent-failure class that every existing monitor misses: the
briefing cron exits 0, launchd shows "active", pipe-health says green — because
they all check the PROCESS. Nothing checked the OUTCOME. On 2026-06-29 the 07:30
briefing job ran clean (exit 0) but its Telegram send 400'd; the backlog
snowballed to 77 recovered-but-undelivered items over days, fully silent.

Design goals (why it is shaped this way):
  * STDLIB ONLY. No third-party imports, and — load-bearing — it NEVER imports
    the systems it watches (framework.frontdoor, screenpipe libs, org_runtime).
    A watchdog built on top of the thing it watches dies with it. Each verify
    reads a FILE, a Redis key (via redis-cli subprocess), or a launchd/log
    timestamp — the cheapest possible probe, never a Graph/Vercel/LLM call.
    (The in-repo imports are ``framework.env.captain_name`` + ``state_dir`` +
    ``watchdog_config_path`` — de-nate / source-adapter resolvers: import-light
    stdlib at load, any lazy read degrades to a generic default on any failure,
    so the watchdog never dies for them.)
  * EXTENSIBLE BY ADDING A ROW. An expectation is one `Expectation(...)` literal
    in `_CATALOG`. Add an outcome to watch = append a row with its id, what,
    cadence, tier, a verify function, and a response policy. Nothing else.
  * MACHINERY HERE, DATA IN THE INSTANCE (egg R017). The deployment-specific
    tables — briefing slot times, the fulltime-officer roster, the
    pipe-freshness table, and which catalog rows are enabled — are read from
    instance/config/watchdog.yml (narrow stdlib parse, generic fail-safe
    defaults), so the framework organ carries no launcher data.
  * COMPOSE, DON'T DUPLICATE. Where a signal is already emitted (overdue
    reflections via the schedule last-run stamps the anomaly-scan reads), the
    verify reuses that source rather than re-deriving it.

The checker (`framework.watchdog.check`) imports `EXPECTATIONS` + `Probe`,
evaluates each expectation against a `Probe` (the thin I/O surface — files +
Redis + clock), and routes the failures by tier. Tests inject a fake Probe so
the whole evaluation runs with zero network / zero real Redis.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import json
import os
import re
from pathlib import Path
from typing import Callable, Optional

from framework.env import captain_name, state_dir, watchdog_config_path


def _cabinet_root() -> Path:
    """The deployment root — ``CABINET_ROOT`` env, else this file's repo root
    (``framework/watchdog/registry.py`` → parents[2]). No hardcoded home path;
    mirrors ``framework.env`` / ``framework.authority.posture.cabinet_root``."""
    return Path(os.environ.get("CABINET_ROOT") or Path(__file__).resolve().parents[2])


# ─────────────────────────────────────────────────────────────────────────────
# Tiers — how a FAILED expectation is responded to. The tier is a property of
# the expectation (declared in the registry), not decided at check time, so the
# routing is auditable from the registry alone.
# ─────────────────────────────────────────────────────────────────────────────
class Tier(enum.Enum):
    AUTO_FIX = "auto-fix"      # deterministic-safe remediation, then log. (a)
    ESCALATE_CHAIR = "chair"   # judgment needed → cabinet:triggers:cos.       (b)
    DRIFT = "drift"            # principle/governance drift → meta-cognition.  (d)
    # NOTE: there is deliberately NO direct-to-Captain tier. Per P-Alerts-To-Chair,
    # every operational alert routes to the Chair; the Chair escalates to the
    # Captain only if genuinely stuck (response tier (c) is the Chair's call, not ours).


# ─────────────────────────────────────────────────────────────────────────────
# Result of evaluating one expectation. `ok=True` → the outcome happened.
# `ok=False` → the outcome did NOT happen (or could not be verified); `detail`
# is the human-readable evidence the Chair (or the log) needs, and `fix_hint`
# is an optional structured payload an AUTO_FIX response uses.
# ─────────────────────────────────────────────────────────────────────────────
@dataclasses.dataclass
class CheckResult:
    expectation_id: str
    ok: bool
    detail: str
    # When ok is False and tier is AUTO_FIX, the checker calls the expectation's
    # `auto_fix(probe, result)` — fix_hint carries any structured context that
    # remediation needs (e.g. which run_mode briefing to re-trigger).
    fix_hint: dict = dataclasses.field(default_factory=dict)
    # `skipped` distinguishes "outcome verified false" from "not applicable right
    # now" (e.g. the PM briefing check before 19:30, or killswitch active). A
    # skipped check is neither a pass nor a failure — it is simply not evaluated.
    skipped: bool = False


@dataclasses.dataclass
class Expectation:
    """One declared outcome the cabinet must keep TRUE.

    Fields:
      id        stable slug (used in logs, dedup keys, proposal ids).
      what      one-line human statement of the outcome (shown to the Chair).
      cadence_s how often this outcome must (re)occur, in seconds. Informational
                for the registry/report; each verify encodes its own freshness
                window because "delivered twice today" is not a simple interval.
      tier      Tier — how a failure is responded to.
      verify    fn(probe) -> CheckResult. MUST be cheap + side-effect-free
                (reads only). Receives the shared Probe.
      auto_fix  fn(probe, CheckResult) -> str|None. ONLY set for AUTO_FIX tier.
                Performs the deterministic-safe remediation and returns a
                one-line description of what it did (or None if it declined).
                Must itself be deterministic-safe — never send outbound, never
                touch anything risky; the canonical safe action is to re-push a
                trigger to the Chair's stream with full context.
    """
    id: str
    what: str
    cadence_s: int
    tier: Tier
    verify: Callable[["Probe"], CheckResult]
    auto_fix: Optional[Callable[["Probe", CheckResult], Optional[str]]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Probe — the ENTIRE I/O surface the verifies are allowed to touch. Keeping it
# behind one injectable object is what makes the whole registry testable with a
# fake (no real Redis, no real files) AND what guarantees a verify can't quietly
# reach for the network. The real implementation lives in check.py; tests pass a
# stub with the same method names.
# ─────────────────────────────────────────────────────────────────────────────
class Probe:
    """Read-only I/O surface (files + Redis + clock). Implemented in check.py.

    Every method is degrade-safe: on any error it returns a benign empty value
    (None / "" / []) rather than raising, so a verify never crashes the whole
    sweep on one unreadable source — it reports the outcome as unverifiable.
    """

    def now(self) -> _dt.datetime:  # pragma: no cover - trivial
        raise NotImplementedError

    def local_now(self) -> _dt.datetime:  # pragma: no cover
        """`now()` converted to the Captain's timezone (platform.yml)."""
        raise NotImplementedError

    def tz_ok(self) -> bool:  # pragma: no cover
        """True if the Captain timezone resolved (so local_now() is reliable).
        False → the briefing slot math would be wrong; the verify SKIPs. Default
        True for probes that don't override it (e.g. the in-memory test stub)."""
        return True

    def read_text(self, path: str) -> str:  # pragma: no cover
        """Full file contents, or "" if missing/unreadable."""
        raise NotImplementedError

    def file_mtime(self, path: str) -> Optional[float]:  # pragma: no cover
        """Epoch seconds of a file's last modification, or None."""
        raise NotImplementedError

    def redis_get(self, key: str) -> str:  # pragma: no cover
        """GET a Redis key as a string, or "" if unset/unreachable."""
        raise NotImplementedError

    def redis_keys(self, pattern: str) -> list[str]:  # pragma: no cover
        """KEYS matching a glob, or [] if unreachable."""
        raise NotImplementedError

    def launchd_loaded(self, label: str) -> Optional[bool]:  # pragma: no cover
        """True/False if a launchd label is loaded; None if undeterminable."""
        raise NotImplementedError

    def launchctl_list(self) -> dict:
        """`launchctl list` filtered to com.cabinet.* labels, as
        {label: {"pid": Optional[int], "status": Optional[int]}} where status is
        the job's LAST EXIT STATUS. Defaults to {} (not NotImplementedError, the
        same deliberate degrade-safe choice as tz_ok): on a non-Mac test host or
        an older Probe stub the scan simply self-disables instead of crashing
        the sweep — {} means "launchd not observable", and the verify treats
        that as unverifiable-skip, never as failure. Real impl in check.py."""
        return {}

    def trigger_chair(self, message: str) -> bool:  # pragma: no cover
        """Push a trigger to cabinet:triggers:cos (the ONLY side-effect a
        verify/auto_fix may cause). Returns True on a confirmed enqueue."""
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared by the verifies (stdlib only).
# ─────────────────────────────────────────────────────────────────────────────
def _parse_iso(s: str) -> Optional[_dt.datetime]:
    """Parse an ISO-8601 timestamp (with or without trailing Z) to aware UTC."""
    s = (s or "").strip()
    if not s:
        return None
    s = s.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M"):
        try:
            return _dt.datetime.strptime(s, fmt).replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
    return None


def _iter_json_records(text: str) -> list[dict]:
    """Decode a stream of concatenated (possibly pretty-printed) JSON objects.

    The frontdoor briefing log is exactly this: each launchd run appends one
    pretty-printed JSON dict. We greedily raw_decode from each top-level `{` at
    a line start. Returns records in file order (oldest → newest)."""
    out: list[dict] = []
    dec = json.JSONDecoder()
    for m in re.finditer(r"(?m)^\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
            if isinstance(obj, dict):
                out.append(obj)
        except ValueError:
            continue
    return out


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY functions — one per seeded expectation. Each is pure given a Probe.
# ─────────────────────────────────────────────────────────────────────────────

# Paths/keys the verifies read. Centralized so a path move is one edit and the
# docs-track-code grep finds them. Resolved launcher-agnostically (de-nate /
# source-adapter): CABINET_ROOT-anchored repo paths via _cabinet_root();
# HOME-anchored runtime dirs (.cabinet logs / Library/Logs) via Path.home();
# the brain STATE dir via framework.env.state_dir() (instance config) — never a
# hardcoded home literal. On the live Mac these resolve byte-identically to the
# previous hardcoded values.
BRIEFING_LOG = str(Path.home() / ".cabinet" / "logs" / "frontdoor-briefing.log")
CAPTAIN_DECISIONS = str(
    _cabinet_root() / "shared" / "interfaces" / "captain-decisions.md"
)
LAST_CAPTAIN_MSG_KEY = "cabinet:last-captain-msg-id"
# The Chair stamps this on EVERY briefing it delivers — including a MANUAL
# delivery when the cron missed (observed value: "2026-06-29T06:29:35Z (manual —
# cron miss)"). The OUTCOME is "the Captain got their briefing", delivered BY ANY MEANS —
# so a fresh marker satisfies the expectation even if the cron's own send failed
# or never ran. We read the leading ISO token and ignore any trailing annotation.
BRIEF_DELIVERED_MARKER_KEY = "cabinet:schedule:last-run:cos:briefing"


# ─────────────────────────────────────────────────────────────────────────────
# Instance config (egg plan R017) — the deployment-specific tables this module
# used to hardcode (briefing slot times, the fulltime-officer roster, the
# pipe-freshness table, and WHICH expectation rows are enabled) live in
# instance/config/watchdog.yml. The registry keeps the MACHINERY (verifies,
# tiers, the router contract); the instance supplies the data. STDLIB-ONLY
# (survival contract — same reasoning as the services.yml parser below): a
# narrow line-parser over exactly the shapes that file documents, never
# PyYAML. A missing or unparseable file/key degrades to GENERIC defaults —
# never launcher data: briefing 07:30/19:30 +45m grace (the framework fleet
# default), an EMPTY roster (no officers to watch), an EMPTY pipe table
# (nothing to watch), and ALL catalog expectations enabled (a bad config can
# narrow the watchdog's inputs, never blind the sweep itself).
# The PATH resolves through the one ratified env seam
# (framework.env.watchdog_config_path(); env CABINET_WATCHDOG_CONFIG
# overrides) so this module carries no instance path tokens (layer-separation
# gate); an unresolvable path ("") reads as an absent file → same generic
# defaults.
# ─────────────────────────────────────────────────────────────────────────────
WATCHDOG_CONFIG = watchdog_config_path()

_BRIEF_DEFAULTS = {"am_hour": 7, "pm_hour": 19, "minute": 30, "grace_min": 45}
# Field-level sanity bounds: a corrupt hour/minute falls back to that field's
# default rather than blowing up the slot math in datetime.replace().
_BRIEF_BOUNDS = {"am_hour": 23, "pm_hour": 23, "minute": 59, "grace_min": 24 * 60}


def _parse_watchdog_config(text: str) -> dict:
    """Parse instance/config/watchdog.yml's four sections with stdlib only.

    Accepted shapes (documented in that file's header): top-level `section:`
    keys; `  key: <int>` scalars under briefing:; `  - <slug>` items under
    fulltime_officers: / expectations:; and under pipe_freshness: a
    `  <pipe>:` entry carrying `    log: <file>` + `    max_stale_s: <int>`.
    Trailing comments are ignored by the value regexes; unknown lines are
    ignored per-entry; incomplete pipe entries are dropped."""
    cfg: dict = {
        "briefing": dict(_BRIEF_DEFAULTS),
        "fulltime_officers": [],
        "pipe_freshness": {},
        "expectations": [],
    }
    section = None
    pipe = None
    pipes_raw: dict = {}
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if m:
            section = m.group(1)
            pipe = None
            continue
        if section == "briefing":
            km = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*(\d+)\b", line)
            if km and km.group(1) in cfg["briefing"]:
                v = int(km.group(2))
                if 0 <= v <= _BRIEF_BOUNDS[km.group(1)]:
                    cfg["briefing"][km.group(1)] = v
        elif section in ("fulltime_officers", "expectations"):
            im = re.match(r"^  - ([A-Za-z0-9._-]+)\b", line)
            if im:
                cfg[section].append(im.group(1))
        elif section == "pipe_freshness":
            pm = re.match(r"^  ([A-Za-z0-9._-]+):\s*$", line)
            if pm:
                pipe = pm.group(1)
                pipes_raw.setdefault(pipe, [None, None])
                continue
            if pipe:
                lm = re.match(r"^    log:\s*([^\s#]+)", line)
                if lm:
                    pipes_raw[pipe][0] = lm.group(1)
                sm = re.match(r"^    max_stale_s:\s*(\d+)\b", line)
                if sm:
                    pipes_raw[pipe][1] = int(sm.group(1))
    # Finalize pipes: only complete (log + max_stale_s) entries survive, in the
    # (fname, max_stale_s) tuple shape verify_pipes_fresh iterates.
    cfg["pipe_freshness"] = {p: (v[0], v[1]) for p, v in pipes_raw.items()
                             if v[0] and isinstance(v[1], int)}
    return cfg


def _load_watchdog_config() -> dict:
    """Read + parse the instance config; ANY failure → pure generic defaults."""
    try:
        text = Path(WATCHDOG_CONFIG).read_text(errors="replace")
    except OSError:
        text = ""
    try:
        return _parse_watchdog_config(text)
    except Exception:
        return {"briefing": dict(_BRIEF_DEFAULTS), "fulltime_officers": [],
                "pipe_freshness": {}, "expectations": []}


_CFG = _load_watchdog_config()

# Briefing schedule (Captain-local wall clock; instance/config/watchdog.yml —
# mirrors the frontdoor-briefing schedule in cabinet/services.yml):
BRIEF_AM_HOUR = _CFG["briefing"]["am_hour"]
BRIEF_PM_HOUR = _CFG["briefing"]["pm_hour"]
BRIEF_MINUTE = _CFG["briefing"]["minute"]
# Grace after the scheduled minute before we expect the outcome to be TRUE.
BRIEF_GRACE_MIN = _CFG["briefing"]["grace_min"]


def _leading_iso(s: str) -> Optional[_dt.datetime]:
    """Parse the leading ISO-8601 token of a string that may carry a trailing
    human annotation, e.g. '2026-06-29T06:29:35Z (manual — cron miss)'. Returns
    aware UTC, or None."""
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?Z?)", s or "")
    return _parse_iso(m.group(1)) if m else None


def _brief_slot_id(slot_local: _dt.datetime) -> str:
    """Stable per-slot id (date + AM/PM) so dedup/escalation is scoped to THIS
    slot — a new slot's failure can fire even while a prior handled slot stays
    quiet. e.g. '2026-06-29-AM'."""
    ampm = "PM" if slot_local.hour >= 12 else "AM"
    return f"{slot_local:%Y-%m-%d}-{ampm}"


def verify_briefing_delivered(probe: "Probe") -> CheckResult:
    """OUTCOME: the most recent *scheduled* briefing actually DELIVERED to the Captain.

    This is the bug-of-record. We do NOT check that the job ran — we check that
    the last briefing-log record reports a CONFIRMED send (`send.sent == True`
    / `status == 'sent'`). A record with `sent: false` (the HTTP-400 case) is a
    FAILED outcome even though the process exited 0.

    Cadence-aware: only asserts after a scheduled slot's grace window has passed,
    so we don't flag "the 19:30 hasn't happened" at 14:00. Within an active
    window, the freshest log record must be a successful send dated *after* the
    slot fired. If the freshest record is stale (older than the slot) → the job
    didn't run at all; if it's fresh but `sent:false` → it ran but the send
    failed (auto-fixable)."""
    eid = "briefing-delivered"
    # If the Captain timezone could not be resolved, local_now() is silently UTC
    # and the 07:30/19:30-LOCAL slot math would be wrong by the UTC offset,
    # false-failing all day. SKIP (not fail) until the TZ is fixed (review MEDIUM).
    if not probe.tz_ok():
        return CheckResult(eid, True,
                          "Captain timezone unresolved — skipping briefing slot "
                          "check until CABINET_CAPTAIN_TZ is valid", skipped=True)
    local = probe.local_now()

    # Which scheduled slot is the most recent that should already be DONE?
    today_am = local.replace(hour=BRIEF_AM_HOUR, minute=BRIEF_MINUTE,
                             second=0, microsecond=0)
    today_pm = local.replace(hour=BRIEF_PM_HOUR, minute=BRIEF_MINUTE,
                             second=0, microsecond=0)
    grace = _dt.timedelta(minutes=BRIEF_GRACE_MIN)
    if local >= today_pm + grace:
        slot_local = today_pm
    elif local >= today_am + grace:
        slot_local = today_am
    else:
        # Before today's AM grace: the most recent due slot is yesterday's PM.
        slot_local = today_pm - _dt.timedelta(days=1)

    slot_id = _brief_slot_id(slot_local)
    slot_utc = slot_local.astimezone(_dt.timezone.utc)

    # SATISFIED-BY-ANY-DELIVERY (refinement 2026-06-29): the OUTCOME is "the Captain
    # got their briefing", delivered by ANY means — not "the cron's send succeeded". The
    # Chair stamps cabinet:schedule:last-run:cos:briefing on every delivery,
    # INCLUDING a manual one when the cron missed. If that marker is dated at/after
    # the due slot, the outcome is TRUE regardless of what the cron log says — so a
    # manually-recovered briefing no longer false-positives. Checked FIRST, before
    # the cron-log inspection, so it short-circuits the failure path.
    marker = _leading_iso(probe.redis_get(BRIEF_DELIVERED_MARKER_KEY))
    if marker is not None and marker >= slot_utc:
        return CheckResult(eid, True,
                          f"briefing delivered for the {slot_id} slot "
                          f"(delivery marker {marker:%Y-%m-%d %H:%M}Z ≥ slot) — "
                          f"satisfied by any means")

    text = probe.read_text(BRIEFING_LOG)
    records = _iter_json_records(text)
    if not records:
        # No log at all → can't verify; treat as a failure to deliver (the log
        # is written on every run, so an empty/absent log means nothing ran).
        return CheckResult(eid, False,
                           f"no briefing-log records at {BRIEFING_LOG} and no "
                           f"delivery marker (expected a delivered briefing for "
                           f"the {slot_id} slot)",
                           fix_hint={"slot_local": slot_local.isoformat(),
                                     "slot_id": slot_id})

    last = records[-1]
    # The briefing log record's "send" is the run_send_path result: it carries
    # the outcome booleans (sent / drained / recovered) at the top level AND the
    # underlying channel.send result nested under "send" (status / error). Read
    # the outer for the outcome, the nested for the failure detail.
    send = last.get("send") or {}
    channel = send.get("send") or {}  # nested channel.send result
    # `sent` is the CANONICAL outcome signal (the outer run_send_path bool). Do
    # NOT also require status=="sent" — a True `sent` with an absent/renamed
    # nested status would otherwise false-FAIL a genuinely delivered briefing
    # (review HIGH 2026-06-29). status is used ONLY for failure-detail text.
    sent = bool(send.get("sent"))
    status = str(channel.get("status") or send.get("status") or "")

    # When did the freshest record land? PREFER a record-level timestamp if the
    # briefing ever stamps one (forward-compatible, decoupled from file mtime);
    # fall back to the log file mtime. mtime alone can be advanced by a write
    # that appends no NEW complete record (rotation/partial write), which could
    # mask a stale success — the satisfied-by-marker check above is the primary
    # guard, and a record-level ts is the durable structural fix (briefing TODO).
    rec_ts = _parse_iso(str(last.get("ts") or last.get("run_time") or ""))
    if rec_ts is not None:
        run_dt_utc = rec_ts
    else:
        mtime = probe.file_mtime(BRIEFING_LOG)
        run_dt_utc = (_dt.datetime.fromtimestamp(mtime, _dt.timezone.utc)
                      if mtime else None)
    # slot_utc was computed above (alongside the delivery-marker check).

    if sent:
        # Delivered — but is it the CURRENT slot's delivery, or a stale success?
        # (The delivery-marker check above already covered any-means delivery; a
        # cron-log success older than the slot with NO marker means it didn't run.)
        if run_dt_utc is not None and run_dt_utc < slot_utc:
            return CheckResult(
                eid, False,
                f"last briefing send SUCCEEDED but is stale (ran "
                f"{run_dt_utc:%Y-%m-%d %H:%M}Z, before the "
                f"{slot_local:%Y-%m-%d %H:%M} local slot) — the scheduled "
                f"briefing did not run",
                fix_hint={"slot_local": slot_local.isoformat(),
                          "slot_id": slot_id, "cause": "did-not-run"})
        return CheckResult(eid, True,
                          f"briefing delivered (status=sent) for the {slot_id} slot")

    # Freshest record is a NON-success. Distinguish "ran but send failed" (fresh
    # record, auto-fixable) from "didn't run" (stale record).
    drained = send.get("drained")
    recovered = send.get("recovered")
    err = channel.get("error") or send.get("error") or status or "unknown"
    if run_dt_utc is not None and run_dt_utc >= slot_utc:
        return CheckResult(
            eid, False,
            f"briefing RAN but send FAILED (status={status!r}, error={err!r}, "
            f"drained={drained}, recovered={recovered}) — backlog undelivered "
            f"for the {slot_id} slot (no delivery by any other means either)",
            fix_hint={"slot_local": slot_local.isoformat(), "slot_id": slot_id,
                      "cause": "send-failed", "error": str(err)[:200]})
    return CheckResult(
        eid, False,
        f"no successful briefing for the {slot_id} slot "
        f"(freshest record status={status!r}, sent={sent})",
        fix_hint={"slot_local": slot_local.isoformat(),
                  "slot_id": slot_id, "cause": "did-not-run"})


def autofix_briefing(probe: "Probe", result: CheckResult) -> Optional[str]:
    """Deterministic-safe remediation for a failed/undelivered briefing.

    Per the brain-bridge + P-Alerts-To-Chair rules, the watchdog NEVER sends an
    outbound message itself and never calls the Telegram API. The
    deterministic-safe fix is to re-trigger the Chair with full context so the
    Chair re-runs the briefing through the gated front-door channel (the one
    legitimate send path). That is both the auto-fix (it re-drives the outcome)
    AND correct routing (the Chair owns the send + can judge a payload bug).

    Anti-thrash: the checker dedups on the expectation id within a cooldown
    window, so this won't machine-gun the Chair on every 30-min cycle while the
    briefing stays broken — it fires once per cooldown until the outcome is TRUE
    again."""
    cause = result.fix_hint.get("cause", "unknown")
    slot = result.fix_hint.get("slot_local", "?")
    err = result.fix_hint.get("error", "")
    cap = captain_name()
    msg = (
        f"OUTCOME-WATCHDOG auto-fix — the recurring briefing did NOT reach {cap} "
        f"for the {slot} slot (cause: {cause}"
        + (f", send error: {err}" if err else "")
        + "). The job's process exited clean but the OUTCOME (a delivered "
        "briefing) did not happen. Please RE-RUN the briefing send now: "
        "`CABINET_ENV=runtime REDIS_HOST=localhost PATH=/opt/homebrew/bin:$PATH "
        "bash cabinet/scripts/run-frontdoor-briefing.sh` (it recovers the "
        "pending/undelivered backlog and re-sends through the gated channel). "
        "If the send still 400s, the payload itself is the bug (e.g. an "
        "over-long chunk or a stale reply-to id) — gather-then-decide, fix the "
        f"root cause, and only escalate to {cap} if you are genuinely stuck. "
        f"Do NOT DM {cap} the raw failure."
    )
    return msg if probe.trigger_chair(msg) else None


# Reflection cadence — reuse the same schedule stamps the anomaly-scan reads.
# A fulltime officer that did work but hasn't reflected within the ceiling is
# overdue. We read cabinet:schedule:last-run:<officer>:reflection and the
# positive work signal cabinet:last-experience:<officer> (set by
# record-experience.sh, 2h TTL) — identical sources to lib/reflection.sh, so we
# compose rather than re-derive. Ceiling mirrors the retro's 48h floor.
# The roster itself is instance data (instance/config/watchdog.yml — egg R017);
# an empty/unconfigured roster means no officers to watch (clean-room degrade).
FULLTIME_OFFICERS = list(_CFG["fulltime_officers"])
REFLECTION_CEILING_S = 48 * 3600


def verify_officer_reflection(probe: "Probe") -> CheckResult:
    """OUTCOME: each fulltime officer that has done recent work has reflected
    within the 48h ceiling. Officers idle (no recent experience record) are not
    expected to reflect — absence of work == nothing to reflect on (same gate as
    reflection_due). Only flags an officer with a *recent work signal* whose last
    reflection is older than the ceiling (or never)."""
    eid = "officer-reflection"
    now = probe.now()
    overdue = []
    for officer in FULLTIME_OFFICERS:
        # WORK SIGNAL (HIGH-8 fix 2026-07-03): last-experience alone made this
        # check vacuous — the key has a 2h TTL and record-experience.sh stopped
        # being called Jun 30, so every officer read as "idle" and the check
        # logged green while the reflection chain was dead. Compose it with the
        # DURABLE cabinet:last-toolcall:<officer> stamp (post-tool-use hook,
        # ISO-8601): a toolcall within the ceiling window == the officer worked.
        last_work = probe.redis_get(f"cabinet:last-experience:{officer}")
        if not last_work:
            tc = _parse_iso(probe.redis_get(f"cabinet:last-toolcall:{officer}"))
            if tc is not None and (now - tc).total_seconds() <= REFLECTION_CEILING_S:
                last_work = "toolcall"
        if not last_work:
            continue  # idle → not expected to reflect
        last_refl_raw = probe.redis_get(
            f"cabinet:schedule:last-run:{officer}:reflection")
        last_refl = _parse_iso(last_refl_raw)
        if last_refl is None:
            overdue.append(f"{officer} (worked recently, never reflected)")
            continue
        age_s = (now - last_refl).total_seconds()
        if age_s > REFLECTION_CEILING_S:
            overdue.append(f"{officer} ({age_s / 3600:.0f}h since last reflection)")
    if overdue:
        return CheckResult(eid, False,
                          "officers overdue for reflection: " + ", ".join(overdue))
    return CheckResult(eid, True, "all working officers reflected within 48h")


# Captain-decision logging — the governance gap just closed. Heuristic, file-only:
# a relayed Captain decision should have a captain-decisions.md entry. We can't
# reconstruct every relay, but we CAN catch the structural failure: the file
# stopped growing while the cabinet kept relaying decisions. The cheap, robust
# proxy is the freshest dated heading in the file vs the freshest Captain DM.
# This is intentionally a DRIFT-tier signal (a note, never an alert): it is a
# soft indicator, not a hard outcome, and false positives must not page anyone.
DECISION_HEADING_RE = re.compile(r"(?m)^##\s+(?:(\d{4}-\d{2}-\d{2})\b|.*?\((\d{4}-\d{2}-\d{2})\))")


def verify_captain_decisions_logged(probe: "Probe") -> CheckResult:
    """OUTCOME (soft): captain-decisions.md is being kept current — its newest
    entry is not staler than the cabinet's most recent Captain interaction by an
    implausible margin. Drift-tier: a note to the meta-cognition sink, not an
    alert. The hard real-time enforcement is the post-tool-use hook; this is the
    backstop that notices if that enforcement silently lapsed."""
    eid = "captain-decisions-logged"
    text = probe.read_text(CAPTAIN_DECISIONS)
    if not text:
        return CheckResult(eid, True, "captain-decisions.md unreadable — skip",
                          skipped=True)
    dates = []
    for m in DECISION_HEADING_RE.finditer(text):
        ds = m.group(1) or m.group(2)
        d = _parse_iso(ds + "T00:00:00")
        if d:
            dates.append(d)
    if not dates:
        return CheckResult(eid, True, "no dated decision headings yet — skip",
                          skipped=True)
    newest = max(dates)
    # Is the cabinet still actively talking to the Captain? Use the inbound
    # msg-id key freshness as a cheap "recent interaction" proxy — but that key
    # carries no timestamp, so we fall back to a generous 7-day staleness floor:
    # only flag if the newest logged decision is > 7 days old. That is a true
    # structural lapse (a week of zero logged decisions), not normal quiet.
    age_days = (probe.now() - newest).total_seconds() / 86400.0
    if age_days > 7:
        return CheckResult(
            eid, False,
            f"newest captain-decisions.md entry is {age_days:.0f} days old "
            f"({newest:%Y-%m-%d}) — the real-time decision-logging discipline "
            f"may have lapsed; verify recent Captain decisions were logged")
    return CheckResult(eid, True,
                      f"captain-decisions.md current (newest {newest:%Y-%m-%d})")


# Cron/pipe silent-failure — a job whose log shows an error or that stopped
# producing output. STRUCTURAL REWORK (lane-ops 2026-07-04): this used to watch
# exactly ONE hardcoded log (status-sweep), so retro-trigger FATAL'd hourly for
# a day+ (launchd PATH missing → redis-cli not found) and memory-worker was
# never scheduled at all — both invisible, because a hand-maintained watch list
# rots the moment the fleet changes. The fleet already HAS a single manifest
# (cabinet/services.yml, "a service without a met floor is DOWN even if
# green"), so the floors are now DERIVED from it: every non-officer,
# non-disabled row gets (a) a log-freshness floor from its declared schedule,
# (b) an error-marker tail scan, and via launchctl (c) a last-exit-status scan
# and (d) a declared-but-not-loaded check — (d) is the one that would have
# caught memory-worker, (a)+(b)+(c) the ones that would have caught
# retro-trigger. Adding a services.yml row is now what enrolls a job here —
# nothing to update in this file.
#
# STDLIB-ONLY CONSTRAINT: the registry's survival contract forbids third-party
# imports (PyYAML included) — a watchdog that dies from a missing dep is worse
# than none. services.yml is repo-controlled and machine-edited, so a narrow
# line-parser over exactly the shapes the manifest uses (flat keys at 4-space
# indent, flow `{ interval_s: N }` / `{ calendar: [...] }`, block calendar
# lists) is reliable HERE; any unparseable/foreign shape degrades per-entry,
# and a wholesale parse failure falls back to the legacy static row so the
# watchdog is never blinded by a manifest rewrite.
SERVICES_MANIFEST = str(_cabinet_root() / "cabinet" / "services.yml")
CABINET_LOG_DIR = str(Path.home() / ".cabinet" / "logs")            # hand-made plists log here
GENERATED_LOG_DIR = str(Path.home() / "Library" / "Logs" / "cabinet")   # generate-plists.py convention
# Markers additions (2026-07-04): "NOGROUP" = a Redis Streams consumer lost its
# group (the memory-worker failure smell; its self-heal log line deliberately
# avoids the token). "command not found" = the launchd-minimal-PATH class that
# killed retro-trigger. Marker scans are WINDOWED to the entry's floor (or 24h)
# so a years-old error line in a quiet log can't page forever.
JOB_ERROR_MARKERS = ("FATAL", "Traceback (most recent call last)",
                     "trigger NOT pushed", "trigger_send failed",
                     "NOGROUP", "command not found")


def _is_watchdog_self_report_line(ln: str) -> bool:
    """True if `ln` is THIS check's own structured finding, not a real service
    error. The outcome-watchdog's own log (outcome-watchdog.log) contains this
    check's findings — e.g. `[FAIL] no-silent-cron-failure ... error marker
    'FATAL' in recent log tail` — which quote JOB_ERROR_MARKERS verbatim. Marker-
    scanning those lines re-detects the marker from our OWN output: a self-
    referential false-positive that fired every cycle and masked real failures.
    A genuine service error line ("FATAL: db down", a Traceback) carries none of
    these self-report signatures, so filtering by them is loss-free for real
    errors."""
    s = ln.lstrip()
    return (
        s.startswith("[FAIL]") or s.startswith("[OK]") or s.startswith("[WARN]")
        or "error marker '" in ln            # this check's own report phrase
        or "→ escalation" in ln          # the '→ escalation SKIPPED/…' echo
        or "no-silent-cron-failure" in ln     # this check's eid in any echo
    )

# Fallback when the manifest is missing/unparseable: the pre-2026-07-04 static
# coverage (status-sweep), so a bad manifest degrades to old behavior, not to
# zero coverage.
_FALLBACK_ENTRIES = [{
    "name": "status-sweep", "label": "com.cabinet.status-sweep",
    "kind": "daemon", "disabled": False,
    "schedule_kind": "interval", "interval_s": 1800, "weekly": False,
}]

# Freshness-floor policy. Deliberately conservative (the 2026-07-01 pipe-alarm
# flood is the cautionary tale — see PIPE_FRESHNESS above):
#   interval  → 2×cadence + 10min grace, floored at 2h: launchd only advances a
#               log's mtime when the job WRITES; a healthy short-cadence service
#               that prints nothing on a quiet pass (intake-surface at 300s)
#               would false-alarm on a tight floor. 2h still catches every real
#               stall while the marker scan supplies the fast signal for
#               loud failures.
#   calendar  → 26h (daily slot + grace); any weekday key → 8 days (weekly);
#               any day-of-month key → 33 days (monthly — lane-supply
#               2026-07-05 for the fidelity-f1 row: without this, a monthly
#               calendar row inherits the 26h daily floor and false-pages
#               every day of the month it correctly does nothing).
#   keepalive → None: long-runners log on EVENTS, not on a clock (a quiet day
#               for memory-worker is normal) — their liveness is owned by the
#               launchctl loaded/exit-status scan instead.
_FLOOR_MIN_S = 7200


def _floor_for_entry(entry: dict) -> Optional[int]:
    if entry.get("schedule_kind") == "interval" and entry.get("interval_s"):
        return max(2 * int(entry["interval_s"]) + 600, _FLOOR_MIN_S)
    if entry.get("schedule_kind") == "calendar":
        # Longest period wins when keys combine (launchd ANDs calendar keys, so
        # a day+weekday row fires at most monthly — the monthly floor applies).
        if entry.get("monthly"):
            return 33 * 86400   # 31-day month + 2 days grace
        return 8 * 86400 if entry.get("weekly") else 26 * 3600
    return None  # keepalive / unknown schedule


def _service_log_candidates(name: str) -> list[str]:
    """Every path a service's output may land at, across BOTH plist eras: the
    generator writes NAME.log/.err under ~/Library/Logs/cabinet; older
    hand-made plists write NAME.log (and cos-inbound NAME.out.log/.err.log)
    under ~/.cabinet/logs. Freshness = newest existing mtime across all of
    them, so a plist migration between conventions never false-alarms."""
    return [
        f"{GENERATED_LOG_DIR}/{name}.log",
        f"{GENERATED_LOG_DIR}/{name}.err",
        f"{GENERATED_LOG_DIR}/{name}.out.log",
        f"{GENERATED_LOG_DIR}/{name}.err.log",
        f"{CABINET_LOG_DIR}/{name}.log",
    ]


def _parse_services_manifest(text: str) -> list[dict]:
    """Parse cabinet/services.yml's service rows with stdlib only (see the
    survival-contract note above). Extracts exactly what the floors need:
    name / label / kind / disabled / schedule shape. Entry keys sit at EXACTLY
    4-space indent in the manifest; deeper lines belong to a block value (env,
    notes, a block-form schedule) — that exact-indent match is what keeps a
    `notes: >-` continuation or env var from being misread as a key."""
    entries: list[dict] = []
    cur: Optional[dict] = None
    in_sched_block = False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^  - name:\s*([A-Za-z0-9._-]+)\s*$", line)
        if m:
            cur = {"name": m.group(1), "label": "", "kind": "",
                   "disabled": False, "schedule_kind": None,
                   "interval_s": None, "weekly": False, "monthly": False}
            entries.append(cur)
            in_sched_block = False
            continue
        if cur is None:
            continue
        km = re.match(r"^    ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            in_sched_block = False
            if key == "kind":
                cur["kind"] = val
            elif key == "label":
                cur["label"] = val
            elif key == "disabled":
                cur["disabled"] = val.lower() in ("true", "yes", "1")
            elif key == "schedule":
                # Strip a trailing YAML comment from flow values before
                # matching (rows annotate cadence inline, e.g. `# daily 03:00`).
                val = val.split("#", 1)[0].strip()
                if val == "keepalive":
                    cur["schedule_kind"] = "keepalive"
                elif "interval_s" in val:
                    im = re.search(r"interval_s:\s*(\d+)", val)
                    if im:
                        cur["schedule_kind"] = "interval"
                        cur["interval_s"] = int(im.group(1))
                elif "calendar" in val:
                    cur["schedule_kind"] = "calendar"
                    cur["weekly"] = "weekday" in val
                    # \bday\s*: cannot match inside "weekday" (k→d is no word
                    # boundary) — monthly detection never false-fires on weekly
                    # rows (lane-supply 2026-07-05, fidelity-f1 monthly floor).
                    cur["monthly"] = bool(re.search(r"\bday\s*:", val))
                elif val == "":
                    in_sched_block = True  # block form follows (calendar list)
            continue
        if in_sched_block:
            # Inside `schedule:`'s block value (≥6-space indent): detect the
            # calendar/interval markers wherever they appear.
            if "calendar" in line:
                cur["schedule_kind"] = "calendar"
            im = re.search(r"interval_s:\s*(\d+)", line)
            if im:
                cur["schedule_kind"] = "interval"
                cur["interval_s"] = int(im.group(1))
            if "weekday" in line:
                cur["weekly"] = True
            if re.search(r"\bday\s*:", line):
                cur["monthly"] = True   # block-form monthly (see \bday note above;
                # the regex alone suffices — "weekday:" carries no boundary
                # before "day", and a combined day+weekday entry IS ≤monthly)
    return entries


def verify_no_silent_cron_failure(probe: "Probe") -> CheckResult:
    """OUTCOME: every service the fleet manifest declares is producing output
    within its cadence, not silently erroring, and actually loaded — with the
    floors DERIVED from cabinet/services.yml (see the rework note above).
    Officer rows are excluded (their lifecycle is the supervisor's; their tmux
    wrappers exit non-zero legitimately); disabled rows are excluded (parked/
    staged is a declared state, not a failure). Escalates to the Chair as ONE
    consolidated finding (anti-thrash cooldown in the router still applies)."""
    eid = "no-silent-cron-failure"
    now_epoch = probe.now().timestamp()
    entries = [e for e in _parse_services_manifest(probe.read_text(SERVICES_MANIFEST))
               if e.get("name")]
    if not entries:
        entries = _FALLBACK_ENTRIES
    watched = [e for e in entries
               if e.get("kind") != "officer" and not e.get("disabled")]
    officer_labels = {e.get("label") for e in entries if e.get("kind") == "officer"}

    problems: list[str] = []
    for e in watched:
        name = e["name"]
        floor_s = _floor_for_entry(e)
        cands = [(p, probe.file_mtime(p)) for p in _service_log_candidates(name)]
        cands = [(p, mt) for p, mt in cands if mt is not None]
        freshest = max((mt for _p, mt in cands), default=None)

        if floor_s is not None:
            if freshest is None:
                problems.append(f"{name}: no log at any known path (never ran / "
                                f"not installed?)")
                # No log → nothing to marker-scan either.
                continue
            idle_s = now_epoch - freshest
            if idle_s > floor_s:
                problems.append(
                    f"{name}: log silent {idle_s / 3600:.1f}h "
                    f"(> {floor_s / 3600:.1f}h floor) — stalled or not firing")
                continue

        # Marker scan, windowed: only files written within the entry's floor
        # (or 24h for floorless keepalive rows) are recent enough that an error
        # line in their tail reflects the CURRENT run era, not archaeology.
        window_s = floor_s if floor_s is not None else 86400
        for path, mt in cands:
            if now_epoch - mt > window_s:
                continue
            tail_lines = [l for l in probe.read_text(path).splitlines()[-25:]
                          if not _is_watchdog_self_report_line(l)]
            tail = "\n".join(tail_lines)
            hit = next((mk for mk in JOB_ERROR_MARKERS if mk in tail), None)
            if hit:
                problems.append(f"{name}: error marker {hit!r} in recent log tail "
                                f"({path.rsplit('/', 1)[-1]})")
                break

    # launchctl surface — {} means "not observable here" (non-Mac host, test
    # stub, launchctl error): both launchd checks self-disable rather than
    # false-fail, per the Probe degrade-safe contract.
    ll = probe.launchctl_list()
    if ll:
        # (c) last-exit-status: any com.cabinet.* label whose last run exited
        # non-zero — INCLUDING labels not (yet) in the manifest, so a stray or
        # freshly-installed agent is still covered. Officer labels excluded
        # (session wrappers restart by design). This is what turns retro-
        # trigger's hourly exit-127 into a page instead of a green launchd row.
        watched_labels = {e.get("label") for e in watched}
        for label in sorted(ll):
            if label in officer_labels:
                continue
            # Self-review fix (lane-ops 2026-07-04): an officer hired AFTER this
            # manifest was written appears as com.cabinet.officer.<slug> with no
            # row — its session wrapper exits non-zero legitimately just like
            # the rostered officers, so exclude the whole officer.* prefix
            # UNLESS the label is a watched non-officer row (the cos-inbound
            # poller lives under that prefix but is a daemon we DO cover).
            if label.startswith("com.cabinet.officer.") and label not in watched_labels:
                continue
            # Adversarial-review fix (lane-ops 2026-07-04): a job that is
            # CURRENTLY RUNNING (pid set) is not judged by `status` — launchctl
            # reports the exit of the PREVIOUS incarnation there, which for a
            # keepalive daemon is almost always a routine SIGTERM (-15) from
            # the last reload/deploy. Live incident that forced this: the
            # healthy cos-inbound poller sat at pid 29983 / status -15 and
            # would have paged the Chair EVERY sweep forever (the 2026-07-01
            # pipe-alarm-flood class this whole check is written to avoid).
            # Coverage survives the skip: interval/cron jobs spend their life
            # NOT running (pid None between runs — retro-trigger's 127 still
            # pages), and a crash-looping keepalive daemon is throttled
            # (ThrottleInterval 30) so it too shows pid None + non-zero status
            # on almost every sweep. A job observed mid-run with a prior
            # failure is simply caught on the next 30-min sweep once it exits.
            if ll[label].get("pid") is not None:
                continue
            status = ll[label].get("status")
            if status not in (0, None):
                problems.append(f"{label}: last exit status {status}")
        # (d) declared-but-not-loaded: an enabled manifest row whose label
        # launchd doesn't know. THE memory-worker failure class — declared in
        # the fleet manifest, hooks feeding its queue, never scheduled. Also
        # deliberately flags a freshly-declared service until its plist is
        # actually bootstrapped (that gap is real downtime, and it self-heals
        # on install).
        for e in watched:
            label = e.get("label")
            if label and label not in ll:
                problems.append(f"{e['name']}: declared in services.yml but not "
                                f"loaded in launchd ({label})")

    if problems:
        shown = problems[:8]
        more = len(problems) - len(shown)
        detail = "cabinet cron issues: " + "; ".join(shown)
        if more > 0:
            detail += f"; +{more} more"
        return CheckResult(eid, False, detail)
    return CheckResult(eid, True,
                      f"{len(watched)} manifest services producing clean output"
                      + ("" if ll else " (launchd scan unavailable — log floors only)"))


# Pipe freshness — the brain's ingestion pipes must be writing within cadence.
# We deliberately DO NOT re-implement pipe-watchdog (which owns kickstart-healing
# of msgraph/teams/embeddings). We add the OUTCOME assertion: "the brain is fresh"
# — the data the Captain's officers reason from is current. If a pipe is stale we ESCALATE
# to the Chair (pipe-watchdog auto-heals; if it's still stale here that means the
# heal didn't take → a human/Chair signal). Cheap: just the log mtimes.
# The watched STATE dir is instance config (framework.env.state_dir(); env
# CABINET_STATE_DIR overrides) — byte-identical to the removed hardcoded state
# path on this deployment, and "" on a clean-room / Flavor-B box, where
# verify_pipes_fresh degrades to nothing-to-watch (a skip, never a false alarm).
SCREENPIPE_STATE_DIR = state_dir()
# pipe → (log filename under the state dir, max staleness seconds). Instance
# data (instance/config/watchdog.yml — egg R017; the cadence-aligned threshold
# rationale is documented there, next to the values). Empty when unconfigured
# → nothing to watch (clean-room degrade; and with no state dir at all,
# verify_pipes_fresh SKIPs outright).
PIPE_FRESHNESS = dict(_CFG["pipe_freshness"])


def verify_pipes_fresh(probe: "Probe") -> CheckResult:
    """OUTCOME: the brain's ingestion pipes are fresh (ingesting within cadence).

    KNOWN STANDING OUTAGE (memory): Microsoft Graph teams + microsoft365
    connections have been connected:false since ~2026-06-02, so msgraph/teams
    pipes legitimately write nothing. We therefore report stale Graph pipes as a
    SINGLE de-duplicated Chair line (not per-pipe spam), and the Chair already
    knows the root (re-auth). embeddings staleness is the one that matters most
    (the index the brain search reads). Pure mtime read — no Graph poll."""
    eid = "pipes-fresh"
    # Flavor-B / unconfigured: no brain state dir → nothing to watch. A skip is
    # neither pass nor fail (never routed), so a clean-room box with no screenpipe
    # pipes never false-alarms on their absence (the "nothing to watch" degrade).
    if not SCREENPIPE_STATE_DIR:
        return CheckResult(eid, True,
                          "no brain state dir configured — nothing to watch",
                          skipped=True)
    now_epoch = probe.now().timestamp()
    stale = []
    for pipe, (fname, max_stale_s) in PIPE_FRESHNESS.items():
        mtime = probe.file_mtime(f"{SCREENPIPE_STATE_DIR}/{fname}")
        if mtime is None:
            stale.append(f"{pipe} (no log)")
            continue
        idle_s = now_epoch - mtime
        if idle_s > max_stale_s:
            stale.append(f"{pipe} ({idle_s / 3600:.1f}h stale)")
    if stale:
        return CheckResult(eid, False,
                          "brain pipes stale (pipe-watchdog should auto-heal; "
                          "escalating residual): " + ", ".join(stale))
    return CheckResult(eid, True, "brain ingestion pipes fresh")


# ─────────────────────────────────────────────────────────────────────────────
# THE CATALOG — every outcome expectation this framework ships. Add an outcome
# to watch = append one Expectation row here (and, if instance/config/
# watchdog.yml narrows `expectations:`, enable its id there too).
# ─────────────────────────────────────────────────────────────────────────────
_CATALOG: list[Expectation] = [
    Expectation(
        id="briefing-delivered",
        what=f"Briefing DELIVERED to {captain_name()} 2x/day "
             f"({BRIEF_AM_HOUR:02d}:{BRIEF_MINUTE:02d} + "
             f"{BRIEF_PM_HOUR:02d}:{BRIEF_MINUTE:02d} local) — a "
             "confirmed send landed, not just that the job ran.",
        cadence_s=12 * 3600,
        tier=Tier.AUTO_FIX,
        verify=verify_briefing_delivered,
        auto_fix=autofix_briefing,
    ),
    Expectation(
        id="officer-reflection",
        what="Each fulltime officer that did recent work reflected within 48h.",
        cadence_s=48 * 3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_officer_reflection,
    ),
    Expectation(
        id="captain-decisions-logged",
        what="Relayed Captain decisions are logged to captain-decisions.md "
             "(real-time discipline hasn't lapsed).",
        cadence_s=24 * 3600,
        tier=Tier.DRIFT,
        verify=verify_captain_decisions_logged,
    ),
    Expectation(
        id="no-silent-cron-failure",
        what="Every enabled cabinet/services.yml service produces output within "
             "its schedule-derived floor, logs no error markers, is loaded in "
             "launchd, and — when not currently running — its last completed "
             "run exited 0 (floors derived from the fleet manifest — lane-ops "
             "2026-07-04; running jobs are never judged by their previous "
             "incarnation's exit).",
        cadence_s=3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_no_silent_cron_failure,
    ),
    Expectation(
        id="pipes-fresh",
        what="Brain ingestion pipes ingesting within cadence (per the "
             "instance pipe-freshness table) so officers reason from current "
             "data.",
        cadence_s=3 * 3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_pipes_fresh,
    ),
]


def _select_expectations(catalog: list[Expectation],
                         enabled_ids: list[str]) -> list[Expectation]:
    """The rows enabled on THIS deployment: the instance config's
    `expectations:` id list (config order). Fail-safe by construction: an
    empty/absent list — or one whose ids are ALL unknown — yields the FULL
    catalog (a bad config can narrow the watchdog's inputs, never silently
    zero the sweep); unknown ids are ignored per-entry."""
    if enabled_ids:
        by_id = {e.id: e for e in catalog}
        picked = [by_id[i] for i in enabled_ids if i in by_id]
        if picked:
            return picked
    return list(catalog)


# ─────────────────────────────────────────────────────────────────────────────
# THE REGISTRY — the catalog rows instance/config/watchdog.yml enables.
# ─────────────────────────────────────────────────────────────────────────────
EXPECTATIONS: list[Expectation] = _select_expectations(_CATALOG,
                                                       _CFG["expectations"])


def expectation_by_id(eid: str) -> Optional[Expectation]:
    return next((e for e in EXPECTATIONS if e.id == eid), None)
