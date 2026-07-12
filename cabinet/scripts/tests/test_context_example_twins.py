"""The shipped Testburg lane-declaration .example twins (Wave G resolver-core).

The egg carries instance/config/contexts/{bakery-site,newsletter}.yml.example
as a fresh hatch's concrete model for declaring lanes (manifest R124 block +
contexts-prune keep list). These tests pin the twins' contract at the SOURCE:

  1. hatch-usable — copied to <slug>.yml, each twin resolves through the REAL
     python resolver (framework.env.lanes()) to exactly its declared slug, and
     the filename-minus-.yml.example equals the slug (the hook-side lane cache
     is filename-keyed, so a drifted example would teach a broken convention);
  2. dormant at the source — a .yml.example twin matches no *.yml glob, so the
     twins never enumerate as live lanes of THIS checkout;
  3. leak-clean — audited against the AUTHORITATIVE banned-pattern list loaded
     from test_testburg_fixture.py (never duplicated, never relaxed), so the
     example vocabulary can only be synthetic Testburg.

Pure-local: tmp_path roots + this checkout's committed files. No network.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTEXTS_DIR = _REPO_ROOT / "instance/config/contexts"

TWINS = ("bakery-site.yml.example", "newsletter.yml.example")


def _load_banned_patterns():
    """The authoritative leak list lives in test_testburg_fixture.py — load it
    by path (package-layout agnostic) instead of copying the patterns."""
    spec = importlib.util.spec_from_file_location(
        "_testburg_fixture_mod", Path(__file__).with_name("test_testburg_fixture.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.BANNED_PATTERNS), mod._DIGIT_RUN


@pytest.mark.parametrize("name", TWINS)
def test_twin_exists_and_slug_matches_filename(name):
    p = _CONTEXTS_DIR / name
    assert p.is_file(), f"shipped example twin missing: {p}"
    expected_slug = name[: -len(".yml.example")]
    m = re.search(r"^slug:\s*(.+)$", p.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"{name}: no top-level slug: scalar"
    assert m.group(1).strip() == expected_slug, (
        f"{name}: filename/slug drift — the hook-side lane cache is "
        f"filename-keyed, so the example must model filename == slug")


def test_twins_resolve_through_the_real_resolver(tmp_path, monkeypatch):
    """Copied to <slug>.yml in a fresh root, the twins ARE the lane enum —
    proven through framework.env.lanes() itself, not a re-implementation."""
    import framework.env as env

    ctx = tmp_path / "instance/config" / "contexts"
    ctx.mkdir(parents=True)
    for name in TWINS:
        target = ctx / name[: -len(".example")]
        target.write_text((_CONTEXTS_DIR / name).read_text(encoding="utf-8"),
                          encoding="utf-8")
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    saved = env._lanes_cache
    env._lanes_cache = None
    try:
        assert env.lanes() == ("bakery-site", "newsletter")
    finally:
        env._lanes_cache = saved


def test_twins_never_enumerate_as_live_lanes(tmp_path, monkeypatch):
    """.yml.example matches no *.yml glob: a root holding ONLY the twins (as
    shipped) resolves an EMPTY lane enum — the twins are models, never lanes."""
    import framework.env as env

    ctx = tmp_path / "instance/config" / "contexts"
    ctx.mkdir(parents=True)
    for name in TWINS:
        (ctx / name).write_text((_CONTEXTS_DIR / name).read_text(encoding="utf-8"),
                                encoding="utf-8")
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    saved = env._lanes_cache
    env._lanes_cache = None
    try:
        assert env.lanes() == ()
    finally:
        env._lanes_cache = saved


@pytest.mark.parametrize("name", TWINS)
def test_twin_is_leak_clean(name):
    banned, digit_run = _load_banned_patterns()
    text = (_CONTEXTS_DIR / name).read_text(encoding="utf-8")
    low = text.lower()
    hits = [pat for pat in banned if pat in low]
    assert not hits, f"{name}: banned token(s) {hits} — examples are Testburg-only"
    assert not digit_run.search(text), f"{name}: 9+ digit run (chat/board-id-shaped)"
