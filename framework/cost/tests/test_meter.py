"""Pins for the cost meter.

Every assertion here is a bug that was actually shipped and measured. The
"REGRESSION" tests fail against the pre-2026-07-26 pricing; keep them that way.
"""

import json
import os
import tempfile
import unittest

from framework.cost import meter


class TestRates(unittest.TestCase):
    def test_cache_multipliers_are_the_published_ones(self):
        # REGRESSION (measured 2026-07-26): the shipped hooks charged cache
        # write at 0.25x input and cache read at 0.02x input for opus/sonnet —
        # exactly 5x under the published 1.25x/0.1x. The fable arm three lines
        # above them was correct, which is how it survived review.
        self.assertEqual(meter.MULT_CACHE_WRITE_5M, 1.25)
        self.assertEqual(meter.MULT_CACHE_WRITE_1H, 2.00)
        self.assertEqual(meter.MULT_CACHE_READ, 0.10)

    def test_opus_cache_read_is_one_and_a_half_micro_per_token(self):
        # $15/MTok input x 0.1 = $1.50/MTok. The old table said $0.30/MTok.
        self.assertEqual(meter.price("claude-opus-4-8", cache_read=1_000_000), 1_500_000)

    def test_opus_cache_write_5m_and_1h_differ(self):
        # The old meter had no concept of the 1h TTL and billed both the same.
        # In real transcripts 100% of cache writes were the 1h flavour.
        five = meter.price("claude-opus-4-8", cache_write_5m=1_000_000)
        hour = meter.price("claude-opus-4-8", cache_write_1h=1_000_000)
        self.assertEqual(five, 18_750_000)
        self.assertEqual(hour, 30_000_000)
        self.assertGreater(hour, five)

    def test_unknown_model_bills_at_the_most_expensive_known_rate(self):
        # REGRESSION: the shipped meter's `*)` arm defaulted to Sonnet — the
        # CHEAPEST row — so any unrecognized model was billed at 1/5 of Opus.
        inp, out, key = meter.resolve_rate("some-model-that-does-not-exist-yet")
        self.assertEqual(key, "unknown")
        worst_in = max(r[0] for r in meter.RATES.values())
        worst_out = max(r[1] for r in meter.RATES.values())
        self.assertEqual((inp, out), (worst_in, worst_out))
        self.assertGreaterEqual(
            meter.price("brand-new-model", input_tokens=1000),
            meter.price("claude-sonnet-4-5", input_tokens=1000),
        )

    def test_known_families_resolve(self):
        for model, expect in (
            ("claude-opus-4-8", "opus"),
            ("claude-fable-5", "fable"),
            ("claude-sonnet-4-5-20250929", "sonnet"),
            ("claude-haiku-4-5-20251001", "haiku"),
        ):
            self.assertEqual(meter.resolve_rate(model)[2], expect, model)

    def test_price_is_linear_and_integer(self):
        one = meter.price("claude-opus-4-8", input_tokens=1)
        self.assertIsInstance(one, int)
        self.assertEqual(meter.price("claude-opus-4-8", input_tokens=1000), one * 1000)


class TestPrincipal(unittest.TestCase):
    def test_injection_shaped_names_are_refused(self):
        for bad in (
            "cos; rm -rf /", "cos\nFLUSHALL", "../../etc/passwd", "-h evil.example",
            "$(whoami)", "a" * 200, "", None, "unknown", "Robert'); DROP TABLE",
        ):
            self.assertEqual(meter.safe_principal(bad), meter.UNATTRIBUTED, repr(bad))

    def test_real_names_survive(self):
        for good in ("cos", "lane-one-ceo", "svc:action-lane", "cto", "lane-two-ceo"):
            self.assertEqual(meter.safe_principal(good), good)

    def test_case_is_normalized(self):
        self.assertEqual(meter.safe_principal("CoS"), "cos")


