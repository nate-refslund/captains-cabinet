"""COG-5 §7.5.5 Stage-A INTERIM — the frozen-holdout CONTENT PIN + the paired
egg-export exclusion assertion. Tests-first, gates-before-code (contract
cognitive-core-phase-5-contract-2026-07-24 §7.5.5(a) + (c)).

HONESTY CLAUSE (§7.5.5 — never claim otherwise): NOTHING in this file is Ring-0.
The content pin is a CI TRIPWIRE over holdout_gen.py's bytes — there is NO schg,
NO hook guard, NO gate-S0 `touches_ring0` refusal until the Ring-0 listing lands
in framework/policies/immutable-core.yml at a Captain germline-unlock window
(§7.5 Stage B). A same-uid actor could edit holdout_gen.py AND update the pin in
one commit; the pin only makes an UNANNOUNCED drift RED in CI. This is the
Stage-A interim posture (honestly named), retired when the listing lands.

Two Stage-A protections, both vacuity-armed while holdout_gen.py is absent (it
lands in W5):
  (a) CONTENT PIN — once holdout_gen.py lands, EXPECTED_HOLDOUT_SHA256 is set to
      its byte sha256 and test_holdout_gen_bytes_match_the_pin asserts the file's
      bytes still match (drift REDs CI). The fixture proof below shows the pin
      MACHINERY bites on a single-byte change NOW, while the target is absent (a
      gate without a biting mutant is decoration — §12).
  (c) EGG EXCLUSION — the egg manifest carries a `delete` + a matching
      `expect-absent` for framework/evolution/holdout_gen.py so no hatched
      cabinet ships an unprotected generator before Stage B (the O-B3 idiom).
      Asserted text-level here (binds THIS wave's manifest edit, the
      test_egg_export.py idiom; kept in a COG-5 file so this unit never edits the
      shared corpus test).

RETIREMENT CONDITION: when holdout_gen.py lands (W5), set EXPECTED_HOLDOUT_SHA256
and delete the absence companion. When the Ring-0 listing lands (Stage B), the
egg delete/expect-absent rows retire (replaced by expect-present) and this whole
interim content pin is superseded by the gate-S0 refusal.

S0: python3.12, no DB, no network. Provenance: authored per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]

HOLDOUT_GEN = _REPO / "framework/evolution/holdout_gen.py"
_MANIFEST = _REPO / "cabinet/scripts/egg-export-manifest.txt"

# The pinned sha256 of holdout_gen.py's bytes. None = vacuity (the module has not
# landed yet). SET THIS to the real digest in the commit that lands holdout_gen.py
# (W5); the byte-match arm below then becomes the live content tripwire.
EXPECTED_HOLDOUT_SHA256: str | None = None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


# ===========================================================================
# (a) the content pin — vacuity-armed until holdout_gen.py lands
# ===========================================================================
class TestHoldoutContentPin:
    def test_target_absent_and_pin_unset(self):
        # COMPANION absence: trips RED the moment holdout_gen.py lands, forcing
        # the RETIREMENT CONDITION (set EXPECTED_HOLDOUT_SHA256 + drop this).
        assert not HOLDOUT_GEN.exists(), (
            "holdout_gen.py LANDED — retire the vacuity: set EXPECTED_HOLDOUT_SHA256 "
            "to its sha256 and enable test_holdout_gen_bytes_match_the_pin.")
        assert EXPECTED_HOLDOUT_SHA256 is None, (
            "EXPECTED_HOLDOUT_SHA256 is set but holdout_gen.py is absent — the pin "
            "has no subject.")

    def test_holdout_gen_bytes_match_the_pin(self):
        # LIVE arm (dormant while vacuity-armed): once EXPECTED is set + the file
        # lands, its bytes must match the pin. Skips honestly while unset so the
        # arm is present-and-armed, never silently green after landing.
        if EXPECTED_HOLDOUT_SHA256 is None or not HOLDOUT_GEN.exists():
            return  # vacuity — test_target_absent_and_pin_unset owns the guard
        assert _sha256_file(HOLDOUT_GEN) == EXPECTED_HOLDOUT_SHA256, (
            "holdout_gen.py bytes DRIFTED from the pinned sha256 — an unannounced "
            "change to the frozen generator (Stage-A CI tripwire, NOT Ring-0).")

    def test_pin_machinery_reds_on_a_byte_change(self, tmp_path):
        # FIXTURE PROOF (bites NOW, target absent): the sha256 pin detects a
        # single-byte change and is stable under identical bytes (anti-no-op).
        f = tmp_path / "holdout_gen.py"
        f.write_bytes(b"# frozen holdout generator\nHOLDOUT_VERSION = 1\n")
        pinned = _sha256_file(f)
        # identical bytes -> identical digest (the pin does not false-positive)
        f.write_bytes(b"# frozen holdout generator\nHOLDOUT_VERSION = 1\n")
        assert _sha256_file(f) == pinned
        # one byte changed -> the pin REDs (drift is caught)
        f.write_bytes(b"# frozen holdout generator\nHOLDOUT_VERSION = 2\n")
        assert _sha256_file(f) != pinned


# ===========================================================================
# (c) the egg exclusion — the manifest carries the delete + expect-absent pair
# ===========================================================================
class TestEggExclusionCarried:
    def test_manifest_carries_the_holdout_delete_and_expect_absent(self):
        # text-level (binds THIS wave's manifest edit, not a HEAD cut — the
        # test_egg_export.py idiom): the Stage-A interim exclusion sibling pair
        # must be present so an unprotected holdout_gen.py never ships (§7.5.5c).
        text = _MANIFEST.read_text(encoding="utf-8")
        rel = "framework/evolution/holdout_gen.py"
        assert f"delete {rel}" in text, "manifest missing the holdout delete rule"
        assert f"expect-absent {rel}" in text, (
            "manifest missing the paired holdout expect-absent rule")

    def test_holdout_is_not_expect_present_during_interim(self):
        # the sibling force-pairing (§16): while Stage-A interim, holdout_gen.py
        # must NOT be expect-present (that is the Stage-B replacement) — a
        # one-sided edit that shipped it unprotected would fail closed here.
        text = _MANIFEST.read_text(encoding="utf-8")
        assert "expect-present framework/evolution/holdout_gen.py" not in text, (
            "holdout_gen.py is expect-present while Stage-A interim — the Ring-0 "
            "listing must land (Stage B) BEFORE it ships.")
