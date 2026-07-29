#!/usr/bin/env python3
"""The Python veil twin IS the renderer's, or CI is red.

world-growth-backtest.py paints beauty-shot timelapse strips and carries its own
copy of the per-bucket veil table, because it draws frames in Pillow rather than
in the browser. That copy said "change one, change both" in a comment — in the
same commit whose entire finding was that a hue table nothing can reach will
drift. A prose contract is not a sensor, so this is one.

It parses the TypeScript rather than importing anything: the constants are the
authority, and a test that re-declared them would be the third copy.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BACKTEST = REPO / "cabinet" / "scripts" / "world-growth-backtest.py"
TERRAIN_PATTERN = (REPO / "cabinet" / "dashboard" / "src" / "lib" / "world"
                   / "terrain-pattern.ts")
BUCKETS = ("dawn", "dusk", "night")


def _ts_hues(bucket: str) -> list[tuple[int, int, int]]:
    m = re.search(rf"^export const {bucket.upper()}_VEIL_HUES = \[([^\]]*)\]",
                  TERRAIN_PATTERN.read_text(), re.M)
    assert m, f"{bucket.upper()}_VEIL_HUES not found in terrain-pattern.ts"
    hexes = re.findall(r"0x([0-9a-fA-F]{6})", m.group(1))
    assert hexes, f"{bucket} hues parsed empty — the regex, not the source, is wrong"
    return [(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) for h in hexes]


def _py_veils() -> dict:
    """`_VEILS` out of the backtest, read as a literal — no import, because the
    module pulls yaml and shells out to sqlite at import time on some paths."""
    tree = ast.parse(BACKTEST.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_VEILS" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("_VEILS not found in world-growth-backtest.py")


def test_the_sources_are_both_real():
    """Vacuity guard: an empty parse on either side would pass every arm."""
    veils = _py_veils()
    assert set(veils) == set(BUCKETS), veils
    for b in BUCKETS:
        assert _ts_hues(b), b


@pytest.mark.parametrize("bucket", BUCKETS)
def test_python_veil_hues_match_the_renderer(bucket):
    py_hues, _ = _py_veils()[bucket]
    assert list(py_hues) == _ts_hues(bucket), (
        f"world-growth-backtest.py's {bucket} veil has drifted from "
        f"terrain-pattern.ts {bucket.upper()}_VEIL_HUES — a beauty shot would "
        f"render a world that does not exist"
    )


@pytest.mark.parametrize("bucket", BUCKETS)
def test_python_veil_coverage_matches_the_renderer(bucket):
    """Coverage lives in lighting.ts's ambientVeil, not in the hue table."""
    lighting = (REPO / "cabinet" / "dashboard" / "src" / "lib" / "world"
                / "lighting.ts").read_text()
    m = re.search(rf"case '{bucket}':\s*\n\s*return \{{ colors: \w+, coverage: ([\d.]+) \}}",
                  lighting)
    assert m, f"coverage for {bucket} not found in lighting.ts ambientVeil"
    assert _py_veils()[bucket][1] == float(m.group(1))


def test_day_has_no_veil_on_either_side():
    """The one bucket that must be absent from the Python table entirely."""
    assert "day" not in _py_veils()
    lighting = (REPO / "cabinet" / "dashboard" / "src" / "lib" / "world"
                / "lighting.ts").read_text()
    assert re.search(r"case 'day':\s*\n\s*return null", lighting)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
