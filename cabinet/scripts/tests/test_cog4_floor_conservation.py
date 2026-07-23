"""COG-4 §9.2 — the FLOOR-CONSERVATION battery (MR3, COUNT + TUPLE strength SF5;
N7's floor leg).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §9.2:
composing N services.yml rows into one organ-runner row must NOT delete N
watchdog floors — per composed organ the derived `(cadence, threshold, probe)`
tuple must be at-least-as-strict as the absorbed row's pre-compose
expectations, anchored to the REAL registry derivations
(`_floor_for_entry` registry.py, `_service_log_candidates`).

The checker under test is `lib_cog4_floors.check_floor_conservation` — the
REFERENCE IMPLEMENTATION the W6 compose commits run. Everything here is LIVE
fixture machinery over synthetic services.yml/manifest pairs (no skip): the
harness itself must be proven to bite NOW. The §9.2 named mutants, each proven:
  * count-drop (a composed row with no derivable per-organ floor)      -> RED
  * missing `freshness_needs` on a composed organ                      -> RED
  * LOOSENED threshold (organ max_staleness > absorbed row's floor)    -> RED (SF5)
  * cadence-SLOWER (runner interval > absorbed row's period)           -> RED
  * shared-runner-log-only probe (expected_output = runner log path)   -> RED
  * duplicated probe artifact across two composed organs               -> RED
  * non-atomic compose (absorbed row still present after)              -> RED

ONE vacuity arm (the W1-u2 idiom) — RETIREMENT CONDITION: retire the skip when
`framework/watchdog/registry.py` gains `_parse_organ_manifests` (§9.2, MR3);
the retired arm cross-checks the REAL derivation against
`lib_cog4_floors.derive_organ_expectations` over these same fixture manifests
(the reference twin law), then the compose gate binds the real function. The
COMPANION hasattr assertion REDs the moment the function lands, so the skip
cannot silently persist.

S0: python3.12, no DB, no network, deterministic. Provenance: authored per the
2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous
grant (COG-4 W2 corpus, unit T3).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_floors as FL                      # noqa: E402
from framework.watchdog import registry           # noqa: E402  (read-only)


# ---------------------------------------------------------------------------
# fixtures — synthetic services.yml texts in the EXACT shape the real narrow
# parser reads (`  - name:` rows, 4-space keys, flow-style schedule)
# ---------------------------------------------------------------------------
_BEFORE = """\
services:
  - name: undo-sweep
    label: com.cabinet.undo-sweep
    kind: cron
    schedule: { interval_s: 21600 }
  - name: world-census
    label: com.cabinet.world-census
    kind: cron
    schedule: { calendar: {hour: 3, minute: 0} }   # daily 03:00
  - name: prediction-calibration
    label: com.cabinet.prediction-calibration
    kind: cron
    schedule: { interval_s: 43200 }
  - name: bystander
    label: com.cabinet.bystander
    kind: cron
    schedule: { interval_s: 1800 }
"""

_AFTER = """\
services:
  - name: organ-runner
    label: com.cabinet.organ-runner
    kind: cron
    schedule: { interval_s: 21600 }
  - name: bystander
    label: com.cabinet.bystander
    kind: cron
    schedule: { interval_s: 1800 }
