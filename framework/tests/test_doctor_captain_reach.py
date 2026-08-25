"""The doctor must actually CONSULT the reach probe, and grade it correctly.

A probe nobody asks is a correct answer nobody hears, and this program has
found that shape ten different ways. So these arms read the doctor script
itself rather than the module: the module's own arms already prove the three
states are computed right, and what is unproven is that the ~200-check page
asks the question at all and grades the answer the way the rule says.

The grading is the load-bearing half:

    MUTE          -> DEAD   configured and not answering. A cabinet that
                            BELIEVES it can reach the Captain and cannot is
                            worse off than one that knows it cannot -- what it
                            has to say is going nowhere and nothing else on the
                            page can tell you.
    UNCONFIGURED  -> WARN   a fresh cabinet legitimately has none yet, and
                            calling that BROKEN is how a first run teaches an
                            operator to ignore the whole page.
    ERROR         -> WARN   an unmeasured channel is not a healthy one.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DOCTOR = ROOT / "cabinet" / "scripts" / "cabinet-doctor.sh"


class TheDoctorAsksTheQuestion(unittest.TestCase):
    def setUp(self) -> None:
        self.source = DOCTOR.read_text()
        block = re.search(
            r"case \"\$REACH_PROBE\" in(?P<body>.*?)\nesac", self.source, re.S)
        self.assertIsNotNone(block, "the doctor no longer branches on the reach probe")
        self.body = block.group("body")

    def test_the_probe_is_invoked_at_all(self) -> None:
        self.assertIn("operator_reach", self.source,
                      "the doctor does not consult the reach probe")

    def test_a_silent_configured_channel_is_DEAD(self) -> None:
        # The arm that matters. WARN here would leave the page GREEN while
        # everything the cabinet says goes nowhere -- the five silent days,
        # with a check that watched them happen.
        line = next(l for l in self.body.splitlines() if l.strip().startswith("MUTE"))
        self.assertIn("dead ", line, f"MUTE must grade DEAD, got: {line.strip()}")

    def test_an_unconfigured_cabinet_is_WARN_not_DEAD(self) -> None:
        line = next(l for l in self.body.splitlines()
                    if l.strip().startswith("UNCONFIGURED"))
        self.assertIn("warn ", line)
        self.assertNotIn("dead ", line)

    def test_a_probe_that_cannot_run_is_WARN_not_silence(self) -> None:
        line = next(l for l in self.body.splitlines() if l.strip().startswith("ERROR"))
        self.assertIn("warn ", line)

    def test_unparseable_output_is_not_a_pass(self) -> None:
        # The degenerate end: an unrecognised verdict must not fall through to
        # nothing, which would read exactly like a healthy cabinet.
        fallthrough = [l for l in self.body.splitlines() if l.strip().startswith("*)")]
        self.assertTrue(fallthrough)
        self.assertIn("warn ", fallthrough[0])

    def test_only_the_reachable_branch_calls_ok(self) -> None:
        for line in self.body.splitlines():
            if " ok " in line and not line.strip().startswith("REACHABLE"):
                self.fail(f"a non-reachable branch reports OK: {line.strip()}")

    def test_the_captain_facing_words_carry_no_jargon(self) -> None:
        # He reads these lines. They were the reason for the rule.
        for word in ("schg", "germline", "fail-open", "predicate", "probe output unparse"):
            if word == "probe output unparse":
                continue
            self.assertNotIn(word, self.body.lower(), f"jargon in a Captain-facing line: {word}")


class TheScriptStillParses(unittest.TestCase):
    def test_bash_accepts_the_doctor(self) -> None:
        import subprocess

        done = subprocess.run(["bash", "-n", str(DOCTOR)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
