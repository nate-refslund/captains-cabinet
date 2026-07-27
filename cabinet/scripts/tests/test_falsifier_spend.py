"""The durable per-day `spend` block in the falsifier series (2026-07-26).

The Redis cost ledgers expire after 8 days, so nothing on the box remembers
what a normal week costs — and an anomaly detector with no trailing baseline
is not a detector. This block is that history: one row per day, written by the
job that already runs daily, so it inherits its idempotence and needs no new
schedule and no new surface.

What is pinned here is mostly what the block REFUSES to say: an unpriced lane
gets no dollar figure, a day with no figures is null rather than zero, and
per-principal lane rows never fold back into the lane total.

Run: python3.12 -m pytest cabinet/scripts/tests/test_falsifier_spend.py -q
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPORT = _SCRIPTS_DIR / "falsifier-report.py"

_spec = importlib.util.spec_from_file_location("falsifier_report_under_test",
                                               str(_REPORT))
fr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fr)

NOW = dt.datetime(2026, 7, 26, 8, 5, tzinfo=dt.timezone.utc)
TOKENS = "cabinet:cost:tokens:daily:2026-07-26"
LANES = "cabinet:cost:lanes:daily:2026-07-26"


def _reader(hashes):
    def read(key):
        return dict(hashes.get(key, {}))
    return read


def test_spend_block_carries_the_days_officer_and_lane_figures():
    block = fr._spend_block(NOW, _reader({
        TOKENS: {"cos_cost_micro": "1500000", "cos_input": "40000",
                 "polads-ceo_polads_cost_micro": "500000"},
        LANES: {"advisor_cost_micro": "250000", "advisor_calls": "12",
                "advisor_units": "0",
                "advisor__cos_cost_micro": "250000", "advisor__cos_calls": "12",
                "tts_calls": "42", "tts_units": "9100"},
    }))
    assert block["date"] == "2026-07-26"
    assert block["total_cost_micro"] == 2_000_000
    # Keyed by the ledger PREFIX: meter.py joins officer and project with the
    # same "_" it uses before the dimension, so they cannot be split back
    # apart here without guessing, and guessing would invent an attribution.
    assert block["officers"] == {"cos": 1_500_000,
                                 "polads-ceo_polads": 500_000}
    assert block["lanes"]["advisor"] == {"cost_micro": 250_000, "calls": 12,
                                         "units": 0}


def test_per_principal_lane_rows_never_double_count_the_lane_total():
    """`advisor__cos_cost_micro` is a breakdown of `advisor_cost_micro`, not a
    second lane. Splitting on a single underscore would fold it back in and
    report double the spend — and a doubled baseline silently raises the bar
    every anomaly row compares against."""
    lanes = fr._parse_lane_fields({
        "advisor_cost_micro": "100", "advisor_calls": "2",
        "advisor__cos_cost_micro": "60", "advisor__cos_calls": "1",
        "advisor__svc:retro_cost_micro": "40", "advisor__svc:retro_calls": "1",
    })
    assert set(lanes) == {"advisor"}
    assert lanes["advisor"]["cost_micro"] == 100


def test_an_unpriced_lane_has_no_cost_field_not_a_zero_one():
    """meter.py records NO cost for a vendor it cannot price. Materialising a
    0 here would turn "we don't know what this costs" into "this is free" —
    the exact lie the meter exists to stop, and the reason the daily line
    renders those lanes as call counts."""
    lanes = fr._parse_lane_fields({"tts_calls": "42", "tts_units": "9100"})
    assert "cost_micro" not in lanes["tts"]
    assert lanes["tts"] == {"calls": 42, "units": 9100}


def test_null_when_unmeasurable_never_a_fake_zero():
    # No reader at all → the whole block is null.
    assert fr._spend_block(NOW, None) is None
    # Reader present, nothing came back → null figures, not zeros. A null day
    # must read as NO EVIDENCE downstream, never as "spent nothing".
    block = fr._spend_block(NOW, _reader({}))
    assert block["total_cost_micro"] is None
    assert block["officers"] is None and block["lanes"] is None
    # A day with a readable officer hash but no lane hash keeps them apart.
    half = fr._spend_block(NOW, _reader({TOKENS: {"cos_cost_micro": "7"}}))
    assert half["total_cost_micro"] == 7 and half["lanes"] is None


def test_a_raising_reader_degrades_instead_of_killing_the_daily_line():
    """The rest of the falsifier line must still append — the spend snapshot
    is telemetry, not a precondition."""
    def boom(key):
        raise RuntimeError("redis on fire")

    block = fr._spend_block(NOW, boom)
    assert block["total_cost_micro"] is None and block["lanes"] is None


def test_unparseable_values_are_skipped_not_guessed():
    block = fr._spend_block(NOW, _reader({
        TOKENS: {"cos_cost_micro": "1000", "broken_cost_micro": "NaN-ish"},
        LANES: {"advisor_cost_micro": "oops", "advisor_calls": "5"},
    }))
    assert block["total_cost_micro"] == 1000
    assert "broken" not in block["officers"]
    assert block["lanes"]["advisor"] == {"calls": 5}


def test_compute_line_includes_spend_and_leaves_cost_7d_alone():
    """Additive by construction: the new key rides alongside cost_7d, and
    cost_7d's numbers are untouched by the change."""
    line = fr.compute_line([], now=NOW, redis_hgetall=_reader({
        TOKENS: {"cos_cost_micro": "900000", "cos_input": "10", "cos_output": "4"},
    }))
    assert line["spend"]["total_cost_micro"] == 900_000
    assert line["cost_7d"]["cost_micro"] == 900_000      # same day, same source
    assert line["cost_7d"]["days_measured"] == 1
    # No reader → both degrade honestly, neither invents a figure.
    bare = fr.compute_line([], now=NOW)
    assert bare["spend"] is None
    assert bare["cost_7d"]["days_measured"] == 0