"""

_COMPOSED = ["undo-sweep", "world-census", "prediction-calibration"]
_RUNNER = "organ-runner"

# derived pre-compose floors (the REAL `_floor_for_entry` law, pinned below):
#   undo-sweep             interval 21600 -> 2*21600+600 = 43800
#   world-census           calendar daily -> 26h         = 93600
#   prediction-calibration interval 43200 -> 2*43200+600 = 87000


def _organ(name: str, staleness: int, output: str) -> dict:
    """A minimal organ manifest carrying exactly what floor derivation reads
    (§4.2 `freshness_needs`); the full organ contract is
    test_cog4_organ_manifest.py's surface, not this battery's."""
    return {"name": name, "kind": "organ",
            "freshness_needs": {"max_staleness_seconds": staleness,
                                "expected_output": output}}


def _good_organs() -> list[dict]:
    return [
        _organ("undo-sweep", 43000, "cabinet/cache/organs/undo-sweep/last-run.json"),
        _organ("world-census", 86400, "cabinet/cache/organs/world-census/census.json"),
        _organ("prediction-calibration", 86400,
               "cabinet/cache/organs/prediction-calibration/calibration.json"),
    ]


def _check(before=_BEFORE, after=_AFTER, runner=_RUNNER, composed=None, organs=None):
    return FL.check_floor_conservation(
        before, after, runner,
        list(_COMPOSED) if composed is None else composed,
        _good_organs() if organs is None else organs)


# ---------------------------------------------------------------------------
# live machinery — the fixture shape really parses through the REAL registry
# ---------------------------------------------------------------------------
class TestFixtureMachineryLive:
    def test_registry_parses_the_fixture_rows(self):
        rows = {e["name"]: e for e in registry._parse_services_manifest(_BEFORE)}
        assert set(rows) == {"undo-sweep", "world-census",
                             "prediction-calibration", "bystander"}
        assert rows["undo-sweep"]["schedule_kind"] == "interval"
        assert rows["undo-sweep"]["interval_s"] == 21600
        assert rows["world-census"]["schedule_kind"] == "calendar"
        assert not rows["world-census"]["weekly"]

    def test_real_floor_derivation_pins(self):
        """The absorbed-row floors this battery compares against are the REAL
        `_floor_for_entry` outputs — pinned so a watchdog floor-law change
        REDs this corpus honestly instead of silently shifting the gate."""
        rows = {e["name"]: e for e in registry._parse_services_manifest(_BEFORE)}
        assert registry._floor_for_entry(rows["undo-sweep"]) == 43800
        assert registry._floor_for_entry(rows["world-census"]) == 93600
        assert registry._floor_for_entry(rows["prediction-calibration"]) == 87000

    def test_effective_periods(self):
        rows = {e["name"]: e for e in registry._parse_services_manifest(_BEFORE)}
        assert FL.effective_period_s(rows["undo-sweep"]) == 21600
        assert FL.effective_period_s(rows["world-census"]) == 86400
        keepalive = {"schedule_kind": "keepalive", "interval_s": None}
        assert FL.effective_period_s(keepalive) is None

    def test_organ_expectation_derivation(self):
        exp, errors = FL.derive_organ_expectations(_good_organs())
        assert errors == []
        assert exp["undo-sweep"] == (
            "cabinet/cache/organs/undo-sweep/last-run.json", 43000)
        assert set(exp) == set(_COMPOSED)


# ---------------------------------------------------------------------------
# the conservation gate — clean compose GREEN, every named mutant REDs
# ---------------------------------------------------------------------------
class TestFloorConservation:
    def test_conforming_compose_is_clean(self):
        assert _check() == []

    def test_count_drop_mutant_reds(self):
        """§9.2 mutant: a compose commit whose floor count drops REDs — one
        composed row ships with NO organ manifest deriving its floor."""
        organs = [o for o in _good_organs() if o["name"] != "world-census"]
        v = _check(organs=organs)
        assert any("COUNT" in x for x in v), v
        assert any("world-census" in x and "no organ manifest" in x for x in v), v

    def test_missing_freshness_needs_mutant_reds(self):
        """§9.2 mutant: a composed organ whose manifest lacks `freshness_needs`
        REDs (the floor-derivation input is mandatory, MR3)."""
        organs = _good_organs()
        del organs[0]["freshness_needs"]
        v = _check(organs=organs)
        assert any("missing freshness_needs" in x for x in v), v

    def test_loosened_threshold_mutant_reds(self):
        """SF5 mutant: organ max_staleness > the absorbed row's derived floor
        (43800s for undo-sweep) — the tuple is NOT at-least-as-strict."""
        organs = _good_organs()
        organs[0]["freshness_needs"]["max_staleness_seconds"] = 50000
        v = _check(organs=organs)
        assert any("LOOSENED" in x and "undo-sweep" in x for x in v), v
        # exactly at the floor is still as-strict — the boundary is inclusive
        organs[0]["freshness_needs"]["max_staleness_seconds"] = 43800
        assert _check(organs=organs) == []

    def test_cadence_slower_mutant_reds(self):
        """§9.2 mutant: the runner wakes SLOWER than an absorbed row ran —
        runner interval 86400 > undo-sweep's 21600 period."""
        after = _AFTER.replace("schedule: { interval_s: 21600 }",
                               "schedule: { interval_s: 86400 }")
        v = _check(after=after)
        assert any("cadence SLOWER" in x and "undo-sweep" in x for x in v), v
        # world-census (daily period) is still satisfied by a daily runner
        assert not any(x.startswith("world-census:") and "cadence" in x for x in v), v

    def test_shared_runner_log_probe_mutant_reds(self):
        """§9.2 probe-field mutant: an organ probed ONLY via the shared runner
        log — a silent organ inside a live runner would never trip its floor.
        Proven against the REAL `_service_log_candidates` path shape AND the
        relative basename spelling."""
        real_candidate = registry._service_log_candidates(_RUNNER)[0]
        organs = _good_organs()
        organs[1]["freshness_needs"]["expected_output"] = real_candidate
        v = _check(organs=organs)
        assert any("SHARED runner log" in x and "world-census" in x for x in v), v
        organs[1]["freshness_needs"]["expected_output"] = f"logs/{_RUNNER}.log"
        v2 = _check(organs=organs)
        assert any("SHARED runner log" in x for x in v2), v2

    def test_duplicate_probe_artifact_reds(self):
        organs = _good_organs()
        organs[1]["freshness_needs"]["expected_output"] = \
            organs[0]["freshness_needs"]["expected_output"]
        v = _check(organs=organs)
        assert any("duplicates organ" in x for x in v), v

    def test_non_atomic_compose_reds(self):
        """§9.2: the compose commit removes the N rows and adds the runner row
        ATOMICALLY — an absorbed row still present after the compose REDs."""
        after = _AFTER + (
            "  - name: undo-sweep\n"
            "    label: com.cabinet.undo-sweep\n"
            "    kind: cron\n"
            "    schedule: { interval_s: 21600 }\n")
        v = _check(after=after)
        assert any("still present after compose" in x for x in v), v

    def test_missing_or_disabled_runner_reds(self):
        v = _check(after="services:\n  - name: bystander\n    label: com.cabinet.bystander\n"
                         "    kind: cron\n    schedule: { interval_s: 1800 }\n")
        assert any("absent from services.yml after compose" in x for x in v), v
        after_disabled = _AFTER.replace(
            "    kind: cron\n    schedule: { interval_s: 21600 }",
            "    kind: cron\n    disabled: true\n    schedule: { interval_s: 21600 }", 1)
        v2 = _check(after=after_disabled)
        assert any("disabled" in x for x in v2), v2

    def test_keepalive_absorbed_row_is_not_composable(self):
        """§9.3: keepalive daemons are never legitimate compose targets — an
        incomparable cadence is a violation, never a pass."""
        before = _BEFORE + (
            "  - name: memory-worker\n"
            "    label: com.cabinet.memory-worker\n"
            "    kind: daemon\n"
            "    schedule: keepalive\n")
        organs = _good_organs() + [
            _organ("memory-worker", 3600, "cabinet/cache/organs/memory-worker/beat.json")]
        v = _check(before=before, composed=_COMPOSED + ["memory-worker"], organs=organs)
        assert any("no comparable cadence" in x for x in v), v

    def test_extra_organs_beyond_the_composed_set_are_welcome(self):
        """Strictly MORE floors is never a violation (shrink-only cuts fleet
        rows, never floors)."""
        organs = _good_organs() + [
            _organ("bonus-organ", 3600, "cabinet/cache/organs/bonus/out.json")]
        assert _check(organs=organs) == []


