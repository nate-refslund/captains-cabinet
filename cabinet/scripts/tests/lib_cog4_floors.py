"""lib_cog4_floors.py — the COG-4 §9.2 floor-conservation REFERENCE checker
(COUNT + TUPLE strength, SF5) + the §10 floor-aware wall-clock bound formula.

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §9.2 (MR3,
floor-preserving composition) and §10.2 (declared bound + tolerance). This lib
is the REFERENCE IMPLEMENTATION the W6 compose commits run (and the
`test_cog4_floor_conservation.py` battery proves NOW on synthetic fixtures):
composing N services.yml rows into one organ-runner row must never delete a
watchdog freshness floor, loosen a threshold, slow a cadence, or hide an organ
behind the shared runner log.

Fidelity by construction: floor derivation is NOT re-invented here — the
checker calls the REAL `framework.watchdog.registry` helpers read-only
(`_parse_services_manifest`, `_floor_for_entry`, `_service_log_candidates`),
so the "absorbed row's pre-compose expectations" side of every comparison is
byte-faithful to the shipped watchdog. The per-organ side
(`derive_organ_expectations`) is the reference twin of the FUTURE
`registry._parse_organ_manifests` (§9.2) — when that function lands, the
vacuity arm in `test_cog4_floor_conservation.py` retires and cross-checks the
real derivation against this one on the same fixtures.

THE CONSERVATION LAW (§9.2, verbatim mechanics):
  (a) COUNT — derived-floor count after >= before for the composed set: every
      absorbed row must map to an organ-manifest expectation (association law
      below), so N absorbed rows yield >= N per-organ floors.
  (b) TUPLE — per composed organ, `(cadence, threshold, probe)` is
      at-least-as-strict, per field:
        cadence   — the runner row's wake interval <= the absorbed row's
                    effective period (the organ runs at least as often);
        threshold — the organ's `freshness_needs.max_staleness_seconds` <= the
                    absorbed row's derived floor seconds (`_floor_for_entry`);
        probe     — the per-organ `expected_output` names a PER-ORGAN artifact:
                    never a `_service_log_candidates(runner)` path (a silent
                    organ inside a live runner must still trip its own floor),
                    and never shared between two composed organs.

ASSOCIATION LAW (reference): an organ manifest's `name` equals the absorbed
row's `name`, 1:1 over the composed set — the pilot composes each projection
row into exactly one organ, and the W6 compose commit controls both names.
Extra organs beyond the composed set are permitted (strictly more floors).

Helper, not a test (pytest collects test_*.py, never lib_*.py). Stdlib +
read-only registry import; no clock, no env, no subprocess — every function is
a pure function of its arguments.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-4 W2 corpus, unit T3).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.watchdog import registry  # noqa: E402  (read-only, stdlib-only module)


# ---------------------------------------------------------------------------
# cadence — the effective period of a parsed services.yml row
# ---------------------------------------------------------------------------
_DAY_S = 86400


def effective_period_s(entry: dict) -> Optional[int]:
    """The cadence (seconds between wakes) of a `_parse_services_manifest` row.

    interval  -> interval_s (the wake period itself);
    calendar  -> the calendar period: monthly 31d, weekly 7d, else daily 24h
                 (longest period wins when keys combine — the same precedence
                 `_floor_for_entry` applies to its floors);
    keepalive / unknown -> None (no comparable cadence: keepalive rows are
                 never legitimate compose targets — §9.3 — and the checker
                 turns an incomparable cadence into a violation, never a pass).
    """
    if entry.get("schedule_kind") == "interval" and entry.get("interval_s"):
        return int(entry["interval_s"])
    if entry.get("schedule_kind") == "calendar":
        if entry.get("monthly"):
            return 31 * _DAY_S
        return 7 * _DAY_S if entry.get("weekly") else _DAY_S
    return None


# ---------------------------------------------------------------------------
# per-organ expectations — the reference twin of the future
# registry._parse_organ_manifests (§9.2)
# ---------------------------------------------------------------------------
def derive_organ_expectations(
    organ_manifests: list[dict],
) -> tuple[dict[str, tuple[str, int]], list[str]]:
    """Derive `{organ name: (expected_output, max_staleness_seconds)}` from
    organ manifest dicts, per the §4.2/§9.2 `freshness_needs` contract
    (`max_staleness_seconds` int >= 1 + non-empty `expected_output` token).

    Returns (expectations, errors). A manifest that cannot yield a floor
    (missing/malformed `freshness_needs`, missing name) contributes an ERROR,
    never a silent skip — a composed organ without a derivable floor is
    exactly the escape the conservation law exists to catch.
    """
    expectations: dict[str, tuple[str, int]] = {}
    errors: list[str] = []
    for i, man in enumerate(organ_manifests):
        if not isinstance(man, dict):
            errors.append(f"organ[{i}]: manifest is not a mapping")
            continue
        name = man.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"organ[{i}]: missing name")
            continue
        fn = man.get("freshness_needs")
        if not isinstance(fn, dict):
            errors.append(f"{name}: missing freshness_needs (no floor derivable — §9.2)")
            continue
        stale = fn.get("max_staleness_seconds")
        out = fn.get("expected_output")
        if not isinstance(stale, int) or isinstance(stale, bool) or stale < 1:
            errors.append(f"{name}: freshness_needs.max_staleness_seconds must be an integer >= 1")
            continue
        if not isinstance(out, str) or not out.strip():
            errors.append(f"{name}: freshness_needs.expected_output must be a non-empty token")
            continue
        if name in expectations:
            errors.append(f"{name}: duplicate organ manifest name")
            continue
        expectations[name] = (out, stale)
    return expectations, errors


def _runner_log_paths(runner_name: str) -> set[str]:
    """Every path (expanduser-normalized) the RUNNER's shared log may land at —
    the `_service_log_candidates` shape (§9.2 probe field anchor)."""
    return {os.path.expanduser(p) for p in registry._service_log_candidates(runner_name)}


def _runner_log_basenames(runner_name: str) -> set[str]:
    """Basename spellings of the runner's shared log (catches a relative
    `expected_output` that names the shared log without its directory)."""
    return {
        f"{runner_name}.log",
        f"{runner_name}.err",
        f"{runner_name}.out.log",
        f"{runner_name}.err.log",
    }


# ---------------------------------------------------------------------------
# THE conservation checker (COUNT + TUPLE) — what a W6 compose commit runs
# ---------------------------------------------------------------------------
def check_floor_conservation(
    before_text: str,
    after_text: str,
    runner_name: str,
    composed_row_names: list[str],
    organ_manifests: list[dict],
) -> list[str]:
    """Verify one composition commit conserves every watchdog floor (§9.2).

    Inputs: the services.yml TEXT before and after the compose commit, the
    runner row's name, the names of the N absorbed rows, and the N(+) organ
    manifest dicts the runner row declares. Returns a sorted list of violation
    strings — EMPTY means the compose conserves floors at COUNT + TUPLE
    strength. Every check fails toward violation (an unparseable/missing input
    is a violation, never a pass).
    """
    v: list[str] = []
    before = {e["name"]: e for e in registry._parse_services_manifest(before_text)
              if e.get("name")}
    after = {e["name"]: e for e in registry._parse_services_manifest(after_text)
             if e.get("name")}

    # --- the runner row (the composed wake vehicle) must be a live fixed-wake row
    runner = after.get(runner_name)
    if runner is None:
        v.append(f"runner row '{runner_name}' absent from services.yml after compose")
    else:
        if runner.get("disabled"):
            v.append(f"runner row '{runner_name}' is disabled — composed floors have no vehicle")
        if runner.get("schedule_kind") != "interval" or not runner.get("interval_s"):
            v.append(f"runner row '{runner_name}' must declare a fixed interval schedule "
                     f"(got schedule_kind={runner.get('schedule_kind')!r})")
    runner_interval = (runner or {}).get("interval_s") \
        if (runner or {}).get("schedule_kind") == "interval" else None

    # --- atomicity of the compose: absorbed rows exist before, are gone after
    for name in composed_row_names:
        if name not in before:
            v.append(f"composed row '{name}' not present in services.yml before compose")
        if name in after:
            v.append(f"composed row '{name}' still present after compose — the compose "
                     f"commit must remove the N rows and add the runner row ATOMICALLY (§9.2)")

    expectations, derive_errors = derive_organ_expectations(organ_manifests)
    v.extend(derive_errors)

    # --- COUNT law: floors after >= floors before for the composed set (belt;
    # the per-row association check below is the suspenders — a bonus organ can
    # never mask a missing one)
    if len(expectations) < len(composed_row_names):
        v.append(f"floor COUNT drops: {len(composed_row_names)} absorbed rows but only "
                 f"{len(expectations)} derivable per-organ floors (§9.2 COUNT law)")

    # --- association law + TUPLE law per composed organ
    seen_outputs: dict[str, str] = {}
    runner_paths = _runner_log_paths(runner_name)
    runner_basenames = _runner_log_basenames(runner_name)
    for name in composed_row_names:
        row = before.get(name)
        if name not in expectations:
            v.append(f"composed row '{name}' has no organ manifest deriving its floor "
                     f"(association law: organ name == absorbed row name)")
            continue
        expected_output, max_staleness = expectations[name]
        if row is None:
            continue  # already reported above; no pre-compose tuple to compare

        # cadence — runner wake interval <= absorbed row's effective period
        period = effective_period_s(row)
        if period is None:
            v.append(f"{name}: absorbed row has no comparable cadence "
                     f"(schedule_kind={row.get('schedule_kind')!r}) — not a legitimate "
                     f"compose target (§9.3)")
        elif runner_interval is None:
            pass  # runner-row violation already recorded; cadence incomparable
        elif int(runner_interval) > int(period):
            v.append(f"{name}: cadence SLOWER after compose — runner interval "
                     f"{runner_interval}s > absorbed period {period}s (§9.2 cadence field)")

        # threshold — organ max_staleness <= the absorbed row's derived floor
        floor = registry._floor_for_entry(row)
        if floor is not None and max_staleness > int(floor):
            v.append(f"{name}: threshold LOOSENED — organ max_staleness_seconds "
                     f"{max_staleness} > absorbed row's derived floor {floor}s "
                     f"(§9.2 threshold field, SF5)")

        # probe — a PER-ORGAN artifact, never the shared runner log
        norm = os.path.expanduser(expected_output)
        if norm in runner_paths or os.path.basename(norm) in runner_basenames:
            v.append(f"{name}: probe targets the SHARED runner log "
                     f"({expected_output!r}) — a silent organ inside a live runner "
                     f"would never trip its floor (§9.2 probe field)")
        prior = seen_outputs.get(expected_output)
        if prior is not None:
            v.append(f"{name}: expected_output {expected_output!r} duplicates organ "
                     f"'{prior}' — probes must be per-organ artifacts (§9.2 probe field)")
        else:
            seen_outputs[expected_output] = name

    return sorted(v)


# ---------------------------------------------------------------------------
# §10 — the floor-aware wall-clock bound formula (N6)
# ---------------------------------------------------------------------------
def wall_clock_bound(p95_s: float) -> float:
    """The declared wall-clock regression bound for one pilot row (§10.2 + the
    S0 floor-aware bound note): bound = p95 x 1.25, FLOORED for sub-10s rows at
    p95 + 5.0s — max(p95 * 1.25, p95 + 5.0) when p95 < 10s.

    Rationale (the floor-aware note): a multiplicative-only tolerance hands a
    5ms row a 6.25ms bound — noise-width, guaranteed false-RED on any loaded
    host. The +5s absolute floor keeps sub-10s rows honest tripwires without
    weakening the x1.25 law for long rows. Pure and deterministic — the
    wall-clock MEASUREMENT stays a tripwire (env-armed, §10.5); only this
    bound formula is hash-stable.
    """
    if isinstance(p95_s, bool) or not isinstance(p95_s, (int, float)):
        raise ValueError("p95_s must be a number")
    if p95_s < 0:
        raise ValueError("p95_s must be >= 0")
    p = float(p95_s)
    if p < 10.0:
        return max(p * 1.25, p + 5.0)
    return p * 1.25
