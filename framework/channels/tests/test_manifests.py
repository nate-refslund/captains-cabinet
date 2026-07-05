"""AX-5 — extension manifests (AX-6 schema) + the axes contract over the
channels package: schema validity, adapter parity, validate-extension.sh
end-to-end, strict axis lint, example-config validity."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.channels import ADAPTERS_BY_CHANNEL, load_org_domains
from framework.channels.outlook import OutlookAdapter
from framework.channels.slack import SlackAdapter
from framework.channels.teams import TeamsAdapter

_CHANNELS_DIR = _REPO_ROOT / "framework" / "channels"
_SCHEMA_PATH = _REPO_ROOT / "framework" / "schemas" / \
    "extension-manifest.schema.json"
_VALIDATE_SH = _REPO_ROOT / "cabinet" / "scripts" / "validate-extension.sh"
_EXAMPLE = _REPO_ROOT / "instance/config" / "channels.yml.example"

ADAPTERS = {
    "teams": TeamsAdapter,
    "outlook": OutlookAdapter,
    "slack": SlackAdapter,
}


def _manifest(name: str) -> dict:
    return json.loads(
        (_CHANNELS_DIR / "manifests" / (name + ".json")).read_text())


def _schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


# ---------------------------------------------------------------------------
# Schema conformance + adapter parity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_manifest_validates_against_the_ax6_schema(name):
    jsonschema.validate(_manifest(name), _schema())


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_manifest_mirrors_the_adapter_contract(name):
    manifest = _manifest(name)
    adapter = ADAPTERS[name]
    assert manifest["name"] == adapter.name == name
    assert manifest["kind"] == "channel"
    assert manifest["undo_contract"] == str(adapter.undo_contract)
    assert set(manifest["action_types"]) == {
        adapter.internal_action_type, adapter.external_action_type}
    assert set(manifest["risk_classes"]) == \
        {"external_comms", "internal_comms"}
    # every declared capability has an entrypoint, and nothing more
    assert set(manifest["entrypoints"]) == set(adapter.capabilities)
    for rel in manifest["entrypoints"].values():
        assert not Path(rel).is_absolute()
        assert (_CHANNELS_DIR / rel).is_file(), rel


def test_risk_classes_stay_in_the_matrix_vocabulary():
    from framework.authority.matrix import RISK_CLASSES
    for name in ADAPTERS:
        assert set(_manifest(name)["risk_classes"]) <= set(RISK_CLASSES)


def test_registry_matches_shipped_manifests():
    assert set(ADAPTERS_BY_CHANNEL) == set(ADAPTERS)


def test_email_undo_contract_is_none():
    # spec §4: email = none; the inverse-required rule keys off this string.
    assert _manifest("outlook")["undo_contract"] == "none"
    assert _manifest("teams")["undo_contract"].startswith("delete_window(")
    assert _manifest("slack")["undo_contract"].startswith("delete_window(")


# ---------------------------------------------------------------------------
# End-to-end: each shipped manifest+module passes validate-extension.sh
# (manifest schema + entrypoint containment + STRICT axis lint)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_validate_extension_gate_passes_end_to_end(name, tmp_path):
    manifest = _manifest(name)
    ext = tmp_path / ("%s-ext" % name)
    ext.mkdir()
    (ext / "manifest.json").write_text(json.dumps(manifest))
    for rel in set(manifest["entrypoints"].values()):
        shutil.copy(_CHANNELS_DIR / rel, ext / rel)
    r = subprocess.run(
        ["bash", str(_VALIDATE_SH), str(ext)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# The axes contract over the whole package: adapters are extensions — ZERO
# axis branches, no allowlist entry needed (spec §6.1/§6.4)
# ---------------------------------------------------------------------------

def test_channels_package_passes_the_axis_linter_strict():
    from framework.tests.test_axes_contract import scan_tree
    violations = scan_tree(_CHANNELS_DIR, rel_to=_REPO_ROOT)
    assert violations == [], violations


# ---------------------------------------------------------------------------
# The shipped instance/config/channels.yml.example is loader-valid
# ---------------------------------------------------------------------------

def test_channels_yml_example_loads_through_the_fail_closed_loader(tmp_path):
    d = tmp_path / "instance/config"
    d.mkdir(parents=True)
    shutil.copy(_EXAMPLE, d / "channels.yml")
    domains = load_org_domains(root=tmp_path)
    assert domains == {"example.com", "example.org"}
