"""CABINET_ENV — the dev | runtime safety switch (fail-safe by default).

The default is **dev**, so any unconfigured session — a developer, a test, this
build session — is SANDBOXED:
  * ``allow_sends()`` is False, so the live dispatch adapter NEVER sends (no
    queue_draft) even on an 'approve'. Acting for real is opt-in, not opt-out.
  * ``ledger_dir()`` points at a separate ``-dev`` directory, so a dev run can
    never pollute the production proof ledger that drives the ladder.

The runtime (``start-officer``) must set ``CABINET_ENV=runtime`` explicitly to
enable production-ledger writes + gated sends. This module is the single switch
the live code + launch scripts consult; ``consequence.py`` is untouched (it
already honours ``CABINET_EVENT_LOG_DIR``, which the runtime launch sets from
``ledger_dir()``).
"""
from __future__ import annotations

import os
from pathlib import Path

_DEV = "dev"
_RUNTIME = "runtime"


def cabinet_env() -> str:
    """The active environment: 'runtime' only when explicitly set; else 'dev'."""
    val = (os.environ.get("CABINET_ENV") or "").strip().lower()
    return _RUNTIME if val == _RUNTIME else _DEV


def is_runtime() -> bool:
    return cabinet_env() == _RUNTIME


def allow_sends() -> bool:
    """True ONLY in the runtime. The live dispatch adapter must gate every
    outbound (queue_draft) on this — so dev/test/build sessions cannot send,
    regardless of how an 'approve' was routed."""
    return is_runtime()


def ledger_dir() -> Path:
    """The consequence-ledger directory for this environment.

    An explicit ``CABINET_EVENT_LOG_DIR`` always wins (the runtime launch sets it).
    Otherwise: the durable per-user ledger for runtime, and a distinct ``-dev``
    sibling for dev — so dev proof can never mix into the production ledger.
    """
    explicit = os.environ.get("CABINET_EVENT_LOG_DIR")
    if explicit:
        return Path(explicit).expanduser()
    base = Path.home() / ".cabinet" / "ledger"
    return base if is_runtime() else base.with_name("ledger-dev")


def _cabinet_root() -> Path:
    """The deployment root — ``CABINET_ROOT`` env, else this file's repo root
    (``framework/env.py`` → parents[1]). No hardcoded absolute path (the old
    ``_captain_tz`` reader baked in ``/Users/nate/...`` — a launcher leak this
    resolver deliberately avoids)."""
    return Path(os.environ.get("CABINET_ROOT") or str(Path(__file__).resolve().parents[1]))


# Cache: captain_name is read once per process (config does not change under a
# running officer; a restart re-reads). None ⇒ not yet resolved.
_captain_name_cache: "str | None" = None


def captain_name(default: str = "Captain") -> str:
    """The Captain's display name for this deployment — the FOUNDATION resolver
    that lets framework code address the launcher WITHOUT hardcoding a name.

    Reads ``captain_name`` from ``instance/config/platform.yml`` (portfolio /
    live deployments), else ``instance/config/product.yml`` (single-product
    ``work`` deployments), per CLAUDE.md → "Addressing the Captain". Any
    absence / parse failure falls back to ``default`` ("Captain") — a generic
    deployment stays generic, never crashes, and never leaks another
    launcher's name. Framework code that greets/represents the Captain calls
    this instead of a string literal."""
    global _captain_name_cache
    if _captain_name_cache is not None:
        return _captain_name_cache
    name = default
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("captain_name")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("captain_name")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                name = val.strip()
                break
    except Exception:
        name = default
    _captain_name_cache = name
    return name
