#!/usr/bin/env python3.12
"""card-flatline-probe.py — is the proactive-card channel still speaking?

The FLEET half of the channel-flatline alarm (the Captain-facing half is one
line in the twice-daily digest / briefing card — see
``framework/frontdoor/card_flatline.py``). This script reads the daily
emission series that ``cabinet/scripts/falsifier-report.py`` appends to
(``shared/interfaces/falsifier-series.jsonl``) and classifies the card channel
in one token line for ``cabinet/scripts/cabinet-doctor.sh``.

It exists because the Captain-facing line is deliberately once-per-episode: it
asks its question and then goes quiet even though the channel is still dark.
The doctor needs the OPPOSITE property — a standing signal for as long as the
condition holds — so both halves read the same verdict and render it under
different rules. That split is also what covers the one case the pure verdict
cannot see on its own: a deliberate window (a disabled fleet row, a declared
absence) that ENDS in the middle of a silence suppresses the one-time question,
and this probe keeps reporting BREACH until cards come back.

READ-ONLY, by construction: no DB, no network, no Redis, no writes of any kind
— one file read plus (through ``read_gates``) the fleet manifest and the
Captain's own declarations. Safe to run at any time, from anywhere.

Modes:
  --probe    print ONE classified token line for cabinet-doctor, exit 0 always
             (a probe that exits non-zero turns a quality finding into a
             fleet-dead verdict). Vocabulary:
               NOSERIES / NEVERACTIVE / OK … / NOSYNC … / QUIET … /
               SILENT … / BREACH … / UNMEASURED … / STALE … / ERROR …
  (default)  one human line + the same verdict as JSON on request; exit 0 when
             the channel is healthy, explained, or unmeasurable, and 1 on a
             BREACH so a hand-run is scriptable.
  --json     print the whole verdict dict (both modes).

Tests: cabinet/scripts/tests/test_card_flatline_probe.py.
Reading: docs/runbooks/card-flatline-alarm.md.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-21
ownership-on-GO ruling, on the Captain's GO of 2026-07-27 for the queued
Captain-Seat follow-ups.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.frontdoor import card_flatline  # noqa: E402


def read_series(path: "Path | None" = None) -> List[Dict[str, Any]]:
    """Parse the emission series, oldest first. A missing file is [] (the
    daily job may never have run on this box) and a corrupt line is skipped —
    one bad append must never cost the good history. Mirrors
    ``tell_digest.read_falsifier_series`` deliberately: the probe must not need
    the digest's live-ledger imports just to read one jsonl."""
    p = Path(path) if path is not None else card_flatline.series_path()
    out: List[Dict[str, Any]] = []
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except ValueError:
                    continue
                if isinstance(doc, dict):
                    out.append(doc)
    except OSError:
        return []
    return out


def verdict(*, series_path: "Path | None" = None,
            root: "Path | None" = None) -> Dict[str, Any]:
    """The one verdict both modes render. Never raises: any failure degrades
    to an ERROR verdict carrying only the exception CLASS name (never a
    message, which can echo a path or a config value)."""
    try:
        # THE FLEET AUDIENCE. This probe feeds the standing health page, not a
        # question put to the Captain -- and until 2026-08-26 his declared
        # absence turned it green for the whole of an absence, so anything that
        # broke while he was away was found on his return. The absence is the
        # worst moment to stop looking. A parked producer still silences it;
        # a Captain who is not reading does not.
        return card_flatline.evaluate(
            read_series(series_path),
            gates=card_flatline.read_gates(
                root=root, audience=card_flatline.AUDIENCE_FLEET))
    except Exception as e:  # noqa: BLE001
        return {"state": "error", "announce": False, "silent_since": None,
                "silent_hours": None, "latest_date": None, "latest_cards": None,
                "reasons": [], "error": type(e).__name__}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Proactive-card channel flatline probe (read-only)")
    parser.add_argument("--probe", action="store_true",
                        help="print one classified token line for cabinet-doctor")
    parser.add_argument("--json", action="store_true",
                        help="also print the whole verdict as JSON")
    parser.add_argument("--series", default=None,
                        help="read this series file instead of the repo default")
    args = parser.parse_args(argv)

    v = verdict(series_path=Path(args.series) if args.series else None)
    if v.get("state") == "error":
        token = f"ERROR reason={v.get('error')}"
    else:
        token = card_flatline.probe_token(v)

    if args.probe:
        print(token)
        if args.json:
            print(json.dumps(v, sort_keys=True))
        return 0

    print(f"card-flatline: {token}")
    line = card_flatline.render_line(v)
    if line:
        print(f"captain line (this run): {line}")
    if args.json:
        print(json.dumps(v, sort_keys=True))
    return 1 if v.get("state") == "flatline" else 0


if __name__ == "__main__":
    sys.exit(main())
