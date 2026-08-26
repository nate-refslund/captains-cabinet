"""A ruling the Captain made, and a note somebody wrote about it, are not the
same record.

The embedder split the decisions ledger on `^## ` alone. A
`### officer-note … [trust:officer]` block lives INSIDE an H2 region, so it was
fused into the Captain's entry, stamped `trust: "captain"`, and dated with his
entry's date. The team's own observations were filed as his rulings, and
nothing downstream reading this record could tell one from the other.

His own words on why this matters at every altitude, given while approving the
fix: *"some captains like me only want to take very high level decisions and let
AI's full autonomy and authority take it from there."* A single ruling can drive
months of work — which makes attribution more load-bearing where he touched
least, not less.

`cabinet/scripts/memory-distill.py` already parses it correctly: it breaks at
the first `### officer-note` and never treats that region as law. The arms below
pin the embedder onto that same rule, and one of them reads the distiller
directly so the convergence target is a real implementation rather than my
belief about one.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "cabinet" / "scripts" / "hooks" / "post-file-write-memory.sh"

LEDGER = """# Captain decisions

## 2026-08-01 — Ship the thing

- Do it the fast way.
- Do not wait for the review.

### officer-note 2026-08-04 [trust:officer]

- I think the fast way will cost us later.
- Recording this in case it does.

## 2026-08-09 — Second ruling

- Unrelated.
"""


def split_entry(entry: str) -> tuple[str, str]:
    """Drive the hook's own awk programs, not a Python re-implementation.

    A re-implementation would test my belief about the parser. These are the
    two lines the shell actually runs.
    """
    body = subprocess.run(
        ["awk", "/^### officer-note/{exit} {print}"],
        input=entry, capture_output=True, text=True, check=True).stdout
    notes = subprocess.run(
        ["awk", "/^### officer-note/{seen=1} seen{print}"],
        input=entry, capture_output=True, text=True, check=True).stdout
    return body, notes


def first_entry(text: str) -> str:
    parts = text.split("\n## ")
    return "## " + parts[1] if len(parts) > 1 else text


class TheCaptainsEntryCarriesOnlyHisWords(unittest.TestCase):
    def setUp(self) -> None:
        self.body, self.notes = split_entry(first_entry(LEDGER))

    def test_the_officer_note_is_not_in_his_ruling(self) -> None:
        # THE arm. Before the fix this text sat inside a row stamped
        # trust:captain, dated 2026-08-01 — a note written three days later,
        # by somebody else, filed as his.
        self.assertNotIn("cost us later", self.body)
        self.assertNotIn("officer-note", self.body)

    def test_his_actual_ruling_survives_intact(self) -> None:
        self.assertIn("Ship the thing", self.body)
        self.assertIn("Do it the fast way", self.body)
        self.assertIn("Do not wait for the review", self.body)

    def test_the_note_is_kept_rather_than_dropped(self) -> None:
        # Losing it would trade one wrong attribution for a different kind of
        # missing record.
        self.assertIn("cost us later", self.notes)
        self.assertIn("officer-note", self.notes)

    def test_an_entry_with_no_note_is_unchanged(self) -> None:
        plain = "## 2026-08-09 — Second ruling\n\n- Unrelated.\n"
        body, notes = split_entry(plain)
        self.assertEqual(body.strip(), plain.strip())
        self.assertEqual(notes.strip(), "")


class TheHookSaysWhoseWordsThoseAre(unittest.TestCase):
    def test_the_two_rows_carry_different_trust(self) -> None:
        source = HOOK.read_text()
        self.assertIn('trust: "captain"', source)
        self.assertIn('trust: "officer"', source)

    def test_the_captain_row_queues_the_body_not_the_whole_entry(self) -> None:
        # The defect was one variable. If it comes back, it comes back here.
        source = HOOK.read_text()
        self.assertIn('"$body" "$meta"', source)
        self.assertNotIn('"$entry" "$meta"', source)


class TheConvergenceTargetIsReal(unittest.TestCase):
    def test_the_distiller_already_breaks_at_the_officer_note(self) -> None:
        # Read the implementation this converges onto rather than trusting a
        # description of it.
        distiller = (ROOT / "cabinet" / "scripts" / "memory-distill.py").read_text()
        self.assertIn('startswith("### officer-note")', distiller)
        self.assertIn("break", distiller)


if __name__ == "__main__":
    unittest.main()
