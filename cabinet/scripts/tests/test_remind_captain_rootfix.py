"""remind-captain.sh CABINET_ROOT root fix — the dead /opt/founders-cabinet
default is gone; the script resolves its OWN repo from $HERE (the
due-at-reminder-tick.sh header pattern), so a DIRECT env-less run works from
any cwd. Matrix:

  * no CABINET_ROOT, cwd = repo root      → context YAML found in THIS repo;
  * no CABINET_ROOT, cwd = unrelated tmp  → same (script-relative, not cwd);
  * missing context slug                  → the refusal names THIS repo's
    path — never the convergence-era /opt/founders-cabinet;
  * explicit CABINET_ROOT                 → still wins (test harness law).

Hermetic: a fake psql on PATH answers the INSERT (no server); the arm's
parse-when/owner-slug run for real (they resolve the repo from their own
file path, which is exactly the property under test)."""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "remind-captain.sh"

# A context slug tracked in the repo (git ls-files instance/config/contexts).
# _default.yml is the ALWAYS-shipped fallback context — it survives the egg
# export (adhoc.yml and the per-product contexts are instance data, stripped),
# so the script-relative default root resolves it with ZERO env on BOTH the
# source instance and a clean/public checkout. Full teeth either way (the
# property under test is root resolution, not which context is used).
_REPO_CONTEXT = "_default"

_FAKE_PSQL = r"""#!/bin/bash
body="$(cat 2>/dev/null || true)"
{ echo "=PSQL="; for a in "$@"; do echo "ARG=$a"; done; echo "=STDIN="; printf '%s\n' "$body"; echo "=END="; } >> "$FAKE_PSQL_LOG"
case "$body" in
  *"INSERT INTO officer_tasks"*) printf '123|2026-07-19 08:00:00+00\n' ;;
esac
exit 0
"""


def _mkbin(tmp_path: Path) -> Path:
    bind = tmp_path / "bin"
    bind.mkdir(exist_ok=True)
    p = bind / "psql"
    p.write_text(_FAKE_PSQL)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bind


def _env(tmp_path: Path, **extra) -> dict:
    env = {**os.environ,
           "PATH": f"{_mkbin(tmp_path)}:{os.environ['PATH']}",
           "CONN": "postgresql://fake",
           "PYTHON": sys.executable,
           "FAKE_PSQL_LOG": str(tmp_path / "psql.log")}
    # the property under test: NO root/context env unless the case sets one
    env.pop("CABINET_ROOT", None)
    env.pop("CABINET_CONTEXT", None)
    env.update(extra)
    return env


def _run(args, env, cwd):
    return subprocess.run(["bash", str(_SCRIPT), *args],
                          capture_output=True, text=True, env=env, cwd=cwd)


class TestScriptRelativeDefault:

    def test_direct_run_from_repo_root_no_env(self, tmp_path):
        r = _run(["+3d", "sign", "the", "filing", "--context", _REPO_CONTEXT],
                 _env(tmp_path), cwd=str(_REPO))
        assert r.returncode == 0, r.stderr
        assert "REMINDER id=123" in r.stdout
        assert f"context={_REPO_CONTEXT}" in r.stdout

    def test_direct_run_from_unrelated_cwd_no_env(self, tmp_path):
        elsewhere = tmp_path / "unrelated" / "deep"
        elsewhere.mkdir(parents=True)
        r = _run(["+3d", "call", "dentist", "--context", _REPO_CONTEXT],
                 _env(tmp_path), cwd=str(elsewhere))
        assert r.returncode == 0, r.stderr
        assert "REMINDER id=123" in r.stdout

    def test_missing_context_refusal_names_this_repo_never_opt(self, tmp_path):
        r = _run(["+3d", "x", "--context", "zz-no-such-context"],
                 _env(tmp_path), cwd=str(tmp_path))
        assert r.returncode == 1
        # the refusal path is THIS repo's script-relative root...
        assert str(_REPO / "instance" / "config" / "contexts"
                   / "zz-no-such-context.yml") in r.stderr
        # ...and the dead convergence-era default is truly gone
        assert "/opt/founders-cabinet" not in r.stderr

    def test_explicit_cabinet_root_still_wins(self, tmp_path):
        root = tmp_path / "custom-root"
        (root / "instance" / "config" / "contexts").mkdir(parents=True)
        # a slug that exists ONLY under the override root — passing proves
        # the env override was consulted, not the script-relative default
        (root / "instance" / "config" / "contexts" / "onlyhere.yml") \
            .write_text("slug: onlyhere\n")
        r = _run(["+3d", "x", "--context", "onlyhere"],
                 _env(tmp_path, CABINET_ROOT=str(root)), cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr
        assert "context=onlyhere" in r.stdout

    def test_no_opt_default_left_in_script(self):
        body = _SCRIPT.read_text(encoding="utf-8")
        assert "/opt/founders-cabinet" not in body
        assert 'CABINET_ROOT="${CABINET_ROOT:-$(cd "$HERE/../.." && pwd)}"' \
            in body
