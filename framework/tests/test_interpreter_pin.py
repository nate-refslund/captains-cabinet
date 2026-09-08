"""A0.3 grep sensor: no bare ``python3`` in an UNLOCKED exec string on the
gap / pull plane.

THE CLASS
=========
``python3`` on the deployment box is **3.9.6**; ``python3.12`` is installed
beside it (contract "Measured on the Captain's box", 2026-09-07).  An exec
string that says ``python3`` therefore does not name an interpreter — it names
whatever is first on ``PATH`` at that moment, on that box, under whatever
environment launchd or the dashboard container happens to hand it.  A0.3 splits
the plane in two and this module owns the second half:

* **Locked** paths (the hooks dir, ``session-task-inject.sh``) cannot be
  pinned — editing them is a Captain ceremony — so every module they can
  import stays importable and correct under 3.9.  That half is asserted
  directly, per module, in ``framework/learning/tests/test_capability_gaps.py``
  (grammar parse, evaluated-union walk) and
  ``cabinet/scripts/tests/test_record_capability_gap_script.py`` (a LIVE import
  under the box's bare ``python3``).
* **Unlocked** exec strings pin ``${CABINET_PYTHON:-python3.12}`` — the shell
  still expands it, so an operator overrides with one variable.  A0.3 names
  three anchors and then asks for "a grep sensor over bare ``python3`` in
  unlocked exec strings", which is this module.

WHY A DERIVED SCOPE AND NOT THE THREE NAMED ANCHORS
===================================================
A hand-listed anchor set is coverage-bound: it goes green over a file nobody
thought to list.  Writing this scanner over a DERIVED scope immediately found
two unlisted violations in the same plane —
``cabinet/scripts/record-capability-gap.sh`` (the officer's own gap recorder,
which imports the very module this unit widened) and the gaps command inside
``cabinet/cron/briefing.sh`` — neither of which appears in A0.3's parenthetical.
Both are fixed in the same commit as this sensor.

So the scope is computed, not typed: every tracked ``.sh`` / ``.ts`` / ``.tsx``
file that is NOT under a germline-locked path AND mentions one of the plane
tokens below.  A new file that execs the gap plane is in scope the day it is
written, without anyone remembering to add it here.

COVERAGE BOUND, STATED
======================
* Only the **gap / pull plane** is in scope — the tokens below.  The general
  ``framework.events.emitter`` exec surface (12 tracked files, most of them
  hooks) is deliberately NOT a token: it is not on the pull path except
  through ``work-graph-complete.sh``, which is in scope by its own name, and
  admitting it would trade one real invariant for seven waivers.
* Only ``.sh`` / ``.ts`` / ``.tsx``.  A ``.py`` file is a module, not an exec
  string; its interpreter is chosen by whoever runs it, and the 3.9 half above
  is what protects it.
* Whole-line comments are stripped before BOTH the scope match and the scan,
  so prose ABOUT ``python3`` (including this module's own subject matter) is
  neither a finding nor a way onto the plane — ``load-preset.sh`` mentions
  ``framework/missions/compiler.py`` in one comment and execs a peers-file
  validator that has nothing to do with this plane.  A bare ``python3`` in a
  TRAILING comment on a code line WOULD be reported; that is the safe
  direction to be wrong in.
* Test sources are out of scope: they never run on the deployment box, and
  the one that asserts this very absence
  (``lib/capability-gaps.test.ts``) has to spell the defect to forbid it.
* ``SANCTIONED`` below is the one place a bare interpreter is CORRECT: a
  drill whose subject IS the box's own ``python3`` must reach it, or it
  measures 3.12 and reports nothing about the interpreter an officer walks.
  It is keyed by exact code text, so one LINE is excused and the rest of the
  same file stays in scope, and ``test_sanctioned_lines_are_still_bare``
  reds if the line is pinned or deleted.
* ``PENDING`` below is the honest half: a pull-path file belongs to a unit
  that has not landed.  Each entry is self-retiring — ``test_pending_entries``
  asserts the violation is still THERE, so the row goes red the moment its
  owner fixes the file, and cannot decay into a blanket waiver.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest


ROOT = Path(__file__).resolve().parents[2]

# The pinned form. One literal, so a grep for it is a grep for the law.
PIN = "${CABINET_PYTHON:-python3.12}"

# A bare interpreter token: `python3` NOT followed by a version suffix.
# `python3.12` and `python3-config` do not match; `/usr/bin/python3` DOES —
# an absolute path to the box's 3.9 is exactly the defect, spelled longer.
BARE_PYTHON3 = re.compile(r"(?<![\w.])python3(?![\w.\-])")

# A file is on the plane if its source mentions any of these. Substrings, not
# regexes: the point is to be obvious rather than clever.
PLANE_TOKENS = (
    "org-runtime.py gaps",       # the gap CLI, the dashboard's only writer
    "capability_gaps",           # the module this unit widened
    "capability-gaps",           # its dashboard reader
    "framework.missions.",       # supervisor / session_bridge / claims / compiler
    "framework/missions/",
    "session_bridge",
    "work-graph-complete",       # the completion half of the pull path
)

SUFFIXES = (".sh", ".ts", ".tsx")

# Files on the plane whose pin belongs to a unit that has not landed. The value
# is WHY, and it names the owner. Self-retiring: see test_pending_entries.
PENDING: Dict[str, str] = {
    # cabinet/scripts/work-graph-complete.sh RETIRED 2026-09-08: unit U2 (the
    # claim) landed the pin with `--claim`, so the row went red exactly as it
    # was built to — deleted here in the same commit that merges U2, per the
    # phase-1 contract AMENDMENTS round 2, A0.10.
    "cabinet/cron/mission-supervisor.sh":
        "the supervisor's own cron — units U2/U3b own the supervisor call path "
        "and rewrite these two exec strings",
}

# Lines on the plane whose bare interpreter is the SUBJECT, not a defect.
#
# The phase-1 drill has to run the pull-path import under the box's OWN
# `python3` — that is stage P2h, and it is how A0.3's locked half (every module
# the locked hook imports stays 3.9-correct) is measured at all. Pinning that
# line would make the drill assert 3.12 against itself and leave the real
# interpreter unmeasured: the sensor would be testing something other than the
# control.
#
# Keyed by EXACT code text, not by path: every other bare `python3` in the same
# file is still a finding, so this cannot widen into a file-level waiver. Each
# entry is self-retiring in the same way PENDING is — test_sanctioned_lines_
# are_still_bare goes red the day the line is pinned, moved or deleted, and the
# row must then be re-argued rather than quietly kept.
SANCTIONED: Dict[str, Dict[str, str]] = {
    "cabinet/scripts/drills/one-responsibility.sh": {
        'BOX_PY="python3"':
            "contract A4.1 + drill stage P2h (one-responsibility.sh:939-951): "
            "the drill imports the pull path under the box's own interpreter "
            "to prove the 3.9 half; a pin here disarms that arm",
    },
}


# A0.3's own parenthetical, asserted to still be IN the derived scope. If a
# rename or a deletion drops one, the scope test goes red rather than the scan
# quietly covering less.
A03_NAMED_ANCHORS = (
    "cabinet/scripts/work-graph-complete.sh",
    "cabinet/dashboard/src/actions/gaps.ts",
    "cabinet/dashboard/src/lib/capability-gaps.ts",
)


# ---------------------------------------------------------------------------
# The locked set — parsed from the live script, never copied
# ---------------------------------------------------------------------------

def _locked_set() -> Tuple[frozenset, Tuple[str, ...]]:
    """(FILES, DIRS) as germline-lock.sh declares them, right now.

    Parsed rather than duplicated: a second copy of the constitutional set is
    a second thing to drift, and the lockstep meta-test already pins the real
    one. If the hooks dir ever leaves DIRS, this sensor's scope grows in the
    same run instead of a session later.
    """
    source = (ROOT / "cabinet" / "scripts" / "germline-lock.sh").read_text()

    def _array(name: str) -> List[str]:
        match = re.search(name + r"=\(\n(.*?)\n\)", source, re.S)
        assert match, "germline-lock.sh has no %s=( ... ) array" % name
        out = []
        for line in match.group(1).splitlines():
            line = line.split("#")[0].strip()
            if len(line) > 1 and line.startswith('"') and line.endswith('"'):
                out.append(line[1:-1])
        return out

    files = _array("FILES")
    dirs = _array("DIRS")
    assert files and dirs, "germline-lock.sh parsed to an EMPTY locked set"
    return frozenset(files), tuple(dirs)


def _is_locked(rel: str) -> bool:
    files, dirs = _locked_set()
    return rel in files or any(rel == d or rel.startswith(d + "/") for d in dirs)


# ---------------------------------------------------------------------------
# Listing — git when it can answer FOR THIS TREE, else a walk (the egg has no
# .git, and an egg unpacked inside another checkout gets a confident wrong
# answer from `git ls-files`, so the toplevel is compared first).
# ---------------------------------------------------------------------------

_WALK_PRUNE = frozenset({
    ".git", "node_modules", "__pycache__", ".pytest_cache", ".next",
    ".venv", "venv", "dist", "build", "out", "pgdata", "redisdata",
})


def _git_files() -> Optional[List[str]]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
    top = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=False, env=env)
    if top.returncode != 0 or not top.stdout.strip():
        return None
    if Path(top.stdout.strip()).resolve() != ROOT.resolve():
        return None
    listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                             capture_output=True, check=False, env=env)
    if listing.returncode != 0:
        return None
    return [raw.decode() for raw in listing.stdout.split(b"\0") if raw]


def _walk_files() -> List[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in _WALK_PRUNE)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            found.append(str(path.relative_to(ROOT)))
    return found


def _candidate_files() -> List[str]:
    listing = _git_files()
    if listing is None:
        listing = _walk_files()
    return sorted(p for p in listing if p.endswith(SUFFIXES))


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------

def strip_comments(rel: str, source: str) -> List[str]:
    """Whole-line comments blanked, everything else verbatim (line count kept)."""
    out = []
    for line in source.split("\n"):
        stripped = line.lstrip()
        if rel.endswith(".sh"):
            comment = stripped.startswith("#")
        else:
            comment = (stripped.startswith("//") or stripped.startswith("*")
                       or stripped.startswith("/*"))
        out.append("" if comment else line)
    return out


def bare_python3_lines(rel: str, source: str) -> List[Tuple[int, str]]:
    """(1-based line, text) for every bare `python3` outside a whole-line comment."""
    return [(n, line.strip())
            for n, line in enumerate(strip_comments(rel, source), start=1)
            if BARE_PYTHON3.search(line)]


def _is_test_source(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (".test." in name or ".spec." in name
            or name.startswith("test_") or name.startswith("test-")
            or "/tests/" in rel or "/__tests__/" in rel)


def plane_files() -> List[str]:
    """Unlocked, non-test, tracked exec-carrying files on the gap / pull plane."""
    on_plane = []
    for rel in _candidate_files():
        if _is_locked(rel) or _is_test_source(rel):
            continue
        try:
            source = (ROOT / rel).read_text(errors="replace")
        except OSError:
            continue
        # Comment-stripped: a file joins the plane by executing it, not by
        # mentioning it.
        code = "\n".join(strip_comments(rel, source))
        if any(token in code for token in PLANE_TOKENS):
            on_plane.append(rel)
    return on_plane


# ---------------------------------------------------------------------------
# The detector's own arms — the sensor proving it can go red at all, in both
# directions, without needing a mutated tree to find out.
# ---------------------------------------------------------------------------

class TestTheDetector:
    def test_a_bare_exec_string_is_a_finding(self):
        found = bare_python3_lines("x.ts", "const cmd = 'python3 script.py gaps list'")
        assert found and found[0][0] == 1

    def test_the_pinned_form_is_not(self):
        assert bare_python3_lines("x.ts", "const cmd = '%s script.py'" % PIN) == []

    def test_a_versioned_interpreter_is_not(self):
        assert bare_python3_lines("x.sh", "python3.12 -m framework.events.emitter") == []

    def test_an_absolute_path_to_the_box_interpreter_IS(self):
        assert bare_python3_lines("x.sh", "/usr/bin/python3 -c 'pass'") != []

    def test_prose_about_the_defect_is_not_the_defect(self):
        assert bare_python3_lines("x.sh", "# bare python3 on the box is 3.9") == []
        assert bare_python3_lines("x.ts", " * bare python3 on the box is 3.9") == []


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------

class TestA03InterpreterPin:
    def test_the_scope_is_not_empty_and_carries_every_named_anchor(self):
        """The degenerate end: a scanner that finds nothing reports success.

        Wired to the live artifacts — each A0.3-named anchor must be DISCOVERED
        by the same scope function the scan uses, not merely exist on disk.
        """
        scope = plane_files()
        assert len(scope) >= 4, "the plane scan found almost nothing: %s" % scope
        missing = [a for a in A03_NAMED_ANCHORS if a not in scope]
        assert missing == [], (
            "A0.3 names these anchors and the scan no longer sees them "
            "(renamed? deleted? relocked?): %s" % missing
        )

    def test_no_bare_python3_in_an_unlocked_plane_exec_string(self):
        findings = {}
        for rel in plane_files():
            if rel in PENDING:
                continue
            excused = SANCTIONED.get(rel, {})
            hits = [(n, text)
                    for n, text in bare_python3_lines(
                        rel, (ROOT / rel).read_text(errors="replace"))
                    if not any(code in text for code in excused)]
            if hits:
                findings[rel] = hits
        assert findings == {}, (
            "A0.3: unlocked exec strings on the gap/pull plane must pin `%s`.\n%s"
            % (PIN, "\n".join(
                "  %s:%d  %s" % (rel, n, text)
                for rel, hits in sorted(findings.items()) for n, text in hits))
        )

    def test_pending_entries_are_still_violating(self):
        """Self-retiring waivers.

        A waiver that survives its own fix is how an allowlist becomes a
        blanket. Each row must still name a real, present violation; when its
        owner lands the pin, THIS goes red and the row is deleted in the same
        commit.
        """
        stale = []
        for rel, why in sorted(PENDING.items()):
            path = ROOT / rel
            if not path.exists():
                stale.append("%s — file is gone (%s)" % (rel, why))
                continue
            if not bare_python3_lines(rel, path.read_text(errors="replace")):
                stale.append("%s — PINNED NOW, delete this PENDING row (%s)" % (rel, why))
        assert stale == [], "\n".join(stale)

    def test_sanctioned_lines_are_still_bare(self):
        """The excuse dies with the line it excuses.

        A sanctioned row claims a specific line REACHES the box interpreter on
        purpose. If it were pinned, moved or deleted, the row would be excusing
        nothing while still hiding whatever replaced it.
        """
        stale = []
        for rel, codes in sorted(SANCTIONED.items()):
            path = ROOT / rel
            if not path.exists():
                stale.append("%s — file is gone" % rel)
                continue
            hits = bare_python3_lines(rel, path.read_text(errors="replace"))
            for code, why in sorted(codes.items()):
                if not any(code in text for _, text in hits):
                    stale.append(
                        "%s — `%s` no longer carries a bare interpreter; delete "
                        "this SANCTIONED row (%s)" % (rel, code, why))
        assert stale == [], "\n".join(stale)

    def test_every_sanctioned_file_is_actually_on_the_plane(self):
        """An excuse for a file the scan never looks at hides nothing and
        misleads the next reader about what is covered."""
        scope = set(plane_files())
        assert set(SANCTIONED) <= scope, sorted(set(SANCTIONED) - scope)

    def test_a_sanctioned_file_is_not_a_sanctioned_file(self):
        """The narrowing itself, asserted: a second bare interpreter in a
        sanctioned file is STILL a finding."""
        rel = "cabinet/scripts/drills/one-responsibility.sh"
        excused = SANCTIONED[rel]
        source = 'BOX_PY="python3"\nrun_it python3 -c pass\n'
        hits = [(n, text) for n, text in bare_python3_lines(rel, source)
                if not any(code in text for code in excused)]
        assert [n for n, _ in hits] == [2]

    def test_every_pending_file_is_actually_on_the_plane(self):
        """A waiver for a file the scan never looks at hides nothing and
        misleads the next reader about what is covered."""
        scope = set(plane_files())
        assert set(PENDING) <= scope, sorted(set(PENDING) - scope)

    def test_the_locked_hook_is_excluded_because_it_cannot_be_pinned(self):
        """The other half of A0.3, asserted as an exclusion rather than assumed.

        `session-task-inject.sh` execs bare `python3` and is schg-locked: it is
        NOT a finding here, and the reason it is safe is that every module it
        imports is 3.9-correct — which its own tests assert.
        """
        rel = "cabinet/scripts/hooks/session-task-inject.sh"
        assert (ROOT / rel).exists()
        assert _is_locked(rel), "the hook left the locked set — A0.3's premise moved"
        assert rel not in plane_files()
        assert bare_python3_lines(rel, (ROOT / rel).read_text()), (
            "the locked hook no longer execs a bare interpreter — if it was "
            "pinned by a ceremony, this exclusion is obsolete"
        )


@pytest.mark.parametrize("rel", [
    "cabinet/dashboard/src/actions/gaps.ts",
    "cabinet/dashboard/src/lib/capability-gaps.ts",
    "cabinet/scripts/record-capability-gap.sh",
    "cabinet/cron/briefing.sh",
])
def test_the_gap_plane_exec_strings_carry_the_pin(rel):
    """Positive arm. The scan above is a NEGATIVE: deleting the exec string
    entirely would satisfy it. These four files must still say the pinned form.
    """
    assert PIN in (ROOT / rel).read_text(), "%s lost the `%s` pin" % (rel, PIN)
