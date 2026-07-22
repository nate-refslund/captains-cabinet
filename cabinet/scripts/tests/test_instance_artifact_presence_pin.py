"""Source-tree presence pin for egg-stripped instance artifacts (teeth restore).

Several CI tolerances in this tree skip or fall back when an instance artifact is
ABSENT, so the artifact-stripped public egg tree stays green. Those skips key on
bare file-absence, which cannot tell "stripped by the egg export" from
"deleted / rotted on the source tree" — so on their own they would let a
COMMITTED deletion of a real instance artifact pass CI silently (PR #171
teeth-review, Concerns 1-3).

This pin closes that class with ONE source-only file. It runs only on the source
instance — keyed on the egg-export manifest, which is itself stripped from the
egg (the same `requires_egg_manifest` discriminator the packaging-pin tests use)
— and asserts every egg-stripped-but-source-tracked artifact whose deletion those
tolerances now mask is still present. On the public egg the manifest is absent →
this whole file skips (the artifacts are legitimately gone there). On the source
tree a committed deletion of any listed artifact FAILs here, restoring the teeth
the individual tolerances gave up. A marker-less absence on the source instance
is real rot, exactly as A3/A4 keep a hard FAIL for a marker-less emptied surface.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "cabinet" / "scripts" / "egg-export-manifest.txt"

# Present on the source instance; stripped or replaced-with-a-twin by egg export.
# Each is the exact surface a PR-#171 tolerance now treats as data-optional, so a
# committed deletion here would otherwise skip / fall back silently instead of
# failing. Adding a NEW egg-stripped instance surface that a tolerance skips on
# should add a row here in the same change — the ratchet: an intentional removal
# updates the pin (and retires its tolerance); an accidental removal trips it.
EGG_STRIPPED_SOURCE_TRACKED = (
    # instance/config reals — the egg ships the .example twin. Back the D2 roster
    # fallback, class-b morphology + docs-sweep allowlist, and the briefing /
    # portfolio preset fallbacks:
    "instance/config/platform.yml",
    "instance/config/outcomes.yml",
    "instance/config/directions.yml",
    "instance/config/sources.yml",
    "instance/config/peers.yml",
    "instance/config/task-watch.yml",
    # instance agent — the egg ships the presets/portfolio twin (briefing +
    # portfolio-chair fallbacks):
    "instance/agents/cos.md",
    # concrete launchd plists — the egg strips absolute-path plists
    # (transform:launchd-portable-only), no template twin. These back the
    # ops-scheduling, fidelity-f1, and plist-cadence tests, whose skips fire per
    # bare absence:
    "cabinet/launchd/com.cabinet.fidelity-f1.plist",
    "cabinet/launchd/com.cabinet.undo-sweep.plist",
    "cabinet/launchd/com.cabinet.actfirst-canary.plist",
    "cabinet/launchd/com.cabinet.falsifier-daily.plist",
)

requires_egg_manifest = pytest.mark.skipif(
    not MANIFEST.is_file(),
    reason="egg-export-manifest.txt absent — private-side export tooling, not "
           "shipped in the egg; instance-presence pins arm on the source instance",
)


@requires_egg_manifest
@pytest.mark.parametrize("rel", EGG_STRIPPED_SOURCE_TRACKED)
def test_egg_stripped_instance_artifact_present_on_source(rel):
    """Full teeth on the source instance: a committed deletion of an egg-stripped
    instance artifact FAILs here even though its own tolerant test skips or falls
    back (PR #171 teeth-review, Concerns 1-3)."""
    assert (REPO / rel).is_file(), (
        f"{rel} is missing on the source tree. The egg-export manifest is present "
        "(this is the source instance, not the public egg), so this is a committed "
        "deletion / rot, not an egg strip — and the tolerances that skip on its "
        "absence would mask it. Restore the file; or, if the removal is deliberate, "
        "drop this row AND retire the tolerance that skipped on it, in the same "
        "change."
    )
