"""Before acting alone, the system demands a source. It never checked it existed.

Measured on the code as it stood: an evidence tuple of `("",)` satisfied the
check, because `"" in anything` is True. The main gate on acting without the
Captain accepted a citation of nothing.

The sibling fence asks the OPPOSITE question -- does this evidence touch a
poisoned ref -- and its containment tolerance is safe there, because
over-matching only forces the propose-only default. Here the polarity is
reversed: an over-match says "a real source was cited" and lets the action go
ahead alone. Same tolerance, opposite consequence.

So the arms below come in two halves. The tolerance must survive, because a
model quotes a real ref with a leading `./`, a namespace prefix, a "see "
lead-in or a `#fragment`, and calling those invented would break real work.
And the degenerate comparands must not, because that is the hole.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework.acting.action_lane import (  # noqa: E402
    _CITATION_FLOOR,
    bundle_refs,
    cites_a_real_ref,
)

BUNDLE = {"3-People/alice.md", "2-Meetings/2026-08-01.md"}


class TheHoleIsClosed(unittest.TestCase):
    def test_a_citation_of_nothing_is_not_a_citation(self) -> None:
        # THE arm. This exact tuple passed before the fix.
        self.assertFalse(cites_a_real_ref(("",), BUNDLE))

    def test_whitespace_and_punctuation_are_not_citations(self) -> None:
        for degenerate in (" ", "\t", "/", ".", "a", "ab"):
            with self.subTest(degenerate):
                self.assertFalse(cites_a_real_ref((degenerate,), BUNDLE))

    def test_an_invented_reference_is_refused(self) -> None:
        self.assertFalse(cites_a_real_ref(("9-Nowhere/ghost.md",), BUNDLE))

    def test_no_citations_at_all_is_refused(self) -> None:
        for empty in ((), None, []):
            with self.subTest(repr(empty)):
                self.assertFalse(cites_a_real_ref(empty, BUNDLE))

    def test_an_empty_bundle_answers_no_to_everything(self) -> None:
        # With nothing to cite, nothing can have been cited. Answering yes here
        # would restore the hole through a different door.
        self.assertFalse(cites_a_real_ref(("3-People/alice.md",), set()))

    def test_a_short_ref_in_the_bundle_cannot_become_a_wildcard(self) -> None:
        # The floor applies to BOTH sides. A bundle carrying a one-character
        # ref must not make every citation valid.
        self.assertFalse(cites_a_real_ref(("anything at all",), {"a"}))


class TheToleranceSurvives(unittest.TestCase):
    """A re-spelled real ref is not an invented one. Losing this would make the
    fix break real work, which is the failure on the other side."""

    def test_exact(self) -> None:
        self.assertTrue(cites_a_real_ref(("3-People/alice.md",), BUNDLE))

    def test_the_shapes_a_model_actually_produces(self) -> None:
        for spelling in (
            "./3-People/alice.md",
            "vault/3-People/alice.md",
            "see 3-People/alice.md",
            "3-People/alice.md#top",
            "  3-People/alice.md  ",
        ):
            with self.subTest(spelling):
                self.assertTrue(cites_a_real_ref((spelling,), BUNDLE), spelling)

    def test_one_good_citation_among_junk_is_enough(self) -> None:
        self.assertTrue(cites_a_real_ref(("", " ", "3-People/alice.md"), BUNDLE))


class TheBundleReader(unittest.TestCase):
    def test_it_reads_the_fenced_refs(self) -> None:
        text = ("--- EMAIL ref=3-People/alice.md ---\n"
                "body\n"
                "--- MEETING ref=2-Meetings/2026-08-01.md ---\n"
                "more\n")
        self.assertEqual(bundle_refs(text), BUNDLE)

    def test_an_empty_or_absent_bundle_is_an_empty_set(self) -> None:
        for nothing in ("", None, "no fences here at all"):
            with self.subTest(repr(nothing)):
                self.assertEqual(bundle_refs(nothing), set())


class TheGuardIsNotVacuous(unittest.TestCase):
    def test_the_untended_predicate_would_have_matched_the_degenerates(self) -> None:
        # The guard's own vacuity witness: prove the naive containment check
        # this replaces DOES accept the empty citation, so the arms above are
        # testing a real difference rather than restating Python.
        naive = lambda cite, bundle: any(  # noqa: E731
            ref == cite or ref in cite or cite in ref for ref in bundle)
        self.assertTrue(naive("", BUNDLE), "the naive check should accept it")
        self.assertFalse(cites_a_real_ref(("",), BUNDLE), "the guarded one must not")

    def test_the_floor_is_a_real_number(self) -> None:
        self.assertGreaterEqual(_CITATION_FLOOR, 2)


if __name__ == "__main__":
    unittest.main()
