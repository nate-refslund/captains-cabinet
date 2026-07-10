"""Instance bindings resolve env → instance yml → quiet defaults, fail-closed."""
from __future__ import annotations

from framework.comms.surface import config as scfg


def test_defaults_are_quiet_and_clean_room_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH",
                       str(tmp_path / "absent.yml"))
    cfg = scfg.load()
    assert cfg["mode"] == "ask-first"
    assert cfg["cap"] == 5
    assert cfg["dashboard_url"] == ""
    assert cfg["briefing_card"] is False


def test_instance_yaml_binds_via_the_env_seam(monkeypatch, tmp_path):
    p = tmp_path / "comms-surface.yml"
    p.write_text(
        "pacing:\n  cap: 3\n  mode: auto-push\n  pileup: 7\n"
        "dashboard_url: https://cab.example\nbriefing_card: true\n",
        encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    cfg = scfg.load()
    assert cfg["cap"] == 3 and cfg["mode"] == "auto-push"
    assert cfg["pileup"] == 7
    assert cfg["dashboard_url"] == "https://cab.example"
    assert cfg["briefing_card"] is True


def test_env_wins_over_instance_yaml(monkeypatch, tmp_path):
    p = tmp_path / "comms-surface.yml"
    p.write_text("pacing:\n  cap: 3\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    monkeypatch.setenv("CABINET_SURFACE_CAP", "2")
    assert scfg.load()["cap"] == 2


def test_corrupt_yaml_and_wild_values_fail_closed(monkeypatch, tmp_path):
    p = tmp_path / "comms-surface.yml"
    p.write_text("::: not yaml {{{", encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    assert scfg.load()["cap"] == 5                 # defaults, never a crash
    monkeypatch.setenv("CABINET_SURFACE_CAP", "9999")
    assert scfg.load()["cap"] == 7                 # clamped to the census cap
    monkeypatch.setenv("CABINET_SURFACE_CAP", "-3")
    assert scfg.load()["cap"] == 1
