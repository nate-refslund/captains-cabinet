#!/usr/bin/env python3.12
"""Thin scheduled runner for the HP-2 independent recompute legs (SHADOW).

Judge-calibration split (house pattern): ALL logic lives in the framework
module (framework/evidence_recompute.py — raw-artifact re-derivation of
fuel-bearing machine outcomes, one verification event per checked outcome
in its OWN evt-recompute day trials, Captain-facing report file); this CLI
only resolves the repo root and delegates, and is what cabinet/services.yml
schedules BY PATH (row com.cabinet.evidence-recompute, shipped
disabled:true — staged dark per the shadow law; the Captain ceremony
enables it).

Exit codes (services.yml `expected:` contract):
  0  ran (agreements, disagreements, or nothing — a disagree is
     INFORMATION for the weekly review, never a fault), OR refused to run
     because the judging-freeze marker is present (one
     "frozen — refusing to run" line; §2.4 freeze respect).
  2  measurement error — a FATAL-class line lands on stderr, which the
     watchdog's error-marker floor turns into a Chair page for free.

HONEST CLAIM (carried by the module on every report line): a DIFFERENT
producer identity but the SAME OS user until HP-1 lands — independence
comes from re-deriving outcomes from raw artifacts, never from a
trust-domain boundary; root forges everything. The report file lives
OUTSIDE both planes (cabinet/logs/, gitignored).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence_recompute import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
