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
    the systems it watches (framework.frontdoor, personal-source libs, org_runtime).
    A watchdog built on top of the thing it watches dies with it. Each verify
    reads a FILE, a Redis key (via redis-cli subprocess), or a launchd/log
    timestamp — the cheapest possible probe, never a Graph/Vercel/LLM call.
    (The in-repo imports are ``framework.env.captain_name`` + ``state_dir`` +
    ``watchdog_config_path`` — launcher-agnostic / source-adapter resolvers: import-light
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
import functools
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

    def redis_hgetall(self, key: str) -> Optional[dict]:
        """HGETALL as {field: value}, or None when NOT OBSERVABLE (Redis
        unreachable, a WRONGTYPE/auth error reply, a desynced pair stream, or
        an older Probe stub). Defaults to None — the same deliberate
        degrade-safe choice as ``launchctl_list`` / ``listdir``: a stub without
        this method self-disables the spend rows instead of crashing the sweep.

        The None-vs-{} distinction is LOAD-BEARING and mirrors
        ``framework.cost.meter.hgetall``: ``{}`` means "the hash exists and is
        empty" — an affirmative observation, and for the spend ledger a
        possible dead meter — while ``None`` means "we could not look", from
        which no conclusion follows. A verify that collapses the two turns an
        unreachable Redis into a false alarm (or, worse, a dead meter into a
        green). Real impl in check.py."""
        return None

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

    def listdir(self, path: str) -> Optional[list[str]]:
        """Sorted entries of a directory, or None when NOT OBSERVABLE
        (missing dir, permission error, an older Probe stub). Defaults to
        None — the same deliberate degrade-safe choice as launchctl_list:
        a stub without this method self-disables the evidence-store facts
        scan instead of crashing the sweep. Verifies MUST treat None as
        unverifiable-skip, never as failure; [] means the directory exists
        and is empty (an affirmative observation). Real impl in check.py."""
        return None

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
# docs-track-code grep finds them. Resolved launcher-agnostically (per the
# launcher-agnostic amendment / source-adapter): CABINET_ROOT-anchored repo
# paths via _cabinet_root();
# HOME-anchored runtime dirs (.cabinet logs / Library/Logs) via Path.home();
# the brain STATE dir via framework.env.state_dir() (instance config) — never a
# hardcoded home literal. On the live Mac these resolve byte-identically to the
# previous hardcoded values.
BRIEFING_LOG = str(Path.home() / ".cabinet" / "logs" / "frontdoor-briefing.log")
CAPTAIN_DECISIONS = str(
    _cabinet_root() / "shared" / "interfaces" / "captain-decisions.md"
)
LAST_CAPTAIN_MSG_KEY = "cabinet:last-captain-msg-id"
# The TIMESTAMPED sibling of the key above (ISO-8601 UTC), written at the same
# instant by the inbound poller's set_last_captain_msg_id. It exists because the
# id key CANNOT express staleness — the captain-decisions verify below wanted
# exactly this signal and said so ("that key carries no timestamp"), then fell
# back to a file-age heuristic. Two keys, two jobs: the id stays untouched for
# its reply-threading consumer (framework/frontdoor/channel.py), and recency
# reads from here. Absent on a fresh cabinet or a box whose poller predates the
# stamp — every reader below MUST degrade to its prior behaviour on None rather
# than treating "no key" as "no contact".
LAST_CAPTAIN_MSG_AT_KEY = "cabinet:last-captain-msg-at"
# Generous by intent: the Captain is ALLOWED to be quiet. A week of zero inbound
# contact is the point at which "quiet Captain" and "dead inbound lane" stop
# being worth distinguishing locally — both deserve a look.
CAPTAIN_INBOUND_SILENCE_S = 7 * 86400
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
# mirrors the one source of truth, platform.yml `briefing_times` — and its
# services.yml calendar mirror — parity-pinned by
# cabinet/scripts/tests/test_briefing_time_parity.py):
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
    # Is the cabinet still actively talking to the Captain? This check WANTED
    # that signal and could not have it: the inbound key carried a message id,
    # not a timestamp, so an id could never express staleness and the code fell
    # back to a bare 7-day file-age floor. The timestamped sibling now exists
    # (LAST_CAPTAIN_MSG_AT_KEY, stamped by the inbound poller), so the check the
    # author described can finally be written.
    #
    # What it buys: a week with no logged decisions is only a LAPSE if there were
    # decisions to log. If the Captain has not said anything since the newest
    # entry, an empty week is correct behaviour, not drift — flagging it trains
    # the reader to ignore this signal. Fail direction is deliberate: an ABSENT
    # key (fresh cabinet, or a poller predating the stamp) leaves the original
    # behaviour byte-for-byte intact, so this can only ever remove false
    # positives, never blind the check.
    age_days = (probe.now() - newest).total_seconds() / 86400.0
    if age_days > 7:
        last_contact = _parse_iso(probe.redis_get(LAST_CAPTAIN_MSG_AT_KEY))
        if last_contact is not None and last_contact <= newest:
            return CheckResult(
                eid, True,
                f"newest captain-decisions.md entry is {age_days:.0f} days old "
                f"({newest:%Y-%m-%d}) but there has been NO Captain contact "
                f"since — nothing to log, so not a logging lapse", skipped=True)
        return CheckResult(
            eid, False,
            f"newest captain-decisions.md entry is {age_days:.0f} days old "
            f"({newest:%Y-%m-%d}) — the real-time decision-logging discipline "
            f"may have lapsed; verify recent Captain decisions were logged")
    return CheckResult(eid, True,
                      f"captain-decisions.md current (newest {newest:%Y-%m-%d})")


def verify_captain_inbound_contact(probe: "Probe") -> CheckResult:
    """OUTCOME: the Captain is still reaching this cabinet — inbound contact
    within CAPTAIN_INBOUND_SILENCE_S.

    SCOPE, STATED HONESTLY. This is the SECOND leg, not the detector. It reads a
    local key written by the local poller and escalates to the Chair, so it
    shares a failure domain with most of what it watches: if the box dies, or
    launchd unloads the sweep, or the Chair is gone, this check dies with them
    and reports nothing. It is worth having anyway because it covers a real and
    distinct shape the off-machine watcher cannot attribute — poller dead while
    the rest of the cabinet is fine — and it names the fault precisely when it
    does fire.

    The PRIMARY inbound detector is the off-machine dead-man
    (framework/liveness/deadman.py, EVENT_CAPTAIN_INBOUND), which alarms on the
    ABSENCE of a ping and therefore survives the outage that silences this row.
    Do not read a green here as "inbound contact is monitored".

    A missing key is SKIP, never a failure: on a fresh cabinet the Captain has
    genuinely never written, and a never-contacted cabinet must not page anyone
    on its first sweep."""
    eid = "captain-inbound-contact"
    raw = probe.redis_get(LAST_CAPTAIN_MSG_AT_KEY)
    last = _parse_iso(raw)
    if last is None:
        return CheckResult(eid, True,
                          "no inbound Captain-contact stamp yet — nothing to "
                          "compare against (fresh cabinet, or the poller "
                          "predates the stamp)", skipped=True)
    age_s = (probe.now() - last).total_seconds()
    if age_s > CAPTAIN_INBOUND_SILENCE_S:
        return CheckResult(
            eid, False,
            f"no inbound message from the Captain for {age_s / 86400.0:.1f} days "
            f"(last {last:%Y-%m-%d %H:%M}Z, floor "
            f"{CAPTAIN_INBOUND_SILENCE_S / 86400.0:.0f}d) — either the inbound "
            f"lane is broken (poller down, token/chat misconfigured) or the "
            f"Captain has genuinely gone quiet; CHECK THE LANE FIRST, because "
            f"this check cannot tell the two apart")
    return CheckResult(eid, True,
                      f"inbound Captain contact {age_s / 3600.0:.1f}h ago "
                      f"({last:%Y-%m-%d %H:%M}Z)")


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
            # Strip a trailing YAML comment from EVERY flow value before
            # matching (apoptosis's sibling parser does the same). Rows
            # annotate inline — `disabled: true   # ABSENCE-DISABLE …`,
            # `schedule: … # daily 03:00` — and a schedule-only strip left
            # `disabled: true  # …` parsing as ENABLED, so parked services
            # false-paged every sweep (bug-hunt 2026-07-14).
            key, val = km.group(1), km.group(2).split("#", 1)[0].strip()
            in_sched_block = False
            if key == "kind":
                cur["kind"] = val
            elif key == "label":
                cur["label"] = val
            elif key == "disabled":
                cur["disabled"] = val.lower() in ("true", "yes", "1")
            elif key == "schedule":
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


# ── COG-4 §9.2 (MR3): per-organ derived floors for composed runner rows ─────
# Composing N services.yml rows into one organ-runner row must NOT delete N
# freshness floors: the runner row EXPLICITLY names its composed organ
# manifests (a block-form `organs:` list, the §9.5 wake-row semantics), and
# each named manifest's `freshness_needs` (`expected_output` artifact token +
# `max_staleness_seconds`) derives ONE expectation PER composed organ,
# asserted by the same no-silent-cron probe BESIDE the per-row expectations.
# A silent organ inside a live runner therefore still trips ITS OWN floor
# (the shared runner log stays fresh; the organ's receipt artifact does not).
# STDLIB ONLY per the survival contract above — a narrow line-parser over
# exactly the manifest shapes the phase-4 contract documents (top-level
# `name:`, a `freshness_needs:` block with two flat keys); anything
# unparseable degrades PER-ENTRY into a LOUD problem line (a composed organ
# without a derivable floor is exactly the escape §9.2 exists to catch),
# and never crashes the check. Reference twin:
# cabinet/scripts/tests/lib_cog4_floors.derive_organ_expectations (the
# conservation checker cross-checks this derivation on the same fixtures).

def _derive_organ_expectation_from_text(text: str):
    """Narrow-parse ONE organ manifest's text → ((name, expected_output,
    max_staleness_seconds), errors). Mirrors the reference-twin strictness:
    name required; `freshness_needs.max_staleness_seconds` an int >= 1;
    `freshness_needs.expected_output` a non-empty token — a manifest that
    cannot yield a floor returns errors, never a silent skip (§9.2)."""
    name: Optional[str] = None
    stale: Optional[int] = None
    out: Optional[str] = None
    in_fn = False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        top = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if top:
            key, val = top.group(1), top.group(2).split("#", 1)[0].strip()
            in_fn = key == "freshness_needs"
            if key == "name" and val:
                name = val.strip("'\"")
            continue
        if in_fn:
            km = re.match(r"^\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if not km:
                continue
            key, val = km.group(1), km.group(2).split("#", 1)[0].strip()
            if key == "max_staleness_seconds":
                try:
                    stale = int(val)
                except ValueError:
                    stale = None
            elif key == "expected_output":
                out = val.strip("'\"") or None
    errors: list[str] = []
    label = name or "<unnamed organ manifest>"
    if not name:
        errors.append("organ manifest carries no non-empty name")
    if stale is None or stale < 1:
        errors.append(f"{label}: freshness_needs.max_staleness_seconds must "
                      "be an integer >= 1 (no floor derivable — §9.2)")
    if not out:
        errors.append(f"{label}: freshness_needs.expected_output must be a "
                      "non-empty token (no probe artifact — §9.2)")
    if errors:
        return None, errors
    return (name, out, stale), []


def _resolve_organ_artifact(token: str) -> str:
    """The declared expected_output token → one probe path: absolute/`~` as
    given (expanduser), else repo-root-relative — the same resolution class as
    SERVICES_MANIFEST above. Never globs, never discovers."""
    p = os.path.expanduser(token)
    if os.path.isabs(p):
        return p
    return str(_cabinet_root() / p)


def _parse_organ_manifests(services_text: str, read_text) -> tuple[list[dict], list[str]]:
    """The §9.2 per-organ floor derivation over cabinet/services.yml: for
    every NON-disabled row carrying a block-form `organs:` list (the composed
    runner rows — the row→manifest association is DECLARED, §9.5), read each
    named manifest via `read_text` (the Probe's file surface; absolute or
    repo-root-relative path) and derive one expectation per composed organ.

    Returns (entries, problems): entries are
    {runner, organ, expected_output, max_staleness_s, manifest} dicts;
    problems are LOUD per-entry derivation failures (an unreadable/unparseable
    declared manifest is a lost floor, never a silent skip). Stdlib only
    (survival contract); a manifest text shape this parser cannot read
    surfaces as a problem for that entry and degrades nothing else."""
    entries: list[dict] = []
    problems: list[str] = []
    cur_name: Optional[str] = None
    cur_disabled = False
    in_organs = False
    declared: list[tuple[str, str]] = []   # (runner row name, manifest ref)
    for raw in (services_text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^  - name:\s*([A-Za-z0-9._-]+)\s*$", line)
        if m:
            cur_name = m.group(1)
            cur_disabled = False
            in_organs = False
            continue
        if cur_name is None:
            continue
        km = re.match(r"^    ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).split("#", 1)[0].strip()
            in_organs = key == "organs" and val == ""
            if key == "disabled":
                cur_disabled = val.lower() in ("true", "yes", "1")
            continue
        if in_organs:
            im = re.match(r"^\s+-\s+(\S+)\s*$", line.split("#", 1)[0].rstrip())
            if im and not cur_disabled:
                declared.append((cur_name, im.group(1)))
    # NOTE: a row whose `disabled:` key follows its `organs:` block would slip
    # the guard above, so re-filter against the full row parse (belt+braces —
    # the same text, the same narrow parser).
    disabled_rows = {e["name"] for e in _parse_services_manifest(services_text)
                     if e.get("disabled")}
    for runner, ref in declared:
        if runner in disabled_rows:
            continue
        path = _resolve_organ_artifact(ref)
        try:
            text = read_text(path)
        except Exception:                                    # noqa: BLE001
            text = None
        if not text:
            problems.append(
                f"{runner}: declared organ manifest {ref!r} unreadable — its "
                "composed floor CANNOT derive (§9.2; a lost floor is a page, "
                "not a skip)")
            continue
        derived, errors = _derive_organ_expectation_from_text(text)
        if derived is None:
            problems.extend(f"{runner}: {err}" for err in errors)
            continue
        organ, out, stale = derived
        entries.append({"runner": runner, "organ": organ,
                        "expected_output": out, "max_staleness_s": stale,
                        "manifest": ref})
    return entries, problems


# Finding severity, worst first — the sort key applied BEFORE truncation (X).
# WHY THIS IS NOT COSMETIC: findings used to be truncated to the first eight in
# APPEND order, and the not-loaded scan appends LAST. So in exactly the situation
# the truncation exists for — a broad outage producing dozens of findings — the
# line naming the CAUSE ("declared but not loaded in launchd") was always the
# first casualty, while eight downstream staleness symptoms survived. Ordering by
# severity first makes the surviving eight the useful eight.
#
# The ranking is causal, not alphabetical: a job launchd does not know about
# cannot run at all; a job with no log anywhere has never run; a non-zero exit is
# a run that failed; staleness and error markers are the symptoms those causes
# produce downstream.
_SEV_NOT_LOADED = 0     # declared/rostered but launchd has never heard of it
_SEV_NO_LOG = 1         # no log at any known path — never ran / not installed
_SEV_EXIT_NONZERO = 2   # the last completed run failed
_SEV_STALE = 3          # loaded and running, but past its freshness floor
_SEV_ORGAN = 4          # a composed organ inside a live runner went quiet
_SEV_MARKER = 5         # an error marker in a recent log tail


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

    # (severity, text) pairs — sorted by severity before truncation (see the
    # _SEV_* table above). The sort is STABLE, so within one severity the
    # original append order (and therefore every existing message string) is
    # preserved exactly.
    problems: list[tuple[int, str]] = []
    for e in watched:
        name = e["name"]
        floor_s = _floor_for_entry(e)
        cands = [(p, probe.file_mtime(p)) for p in _service_log_candidates(name)]
        cands = [(p, mt) for p, mt in cands if mt is not None]
        freshest = max((mt for _p, mt in cands), default=None)

        if floor_s is not None:
            if freshest is None:
                problems.append((_SEV_NO_LOG,
                                 f"{name}: no log at any known path (never ran / "
                                 f"not installed?)"))
                # No log → nothing to marker-scan either.
                continue
            idle_s = now_epoch - freshest
            if idle_s > floor_s:
                problems.append((
                    _SEV_STALE,
                    f"{name}: log silent {idle_s / 3600:.1f}h "
                    f"(> {floor_s / 3600:.1f}h floor) — stalled or not firing"))
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
                problems.append((_SEV_MARKER,
                                 f"{name}: error marker {hit!r} in recent log tail "
                                 f"({path.rsplit('/', 1)[-1]})"))
                break

    # Per-organ derived floors BESIDE the per-row expectations (COG-4 §9.2):
    # composed runner rows declare their organ manifests; each composed organ's
    # expected-output artifact must be fresher than its declared max_staleness.
    # The runner row's OWN log floor + marker scan ran above like any row —
    # these per-organ probes are what keeps N composed floors from collapsing
    # into one shared runner log (a silent organ still trips its own floor).
    organ_entries, organ_problems = _parse_organ_manifests(
        probe.read_text(SERVICES_MANIFEST), probe.read_text)
    problems.extend((_SEV_ORGAN, p) for p in organ_problems)
    for oe in organ_entries:
        artifact = _resolve_organ_artifact(oe["expected_output"])
        mt = probe.file_mtime(artifact)
        if mt is None:
            problems.append((
                _SEV_ORGAN,
                f"{oe['organ']} (organ in {oe['runner']}): expected output "
                f"absent at {artifact} (never produced / not installed?)"))
            continue
        idle_s = now_epoch - mt
        if idle_s > oe["max_staleness_s"]:
            problems.append((
                _SEV_ORGAN,
                f"{oe['organ']} (organ in {oe['runner']}): output stale "
                f"{idle_s / 3600:.1f}h (> {oe['max_staleness_s'] / 3600:.1f}h "
                "declared floor) — the organ is silent inside a live runner"))

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
                problems.append((_SEV_EXIT_NONZERO,
                                 f"{label}: last exit status {status}"))
        # (d) declared-but-not-loaded: an enabled manifest row whose label
        # launchd doesn't know. THE memory-worker failure class — declared in
        # the fleet manifest, hooks feeding its queue, never scheduled. Also
        # deliberately flags a freshly-declared service until its plist is
        # actually bootstrapped (that gap is real downtime, and it self-heals
        # on install).
        for e in watched:
            label = e.get("label")
            if label and label not in ll:
                problems.append((_SEV_NOT_LOADED,
                                 f"{e['name']}: declared in services.yml but not "
                                 f"loaded in launchd ({label})"))

        # NOT DONE HERE — officer not-loaded (the roster mirror). The hole is
        # real and confirmed: the manifest carries ZERO officer rows by design,
        # and the exit-status scan above deliberately EXCLUDES the whole
        # com.cabinet.officer.* prefix (session wrappers exit non-zero
        # legitimately). Both are correct individually, but the manifest's own
        # comment reasons from them that "zero rows here is already a covered
        # case, not a gap" — and that inference is FALSE: an exclusion is not
        # coverage. A booted-out officer (launchctl bootout REMOVES the label)
        # appears in neither scan, so this watchdog is structurally blind to the
        # death of the very Chair it escalates everything to. cabinet-doctor.sh
        # already merges the roster before its per-row check; only this side is
        # blind.
        #
        # Closing it requires comparing launchctl's view against a DECLARED
        # officer set — there is no other mechanical shape, since a booted-out
        # label simply vanishes. Doing that against FULLTIME_OFFICERS
        # contradicts three existing fixtures in
        # framework/watchdog/tests/test_registry.py, whose partial launchctl
        # dicts model a fleet where the rostered officers carry no LaunchAgents
        # and which assert res.ok is True:
        #   test_cron_unrostered_officer_label_not_flagged
        #   test_cron_running_job_prior_exit_status_ignored
        #   test_cron_disabled_row_fully_excluded
        # Those fixtures would each need officer labels added. That is a
        # deliberate, recorded HANDBACK rather than a silent test edit — the
        # fixtures may be encoding a real deployment truth (officers supervised
        # outside launchd on some topologies), and resolving that is a ruling,
        # not a refactor.

    if problems:
        # Severity BEFORE truncation (X) — a stable sort, so message text and
        # within-severity order are unchanged; only WHICH eight survive changes.
        problems.sort(key=lambda p: p[0])
        shown = [text for _sev, text in problems[:8]]
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
PERSONAL_SOURCE_STATE_DIR = state_dir()
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
    # neither pass nor fail (never routed), so a clean-room box with no
    # personal-source pipes never false-alarms on their absence (the "nothing
    # to watch" degrade).
    if not PERSONAL_SOURCE_STATE_DIR:
        return CheckResult(eid, True,
                          "no brain state dir configured — nothing to watch",
                          skipped=True)
    now_epoch = probe.now().timestamp()
    stale = []
    for pipe, (fname, max_stale_s) in PIPE_FRESHNESS.items():
        mtime = probe.file_mtime(f"{PERSONAL_SOURCE_STATE_DIR}/{fname}")
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
# Evidence-plane expectations (Phase 4 — whole-cabinet evidence design
# 2026-07-16 §3 item 1).
#
# WEAK-SIGNAL DOCTRINE (design B9, binding): these expectations ground ONLY
# in INVARIANTS over cheap independent file facts — freshness-class
# (future-dated mtimes), growth (per-trial event cap), continuity-adjacent
# sidecar sanity, and service-outcome liveness. Evidence-PATTERN matches
# (the cluster findings framework/evidence_detectors.py reports) are WEAK
# SIGNALS: they may appear in the Captain report, but they are NEVER
# expectation ground truth here and NEVER all-clear evidence — a watchdog
# whose expectations derive from officer-produced evidence patterns becomes
# an imitable target.
#
# COMPOSE, DON'T DUPLICATE: hash-chain/signature verification is NOT
# re-derived here (registry survival contract — stdlib-only, never import
# framework.evidence, the watched system included): the daily cabinet-doctor
# evidence probes spot-check the newest trial's chain and the evidence-anchor
# job owns store-wide anti-rollback; these rows read only the cheap facts
# around them. The per-trial event cap is PARSED from cabinet-doctor.sh's
# EV_CAP_DEFAULT line (the constant's home, sync-pinned by
# framework/tests/test_evidence_doctor_probes.py) — reused, never minted
# twice; unparseable → that sub-check skips.
#
# STAGED DARK (shadow posture): the shipped instance/config/watchdog.yml
# enable-list deliberately omits these ids — the Captain ceremony that arms
# the Phase-4 services uncomments them there in the same step.
# ─────────────────────────────────────────────────────────────────────────────
_EV_SKEW_S = 900  # future-mtime tolerance (clock-skew grace, not a power bar)

# Deployment-relative surfaces this block watches. Mirrored single-string
# RELs, NOT imports: the survival contract above forbids importing the
# watched plane, and every owning module (framework/onboarding/journey.py
# EVIDENCE_REL, framework/evidence_detectors.py FREEZE_MARKER_REL /
# JOURNAL_REL) imports framework.evidence at module scope — so the values
# are mirrored here and SYNC-PINNED by framework/tests/
# test_evidence_detectors.py (the EV_CAP_DEFAULT pattern: reuse by pinned
# mirror where an import is structurally barred, never a drifting second
# source). The instance/-resident paths are Captain-owned runtime surfaces
# read as config-class facts (mtime/listing/text), never code deps.
_EV_STORE_REL = "instance/evidence/v1"  # = journey.EVIDENCE_REL (A10: never the recorder's env fallback — the env seam is untrusted for watchers)
_EV_ANCHOR_CFG_REL = "instance/config/evidence-anchor.yml"  # = the anchor CLI's binding file
_EV_FREEZE_MARKER_REL = "instance/state/evidence-judging-freeze.json"  # = evidence_detectors.FREEZE_MARKER_REL
_EV_JOURNAL_REL = "shared/interfaces/evidence-shadow-findings.jsonl"  # = evidence_detectors.JOURNAL_REL


def _ev_store_root() -> Path:
    """Doctor parity: $REPO_ROOT/instance/evidence/v1 pinned via the mirrored
    ``_EV_STORE_REL`` — never the recorder's env fallback (A10: the env seam
    is untrusted for watchers)."""
    return _cabinet_root() / _EV_STORE_REL


def _ev_doctor_cap(probe: "Probe") -> Optional[int]:
    """The recorder's per-trial event cap, REUSED from cabinet-doctor.sh's
    ``EV_CAP_DEFAULT=<n>`` line. None (sub-check skips) when unparseable."""
    text = probe.read_text(str(_cabinet_root() / "cabinet" / "scripts"
                               / "cabinet-doctor.sh"))
    m = re.search(r"^EV_CAP_DEFAULT=(\d+)", text or "", re.M)
    return int(m.group(1)) if m else None


def _ev_manifest_entry(probe: "Probe", name: str) -> Optional[dict]:
    """The services.yml row for ``name`` via the existing narrow parser."""
    for entry in _parse_services_manifest(probe.read_text(SERVICES_MANIFEST)):
        if entry.get("name") == name:
            return entry
    return None


def verify_evidence_store_invariants(probe: "Probe") -> CheckResult:
    eid = "evidence-store-invariants"
    store = _ev_store_root()
    trials_dir = store / "trials"
    trial_names = probe.listdir(str(trials_dir))
    sidecar_text = probe.read_text(str(store / ".verify-watermarks.json"))

    if trial_names is None:
        # Not observable (store absent / probe degraded) — plane not
        # activated on this box, or unverifiable: skip, never fail.
        return CheckResult(eid, True,
                           "evidence store not observable (absent or probe "
                           "degraded) — invariants not applicable",
                           skipped=True)
    if not trial_names:
        if sidecar_text.strip():
            # BOTH observations succeeded: an empty trials dir under a
            # surviving watermark sidecar is the affirmative orphan smell
            # (store contents removed while the sidecar survived).
            return CheckResult(eid, False,
                               "watermark sidecar present but the trials dir "
                               "is EMPTY — continuity sidecar orphaned (store "
                               "contents removed?)")
        return CheckResult(eid, True,
                           "evidence plane empty (no trials yet) — "
                           "invariants not applicable", skipped=True)

    problems: list[str] = []
    now_epoch = probe.now().timestamp()

    # Freshness-class invariant: ledger mtimes never sit in the future.
    # (Staleness itself is deliberately NOT paged here — the daily doctor
    # owns it AMBER-max with wake-grace; a kill-switched-quiet store is a
    # legitimate state, not an outcome failure.)
    for name in trial_names:
        mtime = probe.file_mtime(str(trials_dir / name / "events.jsonl"))
        if mtime is not None and mtime > now_epoch + _EV_SKEW_S:
            problems.append(f"future-dated ledger mtime in {name} "
                            f"(+{int(mtime - now_epoch)}s)")

    # Growth invariant: today's/yesterday's day-bounded trials stay within
    # the recorder's enforced per-trial event cap (a breach means the cap
    # failed — segments should have chained instead).
    cap = _ev_doctor_cap(probe)
    if cap:
        now_dt = probe.now()
        days = {now_dt.strftime("%Y%m%d"),
                (now_dt - _dt.timedelta(days=1)).strftime("%Y%m%d")}
        for name in trial_names:
            if name[-8:] in days:
                ledger_text = probe.read_text(str(trials_dir / name
                                                  / "events.jsonl"))
                events = ledger_text.count("\n")
                if events > cap:
                    problems.append(f"{name} holds {events} events > "
                                    f"per-trial cap {cap} (recorder growth "
                                    "invariant breached)")

    # Continuity-adjacent sanity: a PRESENT sidecar must parse as a JSON
    # object (a corrupted sidecar degrades anti-rollback protection). Chain
    # verification itself composes with the doctor/anchor jobs (above).
    if sidecar_text.strip():
        try:
            if not isinstance(json.loads(sidecar_text), dict):
                problems.append("watermark sidecar is not a JSON object — "
                                "anti-rollback protection degraded")
        except ValueError:
            problems.append("watermark sidecar unparseable — anti-rollback "
                            "protection degraded")

    if problems:
        return CheckResult(eid, False,
                           "evidence-store invariant violation: "
                           + "; ".join(problems[:4]))
    return CheckResult(eid, True,
                       f"evidence store facts sane ({len(trial_names)} "
                       "trials; no future mtimes, day trials within cap, "
                       "sidecar parseable)")


def verify_evidence_anchor_fresh(probe: "Probe") -> CheckResult:
    eid = "evidence-anchor-export-fresh"
    # Narrow stdlib parse of the instance binding (survival contract: no
    # PyYAML) — mirrors evidence-anchor.py's own credless-safe posture:
    # unconfigured surfaces skip cleanly.
    anchor_dir = ""
    for raw in probe.read_text(str(_cabinet_root()
                                   / _EV_ANCHOR_CFG_REL)).splitlines():
        m = re.match(r"^anchor_dir:\s*(.+?)\s*$", raw.strip())
        if m:
            anchor_dir = m.group(1).split("#", 1)[0].strip().strip("'\"")
            break
    if not anchor_dir:
        return CheckResult(eid, True,
                           "anchor_dir unconfigured — external anchoring not "
                           "bound on this deployment", skipped=True)
    entry = _ev_manifest_entry(probe, "evidence-anchor")
    if entry is None or entry.get("disabled"):
        return CheckResult(eid, True,
                           "evidence-anchor service staged dark — no export "
                           "floor applies yet (Captain ceremony enables it)",
                           skipped=True)
    anchors = (Path(os.path.expandvars(anchor_dir)).expanduser()
               / "evidence-anchors.jsonl")
    floor = _floor_for_entry(entry) or 26 * 3600
    mtime = probe.file_mtime(str(anchors))
    if mtime is None:
        return CheckResult(eid, False,
                           f"anchor export missing: {anchors} absent while "
                           "the evidence-anchor service is enabled — the "
                           "external anti-rollback anchor is not landing")
    age = probe.now().timestamp() - mtime
    if age > floor:
        return CheckResult(eid, False,
                           f"anchor export stale: {anchors} is "
                           f"{int(age / 3600)}h old > floor "
                           f"{int(floor / 3600)}h — the external "
                           "anti-rollback anchor is not landing")
    return CheckResult(eid, True,
                       f"anchor export fresh ({int(age / 3600)}h old, floor "
                       f"{int(floor / 3600)}h)")


def verify_evidence_detector_liveness(probe: "Probe") -> CheckResult:
    """Detector-service OUTCOME liveness — did the shadow detector's report
    actually land, not just that its job ran. Reads the journal's mtime
    ONLY; finding CONTENTS are never read here (shadow law: nothing
    downstream consumes detector output — liveness is about the service,
    never the findings)."""
    eid = "evidence-shadow-detector-liveness"
    entry = _ev_manifest_entry(probe, "evidence-shadow-detectors")
    if entry is None or entry.get("disabled"):
        return CheckResult(eid, True,
                           "evidence-shadow-detectors staged dark (shadow "
                           "law) — liveness floor not armed", skipped=True)
    # §2.4 freeze respect: while the judging-freeze marker is present the
    # detector REFUSES to run by contract — a quiet journal is the correct
    # outcome, not a failure (the freeze path already paged the Chair).
    marker = _cabinet_root() / _EV_FREEZE_MARKER_REL
    if probe.file_mtime(str(marker)) is not None:
        return CheckResult(eid, True,
                           "judging-freeze marker present — detector refusal "
                           "is the correct outcome", skipped=True)
    journal = _cabinet_root() / _EV_JOURNAL_REL
    floor = _floor_for_entry(entry) or 26 * 3600
    mtime = probe.file_mtime(str(journal))
    if mtime is None:
        return CheckResult(eid, False,
                           "evidence-shadow-detectors is enabled but its "
                           f"findings journal ({journal}) has never been "
                           "appended — the shadow report is not landing")
    age = probe.now().timestamp() - mtime
    if age > floor:
        return CheckResult(eid, False,
                           f"shadow findings journal stale ({int(age / 3600)}h "
                           f"old > floor {int(floor / 3600)}h) — the detector "
                           "service is enabled but its report is not landing")
    return CheckResult(eid, True,
                       f"shadow findings journal fresh ({int(age / 3600)}h "
                       f"old, floor {int(floor / 3600)}h)")


# ─────────────────────────────────────────────────────────────────────────────
# SPEND ANOMALY ROWS (2026-07-26) — what replaced the spend caps.
#
# The Captain removed every dollar cap, then refined the ruling: do NOT build a
# threshold alarm. Money is not the scarce resource — the work rides a flat
# subscription — and Captain ATTENTION is. So a big-but-normal spend week must
# be SILENT. What these rows watch is not the size of a number but its SHAPE
# against the cabinet's own history:
#
#   spend-without-output  cost climbing while nothing is delivered = a runaway
#                         loop, which is exactly what removing the caps makes
#                         possible. Cost climbing alongside delivered work is
#                         the system doing its job and says nothing.
#   spend-lane-anomaly    one lane 20x its own normal, or a lane that has never
#                         billed suddenly billing (a new paid vendor, a
#                         mispriced call, a loop hammering one API).
#   meter-silent          the watch on the watch. With no cap, nothing else
#                         reads the spend ledger — so a dead meter is invisible
#                         and every row above goes quietly green forever.
#
# ALL THREE ARE RELATIVE, NEVER ABSOLUTE. No dollar figure appears in any
# threshold below, deliberately: a constant would need re-tuning every time the
# fleet grows and would page on a busy week, which trains the reader to ignore
# the row. And all three DEFAULT TO SILENCE — insufficient history skips, an
# unreadable source skips. A spend watch that guesses is worse than none.
#
# WHERE THE HISTORY COMES FROM. The Redis cost ledgers carry an 8-day TTL, so
# they cannot supply a trailing baseline. The durable record is the daily
# falsifier series (shared/interfaces/falsifier-series.jsonl), whose line now
# carries a `spend` block (cabinet/scripts/falsifier-report.py::_spend_block).
# Reading that FILE also keeps the independence law intact: the watchdog never
# imports framework.cost, framework.fidelity or framework.frontdoor — the
# systems it is watching here — it reads the artifact they leave behind.
# ─────────────────────────────────────────────────────────────────────────────
FALSIFIER_SERIES = str(
    _cabinet_root() / "shared" / "interfaces" / "falsifier-series.jsonl"
)
# One line per day. 30 days is long enough that a fortnight of quiet still
# leaves a baseline, and short enough that a genuine step-change in how the
# cabinet works ages out of the comparison within a month.
SPEND_LOOKBACK_DAYS = 30
# The series is appended daily (08:05). Two days of tolerance covers one missed
# run + a host that slept; past that the tail is not evidence about today and
# the rows skip rather than compare against a stale day.
SPEND_SERIES_MAX_AGE_S = 48 * 3600
# "Materially up" = at least this multiple of the trailing median. 2x is the
# smallest step that cannot be ordinary variance between two working days.
SPEND_RISE_FACTOR = 2.0
# Baseline days required before spend-without-output will speak. Fewer than
# five DELIVERING days and the median is one anomaly away from meaningless, so
# the row stays silent — a fresh cabinet must never page about its own first
# week.
SPEND_MIN_DELIVERING_DAYS = 5
# A lane 20x its own normal. Huge on purpose: this row exists for a runaway,
# not for a busy afternoon.
LANE_SPIKE_FACTOR = 20.0
# Days of OBSERVED lane history (the day's lane block was readable) before the
# lane row will speak at all.
LANE_MIN_HISTORY_DAYS = 7
# Of those, days on which the lane ACTUALLY billed, before a median of its
# spend means anything. A lane with zero billing days is the "never billed
# before" arm instead; between 1 and 2 it stays silent — no guessed constant
# ever stands in for missing history.
LANE_MIN_BILLING_DAYS = 3
# The officer/session spend ledger meter.py writes (UTC-daily).
COST_TOKENS_DAILY_PREFIX = "cabinet:cost:tokens:daily:"
# Durable per-officer work stamp (post-tool-use hook, ISO-8601) — the same
# signal verify_officer_reflection uses, reused rather than re-derived.
LAST_TOOLCALL_PREFIX = "cabinet:last-toolcall:"
# An officer only counts as "should already be billed" once their last toolcall
# is this old: a turn still in flight has not reached its Stop hook, so it is
# not yet in the ledger and its absence proves nothing. Also, by construction,
# nothing can satisfy this in the first 15 minutes of a UTC day — which is what
# keeps the row quiet across the midnight ledger rollover.
METER_STOP_GRACE_S = 900


def _median(values: list) -> Optional[float]:
    """Median of a non-empty numeric list, else None. Median, not mean: one
    runaway day must not drag the baseline it is being compared against."""
    xs = sorted(float(v) for v in values)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def _read_spend_series(probe: "Probe", limit: int = SPEND_LOOKBACK_DAYS) -> list:
    """The tail of the falsifier series, oldest→newest, dated lines only.

    Corrupt lines are skipped (same tolerance as every other reader of this
    file) — one bad append must never cost the good history. Returns [] when
    the file is absent or unreadable, which every caller treats as
    unobservable-skip, never as zero."""
    text = probe.read_text(FALSIFIER_SERIES)
    if not text.strip():
        return []
    docs: list = []
    # Read generously past `limit` so a run of corrupt lines cannot starve the
    # window, then trim to the newest `limit` usable days.
    for raw in text.splitlines()[-(limit * 3):]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("date"):
            docs.append(doc)
    return docs[-limit:]


def _series_fresh(probe: "Probe", doc: dict) -> bool:
    """Is this line recent enough to say anything about now?"""
    d = _parse_iso(str(doc.get("date") or "") + "T00:00:00")
    if d is None:
        return False
    return (probe.now() - d).total_seconds() <= SPEND_SERIES_MAX_AGE_S


def _day_total_micro(doc: dict) -> Optional[int]:
    """That day's total officer spend, or None when the day has no figures.
    None is NO EVIDENCE — never a zero (see _spend_block's null convention)."""
    spend = doc.get("spend")
    if not isinstance(spend, dict):
        return None
    val = spend.get("total_cost_micro")
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# The delivered-output numerators the daily job already computes from the
# consequence ledger. THIS is the output signal, and it is chosen over calling
# framework.fidelity.consequence.read_ledger() directly for two reasons:
#   * INDEPENDENCE. A verify importing the fidelity plane would put the
#     watchdog on top of one of the systems it watches — the one law this
#     module is built around. Reading the artifact keeps that intact.
#   * COST. read_ledger() parses and de-duplicates every consequence row in
#     every jsonl in the log dir. This sweep runs at :00 and :30 forever, and
#     the same numbers are already computed once a day by the job that owns
#     them. Re-deriving them 48x a day to learn a fact that changes once is
#     precisely the "cheapest honest probe" rule the registry opens with.
# The numerators are 7-DAY rolling windows, so "zero" here means a whole week
# with nothing acted, nothing approved, no proactive card and no label — a
# deliberately conservative bar for calling something a runaway.
_OUTPUT_KEYS = ("acted_7d", "approved_7d", "proactive_cards_7d")


def _output_total(doc: dict) -> Optional[int]:
    """Delivered-output units for that line, or None when the line carries no
    output numerators at all (a truncated/older line — no evidence)."""
    seen = False
    total = 0
    for k in _OUTPUT_KEYS:
        v = doc.get(k)
        if isinstance(v, bool) or not isinstance(v, int):
            continue
        seen = True
        total += v
    labels = doc.get("labels_7d")
    if isinstance(labels, dict):
        for k in ("verdict", "outcome_resolved"):
            v = labels.get(k)
            if isinstance(v, bool) or not isinstance(v, int):
                continue
            seen = True
            total += v
    return total if seen else None


def _skip(eid: str, why: str) -> CheckResult:
    """A skip is neither pass nor failure — the row could not observe."""
    return CheckResult(eid, True, why, skipped=True)


def _never_raises(fn):
    """Turn any escaping exception into a SKIP.

    check.run() already catches a raising verify — but it turns it into a
    FAILURE, which for these rows would page the Chair about money every
    cooldown window on the strength of a parse bug. A sensor that cannot read
    its input has observed nothing, so it must say so; the reason still lands
    in the sweep log line (visible as a skip with its exception named), so this
    hides nothing — it only refuses to dress a broken reader as a finding.

    ``functools.wraps`` is load-bearing, not cosmetic: it sets ``__wrapped__``
    so ``inspect.getsource`` unwraps to the REAL verify. Without it a source-
    reading test (the one pinning that no verify hardcodes a money amount)
    silently inspects this three-line wrapper instead and passes on anything."""
    @functools.wraps(fn)
    def wrapped(probe: "Probe") -> CheckResult:
        try:
            return fn(probe)
        except Exception as e:  # noqa: BLE001
            return _skip(fn.__name__.replace("verify_", "").replace("_", "-"),
                         f"spend check could not run ({type(e).__name__}: "
                         f"{str(e)[:120]}) — observed nothing, so reporting "
                         f"nothing")
    return wrapped


@_never_raises
def verify_spend_without_output(probe: "Probe") -> CheckResult:
    """OUTCOME: the cabinet is not burning money while delivering nothing.

    THE ONE THAT MATTERS. Spend rising with work shipped is the system working.
    Spend rising with a whole week of nothing acted, nothing approved, no
    proactive card and no label is a loop eating tokens in a circle — the exact
    failure that removing the caps makes possible, and the only spend shape
    worth a human's attention.

    Fires only when BOTH hold: today's officer spend is at least
    SPEND_RISE_FACTOR x the trailing median of DELIVERING days, and this line's
    output numerators are all zero. Comparing against delivering days (rather
    than against all days) is what keeps the row alive during a sustained
    runaway: the baseline stays pinned to what a productive day cost instead of
    drifting up to meet the anomaly.

    Silent whenever it cannot know: no series, a stale series, no spend figures
    for the day, no output numerators, or fewer than SPEND_MIN_DELIVERING_DAYS
    delivering days on record."""
    eid = "spend-without-output"
    series = _read_spend_series(probe)
    if not series:
        return _skip(eid, f"no readable falsifier series at {FALSIFIER_SERIES} "
                          f"— spend history not observable")
    latest = series[-1]
    if not _series_fresh(probe, latest):
        return _skip(eid, f"falsifier series tail is stale (newest line "
                          f"{latest.get('date')}) — not evidence about today")
    today_total = _day_total_micro(latest)
    if today_total is None:
        return _skip(eid, f"no spend figures on the {latest.get('date')} line "
                          f"— the meter or Redis was unreadable that day")
    out_today = _output_total(latest)
    if out_today is None:
        return _skip(eid, f"the {latest.get('date')} line carries no output "
                          f"numerators — cannot tell delivery from silence")
    if out_today > 0:
        return CheckResult(eid, True,
                           f"spend accompanied by delivered work "
                           f"({out_today} output units in the 7d window) — "
                           f"cost with output is the system working")

    baseline: list = []
    for doc in series[:-1]:
        total = _day_total_micro(doc)
        out = _output_total(doc)
        if total is None or out is None or out <= 0 or total <= 0:
            continue
        baseline.append(total)
    if len(baseline) < SPEND_MIN_DELIVERING_DAYS:
        return _skip(eid, f"only {len(baseline)} delivering day(s) of spend "
                          f"history (need {SPEND_MIN_DELIVERING_DAYS}) — no "
                          f"baseline for what normal costs, staying silent")
    med = _median(baseline)
    if not med or med <= 0:
        return _skip(eid, "trailing median spend is zero — no baseline")
    if today_total < SPEND_RISE_FACTOR * med:
        return CheckResult(eid, True,
                           f"no output in the 7d window, but spend is not up "
                           f"(${today_total / 1e6:,.2f} vs ${med / 1e6:,.2f} "
                           f"median of {len(baseline)} delivering days) — a "
                           f"quiet cabinet, not a runaway")
    return CheckResult(
        eid, False,
        f"SPEND WITHOUT OUTPUT on {latest.get('date')}: ${today_total / 1e6:,.2f} "
        f"spent ({today_total / med:.1f}x the ${med / 1e6:,.2f} median of "
        f"{len(baseline)} delivering days) while the 7d output window is EMPTY "
        f"(0 acted, 0 approved, 0 proactive cards, 0 labels). Cost is climbing "
        f"and nothing is being delivered — find the loop that is spending and "
        f"shipping nothing, and stop it.")


def _lane_figures(doc: dict) -> Optional[dict]:
    """That day's lane rollups, or None when the day's lanes were not observed.
    A lane MISSING from an observed day is an affirmative zero for that lane;
    a missing DAY is no evidence at all — the two must not be conflated."""
    spend = doc.get("spend")
    if not isinstance(spend, dict):
        return None
    lanes = spend.get("lanes")
    return lanes if isinstance(lanes, dict) else None


def _lane_dim(lanes: dict, lane: str, dim: str) -> Optional[int]:
    """One lane dimension on one observed day: an int, or None when that
    dimension was never recorded (an unpriced lane has NO cost_micro — not a
    zero one)."""
    fig = lanes.get(lane)
    if not isinstance(fig, dict) or fig.get(dim) is None:
        return None
    try:
        return int(fig[dim])
    except (TypeError, ValueError):
        return None


@_never_raises
def verify_spend_lane_anomaly(probe: "Probe") -> CheckResult:
    """OUTCOME: no paid lane is spending unlike itself.

    Two shapes, both judged against the lane's OWN history and nothing else:
      * a lane at >= LANE_SPIKE_FACTOR x the median of the days it actually
        billed; and
      * a lane with NO billing history at all that starts billing — a new paid
        vendor, or an existing one that just became chargeable, which is a fact
        somebody chose to be true and nobody was told about.
    Unpriced lanes (meter.py knows no rate for embeddings/rerank/tts/stt/
    websearch) are watched on CALL VOLUME with the same multiple — leaving the
    lanes most able to run away unwatched because we cannot price them would be
    a sensor pointed away from the risk. Their finding says "calls", never
    dollars.

    HISTORY REQUIRED, else silence: LANE_MIN_HISTORY_DAYS observed days before
    the row speaks at all, and LANE_MIN_BILLING_DAYS days on which a lane
    actually billed before its median means anything. A lane with 1-2 billing
    days is deliberately invisible here — a median of two points is a guess,
    and this row does not guess."""
    eid = "spend-lane-anomaly"
    series = _read_spend_series(probe)
    if not series:
        return _skip(eid, f"no readable falsifier series at {FALSIFIER_SERIES} "
                          f"— lane history not observable")
    latest = series[-1]
    if not _series_fresh(probe, latest):
        return _skip(eid, f"falsifier series tail is stale (newest line "
                          f"{latest.get('date')}) — not evidence about today")
    today = _lane_figures(latest)
    if today is None:
        return _skip(eid, f"no lane figures on the {latest.get('date')} line "
                          f"— the lane ledger was unreadable that day")
    prior = [lanes for lanes in (_lane_figures(d) for d in series[:-1])
             if lanes is not None]
    if len(prior) < LANE_MIN_HISTORY_DAYS:
        return _skip(eid, f"only {len(prior)} observed day(s) of lane history "
                          f"(need {LANE_MIN_HISTORY_DAYS}) — no median to "
                          f"compare against, staying silent")

    findings: list = []
    for lane in sorted(today):
        cost_today = _lane_dim(today, lane, "cost_micro")
        if cost_today is not None and cost_today > 0:
            # A lane absent from an observed day billed 0 that day — an
            # affirmative observation, which is what makes "never billed
            # before" a statement rather than an absence of data.
            billed = [c for c in (_lane_dim(p, lane, "cost_micro") or 0
                                  for p in prior) if c > 0]
            if not billed:
                findings.append(
                    f"{lane} billed ${cost_today / 1e6:,.2f} today with NO "
                    f"billing history in {len(prior)} observed days — a paid "
                    f"lane that was never paid before")
                continue
            if len(billed) < LANE_MIN_BILLING_DAYS:
                continue  # too little history to call anything unusual
            med = _median(billed)
            if med and cost_today >= LANE_SPIKE_FACTOR * med:
                findings.append(
                    f"{lane} spent ${cost_today / 1e6:,.2f} — "
                    f"{cost_today / med:.0f}x its ${med / 1e6:,.2f} median "
                    f"over {len(billed)} billing days")
            continue

        # Unpriced lane: it has no cost today and has never recorded one, so
        # the only honest axis is calls. Never rendered as dollars.
        if any(_lane_dim(p, lane, "cost_micro") is not None for p in prior):
            continue  # priced lane simply idle today — nothing to say
        calls_today = _lane_dim(today, lane, "calls") or 0
        if calls_today <= 0:
            continue
        used = [c for c in (_lane_dim(p, lane, "calls") or 0 for p in prior)
                if c > 0]
        if len(used) < LANE_MIN_BILLING_DAYS:
            continue
        med = _median(used)
        if med and calls_today >= LANE_SPIKE_FACTOR * med:
            findings.append(
                f"{lane} made {calls_today:,} calls (unpriced) — "
                f"{calls_today / med:.0f}x its median of {med:,.0f} over "
                f"{len(used)} active days")

    if findings:
        return CheckResult(
            eid, False,
            f"lane spend unlike itself on {latest.get('date')}: "
            + "; ".join(findings[:4])
            + ". Judged against each lane's own history, not a budget — find "
              "what changed for that lane.")
    return CheckResult(eid, True,
                       f"every lane within its own normal ({len(today)} lanes "
                       f"active, {len(prior)} days of history)")


@_never_raises
def verify_meter_silent(probe: "Probe") -> CheckResult:
    """OUTCOME: the spend ledger is still recording — the watch on the watch.

    While a spend CAP existed, a dead meter announced itself: the gate read $0
    and behaved oddly. With the caps gone nothing else reads this ledger, so a
    meter that stops writing is completely invisible — and it takes both rows
    above down with it, silently and permanently green.

    Fires when officers demonstrably worked today and today's ledger is
    OBSERVED empty (or observed with zero total spend, which is the same
    silence wearing a different hat — e.g. token dimensions landing while the
    cost field does not).

    The None-vs-{} distinction is the whole check: ``None`` from HGETALL means
    Redis was unreadable and NOTHING follows from it (skip); ``{}`` means the
    hash genuinely holds nothing while officers were working, which is the
    alarm. Collapsing the two would either page on every Redis blip or, worse,
    read a dead meter as fine.

    Work signal: the durable ``cabinet:last-toolcall:<officer>`` stamp, reused
    from verify_officer_reflection rather than re-derived. An officer counts
    only once their last toolcall is METER_STOP_GRACE_S old, so a turn still in
    flight (not yet through its Stop hook, so legitimately not yet billed) is
    never the evidence — which also makes the row structurally quiet across the
    UTC midnight rollover. KNOWN LIMIT, stated rather than hidden: an officer
    who is continuously mid-turn on every sweep never satisfies the grace, so a
    fleet with exactly one permanently-hot officer could stay silent. Erring
    toward silence is the correct direction for a row that spends attention."""
    eid = "meter-silent"
    if not FULLTIME_OFFICERS:
        return _skip(eid, "no officer roster configured — nothing to expect "
                          "spend from")
    now = probe.now()
    date = now.strftime("%Y-%m-%d")
    fields = probe.redis_hgetall(COST_TOKENS_DAILY_PREFIX + date)
    if fields is None:
        return _skip(eid, "spend ledger not observable (Redis unreadable or "
                          "an older probe) — no conclusion available")

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    worked: list = []
    for officer in FULLTIME_OFFICERS:
        tc = _parse_iso(probe.redis_get(LAST_TOOLCALL_PREFIX + officer))
        if tc is None or tc < midnight:
            continue
        if (now - tc).total_seconds() < METER_STOP_GRACE_S:
            continue  # turn may still be in flight — not yet billable
        worked.append(officer)
    if not worked:
        return CheckResult(eid, True,
                           "no officer has a billable toolcall today — an "
                           "empty spend ledger is the correct outcome")

    total = 0
    for name, raw in fields.items():
        if not name.endswith("_cost_micro"):
            continue
        try:
            total += int(raw)
        except (TypeError, ValueError):
            continue
    if not fields:
        return CheckResult(
            eid, False,
            f"METER SILENT: {len(worked)} officer(s) worked today "
            f"({', '.join(worked)}) but the {date} spend ledger is EMPTY. "
            f"Nothing else reads this ledger since the caps were removed, so "
            f"every spend check is now blind — check the Stop hook and "
            f"redis-cli reachability before trusting any spend readout.")
    if total <= 0:
        return CheckResult(
            eid, False,
            f"METER SILENT: {len(worked)} officer(s) worked today "
            f"({', '.join(worked)}) and the {date} ledger has "
            f"{len(fields)} field(s) but ZERO recorded cost. The meter is "
            f"writing token dimensions without pricing them — every spend "
            f"check is reading a fabricated zero.")
    return CheckResult(eid, True,
                       f"spend ledger live (${total / 1e6:,.2f} across "
                       f"{len(fields)} fields; {len(worked)} officer(s) "
                       f"worked today)")


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
    # ── Phase-4 evidence-plane rows (STAGED DARK — see the doctrine block
    # above the verifies; the shipped instance enable-list omits these ids
    # until the Captain ceremony arms them). All ESCALATE_CHAIR: evidence-
    # plane rot needs judgment, and P-Alerts-To-Chair means the Chair
    # absorbs it — never the Captain directly (§2.4).
    Expectation(
        id="evidence-store-invariants",
        what="Evidence-store facts stay invariant-sane: no future-dated "
             "ledger mtimes, day trials within the recorder's per-trial "
             "event cap (cap parsed from cabinet-doctor.sh, never minted "
             "twice), watermark sidecar parseable and never orphaned. "
             "Grounded in invariants only — evidence-pattern matches are "
             "weak signals and never expectation ground truth (B9); chain "
             "verification composes with the daily doctor probe + anchor "
             "job.",
        cadence_s=24 * 3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_evidence_store_invariants,
    ),
    Expectation(
        id="evidence-anchor-export-fresh",
        what="The daily external evidence anchor actually LANDED (anchors "
             "file fresh in the configured Captain-owned surface) — the "
             "anti-rollback residual stays closed, not just scheduled. "
             "Skips while unconfigured or staged dark.",
        cadence_s=24 * 3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_evidence_anchor_fresh,
    ),
    Expectation(
        id="evidence-shadow-detector-liveness",
        what="The Phase-4 shadow detector's Captain-facing findings journal "
             "keeps landing while its service is enabled (outcome liveness "
             "only — finding contents are never read; shadow law). Skips "
             "while staged dark or judging-frozen.",
        cadence_s=24 * 3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_evidence_detector_liveness,
    ),
    # APPENDED AT THE END, and SHIPS STAGED DARK — the same convention the
    # Phase-4 evidence rows use. Two reasons, both deliberate:
    #   * position: the enable-order pins in test_registry.py read catalog[:5],
    #     so a row inserted mid-catalog would silently redefine what those pins
    #     assert. Appending leaves every existing pin meaning what it meant.
    #   * dark: enabling it here would change the enabled-row COUNT, which those
    #     same pins fix at 5. Arming is therefore a one-line instance-config
    #     change (uncomment `captain-inbound-contact` in
    #     instance/config/watchdog.yml), not a code change — see that file.
    # The mechanism is fully built and tested either way; only the local
    # SECOND-leg alert is dark. The PRIMARY inbound detector is the off-machine
    # dead-man (framework/liveness/deadman.py), which is independent of this row
    # and of this whole watchdog.
    Expectation(
        id="captain-inbound-contact",
        what=f"{captain_name()} is still reaching this cabinet — an inbound "
             f"message within {CAPTAIN_INBOUND_SILENCE_S // 86400}d. SECOND "
             f"LEG only: the primary inbound detector is the off-machine "
             f"dead-man, which alarms on the ABSENCE of a ping and so survives "
             f"the outage that would silence this row.",
        cadence_s=CAPTAIN_INBOUND_SILENCE_S,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_captain_inbound_contact,
    ),
    # ── Spend anomaly rows (2026-07-26). APPENDED, like every row above, so the
    # catalog-order pins keep meaning what they meant. These ship ENABLED (the
    # instance list names them): unlike the Phase-4 rows there is no ceremony
    # to wait for, and unlike a cap they cost nothing while quiet — every one
    # of them defaults to silence and only speaks when the cabinet's spend
    # stops looking like the cabinet's own history. ESCALATE_CHAIR because
    # every operational alert goes to the Chair; nothing here reaches the
    # Captain unless the Chair judges that it should.
    Expectation(
        id="spend-without-output",
        what="Cost is not climbing while NOTHING is being delivered — spend "
             "materially above the trailing median of delivering days with an "
             "empty 7-day output window is a runaway loop. Spend that "
             "accompanies delivered work is the system working and is never "
             "reported.",
        cadence_s=24 * 3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_spend_without_output,
    ),
    Expectation(
        id="spend-lane-anomaly",
        what="No paid lane is spending unlike ITSELF — a lane at 20x the "
             "median of the days it billed, or a lane with no billing history "
             "at all suddenly billing. Unpriced lanes are watched on call "
             "volume, never reported as dollars. Silent without enough "
             "history to hold a median.",
        cadence_s=24 * 3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_spend_lane_anomaly,
    ),
    Expectation(
        id="meter-silent",
        what="The spend ledger is still recording while officers work — the "
             "watch on the watch. With the caps removed nothing else reads it, "
             "so a dead meter would take every spend check down with it, "
             "silently green.",
        cadence_s=3600,
        tier=Tier.ESCALATE_CHAIR,
        verify=verify_meter_silent,
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
