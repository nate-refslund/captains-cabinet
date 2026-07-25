"""Captain-contact dead-man heartbeat emitter (D1).

WHAT THIS IS. ``emit(event)`` pings an off-machine watcher at the exact moment a
real contact event happens — an outbound message CONFIRMED delivered to the
Captain's transport, or the inbound poller advancing its offset on a Captain
message. The watcher alarms when the ping STOPS. Nothing in this module decides
anything; there is no threshold here and no alert path here.

WHY IT IS SHAPED THIS WAY (the independence test). A detector is only worth
building if the outage cannot disable it:

  * a launchd-scheduled check is NOT independent — the outage class is
    launchd-level, so the same event removes the fault and its detector;
  * an on-box monitor messaging out is PARTIALLY independent — it bypasses the
    officer lane but shares the machine;
  * an off-machine watcher waiting for a ping IS independent — it alarms on
    ABSENCE, and absence is exactly what an outage produces.

So this module never raises an alarm and never talks to the Captain. It is a
heartbeat that the act of talking EMITS. That also makes it the north-star
instrument: time-since-last-confirmed-contact is both the alarm and the
denominator of "value per unit of Captain attention".

WHAT IT DELIBERATELY IS NOT. This is not a direct-to-Captain alert tier. The
constitution's P-Alerts-To-Chair rule stands untouched: every operational alert
still routes to the Chair, and the Chair decides what reaches the Captain (see
``framework/watchdog/registry.py``'s Tier enum). An ABSENCE detector living
outside the lane is a different object from an alert tier inside it — this
module adds the former and leaves the latter exactly as it was.

SURVIVAL CONTRACT. Standard library ONLY, and the HTTP call is inlined with
``urllib`` rather than routed through the probe helpers — the probes are
themselves watched services, and a heartbeat that imports what it watches dies
with it. The ONE optional framework import (``framework.env``, a pure path
resolver) is guarded: if it cannot be imported, path resolution falls back to
the env override and the emitter stays inert rather than failing.

FAIL DIRECTION. ``emit`` NEVER raises and NEVER blocks for long. It is called
from the Captain send path, so a heartbeat failure must never cost a message: a
dead watcher, a bad URL, a DNS hole and a missing config all return a result
dict with ``emitted=False`` and a machine-readable ``reason``. The honest
consequence of an unreachable watcher is that the watcher stops seeing pings and
alarms — which is correct, not a bug.

INERT BY DEFAULT. A fresh clone pings nothing. Configuration is opt-in and
deployment-local; WHERE it lives is not this module's business — the location
resolves through the one ratified env seam, ``framework.env
.liveness_config_path()`` (``CABINET_LIVENESS_CONFIG`` overrides per process),
so this file carries no instance path token. The shipped ``.example`` twin
beside that path documents the shape. Activation — registering the watcher and
pasting real slugs — is a deployment step, never something this code does on
its own.

MULTI-TENANCY (load-bearing, not a nicety). N cabinets share one host, so every
slug MUST be per-instance: two instances pinging one slug make a DEAD instance
indistinguishable from a QUIET one, which is precisely the confusion this whole
detector exists to remove. The config therefore REQUIRES a non-empty
``instance_id:`` field before any event can fire, even when a slug is present — an
operator who copies a config between instances gets silence and a `no-instance`
reason, never a false all-clear on a neighbour's slug.
"""
from __future__ import annotations

import os
import re
import urllib.error
import urllib.request

# Events this emitter knows. Both are CONTACT events, not machinery events.
EVENT_CAPTAIN_OUTBOUND = "captain_outbound"
EVENT_CAPTAIN_INBOUND = "captain_inbound"
KNOWN_EVENTS = (EVENT_CAPTAIN_OUTBOUND, EVENT_CAPTAIN_INBOUND)

# Config path override (mirrors CABINET_WATCHDOG_CONFIG's per-process override
# idiom). Consulted BEFORE framework.env so the emitter still resolves a config
# on a tree where framework.env is unimportable.
CONFIG_ENV = "CABINET_LIVENESS_CONFIG"

