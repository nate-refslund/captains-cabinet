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
    ``_captain_tz`` reader baked in an absolute home path — a launcher leak this
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


# Cache: captain_role is read once per process (same lifecycle as captain_name;
# config is stable under a running officer, a restart re-reads). None ⇒ unresolved.
_captain_role_cache: "str | None" = None


def captain_role(default: str = "the Captain") -> str:
    """The Captain's role/title for this deployment — the sibling of
    ``captain_name()`` that lets framework code name the launcher's ROLE (e.g.
    in a decision-cell LLM prompt) WITHOUT hardcoding it (this deployment's is
    "Head-of-Tech").

    Reads ``captain_role`` from ``instance/config/platform.yml`` (portfolio /
    live deployments), else ``instance/config/product.yml`` (single-product
    ``work`` deployments), exactly like ``captain_name()``. Any absence / parse
    failure falls back to ``default`` ("the Captain") — a generic deployment
    stays generic, never crashes, and never leaks another launcher's role.
    Framework code that names the Captain's role in a runtime string calls this
    instead of a string literal."""
    global _captain_role_cache
    if _captain_role_cache is not None:
        return _captain_role_cache
    role = default
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
            val = data.get("captain_role")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("captain_role")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                role = val.strip()
                break
    except Exception:
        role = default
    _captain_role_cache = role
    return role


# Cache: org_domains is read once per process (same lifecycle as captain_name;
# config is stable under a running officer, a restart re-reads). None ⇒
# unresolved — the EMPTY tuple is a VALID resolved value (a generic deployment
# with no org), so the sentinel is None, never ().
_org_domains_cache: "tuple[str, ...] | None" = None


def org_domains(default: "tuple[str, ...]" = ()) -> "tuple[str, ...]":
    """The org's internal email domains for this deployment — the resolver that
    lifts the action-classifier's internal-vs-external recipient list OUT of the
    universal-base ``framework`` code into instance config, so framework carries
    no launcher's domains.

    Reads the ``org_domains`` list from ``instance/config/platform.yml``
    (portfolio / live deployments), else ``instance/config/product.yml``
    (single-product ``work`` deployments; also accepts a nested
    ``product.org_domains``). Each entry is stripped + lowercased (the
    is_internal predicate compares against an already-lowercased recipient
    domain) and order is preserved. Any absence / parse failure / empty list
    falls back to ``default`` — the EMPTY tuple — so a generic deployment treats
    EVERY recipient as external (the conservative comms ceiling / always-gated),
    never crashes, and never leaks another launcher's org. The classifier's
    is_internal predicate is unchanged; only the domain SOURCE moved here."""
    global _org_domains_cache
    if _org_domains_cache is not None:
        return _org_domains_cache
    domains = tuple(default)
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
            val = data.get("org_domains")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("org_domains")   # product.yml nests it
            if isinstance(val, (list, tuple)):
                cleaned = tuple(
                    d.strip().lower() for d in val
                    if isinstance(d, str) and d.strip())
                if cleaned:
                    domains = cleaned
                    break
    except Exception:
        domains = tuple(default)
    _org_domains_cache = domains
    return domains


# Cache: tasks_board is read once per process (same lifecycle as captain_name).
# None ⇒ unresolved — the empty string is a VALID resolved value (a generic
# deployment with no board configured), so the sentinel is None, never "".
_tasks_board_cache: "str | None" = None


def tasks_board(default: str = "") -> str:
    """The Monday 'Tasks' board id lane-created work lands on for this
    deployment — the resolver that lifts the board id OUT of the universal-base
    ``framework`` code (``action_exec.DEFAULT_TASKS_BOARD``, the act-first
    canary's synthetic probe board) into instance config.

    Resolution order: the env override ``CABINET_TASKS_BOARD`` (an explicit
    per-process override, mirroring ``action_exec``'s existing
    ``ACTION_LANE_DEFAULT_BOARD``) → ``tasks_board`` in
    ``instance/config/platform.yml`` (else ``product.yml`` / nested
    ``product.tasks_board``) → the generic ``default`` (``""``). A generic
    deployment with NO board configured resolves ``""`` — the executor's
    ``board.isdigit()`` guard then refuses the create with a clear error rather
    than silently landing on another launcher's board (fail-closed, never
    leak)."""
    global _tasks_board_cache
    if _tasks_board_cache is not None:
        return _tasks_board_cache
    env_override = (os.environ.get("CABINET_TASKS_BOARD") or "").strip()
    if env_override:
        _tasks_board_cache = env_override
        return env_override
    board = str(default)
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
            val = data.get("tasks_board")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("tasks_board")   # product.yml nests it
            if val is not None and str(val).strip():
                board = str(val).strip()
                break
    except Exception:
        board = str(default)
    _tasks_board_cache = board
    return board


# Cache: captain_timezone is read once per process (same lifecycle as
# captain_name; config is stable under a running officer, a restart re-reads).
# None ⇒ unresolved.
_captain_timezone_cache: "str | None" = None


def captain_timezone(default: str = "Europe/Berlin") -> str:
    """The Captain's IANA timezone NAME for this deployment — the resolver that
    lifts the 'today'-boundary timezone OUT of the universal-base ``framework``
    acting code (``screenpipe_adapter._captain_tz``) into instance config, so
    framework carries no hand-read of ``instance/config/platform.yml``.

    Reads ``captain_timezone`` from ``instance/config/platform.yml`` (portfolio /
    live deployments), else ``instance/config/product.yml`` (single-product
    ``work`` deployments; also accepts a nested ``product.captain_timezone``),
    exactly like ``captain_role()``. Any absence / parse failure / empty value
    falls back to ``default`` — the generic Central-European ``Europe/Berlin``
    (CET/CEST, DST-aware), the SAME fallback the removed hand-reader carried, so
    the greeting-of-the-day boundary stays byte-identical. Returns a bare IANA
    name string, never a tzinfo: the caller owns the name→zoneinfo lookup and
    its own UTC fail-safe if the name is unloadable."""
    global _captain_timezone_cache
    if _captain_timezone_cache is not None:
        return _captain_timezone_cache
    tz = default
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
            val = data.get("captain_timezone")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("captain_timezone")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                tz = val.strip()
                break
    except Exception:
        tz = default
    _captain_timezone_cache = tz
    return tz
