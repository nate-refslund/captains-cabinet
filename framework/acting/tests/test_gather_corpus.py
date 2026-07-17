"""P3b — the "corpus" section source (the cabinet vault) in gather_signals.

The clean-room gap this closes: on org boxes vault_dir() fail-closes to ""
and every vault section is empty, so the lane gathered ZERO sections. Corpus
sections root at env.org_vault_dir() instead — these tests fixture a tmp
corpus wired through the REAL resolver (env override + cache reset) so the
whole seam (accessor → gather) is exercised, plus the accessor's own
resolution order INCLUDING the vault-rename back-compat matrix (2026-07-17:
new env CABINET_ORG_VAULT_DIR, legacy CABINET_PRODUCT_BRAIN_DIR alias, new
platform key org_vault_dir, legacy product_brain_dir key, in-repo vault/
default, legacy in-repo product-brain/, and the deprecated
product_brain_dir() wrapper the schg germline lane still imports). Same
explicit-mtime fencing discipline as test_gather_v2; no live APIs, no repo
corpus reliance."""
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

BOTH_ENVS = ("CABINET_ORG_VAULT_DIR", "CABINET_PRODUCT_BRAIN_DIR")


def _write(root, rel, body, *, mtime=RECENT):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    ts = mtime.timestamp()
    os.utime(p, (ts, ts))
    return p


def _reset(monkeypatch, **env):
    """Clear both resolver env names, apply the given ones, reset the cache."""
    for name in BOTH_ENVS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)