# A slug goes into a URL path, so it is validated as a path segment and never
# escaped-and-hoped: anything outside this set is refused (`bad-slug`) rather
# than quoted, because a slug that needs quoting is an operator typo, not a
# legitimate identifier.
_SLUG_RE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
# The instance id mirrors the project-slug guard shape used by the trigger lib
# (lowercase, hyphenated, bounded) so one vocabulary covers both.
_INSTANCE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_ALLOWED_SCHEMES = ("http://", "https://")

# Short by construction: this runs INSIDE the Captain send path, so the ceiling
# on added latency matters more than catching a slow watcher. Clamped, so a
# fat-fingered config cannot stall a briefing.
_DEFAULT_TIMEOUT_S = 3
_MIN_TIMEOUT_S = 1
_MAX_TIMEOUT_S = 30


def config_path(default: str = "") -> str:
    """Resolve the liveness config path through the ratified env seam.

    ``CABINET_LIVENESS_CONFIG`` wins (per-process override, ``~``-expanded);
    otherwise ``framework.env.liveness_config_path()`` supplies the deployment
    location. The framework import is GUARDED and lazy: this module must stay
    importable — and inert — on a tree where ``framework.env`` is broken or
    absent, because the whole point is that it survives what it measures."""
    override = (os.environ.get(CONFIG_ENV) or "").strip()
    if override:
        return os.path.expanduser(override)
    try:
        from framework import env as _env  # lazy + guarded on purpose

        return _env.liveness_config_path(default)
    except Exception:
        return str(default)


def _strip_comment(value: str) -> str:
    """Drop a trailing ``  # comment``. Only a HASH PRECEDED BY WHITESPACE
    counts, so a URL fragment or a slug containing '#' survives — the same
    convention the watchdog's stdlib config parser uses."""
    cut = re.split(r"\s+#", value, maxsplit=1)[0]
    return cut.strip().strip('"').strip("'")