# ---------------------------------------------------------------------------
# the vacuity arm — the REAL _parse_organ_manifests (W3/W6 watchdog edit)
# ---------------------------------------------------------------------------
class TestRealParseOrganManifestsArm:
    def test_real_derivation_arm(self):
        """VACUITY GUARD — RETIREMENT CONDITION: retire this skip when
        framework/watchdog/registry.py gains `_parse_organ_manifests` (§9.2,
        MR3); the retired arm cross-checks the REAL derivation against
        lib_cog4_floors.derive_organ_expectations over the fixture manifests
        above (same `(expected_output, max_staleness)` pairs), and the compose
        gate then binds the real function. The COMPANION hasattr assertion
        REDs the moment the function lands, so the skip cannot silently
        persist (the W1-u2 idiom)."""
        assert not hasattr(registry, "_parse_organ_manifests"), (
            "framework/watchdog/registry.py has gained _parse_organ_manifests — retire "
            "this vacuity skip and cross-check it against "
            "lib_cog4_floors.derive_organ_expectations per the docstring RETIREMENT "
            "CONDITION")
        pytest.skip(
            "VACUITY: registry._parse_organ_manifests absent this phase-stage — the "
            "reference derivation + conservation checker are proven live above; retire "
            "when the watchdog gains the per-organ floor parser.")
