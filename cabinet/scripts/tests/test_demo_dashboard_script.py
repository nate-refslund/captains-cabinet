"""Contract tests for cabinet/scripts/demo-dashboard.sh (PC-B demo kit).

The demo server itself is exercised manually (it npm-ci's and boots a Next
dev server — too heavy and network-adjacent for the suite); what is pinned
here is the SAFETY CONTRACT the script's header declares:

  * syntax clean (bash -n) and the flag surface: unknown flags and a
    non-numeric --port refuse with 64; --status always exits 0.
  * the environment allowlist: the server is launched under ``env -i`` and
    the script NEVER sources cabinet/.env, never exports REDIS_URL (the
    dashboard's mock-Redis branch must engage), never calls launchctl, and
    binds 127.0.0.1 explicitly.
  * staging is scratch-only: the only rm -rf targets the fixed
    cabinet-testburg-demo-* stage prefix, and the tracked fixture dir is
    only ever read (cp/read, no write path into cabinet/fixtures).
  * staging itself IS exercised end-to-end via ``--stage-only`` (no server,
    no npm): the date rebase must be SINGLE-PASS — the 2026-07-10 adversarial
    review proved the old sequential per-date replace cascaded on any run
    date inside the story window (story days merged, staged files overwrote
    each other, journal lines were silently lost). ``CABINET_DEMO_TODAY``
    pins "today"; ``TMPDIR`` sandboxes the stage into pytest's tmp_path.

Run shape mirrors the sibling script tests: subprocess against the real
script with real bash, no network.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "demo-dashboard.sh"
FIXTURE = REPO / "cabinet" / "fixtures" / "testburg"
TEXT = SCRIPT.read_text(encoding="utf-8")
# The executable surface: comment lines dropped (the header deliberately
# NAMES the forbidden things — the code must never touch them).
CODE = "\n".join(ln for ln in TEXT.splitlines()
                 if not ln.lstrip().startswith("#"))


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=30)


class TestFlagSurface:
    def test_bash_syntax_clean(self):
        proc = subprocess.run(["bash", "-n", str(SCRIPT)],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr

    def test_unknown_flag_refuses_64(self):
        proc = _run("--frobnicate")
        assert proc.returncode == 64
        assert "unknown argument" in proc.stderr

    def test_non_numeric_port_refuses_64(self):
        proc = _run("--port", "abc")
        assert proc.returncode == 64
        assert "digits" in proc.stderr

    def test_status_always_exits_zero(self):
        proc = _run("--status")
        assert proc.returncode == 0
        assert "demo-dashboard:" in proc.stdout


class TestSafetyContract:
    def test_server_env_is_an_allowlist(self):
        assert "env -i" in TEXT, "the server must inherit nothing"

    def test_never_sources_cabinet_env(self):
        assert "cabinet/.env" not in CODE, (
            "only the header may MENTION cabinet/.env — never source it")

    def test_redis_url_never_set(self):
        assert not re.search(r"REDIS_URL\s*=", CODE), (
            "REDIS_URL must stay absent so lib/redis.ts stays on its mock")

    def test_no_launchctl(self):
        assert "launchctl" not in CODE

    def test_binds_loopback_explicitly(self):
        assert "--hostname 127.0.0.1" in TEXT

    def test_rm_rf_only_the_fixed_stage_prefix(self):
        for m in re.finditer(r"rm -rf\s+(\S+)", TEXT):
            assert m.group(1) == '"$STAGE"', (
                f"unexpected rm -rf target {m.group(1)!r}")
        assert "cabinet-testburg-demo-" in TEXT, (
            "the stage guard prefix must stay pinned")

    def test_fixture_is_read_only(self):
        # every reference to the tracked fixture dir is a read (cp source /
        # existence check / generator hint) — no write redirection into it.
        for line in TEXT.splitlines():
            if "$FIXTURE" in line and not line.lstrip().startswith("#"):
                assert not re.search(r">\s*\"?\$FIXTURE", line), line
                assert "rm " not in line, line

    def test_world_is_not_advertised_as_demo_safe(self):
        # /world's engine route reads live surfaces (own redis client +
        # this checkout's world files) — the script must never print a
        # /world URL, and must carry the explicit not-demo-safe warning
        # (2026-07-10 adversarial review). Stage-path mentions like
        # "$STAGE/world" (writer-side belt-and-suspenders) are fine.
        assert "$PORT/world" not in TEXT, (
            "/world must never be advertised as a demo URL")
        assert "NOT demo-safe: /world" in TEXT


class TestStagingRebase:
    """The single-pass date-rebase contract, via ``--stage-only``.

    The story ships as three chronicle days (2026-07-07..09) + two journal
    days (07-08/07-09) with ttl horizons 07-10/07-11. Rebase maps story
    index 3 (2026-07-10) onto "today". The old sequential replace collapsed
    ALL five dates to one on a 2026-07-11 run (one chronicle file left, 3 of
    8 journal lines lost) and scrambled order on 07-12..14; single-pass must
    keep 3+2 distinct files and all 8 lines on EVERY run date.
    """

    STORY = ["2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10",
             "2026-07-11"]

    def _stage(self, tmp_path, *args: str, today: str | None = None) -> Path:
        env = dict(os.environ, TMPDIR=str(tmp_path))
        env.pop("CABINET_DEMO_TODAY", None)
        if today:
            env["CABINET_DEMO_TODAY"] = today
        proc = subprocess.run(
            ["bash", str(SCRIPT), "--stage-only", *args],
            capture_output=True, text=True, timeout=60, env=env)
        assert proc.returncode == 0, proc.stderr
        assert "stage-only complete" in proc.stdout
        stages = list(tmp_path.glob("cabinet-testburg-demo-*"))
        assert len(stages) == 1, stages
        return stages[0]

    @staticmethod
    def _mapping(today: str) -> dict[str, str]:
        base = dt.date.fromisoformat(today)
        return {s: (base + dt.timedelta(days=i - 3)).isoformat()
                for i, s in enumerate(TestStagingRebase.STORY)}

    def test_worst_case_run_date_keeps_every_file_and_line(self, tmp_path):
        stage = self._stage(tmp_path, today="2026-07-11")
        world = sorted(p.name for p in (stage / "world").glob("*.jsonl"))
        undo = sorted(p.name for p in (stage / "undo").glob("*.jsonl"))
        assert world == [f"chronicle-2026-07-{d:02d}.jsonl" for d in (8, 9, 10)]
        assert undo == [f"undo-journal-2026-07-{d:02d}.jsonl" for d in (9, 10)]
        lines = [ln for p in (stage / "undo").glob("*.jsonl")
                 for ln in p.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        assert len(lines) == 8, "staging must never lose a journal line"

    def test_no_cascade_on_any_story_window_date(self, tmp_path):
        """Per-date occurrence parity: for every story date d, the staged
        estate carries exactly as many mapping[d] occurrences as the fixture
        carries d — a cascade breaks this the moment any run date lands
        inside the story window (2026-07-08..14)."""
        fixture_text = "".join(
            p.read_text(encoding="utf-8")
            for sub in ("undo", "world")
            for p in sorted((FIXTURE / sub).glob("*.jsonl")))
        src_counts = {d: fixture_text.count(d) for d in self.STORY}
        assert all(src_counts.values()), "every story date anchors the story"
        for off in range(7):                       # 2026-07-08 .. 2026-07-14
            today = (dt.date(2026, 7, 8) + dt.timedelta(days=off)).isoformat()
            sub = tmp_path / today
            sub.mkdir()
            stage = self._stage(sub, today=today)
            staged_text = "".join(
                p.read_text(encoding="utf-8")
                for d in ("undo", "world")
                for p in sorted((stage / d).glob("*.jsonl")))
            mapping = self._mapping(today)
            for d, want in src_counts.items():
                assert staged_text.count(mapping[d]) == want, (
                    f"today={today}: {d}->{mapping[d]} occurrence drift")

    def test_story_now_and_no_rebase_stage_byte_identical(self, tmp_path):
        for label, extra, today in (("pinned", (), "2026-07-10"),
                                    ("norebase", ("--no-rebase",), None)):
            sub = tmp_path / label
            sub.mkdir()
            stage = self._stage(sub, *extra, today=today)
            for src in sorted(FIXTURE.rglob("*.jsonl")):
                rel = src.relative_to(FIXTURE)
                assert (stage / rel).read_bytes() == src.read_bytes(), rel

    def test_stage_carries_testburg_project_identity(self, tmp_path):
        stage = self._stage(tmp_path, today="2026-07-10")
        active = (stage / "active-project.txt").read_text(encoding="utf-8")
        assert active.strip() == "testburg"
        assert (stage / "projects" / "testburg.yml").is_file()
        assert (stage / "config" / "product.yml").is_file()
