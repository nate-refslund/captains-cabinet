"""lib_cog4_parity_set.py — the COG-4 N9 parity SET assembler (W5 x3).

THE ONE definition of "the entire pilot set + all three §12 fixture cabinets"
(contract §5.3 / §1 N9): the S0 pilot organ fixtures under
`fixtures/cog4/pilot/` + the three non-software fixture cabinets under
`fixtures/cog4/cabinets/<cabinet>/` (landed by W5 x2). The tracked
`cog4-parity-record.json` is `cog4-parity.py`'s output over the UNION of these
manifests assembled into one flat directory (the registry loads a single
top-level dir), and `test_cog4_parity_record.py` regenerates + byte-compares
against the tracked record here (reproducibility + determinism) and asserts the
record covers exactly this union (the N9 coverage law).

WHY A SHARED LIB (§13): the record-generation step and the pre-prove test must
assemble the IDENTICAL manifest set — single-sourcing it here means the two can
never drift. This is a NEW test-side lib (never edits an existing corpus file);
it imports nothing from the action plane and writes nothing of its own.

WHY A SIBLING DIR, NOT `cabinets/`: the §12 N8 token sweep in
`test_cog4_exit_fixtures.py` is scoped to `fixtures/cog4/cabinets/` and asserts
EXACTLY six files there — the pilot manifests and the record are deliberately
SIBLINGS (`fixtures/cog4/pilot/` and `fixtures/cog4/` root) so that sweep never
sees them (the pilot rows are REAL software services; software vocabulary is
honest for them, unlike the non-software cabinets).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W5 x3 (N9 parity record).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.organs.registry import (  # noqa: E402
    MANIFEST_SUFFIXES, load_organ_manifests, read_manifest_file)

# the two source surfaces (relative to the tests dir)
_FIXTURE_COG4 = _HERE / "fixtures" / "cog4"
PILOT_DIR = _FIXTURE_COG4 / "pilot"
CABINETS_ROOT = _FIXTURE_COG4 / "cabinets"
CABINET_NAMES = ("garden-delivery", "care-rota", "harbor-warehouse")

# the tracked record location (a SIBLING of pilot/ and cabinets/ — see the
# module docstring; `.json` is a manifest suffix, so it never sits inside a
# directory the registry is pointed at)
RECORD_PATH = _FIXTURE_COG4 / "cog4-parity-record.json"

# the pilot + cabinet organ names the record MUST span (N9 coverage law). Pilot
# names come from the pilot manifests authored in this unit; cabinet names from
# the six W5-x2 manifests. Both are cross-checked against the manifests on disk
# by `assert_source_shape()` so a rename can never silently shrink coverage.
PILOT_ORGANS = frozenset({
    "charter-shadow", "preference-pairs", "judge-calibration",
    "world-census", "prediction-calibration"})
CABINET_ORGANS = frozenset({
    "garden-rota", "basket-delivery", "visit-rota", "meal-round",
    "quay-inventory", "freight-round"})
EXPECTED_ORGANS = PILOT_ORGANS | CABINET_ORGANS


def cabinet_dirs() -> list[Path]:
    return [CABINETS_ROOT / name for name in CABINET_NAMES]


def source_manifest_paths() -> list[Path]:
    """Every manifest file across the pilot dir + the three cabinet dirs
    (top-level manifest-suffix files only — the registry's own load surface),
    sorted for determinism."""
    paths: list[Path] = []
    for root in (PILOT_DIR, *cabinet_dirs()):
        if not root.is_dir():
            raise FileNotFoundError(
                f"parity-set source dir missing: {root} — the pilot fixtures "
                "(this unit) or the W5-x2 cabinets are not on the tree")
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix.lower() in MANIFEST_SUFFIXES:
                paths.append(p)
    return paths


def assemble(dest_dir) -> Path:
    """Copy every source manifest FLAT into `dest_dir` (created if needed),
    refusing any filename collision loudly (a flat set cannot silently drop a
    manifest). Returns `dest_dir` as a Path — point `cog4-parity.py
    --manifest-dir` at it."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    seen: dict[str, Path] = {}
    for src in source_manifest_paths():
        if src.name in seen:
            raise ValueError(
                f"parity-set filename collision on {src.name!r}: {seen[src.name]} "
                f"vs {src} — the flat assembly would drop one")
        seen[src.name] = src
        shutil.copy2(src, dest / src.name)
    return dest


def declared_operations() -> set[str]:
    """The union of every declared `domain_operations` id across the parity set
    — the exact operation set the record must cover (single-sourced from the
    manifests the CLI itself reads, via the SAME registry loader). A structural
    defect in any manifest raises (never silently shrinks coverage)."""
    ops: set[str] = set()
    for root in (PILOT_DIR, *cabinet_dirs()):
        for manifest in load_organ_manifests(root):
            declared = manifest.get("domain_operations")
            if isinstance(declared, list):
                ops.update(op for op in declared if isinstance(op, str) and op)
    return ops


def source_organs() -> set[str]:
    """Every organ `name` across the parity set (structural read)."""
    names: set[str] = set()
    for src in source_manifest_paths():
        manifest = read_manifest_file(src)
        name = manifest.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return names


def assert_source_shape() -> None:
    """Guard the pinned constants against a manifest rename/move: the organs on
    disk MUST equal EXPECTED_ORGANS, and there must be at least one declared
    operation. Raises AssertionError with the delta on any drift."""
    on_disk = source_organs()
    assert on_disk == EXPECTED_ORGANS, (
        f"parity-set organ drift — on disk {sorted(on_disk)} != expected "
        f"{sorted(EXPECTED_ORGANS)}")
    ops = declared_operations()
    assert ops, "parity set declares zero operations (R-A non-empty idiom)"
