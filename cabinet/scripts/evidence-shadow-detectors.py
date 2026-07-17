#!/usr/bin/env python3.12
"""Thin scheduled runner for the Phase-4 SHADOW evidence detectors.

Judge-calibration split (house pattern): ALL logic lives in the framework
module (framework/evidence_detectors.py — read-only clustering + fail-open
triage + the Captain-facing findings journal); this CLI only resolves the
repo root and delegates, and is what cabinet/services.yml schedules BY
PATH (row com.cabinet.evidence-shadow-detectors, shipped disabled:true —
staged dark per the shadow law; the Captain ceremony enables it).

Exit codes (services.yml `expected:` contract):
  0  ran (findings or none — findings are information, never faults), OR
     refused to run because the judging-freeze marker is present (one
     "frozen — refusing to run" line; §2.4 freeze respect), OR the store
     is absent (evidence plane not activated).
  2  measurement error — a FATAL line lands on stderr, which the
     watchdog's error-marker floor turns into a Chair page for free.

Read-only toward the evidence store (germline query/verify APIs; the sole
sanctioned store byte-change is the first-verify watermark advance). The
report journal lives OUTSIDE the store (shared/interfaces/, gitignored).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence_detectors import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
