"""test_apoptosis — the hygiene organ's born-safe polarity, proven on tmp dirs.

The four load-bearing properties:
  (a) retention windows are respected — nothing younger than the window is
      ever touched, and an original is only removed AFTER its compressed
      archive verifies;
  (b) the realpath jail refuses escapes — symlinks are never followed and an
      entry dir outside the designated roots is refused fail-closed;
  (c) irreversible domains (worktrees / skills / services / templates) produce
      CARDS on the front-door intake surface, never deletions;
  (d) the self-heartbeat is written after a completed sweep.

Everything runs hermetically: HOME is pointed at tmp (so the designated log
roots, LaunchAgents lookups, and state/heartbeat dirs all live under the test
dir), the clock and card transport are injected, and no Redis is touched —
captured cards are validated against the real intake schema instead.

Run: /opt/homebrew/bin/python3.12 -m pytest framework/tests/test_apoptosis.py -q
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import subprocess
from pathlib import Path

import pytest

from framework.hygiene import apoptosis as ap

NOW = dt.datetime(2026, 7, 7, 12, 0, tzinfo=dt.timezone.utc)


def _age(path: Path, days: int) -> None:
    """Set a file's mtime `days` into the past (relative to NOW)."""
    t = (NOW - dt.timedelta(days=days)).timestamp()
    os.utime(path, (t, t))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Hermetic HOME: designated log roots, heartbeat, and state all under tmp."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CABINET_RETENTION_CONFIG", raising=False)
    monkeypatch.delenv("CABINET_HYGIENE_ALLOWED_ROOTS", raising=False)
    monkeypatch.setenv("CABINET_HYGIENE_LOG_DIR", str(tmp_path / "hb"))
    monkeypatch.setenv("CABINET_HYGIENE_STATE_DIR", str(tmp_path / "state"))
    logdir = tmp_path / ".cabinet" / "logs"
    logdir.mkdir(parents=True)
    return tmp_path, logdir


def _cfg(days: int, dirp: Path, pattern: str = "*.log", archive_days=None) -> dict:
    entry: dict = {"dir": str(dirp), "pattern": pattern, "days": days}
    if archive_days is not None:
        entry["archive_days"] = archive_days
    return {"hygiene": {"logs": [entry]}}


# ─────────────────────────────────────────────────────────────────────────────
# (a) retention windows respected
# ─────────────────────────────────────────────────────────────────────────────
def test_retention_window_respected(home):
    tmp, logdir = home
    old = logdir / "cold.log"
    old.write_text("cold contents")
    _age(old, 60)
    young = logdir / "hot.log"
    young.write_text("hot contents")
    _age(young, 1)

    report = ap.sweep_retention(_cfg(45, logdir), now=NOW, dry_run=False)

    # The young file is NEVER touched.
    assert young.is_file() and young.read_text() == "hot contents"
    assert report["skipped_young"] >= 1
    # The old file rotated: original archived (verifiable) BEFORE removal.
    assert not old.exists()
    archives = list((logdir / "archive").glob("cold.log.*.gz"))
    assert len(archives) == 1
    with gzip.open(archives[0], "rb") as fh:
        assert fh.read() == b"cold contents"
    assert len(report["rotated"]) == 1


def test_archives_kept_forever_without_archive_days(home):
    tmp, logdir = home
    adir = logdir / "archive"
    adir.mkdir()
    g = adir / "ancient.log.20250101T000000Z.gz"
    g.write_bytes(gzip.compress(b"x"))
    _age(g, 400)

    report = ap.sweep_retention(_cfg(45, logdir), now=NOW, dry_run=False)
    assert g.is_file()                      # no archive_days → kept
    assert report["deleted_archives"] == []


def test_archive_days_window(home):
    tmp, logdir = home
    adir = logdir / "archive"
    adir.mkdir()
    old_gz = adir / "a.log.20260101T000000Z.gz"
    old_gz.write_bytes(gzip.compress(b"a"))
    _age(old_gz, 30)
    new_gz = adir / "b.log.20260706T000000Z.gz"
    new_gz.write_bytes(gzip.compress(b"b"))
    _age(new_gz, 1)

    report = ap.sweep_retention(
        _cfg(45, logdir, archive_days=10), now=NOW, dry_run=False)
    assert not old_gz.exists()
    assert new_gz.is_file()                 # younger than archive_days → kept
    assert [str(old_gz)] == report["deleted_archives"]


