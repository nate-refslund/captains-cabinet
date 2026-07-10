"""AX-7 — posture presets ×3 + the read-only posture-status.py probe.

Axes spec (docs/plans/cabinet-axes-spec-2026-07-05.md §0/§5): presets are the
UX, axes are the architecture — three pre-filled posture.yml templates whose
axis points are pinned here, each schema-valid against the REAL validator so
a captain who edits only `deployment:` holds a working ruling. All ship the
inert CHANGE-ME deployment (a verbatim copy can never match a CABINET_ID).

posture-status.py emits {level, flavor, target, attested, narrow_cap} via the
posture kernel's own internals — read-only (file_needs=False everywhere), and
any unexpected failure emits the guardian fail-closed shape.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import posture as P

PRESET_DIR = _REPO_ROOT / "instance/config" / "posture-presets"
STATUS_SCRIPT = _REPO_ROOT / "cabinet" / "scripts" / "posture-status.py"

# preset -> the axis point it pre-fills (spec §5)
PRESET_AXES = {
    "personal-macbook": ("guardian", "personal", "macbook"),
    "org-macmini": ("sovereign", "org", "mac_mini"),
    "org-docker": ("guardian", "org", "docker"),
}

LOCKED = lambda p: True  # noqa: E731
UNLOCKED = lambda p: False  # noqa: E731


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("CABINET_POSTURE", "CABINET_ROOT", "CABINET_ID",
                "CABINET_NEEDS_WIRED"):
        monkeypatch.delenv(var, raising=False)


def _load(name: str) -> dict:
    return yaml.safe_load((PRESET_DIR / f"{name}.yml").read_text())


# ---------------------------------------------------------------------------
# The three presets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(PRESET_AXES))
def test_preset_exists_and_is_schema_valid(name):
    data = _load(name)
    assert P.validation_error(data) is None, f"{name}: {P.validation_error(data)}"


@pytest.mark.parametrize("name,axes", sorted(PRESET_AXES.items()))
def test_preset_prefills_its_axis_point(name, axes):
    want_level, want_flavor, want_target = axes
    data = _load(name)
    assert data["posture"] == want_level
    assert data["flavor"] == want_flavor
    assert data["deployment_target"] == want_target


@pytest.mark.parametrize("name", sorted(PRESET_AXES))
def test_preset_ships_inert_deployment_placeholder(name):
    """A verbatim copy must never match a real CABINET_ID (default 'main') —
    treated absent ⇒ guardian until the captain names their deployment."""
    data = _load(name)
    assert data["deployment"] == "CHANGE-ME"
    assert data["deployment"] != P.cabinet_id()


@pytest.mark.parametrize("name", sorted(PRESET_AXES))
def test_preset_never_grant_defaults_empty(name):
    assert _load(name).get("never_grant") == []


def test_personal_preset_documents_the_external_comms_choice():
    """The never_grant comment carries the captain's [external_comms] example
    (Ada's ACT-AND-DRAFT policy) — instance-scoped, never flavor-structural."""
    text = (PRESET_DIR / "personal-macbook.yml").read_text()
    assert "never_grant: [external_comms]" in text


def test_sovereign_preset_prints_the_attestation_ritual():
    text = (PRESET_DIR / "org-macmini.yml").read_text()
    assert "germline-lock.sh unlock" in text
    assert "germline-lock.sh lock" in text


def test_docker_preset_names_the_host_side_ritual():
    text = (PRESET_DIR / "org-docker.yml").read_text()
    assert "ro_mount" in text or ":ro" in text
    assert "host" in text.lower()


def _install_preset(root: Path, name: str) -> Path:
    """Copy a preset into a tmp root as this deployment's ruling (the one
    edit the captain makes: deployment -> CABINET_ID)."""
    data = _load(name)
    data["deployment"] = "main"
    d = root / "instance/config"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "posture.yml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_org_macmini_preset_is_a_working_sovereign_ruling(tmp_path):
    _install_preset(tmp_path, "org-macmini")
    assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED,
                             file_needs=False) == "sovereign"
    # unlocked ⇒ fail-closed guardian (the ritual IS the activation)
    assert P.resolve_posture(root=tmp_path, is_locked_fn=UNLOCKED,
                             file_needs=False) == "guardian"


