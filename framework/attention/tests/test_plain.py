"""framework.attention.plain — PLAIN-LANGUAGE LAW teeth (pytest side).

Pins: every table value + every renderable sentence lints clean; the linter
actually bites (mutation proof); the committed dashboard plain.json is
byte-equivalent to export_plain_json() (one source of truth, drift-guarded).
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from framework.attention import plain

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

GOLDEN_CARD = {
    "id": "sit-x", "kind": "action-proposal", "state": "pending",
    "pid": "prop-abc", "what": "Reply to Sofie about the DPA redline",
    "deadline_iso": "2026-07-12T10:00:00Z", "age_h": 47.0,
    "blast": {"class": "external", "reach": "external"},
    "blast_worst_case": "a message reaches a human outside the machine",
    "why_now": {"decay": "waiting 47h; 2 demotions"},
    "one_tap": {"approve": "direct", "veto": "direct", "defer": "direct"},
    "lane": "testburg",
}


def card(**over):
    c = dict(GOLDEN_CARD)
    c.update(over)
    return c


def all_table_strings() -> list:
    out = []
    out += list(plain.KIND_NAMES.values()) + [plain.KIND_NAME_DEFAULT]
    out += list(plain.STATE_NAMES.values()) + [plain.STATE_NAME_DEFAULT]
    out += list(plain.RISK_SENTENCES.values())
    out += [plain.RISK_DEFAULT, plain.RISK_DEFAULT_CEILING]
    for labels in plain.BUTTON_LABELS.values():
        out += list(labels)
    for verbs in plain.DOOR_BUTTONS.values():
        out += list(verbs.values())
    out += list(plain.MESSAGES.values()) + list(plain.RESULTS.values())
    out += list(plain.CONSEQUENCE_TEMPLATES.values())
    out += list(plain.UNDO_TEMPLATES.values())
    out += list(plain.COPY.values())
    out += list(plain.BANNED.values())  # replacements must themselves be plain
    return out


class TestTablesLintClean(unittest.TestCase):
    def test_every_table_value_is_plain(self):
        for s in all_table_strings():
            self.assertEqual(plain.lint(s), [], f"table string leaks: {s!r}")

    def test_every_kind_and_state_render_is_plain(self):
        kinds = list(plain.KIND_NAMES) + ["mystery-kind"]
        states = list(plain.STATE_NAMES) + ["weird-state"]
        for kind in kinds:
            for state in states:
                c = card(kind=kind, state=state)
                texts = [plain.plain_summary(c, now=NOW)]
                for verb in ("approve", "no", "later"):
                    texts.append(plain.consequence_for(c, verb))
                    texts.append(plain.undo_for(c, verb))
                for t in texts:
                    self.assertEqual(
                        plain.lint(t), [],
                        f"kind={kind} state={state} leaks: {t!r}")

    def test_every_risk_rewrite_and_fallbacks(self):
        for raw in list(plain.RISK_SENTENCES) + ["unknown worst case", None]:
            c = card(blast_worst_case=raw,
                     blast={"class": "ceiling" if raw is None else "low",
                            "reach": "internal"})
            s = plain.plain_summary(c, now=NOW)
            self.assertEqual(plain.lint(s), [], f"risk={raw!r} leaks: {s!r}")

    def test_degraded_cards_stay_plain(self):
        c = card(what=None, lane=None, age_h=None, deadline_iso=None,
                 blast=None, blast_worst_case=None, why_now=None, pid=None)
        s = plain.plain_summary(c, now=NOW)
        self.assertIn(plain.COPY["no_title"], s)
        self.assertEqual(plain.lint(s), [])


class TestSummaryShape(unittest.TestCase):
    def test_one_sentence_summary_reads_plain(self):
        s = plain.plain_summary(GOLDEN_CARD, now=NOW)
        self.assertIn("Suggestion — testburg: Reply to Sofie", s)
        self.assertIn("real person outside", s)
        self.assertIn("waiting 47 hours", s.lower())
        self.assertIn("due in", s)

    def test_decay_rewrite(self):
        self.assertEqual(
            plain.decay_plain("waiting 47h; 2 demotions"),
            "Waiting 47 hours — I've quietly bumped this down 2 times.")
        self.assertEqual(plain.decay_plain("waiting 3h; 0 demotions"),
                         "Waiting 3 hours.")
        self.assertEqual(
            plain.decay_plain("the Chair is holding a judgment open"),
            plain.RISK_SENTENCES["the Chair is holding a judgment open"])
        # Unknown producer shapes are dropped, never echoed.
        self.assertEqual(plain.decay_plain("charter demotion cascade"), "")

    def test_clock_words(self):
        self.assertEqual(plain.age_plain(0.4), "waiting under an hour")
        self.assertEqual(plain.age_plain(1.0), "waiting 1 hour")
        self.assertEqual(plain.age_plain(72.0), "waiting 3 days")
        self.assertEqual(plain.due_plain("2026-07-09T12:00:00Z", NOW), "overdue")
        self.assertEqual(plain.due_plain("2026-07-11T12:00:00Z", NOW),
                         "due in 24 hours")
        self.assertEqual(plain.due_plain("2026-07-19T12:00:00Z", NOW),
                         "due 2026-07-19")

    def test_ceiling_undo_is_honest(self):
        # Internal ceiling: hard-to-undo warning.
        c = card(blast={"class": "ceiling", "reach": "org"},
                 blast_worst_case=None)
        self.assertEqual(plain.undo_for(c, "approve"),
                         plain.UNDO_TEMPLATES["approve:ceiling"])
        # External reach beats ceiling: once fired it LEFT the machine —
        # never promise a pull-back.
        c = card(blast={"class": "ceiling", "reach": "external"})
        self.assertEqual(plain.undo_for(c, "approve"),
                         plain.UNDO_TEMPLATES["approve:no-return"])

    def test_no_return_undo_never_promises_a_pullback(self):
        # The two highest-stakes confirms: money out, external message.
        for worst in sorted(plain.NO_RETURN_WORST_CASES):
            c = card(blast={"class": "org", "reach": "org"},
                     blast_worst_case=worst)
            self.assertEqual(plain.undo_for(c, "approve"),
                             plain.UNDO_TEMPLATES["approve:no-return"], worst)
            self.assertNotIn("pulled back from the receipt",
                             plain.undo_for(c, "approve"))
        # External reach alone is enough.
        c = card(blast={"class": "org", "reach": "external"},
                 blast_worst_case=None)
        self.assertEqual(plain.undo_for(c, "approve"),
                         plain.UNDO_TEMPLATES["approve:no-return"])
        # A plain internal reversible keeps the receipt-undo promise.
        c = card(blast={"class": "low", "reach": "internal"},
                 blast_worst_case=None)
        self.assertIn("pulled back", plain.undo_for(c, "approve"))

    def test_kind_risk_defaults(self):
        # A question has no "I go ahead with it"; a ratification runs nothing.
        q = {"kind": "pipe-prompt", "what": "Include the private calendar?"}
        self.assertEqual(plain.risk_sentence(q),
                         plain.KIND_RISK_DEFAULTS["pipe-prompt"])
        r = {"kind": "outcome-ratification", "what": "Goal sign-off — testburg"}
        self.assertEqual(plain.risk_sentence(r),
                         plain.KIND_RISK_DEFAULTS["outcome-ratification"])
        # Exact producer strings and ceiling still win over kind defaults.
        q2 = dict(q, blast={"class": "ceiling"})
        self.assertEqual(plain.risk_sentence(q2), plain.RISK_DEFAULT_CEILING)

    def test_escalation_door_is_decidable(self):
        # An either/or headline must never get a generic [✓ Approve].
        btns = plain.door_buttons("escalation")
        self.assertEqual(btns["approve"], "I'll decide")
        self.assertEqual(btns["no"], "Ask the Chair")
        c = {"kind": "escalation",
             "what": "Two officers disagree: ship the beta, or hold it"}
        approve = plain.consequence_for(c, "approve")
        self.assertIn("Nothing runs yet", approve)
        self.assertNotIn("I go ahead", approve)
        self.assertIn("The Chair settles it", plain.consequence_for(c, "no"))


class TestLinterBites(unittest.TestCase):
    def test_mutation_proof(self):
        hits = plain.lint("verdicts happen in the Telegram binder")
        self.assertEqual([v["term"] for v in hits], ["verdicts", "binder"])

    def test_word_boundaries(self):
        self.assertEqual(plain.lint("rapid progress"), [])          # not 'pid'
        self.assertEqual(plain.lint("t2-rubric.md"), [])            # joined id
        self.assertEqual(len(plain.lint("the T2 queue")), 1)
        self.assertEqual(plain.lint("parked until Monday"), [])

    def test_a_planted_template_violation_turns_red(self):
        mutated = plain.COPY["footer_hint"] + " — check the census"
        self.assertTrue(plain.lint(mutated))


class TestExportDrift(unittest.TestCase):
    def test_committed_dashboard_json_matches_export(self):
        repo = Path(__file__).resolve().parents[3]
        committed = repo / ("cabinet/dashboard/src/lib/attention/plain.json")
        self.assertTrue(committed.exists(),
                        "run: python3.12 -m framework.attention.plain --export "
                        "> cabinet/dashboard/src/lib/attention/plain.json")
        self.assertEqual(json.loads(committed.read_text(encoding="utf-8")),
                         plain.export_plain_json(),
                         "plain.json drifted — regenerate from the module")


if __name__ == "__main__":
    unittest.main()
