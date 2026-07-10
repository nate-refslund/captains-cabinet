"""SOV-1 — posture selection kernel truth-table [FI-1].

Guardian is the answer to every ambiguity: absent / corrupt / unknown-key /
deployment-mismatch / unlocked all resolve `guardian`; env may only narrow
(`CABINET_POSTURE=guardian` brakes, `=sovereign` is IGNORED); there is NO
dev bypass of the schg attestation — tests inject `is_locked_fn` and own
their tmp roots.
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
    d = root / "instance" / "config"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "posture.yml"
    p.write_text(text if text is not None else yaml.safe_dump(cfg))
    return p


# ---------------------------------------------------------------------------
# Truth table
# ---------------------------------------------------------------------------

def test_absent_resolves_guardian(tmp_path):
    assert P.posture_config_present(tmp_path) is False
    assert P.resolve_posture(root=tmp_path) == "guardian"
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_valid_locked_matching_resolves_sovereign(tmp_path):
    write_posture(tmp_path)
    assert P.posture_config_present(tmp_path) is True
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"


def test_valid_guardian_ruling_resolves_guardian(tmp_path):
    write_posture(tmp_path, posture="guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_unlocked_resolves_guardian(tmp_path):
    write_posture(tmp_path)
    # Default attestation on a real tmp file: no schg flag ⇒ not locked.
    assert P.resolve_posture(root=tmp_path) == "guardian"
    # Injected refusal behaves identically.
    assert P.resolve_posture(root=tmp_path, is_locked_fn=UNLOCKED) == "guardian"


def test_unparseable_resolves_guardian(tmp_path):
    write_posture(tmp_path, text="posture: [unclosed\n  ")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_unknown_key_is_corrupt_guardian(tmp_path):
    write_posture(tmp_path, dev_bypass=True)
    assert P.load_posture_config(tmp_path, is_locked_fn=LOCKED) is None
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


@pytest.mark.parametrize("overrides", [
    {"version": 2},
    {"status": "draft"},
    {"flavor": "corporate"},
    {"posture": "yolo"},
    {"basis": ""},
    {"deployment": ""},
    {"lanes": "bakery"},
    {"lanes": {"bakery": "wide-open"}},
    {"caps": {"hard_multiplier": 0}},
    {"caps": {"hard_multiplier": 10, "soft": 1}},
    {"max_auto_exec_steps": 0},
])
def test_schema_violations_resolve_guardian(tmp_path, overrides):
    write_posture(tmp_path, **overrides)
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_missing_required_key_resolves_guardian(tmp_path):
    cfg = yaml.safe_load(yaml.safe_dump({
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "b", "deployment": "main", "flavor": "org",
    }))  # no `posture`
    write_posture(tmp_path, text=yaml.safe_dump(cfg))
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_deployment_mismatch_treated_absent(tmp_path, monkeypatch):
    write_posture(tmp_path, deployment="mini-bakery")  # CABINET_ID defaults "main"
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"
    monkeypatch.setenv("CABINET_ID", "mini-bakery")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "sovereign"


# ---------------------------------------------------------------------------
# Lane override
# ---------------------------------------------------------------------------

def test_lane_override_widens_named_lane_only(tmp_path):
    write_posture(tmp_path, posture="guardian", lanes={"bakery": "sovereign"})
    assert P.resolve_posture("bakery", root=tmp_path, is_locked_fn=LOCKED) == "sovereign"
    assert P.resolve_posture("newsletter", root=tmp_path, is_locked_fn=LOCKED) == "guardian"
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_lane_override_narrows_named_lane(tmp_path):
    write_posture(tmp_path, posture="sovereign", lanes={"bakery": "guardian"})
    assert P.resolve_posture("bakery", root=tmp_path, is_locked_fn=LOCKED) == "guardian"
    assert P.resolve_posture("newsletter", root=tmp_path, is_locked_fn=LOCKED) == "sovereign"


# ---------------------------------------------------------------------------
# Env may only narrow — and there is NO unlocked-ok bypass
# ---------------------------------------------------------------------------

def test_env_guardian_narrows_over_sovereign_ruling(tmp_path, monkeypatch):
    write_posture(tmp_path)
    monkeypatch.setenv("CABINET_POSTURE", "guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_env_sovereign_never_widens(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_POSTURE", "sovereign")
    assert P.resolve_posture(root=tmp_path) == "guardian"  # no config at all
    write_posture(tmp_path, posture="guardian")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"


def test_no_unlocked_ok_env_bypass(tmp_path, monkeypatch):
    """The killed CABINET_POSTURE_UNLOCKED_OK override must have no effect."""
    write_posture(tmp_path)
    monkeypatch.setenv("CABINET_POSTURE_UNLOCKED_OK", "1")
    assert P.resolve_posture(root=tmp_path) == "guardian"  # still unlocked ⇒ guardian


def test_is_locked_non_darwin_is_false(tmp_path, monkeypatch):
    p = write_posture(tmp_path)
    monkeypatch.setattr(P.sys, "platform", "linux")
    assert P.is_locked(p) is False


def test_is_locked_missing_file_is_false(tmp_path):
    assert P.is_locked(tmp_path / "nope.yml") is False


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

def test_hard_multiplier_defaults_and_reads_config(tmp_path):
    assert P.hard_multiplier(tmp_path) == 10
    write_posture(tmp_path, caps={"hard_multiplier": 3})
    assert P.hard_multiplier(tmp_path, is_locked_fn=LOCKED) == 3
    assert P.hard_multiplier(tmp_path, is_locked_fn=UNLOCKED) == 10  # unattested ⇒ default


def test_max_auto_steps_guardian_forced_two(tmp_path):
    write_posture(tmp_path, max_auto_exec_steps=9)
    assert P.max_auto_steps("guardian", tmp_path, is_locked_fn=LOCKED) == 2
    assert P.max_auto_steps("sovereign", tmp_path, is_locked_fn=LOCKED) == 9


def test_max_auto_steps_sovereign_defaults(tmp_path):
    write_posture(tmp_path)
    assert P.max_auto_steps("sovereign", tmp_path, is_locked_fn=LOCKED) == 5
    # A sovereign claim without an attestable ruling narrows to guardian's 2.
    assert P.max_auto_steps("sovereign", tmp_path, is_locked_fn=UNLOCKED) == 2


# ---------------------------------------------------------------------------
# Corrupt/unlocked ruling files a deduped need (when the seam is wired)
# ---------------------------------------------------------------------------

def _open_needs(root):
    return N.list_open(root=root)


def test_corrupt_files_need_when_wired(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path, dev_bypass=True)
    P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED)
    P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED)  # re-resolve dedups
    rows = _open_needs(tmp_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "decision"
    assert rows[0]["action_type"] == "posture_config"
    assert rows[0]["count"] == 2
    assert "corrupt" in rows[0]["why"]


def test_unlocked_files_need_when_wired(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path)
    P.resolve_posture(root=tmp_path)  # default attestation: unlocked
    rows = _open_needs(tmp_path)
    assert len(rows) == 1
    assert "not schg-locked" in rows[0]["why"]


def test_guardian_default_files_nothing(tmp_path):
    """Bit-identical default: unwired guardian world writes NO ledger."""
    write_posture(tmp_path, dev_bypass=True)
    P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED)
    assert not N.ledger_path(tmp_path).exists()


def test_mismatch_is_silent_even_when_wired(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path, deployment="someone-else")
    P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED)
    assert _open_needs(tmp_path) == []


# ---------------------------------------------------------------------------
# The shipped example validates
# ---------------------------------------------------------------------------

def test_shipped_example_is_schema_valid():
    example = _REPO_ROOT / "instance" / "config" / "posture.yml.example"
    data = yaml.safe_load(example.read_text())
    assert P.validation_error(data) is None
    assert data["posture"] in P.POSTURES
