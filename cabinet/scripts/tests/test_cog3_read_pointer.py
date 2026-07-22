"""COG-3 STEP 0 — the §7.4 read-pointer tripwire, tests-first.

§7.4 (attack C-m11): NO pointer file is created this phase — the pointer stays a
documentation-level concept. Creating `~/.cabinet/state/cog3-read-pointer` is the
FIRST act of the future flip amendment (named in the P8 handback row), never a
COG-3 deliverable. verify-cognitive-phase3.sh (a later unit) carries the same
tripwire; this test is its permanent CI mirror.

The mutant is proven under a SCRATCH home — the real ~/.cabinet is never touched.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

from pathlib import Path

_POINTER_REL = Path(".cabinet") / "state" / "cog3-read-pointer"


def read_pointer_violation(home) -> Path | None:
    """The tripwire predicate: the pointer path under `home` if it exists, else
    None. Parametrized on `home` so the bite is provable without touching the
    real home directory."""
    p = Path(home) / _POINTER_REL
    return p if p.exists() else None


class TestReadPointerTripwire:
    def test_no_cog3_read_pointer_this_phase(self):
        # THE production assertion — the pointer must NOT exist in the shadow phase.
        assert read_pointer_violation(Path.home()) is None, (
            "§7.4 breach: ~/.cabinet/state/cog3-read-pointer exists — the read "
            "pointer is a later, gated flip-amendment act, not a COG-3 deliverable.")

    def test_tripwire_bites_when_a_pointer_is_present(self, tmp_path):
        # the anti-no-op mutant: a present pointer under a scratch home is detected,
        # so the production assertion above WOULD go RED the instant the file lands.
        (tmp_path / _POINTER_REL).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / _POINTER_REL).write_text("flip", encoding="utf-8")
        assert read_pointer_violation(tmp_path) is not None

    def test_tripwire_is_silent_on_a_clean_scratch_home(self, tmp_path):
        # discrimination: an absent pointer folds (not always-RED).
        assert read_pointer_violation(tmp_path) is None
