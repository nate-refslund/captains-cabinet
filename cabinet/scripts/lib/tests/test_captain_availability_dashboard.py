"""The dashboard's availability write path — pinned against the command the
dashboard action ACTUALLY runs, not against a description of it.

Captain direction 2026-07-26: the dial must be adjustable from the dashboard,
not only from Telegram. The dashboard is TypeScript and cannot be unit-tested
from here, so this file does the thing that matters instead: it EXTRACTS the
command template out of ``cabinet/dashboard/src/actions/config.ts``, renders it
with a value, and executes it. Every arm therefore fails if the action stops
running the store's own recorder — if it grows a ``sed``, if it points at
``instance/config/platform.yml``, if it drops ``--source dashboard``, or if the
template disappears entirely. A test that merely ran the CLI would pass just as
happily with no dashboard write path at all; this one cannot.

What each arm pins:

  * the action writes through ``captain_availability.py`` — the module that
    owns the store, the grammar, the range check and the append-only rule —
    and NOT through platform.yml, which is a marker-managed generator output
    with exactly one writer;
  * that command really does land a valid adjustment row, with ``source:
    dashboard`` as its provenance, and the resolver every consumer reads then
    serves it (``framework.env.captain_availability()`` → ``adjusted``);
  * a value the dial cannot hold — out of range, or fractional — exits
    non-zero and writes NOTHING. Refuse, don't round;
  * ``away`` survives the whole path as a real ruling of 0 min/day, not as an
    absence. The degenerate end has to work or the control cannot say "leave me
    alone";
  * the receipt pattern the action requires before it reports success actually
    matches what the writer prints — and does NOT match the mock-exec string
    that once let a dashboard save be reported as done with nothing on disk;
  * the row's field names are the ones the dashboard's own reader
    (``cabinet/dashboard/src/lib/config.ts``) looks for, so the write and the
    Settings read cannot drift apart.

The interpreter is swapped for ``sys.executable`` before running: this suite is
invoked as ``python3 -m pytest`` in CI, and whether a runner image happens to
carry a ``python3.12`` binary is not a property of the dashboard action worth
reding a build over. The template's own interpreter token is asserted
separately.

Run: cd cabinet/scripts/lib && python3.12 -m pytest tests/test_captain_availability_dashboard.py -q
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
ACTION_TS = REPO / "cabinet/dashboard/src/actions/config.ts"
READER_TS = REPO / "cabinet/dashboard/src/lib/config.ts"
WRITER_REL = "cabinet/scripts/lib/captain_availability.py"


# ---------------------------------------------------------------------------
# extraction — the binding between this suite and the live dashboard action
# ---------------------------------------------------------------------------
def _action_source() -> str:
    if not ACTION_TS.is_file():
        pytest.fail(f"{ACTION_TS} is missing — the dashboard action surface moved")
    return ACTION_TS.read_text(encoding="utf-8")


def _writer_rel(src: str) -> str:
    m = re.search(r"const AVAILABILITY_WRITER = cabinetPath\('([^']+)'\)", src)
    if not m:
        pytest.fail(
            "no AVAILABILITY_WRITER path in cabinet/dashboard/src/actions/config.ts — "
            "the dashboard has no availability write path, or it stopped naming the "
            "module that owns the store")
    return m.group(1)


def _command_template(src: str) -> str:
    tpls = re.findall(r"`([^`]*--source dashboard[^`]*)`", src)
    if len(tpls) != 1:
        pytest.fail(
            f"expected exactly one dashboard availability command template in "
            f"{ACTION_TS}, found {len(tpls)}")
    return tpls[0]


def _receipt_pattern(src: str) -> str:
    m = re.search(r"const AVAILABILITY_RECEIPT = /(.+)/\s*$", src, re.M)
    if not m:
        pytest.fail(
            "no AVAILABILITY_RECEIPT guard in the dashboard action — without it a "
            "mock or no-op exec reports a save that never reached disk")
    return m.group(1).replace(r"\/", "/")


def _argv(value: str) -> list[str]:
    """The action's own command, rendered with `value` and made runnable."""
    src = _action_source()
    template = _command_template(src)
    rel = _writer_rel(src)
    assert rel == WRITER_REL, (
        f"the dashboard writes availability through {rel!r}; the module that owns "
        f"the store is {WRITER_REL!r}")
    assert not re.search(r"\bsed\b", template), (
        f"the dashboard availability command runs sed: {template!r}")
    assert "platform.yml" not in template, (
        f"the dashboard availability command targets platform.yml, which has one "
        f"writer and is not where the served value lives: {template!r}")

    def _sub(m: "re.Match[str]") -> str:
        expr = m.group(1).strip()
        if expr == "AVAILABILITY_WRITER":
            return str(REPO / rel)
        if expr.endswith(".cli"):
            return value
        pytest.fail(f"unrecognised placeholder ${{{expr}}} in {template!r}")
        return ""  # unreachable; pytest.fail raises

    rendered = re.sub(r"\$\{([^}]+)\}", _sub, template)
    assert "${" not in rendered, f"unsubstituted placeholder left in {rendered!r}"
    argv = shlex.split(rendered)
    assert argv[0] == "python3.12", (
        f"the action's interpreter token is {argv[0]!r}; the repo pins python3.12 "
        f"and the writer's own shebang is python3.12")
    argv[0] = sys.executable
    return argv


