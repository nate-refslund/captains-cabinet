#!/usr/bin/env python3
"""intent_report.py — roll measure_intent JSONL shards into the D17 report:
AGB (as-good-or-better) is the HEADLINE, decision-match a DIAGNOSTIC.

The personal-agent reframe (sovereign spec D17/INT-1..3): the harness
objective is no longer "did the clone match the Captain's literal reply?" but
"did its outcome serve the Captain's reconstructed intent as good or better
than what the Captain actually sent?". This module is a pure reader over the
per-case recs measure_intent emits — no LLM calls, no network, no ledger writes.

Rates follow the harness's no-silent-caps rule: an unmeasured rate is a
visible None, never a silent 0.0/1.0.
  - agb_rate            = as_good_or_better / (as_good_or_better + worse)
                          (incomparable / error / "" excluded — mirrors how
                          unknown verdicts are excluded elsewhere)
  - decision_match_rate = match / (match + partial + divergent)  [diagnostic]
  - intent_aligned_rate = intent-aligned / (intent-aligned + intent-divergent)
                          [diagnostic; intent-partial excluded]

Summaries are SEGMENTED per identity_mode (D17: "segment baselines per
identity") — a rec with no identity_mode stamp is the historical clone
default. The first clone-identity report IS the AGB baseline the
identity_mode='agent' flip is gated on.

Usage:
  python3 -m framework.fidelity.intent_report shard0.jsonl shard1.jsonl
  python3 -m framework.fidelity.intent_report --json shards/*.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from framework.env import captain_name

# Verdict vocabularies (scorer.py is the source; mirrored here as read-side
# constants so the reader never imports the scoring/LLM stack).
_AGB = "as_good_or_better"
_OUTCOME_JUDGED = (_AGB, "worse")
_DECISION_JUDGED = ("match", "partial", "divergent")
_INTENT_JUDGED = ("intent-aligned", "intent-divergent")
# The identity a pre-D17 rec (no identity_mode key) was measured under.
_DEFAULT_IDENTITY = "clone"


def load_recs(paths: list) -> list:
    """Read measure_intent rec lines from JSONL shard files. Malformed lines
    and non-dict rows are skipped (a crashed shard tail must not sink the
    report); a missing file raises — a named gap, not a silent zero."""
    recs = []
    for p in paths:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    recs.append(rec)
    return recs


def _rate(num: int, denom: int) -> Optional[float]:
    """num/denom, or the visible None when unmeasured (denom == 0)."""
    return (num / denom) if denom else None


def _summarize_bucket(recs: list) -> dict:
    """Roll one identity segment's recs into counts + rates."""
    outcome = {v: 0 for v in (_AGB, "worse", "incomparable", "error")}
    decision = {v: 0 for v in _DECISION_JUDGED}
    intent = {"intent-aligned": 0, "intent-partial": 0, "intent-divergent": 0}
    leaked = errors = 0
    for r in recs:
        if r.get("leaked"):
            leaked += 1
            continue
        if r.get("error"):
            errors += 1
            continue
        ov = r.get("outcome_verdict")
        if ov in outcome:
            outcome[ov] += 1
        dv = r.get("decision_verdict")
        if dv in decision:
            decision[dv] += 1
        iv = r.get("intent_verdict")
        if iv in intent:
            intent[iv] += 1
    return {
        "n_recs": len(recs),
        "leaked": leaked,
        "errors": errors,
        "outcome_counts": outcome,
        "decision_counts": decision,
        "intent_counts": intent,
        # HEADLINE — the AGB rate (D17). incomparable/error excluded.
        "agb_rate": _rate(outcome[_AGB],
                          sum(outcome[v] for v in _OUTCOME_JUDGED)),
        # DIAGNOSTICS — the legacy mimicry + intent axes.
        "decision_match_rate": _rate(decision["match"],
                                     sum(decision[v]
                                         for v in _DECISION_JUDGED)),
        "intent_aligned_rate": _rate(intent["intent-aligned"],
                                     sum(intent[v] for v in _INTENT_JUDGED)),
    }


def summarize(recs: list) -> dict:
    """Segment recs per identity_mode (absent ⇒ 'clone', the historical
    default) and summarize each segment plus the overall pool. Shape:
    ``{"overall": {...}, "identities": {"clone": {...}, "agent": {...}}}``."""
    by_identity: dict = {}
    for r in recs:
        mode = r.get("identity_mode") or _DEFAULT_IDENTITY
        by_identity.setdefault(mode, []).append(r)
    return {
        "overall": _summarize_bucket(recs),
        "identities": {mode: _summarize_bucket(rs)
                       for mode, rs in sorted(by_identity.items())},
    }


def _fmt_rate(rate: Optional[float]) -> str:
    return "unmeasured" if rate is None else f"{rate:.0%}"


def render(summary: dict) -> str:
    """Human-readable report, AGB headline first, diagnostics after."""
    cap = captain_name()
    lines = []
    overall = summary.get("overall") or {}
    lines.append("# Intent-fidelity report (D17 — outcome objective)")
    lines.append(
        f"HEADLINE  AGB (as-good-or-better vs {cap}'s real reply, judged "
        f"against reconstructed intent): {_fmt_rate(overall.get('agb_rate'))}")
    for mode, seg in (summary.get("identities") or {}).items():
        oc = seg.get("outcome_counts") or {}
        lines.append(f"\n## identity: {mode}  (n={seg.get('n_recs', 0)}, "
                     f"leaked={seg.get('leaked', 0)}, "
                     f"errors={seg.get('errors', 0)})")
        lines.append(
            f"  AGB rate: {_fmt_rate(seg.get('agb_rate'))}  "
            f"[{oc.get(_AGB, 0)} agb / {oc.get('worse', 0)} worse / "
            f"{oc.get('incomparable', 0)} incomparable / "
            f"{oc.get('error', 0)} error]")
        lines.append(
            f"  diagnostic decision-match: "
            f"{_fmt_rate(seg.get('decision_match_rate'))}  "
            f"{seg.get('decision_counts')}")
        lines.append(
            f"  diagnostic intent-aligned: "
            f"{_fmt_rate(seg.get('intent_aligned_rate'))}  "
            f"{seg.get('intent_counts')}")
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> None:
    ap = argparse.ArgumentParser(
        description="Roll measure_intent shards into the AGB report")
    ap.add_argument("shards", nargs="+",
                    help="measure_intent JSONL shard file(s)")
    ap.add_argument("--json", action="store_true",
                    help="emit the summary dict as JSON instead of text")
    args = ap.parse_args(argv)
    summary = summarize(load_recs(args.shards))
    if args.json:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render(summary))


if __name__ == "__main__":
    main()