def test_dry_run_mutates_nothing(home):
    tmp, logdir = home
    old = logdir / "cold.log"
    old.write_text("cold")
    _age(old, 60)
    report = ap.sweep_retention(_cfg(45, logdir), now=NOW, dry_run=True)
    assert old.is_file()
    assert not (logdir / "archive").exists()
    assert report["rotated"] and report["rotated"][0]["dry_run"] is True


# ─────────────────────────────────────────────────────────────────────────────
# (b) realpath jail refuses escape
# ─────────────────────────────────────────────────────────────────────────────
def test_jail_refuses_symlink_escape(home):
    tmp, logdir = home
    secret = tmp / "secret.log"            # OUTSIDE the designated roots
    secret.write_text("do not touch")
    _age(secret, 60)
    (logdir / "evil.log").symlink_to(secret)

    report = ap.sweep_retention(_cfg(10, logdir), now=NOW, dry_run=False)

    assert secret.is_file() and secret.read_text() == "do not touch"
    assert (logdir / "evil.log").is_symlink()          # link itself untouched
    assert not (logdir / "archive").exists()           # nothing was archived
    assert any("symlink" in r for r in report["refused"])


def test_jail_refuses_dir_outside_designated_roots(home):
    tmp, logdir = home
    outside = tmp / "outside-logs"
    outside.mkdir()
    f = outside / "x.log"
    f.write_text("x")
    _age(f, 400)

    report = ap.sweep_retention(_cfg(10, outside), now=NOW, dry_run=False)
    assert f.is_file()                                  # refused, not swept
    assert any("outside designated log roots" in r for r in report["refused"])


def test_allowed_roots_env_extends_jail(home, monkeypatch):
    tmp, logdir = home
    extra = tmp / "extra-root"
    extra.mkdir()
    f = extra / "y.log"
    f.write_text("y")
    _age(f, 60)
    monkeypatch.setenv("CABINET_HYGIENE_ALLOWED_ROOTS", str(extra))
    report = ap.sweep_retention(_cfg(45, extra), now=NOW, dry_run=False)
    assert not f.exists() and len(report["rotated"]) == 1


def test_pycache_cap_and_symlink_jail(home, tmp_path):
    tmp, _ = home
    repo = tmp_path / "repo"
    (repo / "pkg" / "__pycache__").mkdir(parents=True)
    big = repo / "pkg" / "__pycache__" / "mod.pyc"
    big.write_bytes(b"\0" * (2 * 1024 * 1024))
    target = tmp_path / "target_pycache"                # outside the repo
    target.mkdir()
    keep = target / "keep.pyc"
    keep.write_bytes(b"\0" * 1024)
    (repo / "other").mkdir()
    (repo / "other" / "__pycache__").symlink_to(target)
    # A worktree's caches are NOT this sweep's to touch.
    wt_pyc = repo / ".claude" / "worktrees" / "wt" / "__pycache__"
    wt_pyc.mkdir(parents=True)
    (wt_pyc / "w.pyc").write_bytes(b"\0" * 1024)

    # Under the cap → nothing deleted.
    r0 = ap.sweep_pycache(repo, dry_run=False, cap_mb=1000)
    assert r0["deleted"] == [] and big.is_file()

    # Over the cap → the real cache dir goes; symlink + outside target refused.
    r1 = ap.sweep_pycache(repo, dry_run=False, cap_mb=1)
    assert not (repo / "pkg" / "__pycache__").exists()
    assert keep.is_file()                               # jail held
    assert any("refused" in x for x in r1["refused"])
    assert wt_pyc.is_dir()                              # worktrees pruned from walk


# ─────────────────────────────────────────────────────────────────────────────
# (c) irreversible domains → CARDS, never deletions
# ─────────────────────────────────────────────────────────────────────────────
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(repo: Path, *args: str) -> None:
    env = {**os.environ, **GIT_ENV}
    subprocess.run(["git", *args], cwd=str(repo), env=env, check=True,
                   capture_output=True, text=True, timeout=30)