@pytest.fixture
def vault(tmp_path):
    return tmp_path / "vault-personal"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A tmp org-vault corpus resolved through the REAL accessor: env
    override set + process cache reset (monkeypatch restores both)."""
    d = tmp_path / "corpus"
    d.mkdir()
    _reset(monkeypatch, CABINET_ORG_VAULT_DIR=str(d))
    return d


# --- the clean-room fix: corpus sections appear without any vault ------------

def test_seeded_corpus_gathers_on_vaultless_box(vault, corpus):
    # vault dir never created — the org-box shape that used to gather ZERO
    _write(corpus, "architecture.md", "Next.js on Vercel; Neon Postgres")
    _write(corpus, "decisions/d1.md", "Decided: ship the EU flow first")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- CORPUS ref=vault/architecture.md ---" in out
    assert "Neon Postgres" in out
    assert "--- CORPUS ref=vault/decisions/d1.md ---" in out


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
    assert "vault/deploy-notes/fresh.md" in out
    assert "future.md" not in out                  # > as_of never leaks
    assert "stale.md" not in out                   # outside the 72h window


def test_strategic_corpus_is_unwindowed(vault, corpus):
    _write(corpus, "incidents/i1.md", "root cause: WAL wedge", mtime=ANCIENT)
    assert "incidents/i1.md" not in ral.gather_signals(AS_OF, vault=vault)
    out = ral.gather_signals(AS_OF, vault=vault, profile="strategic")
    assert "--- CORPUS ref=vault/incidents/i1.md ---" in out
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
    assert "--- CORPUS ref=vault/architecture.md ---" in out


# --- env.org_vault_dir() resolution order -------------------------------------

def test_accessor_env_override_wins(tmp_path, monkeypatch):
    d = tmp_path / "elsewhere"
    d.mkdir()
    _reset(monkeypatch, CABINET_ORG_VAULT_DIR=str(d))
    assert fenv.org_vault_dir() == str(d)


def test_accessor_legacy_env_alias_still_honored(tmp_path, monkeypatch):
    """Back-compat matrix: a pre-rename deployment exporting ONLY
    CABINET_PRODUCT_BRAIN_DIR must keep resolving byte-identically."""
    d = tmp_path / "legacy-env"
    d.mkdir()
    _reset(monkeypatch, CABINET_PRODUCT_BRAIN_DIR=str(d))
    assert fenv.org_vault_dir() == str(d)


def test_accessor_new_env_beats_legacy_env(tmp_path, monkeypatch):
    new = tmp_path / "new-env"
    old = tmp_path / "old-env"
    new.mkdir(); old.mkdir()
    _reset(monkeypatch, CABINET_ORG_VAULT_DIR=str(new),
           CABINET_PRODUCT_BRAIN_DIR=str(old))
    assert fenv.org_vault_dir() == str(new)


def test_accessor_repo_default_when_vault_dir_exists(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "vault").mkdir(parents=True)
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "vault")


def test_accessor_legacy_repo_default_still_honored(tmp_path, monkeypatch):
    """An un-migrated checkout that still carries product-brain/ (and no
    vault/) must keep resolving its corpus."""
    root = tmp_path / "repo"
    (root / "product-brain").mkdir(parents=True)
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "product-brain")


def test_accessor_vault_beats_legacy_dir_when_both_exist(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "vault").mkdir(parents=True)
    (root / "product-brain").mkdir()
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "vault")


def test_accessor_fail_closed_empty_when_absent(tmp_path, monkeypatch):
    root = tmp_path / "cleanroom"                  # neither corpus dir inside
    root.mkdir()
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == ""


def _root_with_platform_yml(tmp_path, body: str):
    root = tmp_path / "repo"
    (root / "instance" / "config").mkdir(parents=True)
    (root / "instance" / "config" / "platform.yml").write_text(body)
    return root


def test_accessor_platform_key_relative_resolves_against_root(tmp_path, monkeypatch):
    """The platform.yml org_vault_dir key the generator stamps is READ — a
    relative value resolves against the repo root, between the env override
    and the in-repo default."""
    root = _root_with_platform_yml(tmp_path, 'org_vault_dir: "docs/brain"\n')
    (root / "docs" / "brain").mkdir(parents=True)
    (root / "vault").mkdir()                       # in-repo default ALSO exists
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "docs" / "brain")


def test_accessor_legacy_platform_key_still_honored(tmp_path, monkeypatch):
    """Back-compat matrix: a pre-rename platform.yml carrying ONLY the
    product_brain_dir key keeps steering the resolver."""
    root = _root_with_platform_yml(tmp_path, 'product_brain_dir: "docs/brain"\n')
    (root / "docs" / "brain").mkdir(parents=True)
    (root / "vault").mkdir()
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "docs" / "brain")


def test_accessor_new_platform_key_beats_legacy_key(tmp_path, monkeypatch):
    root = _root_with_platform_yml(
        tmp_path,
        'org_vault_dir: "docs/new-brain"\nproduct_brain_dir: "docs/old-brain"\n')
    (root / "docs" / "new-brain").mkdir(parents=True)
    (root / "docs" / "old-brain").mkdir(parents=True)
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "docs" / "new-brain")


def test_accessor_env_override_beats_platform_key(tmp_path, monkeypatch):
    root = _root_with_platform_yml(tmp_path, 'org_vault_dir: "docs/brain"\n')
    (root / "docs" / "brain").mkdir(parents=True)
    override = tmp_path / "elsewhere"
    override.mkdir()
    _reset(monkeypatch, CABINET_ORG_VAULT_DIR=str(override))
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(override)


def test_accessor_platform_key_missing_dir_fails_closed(tmp_path, monkeypatch):
    """A configured path that does not exist falls through (never a phantom
    scan root): to the in-repo default if present, else ''."""
    root = _root_with_platform_yml(tmp_path, 'org_vault_dir: "docs/nonexistent"\n')
    (root / "vault").mkdir()
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "vault")

    root2 = _root_with_platform_yml(tmp_path / "two", 'org_vault_dir: "docs/nonexistent"\n')
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root2)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == ""


def test_accessor_platform_key_stamped_default_matches_in_repo(tmp_path, monkeypatch):
    """The generator's stamped default ("vault") resolves to the same
    <root>/vault the in-repo arm would pick — wiring the key changes
    nothing for generated instances (backward compatible)."""
    root = _root_with_platform_yml(tmp_path, 'org_vault_dir: "vault"\n')
    (root / "vault").mkdir()
    _reset(monkeypatch)
    monkeypatch.setattr(fenv, "_cabinet_root", lambda: root)
    monkeypatch.setattr(fenv, "_org_vault_dir_cache", None)
    assert fenv.org_vault_dir() == str(root / "vault")


# --- the deprecated wrapper (germline lane still imports it) -------------------

def test_deprecated_product_brain_dir_wrapper_delegates(tmp_path, monkeypatch):
    """framework/acting/run_action_lane.py (schg germline) imports
    product_brain_dir by name — the wrapper must stay a WORKING alias of
    org_vault_dir(), including the legacy env alias, until the next
    unlock-window modernization."""
    d = tmp_path / "somewhere"
    d.mkdir()
    _reset(monkeypatch, CABINET_ORG_VAULT_DIR=str(d))
    assert fenv.product_brain_dir() == str(d)
    assert fenv.product_brain_dir() == fenv.org_vault_dir()
