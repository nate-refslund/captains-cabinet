"""The cancel window is machinery nobody calls.

`framework/authority/veto.py` builds the whole thing -- queue a veto, kill the
draft, scan and send when the window closes. It has **zero non-test callers**.
So an action class allowed to proceed on the promise that the Captain gets a
window to stop it proceeds on a promise nothing keeps: the first person to reach
for the handle finds there is none.

WHY THIS IS A SENSOR AND NOT A FIX. Wiring the plane is a change to what the
cabinet does without him, and picking WHERE to wire it is the decision -- there
are several call sites it could plausibly hang from, and choosing one silently
would be exactly the kind of direction change that is his to make. What can be
done without him, and what this does, is make the gap impossible to forget:
this arm is RED for as long as the plane stays unwired, so the promise cannot
quietly go on being made.

The moment a real caller appears, the arm goes green on its own and stops
nagging. That is the shape a sensor should have -- it retires itself when the
thing it watches is fixed, rather than needing someone to remember to delete it.

DELIBERATELY A STATIC SCAN. It imports none of the authority modules and calls
no gate function, so no verdict-resolution behaviour can affect what it reports.
A reviewer can confirm that by reading the import block.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# The plane's entry points. Word-boundary matched, never a substring scan: a
# plain `in` would count `_validate_skill_draft` as a `kill_draft` caller and
# the sensor would be vacuously green from the day it was written.
ENTRY_POINTS = ("enqueue_veto", "scan_and_send", "kill_draft")
SYMBOL = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(ENTRY_POINTS) + r")(?![A-Za-z0-9_])")

DEFINITION_SITE = ROOT / "framework" / "authority" / "veto.py"
SKIP_PARTS = {"tests", "docs", "patches", "node_modules", ".git"}


def production_files():
    for pattern in ("**/*.py", "**/*.sh"):
        for path in ROOT.glob(pattern):
            if SKIP_PARTS & set(path.parts):
                continue
            if path == DEFINITION_SITE:
                continue        # the definition is not a caller
            yield path


def callers() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in production_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in SYMBOL.finditer(text):
            found.setdefault(match.group(1), []).append(
                str(path.relative_to(ROOT)))
    return found


class TheSensorIsNotVacuous(unittest.TestCase):
    """Two controls. Without them a scan that silently matched nothing -- a bad
    root, a typo in the pattern -- would report "no callers" forever and look
    exactly like a correct sensor."""

    def test_it_can_see_files_at_all(self) -> None:
        self.assertGreater(len(list(production_files())), 200,
                           "the scan surface is empty, so its verdict is meaningless")

    def test_word_boundaries_do_not_match_a_longer_name(self) -> None:
        # The named trap: `_validate_skill_draft` must not count as a
        # `kill_draft` caller.
        self.assertIsNone(SYMBOL.search("def _validate_skill_draft(self):"))
        self.assertIsNotNone(SYMBOL.search("veto.kill_draft(row)"))
        self.assertIsNotNone(SYMBOL.search("    enqueue_veto(card)"))


class TheCancelWindowHasSomeoneToCallIt(unittest.TestCase):
    # XFAIL, STRICT, and the strictness is the whole point. A plain red arm
    # would break the suite for everyone until someone got round to it, and
    # the usual answer to that is to skip it -- which turns a live sensor into
    # a disabled one, the exact failure this codebase keeps finding.
    #
    # Strict xfail is the opposite: it asserts the gap EXISTS. The day a real
    # caller appears this arm XPASSes and ERRORS, forcing whoever wired it to
    # come here, delete the marker, and confirm on the record that the promise
    # is now kept. The sensor retires itself and cannot be quietly satisfied.
    @pytest.mark.xfail(
        strict=True,
        reason="the cancel window is built and nothing calls it; wiring it is "
               "a change to what the cabinet does unattended and WHERE it hangs "
               "is the Captain's call. Delete this marker in the commit that "
               "wires it.")
    def test_the_veto_plane_is_wired(self) -> None:
        found = callers()
        self.assertTrue(
            found,
            "The cancel window is built and nothing calls it. An action class "
            "that proceeds on the promise of a window to stop it is making a "
            "promise nothing keeps -- the first person to reach for the handle "
            "finds there is none.\n\n"
            "Wiring it is the Captain's call: it changes what the cabinet does "
            "without him, and WHERE it hangs is the decision. This arm stays "
            "red until it is wired, so the promise cannot quietly go on being "
            "made, and it goes green on its own the moment a real caller "
            f"appears.\n\nEntry points with no caller: {', '.join(ENTRY_POINTS)}")


if __name__ == "__main__":
    unittest.main()
