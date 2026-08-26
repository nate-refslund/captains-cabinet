"""The one place the tree tells a stranger where the model lives must be true.

It pointed at a settings file that disclaims the value in its own words -- "The
LLM model is NOT parsed from this file" -- and had done since before anyone
noticed. A newcomer following the only pointer we give them landed on a file
that told them they were in the wrong place.

The sentence is now a claim about the world, so it gets a sensor. Both halves
matter: the corrected text must not name the disclaiming file as the owner, and
the pins it DOES name must still exist. A doc correction that rots back into a
lie six months later is the same defect with a later date.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DOCS = (ROOT / "CLAUDE.md", ROOT / "docs" / "templates" / "CLAUDE-egg.md")
# Every file the corrected sentence claims carries a model pin. If a pin moves
# and the sentence is not updated, this goes red rather than the doc quietly
# becoming wrong again.
CLAIMED_PINS = (
    "framework/acting/run_action_lane.py",
    "framework/fidelity/oauth_llm.py",
    "framework/frontdoor/actfirst_canary.py",
    "framework/onboarding/plan.py",
    "framework/onboarding/onboard.py",
)
MODEL_LITERAL = re.compile(r"""=\s*["']claude-[a-z0-9.\-\[\]]+["']""")


def routing_section(path: Path) -> str:
    text = path.read_text()
    start = text.index("## Model Routing")
    rest = text[start + len("## Model Routing"):]
    end = rest.find("\n## ")
    return rest[:end if end != -1 else len(rest)]


class TheClaimIsTrue(unittest.TestCase):
    def test_it_does_not_name_the_disclaiming_file_as_the_owner(self) -> None:
        disclaimer = (ROOT / "instance" / "config" / "platform.yml.example")
        if disclaimer.is_file():
            self.assertIn("NOT parsed from this file", disclaimer.read_text(),
                          "the disclaimer moved; this arm is now testing nothing")
        for doc in DOCS:
            with self.subTest(doc.name):
                section = routing_section(doc)
                self.assertNotRegex(
                    section,
                    r"Model IDs live in `instance/config/platform\.yml`",
                    "points at a file that disclaims the value")

    def test_every_file_the_sentence_names_still_carries_a_pin(self) -> None:
        for doc in DOCS:
            section = routing_section(doc)
            for pin in CLAIMED_PINS:
                name = Path(pin).name
                if name not in section:
                    continue
                with self.subTest(f"{doc.name}:{name}"):
                    target = ROOT / pin
                    self.assertTrue(target.is_file(), f"{pin} named but missing")
                    self.assertRegex(
                        target.read_text(), MODEL_LITERAL,
                        f"{pin} is named as carrying a model pin and no longer does")

    def test_the_two_documents_agree(self) -> None:
        # The egg twin is what a stranger reads. If they disagree, one of them
        # is lying to whichever reader gets it.
        first, second = (routing_section(d) for d in DOCS)
        self.assertEqual(first.strip().splitlines()[0], second.strip().splitlines()[0])

    def test_the_arm_can_fail(self) -> None:
        # If `routing_section` ever stopped finding the section it would return
        # nothing and every assertion above would pass vacuously.
        for doc in DOCS:
            with self.subTest(doc.name):
                self.assertGreater(len(routing_section(doc)), 200)


if __name__ == "__main__":
    unittest.main()
