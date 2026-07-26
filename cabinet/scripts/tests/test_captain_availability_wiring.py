"""The availability dial's WIRING — every consumer actually reads the dial.

Captain ruling 2026-07-26: onboarding asks how much of his day the cabinet gets,
the answer is a first-class instance value adjustable from his phone, and the
org fits the declared budget — never the reverse. A resolver nothing consumes
would be exactly the machinery-outruns-value failure, so these arms pin the
CONSUMERS, not the resolver (framework/tests/test_env.py owns that):

  * the Captain-seat evidence pack prints the declared budget when there is one
    AND the measured absence when there is not — both ends, because a sensor
    that cannot detect the degenerate case is not a sensor;
  * the pack's absence line SAYS the org does not know, rather than printing a
    zero that would read as a real ruling;
  * the retro's Part 1c (and its byte-parity doctrine-pack twin) carry the
    judge-relative-to-the-budget clause the reviewer needs;
  * the comms-surface pacing cap scales from the budget, keeps its shipped
    default when the budget is UNKNOWN, and never overrides a configured cap;
  * the inbound poller dispatches the verb from its own process, gated on the
    Captain's own chat id, with a fail-open relay.

Hermetic: every pack run points CAPTAIN_SEAT_ROOT at a tmp tree and shadows
`redis-cli` with a stub that connects to nothing, so no live store, control
plane or network is touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PACK = REPO / "cabinet/scripts/meta-cognition/captain-seat-pack.sh"
RETRO_SKILL = REPO / "memory/skills/cross-officer-retro.md"
PACK_TWIN = REPO / "packs/doctrine-pack/skills/cross-officer-retro/SKILL.md"
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"

ABSENCE = ("no declared availability — the org does not know how much of the "
           "captain it is entitled to")


def _run_pack(seat_root: Path, scratch: Path) -> str:
    """The pack, read-only, against a tmp root in a rebuilt environment."""
    shim = scratch / "bin"
    shim.mkdir(parents=True, exist_ok=True)
    redis = shim / "redis-cli"
    redis.write_text("#!/bin/sh\nexit 1\n")
    redis.chmod(0o755)
    py = shim / "python3.12"
    py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    py.chmod(0o755)
    home = scratch / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": f"{shim}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(home),
        "LC_ALL": "C.UTF-8",
        "CAPTAIN_SEAT_ROOT": str(seat_root),
        "CAPTAIN_SEAT_WINDOW_DAYS": "14",
    }
    proc = subprocess.run(["bash", str(PACK)], env=env, cwd=str(scratch),
                          capture_output=True, text=True, timeout=120,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _seat_root(tmp_path: Path, store_body: str | None = None,
               platform_body: str | None = None) -> Path:
    root = tmp_path / "seat"
    (root / "instance/config").mkdir(parents=True, exist_ok=True)
    if store_body is not None:
        (root / "instance/config/captain-availability.yml").write_text(
            store_body, encoding="utf-8")
    if platform_body is not None:
        (root / "instance/config/platform.yml").write_text(
            platform_body, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# the Captain-seat pack — both ends
# ---------------------------------------------------------------------------
def test_pack_prints_the_declared_budget(tmp_path):
    root = _seat_root(tmp_path, store_body=(
        "entries:\n"
        "  - at: 2026-01-02T08:00:00Z\n"
        "    minutes_per_day: 120\n"
        "    mode: substantial\n"
        "    source: telegram\n"
        "  - at: 2026-01-09T18:30:00Z\n"
        "    minutes_per_day: 20\n"
        "    mode: part_time\n"
        "    source: telegram\n"))
    out = _run_pack(root, tmp_path / "scratch")
    assert "AVAILABILITY — what he said he has" in out
    assert "declared: 20 min/day  mode=part_time  source=adjusted" in out, out
    assert "set_at: 2026-01-09T18:30:00Z" in out
    assert ABSENCE not in out


def test_pack_reads_the_onboarding_stamp_when_there_is_no_store(tmp_path):
    root = _seat_root(tmp_path, platform_body=(
        "captain_name: Ada\n"
        "captain_availability_minutes_per_day: 30\n"
        "captain_availability_mode: part_time\n"))
    out = _run_pack(root, tmp_path / "scratch")
    assert "declared: 30 min/day  mode=part_time  source=onboarding" in out, out


def test_pack_reports_an_undeclared_budget_as_a_measured_absence(tmp_path):
    """THE degenerate end. An org that never asked must be told so in words —
    a printed 0, or a silent section, would read as a real ruling of zero."""
    root = _seat_root(tmp_path)
    out = _run_pack(root, tmp_path / "scratch")
    assert "AVAILABILITY — what he said he has" in out
    assert ABSENCE in out, out
    assert "declared:" not in out


def test_pack_does_not_write_into_the_tree_it_reads(tmp_path):
    root = _seat_root(tmp_path, store_body=(
        "entries:\n  - at: 2026-01-09T18:30:00Z\n    minutes_per_day: 20\n"))
    store = root / "instance/config/captain-availability.yml"
    before = store.read_bytes()
    _run_pack(root, tmp_path / "scratch")
    assert store.read_bytes() == before


# ---------------------------------------------------------------------------
# the retro contract (and its byte-parity twin)
# ---------------------------------------------------------------------------
def test_part_1c_judges_cost_relative_to_the_declared_budget():
    text = RETRO_SKILL.read_text(encoding="utf-8")
    assert "Judge cost RELATIVE to the declared availability in the pack's " \
           "AVAILABILITY section" in text
    assert "The org fits the declared budget, never the reverse." in text
    assert "itself pack evidence" in text


def test_doctrine_pack_twin_carries_the_same_clause():
    """The pack copy is what a pack INSTALLER gets; a canonical-only edit ships
    stale doctrine to everyone outside this repo."""
    assert "Judge cost RELATIVE to the declared availability" in \
        PACK_TWIN.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the comms-surface pacing consumer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("minutes,expect_cap", [
    (0, 1),        # away — the floor
    (10, 1),       # minimal
    (30, 2),       # part-time
    (120, 3),      # substantial
    (480, 5),      # full-time — the shipped default
])
def test_pacing_cap_scales_from_the_declared_budget(tmp_path, monkeypatch,
                                                    minutes, expect_cap):
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework import env
    from framework.comms.surface import config as surface_config

    store = tmp_path / f"avail-{minutes}.yml"
    store.write_text(f"entries:\n  - at: 2026-07-26T00:00:00Z\n"
                     f"    minutes_per_day: {minutes}\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_CAPTAIN_AVAILABILITY_FILE", str(store))
    monkeypatch.delenv("CABINET_SURFACE_CAP", raising=False)
    saved = env._captain_availability_cache
    env._captain_availability_cache = None
    try:
        assert surface_config.load(instance={})["cap"] == expect_cap
    finally:
        env._captain_availability_cache = saved


def test_unknown_budget_leaves_the_shipped_cap_untouched(tmp_path, monkeypatch):
    """UNKNOWN must change NOTHING — a consumer that narrowed on absence would
    be inventing a budget nobody declared."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework import env
    from framework.comms.surface import config as surface_config

    monkeypatch.setenv("CABINET_CAPTAIN_AVAILABILITY_FILE",
                       str(tmp_path / "absent.yml"))
    monkeypatch.delenv("CABINET_SURFACE_CAP", raising=False)
    saved = env._captain_availability_cache
    env._captain_availability_cache = None
    try:
        assert surface_config.load(instance={})["cap"] == \
            surface_config.DEFAULTS["cap"]
    finally:
        env._captain_availability_cache = saved


