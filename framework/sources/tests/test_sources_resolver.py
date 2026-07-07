"""Resolver tests for ``framework.sources.get_source()`` — SRC-0.

Proves the FOUNDATION resolver's contract:
  * absent sources.yml            ⇒ NullPersonalSource (fail-closed)
  * malformed / adapterless yaml  ⇒ NullPersonalSource (fail-closed)
  * a valid stub adapter binding  ⇒ the stub is imported + instantiated
  * get_source() caches           ⇒ one resolution per process
  * NullPersonalSource satisfies base.PersonalSource (runtime_checkable)
  * LAYER SEP: framework/sources/*.py carries no bare quoted instance token nor
    any screenpipe import (the seam names the Protocol; the adapter — living in
    the instance/flavor-a tree — names screenpipe).

The layer-sep needle is assembled at runtime from ``chr()`` + a split word so
THIS test file does not itself carry the quoted token that
``check-layer-separation.sh`` greps for.
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

from framework import sources as src_pkg
from framework.sources.base import PersonalDispatch, PersonalSource
from framework.sources.null import NullPersonalDispatch, NullPersonalSource

_SRC_DIR = Path(src_pkg.__file__).resolve().parent


@pytest.fixture(autouse=True)
def _isolate():
    """Each case starts from a clean resolver cache, sys.path, sys.modules and
    CABINET_ROOT — and restores them after — so the bound-source global never
    leaks across tests (or into the rest of the framework suite)."""
    src_pkg._reset_cache()
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    saved_root = os.environ.get("CABINET_ROOT")
    try:
        yield
    finally:
        src_pkg._reset_cache()
        sys.path[:] = saved_path
        for name in set(sys.modules) - saved_modules:
            sys.modules.pop(name, None)
        if saved_root is None:
            os.environ.pop("CABINET_ROOT", None)
        else:
            os.environ["CABINET_ROOT"] = saved_root


def _mk_instance(root: Path):
    """Create ``<root>/instance/config`` and ``<root>/instance/flavor-a`` (joined
    literals, so this helper trips no layer-sep token) and return both."""
    cfg_dir = root / "instance/config"
    adapter_dir = root / "instance/flavor-a"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    adapter_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir, adapter_dir


def _write_stub(adapter_dir: Path, module: str) -> None:
    """Write a Protocol-complete stub adapter module into the flavor-a dir."""
    (adapter_dir / (module + ".py")).write_text(textwrap.dedent('''
        class StubSource:
            IS_STUB = True
            def available(self): return True
            def search(self, handle, *, topic=None):
                return {"hits": ["STUB"], "topic_terms": None}
            def find_reply_candidates(self, *, since=None): return []
            def person_intel(self, slug): return ""
            def open_commitments(self, direction): return []
            def voice_profile(self): return ""
            def model_patterns(self): return ""
            def drafting_lessons(self, before_ts): return ""
            def read_note(self, path): return "STUB-NOTE"
            def find_threads(self, hours=48): return []
            def gather(self, thread, *, do_prep=True): return {}
            def draft_fn(self, thread, ctx, *, min_confidence=0.0): return ""
            def captain_replied_since(self, slug, when): return None
            def still_awaiting(self, slug, hours=72): return None
            def deploy_health(self, app, limit=8): return {}
            def briefing_commitments(self, direction="owed_by_captain"): return []
    '''), encoding="utf-8")


def test_absent_sources_yml_fails_closed_to_null(tmp_path):
    _mk_instance(tmp_path)  # the config dir exists, but NO sources.yml in it
    os.environ["CABINET_ROOT"] = str(tmp_path)
    assert isinstance(src_pkg.get_source(), NullPersonalSource)


def test_no_config_tree_at_all_fails_closed_to_null(tmp_path):
    os.environ["CABINET_ROOT"] = str(tmp_path)  # empty root — nothing there at all
    assert isinstance(src_pkg.get_source(), NullPersonalSource)


@pytest.mark.parametrize("body", [
    "adapter: [",                      # invalid yaml (parser error)
    "just a scalar string",            # valid yaml, but not a mapping
    "other_key: 1",                    # mapping, no adapter key
    "adapter: 12345",                  # adapter not a string
    "adapter: no_colon_here",          # missing module:Class separator
    "adapter: ':OnlyClass'",           # empty module
    "adapter: 'only_module:'",         # empty class
    "adapter: nonexistent_module_xyz:Klass",  # module not importable
])
def test_malformed_or_unresolvable_fails_closed_to_null(tmp_path, body):
    cfg_dir, _ = _mk_instance(tmp_path)
    (cfg_dir / "sources.yml").write_text(body + "\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    assert isinstance(src_pkg.get_source(), NullPersonalSource)


def test_stub_adapter_binding_is_loaded(tmp_path):
    cfg_dir, adapter_dir = _mk_instance(tmp_path)
    _write_stub(adapter_dir, "srcstub_bind")
    (cfg_dir / "sources.yml").write_text(
        "adapter: srcstub_bind:StubSource\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    src = src_pkg.get_source()
    assert getattr(src, "IS_STUB", False) is True
    assert type(src).__name__ == "StubSource"
    assert src.search("x")["hits"] == ["STUB"]
    # a real adapter structurally satisfies the read Protocol, same as Null does
    assert isinstance(src, PersonalSource)


# --- get_dispatch() (the WRITE/actuator sibling resolver, SRC-3) ------------
def _write_dispatch_stub(adapter_dir: Path, module: str) -> None:
    """A Protocol-complete stub PersonalDispatch module in the flavor-a dir."""
    (adapter_dir / (module + ".py")).write_text(textwrap.dedent('''
        class StubDispatch:
            IS_STUB = True
            def queue_draft(self, *a, **k): return None
            def deliver(self, *a, **k): return {"ok": True, "stub": True}
            def append_note(self, *a, **k): return None
            def log_reasoning(self, **k): return None
            def ensure_signature(self, text, channel): return text
            def write_daily_note(self, date, content): return {"action": "stub"}
            def daily_note_path(self, date): return "1-Daily/" + str(date) + ".md"
    '''), encoding="utf-8")


def test_absent_dispatch_key_fails_closed_to_null(tmp_path):
    """A sources.yml that binds a READ adapter but NO ``dispatch:`` key still
    fail-closes the WRITE side to NullPersonalDispatch (independent resolvers)."""
    cfg_dir, _ = _mk_instance(tmp_path)
    (cfg_dir / "sources.yml").write_text("adapter: x:Y\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    assert isinstance(src_pkg.get_dispatch(), NullPersonalDispatch)


def test_dispatch_stub_binding_is_loaded(tmp_path):
    cfg_dir, adapter_dir = _mk_instance(tmp_path)
    _write_dispatch_stub(adapter_dir, "dispstub_bind")
    (cfg_dir / "sources.yml").write_text(
        "dispatch: dispstub_bind:StubDispatch\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    d = src_pkg.get_dispatch()
    assert getattr(d, "IS_STUB", False) is True
    assert type(d).__name__ == "StubDispatch"
    assert d.deliver("x") == {"ok": True, "stub": True}
    assert isinstance(d, PersonalDispatch)


def test_get_dispatch_caches_one_resolution(tmp_path):
    cfg_dir, adapter_dir = _mk_instance(tmp_path)
    _write_dispatch_stub(adapter_dir, "dispstub_cache")
    cfg = cfg_dir / "sources.yml"
    cfg.write_text("dispatch: dispstub_cache:StubDispatch\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    first = src_pkg.get_dispatch()
    assert src_pkg.get_dispatch() is first     # cached identity
    cfg.unlink()
    assert src_pkg.get_dispatch() is first     # still cached (no re-resolve)


def test_source_and_dispatch_caches_are_independent(tmp_path):
    """Binding one side must not resolve the other: an adapter-only sources.yml
    gives a real source but a Null dispatch, and vice versa."""
    cfg_dir, adapter_dir = _mk_instance(tmp_path)
    _write_stub(adapter_dir, "src_only")
    (cfg_dir / "sources.yml").write_text("adapter: src_only:StubSource\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    assert type(src_pkg.get_source()).__name__ == "StubSource"
    assert isinstance(src_pkg.get_dispatch(), NullPersonalDispatch)


def test_stray_same_named_module_is_refused(tmp_path, monkeypatch):
    """Corridor hardening: a module of the configured name that resolves OUTSIDE
    the instance/flavor-a tree (e.g. shadowed on sys.path) is refused — the
    resolver fails closed rather than binding a stray."""
    cfg_dir, adapter_dir = _mk_instance(tmp_path)
    # Put a same-named module in a DIFFERENT dir, earlier on sys.path, with NO
    # copy inside instance/flavor-a — so import resolves the stray.
    stray_dir = tmp_path / "stray"
    stray_dir.mkdir()
    (stray_dir / "srcstub_stray.py").write_text("class StubSource:\n    pass\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(stray_dir))
    (cfg_dir / "sources.yml").write_text(
        "adapter: srcstub_stray:StubSource\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    assert isinstance(src_pkg.get_source(), NullPersonalSource)


def test_get_source_caches_one_resolution(tmp_path):
    cfg_dir, adapter_dir = _mk_instance(tmp_path)
    _write_stub(adapter_dir, "srcstub_cache")
    cfg = cfg_dir / "sources.yml"
    cfg.write_text("adapter: srcstub_cache:StubSource\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    first = src_pkg.get_source()
    second = src_pkg.get_source()
    assert first is second                    # cached identity — resolved once
    cfg.unlink()                              # remove the config…
    assert src_pkg.get_source() is first      # …still the cached instance (no re-resolve)


def test_null_source_and_dispatch_satisfy_the_protocols():
    assert isinstance(NullPersonalSource(), PersonalSource)
    assert isinstance(NullPersonalDispatch(), PersonalDispatch)
    # fail-closed reads never leak / never crash (except the honest read_note)
    ns = NullPersonalSource()
    assert ns.available() is False
    assert ns.search("x") == {"hits": [], "topic_terms": None}
    assert ns.find_reply_candidates() == []
    assert ns.person_intel("slug") == ""
    assert ns.open_commitments("owed_by") == []
    assert ns.voice_profile() == "" and ns.model_patterns() == ""
    assert ns.drafting_lessons("2026-01-01") == ""
    with pytest.raises(FileNotFoundError):
        ns.read_note("anything.md")
    # fail-closed writes no-op, never send/raise
    nd = NullPersonalDispatch()
    assert nd.queue_draft("x") is None
    assert nd.deliver("x") is None
    assert nd.append_note("rel", "body") is None
    assert nd.log_reasoning(action="x") is None


def test_sources_package_has_no_launcher_coupling():
    """LAYER SEP self-check: base.py / null.py / __init__.py carry no bare quoted
    instance path token (the ``check-layer-separation.sh`` needle) and no
    screenpipe / _shared import. Needle assembled at runtime so this file stays
    clean of the token itself."""
    dq, sq = chr(34), chr(39)
    needle_dq = dq + "inst" + "ance" + dq     # the double-quoted instance token
    needle_sq = sq + "inst" + "ance" + sq     # the single-quoted instance token
    forbidden_imports = (
        "screenpipe", "draft_lib", "commitments_lib", "context_lib",
        "me_signal", "sp_lib", "product_ops_lib", "email_lib",
        "teams_graph_lib", "agent_reasoning",
    )
    for name in ("base.py", "null.py", "__init__.py"):
        text = (_SRC_DIR / name).read_text(encoding="utf-8")
        assert needle_dq not in text, "%s carries a bare quoted instance token" % name
        assert needle_sq not in text, "%s carries a bare quoted instance token" % name
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                for tok in forbidden_imports:
                    assert tok not in stripped, "%s statically imports %s" % (name, tok)
