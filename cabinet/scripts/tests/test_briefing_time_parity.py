"""Briefing-time SOURCE-OF-TRUTH parity (silent-defaults audit C, 2026-07-18).

ONE key — instance/config/platform.yml `briefing_times` (framework.env.
briefing_times(); fleet default 07:30,19:30) — and every surface that speaks
a briefing time must agree with it:

  * the RENDERED com.cabinet.frontdoor-briefing plist (generate-plists.py
    stamps StartCalendarInterval from the key — fixture-verified with a
    DIVERGENT services.yml row to prove the key wins, and repo-verified with
    a real full-fleet render);
  * the cabinet/services.yml calendar row (the documented no-config fallback
    MIRROR — drift fails here);
  * the watchdog registry's BRIEF_* slot constants (instance/config/
    watchdog.yml `briefing:` block — its no-PyYAML survival parser cannot
    import the resolver, so parity is pinned from the outside);
  * the prose surfaces that tell officers/the Captain when briefings happen
    (preset + instance cos.md, the /cabinet-briefing command, the deploy
    runbook, the preset coo quarter-close line) — any HH:MM on a
    briefing-mentioning line must be one of the declared slots (this is the
    rot class that shipped 07:00/19:00 for weeks against a 07:30/19:30
    fleet);
  * the .example twins: platform.yml.example must ship `briefing_times` at
    the REAL fleet default, and comms-surface.yml.example must document
    every framework DEFAULTS key (pins the once-missing hard_all_cap).

A divergence anywhere FAILS — that is the point. If this test fails after
you deliberately changed the schedule: change platform.yml `briefing_times`,
re-run generate-plists.py, and re-sync the two mirrors + the prose lines it
names.

NOTE: memory/golden-evals/eval-006-briefings-on-schedule.md carries the same
prose but is germline-locked (schg) — its fix is staged at
patches/germline-eval-006-briefing-times-2026-07-18.patch; add it to
PROSE_FILES once the Captain lands that patch.

Hermetic: fixture renders run in tmp CABINET_ROOT via subprocess (argument
lists, no shell); the repo render writes to a tmp --output-dir (the script
refuses ~/Library/LaunchAgents and never touches launchctl).
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import yaml

import framework.env as fenv
from framework.comms.surface import config as surface_config
from framework.watchdog import registry

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "cabinet" / "scripts" / "generate-plists.py"
BRIEFING_PLIST = "com.cabinet.frontdoor-briefing.plist"

# Every tracked prose surface that states briefing wall-clock times. On any
# line that mentions briefings, every HH:MM token must be a declared slot.
PROSE_FILES = (
    "presets/portfolio/agents/cos.md",
    "instance/agents/cos.md",
    ".claude/commands/cabinet-briefing.md",
    "cabinet/docs/mac-mini-deploy-runbook.md",
    "presets/developer/agents/coo.md",
    "presets/work/agents/coo.md",
)

_TIME_TOKEN = re.compile(r"\b(\d{1,2}:\d{2})\b")


def _normalize(values) -> tuple:
    """services.yml/platform.yml shapes → canonical ("HH:MM", ...)."""
    out = []
    for v in values:
        slot = fenv._normalize_briefing_slot(v)
        assert slot is not None, f"unnormalizable briefing slot {v!r}"
        if slot not in out:
            out.append(slot)
    return tuple(out)


def declared_times() -> tuple:
    """What THIS repo's platform.yml declares (or the fleet default when the
    key is absent) — the expectation every other surface is held to. Derived
    from the on-disk YAML, never a hardcoded deployment literal."""
    cfg = REPO_ROOT / "instance" / "config" / "platform.yml"
    if cfg.exists():
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        raw = data.get("briefing_times")
        if raw is not None:
            return _normalize(raw.split(",") if isinstance(raw, str) else raw)
    return tuple(fenv._BRIEFING_TIMES_DEFAULT)


def _render(root: Path, out_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    # The render must be config-driven, not inherited-env-driven.
    env.pop("CABINET_BRIEFING_TIMES", None)
    env.pop("CABINET_WATCHDOG_CONFIG", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(out_dir)],
        capture_output=True, text=True, env=env, timeout=120,
    )


def _calendar(plist_path: Path) -> tuple:
    with open(plist_path, "rb") as fh:
        pl = plistlib.load(fh)
    cal = pl.get("StartCalendarInterval")
    assert cal, f"{plist_path.name} has no StartCalendarInterval"
    return tuple(f"{e['Hour']:02d}:{e['Minute']:02d}" for e in cal)


def _fixture_root(tmp_path: Path, *, platform_body: "str | None") -> Path:
    root = tmp_path / "root"
    (root / "cabinet").mkdir(parents=True)
    (root / "instance" / "config").mkdir(parents=True)
    # A DIVERGENT briefing calendar (06:00) + a bystander service that must
    # render untouched — proves the stamp overrides exactly one row.
    (root / "cabinet" / "services.yml").write_text(
        "services:\n"
        "  - name: frontdoor-briefing\n"
        "    label: com.cabinet.frontdoor-briefing\n"
        "    kind: daemon\n"
        "    command: bash cabinet/scripts/run-frontdoor-briefing.sh\n"
        "    schedule:\n"
        "      calendar:\n"
        "        - { hour: 6, minute: 0 }\n"
        "  - name: bystander\n"
        "    label: com.cabinet.bystander\n"
        "    kind: cron\n"
        "    command: bash cabinet/cron/bystander.sh\n"
        "    schedule:\n"
        "      calendar:\n"
        "        - { hour: 6, minute: 0 }\n",
        encoding="utf-8")
    if platform_body is not None:
        (root / "instance" / "config" / "platform.yml").write_text(
            platform_body, encoding="utf-8")
    return root


class TestGeneratorStampsFromPlatformYml:
    def test_platform_yml_wins_over_divergent_services_row(self, tmp_path):
        """THE SoT behavior: platform.yml `briefing_times` overrides the
        services.yml calendar row in the rendered plist, with a printed
        provenance line naming the divergence. The bystander service keeps
        its own manifest schedule."""
        root = _fixture_root(
            tmp_path, platform_body='briefing_times: ["08:15", "20:45"]\n')
        out = tmp_path / "out"
        proc = _render(root, out)
        assert proc.returncode == 0, proc.stderr
        assert _calendar(out / BRIEFING_PLIST) == ("08:15", "20:45")
        assert _calendar(out / "com.cabinet.bystander.plist") == ("06:00",)
        assert "stamped from platform.yml briefing_times" in proc.stdout
        assert "source of truth" in proc.stdout      # divergence was named

    def test_absent_key_stamps_fleet_default(self, tmp_path):
        """No platform.yml at all → the fleet default 07:30/19:30 is stamped
        (a clean-room render is schedule-correct with zero config; the
        divergent 06:00 manifest row still loses — one authority)."""
        root = _fixture_root(tmp_path, platform_body=None)
        out = tmp_path / "out"
        proc = _render(root, out)
        assert proc.returncode == 0, proc.stderr
        assert _calendar(out / BRIEFING_PLIST) == ("07:30", "19:30")


class TestRepoParity:
    def test_rendered_plist_matches_declared_times(self, tmp_path):
        """The REAL full-fleet render (this is also the lane's required
        generate-plists smoke run): the briefing plist must carry exactly the
        declared slots."""
        out = tmp_path / "out"
        proc = _render(REPO_ROOT, out)
        assert proc.returncode == 0, proc.stderr
        assert _calendar(out / BRIEFING_PLIST) == declared_times()

    def test_services_yml_mirror_matches(self):
        data = yaml.safe_load(
            (REPO_ROOT / "cabinet" / "services.yml").read_text(encoding="utf-8"))
        row = next(s for s in data["services"]
                   if s.get("label") == "com.cabinet.frontdoor-briefing")
        cal = row["schedule"]["calendar"]
        mirror = _normalize(
            f"{e['hour']:02d}:{e['minute']:02d}" for e in cal)
        assert mirror == declared_times(), (
            "cabinet/services.yml frontdoor-briefing calendar row has drifted "
            "from platform.yml `briefing_times` — re-sync the fallback mirror")

    def test_watchdog_registry_slots_match(self):
        """instance/config/watchdog.yml `briefing:` (via the registry's
        import-time no-PyYAML parse) must expect the SAME slots the fleet
        fires at — a drifted watchdog would false-alarm (or sleep through)
        every real briefing."""
        watchdog = _normalize((
            f"{registry.BRIEF_AM_HOUR:02d}:{registry.BRIEF_MINUTE:02d}",
            f"{registry.BRIEF_PM_HOUR:02d}:{registry.BRIEF_MINUTE:02d}",
        ))
        assert watchdog == declared_times(), (
            "instance/config/watchdog.yml briefing block has drifted from "
            "platform.yml `briefing_times` — update am_hour/pm_hour/minute")

    def test_prose_surfaces_speak_declared_times_only(self):
        declared = set(declared_times())
        offenders = []
        # The egg export strips instance/* prose; the preset twin
        # (presets/portfolio/agents/cos.md, also in PROSE_FILES) carries the
        # same briefing-time parity invariant, so an absent instance prose file
        # on a clean/public checkout is tolerated — the invariant still runs
        # full-teeth against the preset twin. The source instance ships
        # instance/agents/cos.md ⇒ it is checked there (no tolerance fires). A
        # missing NON-instance prose file (or an absent preset twin) is real
        # rot and still fails loudly.
        preset_twin = REPO_ROOT / "presets/portfolio/agents/cos.md"
        for rel in PROSE_FILES:
            p = REPO_ROOT / rel
            if not p.exists() and rel.startswith("instance/") and preset_twin.exists():
                continue
            assert p.exists(), f"{rel} is tracked prose — missing from checkout"
            for n, line in enumerate(
                    p.read_text(encoding="utf-8").splitlines(), 1):
                if "riefing" not in line:       # Briefing / briefings
                    continue
                for tok in _TIME_TOKEN.findall(line):
                    slot = fenv._normalize_briefing_slot(tok)
                    if slot is not None and slot not in declared:
                        offenders.append(f"{rel}:{n}: {tok} (line: {line.strip()[:90]})")
        assert not offenders, (
            "briefing-time prose has drifted from platform.yml "
            "`briefing_times` " + str(sorted(declared)) + ":\n  "
            + "\n  ".join(offenders))


class TestExampleTwins:
    def test_platform_example_ships_the_fleet_default(self):
        data = yaml.safe_load(
            (REPO_ROOT / "instance" / "config" / "platform.yml.example")
            .read_text(encoding="utf-8"))
        raw = data.get("briefing_times")
        assert raw is not None, (
            "platform.yml.example must ship `briefing_times` — a fresh hatch "
            "inherits its config surface from the example twin")
        assert _normalize(raw) == tuple(fenv._BRIEFING_TIMES_DEFAULT), (
            "the example twin must carry the REAL fleet default 07:30/19:30")
        assert isinstance(data.get("captain_timezone"), str) and \
            data["captain_timezone"].strip(), (
            "platform.yml.example must ship `captain_timezone` (the resolver "
            "falls back to UTC LOUDLY without it)")

    def test_comms_surface_example_documents_every_default(self):
        data = yaml.safe_load(
            (REPO_ROOT / "instance" / "config" / "comms-surface.yml.example")
            .read_text(encoding="utf-8"))
        keys = set(data or {})
        pacing = data.get("pacing")
        if isinstance(pacing, dict):
            keys |= set(pacing)
        missing = set(surface_config.DEFAULTS) - keys
        assert not missing, (
            "comms-surface.yml.example is missing framework DEFAULTS keys "
            f"{sorted(missing)} — every knob must be discoverable in the "
            "example twin (this pin caught hard_all_cap once already)")
