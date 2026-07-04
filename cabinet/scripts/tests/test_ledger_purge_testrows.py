"""Tests for cabinet/scripts/ledger-purge-testrows.sh (2026-07-04 prep).

The purge is PREP ONLY until the Captain flips CABINET_PURGE_CONFIRM=1
against the live ledger — so these tests are the only execution the script
gets before that moment. They exercise it end-to-end against TEMP fixture
ledgers (never the live one): both refuse-gates, the dry-run preview, the
exact junk criteria, byte-verbatim preservation of kept rows, the
backup-first guarantee, the no-rewrite-when-unchanged invariant, and — since
the 2026-07-04 adversarial-review fix — the consequence-events family (the
graduation read path, dual-emitted by the same leaking suites; see
TestConsequenceFamily).

Run shape mirrors cabinet/scripts/tests/test_generate_instance.py:
subprocess against the real script, real bash, real python3 filter.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "ledger-purge-testrows.sh"


# --- fixture ledger ----------------------------------------------------------
# Mirrors the REAL leaked shapes observed in the live ledger on 2026-07-04
# (see script header): fidelity fixture rows carry payload.subject ==
# "abc1234567"; junk subagent completions carry completed_by == "subagent"
# with no FW-*/PROD-* task_ref (a TASK-* ref is still junk per the exact
# criteria — only FW/PROD refs are genuine work-graph signal).

DROP_ROWS = [
    # fixture fidelity rows (criterion 1)
    {"id": "e1", "event_type": "fidelity_case_evaluated", "actor": "chair",
     "payload": {"subject": "abc1234567", "refs": ["abc1234567"]},
     "parent_id": None, "created_at": "2026-06-21T07:46:10+00:00"},
    {"id": "e2", "event_type": "fidelity_case_scored", "actor": "chair",
     "payload": {"subject": "abc1234567"},
     "parent_id": None, "created_at": "2026-06-21T07:46:11+00:00"},
    # junk subagent completions (criterion 2)
    {"id": "e3", "event_type": "work_item_completed", "actor": "unknown",
     "payload": {"agent_type": "", "agent_id": "a1", "session_id": "s",
                 "completed_by": "subagent"},
     "parent_id": None, "created_at": "2026-06-18T15:43:33+00:00"},
    {"id": "e4", "event_type": "work_item_completed", "actor": "cos",
     "payload": {"task_ref": "TASK-99", "agent_type": "TASK-99 helper",
                 "agent_id": "a2", "session_id": "s",
                 "completed_by": "subagent"},
     "parent_id": None, "created_at": "2026-06-18T15:44:00+00:00"},
]

KEEP_ROWS = [
    # genuine subagent completion — FW ref present (work-graph signal)
    {"id": "k1", "event_type": "work_item_completed", "actor": "cto",
     "payload": {"task_ref": "FW-12", "agent_type": "FW-12 builder",
                 "agent_id": "a3", "session_id": "s",
                 "completed_by": "subagent"},
     "parent_id": None, "created_at": "2026-06-18T16:00:00+00:00"},
    # genuine framework-emitted completion (no completed_by marker at all)
    {"id": "k2", "event_type": "work_item_completed", "actor": "cos",
     "payload": {"task_id": "outcome-001-task-003"},
     "parent_id": None, "created_at": "2026-06-19T09:00:00+00:00"},
    # unrelated event type
    {"id": "k3", "event_type": "mission_created", "actor": "cos",
     "payload": {"mission_id": "m-1"},
     "parent_id": None, "created_at": "2026-06-19T09:01:00+00:00"},
    # genuine fidelity row — real subject, not the fixture literal
    {"id": "k4", "event_type": "fidelity_case_evaluated", "actor": "chair",
     "payload": {"subject": "case-real-01"},
     "parent_id": None, "created_at": "2026-06-22T10:00:00+00:00"},
]

GARBAGE_LINE = "NOT-JSON{{{ definitely not parseable\n"

# --- consequence-family fixtures (2026-07-04 adversarial-review fix) ---------
# The leaking fidelity suites DUAL-EMIT (framework/fidelity/fidelity_events.py):
# each case lands in the org-event family (subject under payload, above) AND
# in the consequence family (subject at TOP level — the
# framework/fidelity/consequence.py schema). 1,996 fixture rows sat in the
# live consequence family at prep (~85% of it), and that family is the
# GRADUATION READ PATH — so the purge must clean it too. Shapes below mirror
# the real leaked rows observed 2026-07-04.

CONSEQ_DROP_ROWS = [
    {"ts": "2026-06-21T07:46:10.589977+00:00",
     "actor": {"kind": "officer", "id": "chair"},
     "lane": "send-1to1-reply", "action": "fidelity-case-evaluated",
     "subject": "abc1234567", "refs": ["abc1234567"]},
    {"ts": "2026-06-21T07:46:11.120000+00:00",
     "actor": {"kind": "officer", "id": "chair"},
     "lane": "send-1to1-reply", "action": "fidelity-case-scored",
     "subject": "abc1234567", "refs": []},
]

CONSEQ_KEEP_ROWS = [
    # genuine consequence row — real case id, must survive byte-verbatim
    {"ts": "2026-06-23T09:00:00+00:00",
     "actor": {"kind": "officer", "id": "chair"},
     "lane": "send-1to1-reply", "action": "fidelity-case-evaluated",
     "subject": "case-real-77", "refs": ["case-real-77"]},
    # family-separation tripwire: a consequence row that MENTIONS the org
    # criterion-2 fields must be KEPT — criterion 2 (junk subagent
    # completions) is an org-event shape and must never fire on this family.
    {"ts": "2026-06-23T09:05:00+00:00",
     "actor": {"kind": "officer", "id": "chair"},
     "lane": "ops", "action": "work_item_completed",
     "subject": "case-real-88",
     "payload": {"completed_by": "subagent", "task_ref": "TASK-1"},
     "event_type": "work_item_completed", "refs": []},
]


def _build_conseq_fixture(ledger_dir: Path) -> str:
    """One consequence-family day-file: junk + genuine interleaved.

    Returns its content for byte-level assertions. Callers pair it with
    _build_fixture so a mixed-family ledger dir is exercised end-to-end.
    """
    ledger_dir.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(CONSEQ_DROP_ROWS[0]) + "\n"
        + json.dumps(CONSEQ_KEEP_ROWS[0]) + "\n"
        + json.dumps(CONSEQ_DROP_ROWS[1]) + "\n"
        + json.dumps(CONSEQ_KEEP_ROWS[1]) + "\n"
    )
    (ledger_dir / "consequence-events-2026-06-21.jsonl").write_text(content)
    return content


def _build_fixture(ledger_dir: Path) -> tuple[str, str]:
    """Two ledger files: one with junk interleaved, one entirely clean.

    Returns (mixed_content, clean_content) for byte-level assertions.
    """
    ledger_dir.mkdir(parents=True, exist_ok=True)
    mixed_lines = [
        json.dumps(DROP_ROWS[0]) + "\n",
        json.dumps(KEEP_ROWS[0]) + "\n",
        json.dumps(DROP_ROWS[2]) + "\n",
        json.dumps(KEEP_ROWS[1]) + "\n",
        json.dumps(DROP_ROWS[1]) + "\n",
        json.dumps(KEEP_ROWS[2]) + "\n",
        json.dumps(DROP_ROWS[3]) + "\n",
        GARBAGE_LINE,
        json.dumps(KEEP_ROWS[3]) + "\n",
    ]
    mixed = "".join(mixed_lines)
    (ledger_dir / "events-2026-06-21.jsonl").write_text(mixed)

    clean = json.dumps(KEEP_ROWS[2]) + "\n" + json.dumps(KEEP_ROWS[3]) + "\n"
    (ledger_dir / "events-2026-06-22.jsonl").write_text(clean)
    return mixed, clean


def _run(script: Path, ledger_dir: Path, *, confirm: bool = False,
         dry_run: bool = False,
         include_today: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # The pytest session fence (repo-root conftest.py) points
    # CABINET_EVENT_LOG_DIR at the session sandbox — override per-test so the
    # subprocess operates on THIS test's fixture. Defensive pops: never
    # inherit a confirm/dry-run/include-today flag from the outer session.
    env["CABINET_EVENT_LOG_DIR"] = str(ledger_dir)
    env.pop("CABINET_PURGE_CONFIRM", None)
    env.pop("CABINET_PURGE_DRY_RUN", None)
    env.pop("CABINET_PURGE_INCLUDE_TODAY", None)
    if confirm:
        env["CABINET_PURGE_CONFIRM"] = "1"
    if dry_run:
        env["CABINET_PURGE_DRY_RUN"] = "1"
    if include_today:
        env["CABINET_PURGE_INCLUDE_TODAY"] = "1"
    return subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True,
        timeout=60,
    )


class TestRefuseGates:
    def test_refuses_without_confirm_flag(self, tmp_path):
        ledger = tmp_path / "events"
        mixed, clean = _build_fixture(ledger)
        result = _run(SCRIPT, ledger, confirm=False)
        assert result.returncode == 1
        assert "CABINET_PURGE_CONFIRM" in result.stderr
        # Nothing was touched — ledger byte-identical, no backup created.
        assert (ledger / "events-2026-06-21.jsonl").read_text() == mixed
        assert (ledger / "events-2026-06-22.jsonl").read_text() == clean
        assert not (tmp_path / "ledger-backups").exists()

    def test_refuses_without_conftest_fence(self, tmp_path):
        # Reproduce the REAL gate mechanism (no override backdoor): copy the
        # script into a fake repo layout whose root has NO conftest.py —
        # REPO_ROOT derives from the script's own location, so the fence
        # check fails even with the confirm flag set.
        fake_repo = tmp_path / "repo"
        scripts_dir = fake_repo / "cabinet" / "scripts"
        scripts_dir.mkdir(parents=True)
        fake_script = scripts_dir / "ledger-purge-testrows.sh"
        shutil.copy2(SCRIPT, fake_script)

        ledger = tmp_path / "events"
        mixed, clean = _build_fixture(ledger)
        result = _run(fake_script, ledger, confirm=True)
        assert result.returncode == 1
        assert "fence" in result.stderr
        assert (ledger / "events-2026-06-21.jsonl").read_text() == mixed
        assert not (tmp_path / "ledger-backups").exists()

    def test_real_repo_root_has_the_fence(self):
        # The gate the previous test bypassed must HOLD in this checkout:
        # repo-root conftest.py exists and carries the env-var marker the
        # script greps for. If this fails, the fence was deleted/renamed and
        # the purge must not run.
        repo_root = SCRIPT.parent.parent.parent
        conftest = repo_root / "conftest.py"
        assert conftest.exists()
        assert "CABINET_EVENT_LOG_DIR" in conftest.read_text()

    def test_refuses_on_missing_ledger_dir(self, tmp_path):
        result = _run(SCRIPT, tmp_path / "does-not-exist", confirm=True)
        assert result.returncode == 1
        assert "ledger dir not found" in result.stderr

    def test_refuses_on_empty_ledger_dir(self, tmp_path):
        empty = tmp_path / "events"
        empty.mkdir()
        result = _run(SCRIPT, empty, confirm=True)
        assert result.returncode == 1
        assert "nothing to purge" in result.stderr


class TestDryRun:
    def test_dry_run_previews_without_writing(self, tmp_path):
        ledger = tmp_path / "events"
        mixed, clean = _build_fixture(ledger)
        result = _run(SCRIPT, ledger, dry_run=True)  # note: NO confirm needed
        assert result.returncode == 0, result.stderr
        assert "DRY RUN" in result.stdout
        # counts visible for the Captain's go/no-go call — totals span BOTH
        # ledger files (9 mixed + 2 clean = 11; 4 junk rows drop)
        assert "rows before:            11" in result.stdout
        assert "rows after:             7" in result.stdout
        # zero mutation, zero backup
        assert (ledger / "events-2026-06-21.jsonl").read_text() == mixed
        assert (ledger / "events-2026-06-22.jsonl").read_text() == clean
        assert not (tmp_path / "ledger-backups").exists()


class TestPurge:
    def test_purges_exact_criteria_and_backs_up_first(self, tmp_path):
        ledger = tmp_path / "events"
        mixed, clean = _build_fixture(ledger)
        clean_inode_before = (ledger / "events-2026-06-22.jsonl").stat().st_ino

        result = _run(SCRIPT, ledger, confirm=True)
        assert result.returncode == 0, result.stderr

        # (c) before/after counts printed, per criterion — totals span BOTH
        # ledger files (9 mixed + 2 clean = 11; 4 junk rows drop)
        assert "rows before:            11" in result.stdout
        assert "rows after:             7" in result.stdout
        assert "dropped (fixture subject=='abc1234567'): 2" in result.stdout
        assert "dropped (junk subagent work_item_completed):  2" in result.stdout

        # (b) kept rows are byte-verbatim, in original order; junk gone
        expected_kept = (
            json.dumps(KEEP_ROWS[0]) + "\n"
            + json.dumps(KEEP_ROWS[1]) + "\n"
            + json.dumps(KEEP_ROWS[2]) + "\n"
            + GARBAGE_LINE                       # unparseable NEVER dropped
            + json.dumps(KEEP_ROWS[3]) + "\n"
        )
        assert (ledger / "events-2026-06-21.jsonl").read_text() == expected_kept

        # untouched file: content identical AND same inode (never rewritten —
        # a rewrite would show up as a fresh inode from the tempfile replace)
        clean_file = ledger / "events-2026-06-22.jsonl"
        assert clean_file.read_text() == clean
        assert clean_file.stat().st_ino == clean_inode_before

        # (a) backup exists as a SIBLING of the events dir, holds the
        # ORIGINAL (pre-purge) bytes of every ledger file
        backups = sorted((tmp_path / "ledger-backups").glob("purge-*/events"))
        assert len(backups) == 1
        assert (backups[0] / "events-2026-06-21.jsonl").read_text() == mixed
        assert (backups[0] / "events-2026-06-22.jsonl").read_text() == clean

        # the follow-up warning about the Store mirror is surfaced
        assert "org-runtime.sqlite3" in result.stdout

    def test_purge_is_idempotent(self, tmp_path):
        ledger = tmp_path / "events"
        _build_fixture(ledger)
        first = _run(SCRIPT, ledger, confirm=True)
        assert first.returncode == 0, first.stderr
        after_first = (ledger / "events-2026-06-21.jsonl").read_text()

        second = _run(SCRIPT, ledger, confirm=True)
        assert second.returncode == 0, second.stderr
        # nothing junk left: before == after (5 kept mixed + 2 clean)
        assert "rows before:            7" in second.stdout
        assert "rows after:             7" in second.stdout
        assert "files rewritten: 0" in second.stdout
        assert (ledger / "events-2026-06-21.jsonl").read_text() == after_first


class TestLiveAppendRaceGuard:
    """The active TODAY-file is never rewritten by default — the running org
    appends to it, and a rewrite could clobber (and fail to back up) a row
    appended between our read and the atomic replace. Junk in it waits for a
    later run, or for an explicitly quiesced run (INCLUDE_TODAY=1)."""

    @staticmethod
    def _today_name() -> str:
        from datetime import datetime, timezone
        return f"events-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"

    def _build_today_fixture(self, ledger: Path) -> str:
        ledger.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(DROP_ROWS[0]) + "\n"   # junk that must SURVIVE today
            + json.dumps(KEEP_ROWS[2]) + "\n"
        )
        (ledger / self._today_name()).write_text(content)
        return content

    def test_today_file_is_skipped_by_default(self, tmp_path):
        ledger = tmp_path / "events"
        today_content = self._build_today_fixture(ledger)
        result = _run(SCRIPT, ledger, confirm=True)
        assert result.returncode == 0, result.stderr
        # untouched — junk row still present, file byte-identical
        assert (ledger / self._today_name()).read_text() == today_content
        # and the operator is TOLD what was left behind and why
        assert "live-append race guard" in result.stdout
        assert "1 junk rows left" in result.stdout
        assert "files rewritten: 0" in result.stdout
        # backup still captured the file (snapshot completeness)
        backups = sorted((tmp_path / "ledger-backups").glob("purge-*/events"))
        assert (backups[0] / self._today_name()).read_text() == today_content

    def test_include_today_override_purges_it(self, tmp_path):
        ledger = tmp_path / "events"
        self._build_today_fixture(ledger)
        result = _run(SCRIPT, ledger, confirm=True, include_today=True)
        assert result.returncode == 0, result.stderr
        expected = json.dumps(KEEP_ROWS[2]) + "\n"
        assert (ledger / self._today_name()).read_text() == expected
        assert "live-append race guard" not in result.stdout


class TestConsequenceFamily:
    """consequence-events-*.jsonl — the graduation read path (2026-07-04
    adversarial-review fix). The same fidelity suites dual-emitted the fixture
    rows into this family (top-level subject, not payload.subject); the purge
    must clean it with the fixture-subject criterion ONLY, never the
    subagent criterion (an org-event shape), and the same backup / dry-run /
    today-race machinery must cover it."""

    def test_purges_conseq_fixture_rows_keeps_genuine_byte_verbatim(self, tmp_path):
        ledger = tmp_path / "events"
        mixed, clean = _build_fixture(ledger)          # org family alongside
        conseq = _build_conseq_fixture(ledger)

        result = _run(SCRIPT, ledger, confirm=True)
        assert result.returncode == 0, result.stderr

        # counts span BOTH families: 9 mixed + 2 clean org + 4 conseq = 15;
        # 4 org junk + 2 conseq junk drop -> 9 remain
        assert "rows before:            15" in result.stdout
        assert "rows after:             9" in result.stdout
        assert "dropped (consequence fixture subject=='abc1234567'): 2" in result.stdout
        # org-family counters unchanged by the new family
        assert "dropped (fixture subject=='abc1234567'): 2" in result.stdout
        assert "dropped (junk subagent work_item_completed):  2" in result.stdout

        # kept consequence rows byte-verbatim, in original order — including
        # the family-separation tripwire row that mimics org criterion-2
        # fields (completed_by=='subagent', no FW/PROD ref) and MUST survive
        expected_conseq = (
            json.dumps(CONSEQ_KEEP_ROWS[0]) + "\n"
            + json.dumps(CONSEQ_KEEP_ROWS[1]) + "\n"
        )
        conseq_file = ledger / "consequence-events-2026-06-21.jsonl"
        assert conseq_file.read_text() == expected_conseq

        # backup captured the ORIGINAL consequence bytes alongside the org files
        backups = sorted((tmp_path / "ledger-backups").glob("purge-*/events"))
        assert len(backups) == 1
        assert (backups[0] / "consequence-events-2026-06-21.jsonl").read_text() == conseq
        assert (backups[0] / "events-2026-06-21.jsonl").read_text() == mixed
        assert (backups[0] / "events-2026-06-22.jsonl").read_text() == clean

    def test_conseq_only_ledger_is_valid_input(self, tmp_path):
        # A dir holding ONLY the consequence family must not trip the
        # nothing-to-purge refusal (bash-3.2 empty-array handling — the
        # families are globbed independently and either may be absent).
        ledger = tmp_path / "events"
        _build_conseq_fixture(ledger)
        result = _run(SCRIPT, ledger, confirm=True)
        assert result.returncode == 0, result.stderr
        assert "rows before:            4" in result.stdout
        assert "rows after:             2" in result.stdout
        assert "dropped (consequence fixture subject=='abc1234567'): 2" in result.stdout

    def test_dry_run_previews_conseq_without_writing(self, tmp_path):
        ledger = tmp_path / "events"
        _build_fixture(ledger)
        conseq = _build_conseq_fixture(ledger)
        result = _run(SCRIPT, ledger, dry_run=True)
        assert result.returncode == 0, result.stderr
        assert "DRY RUN" in result.stdout
        assert "dropped (consequence fixture subject=='abc1234567'): 2" in result.stdout
        # zero mutation, zero backup
        conseq_file = ledger / "consequence-events-2026-06-21.jsonl"
        assert conseq_file.read_text() == conseq
        assert not (tmp_path / "ledger-backups").exists()

    def test_conseq_today_file_is_race_guarded(self, tmp_path):
        # The fidelity harness appends to TODAY'S consequence file while the
        # org runs — same live-append race as the org family, same guard.
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ledger = tmp_path / "events"
        ledger.mkdir(parents=True)
        content = (
            json.dumps(CONSEQ_DROP_ROWS[0]) + "\n"   # junk that must SURVIVE today
            + json.dumps(CONSEQ_KEEP_ROWS[0]) + "\n"
        )
        today_file = ledger / f"consequence-events-{today}.jsonl"
        today_file.write_text(content)

        result = _run(SCRIPT, ledger, confirm=True)
        assert result.returncode == 0, result.stderr
        assert today_file.read_text() == content          # byte-untouched
        assert "live-append race guard" in result.stdout
        assert "1 junk rows left" in result.stdout
        assert "files rewritten: 0" in result.stdout

        # the quiesced override purges it, exactly like the org family
        result2 = _run(SCRIPT, ledger, confirm=True, include_today=True)
        assert result2.returncode == 0, result2.stderr
        assert today_file.read_text() == json.dumps(CONSEQ_KEEP_ROWS[0]) + "\n"

    def test_purge_is_idempotent_across_families(self, tmp_path):
        ledger = tmp_path / "events"
        _build_fixture(ledger)
        _build_conseq_fixture(ledger)
        first = _run(SCRIPT, ledger, confirm=True)
        assert first.returncode == 0, first.stderr
        second = _run(SCRIPT, ledger, confirm=True)
        assert second.returncode == 0, second.stderr
        # nothing junk left anywhere: before == after, zero rewrites
        assert "rows before:            9" in second.stdout
        assert "rows after:             9" in second.stdout
        assert "files rewritten: 0" in second.stdout
