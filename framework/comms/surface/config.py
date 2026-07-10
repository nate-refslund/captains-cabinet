"""framework.comms.surface.config — instance bindings for the TG engine.

Resolution order for every knob: env var → ``instance/config/comms-surface.yml``
→ hardcoded safe default. Fail-closed: an absent or corrupt instance file
resolves to the defaults (ask-first, cap 5, no dashboard links) — a clean-room
deployment gets a working, quiet surface with zero configuration. No launcher
literals; the repo root comes from ``framework.env._cabinet_root`` (which
honors ``CABINET_ROOT``).

The one Captain-confirmable knob from the master prompt (§4): ``mode`` —
``ask-first`` (default, recommended) vs ``auto-push``.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Foundation defaults (master prompt §4; cap clamps mirror the charter's
# decisions_render_cap ceiling so the surface can never out-render the census).
DEFAULTS = {
    "cap": 5,                      # active action-cards at once (3–5 band)
    "mode": "ask-first",           # ask-first | auto-push
    "pileup": 3,                   # fresh decisions before the one nudge card
    "snooze_hours": 2.0,           # the nudge's "Snooze" duration
    "urgent_interrupts": 2,        # max urgent jumps per rolling window
    "urgent_window_hours": 12.0,   # the rolling window for urgent jumps
    "hard_all_cap": 25,            # ceiling for the "show everything" override
    "briefing_card": False,        # briefing-as-card send path (dark until wired)
    "dashboard_url": "",           # deep-link base; empty = no links (fail-closed)
    # Pin design (pin-recommendation doc, Captain-ratified 2026-07-10):
    #   adopt    — the pin is the #1 item's own standing card (shipped mode)
    #   overview — ONE live standing overview card ("⚑ N need you" + top
    #              names when N≤5), edited in place, stays the pin.
    # Foundation default stays "adopt" (the shipped behavior); the ratified
    # instance value lives in instance/config/comms-surface.yml.
    "pin_mode": "adopt",
}

_CAP_MIN, _CAP_MAX = 1, 7
_MODES = ("ask-first", "auto-push")
_PIN_MODES = ("adopt", "overview")


def _instance_file() -> Path:
    # The instance/ reference lives on framework.env (the sanctioned
    # layer-crossing seam), never in this module.
    from framework import env
    return env.comms_surface_path()


def _load_instance() -> dict:
    """The instance override block. {} on absent/corrupt/odd-shaped file —
    never raises, never best-effort-merges garbage."""
    p = _instance_file()
    try:
        if not p.exists():
            return {}
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — corrupt config must not crash the surface
        return {}


def _num(val, default, lo=None, hi=None):
    try:
        n = float(val)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def load(*, instance: "dict | None" = None) -> dict:
    """The resolved engine config dict. ``instance`` injectable for tests."""
    inst = _load_instance() if instance is None else (instance or {})
    pac = inst.get("pacing") if isinstance(inst.get("pacing"), dict) else {}

    def pick(env_key: str, yml_key: str):
        v = os.environ.get(env_key)
        if v is not None and str(v).strip() != "":
            return v
        return pac.get(yml_key, inst.get(yml_key))

    cap = int(_num(pick("CABINET_SURFACE_CAP", "cap"),
                   DEFAULTS["cap"], _CAP_MIN, _CAP_MAX))
    mode = str(pick("CABINET_SURFACE_MODE", "mode") or DEFAULTS["mode"]).strip().lower()
    if mode not in _MODES:
        mode = DEFAULTS["mode"]      # unknown mode narrows to ask-first, never louder
    pin_mode = str(pick("CABINET_SURFACE_PIN_MODE", "pin_mode")
                   or DEFAULTS["pin_mode"]).strip().lower()
    if pin_mode not in _PIN_MODES:
        pin_mode = DEFAULTS["pin_mode"]   # unknown pin design falls back to shipped
    return {
        "cap": cap,
        "mode": mode,
        "pin_mode": pin_mode,
        "pileup": int(_num(pick("CABINET_SURFACE_PILEUP", "pileup"),
                           DEFAULTS["pileup"], 1, 50)),
        "snooze_hours": _num(pick("CABINET_SURFACE_SNOOZE_H", "snooze_hours"),
                             DEFAULTS["snooze_hours"], 0.25, 48.0),
        "urgent_interrupts": int(_num(
            pick("CABINET_SURFACE_URGENT_N", "urgent_interrupts"),
            DEFAULTS["urgent_interrupts"], 0, 10)),
        "urgent_window_hours": _num(
            pick("CABINET_SURFACE_URGENT_WINDOW_H", "urgent_window_hours"),
            DEFAULTS["urgent_window_hours"], 1.0, 72.0),
        "hard_all_cap": int(_num(pick("CABINET_SURFACE_ALL_CAP", "hard_all_cap"),
                                 DEFAULTS["hard_all_cap"], 1, 100)),
        "briefing_card": str(pick("CABINET_BRIEFING_CARD", "briefing_card")
                             or DEFAULTS["briefing_card"]).strip().lower()
        in ("1", "true", "yes", "on"),
        "dashboard_url": str(pick("CABINET_DASHBOARD_URL", "dashboard_url")
                             or DEFAULTS["dashboard_url"]).strip(),
    }


# ---------------------------------------------------------------------------
# Clocks — the same env contract the gate uses (CABINET_CAPTAIN_TZ,
# CABINET_BRIEFING_TIMES), so the engine's horizon math and the gate's
# quiet-hours math read the same captain clock.
# ---------------------------------------------------------------------------

def captain_tz() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("CABINET_CAPTAIN_TZ", "UTC"))
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def next_briefing(now: datetime) -> datetime:
    """The next scheduled briefing instant after ``now`` (Captain tz),
    from ``CABINET_BRIEFING_TIMES`` (default 07:30,19:30) — the engine's
    wrong-by-tomorrow horizon, matching the gate's own timing check."""
    now_local = now.astimezone(captain_tz())
    times = [t.strip() for t in os.environ.get(
        "CABINET_BRIEFING_TIMES", "07:30,19:30").split(",") if t.strip()]
    cands = []
    for t in times:
        try:
            h, m = t.split(":")
            b = now_local.replace(hour=int(h), minute=int(m),
                                  second=0, microsecond=0)
        except (ValueError, IndexError):
            continue
        if b <= now_local:
            b = b + timedelta(days=1)
        cands.append(b)
    return min(cands) if cands else now_local + timedelta(days=1)


def attention_dir() -> Path:
    """The engine's durable-state home — the same directory the gate's
    standing-card map lives in (CABINET_ATTENTION_DIR)."""
    return Path(os.environ.get("CABINET_ATTENTION_DIR") or
                os.path.expanduser("~/Library/Application Support/cabinet/attention"))