def test_guardian_presets_are_inert_even_locked(tmp_path):
    for name in ("personal-macbook", "org-docker"):
        _install_preset(tmp_path, name)
        assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED,
                                 file_needs=False) == "guardian"


# ---------------------------------------------------------------------------
# posture-status.py — the read-only JSON probe
# ---------------------------------------------------------------------------

def _run_status(root: Path) -> dict:
    env = dict(os.environ)
    env.pop("CABINET_POSTURE", None)
    env.update({"CABINET_ROOT": str(root), "CABINET_ID": "main"})
    res = subprocess.run([sys.executable, str(STATUS_SCRIPT)], env=env,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _write_ruling(root: Path, **overrides) -> Path:
    cfg = {"version": 1, "status": "ruled",
           "ruled_at": "2026-07-05T00:00:00Z", "basis": "test ruling",
           "deployment": "main", "flavor": "org", "posture": "sovereign"}
    cfg.update(overrides)
    d = root / "instance/config"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "posture.yml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_status_empty_root_is_the_guardian_default_shape(tmp_path):
    out = _run_status(tmp_path)
    assert set(out) == {"level", "flavor", "target", "attested", "narrow_cap"}
    assert out["level"] == "guardian"
    assert out["flavor"] is None
    assert out["target"] == P.infer_deployment_target()
    assert out["attested"] is False
    assert out["narrow_cap"] is None


def test_status_surfaces_unattested_ruling_facts_fail_closed(tmp_path):
    """An unlocked sovereign ruling: level stays guardian (fail-closed), but
    the topology/identity facts (flavor, declared target) still render."""
    _write_ruling(tmp_path, deployment_target="docker")
    out = _run_status(tmp_path)
    assert out["level"] == "guardian" and out["attested"] is False
    assert out["flavor"] == "org"
    assert out["target"] == "docker"


def test_status_honors_unattested_earn_up_and_narrow_cap(tmp_path):
    _write_ruling(tmp_path, posture="earn_up", flavor="personal")
    out = _run_status(tmp_path)
    assert out["level"] == "earn_up"          # narrowing needs no attestation
    assert out["flavor"] == "personal" and out["attested"] is False

    (tmp_path / "instance/config" / "posture-narrow").write_text("guardian\n")
    out = _run_status(tmp_path)
    assert out["narrow_cap"] == "guardian"
    assert out["level"] == "earn_up"          # caps only narrow, never widen


def test_status_corrupt_ruling_reads_as_absent(tmp_path):
    _write_ruling(tmp_path, evil_key="x")
    out = _run_status(tmp_path)
    assert out["level"] == "guardian"
    assert out["flavor"] is None and out["attested"] is False


def test_status_probe_files_no_needs(tmp_path):
    """READ-ONLY contract: even a corrupt ruling must not make the status
    probe file a need (file_needs=False everywhere) or write anything."""
    ruling = _write_ruling(tmp_path, evil_key="x")
    before = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    _run_status(tmp_path)
    after = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    assert after == before and ruling in after


def test_status_attested_path_in_process(tmp_path, monkeypatch):
    """The attested=True face (schg can't be faked in a subprocess): load the
    script as a module and re-point the backend fn, per the posture-module
    test seam."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_ID", "main")
    _write_ruling(tmp_path, deployment_target="macbook")
    spec = importlib.util.spec_from_file_location("posture_status_ax7",
                                                  STATUS_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setitem(P._BACKEND_FNS, "schg", lambda p: True)
    out = mod.status()
    assert out["attested"] is True
    assert out["level"] == "sovereign"
    assert out["target"] == "macbook"
