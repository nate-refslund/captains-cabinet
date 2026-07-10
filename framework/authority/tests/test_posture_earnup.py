"""AX-1 — the 3-level posture kernel (axes spec 2026-07-05 §1).

Selection asymmetry: `sovereign` requires the fully attested ruling
(unchanged); `earn_up` is a NARROWING choice honored even from a
valid-but-UNLOCKED ruling (its table may only narrow vs guardian —
matrix-validated — so no attestation is needed). Runtime surfaces
(CABINET_POSTURE env, the `posture-narrow` cap file) can only NARROW, by
min-permissiveness — never widen, not even an earn_up ruling back to
guardian. Plus the axes schema keys (never_grant / deployment_target) and
the symlink/traversal containment on the ruling path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import needs as N
from framework.authority import posture as P

LOCKED = lambda p: True  # noqa: E731 — the injected attestation stub
UNLOCKED = lambda p: False  # noqa: E731


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("CABINET_POSTURE", "CABINET_NEEDS_WIRED", "CABINET_ID",
                "CABINET_ROOT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))


def write_posture(root: Path, text: str | None = None, **overrides) -> Path:
    cfg = {
        "version": 1,
        "status": "ruled",
        "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "test ruling",
        "deployment": "main",
        "flavor": "org",
        "posture": "sovereign",
    }
    cfg.update(overrides)
    # Path built from the kernel's own resolver (layer-separation gate:
    # no literal instance token here; test_posture.py pins the location).
    p = P.posture_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if text is not None else yaml.safe_dump(cfg))
    return p


def write_narrow(root: Path, word: str) -> Path:
    p = P.narrow_cap_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(word)
    return p


def _open_needs(root):
    return N.list_open(root=root)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

def test_earn_up_joins_the_posture_vocab():
    assert P.EARN_UP == "earn_up"
    assert P.POSTURES == frozenset({"earn_up", "guardian", "sovereign"})
    r = P.POSTURE_PERMISSIVENESS
    assert r["earn_up"] < r["guardian"] < r["sovereign"]
    assert set(r) == set(P.POSTURES)


# ---------------------------------------------------------------------------
# Selection asymmetry — sovereign needs the lock, earn_up does not
# ---------------------------------------------------------------------------

def test_attested_earn_up_ruling_resolves_earn_up(tmp_path):
    write_posture(tmp_path, posture="earn_up")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "earn_up"


def test_unlocked_earn_up_ruling_is_honored_without_attestation(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path, posture="earn_up")
    # Default attestation on a real tmp file: no schg flag ⇒ not locked —
    # and the narrowing ruling is honored anyway.
    assert P.resolve_posture(root=tmp_path) == "earn_up"
    # Working as designed ⇒ nothing to repair ⇒ NO unlocked-ruling need.
    assert _open_needs(tmp_path) == []


def test_unlocked_sovereign_ruling_still_resolves_guardian_with_need(
        tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path)  # posture: sovereign
    assert P.resolve_posture(root=tmp_path) == "guardian"
    rows = _open_needs(tmp_path)
    assert len(rows) == 1 and "not schg-locked" in rows[0]["why"]


def test_unlocked_mixed_ruling_caps_at_guardian_and_files_need(
        tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path, posture="earn_up", lanes={"bakery": "sovereign"})
    # The sovereign lane override is capped at guardian (unattested)...
    assert P.resolve_posture("bakery", root=tmp_path) == "guardian"
    # ...while the earn_up default is honored.
    assert P.resolve_posture("newsletter", root=tmp_path) == "earn_up"
    assert P.resolve_posture(root=tmp_path) == "earn_up"
    # A ruling naming anything beyond earn_up is attestation-worthy ⇒ need.
    rows = _open_needs(tmp_path)
    assert len(rows) == 1 and "not schg-locked" in rows[0]["why"]


def test_attested_lane_overrides_carry_earn_up(tmp_path):
    write_posture(tmp_path, posture="guardian", lanes={"bakery": "earn_up"})
    assert P.resolve_posture("bakery", root=tmp_path, is_locked_fn=LOCKED) == "earn_up"
    assert P.resolve_posture("newsletter", root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_load_posture_config_contract_unchanged_for_unattested_earn_up(tmp_path):
    """The pre-axes reader keeps returning None for ANY unattested ruling —
    earn_up's unattested narrowing lives in resolve_posture only."""
    write_posture(tmp_path, posture="earn_up")
    assert P.load_posture_config(tmp_path, is_locked_fn=UNLOCKED) is None
    assert P.load_posture_config(tmp_path, is_locked_fn=LOCKED) is not None


