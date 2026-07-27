"""framework.cost — the cabinet's ONE cost meter.

Every path that spends money prices it here. Before this module the rate table
was duplicated inline in two shell hooks and drifted: cache tokens were charged
at 0.25x/0.02x of the input rate instead of the documented 1.25x/0.1x, and the
1-hour cache TTL (2.0x) was billed as if it were the 5-minute one. Measured
against 279 real transcripts the shipped meter under-reported by 16.0x.

Two rules keep that from recurring:

  * Cache prices are DERIVED from the input rate by the published multipliers
    (see MULT_*), never typed in as separate literals. A wrong cache price now
    requires editing a multiplier that is asserted by a test.
  * An UNKNOWN model resolves to the most expensive known rate, never the
    cheapest. Every estimation error in this module must fail toward
    OVER-reporting, because the cabinet no longer blocks on spend (Captain
    2026-07-26 "unlimited spending") and the meter is therefore a WATCH, not a
    gate. A watch that under-reports is worse than no watch at all.

See docs/cost-metering.md.
"""

from .meter import (  # noqa: F401
    LANES,
    MULT_CACHE_READ,
    MULT_CACHE_WRITE_1H,
    MULT_CACHE_WRITE_5M,
    RATES,
    TranscriptSlice,
    daily_lane_key,
    daily_token_key,
    parse_transcript,
    price,
    record_lane,
    resolve_rate,
    safe_principal,
)