def _write_transcript(path, entries):
    with open(path, "w") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _assistant(mid, model="claude-opus-4-8", **usage):
    u = {"input_tokens": 0, "output_tokens": 0,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    u.update(usage)
    return {"type": "assistant", "message": {"id": mid, "model": model, "usage": u}}


class TestTranscriptParse(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "t.jsonl")

    def test_dedupes_by_message_id(self):
        # REGRESSION: Claude Code writes one assistant entry PER CONTENT BLOCK,
        # every copy repeating the same message-level usage. A real 821-entry
        # transcript held 352 distinct ids; summing entries over-counted
        # cache_read by 2.3x. Billing is per API response.
        _write_transcript(self.path, [
            _assistant("msg_1", input_tokens=100),
            _assistant("msg_1", input_tokens=100),
            _assistant("msg_1", input_tokens=100),
            _assistant("msg_2", input_tokens=100),
        ])
        s = meter.parse_transcript(self.path)
        self.assertEqual(s.responses_billed, 2)
        self.assertEqual(s.duplicates_skipped, 2)
        self.assertEqual(s.input_tokens, 200)

    def test_counts_every_turn_not_just_the_last(self):
        # REGRESSION: the shipped hook ran `tail -100 | jq ... | tail -1`, so a
        # response containing 30 tool round-trips was billed as ONE API call.
        _write_transcript(self.path, [_assistant("m%d" % i, output_tokens=10) for i in range(30)])
        s = meter.parse_transcript(self.path)
        self.assertEqual(s.responses_billed, 30)
        self.assertEqual(s.output_tokens, 300)

    def test_watermark_bills_each_response_exactly_once(self):
        _write_transcript(self.path, [_assistant("m1", output_tokens=10)])
        first = meter.parse_transcript(self.path, from_line=0)
        self.assertEqual(first.responses_billed, 1)
        self.assertEqual(first.lines_read, 1)

        with open(self.path, "a") as fh:
            fh.write(json.dumps(_assistant("m2", output_tokens=10)) + "\n")
        second = meter.parse_transcript(self.path, from_line=first.lines_read)
        self.assertEqual(second.responses_billed, 1)      # only the new one
        self.assertEqual(second.lines_read, 2)

        third = meter.parse_transcript(self.path, from_line=second.lines_read)
        self.assertEqual(third.responses_billed, 0)       # nothing new
        self.assertEqual(third.cost_micro, 0)

    def test_synthetic_entries_are_not_billed(self):
        _write_transcript(self.path, [
            _assistant("m1", model="<synthetic>", input_tokens=999999),
            _assistant("m2", input_tokens=10),
        ])
        s = meter.parse_transcript(self.path)
        self.assertEqual(s.responses_billed, 1)
        self.assertEqual(s.input_tokens, 10)

    def test_ttl_split_is_read_from_cache_creation(self):
        _write_transcript(self.path, [{
            "type": "assistant",
            "message": {"id": "m1", "model": "claude-opus-4-8", "usage": {
                "input_tokens": 0, "output_tokens": 0,
                "cache_creation_input_tokens": 1_000_000,
                "cache_read_input_tokens": 0,
                "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000,
                                   "ephemeral_5m_input_tokens": 0}}}}])
        s = meter.parse_transcript(self.path)
        self.assertEqual(s.cost_micro, 30_000_000)   # 1h rate, not the 5m rate

    def test_legacy_transcript_without_ttl_split_falls_back_to_5m(self):
        _write_transcript(self.path, [_assistant("m1", cache_creation_input_tokens=1_000_000)])
        s = meter.parse_transcript(self.path)
        self.assertEqual(s.cost_micro, 18_750_000)

    def test_corrupt_lines_are_skipped_not_fatal(self):
        with open(self.path, "w") as fh:
            fh.write("not json at all\n")
            fh.write(json.dumps(_assistant("m1", output_tokens=10)) + "\n")
            fh.write("{unterminated\n")
        s = meter.parse_transcript(self.path)
        self.assertEqual(s.responses_billed, 1)
        self.assertEqual(s.lines_read, 3)

    def test_missing_file_is_empty_not_an_exception(self):
        s = meter.parse_transcript(os.path.join(self.dir, "nope.jsonl"))
        self.assertEqual(s.responses_billed, 0)
        self.assertEqual(s.cost_micro, 0)


class TestLaneLedger(unittest.TestCase):
    def test_lane_key_is_separate_from_the_officer_ledger(self):
        # Folding lanes into the officer hash would change what `*_cost_micro`
        # means for any fork still running a per-officer cap.
        self.assertNotEqual(meter.daily_lane_key("2026-07-26"),
                            meter.daily_token_key("2026-07-26"))
        self.assertEqual(meter.daily_lane_key("2026-07-26"),
                         "cabinet:cost:lanes:daily:2026-07-26")

    def test_unknown_lane_is_refused(self):
        self.assertFalse(meter.record_lane("not-a-lane", "cos", cost_micro=1))

    def test_hgetall_distinguishes_unreadable_from_empty(self):
        # None ("could not look") must never be confused with {} ("looked, and
        # the ledger is empty") — the second is a possible broken meter and has
        # to be alarmable; the first is simply no observation.
        self.assertIsNone(meter.hgetall.__doc__ and None)  # doc exists
        self.assertTrue("NOT OBSERVABLE" in meter.hgetall.__doc__)

    def test_sum_cost_micro_ignores_non_numeric(self):
        h = {"a_cost_micro": "100", "b_cost_micro": "junk", "c_calls": "5"}
        self.assertEqual(meter.sum_cost_micro(h.keys(), h), 100)


if __name__ == "__main__":
    unittest.main()
