"""Whole-tree RATCHET: no unguarded empty-array expansion in tracked shell.

THE CLASS
=========
macOS ships ``/bin/bash`` 3.2.57 and always will (Apple froze it at the last
GPLv2 release).  In bash 3.2, expanding an **empty** array under ``set -u``
aborts with ``unbound variable``; bash >= 4.4 permits it::

    a=(); echo "${a[@]}"          # bash 3.2 + set -u  -> ABORT
    a=(); echo "${a[@]+"${a[@]}"}"  # safe everywhere    -> zero arguments

Every officer LaunchAgent hardcodes ``/bin/bash``
(``cabinet/launchd/com.cabinet.officer.template.plist``), ``bash`` on ``PATH``
resolves to that same 3.2 binary on a stock Mac, and the launchers run
``set -euo pipefail``.  So this is a fleet-down class, not a style nit: it took
every officer offline between 2026-07-15 and this ratchet's landing, and it
also killed the hatch at ``proof-c1``.

WHY A TEXT RATCHET AND NOT JUST AN EXECUTION TEST
=================================================
All seven CI jobs are ``ubuntu-latest`` (bash 5.x), where the construct is
legal — CI structurally cannot execute its way into this defect.  The
execution sensors therefore live in
``cabinet/scripts/lib/tests/test_bash32_empty_array.py`` and SKIP on CI (they
run on the Mac, where it matters).  THIS module is the half that has teeth on
ubuntu: it never runs a shell, it reads tracked shell source and goes red on
the shape.  Between them, neither platform is a blind spot.

WHAT COUNTS AS SAFE
===================
An expansion is accepted when any of these holds:

* the array is initialised with at least one element and never re-emptied;
* the expansion uses an alternate-value form (``${a[@]+...}`` / ``${a[@]:-}``
  / ``${a[@]:+...}``) — note these are NOT interchangeable: ``${a[@]+"${a[@]}"}``
  yields ZERO arguments while ``"${a[@]:-}"`` yields ONE EMPTY argument, which
  is its own bug when the target is an argv;
* a ``${#a[@]}`` count guard appears between the possibly-empty initialisation
  and the expansion.

COVERAGE BOUND, STATED HONESTLY
===============================
This is a text scanner, so it cannot see a guard expressed as anything other
than a ``${#a[@]}`` count — e.g. a parallel ``$FAIL`` counter, or a
``[ -n "$str" ]`` on the string that later feeds ``read -ra``.  Those are real
and safe today; each is listed in ``ALLOWLIST`` below with the specific
invariant that makes it safe.  The allowlist is **shrink-only**: an entry that
no longer corresponds to a finding fails this test so dead entries cannot
accumulate into a blanket waiver.  Adding an entry is a deliberate, reviewed
act — the default for a new finding is to fix the shell, not to widen the list.

The scanner is stdlib-only, read-only (source is ``read_text``-scanned, never
imported or executed), and every regex is a static module constant.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

# NAME=()            — declared explicitly EMPTY (optionally local/declare -a)
RE_DECL_EMPTY = re.compile(
    r"(?:^|[;&|]\s*|\b)(?:local|declare|typeset|readonly)?\s*"
    r"(?:-a\s+|-A\s+)?([A-Za-z_][A-Za-z0-9_]*)=\(\s*\)"
)
# NAME=( item ...    — declared with at least one element on the same line
RE_DECL_FULL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=\(\s*(?![\s)])")
# NAME=(             — multi-line array literal; element(s) on following lines
RE_DECL_OPEN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=\(\s*$")
# read -ra NAME      — may bind ZERO elements when the here-string is empty
RE_READ_ARRAY = re.compile(
    r"\bread\s+(?:-[A-Za-z]*\s+)*-[A-Za-z]*a[A-Za-z]*\s+([A-Za-z_][A-Za-z0-9_]*)"
)
# NAME+=(            — append to a possibly-never-created array
RE_APPEND = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\+=\(")
# ${NAME[@]} / ${NAME[*]} — the expansion that aborts. ${#NAME[@]} is SAFE in
# 3.2 (yields 0) and is deliberately not matched: the leading '#' means the
# capture group cannot start there.
RE_EXPANSION = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\[[@*]\]\}")


def find_violations(source: str) -> list[tuple[str, int, str]]:
    """Return (array_name, 1-based line, line_text) for each unguarded site."""
    lines = source.split("\n")
    # Blank out whole-line comments so commented-out examples never trip this.
    code = ["" if ln.lstrip().startswith("#") else ln for ln in lines]

    # Events are walked in SOURCE ORDER (line, then column). Order is
    # load-bearing twice over: a guard only counts if it precedes the use, and
    # a populate only counts if it precedes the use. An order-insensitive pass
    # reported the exact pre-fix officer-env.sh shape as CLEAN, because the
    # conditional `&& _observe_arg=(--observe-only)` on the next line read as
    # proof the array was populated.
    events: list[tuple[int, int, str, str]] = []  # (line, col, kind, name)
    for lineno, line in enumerate(code, start=1):
        for match in RE_DECL_EMPTY.finditer(line):
            events.append((lineno, match.start(), "empty", match.group(1)))
        for match in RE_READ_ARRAY.finditer(line):
            events.append((lineno, match.start(), "empty", match.group(1)))
        for match in RE_APPEND.finditer(line):
            events.append((lineno, match.start(), "append", match.group(1)))
        for match in RE_DECL_FULL.finditer(line):
            # A CONDITIONAL populate proves nothing: `[ x ] && a=(one)` leaves
            # the array empty on the other branch, which is the default path
            # more often than not.
            preceding = line[: match.start()]
            conditional = "&&" in preceding or "||" in preceding
            events.append(
                (lineno, match.start(), "cond_full" if conditional else "full", match.group(1))
            )
        for match in RE_DECL_OPEN.finditer(line):
            following = code[lineno].strip() if lineno < len(code) else ""
            if following and not following.startswith(")"):
                events.append((lineno, match.start(), "full", match.group(1)))
        for match in re.finditer(r"\$\{#([A-Za-z_][A-Za-z0-9_]*)\[[@*]\]", line):
            events.append((lineno, match.start(), "count_guard", match.group(1)))
        for match in RE_EXPANSION.finditer(line):
            name = match.group(1)
            safe = any(
                form in line
                for form in (
                    "${%s[@]+" % name,
                    "${%s[@]:" % name,
                    "${%s[*]+" % name,
                    "${%s[*]:" % name,
                )
            )
            events.append((lineno, match.start(), "safe_use" if safe else "use", name))

    possibly_empty: dict[str, bool] = {}
    guarded: dict[str, bool] = {}
    violations: list[tuple[str, int, str]] = []

    for lineno, _col, kind, name in sorted(events):
        if kind == "empty":
            possibly_empty[name] = True
            guarded[name] = False
        elif kind == "append":
            # An append only proves non-emptiness when it is unconditional AND
            # always reached — not decidable here, so it never clears the flag.
            # It does mark a never-declared array as possibly empty.
            possibly_empty.setdefault(name, True)
            guarded.setdefault(name, False)
        elif kind == "full":
            possibly_empty[name] = False
        elif kind == "cond_full":
            pass
        elif kind == "count_guard":
            guarded[name] = True
        elif kind == "use":
            if possibly_empty.get(name) and not guarded.get(name):
                violations.append((name, lineno, code[lineno - 1].strip()))
    return violations


def _tracked_shell_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    found: list[Path] = []
    for raw in listing:
        if not raw:
            continue
        path = ROOT / raw.decode()
        if not path.is_file():
            continue
        if path.suffix in (".sh", ".bash"):
            found.append(path)
            continue
        try:
            with path.open("rb") as handle:
                first = handle.readline(200)
        except OSError:
            continue
        if first.startswith(b"#!") and (b"bash" in first or first.strip() == b"#!/bin/sh"):
            found.append(path)
    return found


# ---------------------------------------------------------------------------
# Shrink-only allowlist: (repo-relative path, array name) -> why it is safe.
#
# Every entry is a site the SCANNER cannot clear but a human has: the guard
# exists, it just is not spelled `${#arr[@]}`. Fix the shell before adding a
# row here; a row is a statement that the invariant below actually holds.
# ---------------------------------------------------------------------------
ALLOWLIST: dict[tuple[str, str], str] = {
    ("cabinet/scripts/cabinet-feedback.sh", "SPECS"): (
        "SPECS+= runs unconditionally (the email and long-id patterns) before "
        "any expansion, so the array is never empty at either use site."
    ),
    ("cabinet/scripts/captain-rules/eval-encode-pipeline.sh", "FAILURES"): (
        "Expanded only inside `if [ \"$FAIL\" -gt 0 ]`. FAIL is incremented on "
        "the line immediately above every FAILURES+= (single `fail()` helper), "
        "so FAIL>0 implies the array is non-empty."
    ),
    ("cabinet/scripts/captain-rules/eval.sh", "ids"): (
        "`read -ra ids` runs only inside `[ -n \"$expected_...\" ]`, so the "
        "here-string is non-empty and binds at least one element."
    ),
    ("cabinet/scripts/captain-rules/scaffold-entry.sh", "arr"): (
        "`read -ra arr <<< \"$triggers\"` — $triggers is required non-empty "
        "earlier (the script exits 1 on an empty answer)."
    ),
    ("cabinet/scripts/install-extensions.sh", "envs"): (
        "`read -ra envs` runs only inside `[ -n \"$required_env\" ]`."
    ),
    ("cabinet/scripts/run-fidelity-f1.sh", "_ROLE_ARR"): (
        "ROLES resolves through `${F1_ROLES:-${F1_ROLE:-cos}}` — the `:-` form "
        "substitutes on empty as well as unset, so it is never the empty "
        "string. The script also does not enable `set -u`."
    ),
    ("cabinet/scripts/start-officer.sh", "_CEO_TOKEN_CANDIDATES"): (
        "The bare `TELEGRAM_CEO_TOKEN` candidate is appended unconditionally "
        "before both uses. The script also does not enable `set -u`."
    ),
    ("cabinet/scripts/test-audit-framework-backlog-drift.sh", "FAILURES"): (
        "Test harness: expanded only under `[ \"$FAIL\" -gt 0 ]`, and FAIL is "
        "incremented in lockstep on the line above every FAILURES+=."
    ),
    ("cabinet/scripts/test-cabinet-bootstrap.sh", "FAILURES"): (
        "Test harness: expanded only under `[ \"$FAIL\" -gt 0 ]`, and FAIL is "
        "incremented in lockstep on the line above every FAILURES+=."
    ),
    ("cabinet/scripts/test-cabinet-spawn.sh", "FAILURES"): (
        "Test harness: expanded only under `[ \"$FAIL\" -gt 0 ]`, and FAIL is "
        "incremented in lockstep on the line above every FAILURES+=."
    ),
    ("cabinet/scripts/test-memory.sh", "FAILURES"): (
        "Test harness: expanded only in the `[ \"$FAIL\" -eq 0 ]` else-branch, "
        "and FAIL is incremented in lockstep on the line above every "
        "FAILURES+=."
    ),
    ("cabinet/scripts/test-pre-push-hook.sh", "FAILURES"): (
        "Test harness: expanded only under `[ \"$FAIL\" -gt 0 ]`, and FAIL is "
        "incremented in lockstep on the line above every FAILURES+=."
    ),
    ("cabinet/scripts/test-triggers.sh", "FAILURES"): (
        "Test harness: expanded only in the `[ \"$FAIL\" -eq 0 ]` else-branch, "
        "and FAIL is incremented in lockstep on the line above every "
        "FAILURES+=."
    ),
}


# ---------------------------------------------------------------------------
# Engine self-tests — a ratchet nobody has tried to defeat is an assumption.
# These plant KNOWN-bad and KNOWN-good shell text so a scanner that silently
# stopped matching cannot present itself as a clean tree.
# ---------------------------------------------------------------------------


def test_scanner_flags_the_shape_that_took_the_fleet_down():
    """The exact pre-fix officer-env.sh shape must be reported."""
    planted = (
        "officer_env_load_file() {\n"
        "  local -a _observe_arg=()\n"
        '  [ "${CABINET_OBSERVE_ONLY:-0}" = "1" ] && _observe_arg=(--observe-only)\n'
        '  python3.12 parser.py --scope "$f" "${_observe_arg[@]}"\n'
        "}\n"
    )
    found = find_violations(planted)
    assert [(name, line) for name, line, _ in found] == [("_observe_arg", 4)], found


@pytest.mark.parametrize(
    "planted",
    [
        # alternate-value form: zero args when empty
        'a=()\necho "${a[@]+"${a[@]}"}"\n',
        # count guard between init and use
        'a=()\nif [ ${#a[@]} -gt 0 ]; then\n  echo "${a[@]}"\nfi\n',
        # never empty: one element at declaration
        'a=(one)\necho "${a[@]}"\n',
        # never empty: multi-line literal
        'a=(\n  one\n  two\n)\necho "${a[@]}"\n',
        # ${#a[@]} alone is legal in 3.2 and must not be reported
        'a=()\necho "${#a[@]}"\n',
        # a commented-out example must not trip the scanner
        'a=()\n# echo "${a[@]}"\n',
    ],
)
def test_scanner_accepts_the_safe_forms(planted: str):
    assert find_violations(planted) == []


def test_scanner_catches_a_read_ra_that_can_bind_nothing():
    """`read -ra` on an empty here-string binds ZERO elements in 3.2."""
    planted = 'IFS="," read -ra parts <<< "$maybe_empty"\nfor p in "${parts[@]}"; do :; done\n'
    found = find_violations(planted)
    assert [name for name, _, _ in found] == ["parts"], found


def test_scanner_catches_a_reset_to_empty_after_a_populated_declaration():
    """A populated array that is later re-emptied is unsafe from then on."""
    planted = 'a=(one)\necho "${a[@]}"\na=()\necho "${a[@]}"\n'
    found = find_violations(planted)
    assert [(name, line) for name, line, _ in found] == [("a", 4)], found


# ---------------------------------------------------------------------------
# The ratchet itself
# ---------------------------------------------------------------------------


def test_no_unguarded_empty_array_expansion_in_tracked_shell():
    unexpected: list[str] = []
    seen: set[tuple[str, str]] = set()

    for path in _tracked_shell_files():
        rel = path.relative_to(ROOT).as_posix()
        for name, lineno, text in find_violations(path.read_text(encoding="utf-8", errors="replace")):
            key = (rel, name)
            seen.add(key)
            if key in ALLOWLIST:
                continue
            unexpected.append(f"  {rel}:{lineno}  array '{name}'\n      {text}")

    assert not unexpected, (
        "Unguarded empty-array expansion(s) found. On macOS /bin/bash 3.2 with "
        "`set -u` these abort with 'unbound variable' — on Linux/bash 5 they "
        "are silently fine, which is how this class ships.\n"
        "Fix with the alternate-value form `${arr[@]+\"${arr[@]}\"}` (zero "
        "arguments when empty) or a `${#arr[@]}` count guard. Do NOT reach for "
        "`\"${arr[@]:-}\"` when the expansion is an argv: it yields one EMPTY "
        "argument.\n\n" + "\n".join(unexpected)
    )

    stale = sorted(key for key in ALLOWLIST if key not in seen)
    assert not stale, (
        "ALLOWLIST is shrink-only and these entries no longer match any "
        "finding — delete them so the list cannot grow into a blanket "
        "waiver:\n" + "\n".join(f"  {path}  [{name}]" for path, name in stale)
    )


def test_the_two_repaired_sites_use_the_safe_form():
    """Pin the specific repairs so a naive revert is a test failure."""
    officer_env = (ROOT / "cabinet/scripts/lib/officer-env.sh").read_text(encoding="utf-8")
    assert '${_observe_arg[@]+"${_observe_arg[@]}"}' in officer_env, (
        "officer-env.sh lost the bash-3.2-safe observe-only expansion; every "
        "officer boot dies on macOS without it"
    )
    assert '"${_observe_arg[@]}")' not in officer_env

    bootstrap = (ROOT / "cabinet/scripts/bootstrap-roles.sh").read_text(encoding="utf-8")
    assert '${cap_args[@]+"${cap_args[@]}"}' in bootstrap
