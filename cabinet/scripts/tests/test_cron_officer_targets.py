"""W10 (2026-07-09) — cron trigger targets must exist on the live roster.

research-sweep.sh fired `trigger_send cro` and backlog-refine.sh
`trigger_send cpo` long after both seats were retired (live roster:
cos + lane CEOs + comms-officer) — every run XADDed into a dead officer
stream and the work silently never happened. These tests pin the repair:

  * every literal `trigger_send <officer>` in cabinet/cron/*.sh names an
    officer that exists in the platform.yml `officers:` block (env-var
    indirection like "$TARGET_OFFICER" is exempt — its default is checked
    separately);
  * the two repaired scripts default their target env vars to a live
    officer, so a bare launchd run cannot regress to a dead stream.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CRON = _REPO / "cabinet" / "cron"
_PLATFORM = _REPO / "instance" / "config" / "platform.yml"

# trigger_send <target> — target is the first argv after the verb.
_SEND_RE = re.compile(r"\btrigger_send\s+(\"?\$?\{?[A-Za-z_][A-Za-z0-9_-]*\}?\"?)")
_DEFAULT_RE = re.compile(
    r"TARGET_OFFICER=\"\$\{[A-Z_]+:-([a-z][a-z0-9-]*)\}\"")


def live_roster() -> set[str]:
    """Officer keys from the LIVE (uncommented) officers: block. The spawn
    parser greps inline-YAML lines, so we mirror that: `  key: { type: ...`."""
    roster: set[str] = set()
    in_block = False
    for line in _PLATFORM.read_text().splitlines():
        if re.match(r"^officers:\s*$", line):
            in_block = True
            continue
        if in_block:
            m = re.match(r"^  ([a-z][a-z0-9-]*):\s*\{", line)
            if m:
                roster.add(m.group(1))
            elif line.strip() and not line.startswith("#") and not line.startswith("  "):
                in_block = False
    return roster


def _literal_targets(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        # Only real invocation lines — not comments, error prose (echo/FATAL
        # "trigger_send not defined/failed"), or the declare -f guard.
        if (stripped.startswith("#") or "echo" in line
                or "declare -f" in line or "FATAL" in line):
            continue
        for m in _SEND_RE.finditer(line):
            tok = m.group(1).strip('"')
            if tok.startswith("$"):
                continue  # env-var indirection; default pinned separately
            out.append(tok)
    return out


def test_roster_parses_and_has_the_chair():
    roster = live_roster()
    assert "cos" in roster, f"roster parse broke: {roster}"


@pytest.mark.parametrize("script", sorted(_CRON.glob("*.sh")),
                         ids=lambda p: p.name)
def test_no_cron_targets_a_retired_officer(script):
    roster = live_roster()
    for target in _literal_targets(script.read_text()):
        assert target in roster, (
            f"{script.name} sends triggers to '{target}' which is not on the "
            f"live roster {sorted(roster)} — a dead stream (the exact W10 bug)")


@pytest.mark.parametrize("script,envvar", [
    ("research-sweep.sh", "RESEARCH_SWEEP_OFFICER"),
    ("backlog-refine.sh", "BACKLOG_REFINE_OFFICER"),
])
def test_repaired_scripts_default_to_a_live_officer(script, envvar):
    text = (_CRON / script).read_text()
    assert envvar in text
    m = _DEFAULT_RE.search(text)
    assert m, f"{script}: TARGET_OFFICER default pattern missing"
    assert m.group(1) in live_roster()


def test_repaired_scripts_are_scheduled():
    import yaml
    services = yaml.safe_load(
        (_REPO / "cabinet" / "services.yml").read_text())["services"]
    by_name = {s.get("name"): s for s in services}
    for name in ("research-sweep", "backlog-refine"):
        row = by_name.get(name)
        assert row and not row.get("disabled"), f"{name} row missing/disabled"
        assert row.get("schedule", {}).get("calendar"), f"{name} unscheduled"