def test_a_configured_cap_always_wins_over_the_budget(tmp_path, monkeypatch):
    """A configured value is a RULING. The budget scales the default, never
    overrides a deployment that already decided."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework import env
    from framework.comms.surface import config as surface_config

    store = tmp_path / "avail.yml"
    store.write_text("entries:\n  - at: 2026-07-26T00:00:00Z\n"
                     "    minutes_per_day: 0\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_CAPTAIN_AVAILABILITY_FILE", str(store))
    monkeypatch.delenv("CABINET_SURFACE_CAP", raising=False)
    saved = env._captain_availability_cache
    env._captain_availability_cache = None
    try:
        assert surface_config.load(instance={"pacing": {"cap": 6}})["cap"] == 6
        env._captain_availability_cache = None
        assert surface_config.load(
            instance={"availability_pacing": False})["cap"] == \
            surface_config.DEFAULTS["cap"]
    finally:
        env._captain_availability_cache = saved


def test_every_surface_default_is_documented_in_the_example_twin():
    """The parity pin the availability_pacing knob has to satisfy: a knob the
    example twin never mentions is undiscoverable."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import yaml
    from framework.comms.surface import config as surface_config

    data = yaml.safe_load(
        (REPO / "instance/config/comms-surface.yml.example")
        .read_text(encoding="utf-8"))
    keys = set(data or {})
    if isinstance(data.get("pacing"), dict):
        keys |= set(data["pacing"])
    assert "availability_pacing" in keys
    assert not set(surface_config.DEFAULTS) - keys


# ---------------------------------------------------------------------------
# the phone dispatch branch
# ---------------------------------------------------------------------------
def test_poller_dispatches_the_verb_captain_gated_and_fails_open():
    """Text-scan of the poller's dispatch chain: the branch must exist, be
    gated on the Captain's own id like every sibling branch, and relay on
    failure so a real message is never silently eaten."""
    text = POLLER.read_text(encoding="utf-8")
    assert "def is_availability_command(" in text
    assert "def availability_command_reply(" in text
    assert 'elif frm == str(captain) and is_availability_command(text):' in text
    branch = text.split(
        'elif frm == str(captain) and is_availability_command(text):', 1)[1]
    branch = branch.split("elif frm == str(captain) and text:", 1)[0]
    assert 'kind="availability"' in branch, "the DM must be archived"
    assert '"kind": "availability-command"' in branch, "flight-recorder row"
    assert "if not sent:" in branch and "deliver(text" in branch, (
        "a record-or-send failure must fall OPEN to the Chair relay")