@pytest.fixture
def fixture_repo(home, tmp_path):
    """A tiny real repo carrying one of every propose-only finding class."""
    tmp, _ = home
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("fixture\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "seed")
    # Merged worktree under .claude/worktrees (same HEAD → trivially merged).
    _git(repo, "worktree", "add", "-q",
         str(repo / ".claude" / "worktrees" / "done"), "-b", "side")
    # Dormant promoted skill (usage 0, old, passed sunset via frontmatter).
    sd = repo / ".claude" / "skills" / "dead-skill"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(
        "---\nname: dead-skill\ndescription: test fixture\n"
        "sunset: 2026-06-01\n---\n\n# Skill: Dead Skill\n\n"
        "**Status:** promoted\n**Date:** 2026-01-01\n**Usage count:** 0\n")
    # Live promoted skill with a manifest sunset CONDITION — must NOT flag.
    sa = repo / ".claude" / "skills" / "alive-skill"
    sa.mkdir(parents=True)
    (sa / "SKILL.md").write_text(
        "---\nname: alive-skill\ndescription: test fixture\n---\n\n"
        "# Skill: Alive\n\n**Status:** promoted\n**Date:** 2026-01-01\n"
        "**Usage count:** 12\n")
    (sa / "manifest.yml").write_text("sunset: after the successor pack ships\n")
    # Stale evolved draft.
    ev = repo / "memory" / "skills" / "evolved"
    ev.mkdir(parents=True)
    (ev / "old-draft.md").write_text(
        "# Skill: Old Draft\n\n**Status:** draft\n**Date:** 2026-01-01\n"
        "**Usage count:** 0\n**Last used:** 2026-02-01\n")
    # Pack manifest with a passed sunset.
    pd = repo / ".claude-plugin"
    pd.mkdir()
    (pd / "plugin.json").write_text(json.dumps(
        {"name": "old-pack", "sunset": "2026-06-01"}))
    # Fleet manifest with a long-disabled row (explicit disabled_since — no
    # blame needed in the fixture; the live manifest path uses git blame).
    cab = repo / "cabinet"
    (cab / "launchd").mkdir(parents=True)
    (cab / "services.yml").write_text(
        "services:\n"
        "  - name: dead-service\n"
        "    label: com.test.dead-service\n"
        "    kind: daemon\n"
        "    disabled: true\n"
        "    disabled_since: 2026-01-01\n"
        "    notes: parked fixture row\n"
        "  - name: live-service\n"
        "    label: com.test.live-service\n"
        "    kind: daemon\n")
    # Never-instantiated launchd template.
    (cab / "launchd" / "com.test.ghost.template.plist").write_text("<plist/>\n")
    return repo


def test_findings_become_cards_not_deletions(fixture_repo):
    repo = fixture_repo
    captured: list[dict] = []

    def fake_enqueue(item: dict) -> str:
        captured.append(item)
        return f"1-{len(captured)}"

    report = ap.run_sweep(repo_root=repo, now=NOW, enqueue_fn=fake_enqueue)

    # NOTHING irreversible was touched.
    assert (repo / ".claude" / "worktrees" / "done").is_dir()
    assert (repo / ".claude" / "skills" / "dead-skill" / "SKILL.md").is_file()
    assert (repo / "memory" / "skills" / "evolved" / "old-draft.md").is_file()
    assert (repo / "cabinet" / "launchd" / "com.test.ghost.template.plist").is_file()
    assert "disabled: true" in (repo / "cabinet" / "services.yml").read_text()

    # Cards landed on the intake surface — and are VALID canonical items.
    from framework.frontdoor import intake
    domains = {c["payload"]["domain"] for c in captured}
    assert {"worktrees", "skills", "services"} <= domains
    for card in captured:
        intake.validate_item(card)          # the real schema, no transport
        assert card["source"] == "apoptosis"
        assert card["urgency_tier"] == "batch"
        assert card["payload"]["propose_only"] is True
        s = card["payload"]["summary"]
        assert "PROPOSE-ONLY" in s and "UNDO" in s and "DECIDE" in s

    by_domain = {c["payload"]["domain"]: c for c in captured}
    wt = by_domain["worktrees"]
    assert "git worktree remove" in wt["payload"]["summary"]
    assert any("done" in f["path"] for f in wt["payload"]["findings"])
    sk = by_domain["skills"]
    names = {f["name"] for f in sk["payload"]["findings"]}
    assert {"dead-skill", "old-draft", "old-pack"} <= names
    assert "alive-skill" not in names       # usage + condition-sunset ≠ dormant
    assert any("sunset passed" in "; ".join(f["reasons"])
               for f in sk["payload"]["findings"])
    sv = by_domain["services"]
    sv_names = {f.get("name") or f.get("template") for f in sv["payload"]["findings"]}
    assert {"dead-service", "com.test.ghost.template.plist"} <= sv_names
    assert not any(f.get("name") == "live-service"
                   for f in sv["payload"]["findings"])

    # Report mirrors the enqueues.
    assert all(c["enqueued_id"] for c in report["cards"])


def test_recard_cooldown_suppresses_identical_findings(fixture_repo):
    repo = fixture_repo
    captured: list[dict] = []

    def fake_enqueue(item: dict) -> str:
        captured.append(item)
        return f"1-{len(captured)}"

    ap.run_sweep(repo_root=repo, now=NOW, enqueue_fn=fake_enqueue)
    first = len(captured)
    assert first >= 3
    r2 = ap.run_sweep(repo_root=repo, now=NOW + dt.timedelta(hours=6),
                      enqueue_fn=fake_enqueue)
    assert len(captured) == first           # nothing re-pinged inside cooldown
    assert all(c["suppressed"] == "cooldown" for c in r2["cards"])


def test_pack_copy_sunsets_are_scanned(tmp_path):
    """Marketplace pack copies (packs/*/skills/*/SKILL.md) are reaper sources:
    a passed date-typed sunset flags (the removal-wave review trigger for the
    T4 pack rail's parallel copies), while a bare condition string still only
    annotates — it never flags on its own."""
    repo = tmp_path / "packs-repo"
    passed = repo / "packs" / "doctrine-pack" / "skills" / "sunset-copy"
    passed.mkdir(parents=True)
    (passed / "SKILL.md").write_text(
        "---\nname: sunset-copy\ndescription: test fixture\n"
        "sunset: '2026-06-01'\n---\n\n# Skill: Sunset Copy\n")
    cond = repo / "packs" / "doctrine-pack" / "skills" / "condition-copy"
    cond.mkdir(parents=True)
    (cond / "SKILL.md").write_text(
        "---\nname: condition-copy\ndescription: test fixture\n"
        "sunset: 'undefined +90d review'\n---\n\n# Skill: Condition Copy\n")

    findings = ap.scan_skills(repo, now=NOW)

    by_name = {f["name"]: f for f in findings}
    hit = by_name["sunset-copy"]
    assert hit["skill_kind"] == "pack-copy"
    assert hit["path"] == "packs/doctrine-pack/skills/sunset-copy/SKILL.md"
    assert any(r == "sunset passed (2026-06-01)" for r in hit["reasons"])
    # Condition-only sunset annotates but never flags (propose-only stays quiet).
    assert "condition-copy" not in by_name


# ─────────────────────────────────────────────────────────────────────────────
# (d) heartbeat written after a completed sweep
# ─────────────────────────────────────────────────────────────────────────────
def test_heartbeat_written(home, tmp_path):
    tmp, _ = home
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    report = ap.run_sweep(repo_root=repo, now=NOW, enqueue_fn=lambda i: "1-1")
    hb = Path(report["heartbeat"])
    assert hb == tmp / "hb" / "apoptosis-sweep.log"
    text = hb.read_text()
    assert "apoptosis-sweep: ok" in text
    assert ap._iso(NOW) in text
    # The success line must never trip the outcome-watchdog's error-marker scan.
    for marker in ("FATAL", "Traceback (most recent call last)",
                   "command not found", "NOGROUP"):
        assert marker not in text


def test_heartbeat_and_config_precedence(home, monkeypatch, tmp_path):
    tmp, logdir = home
    cfg_file = tmp_path / "ret.yml"
    cfg_file.write_text(
        "hygiene:\n  logs:\n    - dir: %s\n      pattern: '*.log'\n      days: 45\n"
        % logdir)
    monkeypatch.setenv("CABINET_RETENTION_CONFIG", str(cfg_file))
    assert ap.load_retention_config()["hygiene"]["logs"][0]["days"] == 45
    # Explicit arg wins over env.
    other = tmp_path / "other.yml"
    other.write_text("hygiene: {}\n")
    assert ap.load_retention_config(other) == {"hygiene": {}}
    # Absent path / corrupt file → fail-closed empty.
    monkeypatch.delenv("CABINET_RETENTION_CONFIG")
    assert ap.load_retention_config() == {}
    bad = tmp_path / "bad.yml"
    bad.write_text("a: [1, 2")            # unterminated flow — parse error
    assert ap.load_retention_config(bad) == {}
    # A parseable-but-foreign shape (list, scalar) is also fail-closed.
    listy = tmp_path / "listy.yml"
    listy.write_text("- 1\n- 2\n")
    assert ap.load_retention_config(listy) == {}
