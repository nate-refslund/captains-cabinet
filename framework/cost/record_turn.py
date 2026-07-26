"""CLI the Stop hook calls to meter one officer turn.

    PYTHONPATH=$CABINET_ROOT python3 -m framework.cost.record_turn \
        --transcript <path> --session <id> --officer <slug> [--project <slug>]

Prints a one-line summary to stdout (the hook routes it to stderr; the Stop
protocol needs stdout clean) and always exits 0: a metering failure must never
break an officer's turn.

The watermark lives in Redis under ``cabinet:cost:wm:<session_id>`` and is
advanced ONLY after the ledger write succeeds, so a Redis blip re-bills the
same lines on the next Stop rather than losing them. Over-counting a retry is
the correct direction of error for a watch that no longer gates anything.
"""

from __future__ import annotations

import argparse
import sys

from framework.cost import meter


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="framework.cost.record_turn")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--session", default="")
    ap.add_argument("--officer", default="")
    ap.add_argument("--project", default="")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and print, write nothing (used by the tests)")
    args = ap.parse_args(argv)

    officer = meter.safe_principal(args.officer)
    if officer == meter.UNATTRIBUTED:
        # An unattributed session still spent money, but writing it against a
        # bogus field would corrupt per-officer accounting. Say so loudly on
        # stderr rather than dropping it silently — with no spend cap left,
        # nothing else is watching this ledger.
        print("cost-meter: SKIP — no usable officer identity (OFFICER_NAME=%r); "
              "turn NOT metered" % (args.officer,))
        return 0

    # The Stop payload defaults session_id to the literal "unknown"; letting
    # that through would key every such session on ONE shared watermark, where a
    # long transcript's counter silently suppresses billing for a short one.
    session = args.session
    if meter.safe_principal(session) == meter.UNATTRIBUTED:
        session = officer
    from_line = 0 if args.dry_run else meter.read_watermark(session)
    sl = meter.parse_transcript(args.transcript, from_line=from_line)

    if sl.responses_billed == 0:
        # A transcript SHORTER than its watermark was rotated or replaced. Repair
        # the watermark even though there is nothing to bill, or the meter stays
        # dark for this session until the file grows past the stale mark.
        if sl.watermark_reset and not args.dry_run:
            meter.write_watermark(session, sl.lines_read)
            print("cost-meter: watermark reset (transcript shorter than mark) → %d"
                  % sl.lines_read)
        return 0

    if args.dry_run:
        print("cost-meter: DRY responses=%d cost=$%.4f in=%d out=%d cw=%d cr=%d dup_skipped=%d models=%s"
              % (sl.responses_billed, sl.cost_micro / 1e6, sl.input_tokens,
                 sl.output_tokens, sl.cache_write, sl.cache_read,
                 sl.duplicates_skipped, sl.models))
        return 0

    ok = meter.record_session_turn(officer, sl, project=args.project or None)
    if ok:
        meter.write_watermark(session, sl.lines_read)
        print("cost-meter: officer=%s responses=%d cost=$%.4f (was billed as 1 response "
              "before 2026-07-26) dup_skipped=%d" % (officer, sl.responses_billed,
                                                     sl.cost_micro / 1e6, sl.duplicates_skipped))
    else:
        # Watermark deliberately NOT advanced — retry next Stop.
        print("cost-meter: WARN ledger write failed; watermark held at %d, will re-bill "
              "%d responses next Stop" % (from_line, sl.responses_billed))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the officer's turn
        print("cost-meter: ERROR %s" % exc)
        sys.exit(0)
