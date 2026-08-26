"""The page that tells the Captain what each rung of autonomy does must be true.

It said *intend-to* meant "announce, act unless vetoed". Nothing sends that
announcement and nothing accepts a stop.

The finding that surfaced this framed it as the rung giving him LESS warning
than the more permissive rung above -- acting with no heads-up. Reading the code
says otherwise, and in the safe direction: `run_action_lane.ACT_VERDICTS`
deliberately excludes `auto_with_veto_window`, with a comment saying verdicts
must not promise unbuilt machinery. So work at that rung PROPOSES, exactly like
the rung below. He was never at risk of a surprise; he was at risk of expecting
an announcement that would never come, and of believing a rung had been earned
that changes nothing.

These arms hold both halves: the page must not claim the unbuilt behaviour, and
the lane must keep refusing to act on that verdict. If someone later wires the
announcement, the second arm goes red and the page has to be updated in the same
change -- which is the point of pinning it here rather than in a doc lint.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

PAGE = ROOT / "docs" / "how-your-cabinet-is-governed.md"


class ThePageDoesNotPromiseUnbuiltBehaviour(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PAGE.read_text()

    def test_it_no_longer_says_the_rung_announces_then_acts(self) -> None:
        self.assertNotIn("announce, act unless vetoed", self.text)

    def test_it_says_in_plain_words_what_the_rung_does_today(self) -> None:
        self.assertIn("proposes", self.text.lower())
        self.assertIn("nothing accepts a stop", self.text)

    def test_the_other_three_rungs_are_untouched(self) -> None:
        for rung in ("would-like-to", "ive-done", "ive-been-doing"):
            with self.subTest(rung):
                self.assertIn(rung, self.text)
        self.assertIn("propose\nfirst)", self.text.replace("*", ""))
        self.assertIn("act, report", self.text)
        self.assertIn("fully graduated", self.text)


class TheLaneStillRefusesToActOnIt(unittest.TestCase):
    def test_the_verdict_is_not_in_the_act_set(self) -> None:
        # The thing that makes the page's new sentence true. If this changes,
        # the page is wrong again and this arm says so.
        from framework.acting import run_action_lane

        self.assertNotIn("auto_with_veto_window", run_action_lane.ACT_VERDICTS)

    def test_the_rungs_below_and_above_are_where_the_page_says(self) -> None:
        from framework.acting import run_action_lane

        # `ive-done` maps to notify_after and DOES act -- so the page's claim
        # that the rung above is more permissive is checked, not assumed.
        self.assertIn("notify_after", run_action_lane.ACT_VERDICTS)

    def test_the_ladder_still_maps_the_rung_to_that_verdict(self) -> None:
        # If the mapping moved, this whole page section is about a rung that no
        # longer exists and the arms above would pass while saying nothing.
        from framework.learning import trust_ladder

        mapped = getattr(trust_ladder, "RUNG_TO_VERDICT", None) or {}
        if mapped:
            self.assertEqual(mapped.get("intend-to"), "auto_with_veto_window")
        else:
            self.assertIn("auto_with_veto_window",
                          Path(trust_ladder.__file__).read_text())


if __name__ == "__main__":
    unittest.main()
