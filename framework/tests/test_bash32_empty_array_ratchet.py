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

IT MUST RUN ON THE DELIVERED EGG, WHICH HAS NO ``.git``
=======================================================
The egg a stranger receives is gitless by construction: ``hatch.sh`` and
``null-hatch.sh`` both export with ``git archive HEAD | tar -x`` (null-hatch
falls back to a ``--exclude='./.git'`` tree copy for an already-gitless
source).  So the file listing cannot *require* git — see
``_tracked_shell_files`` for the two distinct ways git fails to answer and why
each one falls through to a filesystem walk rather than raising or lying.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
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


# Directory names that are never part of the delivered source tree. Pruned on
# the WALK path only — the git path is authoritative and excludes them already.
# Verified 2026-07-26: NO tracked file lives under any of these names, so the
# prune costs zero coverage today, and test_the_two_listings_agree_file_for_file
# goes red the day that stops being true rather than letting the walk quietly
# lose a file. They are pruned because a stranger's egg is a working directory:
# `npm install` under any of the three tracked package.json trees would
# otherwise drop thousands of vendored shell scripts into the scan and turn a
# green gate red on third-party source.
_WALK_PRUNE = frozenset(
    {
        ".git", ".hg", ".svn",                                  # VCS metadata
        "node_modules",                                          # vendored JS
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".venv", "venv",                                         # a stranger's virtualenv
        ".next", "out", "dist", "build",                          # build output
        "pgdata", "redisdata",                                    # docker volumes
    }
)


def _is_shell_file(path: Path) -> bool:
    """Suffix, else shebang. ONE predicate, shared by both listing modes.

    Two copies of this rule would be two chances for the modes to disagree,
    which is precisely the property ``test_the_two_listings_agree_file_for_file``
    exists to hold.
    """
    if path.suffix in (".sh", ".bash"):
        return True
    try:
        with path.open("rb") as handle:
            first = handle.readline(200)
    except OSError:
        return False
    return first.startswith(b"#!") and (b"bash" in first or first.strip() == b"#!/bin/sh")


# Ambient git-control env vars. A leaked GIT_DIR/GIT_WORK_TREE would point the
# probe below at a DIFFERENT repository, so which listing mode runs would depend
# on the caller's environment instead of on the filesystem. Scrubbed for the
# child process only — the parent env is never touched.
_GIT_ENV_OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in _GIT_ENV_OVERRIDES:
        env.pop(name, None)
    return env


def _git_shell_files(root: Path) -> list[Path] | None:
    """Tracked shell under ``root``, or ``None`` when git cannot answer FOR IT.

    Git fails to answer in two distinct ways and BOTH must fall through rather
    than raise or lie:

    * **No repository.** A delivered egg has no ``.git`` (see the module
      docstring). ``git ls-files`` exits 128 there; under ``check=True`` that
      became a ``CalledProcessError``, i.e. a hard test ERROR — a green gate
      going red on the one artifact this ratchet most needs to scan. Measured:
      it took ``bash cabinet/scripts/null-hatch.sh`` (hatch proof-a, the
      ``null-hatch`` CI job, and the suite a stranger runs on the unpacked egg)
      from exit 0 to exit 1 as its sole failure.
    * **The wrong repository.** Unpack that egg inside some *other* checkout
      and ``git ls-files`` SUCCEEDS — it lists the outer repo's tracked files
      under this directory, i.e. none of them, exit 0. The scan would read zero
      files and present itself as a clean tree. A silently empty sensor is
      worse than a loud failure, so the toplevel is compared before the listing
      is trusted.
    """
    toplevel = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    if toplevel.returncode != 0 or not toplevel.stdout.strip():
        return None
    if Path(toplevel.stdout.strip()).resolve() != root.resolve():
        return None
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
        env=_git_env(),
    )
    if listing.returncode != 0:
        return None
    found: list[Path] = []
    for raw in listing.stdout.split(b"\0"):
        if not raw:
            continue
        path = root / raw.decode()
        if path.is_file() and _is_shell_file(path):
            found.append(path)
    return sorted(found)