def parse_config(text: str) -> dict:
    """Parse the liveness config with the standard library only.

    NO PyYAML — same survival reasoning as the watchdog registry's parser: a
    heartbeat that dies from a missing third-party dep is worse than none.
    Accepted shapes are exactly what ``liveness.yml.example`` documents:
    top-level ``key: value`` scalars, and 2-space ``key: value`` entries under
    an ``events:`` section. Unknown lines are ignored per-entry; an unparseable
    file degrades to an EMPTY config, which means INERT — a bad config can only
    ever silence this emitter, never make it ping the wrong watcher."""
    cfg: dict = {"enabled": True, "instance_id": "", "base_url": "",
                 "timeout_s": _DEFAULT_TIMEOUT_S, "events": {}, "_present": True}
    in_events = False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            in_events = False
            if line.strip() == "events:":
                in_events = True
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if not m:
                continue
            key, val = m.group(1), _strip_comment(m.group(2))
            if key == "enabled":
                cfg["enabled"] = val.lower() not in ("false", "no", "0", "off")
            elif key in ("instance_id", "base_url"):
                cfg[key] = val
            elif key == "timeout_s":
                try:
                    cfg["timeout_s"] = int(val)
                except ValueError:
                    pass  # keep the default; a typo must not stall a send
            continue
        if in_events:
            m = re.match(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if m:
                cfg["events"][m.group(1)] = _strip_comment(m.group(2))
    return cfg


def load_config(path: str | None = None) -> dict:
    """Read + parse the config. An absent/unreadable file yields the EMPTY
    (inert) config with ``_present=False`` — never an exception, never a partial
    ping. The flag exists so ``resolve`` can distinguish "this deployment has not
    configured a dead-man" from "configured but missing a slug"; both are inert,
    but only the second is a mistake worth noticing."""
    p = path if path is not None else config_path()
    if not p:
        cfg = parse_config("")
        cfg["_present"] = False
        return cfg
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return parse_config(fh.read())
    except Exception:
        cfg = parse_config("")
        cfg["_present"] = False
        return cfg


def _result(event: str, emitted: bool, reason: str, **extra) -> dict:
    out = {"event": event, "emitted": emitted, "reason": reason,
           "status": None, "url": None, "instance_id": None}
    out.update(extra)
    return out


def resolve(event: str, cfg: dict) -> dict:
    """Decide whether ``event`` may fire, and to where — WITHOUT any network.

    Split out from :func:`emit` so the whole inert/active decision is testable
    with zero I/O, and so a caller that wants to log the reason can get it
    without paying for a request. Returns the same result shape as ``emit``;
    ``reason == 'ready'`` means the URL is populated and safe to fetch."""
    if not cfg.get("_present", True):
        return _result(event, False, "no-config")
    if not cfg.get("enabled", True):
        return _result(event, False, "disabled")
    if event not in KNOWN_EVENTS:
        return _result(event, False, "unknown-event")

    instance = (cfg.get("instance_id") or "").strip()
    if not instance:
        # The multi-tenancy guard, and deliberately a HARD stop rather than a
        # default: an unnamed instance sharing a neighbour's slug is exactly the
        # dead-vs-quiet ambiguity this detector exists to remove.
        return _result(event, False, "no-instance")
    if not _INSTANCE_RE.match(instance):
        return _result(event, False, "bad-instance")

    base = (cfg.get("base_url") or "").strip().rstrip("/")
    if not base:
        return _result(event, False, "no-base-url", instance_id=instance)
    if not base.startswith(_ALLOWED_SCHEMES):
        # http/https only — never let a config turn a heartbeat into a file:// or
        # gopher:// fetch through urllib's opener.
        return _result(event, False, "bad-base-url", instance_id=instance)

    slug = (cfg.get("events", {}).get(event) or "").strip()
    if not slug:
        return _result(event, False, "no-slug", instance_id=instance)
    if not _SLUG_RE.match(slug):
        return _result(event, False, "bad-slug", instance_id=instance)

    return _result(event, False, "ready", instance_id=instance,
                   url=f"{base}/{slug}")


def emit(event: str, *, cfg: dict | None = None, opener=None,
         config_path_override: str | None = None) -> dict:
    """Ping the off-machine watcher for ``event``. Never raises.

    Returns ``{event, emitted, reason, status, url, instance_id}``. ``emitted`` is
    True ONLY when the watcher answered; every other outcome carries a
    machine-readable ``reason`` (``no-config``/``no-instance``/``no-slug``/
    ``bad-*``/``disabled``/``transport-error``) so a caller can log precisely
    why a heartbeat did not fire — the failure mode this whole design exists to
    kill is a signal that looks delivered and is not.

    ``opener`` is the seam the tests drive; it takes ``(url, timeout)`` and
    returns an HTTP status int."""
    try:
        conf = cfg if cfg is not None else load_config(config_path_override)
        decision = resolve(event, conf)
        if decision["reason"] != "ready":
            return decision

        timeout = conf.get("timeout_s", _DEFAULT_TIMEOUT_S)
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT_S
        timeout = max(_MIN_TIMEOUT_S, min(_MAX_TIMEOUT_S, timeout))

        fetch = opener or _default_opener
        try:
            status = fetch(decision["url"], timeout)
        except Exception as exc:  # transport, DNS, TLS, timeout — all the same
            return _result(event, False, "transport-error",
                           instance_id=decision["instance_id"], url=decision["url"],
                           error=type(exc).__name__)
        return _result(event, True, "ok", instance_id=decision["instance_id"],
                       url=decision["url"], status=status)
    except Exception as exc:  # pragma: no cover - belt: emit must NEVER raise
        return _result(event, False, "internal-error", error=type(exc).__name__)


def _default_opener(url: str, timeout: int) -> int:
    """Inline stdlib GET. Deliberately NOT the shared probe helper: the probes
    are watched services, and importing what you watch is how a detector dies
    in the same event as the fault. Instance identity rides the SLUG (enforced
    per-instance by ``resolve``), not this request — the User-Agent is a fixed
    diagnostic string and carries no identity."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "cabinet-liveness/1")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return int(getattr(resp, "status", 0) or 0)
