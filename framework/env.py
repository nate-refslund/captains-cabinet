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
