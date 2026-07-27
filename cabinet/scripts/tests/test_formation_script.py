"""Tests for cabinet/scripts/formation.sh (Phase 3 SCAFFOLD stage machine).

Pins the scaffold's acceptance surface: syntax, --help, a full foreground run
producing honest IOUs + the six stamps, journal-based RESUME, --undo
supersede-archive, the printed cost estimate + call cap, and the two
structural denials (no append-interface.sh grant; no outcomes.yml write).

Hermetic: every run gets a tmp CABINET_ROOT — the checkout's own instance/
is never touched. Run: python3.12 -m pytest
cabinet/scripts/tests/test_formation_script.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_FORMATION = _SCRIPTS_DIR / "formation.sh"

_STAMPS = ("FORMATION_START", "DISCOVERY_DONE", "READ_SCOPE_RATIFIED",
           "INGEST_DONE", "STRATEGY_DONE", "BRIEFING_DONE")


def _run(args, root: Path, env_extra: dict | None = None):
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(_FORMATION), *args],
        cwd=_REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=120,
    )


def _journal_rows(root: Path, run_id: str) -> list[dict]:
    path = root / "instance/onboarding/formation" / run_id / "journal.jsonl"
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _run_id_from(stdout: str) -> str:
    for line in stdout.splitlines():
        if "— run formation-" in line:
            return line.split("— run ", 1)[1].split(" ", 1)[0].strip()
    raise AssertionError(f"no run id in output:\n{stdout}")


# ---------------------------------------------------------------------------
# syntax + help
# ---------------------------------------------------------------------------
def test_bash_syntax_clean():
    p = subprocess.run(["bash", "-n", str(_FORMATION)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_help_documents_the_contract(tmp_path):
    p = _run(["--help"], tmp_path)
    assert p.returncode == 0, p.stderr
    for needle in ("--run-id", "--undo", "PROPOSE-ONLY",
                   "CABINET_FORMATION_CALL_CAP", "journal.jsonl",
                   "_pre-adopt", "nothing deleted"):
        assert needle in p.stdout, f"--help missing {needle!r}"
    # help must not touch the root
    assert not (tmp_path / "instance").exists()


def test_unknown_flag_refuses(tmp_path):
    p = _run(["--frobnicate"], tmp_path)
    assert p.returncode == 2
    assert "unknown flag" in p.stderr


# ---------------------------------------------------------------------------
# the full scaffold run — end to end, honest IOUs, nothing activates
# ---------------------------------------------------------------------------
def test_full_run_stamps_journals_and_stays_propose_only(tmp_path):
    p = _run([], tmp_path, {"CABINET_FORMATION_CALL_CAP": "9"})
    assert p.returncode == 0, p.stderr
    rid = _run_id_from(p.stdout)

    # cost estimate + cap printed up front, honestly zero
    assert "LLM CLI calls this run: 0" in p.stdout
    assert "cap of 9" in p.stdout

    # all six stamps journaled, in order
    rows = _journal_rows(tmp_path, rid)
    assert [r["stage"] for r in rows] == list(_STAMPS)
    assert rows[0]["status"] == "open" and "call_cap=9" in rows[0]["note"]
    for row in rows[1:]:
        # INVERTED 2026-07-26 (ordering inversion): DISCOVERY_DONE derives the
        # estate for real; every stage after it is still an honest IOU.
        if row["stage"] == "DISCOVERY_DONE":
            assert row["status"] == "derived"
            assert "no new read" in row["note"]
        else:
            assert row["status"] == "stub-iou"
            assert "not yet built" in row["note"]  # honest IOU, no fake work

    # artifacts + flight log exist in the run dir
    rdir = tmp_path / "instance/onboarding/formation" / rid
    assert (rdir / "discovery.yml").is_file()      # derived, not an IOU
    assert not (rdir / "discovery-IOU.md").exists()
    assert (rdir / "briefing-IOU.md").is_file()
    flight = (rdir / "flight.log").read_text()
    for stamp in _STAMPS:
        assert f"STAMP {stamp}" in flight
    assert "FLIGHT SUMMARY" in p.stdout

    # NOTHING ACTIVATES: no compiler-readable surface was written.
    # NARROWED 2026-07-26 from "instance/config does not exist" — DISCOVERY_DONE
    # now writes the propose-only lanes proposal there, deliberately, so it sits
    # beside the answers file the Captain ratifies it into. The invariant itself
    # is unchanged and is now asserted by NAME rather than by a directory-absence
    # proxy: the compiler's filename gate reads only outcomes.yml, the generator
    # takes lanes ONLY from the answers file, and the EXACT set of config files
    # this run may write is pinned so a future writer cannot slip a second one in.
    assert not (tmp_path / "instance/config/outcomes.yml").exists()
    assert not (tmp_path / "instance/config/cabinet-init.answers.yml").exists()
    config_dir = tmp_path / "instance/config"
    assert sorted(f.name for f in config_dir.iterdir()) == ["lanes-proposed.yml"]
    proposal = (config_dir / "lanes-proposed.yml").read_text()
    assert "captain_ratified: false" in proposal


def test_resume_skips_journaled_stages_and_appends_nothing_twice(tmp_path):
    first = _run([], tmp_path)
    assert first.returncode == 0, first.stderr
    rid = _run_id_from(first.stdout)
    before = _journal_rows(tmp_path, rid)

    again = _run(["--run-id", rid], tmp_path)
    assert again.returncode == 0, again.stderr
    assert again.stdout.count("[skip]") == 5       # every stage skipped
    assert "[iou ]" not in again.stdout
    assert _journal_rows(tmp_path, rid) == before  # append-only, no dupes


def test_partial_run_resumes_from_the_journal(tmp_path):
    # seed a run with only the first two stages done (python half directly)
    env = dict(os.environ, CABINET_ROOT=str(tmp_path))
    def _py(*args):
        return subprocess.run(
            ["python3.12", "-m", "framework.onboarding.formation", *args],
            cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=60)
    rid = _py("open", "--id-only").stdout.strip()
    assert rid.startswith("formation-")
    _py("stage", "--run-id", rid, "--stamp", "DISCOVERY_DONE")

    p = _run(["--run-id", rid], tmp_path)
    assert p.returncode == 0, p.stderr
    assert p.stdout.count("[skip]") == 1           # discovery already done
    assert p.stdout.count("[iou ]") == 4           # the rest ran now
    assert [r["stage"] for r in _journal_rows(tmp_path, rid)] == list(_STAMPS)


# ---------------------------------------------------------------------------
# --undo — supersede-archive, nothing deleted, honest refusal
# ---------------------------------------------------------------------------
def test_undo_supersede_archives_the_run_dir(tmp_path):
    run = _run([], tmp_path)
    rid = _run_id_from(run.stdout)
    p = _run(["--undo", rid], tmp_path)
    assert p.returncode == 0, p.stderr
    assert "archived" in p.stdout and "Nothing deleted" in p.stdout

    fdir = tmp_path / "instance/onboarding/formation"
    assert not (fdir / rid).exists()
    archives = list(fdir.glob("_pre-adopt-*/" + rid))
    assert len(archives) == 1
    assert (archives[0] / "journal.jsonl").is_file()   # contents intact


def test_undo_missing_run_exits_nonzero(tmp_path):
    p = _run(["--undo", "formation-19990101-000000-dead"], tmp_path)
    assert p.returncode != 0
    assert "no-such-run" in p.stdout


def test_undo_path_escape_refuses(tmp_path):
    p = _run(["--undo", "../../etc"], tmp_path)
    assert p.returncode != 0
    assert "invalid run id" in p.stderr


# ---------------------------------------------------------------------------
# structural denials
# ---------------------------------------------------------------------------
def _executable_lines() -> list[str]:
    """The script minus comments — the surface that can actually DO things."""
    out = []
    for line in _FORMATION.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(line)
    return out


def test_formation_is_not_granted_append_interface():
    """Formation never invokes the Captain-law ledgers' writer — the
    self-persuasion channel stays closed (design §4 Phase 3 rails). The
    header COMMENT may name the denial; executable lines may not."""
    for line in _executable_lines():
        assert "append-interface" not in line, line


def test_formation_never_names_a_compiler_readable_surface():
    """No executable line so much as spells the activation surface."""
    for line in _executable_lines():
        assert "outcomes.yml" not in line, line
