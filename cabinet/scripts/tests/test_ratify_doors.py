"""THREE DOORS, ONE WRITER — asserted mechanically, not by reading the code.

The tap's whole shape is that ratification happens in exactly one place and
every door calls it. Three arms hold that up:

  * each door, driven end to end, produces the SAME two files and one receipt;
  * no door composes the outcome YAML — the live filename appears in neither
    the web action nor the chat verb's route, which is checkable and checked;
  * the SUPERSEDED TWIN delegates. `org-runtime outcomes ratify` used to write
    SQLite and an `outcome.ratified` store row and never touch the one file
    the mission compiler reads, so "ratified" there activated nothing. Two
    ratify verbs is a dead twin, and this arm is what keeps it one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from framework.onboarding import genesis            # noqa: E402

ANSWERS = {"version": 1, "cabinet": {"id": "acme-hq"}}

#: The live mission file. Written out HERE rather than imported from the
#: writer, so the invariant arms below fail for the reason the invariant names
#: — a door that composes YAML, or a twin that never touches this file — and
#: not because a module they do not test is missing. One arm pins the two
#: spellings together so they cannot drift apart.
OUTCOMES_REL = "instance/config/outcomes.yml"
_LIVE_FILE = OUTCOMES_REL.rsplit("/", 1)[-1]


def test_the_live_filename_matches_the_writers():
    from framework.outcomes.ratify import OUTCOMES_REL as writer_rel
    assert writer_rel == OUTCOMES_REL

_WEB_DOOR = _REPO / "cabinet" / "dashboard" / "src" / "actions" / "outcomes.ts"
_CHAT_DOOR = _REPO / "framework" / "frontdoor" / "binder_wire.py"
_TERMINAL_DOOR = _REPO / "cabinet" / "scripts" / "outcome-ratify.sh"


def _card(cid):
    return {"id": cid, "name": "Card %s" % cid, "lane": None,
            "what": "ship it", "why": "asked",
            "proof_expected": "a receipt", "proposed_by": "onboarding-genesis"}


@pytest.fixture
def hatched(tmp_path):
    genesis.merge_proposals([_card("acme-001")], tmp_path, answers=ANSWERS,
                            now="2026-09-01T00:00:00Z")
    return tmp_path


def _env(root: Path) -> dict:
    env = dict(os.environ)
    # A0.4: pin the ledger explicitly — unset, every child writes its own.
    env["CABINET_EVENT_LOG_DIR"] = str(root / "events")
    env["CABINET_ROOT"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _run(argv, root: Path):
    return subprocess.run(argv, cwd=str(_REPO), env=_env(root),
                          capture_output=True, text=True, timeout=180)


def _ledger(root: Path) -> list:
    rows = []
    for log in sorted((root / "events").glob("events-*.jsonl")):
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return [r for r in rows if r["event_type"] == "captain_outcome_ratified"]


def _live_rows(root: Path) -> list:
    return yaml.safe_load((root / OUTCOMES_REL).read_text(encoding="utf-8"))["outcomes"]


# ---------------------------------------------------------------------------
# The terminal door — the shipped wrapper, not a hand-built command line.
# ---------------------------------------------------------------------------
def test_terminal_door_script_ratifies(hatched):
    proc = _run(["bash", str(_TERMINAL_DOOR), "acme-001",
                 "--principal", "uid:501", "--json"], hatched)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["status"] == "ratified"
    row = _live_rows(hatched)[0]
    assert row["ratified_via"] == "terminal" and row["ratified_by"] == "operator"
    assert len(_ledger(hatched)) == 1
    assert _ledger(hatched)[0]["actor"] == "operator"


def test_terminal_door_script_lists(hatched):
    proc = _run(["bash", str(_TERMINAL_DOOR), "--list", "--json"], hatched)
    assert proc.returncode == 0, proc.stderr
    rows = json.loads(proc.stdout.strip().splitlines()[-1])
    assert [r["id"] for r in rows] == ["acme-001"]


def test_terminal_door_pins_the_interpreter():
    """Never a bare `python3`: the officer PATH's python3 is 3.9 on the live
    deployment, and an unpinned interpreter is how a module silently changes
    meaning between the door and the writer."""
    text = _TERMINAL_DOOR.read_text(encoding="utf-8")
    assert "${CABINET_PYTHON:-python3.12}" in text
    body = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    for line in body:
        assert "python3 " not in line, line


# ---------------------------------------------------------------------------
# ONE WRITER — no door composes the outcome YAML.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("door", ["web", "chat", "terminal"])
def test_no_door_composes_the_outcome_file(door):
    path = {"web": _WEB_DOOR, "chat": _CHAT_DOOR, "terminal": _TERMINAL_DOOR}[door]
    assert path.is_file(), "%s does not exist — this grep now checks nothing" % path
    text = path.read_text(encoding="utf-8")
    assert _LIVE_FILE not in text, (
        "%s names the live outcomes file; only framework/outcomes/ratify.py may"
        % path)


def test_every_door_calls_the_one_writer():
    """The other half: absent this, the grep above passes on a door that does
    nothing at all."""
    assert "framework.outcomes.ratify" in _WEB_DOOR.read_text(encoding="utf-8")
    assert "framework.outcomes.ratify" in _TERMINAL_DOOR.read_text(encoding="utf-8")
    assert "from framework.outcomes import ratify" in _CHAT_DOOR.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The superseded twin.
# ---------------------------------------------------------------------------
def test_store_ratify_delegates(hatched):
    """`org-runtime outcomes ratify` must change the file the compiler reads.

    Before the tap it changed only SQLite — a ratification that activated
    nothing. The store row is still written when this store knows the id; the
    outcomes file is what makes the verb mean something.
    """
    proc = _run([sys.executable, str(_REPO / "cabinet" / "scripts" / "org-runtime.py"),
                 "outcomes", "ratify", "acme-001", "--ratified-by", "captain"],
                hatched)
    assert proc.returncode == 0, proc.stderr
    row = _live_rows(hatched)[0]
    assert row["id"] == "acme-001" and row["status"] == "active"
    assert row["captain_ratified"] is True
    assert row["ratified_via"] == "terminal"
    assert len(_ledger(hatched)) == 1


def test_store_ratify_refuses_an_unknown_id_without_writing(hatched):
    proc = _run([sys.executable, str(_REPO / "cabinet" / "scripts" / "org-runtime.py"),
                 "outcomes", "ratify", "no-such-card"], hatched)
    assert proc.returncode != 0
    assert not (hatched / OUTCOMES_REL).exists()
    assert _ledger(hatched) == []