def _walk_shell_files(root: Path) -> list[Path]:
    """Filesystem fallback for a gitless tree — a delivered egg or a stranger's.

    Symlinked directories are listed but not descended (``os.walk`` default),
    which matches git: it does not track through a directory symlink either.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _WALK_PRUNE)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_file() and _is_shell_file(path):
                found.append(path)
    return sorted(found)


def _tracked_shell_files(root: Path = ROOT) -> list[Path]:
    """Every shell file in the delivered tree — git-tracked listing when git can
    answer for ``root``, filesystem walk otherwise.

    In a checkout "tracked" is literal. In a gitless export it means "shipped in
    the tree", which is the same set by construction (the export IS the tracked
    tree) — pinned file-for-file by
    ``test_the_two_listings_agree_file_for_file``.
    """
    tracked = _git_shell_files(root)
    return tracked if tracked is not None else _walk_shell_files(root)


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
    files = _tracked_shell_files()

    # NON-VACUITY. An empty listing scans nothing and reports a clean tree, so
    # the corpus is anchored on files that must exist for this ratchet to mean
    # anything: the two the repair lives in, plus the gate that exports the
    # gitless egg. A listing that misses them is reading the wrong tree, not
    # finding a clean one.
    rels = {path.relative_to(ROOT).as_posix() for path in files}
    for anchor in (
        "cabinet/scripts/lib/officer-env.sh",
        "cabinet/scripts/bootstrap-roles.sh",
        "cabinet/scripts/null-hatch.sh",
    ):
        assert anchor in rels, (
            f"shell listing has {len(files)} file(s) and does not include "
            f"{anchor} — the scan is reading the wrong tree, so a PASS here "
            "would be vacuous"
        )

    unexpected: list[str] = []
    seen: set[tuple[str, str]] = set()

    for path in files:
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


# ---------------------------------------------------------------------------
# The gitless egg — the tree this ratchet is actually shipped to scan.
#
# `null-hatch.sh` (hatch proof-a, the `null-hatch` CI job, and the suite a
# stranger runs on the unpacked egg) ALWAYS builds a gitless sandbox and runs
# `pytest framework/sources framework/tests` inside it. So these arms exercise
# THIS FILE, from disk, in a directory with no `.git` — the shape that turned
# that gate red.
# ---------------------------------------------------------------------------

_RATCHET_REL = "framework/tests/test_bash32_empty_array_ratchet.py"
_RATCHET_NODE = f"{_RATCHET_REL}::test_no_unguarded_empty_array_expansion_in_tracked_shell"


def _materialise_gitless_egg(tmp_path: Path) -> Path:
    """The delivered egg in miniature: the whole shell corpus, no ``.git``.

    Only shell files and the harness the sub-run needs are copied — the corpus
    is what the ratchet reads, and the ALLOWLIST staleness check needs every
    allowlisted file present or it reports phantom stale entries.
    """
    egg = tmp_path / "egg"
    for path in _tracked_shell_files():
        dst = egg / path.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
    # pytest.ini pins rootdir so the repo-root conftest fence still loads in the
    # sub-run (see conftest.py — no pytest run may write the live audit ledger).
    for rel in (_RATCHET_REL, "conftest.py", "pytest.ini"):
        src = ROOT / rel
        if src.is_file():
            dst = egg / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    assert not (egg / ".git").exists(), "the egg fixture must be gitless"
    return egg


def _run_ratchet_in(egg: Path) -> subprocess.CompletedProcess:
    """Run the shipped ratchet from inside ``egg`` — no git anywhere above it."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", _RATCHET_NODE, "-q", "-p", "no:cacheprovider"],
        cwd=str(egg),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_the_ratchet_runs_green_in_a_gitless_export(tmp_path: Path):
    """THE regression sensor: no git, still exit 0.

    Against a ratchet that shells out to ``git ls-files`` under ``check=True``
    this sub-run dies with ``CalledProcessError`` — which is exactly how
    ``null-hatch.sh`` went from exit 0 to exit 1.
    """
    egg = _materialise_gitless_egg(tmp_path)
    result = _run_ratchet_in(egg)
    assert result.returncode == 0, (
        "the ratchet cannot run in a tree with no .git — that is the "
        "delivered egg, hatch proof-a and the null-hatch CI job:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


def test_the_ratchet_keeps_its_teeth_in_a_gitless_export(tmp_path: Path):
    """Portability must not cost detection: plant a real regression, expect red.

    A fallback that quietly listed nothing would make the arm above green while
    the ratchet guarded exactly zero files.
    """
    egg = _materialise_gitless_egg(tmp_path)
    planted = egg / "cabinet" / "scripts" / "bash32-regression-probe.sh"
    planted.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "probe_args=()\n"
        '[ "${SOME_FLAG:-0}" = "1" ] && probe_args=(--flag)\n'
        'printf "%s\\n" "${probe_args[@]}"\n',
        encoding="utf-8",
    )
    result = _run_ratchet_in(egg)
    assert result.returncode != 0, (
        "the ratchet passed a tree containing a genuine unguarded empty-"
        f"array expansion:\n{result.stdout}"
    )
    assert "bash32-regression-probe.sh" in result.stdout, (
        "the ratchet went red without naming the planted regression — it "
        "failed for some other reason, so this is not evidence of teeth:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "probe_args" in result.stdout, result.stdout


def test_the_two_listings_agree_file_for_file(tmp_path: Path):
    """git-tracked listing == filesystem walk. No coverage traded for portability.

    Also the live sensor on ``_WALK_PRUNE``: the day a tracked shell file lands
    under a pruned directory name, the walk loses it and this goes red.

    HONEST SKIP: inside a gitless export there is no git side to compare
    against, and this module is run there — ``null-hatch.sh`` executes
    ``pytest framework/sources framework/tests`` in its egg. Asserting a git
    listing exists would make THIS arm the thing that turns that gate red,
    which is the exact defect it was written to close. It has teeth in every
    checkout, CI included, which is where a drift between the two modes would
    be introduced in the first place.
    """
    from_git = _git_shell_files(ROOT)
    if from_git is None:
        # A skip is only honest when the tree GENUINELY has no repository. If a
        # `.git` is sitting right there and git still would not answer, this arm
        # has been disabled by something — ambient env, a broken git, a
        # worktree oddity — and a quiet skip would hide it. Loud instead.
        assert not (ROOT / ".git").exists(), (
            f"{ROOT}/.git exists but git would not name it as the toplevel, so "
            "the git side of this comparison vanished for a reason that is NOT "
            "'this is a delivered egg'. Refusing to skip: that would retire "
            "this sensor silently."
        )
        pytest.skip(
            f"{ROOT} has no .git (a delivered egg is gitless by construction), "
            "so there is no git listing to compare the walk against — the walk "
            "is the only mode here. Skipped honestly rather than failed on a "
            "premise this tree cannot satisfy."
        )

    egg = _materialise_gitless_egg(tmp_path)
    assert _git_shell_files(egg) is None, (
        "the egg fixture answered as a git repository, so the walk path was "
        "never exercised"
    )
    walked = _tracked_shell_files(egg)

    assert {p.relative_to(egg).as_posix() for p in walked} == {
        p.relative_to(ROOT).as_posix() for p in from_git
    }
    assert len(walked) == len(from_git)
