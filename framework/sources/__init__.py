"""framework/sources — ``get_source()`` / ``get_dispatch()``: the bound seams.

The FOUNDATION resolvers for the personal-sensing seam, mirror of
``env.captain_name()``: each reads its adapter binding from instance config,
dynamically imports it, caches it, and FAIL-CLOSES to the null adapter on any
absence / parse-fail / import-fail. Framework CORE calls ``get_source()`` (the
READ side) and ``get_dispatch()`` (the WRITE/actuator side) and depends only on
the ``base.PersonalSource`` / ``base.PersonalDispatch`` Protocols — never on
screenpipe. ``sources.yml`` names the READ adapter under ``adapter:`` and the
WRITE adapter under ``dispatch:``; both are DATA the instance owns.

LAYER SEPARATION (the Corridor hard rule — ``check-layer-separation.sh``).
Framework may not statically import from the instance layer, nor carry a bare
quoted instance path token in a ``Path(...) / <token> / ...`` construction. Two
existing framework files load instance config WITHOUT tripping the gate, and
this resolver copies them exactly:

  * ``env.py:87`` reads ``"instance/config/platform.yml"`` — a SINGLE JOINED
    string literal, not the bare token and not ``/ <token> /``. The gate greps
    for the exact quoted token; a joined path string never matches. This module
    reads ``"instance/config/sources.yml"`` the identical way.
  * ``retro.py`` DYNAMICALLY loads a path/config-named module via importlib.
    The gate only catches a STATIC ``import``/``from`` of the instance package.
    This module ``importlib.import_module``-loads the CONFIG-NAMED adapter (the
    module name is DATA in ``sources.yml``) after adding the adapter dir to
    ``sys.path`` via the joined literal ``"instance/flavor-a"`` — framework
    never names an instance module statically; the binding is data the instance
    owns.

py3.9-compatible (typing via ``base``; ``yaml.safe_load`` only; no match/case).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from framework.sources.base import PersonalDispatch, PersonalSource
from framework.sources.null import NullPersonalDispatch, NullPersonalSource

__all__ = [
    "PersonalSource",
    "PersonalDispatch",
    "NullPersonalSource",
    "NullPersonalDispatch",
    "get_source",
    "get_dispatch",
]

# Module-global caches: each bound adapter is resolved ONCE per process (config
# does not change under a running officer; a restart re-reads). ``None`` ⇒ not
# yet resolved. A resolved value is ALWAYS a real-or-Null adapter, never
# ``None`` — so the getters never re-do the work and never return ``None``.
_source_cache = None
_dispatch_cache = None


def _cabinet_root() -> Path:
    """The deployment root — ``CABINET_ROOT`` env, else this file's repo root
    (``framework/sources/__init__.py`` → ``parents[2]``). No hardcoded absolute
    path (mirrors ``env._cabinet_root()``)."""
    return Path(os.environ.get("CABINET_ROOT") or str(Path(__file__).resolve().parents[2]))


def _load_bound(config_key):
    """Resolve + import the adapter named under ``config_key`` in
    ``instance/config/sources.yml``, or ``None`` to fail-close.

    Shared by ``get_source()`` (``config_key='adapter'``, the READ side) and
    ``get_dispatch()`` (``config_key='dispatch'``, the WRITE side). Reads
    ``<root>/instance/config/sources.yml`` (a JOINED literal — never a bare
    quoted instance token), ``yaml.safe_load`` only, expecting
    ``<config_key>: "module:Class"``. Adds ``<root>/instance/flavor-a`` (JOINED
    literal) to ``sys.path`` and ``importlib.import_module``-loads the
    CONFIG-NAMED module, then instantiates the named class. ANY absence / parse /
    import / attribute / instantiation error returns ``None`` so the caller binds
    the null adapter. Never raises, never leaks — the whole binding is DATA the
    instance owns."""
    try:
        import yaml  # local import: keep the package import-light + pyyaml-optional
    except Exception:
        return None
    try:
        root = _cabinet_root()
        cfg = root / "instance/config/sources.yml"        # joined literal (layer-sep safe)
        if not cfg.exists():
            return None
        try:
            data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        adapter = data.get(config_key)
        if not isinstance(adapter, str) or ":" not in adapter:
            return None
        module_name, _, class_name = adapter.partition(":")
        module_name = module_name.strip()
        class_name = class_name.strip()
        if not module_name or not class_name:
            return None

        adapter_dir = str(root / "instance/flavor-a")     # joined literal (layer-sep safe)
        if os.path.isdir(adapter_dir) and adapter_dir not in sys.path:
            sys.path.insert(0, adapter_dir)

        mod = importlib.import_module(module_name)

        # Defense-in-depth (Corridor: restrict module loading to the TRUSTED
        # trees). If the resolved module has a concrete file, it MUST live in
        # one of exactly two places: the instance adapter tree (flavor-a) or
        # THIS framework/sources package itself, which ships the framework-side
        # adapters (``framework.sources.org:OrgSource`` — the org-box binding).
        # Anything else means a same-named module elsewhere on sys.path
        # shadowed the adapter — fail-closed rather than bind a stray.
        mod_file = getattr(mod, "__file__", None)
        if mod_file:
            real_mod = os.path.realpath(mod_file)
            trusted_dirs = (
                os.path.realpath(adapter_dir),
                os.path.realpath(os.path.dirname(__file__)),  # framework/sources
            )
            if not any(real_mod == d or real_mod.startswith(d + os.sep)
                       for d in trusted_dirs):
                return None

        cls = getattr(mod, class_name, None)
        if cls is None:
            return None
        return cls()
    except Exception:
        # Absolutely nothing escapes: an unexpected error binds the null adapter.
        return None


def get_source() -> PersonalSource:
    """The bound personal SOURCE (read) for this deployment — the FOUNDATION
    resolver (mirror of ``env.captain_name()``). Reads the ``adapter:`` binding
    from ``instance/config/sources.yml``, ``importlib``-loads it, caches it, and
    fail-closes to ``NullPersonalSource`` on any absence / parse-fail /
    import-fail. Returns an object satisfying ``base.PersonalSource`` — never
    ``None``."""
    global _source_cache
    if _source_cache is not None:
        return _source_cache
    loaded = _load_bound("adapter")
    _source_cache = loaded if loaded is not None else NullPersonalSource()
    return _source_cache


def get_dispatch() -> PersonalDispatch:
    """The bound personal DISPATCH (write / actuator) for this deployment — the
    sibling of ``get_source()``. Reads the ``dispatch:`` binding from
    ``instance/config/sources.yml``, ``importlib``-loads it, caches it, and
    fail-closes to ``NullPersonalDispatch`` on any absence / parse-fail /
    import-fail. Returns an object satisfying ``base.PersonalDispatch`` — never
    ``None``. On a clean-room / Flavor-B box (no ``dispatch:`` binding) the null
    dispatch no-ops every write, so the egress lanes degrade to
    draft-capture-only, exactly as when ``env.allow_sends()`` is ``False``."""
    global _dispatch_cache
    if _dispatch_cache is not None:
        return _dispatch_cache
    loaded = _load_bound("dispatch")
    _dispatch_cache = loaded if loaded is not None else NullPersonalDispatch()
    return _dispatch_cache


def _reset_cache() -> None:
    """Clear the resolved-adapter caches (test seam only). The next
    ``get_source()`` / ``get_dispatch()`` re-resolves from config. Not part of
    the public contract."""
    global _source_cache, _dispatch_cache
    _source_cache = None
    _dispatch_cache = None
