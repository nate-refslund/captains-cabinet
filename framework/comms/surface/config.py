"""framework.comms.surface.config — instance bindings for the TG engine.

Resolution order for every knob: env var → ``instance/config/comms-surface.yml``
→ hardcoded safe default. Fail-closed: an absent or corrupt instance file
resolves to the defaults — ask-first, cap 5, no dashboard links, and the
Captain-ratified briefing card + overview pin — so a clean-room deployment
gets the ratified surface with zero configuration. No launcher literals; the
repo root is ``framework.env._cabinet_root`` (which honors ``CABINET_ROOT``).

The one Captain-confirmable knob from the master prompt (§4): ``mode`` —
``ask-first`` (default, recommended) vs ``auto-push``.

AVAILABILITY-AWARE PACING (Captain ruling 2026-07-26). When the deployment has
set NO cap of its own, the active-card cap scales from the Captain's declared
time budget (``framework.env.captain_availability()``): away/minimal floors it,
part-time and substantial narrow it, and an UNKNOWN budget changes nothing at
all. An explicitly configured cap always wins — a configured value is a ruling,
and the budget must never silently override one. ``availability_pacing: false``
turns the derivation off entirely.
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
    # Briefing-as-card: the 07:30/19:30 briefing arrives as ONE card (status +
    # "N decisions ready" + a Triage control) instead of the chunked text wall.
    # WIRED, not dark: frontdoor.run_briefing._briefing_card_mode() reads this
    # and swaps the send path, and briefing_card.maybe_send() gates on it.
    # Captain-ratified TRUE 2026-07-11 (one-voice reset). That ratification
    # used to live only in instance/config/comms-surface.yml — which the egg
    # deletes — so every fresh cabinet silently got the pre-ruling text wall.
    "briefing_card": True,
    "dashboard_url": "",           # deep-link base; empty = no links (fail-closed)
    # Pin design (pin-recommendation doc, Captain-ratified 2026-07-10):
    #   adopt    — the pin is the #1 item's own standing card (the original
    #              shipped mode; still selectable, still covered by tests)
    #   overview — ONE live standing overview card ("⚑ N need you" + top
    #              names when N≤5), edited in place, stays the pin.
    # Captain ratified "overview" on 2026-07-10. Same story as briefing_card:
    # the ratified value lived only in the instance file the egg deletes, so
    # the DEFAULT is now the ratified design rather than this deployment's
    # private override. An unknown value narrows here, to the ratified design.
    "pin_mode": "overview",
    # Availability-aware pacing (Captain ruling 2026-07-26): when the deployment
    # has NOT set its own cap, scale it from the Captain's declared time budget
    # (framework.env.captain_availability()). The org fits the declared budget,
    # never the reverse — 146 cards chasing 2 approvals is what the un-scaled
    # cap looked like. Set false to pin the cap regardless of availability.
    # UNKNOWN availability changes NOTHING: the shipped cap stands, because a
    # consumer must never invent a number for an answer nobody gave.
    "availability_pacing": True,
}

_CAP_MIN, _CAP_MAX = 1, 7
_MODES = ("ask-first", "auto-push")
_PIN_MODES = ("adopt", "overview")

#: minutes/day → active-card cap, smallest band first. The bands mirror
#: ``framework.env.AVAILABILITY_MODES`` (away/minimal/part_time/substantial);
#: anything above the last band keeps the shipped ``DEFAULTS["cap"]``. ONE knob
#: on purpose — the frontdoor's expiry/TTL constants are deliberately untouched.
_AVAILABILITY_CAP_BANDS = ((10, 1), (30, 2), (120, 3), (240, 4))


def _availability_cap(default_cap: int) -> int:
    """The cap the declared availability implies, or ``default_cap`` when
    availability is UNKNOWN (or unreadable). Fail-safe: any error keeps the
    shipped default, so a broken store can never widen or narrow the surface."""
    try:
        from framework import env
        minutes = env.captain_availability().get("minutes_per_day")
    except Exception:  # noqa: BLE001 — pacing must not depend on a config read
        return default_cap
    if minutes is None:
        return default_cap             # unknown ⇒ unchanged, never invented
    for band, cap in _AVAILABILITY_CAP_BANDS:
        if minutes <= band:
            return cap
    return default_cap


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

    # An EXPLICIT cap (env or instance file) always wins. Only when the
    # deployment has said nothing does the declared availability decide — a
    # configured cap is a ruling, and a budget must never silently override one.
    raw_cap = pick("CABINET_SURFACE_CAP", "cap")
    avail_pacing = pick("CABINET_SURFACE_AVAILABILITY_PACING", "availability_pacing")
    avail_pacing = (DEFAULTS["availability_pacing"] if avail_pacing is None
                    else str(avail_pacing).strip().lower() in ("1", "true", "yes", "on"))
    cap_default = (_availability_cap(DEFAULTS["cap"]) if avail_pacing
                   else DEFAULTS["cap"])
    cap = int(_num(raw_cap, cap_default, _CAP_MIN, _CAP_MAX))
    mode = str(pick("CABINET_SURFACE_MODE", "mode") or DEFAULTS["mode"]).strip().lower()
    if mode not in _MODES:
        mode = DEFAULTS["mode"]      # unknown mode narrows to ask-first, never louder
    pin_mode = str(pick("CABINET_SURFACE_PIN_MODE", "pin_mode")
                   or DEFAULTS["pin_mode"]).strip().lower()
    if pin_mode not in _PIN_MODES:
        pin_mode = DEFAULTS["pin_mode"]   # unknown pin design falls back to ratified
    # An explicitly configured value must win even when it is FALSY. `or`
    # coalescing was harmless while the default was False; against the
    # ratified True it would swallow `briefing_card: false` — the documented
    # opt-out, and the literal value the shipped .example twin carries — and
    # silently re-arm the card a deployment just turned off. Absent (None) is
    # the only thing that may fall through to the default.
    bcard = pick("CABINET_BRIEFING_CARD", "briefing_card")
    bcard = DEFAULTS["briefing_card"] if bcard is None else bcard
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
        "briefing_card": str(bcard).strip().lower() in ("1", "true", "yes", "on"),
        "dashboard_url": str(pick("CABINET_DASHBOARD_URL", "dashboard_url")
                             or DEFAULTS["dashboard_url"]).strip(),
        "availability_pacing": avail_pacing,
    }


# ---------------------------------------------------------------------------
# Clocks — the same contract the gate uses (env CABINET_CAPTAIN_TZ /
# CABINET_BRIEFING_TIMES win, else the framework.env resolvers over instance
# platform.yml `captain_timezone` / `briefing_times`), so the engine's horizon
# math and the gate's quiet-hours math read the same captain clock (TZ + SoT
# unification 2026-07-18).
# ---------------------------------------------------------------------------

def captain_tz() -> ZoneInfo:
    # A LOADABLE env CABINET_CAPTAIN_TZ wins; an UNLOADABLE env value (e.g. a
    # wrapper's one-line read leaked YAML quotes) falls THROUGH to THE resolver
    # (platform.yml → LOUD UTC fallback) instead of silently assuming UTC — same
    # contract as gate._captain_tz.
    name = (os.environ.get("CABINET_CAPTAIN_TZ") or "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            pass
    from framework import env
    try:
        return ZoneInfo(env.captain_timezone())   # platform.yml → LOUD UTC fallback
    except Exception:  # noqa: BLE001 — tzdata fail-safe; the resolver warned
        return ZoneInfo("UTC")


def next_briefing(now: datetime) -> datetime:
    """The next scheduled briefing instant after ``now`` (Captain tz), from
    ``CABINET_BRIEFING_TIMES`` (default: the platform.yml ``briefing_times``
    resolver, fleet default 07:30,19:30) — the engine's wrong-by-tomorrow
    horizon, matching the gate's own timing check."""
    from framework import env
    now_local = now.astimezone(captain_tz())
    raw = (os.environ.get("CABINET_BRIEFING_TIMES") or "").strip()
    times = []
    if raw:
        # Normalize env tokens through the shared validator — drops an
        # out-of-range slot like "25:99" (silently ignored here, and a crash on
        # the gate's parallel path) instead of trusting the raw string.
        times = [s for s in (env._normalize_briefing_slot(t) for t in raw.split(",")) if s]
    if not times:
        # env unset, or set but no valid slot → the platform.yml `briefing_times`
        # source of truth (fleet default 07:30,19:30), never a nonsense horizon.
        times = list(env.briefing_times())
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