def _run(value: str, store: Path) -> "subprocess.CompletedProcess[str]":
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(REPO)
    env["CABINET_CAPTAIN_AVAILABILITY_FILE"] = str(store)
    return subprocess.run(_argv(value), capture_output=True, text=True,
                          env=env, cwd=str(REPO))


def _reading(store: Path, monkeypatch) -> dict:
    """What every consumer sees — the resolver, not a second parse of the file."""
    monkeypatch.setenv("CABINET_ROOT", str(REPO))
    monkeypatch.setenv("CABINET_CAPTAIN_AVAILABILITY_FILE", str(store))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework import env
    env._captain_availability_cache = None
    try:
        return env.captain_availability()
    finally:
        env._captain_availability_cache = None


@pytest.fixture
def store(tmp_path) -> Path:
    return tmp_path / "captain-availability.yml"


# ---------------------------------------------------------------------------
# the action writes through the store owner, never a platform.yml sed
# ---------------------------------------------------------------------------
def test_the_action_runs_the_store_writer_with_dashboard_provenance():
    src = _action_source()
    template = _command_template(src)
    assert WRITER_REL == _writer_rel(src)
    assert " set " in template
    assert "--source dashboard" in template, (
        "the row must carry where it came from; 'adjusted' is the precedence "
        "level, dashboard is the provenance")
    assert not re.search(r"\bsed\b", template)
    assert "platform.yml" not in template


def test_the_action_gates_on_auth_before_anything_else():
    """A Server Action is a global action-ID POST endpoint and middleware never
    covers action dispatch, so the guard has to be the first statement — not the
    first statement inside the try."""
    src = _action_source()
    m = re.search(r"export async function updateCaptainAvailability\([^)]*\)\s*\{\n",
                  src)
    assert m, "no updateCaptainAvailability action in the dashboard"
    body = src[m.end():]
    first = next(line for line in body.splitlines()
                 if line.strip() and not line.strip().startswith(("//", "/*", "*")))
    assert "requireDashboardAuth" in first, (
        f"first statement of updateCaptainAvailability is {first.strip()!r}")
    action = body.split("\nexport async function ", 1)[0]
    assert not re.search(r"\bsed\b", action)
    assert "platform.yml" not in action


