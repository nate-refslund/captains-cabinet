"""Tests for cabinet/scripts/feed-purge-testrows.sh (2026-07-16 prep).

The purge is PREP ONLY until the Captain flips CABINET_PURGE_CONFIRM=1
against the live feed — so these tests are the only execution the script
gets before that moment. They exercise it end-to-end against TEMP fixture
feeds (never the live one): both refuse-gates, the dry-run preview, the
exact junk criterion (and what it deliberately KEEPS — the orchestrator
closure row, hashed-key demotes, garbage lines), byte-verbatim preservation
of kept rows, the backup-first guarantee, the no-rewrite-when-unchanged
invariant, the today-file race guard, and that seq.txt/cursors are never
modified.

Run shape mirrors cabinet/scripts/tests/test_ledger_purge_testrows.py:
subprocess against the real script, real bash, real python3 filter.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "feed-purge-testrows.sh"


# --- fixture feed -------------------------------------------------------------
# Mirrors the REAL leaked shape observed in the live feed on 2026-07-16 (see
# script header): test_actfirst_gate.py's expired "stale ask" card, demoted
# by run_action_lane.py's card-expiry sweep, journalled by feed.append_event.

DROP_ROWS = [
    {"direction": "in", "kind": "demote", "situation_key": "slug:stale-ask",
     "demote_reason": "card-expiry", "ts": "2026-07-14T10:00:00Z", "seq": 10},
    {"direction": "in", "kind": "demote", "situation_key": "slug:stale-ask",
     "demote_reason": "card-expiry", "ts": "2026-07-14T11:00:00Z", "seq": 11},
]

KEEP_ROWS = [
    # THE closure row (2026-07-11 shape): same phantom situation_key, but
    # written by the RUNNING orchestrator-triage — genuine system output,
    # deliberately outside the criterion (kind != "demote").
    {"direction": "in", "kind": "closure", "situation_key": "slug:stale-ask",
     "source": "orchestrator-triage", "ts": "2026-07-14T12:00:00Z",
     "closure_reason": "bulk expiry", "seq": 12},
    # genuine demote — hashed sit-* key, never the fixture slug
    {"direction": "in", "kind": "demote",
     "situation_key": "sit-f90b3a30e0fa370c", "demote_reason": "card-expiry",
     "ts": "2026-07-14T13:00:00Z", "seq": 13},
    # same slug but a DIFFERENT demote_reason — defensively outside the
    # exact triple (only what the tests provably wrote is removed)
    {"direction": "in", "kind": "demote", "situation_key": "slug:stale-ask",
     "demote_reason": "manual", "ts": "2026-07-14T14:00:00Z", "seq": 14},
    # ordinary runtime traffic
    {"direction": "out", "kind": "message", "telegram_message_id": 7,
     "chat": "1234", "content_len": 9, "ts": "2026-07-14T15:00:00Z",
     "seq": 15},
]

GARBAGE_LINE = "NOT-JSON{{{ definitely not parseable\n"


def _jsonl(rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


def _write_feed(feed_dir: Path, *, with_today: bool = False):
    """Historical file with junk+keeps+garbage; optionally a today-file."""
    feed_dir.mkdir(parents=True, exist_ok=True)
    hist = feed_dir / "feed-2026-01-02.jsonl"
    hist.write_text(
        _jsonl(DROP_ROWS[:1]) + _jsonl(KEEP_ROWS[:2]) + GARBAGE_LINE
        + _jsonl(DROP_ROWS[1:]) + _jsonl(KEEP_ROWS[2:]),
        encoding="utf-8",
    )
    clean = feed_dir / "feed-2026-01-01.jsonl"
    clean.write_text(_jsonl(KEEP_ROWS[:1]), encoding="utf-8")
    (feed_dir / "seq.txt").write_text("15", encoding="utf-8")
    cursors = feed_dir / "cursors"
    cursors.mkdir()
    (cursors / "cos.txt").write_text("12", encoding="utf-8")
    if with_today:
        today = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d")
        (feed_dir / f"feed-{today}.jsonl").write_text(
            _jsonl(DROP_ROWS[:1]) + _jsonl(KEEP_ROWS[-1:]), encoding="utf-8")
    return hist, clean


def _run(feed_dir: Path, *, dry_run: bool = False, confirm: bool = False,
         include_today: bool = False, script: Path = SCRIPT):
    env = dict(os.environ)
    for var in ("CABINET_PURGE_DRY_RUN", "CABINET_PURGE_CONFIRM",
                "CABINET_PURGE_INCLUDE_TODAY"):
        env.pop(var, None)
    env["CABINET_FEED_DIR"] = str(feed_dir)
    if dry_run:
        env["CABINET_PURGE_DRY_RUN"] = "1"
    if confirm:
        env["CABINET_PURGE_CONFIRM"] = "1"
    if include_today:
        env["CABINET_PURGE_INCLUDE_TODAY"] = "1"
    return subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True)


class TestGates:
    def test_refuses_without_confirm(self, tmp_path):
        feed = tmp_path / "feed"
        hist, _ = _write_feed(feed)
        before = hist.read_bytes()
        result = _run(feed)
        assert result.returncode != 0
        assert "CABINET_PURGE_CONFIRM" in result.stderr
        assert hist.read_bytes() == before
        assert not (tmp_path / "feed-backups").exists()

    def test_refuses_without_conftest_fence(self, tmp_path):
        # Copy the script into a fake repo layout whose root has NO
        # conftest.py — REPO_ROOT derives from the script's own location,
        # so the fence grep fails and the mutating run is refused.
        fake_scripts = tmp_path / "repo" / "cabinet" / "scripts"
        fake_scripts.mkdir(parents=True)
        fake_script = fake_scripts / "feed-purge-testrows.sh"
        shutil.copy(SCRIPT, fake_script)
        feed = tmp_path / "feed"
        hist, _ = _write_feed(feed)
        before = hist.read_bytes()
        result = _run(feed, confirm=True, script=fake_script)
        assert result.returncode != 0
        assert "fence" in result.stderr
        assert hist.read_bytes() == before

    def test_real_repo_root_has_the_fence(self):
        # Canary: the gate-2 grep target must exist in THIS checkout. If
        # this fails, the conftest CABINET_FEED_DIR fence was deleted or
        # renamed and the purge (and the leak protection) is broken.
        repo_root = SCRIPT.resolve().parent.parent.parent
        conftest = repo_root / "conftest.py"
        assert conftest.exists()
        assert "CABINET_FEED_DIR" in conftest.read_text()

    def test_refuses_on_missing_feed_dir(self, tmp_path):
        result = _run(tmp_path / "nope", dry_run=True)
        assert result.returncode != 0
        assert "feed dir not found" in result.stderr

    def test_refuses_on_empty_feed_dir(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        result = _run(feed, dry_run=True)
        assert result.returncode != 0
        assert "nothing to purge" in result.stderr


class TestDryRun:
    def test_dry_run_mutates_nothing(self, tmp_path):
        feed = tmp_path / "feed"
        hist, clean = _write_feed(feed)
        before_hist, before_clean = hist.read_bytes(), clean.read_bytes()
        result = _run(feed, dry_run=True)
        assert result.returncode == 0, result.stderr
        assert hist.read_bytes() == before_hist
        assert clean.read_bytes() == before_clean
        assert not (tmp_path / "feed-backups").exists()
        assert "DRY RUN" in result.stdout
        assert "dropped (demote/slug:stale-ask/card-expiry): 2" in \
            result.stdout
        assert "would rewrite: feed-2026-01-02.jsonl (-2 rows)" in \
            result.stdout

    def test_dry_run_does_not_create_seq_txt(self, tmp_path):
        # A dry run writes NOTHING — including the lock file (the flock is
        # only taken for mutating runs).
        feed = tmp_path / "feed"
        _write_feed(feed)
        (feed / "seq.txt").unlink()
        result = _run(feed, dry_run=True)
        assert result.returncode == 0, result.stderr
        assert not (feed / "seq.txt").exists()


class TestPurge:
    def test_drops_exact_triple_keeps_everything_else(self, tmp_path):
        feed = tmp_path / "feed"
        hist, clean = _write_feed(feed)
        before_hist = hist.read_bytes()
        result = _run(feed, confirm=True)
        assert result.returncode == 0, result.stderr

        kept = hist.read_text(encoding="utf-8")
        kept_lines = kept.splitlines(keepends=True)
        # exact triple gone
        assert "card-expiry" in kept  # the sit-* genuine demote remains
        parsed = [json.loads(ln) for ln in kept_lines
                  if not ln.startswith("NOT-JSON")]
        assert not any(
            r.get("kind") == "demote"
            and r.get("situation_key") == "slug:stale-ask"
            and r.get("demote_reason") == "card-expiry" for r in parsed)
        # every keep survived, byte-verbatim (original serialization)
        for row in KEEP_ROWS:
            assert json.dumps(row) + "\n" in kept
        assert GARBAGE_LINE in kept
        assert "PURGE APPLIED" in result.stdout
        assert "dropped (demote/slug:stale-ask/card-expiry): 2" in \
            result.stdout

        # backup-first: pre-purge bytes preserved
        backups = list((tmp_path / "feed-backups").glob(
            "purge-*/feed/feed-2026-01-02.jsonl"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == before_hist
        # seq.txt + cursors ride along in the backup
        assert list((tmp_path / "feed-backups").glob("purge-*/feed/seq.txt"))
        assert list((tmp_path / "feed-backups").glob(
            "purge-*/feed/cursors/cos.txt"))

    def test_untouched_file_not_rewritten(self, tmp_path):
        feed = tmp_path / "feed"
        _, clean = _write_feed(feed)
        stat_before = clean.stat()
        result = _run(feed, confirm=True)
        assert result.returncode == 0, result.stderr
        stat_after = clean.stat()
        # no junk in this file -> never rewritten (same inode, same mtime)
        assert stat_after.st_ino == stat_before.st_ino
        assert stat_after.st_mtime_ns == stat_before.st_mtime_ns

    def test_seq_and_cursors_never_modified(self, tmp_path):
        feed = tmp_path / "feed"
        _write_feed(feed)
        cursor = feed / "cursors" / "cos.txt"
        result = _run(feed, confirm=True)
        assert result.returncode == 0, result.stderr
        assert (feed / "seq.txt").read_text() == "15"
        assert cursor.read_text() == "12"

    def test_preserves_file_mode_after_rewrite(self, tmp_path):
        feed = tmp_path / "feed"
        hist, _ = _write_feed(feed)
        os.chmod(hist, 0o644)
        result = _run(feed, confirm=True)
        assert result.returncode == 0, result.stderr
        assert (hist.stat().st_mode & 0o7777) == 0o644

    def test_second_run_is_idempotent(self, tmp_path):
        feed = tmp_path / "feed"
        hist, _ = _write_feed(feed)
        first = _run(feed, confirm=True)
        assert first.returncode == 0, first.stderr
        after_first = hist.read_bytes()
        second = _run(feed, confirm=True)
        assert second.returncode == 0, second.stderr
        assert hist.read_bytes() == after_first
        assert "dropped (demote/slug:stale-ask/card-expiry): 0" in \
            second.stdout
        assert "files rewritten: 0" in second.stdout

    def test_valid_json_non_dict_line_kept_and_counted(self, tmp_path):
        # A bare JSON list parses but is not a row object — fail-safe keep,
        # visible in the diagnostic counter (pins the AttributeError
        # regression class the events purge documents).
        feed = tmp_path / "feed"
        hist, _ = _write_feed(feed)
        non_dict = "[1, 2, 3]\n"
        with open(hist, "a", encoding="utf-8") as fh:
            fh.write(non_dict)
        result = _run(feed, confirm=True)
        assert result.returncode == 0, result.stderr
        assert non_dict in hist.read_text(encoding="utf-8")
        # garbage line + non-dict line both preserved and both counted
        assert "unparseable lines preserved (never dropped): 2" in \
            result.stdout


class TestTodayGuard:
    def test_today_file_skipped_by_default(self, tmp_path):
        feed = tmp_path / "feed"
        _write_feed(feed, with_today=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d")
        today_file = feed / f"feed-{today}.jsonl"
        before = today_file.read_bytes()
        result = _run(feed, confirm=True)
        assert result.returncode == 0, result.stderr
        assert today_file.read_bytes() == before
        assert "skipped (active today-file" in result.stdout
        assert "1 junk rows left" in result.stdout

    def test_include_today_purges_it(self, tmp_path):
        feed = tmp_path / "feed"
        _write_feed(feed, with_today=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d")
        today_file = feed / f"feed-{today}.jsonl"
        result = _run(feed, confirm=True, include_today=True)
        assert result.returncode == 0, result.stderr
        kept = today_file.read_text(encoding="utf-8")
        assert "slug:stale-ask" not in kept
        assert json.dumps(KEEP_ROWS[-1]) + "\n" in kept
        assert "skipped (active today-file" not in result.stdout
