"""Every writer of the officer heartbeat writes the SAME kind of stamp.

WHAT THIS CAUGHT (2026-08-14). ``cabinet:heartbeat:<slug>`` has four writers.
Three of them stamped ISO-8601 (``date -u +%Y-%m-%dT%H:%M:%SZ``); the fourth,
``start-officer-mac.sh`` — the one that runs FIRST, at officer boot — stamped
Unix seconds (``date -u +%s``). No shell reader noticed, because every shell
reader tests PRESENCE and lets the 900-second TTL do the freshness work. The
dashboard does not: ``cabinet/dashboard/src/lib/liveness.ts`` parses the value,
and ``Date.parse("1786719742")`` is ``NaN``, which is that module's ``unknown``
arm. So for the minutes between an officer's own boot stamp and the
supervisor's first refresh, a HEALTHY, JUST-STARTED officer rendered as
"heartbeat unreadable" in amber — on precisely the screen an operator watches
after pressing "Wake your Cabinet".

WHY THE TEST IS SHAPED THIS WAY. It does not pin a string; it extracts the
``date`` format expression each writer actually uses and asserts the value that
expression PRODUCES round-trips through ``datetime.fromisoformat``. A writer
that switches to another genuinely-ISO spelling passes; a writer that goes back
to an epoch, or invents a third format, fails — including one added tomorrow,
because the writer list is discovered by grep rather than enumerated here.

Verified to FAIL against pre-change code: restoring ``date -u +%s`` in
start-officer-mac.sh reds ``test_every_heartbeat_writer_stamps_iso8601``.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The officer-liveness key the dashboard parses. The `:liveness:` and
# `:activity:` keys are different planes with different readers and are not in
# scope here — the pattern below excludes them by requiring the slug variable
# to follow the prefix directly.
_KEY_RE = re.compile(r'cabinet:heartbeat:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?"')
# `\S+` would swallow the closing `)"` of an inline `$(date -u +FMT)`; the
# format itself never contains a paren or a quote.
_DATE_FMT_RE = re.compile(r'date -u \+([^\s)"]+)')


def _writer_lines() -> list[tuple[Path, int, str]]:
    """Every shell line that SETs the officer heartbeat key, found by grep so a
    writer added later is in scope without editing this file."""
    out = subprocess.run(
        ["git", "grep", "-n", "-E", r"(SETEX|SET) \"cabinet:heartbeat:\$", "--",
         "cabinet", "framework"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=False,
    ).stdout
    rows: list[tuple[Path, int, str]] = []
    for row in out.splitlines():
        path_s, lineno_s, text = row.split(":", 2)
        if "/tests/" in path_s or path_s.endswith("_test.py"):
            continue
        if not _KEY_RE.search(text):
            continue          # :liveness: / :activity: planes, not this key
        rows.append((_REPO_ROOT / path_s, int(lineno_s), text))
    return rows


def _stamp_expression(path: Path, lineno: int, text: str) -> str:
    """The `date -u +FMT` this writer's value comes from — on the line itself,
    or on the assignment of the variable it interpolates."""
    inline = _DATE_FMT_RE.search(text)
    if inline:
        return inline.group(1)
    var = re.search(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?" EX', text)
    assert var, f"{path}:{lineno}: heartbeat value is neither an inline date nor a variable: {text}"
    body = path.read_text(encoding="utf-8")
    assign = re.search(rf'{var.group(1)}=\$\(\s*date -u \+([^\s)"]+)\s*\)', body)
    assert assign, f"{path}: could not find where ${var.group(1)} is stamped"
    return assign.group(1)


def test_there_are_writers_to_check():
    """The degenerate end of this file: a grep that matches nothing would make
    every assertion below vacuously true."""
    assert len(_writer_lines()) >= 3, _writer_lines()


@pytest.mark.parametrize("row", _writer_lines(), ids=lambda r: f"{r[0].name}:{r[1]}")
def test_every_heartbeat_writer_stamps_iso8601(row):
    path, lineno, text = row
    fmt = _stamp_expression(path, lineno, text)
    produced = subprocess.run(
        ["date", "-u", f"+{fmt}"], capture_output=True, text=True, check=True
    ).stdout.strip()
    try:
        datetime.fromisoformat(produced.replace("Z", "+00:00"))
    except ValueError:  # pragma: no cover - the failure message is the point
        raise AssertionError(
            f"{path.relative_to(_REPO_ROOT)}:{lineno} stamps the officer "
            f"heartbeat as {produced!r} (from `date -u +{fmt}`), which is not "
            f"ISO-8601. The dashboard parses this value with Date.parse and "
            f"renders an unparseable stamp as 'heartbeat unreadable' — so a "
            f"healthy officer looks broken. Every other writer of this key "
            f"uses `date -u +%Y-%m-%dT%H:%M:%SZ`."
        )


def test_all_writers_agree_on_one_format():
    """Three ISO spellings would each pass the arm above and still make the
    fleet's own stamps incomparable to each other."""
    formats = {_stamp_expression(*row) for row in _writer_lines()}
    assert len(formats) == 1, (
        f"the officer heartbeat is stamped {len(formats)} different ways: {sorted(formats)}"
    )