# ---------------------------------------------------------------------------
# the command writes a valid adjustment row, and the resolver serves it
# ---------------------------------------------------------------------------
def test_the_command_writes_a_valid_adjustment_row(store, monkeypatch):
    proc = _run("part_time", store)
    assert proc.returncode == 0, proc.stderr
    assert store.exists(), "the dashboard command wrote nothing"

    text = store.read_text(encoding="utf-8")
    assert "schema: cabinet.captain-availability/v1" in text
    assert "entries:" in text
    assert "    minutes_per_day: 30\n" in text
    assert "    mode: part_time\n" in text
    assert "    source: dashboard\n" in text
    assert re.search(r"^  - at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", text, re.M)

    got = _reading(store, monkeypatch)
    assert got["minutes_per_day"] == 30
    assert got["mode"] == "part_time"
    assert got["source"] == "adjusted", (
        "the row is in the adjustment store, so the resolver must serve it above "
        "whatever onboarding stamped")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", got["set_at"] or "")


def test_exact_minutes_land_as_the_declared_number(store, monkeypatch):
    assert _run("90", store).returncode == 0
    got = _reading(store, monkeypatch)
    assert got["minutes_per_day"] == 90
    assert got["source"] == "adjusted"


def test_away_is_a_real_ruling_not_an_absence(store, monkeypatch):
    """The degenerate end. 0 min/day is a declaration; UNKNOWN is the absence,
    and a Captain who is 90% elsewhere needs the dashboard to say the first."""
    assert _run("away", store).returncode == 0
    got = _reading(store, monkeypatch)
    assert got["minutes_per_day"] == 0
    assert got["mode"] == "away"
    assert got["source"] == "adjusted"


def test_a_later_write_wins_without_rewriting_the_earlier_one(store, monkeypatch):
    assert _run("part_time", store).returncode == 0
    first = store.read_text(encoding="utf-8")
    assert _run("minimal", store).returncode == 0
    after = store.read_text(encoding="utf-8")
    assert after.startswith(first), "the append rewrote history"
    assert _reading(store, monkeypatch)["minutes_per_day"] == 10


# ---------------------------------------------------------------------------
# refuse, don't round — and write nothing while refusing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["1441", "99999", "90.5", "1.5", "vacation", "-1"])
def test_a_value_the_dial_cannot_hold_writes_nothing(value, store):
    proc = _run(value, store)
    assert proc.returncode != 0, (
        f"{value!r} was accepted: {proc.stdout!r}")
    assert not store.exists(), (
        f"{value!r} was refused but still touched the store")


# ---------------------------------------------------------------------------
# the success guard is wired to what the writer really prints
# ---------------------------------------------------------------------------
def test_the_receipt_guard_matches_the_writer_and_rejects_a_mock(store):
    pattern = _receipt_pattern(_action_source())
    proc = _run("part_time", store)
    assert proc.returncode == 0, proc.stderr
    assert re.search(pattern, proc.stdout), (
        f"the action requires {pattern!r} before reporting success, but the writer "
        f"prints {proc.stdout!r} — the guard would reject every real save")
    # The string lib/docker.ts used to RETURN for a command it declined to run.
    # It rejects now, so this can no longer arrive as stdout — the assertion
    # stays as a ratchet: any output that is not the receipt is not a save.
    assert not re.search(pattern, "mock: command executed")
    assert not re.search(pattern, "")


def test_the_row_carries_the_fields_the_dashboard_reader_looks_for(store):
    """Write and read must not drift: the recorder's field names are the ones
    getCaptainAvailability() reads out of the same file."""
    assert _run("part_time", store).returncode == 0
    reader = READER_TS.read_text(encoding="utf-8")
    for field in ("entries", "minutes_per_day", "mode"):
        assert field in reader, f"the dashboard reader no longer reads {field!r}"
    assert "r.at" in reader, "the dashboard reader no longer reads the row stamp"

    import yaml
    doc = yaml.safe_load(store.read_text(encoding="utf-8"))
    assert isinstance(doc, dict) and isinstance(doc.get("entries"), list)
    assert set(doc["entries"][-1]) == {"at", "minutes_per_day", "mode", "source"}
