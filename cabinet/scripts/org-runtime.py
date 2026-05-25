#!/usr/bin/env python3
"""CLI wrapper for the org runtime vertical slice."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from org_runtime import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