# ---------------------------------------------------------------------------
# Env cap — narrows by min-permissiveness, never widens
# ---------------------------------------------------------------------------

def test_env_earn_up_narrows_from_anywhere(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_POSTURE", "earn_up")
    assert P.resolve_posture(root=tmp_path) == "earn_up"  # no config at all
    write_posture(tmp_path)  # attested sovereign
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "earn_up"
    write_posture(tmp_path, posture="guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "earn_up"


def test_env_guardian_never_widens_an_earn_up_ruling(tmp_path, monkeypatch):
    write_posture(tmp_path, posture="earn_up")
    monkeypatch.setenv("CABINET_POSTURE", "guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "earn_up"


def test_env_guardian_still_brakes_sovereign(tmp_path, monkeypatch):
    write_posture(tmp_path)
    monkeypatch.setenv("CABINET_POSTURE", "guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_env_guardian_drop_brake_stays_silent_on_corrupt_file(
        tmp_path, monkeypatch):
    """Byte-parity with the legacy short-circuit: the env=guardian brake never
    read the ruling, so it files no corrupt-config need either."""
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_POSTURE", "guardian")
    write_posture(tmp_path, dev_bypass=True)  # unknown key ⇒ corrupt
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"
    assert not N.ledger_path(tmp_path).exists()


def test_env_sovereign_and_garbage_still_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_POSTURE", "sovereign")
    assert P.resolve_posture(root=tmp_path) == "guardian"
    monkeypatch.setenv("CABINET_POSTURE", "yolo")
    write_posture(tmp_path)
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"


# ---------------------------------------------------------------------------
# posture-narrow cap file — the second narrow-only surface
# ---------------------------------------------------------------------------

def test_narrow_cap_guardian_caps_sovereign(tmp_path):
    write_posture(tmp_path)
    write_narrow(tmp_path, "guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_narrow_cap_earn_up_caps_everything(tmp_path):
    write_posture(tmp_path)
    write_narrow(tmp_path, "earn_up\n")  # whitespace tolerated
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "earn_up"


def test_narrow_cap_never_widens(tmp_path):
    write_posture(tmp_path, posture="earn_up")
    write_narrow(tmp_path, "guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "earn_up"


def test_narrow_cap_absent_is_no_cap(tmp_path):
    write_posture(tmp_path)
    assert P.narrow_cap(tmp_path) is None
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"


@pytest.mark.parametrize("garbage", ["sovereign", "yolo", "", "  "])
def test_narrow_cap_unrecognized_content_fails_closed_to_earn_up(
        tmp_path, garbage):
    """A corrupted narrowing request must never fail open to a wider posture
    than the Captain may have asked for — and `sovereign` in the cap file is
    a widening attempt, treated exactly like garbage."""
    write_posture(tmp_path)
    write_narrow(tmp_path, garbage)
    assert P.narrow_cap(tmp_path) == "earn_up"
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "earn_up"


# ---------------------------------------------------------------------------
# Axes schema keys — never_grant / deployment_target (closed vocab, optional)
# ---------------------------------------------------------------------------

def test_never_grant_valid_lists_pass_schema(tmp_path):
    write_posture(tmp_path, never_grant=[])
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"
    write_posture(tmp_path, never_grant=["external_comms", "spend"])
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"


@pytest.mark.parametrize("bad", [
    "external_comms",            # not a list
    ["external_commz"],          # typo ⇒ would silently protect nothing
    ["external_comms", 123],     # non-string entry
    [""],                        # empty entry
])
def test_never_grant_malformed_is_corrupt_guardian(tmp_path, bad):
    write_posture(tmp_path, never_grant=bad)
    assert P.load_posture_config(tmp_path, is_locked_fn=LOCKED) is None
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_never_grant_classes_accessor(tmp_path):
    assert P.never_grant_classes(tmp_path) == frozenset()          # absent
    write_posture(tmp_path, never_grant=["external_comms", "spend"])
    # honored attested AND unattested — dropping classes is a pure narrowing
    assert P.never_grant_classes(tmp_path) == {"external_comms", "spend"}
    write_posture(tmp_path, never_grant=["nope"])                  # corrupt
    assert P.never_grant_classes(tmp_path) == frozenset()
    write_posture(tmp_path)                                        # key absent
    assert P.never_grant_classes(tmp_path) == frozenset()


@pytest.mark.parametrize("target", ["macbook", "mac_mini", "docker"])
def test_deployment_target_valid_values_pass_schema(tmp_path, target):
    write_posture(tmp_path, deployment_target=target)
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"
    assert P.deployment_target(tmp_path) == target


def test_deployment_target_unknown_value_is_corrupt_guardian(tmp_path):
    write_posture(tmp_path, deployment_target="cloud")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_deployment_target_readable_without_lock(tmp_path):
    # The target selects WHICH attestation backend applies — its read cannot
    # itself require attestation (circular). Unlocked ruling still answers.
    write_posture(tmp_path, deployment_target="mac_mini")
    assert P.deployment_target(tmp_path) == "mac_mini"


def test_deployment_target_inference(tmp_path, monkeypatch):
    # No ruling + no dockerenv ⇒ macbook (the fail-closed default: schg
    # attests False off-Darwin).
    monkeypatch.setattr(P, "_DOCKERENV", tmp_path / "no-such-sentinel")
    assert P.deployment_target(tmp_path) == "macbook"
    # dockerenv present ⇒ docker
    sentinel = tmp_path / "dockerenv"
    sentinel.write_text("")
    monkeypatch.setattr(P, "_DOCKERENV", sentinel)
    assert P.deployment_target(tmp_path) == "docker"
    # an explicit ruling value beats the sentinel
    write_posture(tmp_path, deployment_target="mac_mini")
    assert P.deployment_target(tmp_path) == "mac_mini"
    # a mismatched-deployment ruling is treated absent ⇒ back to inference
    write_posture(tmp_path, deployment="someone-else",
                  deployment_target="mac_mini")
    assert P.deployment_target(tmp_path) == "docker"


def test_old_files_without_axes_keys_stay_valid(tmp_path):
    write_posture(tmp_path)  # no never_grant / deployment_target
    cfg = P.load_posture_config(tmp_path, is_locked_fn=LOCKED)
    assert cfg is not None
    assert "never_grant" not in cfg and "deployment_target" not in cfg


# ---------------------------------------------------------------------------
# Symlink / traversal containment (axes Corridor constraint)
# ---------------------------------------------------------------------------

def test_symlinked_ruling_is_refused_even_with_lock_stub(tmp_path, monkeypatch):
    """A symlink could borrow another schg-locked file's attestation — the
    realpath containment refuses it before the lock check ever runs."""
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    real = tmp_path / "elsewhere.yml"
    real.write_text(yaml.safe_dump({
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "forged", "deployment": "main", "flavor": "org",
        "posture": "sovereign",
    }))
    ruling = P.posture_path(tmp_path)
    ruling.parent.mkdir(parents=True)
    ruling.symlink_to(real)
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"
    rows = _open_needs(tmp_path)
    assert len(rows) == 1 and "symlink" in rows[0]["why"]


def test_dir_level_symlink_is_refused(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    (elsewhere).mkdir()
    (elsewhere / "posture.yml").write_text(yaml.safe_dump({
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "forged", "deployment": "main", "flavor": "org",
        "posture": "sovereign",
    }))
    cfg_dir = P.posture_path(tmp_path).parent
    cfg_dir.parent.mkdir()
    cfg_dir.symlink_to(elsewhere)
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_is_locked_refuses_a_symlink(tmp_path):
    real = tmp_path / "real.yml"
    real.write_text("x: 1")
    link = tmp_path / "link.yml"
    link.symlink_to(real)
    assert P.is_locked(link) is False  # a link is never attestable


# ---------------------------------------------------------------------------
# Budget tunables under earn_up
# ---------------------------------------------------------------------------

def test_earn_up_gets_the_guardian_step_budget(tmp_path):
    write_posture(tmp_path, posture="earn_up", max_auto_exec_steps=9)
    assert P.max_auto_steps("earn_up", tmp_path, is_locked_fn=LOCKED) == 2


def test_hard_multiplier_still_requires_attestation(tmp_path):
    write_posture(tmp_path, posture="earn_up", caps={"hard_multiplier": 3})
    assert P.hard_multiplier(tmp_path, is_locked_fn=UNLOCKED) == 10
    assert P.hard_multiplier(tmp_path, is_locked_fn=LOCKED) == 3
