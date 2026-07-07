"""P3b — the "corpus" section source (org product-brain) in gather_signals.

The clean-room gap this closes: on org boxes vault_dir() fail-closes to ""
and every vault section is empty, so the lane gathered ZERO sections. Corpus
sections root at env.product_brain_dir() instead — these tests fixture a tmp
corpus wired through the REAL resolver (CABINET_PRODUCT_BRAIN_DIR override +
cache reset) so the whole seam (accessor → gather) is exercised, plus the
accessor's own resolution order. Same explicit-mtime fencing discipline as
test_gather_v2; no live APIs, no repo corpus reliance."""
from __future__ import annotations

import datetime as dt
import os

import pytest

import framework.env as fenv
from framework.acting import run_action_lane as ral

AS_OF = dt.datetime(2026, 7, 7, 12, 0, 0, tzinfo=dt.timezone.utc)
RECENT = AS_OF - dt.timedelta(hours=1)
OLD = AS_OF - dt.timedelta(hours=100)      # outside the 72h operational window
ANCIENT = AS_OF - dt.timedelta(hours=1000)
FUTURE = AS_OF + dt.timedelta(hours=1)


def _write(root, rel, body, *, mtime=RECENT):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    ts = mtime.timestamp()
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def vault(tmp_path):
    return tmp_path / "vault"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A tmp product-brain corpus resolved through the REAL accessor: env
    override set + process cache reset (monkeypatch restores both)."""
    d = tmp_path / "corpus"
    d.mkdir()
    monkeypatch.setenv("CABINET_PRODUCT_BRAIN_DIR", str(d))
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    return d


# --- the clean-room fix: corpus sections appear without any vault ------------

def test_seeded_corpus_gathers_on_vaultless_box(vault, corpus):
    # vault dir never created — the org-box shape that used to gather ZERO
    _write(corpus, "architecture.md", "Next.js on Vercel; Neon Postgres")
    _write(corpus, "decisions/d1.md", "Decided: ship the EU flow first")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- CORPUS ref=product-brain/architecture.md ---" in out
    assert "Neon Postgres" in out
    assert "--- CORPUS ref=product-brain/decisions/d1.md ---" in out


def test_empty_corpus_dir_yields_no_corpus_sections(vault, corpus):
    _write(vault, "6-Commitments/cmt-1.md", "an open commitment")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "CORPUS" not in out                     # empty dir → section empty
    assert "6-Commitments/cmt-1.md" in out         # vault unaffected


def test_unresolved_corpus_skips_fail_closed(vault, monkeypatch):
    # a box with NO corpus configured: resolver "" → section skipped, no error
    monkeypatch.setattr(ral, "product_brain_dir", lambda: "")
    _write(vault, "2-Meetings/m.md", "notes")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "CORPUS" not in out
    assert "--- MEETING ref=2-Meetings/m.md ---" in out


# --- fencing (same as_of/window discipline as vault sections) ----------------

def test_corpus_as_of_ceiling_and_operational_window(vault, corpus):
    _write(corpus, "deploy-notes/future.md", "not yet", mtime=FUTURE)
    _write(corpus, "deploy-notes/fresh.md", "shipped v2", mtime=RECENT)
    _write(corpus, "deploy-notes/stale.md", "old news", mtime=OLD)
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "product-brain/deploy-notes/fresh.md" in out
    assert "future.md" not in out                  # > as_of never leaks
    assert "stale.md" not in out                   # outside the 72h window


def test_strategic_corpus_is_unwindowed(vault, corpus):
    _write(corpus, "incidents/i1.md", "root cause: WAL wedge", mtime=ANCIENT)
    assert "incidents/i1.md" not in ral.gather_signals(AS_OF, vault=vault)
    out = ral.gather_signals(AS_OF, vault=vault, profile="strategic")
    assert "--- CORPUS ref=product-brain/incidents/i1.md ---" in out
    assert "WAL wedge" in out                      # ancient, but unwindowed


def test_operational_corpus_cap_is_newest_4(vault, corpus):
    for i in range(1, 6):                          # f1 newest … f5 oldest
        _write(corpus, f"decisions/f{i}.md", f"decision {i}",
               mtime=AS_OF - dt.timedelta(hours=i))
    out = ral.gather_signals(AS_OF, vault=vault)
    for i in range(1, 5):
        assert f"decisions/f{i}.md" in out
    assert "decisions/f5.md" not in out            # 5th exceeds the cap of 4


# --- coexistence: additive alongside the vault --------------------------------

def test_vault_and_corpus_coexist_additively(vault, corpus):
    _write(vault, "6-Commitments/cmt-1.md", "owes the licences")
    _write(corpus, "architecture.md", "stack facts")
    out = ral.gather_signals(AS_OF, vault=vault)
    # vault block byte-shape unchanged (no prefix), corpus namespaced
    assert "--- OPEN COMMITMENT ref=6-Commitments/cmt-1.md ---" in out
    assert "--- CORPUS ref=product-brain/architecture.md ---" in out


# --- env.product_brain_dir() resolution order ---------------------------------

def test_accessor_env_override_wins(tmp_path, monkeypatch):
    d = tmp_path / "elsewhere"
    d.mkdir()
    monkeypatch.setenv("CABINET_PRODUCT_BRAIN_DIR", str(d))
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == str(d)


def test_accessor_repo_default_when_dir_exists(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "product-brain").mkdir(parents=True)
    monkeypatch.delenv("CABINET_PRODUCT_BRAIN_DIR", raising=False)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == str(root / "product-brain")


def test_accessor_fail_closed_empty_when_absent(tmp_path, monkeypatch):
    root = tmp_path / "cleanroom"                  # no product-brain/ inside
    root.mkdir()
    monkeypatch.delenv("CABINET_PRODUCT_BRAIN_DIR", raising=False)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == ""


def _root_with_platform_yml(tmp_path, key_value: str):
    root = tmp_path / "repo"
    (root / "instance" / "config").mkdir(parents=True)
    (root / "instance" / "config" / "platform.yml").write_text(
        f'product_brain_dir: "{key_value}"\n'
    )
    return root


def test_accessor_platform_key_relative_resolves_against_root(tmp_path, monkeypatch):
    """Review fix 2026-07-07: the platform.yml product_brain_dir key the
    generator stamps is READ (it was dead config) — a relative value resolves
    against the repo root, between the env override and the in-repo default."""
    root = _root_with_platform_yml(tmp_path, "docs/brain")
    (root / "docs" / "brain").mkdir(parents=True)
    (root / "product-brain").mkdir()               # in-repo default ALSO exists
    monkeypatch.delenv("CABINET_PRODUCT_BRAIN_DIR", raising=False)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == str(root / "docs" / "brain")


def test_accessor_env_override_beats_platform_key(tmp_path, monkeypatch):
    root = _root_with_platform_yml(tmp_path, "docs/brain")
    (root / "docs" / "brain").mkdir(parents=True)
    override = tmp_path / "elsewhere"
    override.mkdir()
    monkeypatch.setenv("CABINET_PRODUCT_BRAIN_DIR", str(override))
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == str(override)


def test_accessor_platform_key_missing_dir_fails_closed(tmp_path, monkeypatch):
    """A configured path that does not exist falls through (never a phantom
    scan root): to the in-repo default if present, else ''."""
    root = _root_with_platform_yml(tmp_path, "docs/nonexistent")
    (root / "product-brain").mkdir()
    monkeypatch.delenv("CABINET_PRODUCT_BRAIN_DIR", raising=False)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == str(root / "product-brain")

    root2 = _root_with_platform_yml(tmp_path / "two", "docs/nonexistent")
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root2)
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == ""


def test_accessor_platform_key_stamped_default_matches_in_repo(tmp_path, monkeypatch):
    """The generator's stamped default ("product-brain") resolves to the same
    <root>/product-brain the in-repo arm would pick — wiring the key changed
    nothing for generated instances (backward compatible)."""
    root = _root_with_platform_yml(tmp_path, "product-brain")
    (root / "product-brain").mkdir()
    monkeypatch.delenv("CABINET_PRODUCT_BRAIN_DIR", raising=False)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_product_brain_dir_cache", None)
    assert fenv.product_brain_dir() == str(root / "product-brain")
