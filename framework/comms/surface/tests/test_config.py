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
    # Captain ratified briefing-as-card TRUE on 2026-07-11 (one-voice reset).
    # This pinned False until 2026-07-26, which is why the ratified experience
    # never reached a fresh cabinet: the egg deletes the instance file that
    # carried it. Pinned to the ratified value — it must still fail on drift.
    assert cfg["briefing_card"] is True


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


def test_pin_mode_defaults_to_overview_and_fails_closed(monkeypatch, tmp_path):
    # Captain ratified pin_mode "overview" on 2026-07-10. This pinned "adopt"
    # until 2026-07-26 — the ratified value lived only in the instance file the
    # egg deletes, so a fresh cabinet got the pre-ruling pin. Pinned to the
    # ratified design; a drift back to "adopt" must still fail here.
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH",
                       str(tmp_path / "absent.yml"))
    assert scfg.load()["pin_mode"] == "overview"   # foundation default
    p = tmp_path / "comms-surface.yml"
    p.write_text("pin_mode: sideways\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    assert scfg.load()["pin_mode"] == "overview"   # unknown value → ratified


def test_pin_mode_adopt_stays_selectable(monkeypatch, tmp_path):
    """The original design is opt-in-able, not deleted — the flip of the
    default (2026-07-26) must not strand a deployment that wants it back."""
    p = tmp_path / "comms-surface.yml"
    p.write_text("pin_mode: adopt\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    assert scfg.load()["pin_mode"] == "adopt"
    monkeypatch.setenv("CABINET_SURFACE_PIN_MODE", "overview")
    assert scfg.load()["pin_mode"] == "overview"   # env still wins over file


def test_explicit_briefing_card_false_is_honoured(monkeypatch, tmp_path):
    """The documented opt-out must survive the ratified-true default. `or`
    coalescing (pre-2026-07-26) treated an explicit falsy value as ABSENT, so
    flipping the default would have silently re-armed the card for anyone who
    wrote `briefing_card: false` — the literal value the .example twin ships."""
    p = tmp_path / "comms-surface.yml"
    p.write_text("briefing_card: false\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    assert scfg.load()["briefing_card"] is False
    monkeypatch.setenv("CABINET_BRIEFING_CARD", "0")
    assert scfg.load()["briefing_card"] is False   # env opt-out too
    monkeypatch.setenv("CABINET_BRIEFING_CARD", "1")
    assert scfg.load()["briefing_card"] is True


def test_pin_mode_overview_binds_from_yaml_and_env(monkeypatch, tmp_path):
    p = tmp_path / "comms-surface.yml"
    p.write_text("pin_mode: overview\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    assert scfg.load()["pin_mode"] == "overview"   # the ratified knob (2026-07-10)
    monkeypatch.setenv("CABINET_SURFACE_PIN_MODE", "adopt")
    assert scfg.load()["pin_mode"] == "adopt"      # env wins over the file


def test_captain_tz_env_unset_resolves_via_platform_yml(tmp_path, monkeypatch):
    """TZ unification (2026-07-18): the engine's clock follows THE one
    resolver (platform.yml captain_timezone) when the env override is absent
    — same contract as the gate, so horizon math never disagrees with
    quiet-hours math."""
    import framework.env as fenv
    monkeypatch.delenv("CABINET_CAPTAIN_TZ", raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    cfg = tmp_path / "instance/config"
    cfg.mkdir(parents=True)
    (cfg / "platform.yml").write_text(
        "captain_timezone: Asia/Tokyo\n", encoding="utf-8")
    saved = fenv._captain_timezone_cache
    fenv._captain_timezone_cache = None
    try:
        assert str(scfg.captain_tz()) == "Asia/Tokyo"
    finally:
        fenv._captain_timezone_cache = saved


def test_next_briefing_env_unset_reads_platform_yml_slots(tmp_path, monkeypatch):
    """SoT (2026-07-18): the engine's wrong-by-tomorrow horizon reads
    platform.yml `briefing_times` when the env override is absent."""
    from datetime import datetime, timezone
    import framework.env as fenv
    monkeypatch.delenv("CABINET_BRIEFING_TIMES", raising=False)
    monkeypatch.delenv("CABINET_CAPTAIN_TZ", raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    cfg = tmp_path / "instance/config"
    cfg.mkdir(parents=True)
    (cfg / "platform.yml").write_text(
        'captain_timezone: UTC\nbriefing_times: ["05:10", "17:40"]\n',
        encoding="utf-8")
    saved_tz = fenv._captain_timezone_cache
    saved_bt = fenv._briefing_times_cache
    fenv._captain_timezone_cache = None
    fenv._briefing_times_cache = None
    try:
        noon = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
        nxt = scfg.next_briefing(noon)           # noon UTC → 17:40 today
        assert (nxt.hour, nxt.minute) == (17, 40)
    finally:
        fenv._captain_timezone_cache = saved_tz
        fenv._briefing_times_cache = saved_bt


def test_captain_tz_unloadable_env_falls_through_to_resolver(tmp_path, monkeypatch):
    """P2 (fix 2026-07-18): an unloadable env CABINET_CAPTAIN_TZ (leaked YAML
    quotes) falls through to THE resolver instead of a silent UTC — same
    contract as gate._captain_tz, so the engine's clock never disagrees."""
    import framework.env as fenv
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", '"Europe/Berlin"')   # quotes leaked
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    cfg = tmp_path / "instance/config"
    cfg.mkdir(parents=True)
    (cfg / "platform.yml").write_text(
        "captain_timezone: Asia/Tokyo\n", encoding="utf-8")
    saved = fenv._captain_timezone_cache
    fenv._captain_timezone_cache = None
    try:
        assert str(scfg.captain_tz()) == "Asia/Tokyo"
    finally:
        fenv._captain_timezone_cache = saved


def test_next_briefing_env_out_of_range_slot_does_not_crash(monkeypatch):
    """P4b (fix 2026-07-18): an out-of-range env slot is dropped by the shared
    normalizer; the engine keeps the valid sibling instead of silently ignoring
    the bad one and drifting."""
    from datetime import datetime, timezone
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", "UTC")
    monkeypatch.setenv("CABINET_BRIEFING_TIMES", "25:99,05:10")
    noon = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    nxt = scfg.next_briefing(noon)               # noon UTC → tomorrow 05:10
    assert (nxt.hour, nxt.minute) == (5, 10)
