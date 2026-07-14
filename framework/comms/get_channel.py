"""framework.comms.get_channel — bind the ChannelAdapter for this deployment.

Reads ``instance/config/sources.yml → channel:`` (the same instance seam the
brain bridge uses via ``framework.sources``). Resolution order:
``CABINET_CHANNEL`` env override → ``sources.yml`` channel → default
``telegram``. Binding rules:

  * an explicit ``null``/``none`` OR an UNKNOWN channel name binds the
    NullAdapter (fail-closed — never another launcher's channel);
  * a broken adapter import also degrades to null (never a crash);
  * ABSENT / unreadable config falls back to this deployment's default,
    ``telegram`` — NOT null. A clean-room / Flavor-B box makes itself no-op by
    setting ``channel: null`` (or ``CABINET_CHANNEL=null``); if it does not, the
    telegram adapter still cannot send, because ``channel.py`` is hard-gated by
    ``env.allow_sends()`` and requires the bot token + Captain id in the env
    (absent on a clean-room box ⇒ "telegram not configured", no send).

Bound once per process.

FOUNDATION-FIRST: this resolver is the ONLY place the instance's channel
CHOICE is read; the adapters name their channel, the resolver binds them by
config, and framework code above the seam names neither.
"""
from __future__ import annotations

import os
import sys

_CACHE = None


def _configured_channel() -> str:
    env_override = (os.environ.get("CABINET_CHANNEL") or "").strip()
    if env_override:
        return env_override.lower()
    try:
        import yaml
        from framework import env
        p = env._cabinet_root() / "instance/config/sources.yml"
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict) and "channel" in data:
                val = data["channel"]
                # YAML `channel: null` (or a bare `channel:`) parses to None —
                # that is the documented off-switch, NOT an absent key. It
                # must bind the NullAdapter, never fall through to telegram.
                if val is None:
                    return "null"
                if isinstance(val, str) and val.strip():
                    return val.strip().lower()
    except Exception:
        pass
    return "telegram"   # this deployment's default; clean-room sets channel: null


def get_channel(*, force: bool = False):
    """The bound ChannelAdapter (cached). ``force`` re-resolves (tests)."""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    name = _configured_channel()
    try:
        if name == "telegram":
            from framework.comms.adapters.telegram import TelegramAdapter
            _CACHE = TelegramAdapter()
        elif name in ("null", "none", ""):
            from framework.comms.adapters.null import NullAdapter
            _CACHE = NullAdapter()
        else:
            print(f"[comms] unknown channel '{name}' in sources.yml — binding "
                  f"null adapter (fail-closed)", file=sys.stderr)
            from framework.comms.adapters.null import NullAdapter
            _CACHE = NullAdapter()
    except Exception as e:  # a broken adapter import must not crash the caller
        print(f"[comms] channel '{name}' failed to bind ({e}) — null adapter",
              file=sys.stderr)
        from framework.comms.adapters.null import NullAdapter
        _CACHE = NullAdapter()
    return _CACHE
