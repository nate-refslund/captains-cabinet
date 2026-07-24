"""COG-4 W2 T2 — the DISPATCH/INTEGRITY sim corpus (contract
cognitive-core-phase-4-contract-2026-07-23 §12 rows 3, 5, 6, 9, 10, 11, 12, 14,
15 + the §7.3 six-limb recheck-order battery). Tests-first, file-seeded, no DSN,
deterministic — declared cutoffs, no clock (§12 preamble).

WHAT RUNS LIVE NOW vs WHAT IS SKIPPED (the W1-u2 mergeability idiom, §13):

  * LIVE — the fixture dispatch-simulator machinery in THIS file encodes the
    §7.3 dispatcher spec (serve → snapshot-staleness → authority → budget →
    organ-freshness → IDEMPOTENCY, the charter-quadruple-bearing order) as a
    pure reference function over scratch schedule stores, and EVERY §12
    negative-control mutant for the T2 sims is implemented as a real divergent
    dispatcher variant whose named escape is PROVEN TO BITE in this run
    (a property that the reference satisfies and the mutant fails — a gate
    without a biting mutant is decoration, §12). The shipped COG-3 store
    grounds the tampering idiom end-to-end: a real graph store is built via
    the cog3-rebuild.py CLI in a tmp root, forged, and observed to REFUSE
    through an allowlisted reader CLI (the serve-REFUSE precedent, §6.3).
  * SKIPPED — every arm that targets the not-yet-built dispatch CLI
    `cabinet/scripts/cog4-dispatch-shadow.py` carries a vacuity skip with an
    explicit RETIREMENT CONDITION in its docstring plus a companion absence
    assertion that goes RED the moment the CLI lands (§13: every vacuity guard
    carries its own retirement condition), so no skip can silently persist.
    RETIREMENTS (integrator corpus surgery per §13 + the unit
    contradictions[] routes, W5 landing 2026-07-24):
    cabinet/scripts/cog4-dispatch-shadow.py landed (W5 x1, 7272db13) — all 10
    TestRealDispatchCliArms companion absence assertions tripped RED as
    designed and every arm is converted per its own RETIREMENT CONDITION: the
    same scenario seeds and the same asserts, re-seeded onto REAL
    kernel-shaped stores and run against the landed CLI (subprocess adapter
    over its shadow-record output — `lib_cog4_dispatch_adapter`, a W5
    test-side lib, not a sibling W2 corpus file, so L1111 self-containment
    between parallel W2 units is intact). The fixture machinery, reference
    tier and every biting mutant above stay LIVE and unchanged.

SELF-CONTAINED BY LAW (LESSONS L1111): parallel W2 units never maintain shared
pinned constants — all machinery, seeds and mutants live in this file; nothing
here is imported by (or imports from) a sibling W2 corpus file.

FIXTURE-SHAPE HONESTY:
  * Fixture descriptors carry ONLY the three enforcement members the dispatch
    limbs may read — risk_class / ceiling / undo_contract — plus the open
    `capability` observation identity (§5.2). The presentation-only compat
    `action_type` member is deliberately OMITTED from fixture descriptors: no
    dispatch limb may key on it, and minting fixture members of the closed 30
    enum here would couple this unit to the classifier surface (L1111). The
    risk-class tokens below are obviously-fixture spellings (`fixture_low`…),
    never members of the real closed 13 — the fixture verdict policy maps them;
    the real matrix join is the W5 dispatcher's (§7.3(3)) and binds via the
    retirement arms.
  * The fixture organ manifests model the PROPOSED §4.2 organ fields
    (freshness_needs / fallback / permissions / dependencies / idempotency) as
    plain data. Nothing here validates against the germline extension schema —
    that is the §4.5 Captain-windowed W4 micro-unit; these tests do not touch
    or depend on it.
  * The fixture rows-hash is a chained digest over RE-PARSED canonical row
    bytes (content INCLUDED), the strict §6.3 shape — deliberately stricter
    than the shipped objectives identity-hash dialect, so hand-editing row
    CONTENT bites here (sim 11) even though the same edit does not move an
    identity-only chain.
  * The token discipline: no fenced data-plane literal appears in this file
    beyond tmp-path fixtures (the boundary manifest allowlists test_cog4_* for
    the scheduler store token; the objectives store token never appears here as
    a contiguous literal — the assembled-token discipline of the sibling
    boundary harness).

CORPUS LAW (§13): this unit is purely ADDITIVE — no existing test/lib file is
edited; any contradiction with an existing surface routes to the integrator.
Builders NEVER edit this corpus; retirement of the vacuity arms is the
integrator's move when the target CLIs land.

S0: python3.12, no DB, no network (the one subprocess family runs shipped
in-repo CLIs on tmp stores). Provenance: authored per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant
(COG-4 contract §12/§13; Fable 5 corpus authorship per the two-tier law).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The real-CLI adapter for the retired arms (W5 landing 2026-07-24 — module
# docstring RETIREMENTS note; a W5 test-side lib, never a sibling W2 corpus).
import lib_cog4_dispatch_adapter as A  # noqa: E402

# The real target surface (landed W5 x1; bound by the retired arms below).
_DISPATCH_CLI_REL = "cabinet/scripts/cog4-dispatch-shadow.py"
_DISPATCH_CLI = _REPO / _DISPATCH_CLI_REL

# Shipped COG-3 CLIs (the tampering-precedent arm; both on the boundary
# allowlists for their own store — this file only subprocess-runs them).
_COG3_REBUILD = _REPO / "cabinet" / "scripts" / "cog3-rebuild.py"
_COG3_INBOX = _REPO / "cabinet" / "scripts" / "cog3-verdict-inbox.py"

CUTOFF = "2026-07-20T00:00:00Z"
NOW = "2026-07-21T00:00:00Z"

# ===========================================================================
# Canonical bytes + the chained rows-hash (the §6.3 strict shape, fixture-local)
# ===========================================================================

_CHAIN_SEED = "cog4-w2-t2-schedule-fixture"


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rows_chain(rows) -> str:
    """Chained hash over RE-PARSED canonical row bytes (content included, §6.3
    — never file bytes, the A-m11 law), seeded with a fixture domain seed."""
    chain = _digest(_CHAIN_SEED.encode("utf-8"))
    for row in rows:
        chain = _digest((chain + _digest(_canon(row))).encode("utf-8"))
    return chain


def _atomic_write(path: Path, text: str) -> None:
    """tmp + os.replace — the kernel atomic-write IDIOM (§6.1e; the fixture
    omits O_EXCL+fsync, which are the W3 kernel's obligations)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ===========================================================================
# Snapshot / schedule-store fixture builders (§7.1-§7.2 shapes)
# ===========================================================================

_WAKE_INPUT_KEYS = (
    "cortex_belief_store_hash",
    "objectives_graph_rows_hash",
    "organ_registry_hash",
    "services_manifest_hash",
    "organ_health_hash",
    "failure_history_hash",
    "capability_availability_hash",
)


def make_snapshot(**overrides):
    """A §7.1-shaped wake snapshot: every input a DECLARED parameter (no env,
    no clock — A-M6); the SF2 families are explicit members."""
    snap = {
        "schema_version": "cog4-snapshot-fixture/v1",
        "wake_input_hashes": {
            "cortex_belief_store_hash": "cortexhash-aaa",
            "objectives_graph_rows_hash": "objgraphhash-bbb",
            "organ_registry_hash": "registryhash-ccc",
            "services_manifest_hash": "serviceshash-ddd",
            "organ_health_hash": "healthhash-eee",
            "failure_history_hash": "failhash-fff",
            "capability_availability_hash": "capshash-ggg",
        },
        "budget_version": "budget-v1",
        "posture_version": "posture-v1",
        "trust_table_version": "trust-v1",
        "scheduler_policy_version": "policy-v1",
        "scope": {"cabinet": "fixture"},
        "cutoff": CUTOFF,
    }
    for key, value in overrides.items():
        if key == "wake_input_hashes":
            snap["wake_input_hashes"] = dict(snap["wake_input_hashes"], **value)
        else:
            snap[key] = value
    return snap


def make_row(organ, operation, *, risk="fixture_low", ceiling=(), undo="none",
             budget_units=1, deps=(), planner_admitted=True, **extra):
    """A §7.2 decision row. The descriptor carries the three enforcement
    members + the open capability id ONLY (see FIXTURE-SHAPE HONESTY above)."""
    capability = f"{organ}/{operation}"
    row = {
        "organ": organ,
        "operation": operation,
        "descriptor": {
            "capability": capability,
            "risk_class": risk,
            "ceiling": sorted(ceiling),
            "undo_contract": undo,
        },
        "reason": "fixture-eligible",
        "budget_units": budget_units,
        "deps": sorted(deps),
        "tie_break_key": capability,
        "planner_admitted": planner_admitted,
    }
    row.update(extra)
    return row


def make_organ_manifest(name, *, max_staleness=3600, fallback="skip",
                        permissions=(), dependencies=(),
                        idem_fields=("organ", "operation", "wake_id")):
    """A fixture organ manifest modelling the PROPOSED §4.2 fields as data."""
    return {
        "name": name,
        "kind": "organ",
        "freshness_needs": {
            "max_staleness_seconds": max_staleness,
            "expected_output": f"out/{name}.json",
        },
        "fallback": fallback,
        "permissions": sorted(permissions),
        "dependencies": sorted(dependencies),
        "idempotency": {"key_fields": list(idem_fields)},
    }


def build_schedule_fixture(snapshot, rows, cache_dir: Path):
    """The deterministic fixture fold→store writer: rows total-ordered by
    (tie_break_key, canonical bytes) (§7.2 determinism), snapshot.json +
    schedule.jsonl + schedule-manifest.json written atomically, the manifest
    carrying the MANDATORY rows_hash (§6.3) + the epoch wake-input hashes."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: (r["tie_break_key"], _canon(r)))
    _atomic_write(cache_dir / "snapshot.json",
                  json.dumps(snapshot, sort_keys=True, indent=1) + "\n")
    _atomic_write(cache_dir / "schedule.jsonl",
                  "".join(_canon(r).decode("utf-8") + "\n" for r in ordered))
    manifest = {
        "schema_version": "cog4-schedule-fixture/v1",
        "epoch": {
            "scheduler_version": "fixture-1",
            "snapshot_hash": _digest(_canon(snapshot)),
            "wake_input_hashes": dict(snapshot["wake_input_hashes"]),
            "scope": snapshot["scope"],
            "cutoff": snapshot["cutoff"],
        },
        "rows_hash": _rows_chain(ordered),
        "counts": {"rows": len(ordered)},
    }
    _atomic_write(cache_dir / "schedule-manifest.json",
                  json.dumps(manifest, sort_keys=True, indent=1) + "\n")
    return manifest


def crashed_build(snapshot, rows, cache_dir: Path) -> None:
    """A mid-fold KILL (sim 15): the tmp file is written, the atomic replace
    never happens — a prior valid store (if any) must stay untouched."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: (r["tie_break_key"], _canon(r)))
    (cache_dir / "schedule.jsonl.tmp").write_text(
        "".join(_canon(r).decode("utf-8") + "\n" for r in ordered),
        encoding="utf-8")


def make_live(snapshot, manifests, **overrides):
    """Declared live state at (hypothetical) dispatch time — every member is
    data handed in, never an env/clock read."""
    live = {
        "wake_input_hashes": dict(snapshot["wake_input_hashes"]),
        "remaining_budget": 100,
        "wake_id": "wake-0001",
        "organ_output_age_seconds": {name: 0 for name in manifests},
        "organ_health": {name: {"probe_ran": True, "exit_code": 0}
                         for name in manifests},
        "organs_available": sorted(manifests),
        "capabilities_available": sorted(
            {p for m in manifests.values() for p in m["permissions"]}),
        "shadow_log": [],
        "services_cadence": [{"service": "fixture-cron-row",
                              "interval_seconds": 1800}],
    }
    live.update(overrides)
    return live


# ===========================================================================
# The verdict joint (fixture) — §5.2: predicates read risk_class/ceiling/
# undo_contract ONLY, never `capability`
# ===========================================================================

GATED_VERDICTS = frozenset({"always_gated", "propose_only", "ceiling", "undo_gap"})


def make_policy():
    return {
        "risk_verdicts": {
            "fixture_low": "auto_ok",
            "fixture_propose": "propose_only",
            "fixture_gated": "always_gated",
        },
        "undo_required": frozenset({"fixture_mutating"}),
    }


def resolve_verdict(descriptor, policy) -> str:
    """The capability-BLIND reference verdict resolution (§5.2: operation names
    carry no authority — only the three enforcement members are read)."""
    if descriptor["ceiling"]:
        return "ceiling"
    risk = descriptor["risk_class"]
    if risk in policy["undo_required"] and descriptor["undo_contract"] == "none":
        return "undo_gap"
    return policy["risk_verdicts"].get(risk, "auto_ok")


def mutant_verdict_capability_keyed(descriptor, policy) -> str:
    """§5.2 named mutant — a verdict function KEYING ON `capability`: any
    operation under the open `trusted-organ/` name is softened to auto_ok
    regardless of its enforcement members. Must FAIL the capability-blindness
    property."""
    if descriptor["capability"].startswith("trusted-organ/"):
        return "auto_ok"
    return resolve_verdict(descriptor, policy)


# ===========================================================================
# Health classification (sim 5, incl. the S0 finding) + floors (§9.2 analog)
# ===========================================================================

def classify_health(outcome) -> str:
    """S0 finding (§12 sim 5, T2 brief): a health_proof that RAN and exited 1
    is an HONEST FAILING probe — the organ is UNHEALTHY, with positive
    evidence. Only a probe that could not run at all is a CRASH (no health
    information; absence recorded honestly, never invented — §2.1/SF2)."""
    if outcome is None or not outcome.get("probe_ran"):
        return "crashed"
    return "healthy" if outcome.get("exit_code") == 0 else "unhealthy"


def mutant_classify_exit1_as_crash(outcome) -> str:
    """Named escape (S0 finding inverted): lumps every non-zero exit into
    "crashed", inventing a crash where the probe honestly reported unhealth."""
    if outcome is None or not outcome.get("probe_ran"):
        return "crashed"
    return "healthy" if outcome.get("exit_code") == 0 else "crashed"


def derive_floors(manifests, organ_health=None):
    """Per-organ watchdog floor pairs (expected_output, max_staleness) derived
    from manifests ONLY — health-INDEPENDENT by law (§12 sim 5 "floors still
    derive"; §9.2). `organ_health` is accepted and deliberately UNREAD."""
    return {name: (m["freshness_needs"]["expected_output"],
                   m["freshness_needs"]["max_staleness_seconds"])
            for name, m in sorted(manifests.items())}


def mutant_floor_crash_suppresses(manifests, organ_health):
    """§12 sim-5 named mutant — crash-suppresses-floor: a crashed/unhealthy
    organ silently LOSES its watchdog floor. Must FAIL the floors-still-derive
    property."""
    return {name: pair for name, pair in derive_floors(manifests).items()
            if classify_health((organ_health or {}).get(name)) == "healthy"}


def floor_fires(floors, live, outcome=None):
    """The watchdog-side floor check — INDEPENDENT of dispatch by construction
    (§12 sim 3 "watchdog floor fires independently"): `outcome` is accepted and
    deliberately UNREAD; only declared output ages are consulted."""
    fired = set()
    for name, (_expected, need) in floors.items():
        age = live["organ_output_age_seconds"].get(name)
        if age is not None and age > need:
            fired.add(name)
    return fired


def mutant_floor_consults_dispatch(floors, live, outcome):
    """Supplementary named escape — a floor that reads the dispatch outcome and
    SUPPRESSES itself for organs the dispatcher already refused-with-flag
    (dependence where the law demands independence). Must FAIL sim 3's
    independence property."""
    fired = floor_fires(floors, live)
    if outcome is not None:
        already = {r["organ"] for r in outcome.records
                   if r.get("staleness_flagged")}
        fired -= already
    return fired


# ===========================================================================
# The dispatcher (reference + named-escape mutants) — §7.3 six limbs in order
# ===========================================================================

class Outcome:
    """A shadow dispatch outcome. `mode` ∈ {dispatch, serve_refused,
    stale_snapshot, safe_fallback}; only mode="dispatch" may carry
    decision="would_dispatch" records — every other mode grants NOTHING."""

    def __init__(self, mode, reason, records, safe_schedule=None):
        self.mode = mode
        self.reason = reason
        self.records = records
        self.safe_schedule = safe_schedule

    def would_dispatch(self):
        return [r for r in self.records if r["decision"] == "would_dispatch"]


def _record(row, decision, reason, limb, **extra):
    rec = {
        "organ": row["organ"],
        "operation": row["operation"],
        "capability": row["descriptor"]["capability"],
        "descriptor": dict(row["descriptor"]),
        "decision": decision,
        "reason": reason,
        "limb": limb,
        "planner_admitted": row.get("planner_admitted", False),
    }
    rec.update(extra)
    return rec


def _load_store(cache_dir: Path):
    """Availability classification precedes integrity: what cannot be parsed
    cannot be verified (§7.4 missing/corrupt ⇒ safe fallback; §6.3 integrity
    refusals require a parseable store)."""
    cache_dir = Path(cache_dir)
    snap_p = cache_dir / "snapshot.json"
    rows_p = cache_dir / "schedule.jsonl"
    man_p = cache_dir / "schedule-manifest.json"
    if not (snap_p.exists() and rows_p.exists() and man_p.exists()):
        return "missing", None, None, None
    try:
        snapshot = json.loads(snap_p.read_text(encoding="utf-8"))
        manifest = json.loads(man_p.read_text(encoding="utf-8"))
        rows = [json.loads(line) for line
                in rows_p.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "corrupt", None, None, None
    return "ok", snapshot, manifest, rows


def derive_idempotency_key(row, manifest, live) -> str:
    """Limb 6 (§7.3 SF1): the key is RE-DERIVED per the organ manifest's
    declared idempotency discipline — never trusted from the row."""
    context = {"organ": row["organ"], "operation": row["operation"],
               "wake_id": live["wake_id"]}
    fields = manifest["idempotency"]["key_fields"]
    missing = [f for f in fields if f not in context]
    if missing:
        raise AssertionError(f"fixture bug: idempotency key_fields {missing} "
                             "have no declared context value")
    return _digest(_canon({f: context[f] for f in fields}))


def _dispatch_core(cache_dir, live, manifests, policy, *,
                   verdict_fn=resolve_verdict, escapes=frozenset()):
    """The §7.3 dispatcher spec, encoded. `escapes` names the EXACT deviation a
    mutant carries (greppable; empty for the reference). PURE: reads the store
    + declared live state, returns records, executes nothing, writes nothing."""
    status, _snapshot, manifest, rows = _load_store(cache_dir)
    if status != "ok":
        # §7.4: missing/corrupt state ⇒ the FIXED SAFE SCHEDULE (the services
        # manifest's own cadence) and NEVER permission.
        if "fallback_implies_permission" in escapes:
            granted = [_record(make_row("safe-fallback", entry["service"]),
                               "would_dispatch", f"store_{status}:auto_grant",
                               "fallback")
                       for entry in live["services_cadence"]]
            return Outcome("safe_fallback", f"store_{status}", granted,
                           safe_schedule=list(live["services_cadence"]))
        return Outcome("safe_fallback", f"store_{status}", [],
                       safe_schedule=list(live["services_cadence"]))

    # ---- limb 1: SERVE (verified single read + REFUSE limbs, §6.3) ----------
    if "skip_when_absent_rows_hash" in escapes:
        recorded_rows_hash = manifest.get("rows_hash")   # the objectives shape
        if recorded_rows_hash is not None and _rows_chain(rows) != recorded_rows_hash:
            return Outcome("serve_refused", "rows_hash_mismatch", [])
    else:
        if "rows_hash" not in manifest:
            # §6.3 MANDATORY-PRESENT: an absent key REFUSES (closing the
            # objectives skip-when-absent hole for this surface).
            return Outcome("serve_refused", "rows_hash_key_absent", [])
        if _rows_chain(rows) != manifest["rows_hash"]:
            return Outcome("serve_refused", "rows_hash_mismatch", [])
    if _digest(_canon(_snapshot)) != manifest["epoch"]["snapshot_hash"]:
        # the counterfactual-style mismatch limb (§7.3(1)).
        return Outcome("serve_refused", "snapshot_hash_mismatch", [])

    # ---- limb 2: SNAPSHOT FRESHNESS (stale-snapshot, N3) --------------------
    recorded = manifest["epoch"]["wake_input_hashes"]
    live_hashes = live["wake_input_hashes"]
    for key in sorted(set(recorded) | set(live_hashes)):
        rec_v, live_v = recorded.get(key), live_hashes.get(key)
        if "null_hole_comparator" in escapes:
            # the named §12 sim-14 escape: `is not None and` — a recorded null
            # skips the compare even when a live value exists.
            if rec_v is not None and rec_v != live_v:
                return Outcome("stale_snapshot", f"stale_snapshot:{key}", [])
        else:
            # symmetric: ANY difference — including recorded-null-but-live-
            # exists and live-null-but-recorded-exists — REFUSES.
            if rec_v != live_v:
                return Outcome("stale_snapshot", f"stale_snapshot:{key}", [])

    # ---- per-row limbs 3..6 (+ the live-eligibility rechecks) ---------------
    records = []
    cumulative = 0
    seen_keys = {r["idempotency_key"] for r in live["shadow_log"]
                 if "idempotency_key" in r}
    limb_order = ["authority", "budget"]
    if "order_budget_before_authority" in escapes:
        limb_order = ["budget", "authority"]

    for row in rows:
        organ = row["organ"]
        manifest_for = manifests[organ]
        descriptor = row["descriptor"]
        refused = None

        for limb in limb_order:
            if limb == "authority" and "verdict_ignoring" not in escapes:
                verdict = verdict_fn(descriptor, policy)
                if verdict in GATED_VERDICTS:
                    refused = _record(row, "refused", f"authority:{verdict}",
                                      "authority", verdict=verdict)
                    break
            if limb == "budget":
                admitted = row.get("planner_admitted", False)
                if "planner_said_yes" in escapes and admitted:
                    continue                      # trusts the plan — the escape
                if cumulative + row["budget_units"] > live["remaining_budget"]:
                    refused = _record(row, "refused", "budget_overflow",
                                      "budget")
                    break
        if refused is not None:
            records.append(refused)
            continue

        # limb 5: organ freshness_needs vs live staleness.
        age = live["organ_output_age_seconds"].get(organ)
        need = manifest_for["freshness_needs"]["max_staleness_seconds"]
        if age is not None and age > need:
            if "staleness_implies_dispatch" in escapes:
                # the named §12 sim-3 escape: staleness becomes AUTO-PERMISSION
                # to run outside ceilings ("refresh it now").
                records.append(_record(row, "would_dispatch",
                                       "auto_refresh_outside_ceilings",
                                       "freshness", staleness_flagged=True))
                cumulative += row["budget_units"]
                continue
            records.append(_record(row, "refused", f"stale_organ:age={age}",
                                   "freshness", staleness_flagged=True))
            continue

        # live-eligibility rechecks (sims 5/6/9). Placement between the pinned
        # limbs 5 and 6 is FIXTURE-LOCAL: §7.3 pins the order of the six named
        # limbs only; these properties assert refusal+reason, never position.
        health = classify_health(live["organ_health"].get(organ))
        if health != "healthy":
            fallback = manifest_for["fallback"]
            if fallback == "safe_noop":
                records.append(_record(row, "safe_noop",
                                       f"health_{health}:fallback_safe_noop",
                                       "eligibility", health=health,
                                       fallback=fallback))
            elif fallback == "escalate":
                records.append(_record(row, "escalation_flagged",
                                       f"health_{health}:fallback_escalate",
                                       "eligibility", health=health,
                                       fallback=fallback))
            else:
                records.append(_record(row, "refused",
                                       f"health_{health}:fallback_skip",
                                       "eligibility", health=health,
                                       fallback=fallback))
            continue

        if "dispatch_anyway_on_missing_dep" not in escapes:
            dep_missing = None
            for dep in sorted(set(row["deps"]) | set(manifest_for["dependencies"])):
                if dep.startswith("organ:"):
                    if dep.split(":", 1)[1] not in live["organs_available"]:
                        dep_missing = dep
                        break
                elif dep not in live["capabilities_available"]:
                    dep_missing = dep
                    break
            if dep_missing is not None:
                records.append(_record(row, "refused",
                                       f"dependency_unavailable:{dep_missing}",
                                       "eligibility"))
                continue

        capability_missing = next(
            (p for p in manifest_for["permissions"]
             if p not in live["capabilities_available"]), None)
        if capability_missing is not None:
            if "silent_substitute_capability" in escapes:
                # the named §12 sim-9 escape: silently RE-CLASSIFY the work to
                # an available capability and proceed.
                substitute = (sorted(live["capabilities_available"])[0]
                              if live["capabilities_available"] else "mcp:none")
                swapped = dict(row, descriptor=dict(descriptor,
                                                    capability=substitute))
                records.append(_record(swapped, "would_dispatch",
                                       "substituted_capability", "eligibility"))
                cumulative += row["budget_units"]
                continue
            records.append(_record(row, "refused",
                                   f"capability_unavailable:{capability_missing}",
                                   "eligibility"))
            continue

        # limb 6: IDEMPOTENCY (SF1 — the charter quadruple's fourth member).
        if "trust_row_idempotency_key" in escapes:
            key = row.get("idempotency_key",
                          derive_idempotency_key(row, manifest_for, live))
        else:
            key = derive_idempotency_key(row, manifest_for, live)
        if key in seen_keys:
            records.append(_record(row, "refused", "idempotency_replay",
                                   "idempotency", idempotency_key=key))
            continue

        seen_keys.add(key)
        cumulative += row["budget_units"]
        records.append(_record(row, "would_dispatch", "all_limbs_green",
                               "none", idempotency_key=key))

    return Outcome("dispatch", None, records)


def reference_dispatch(cache_dir, live, manifests, policy):
    """THE spec-encoded §7.3 reference dispatcher (shadow comparator): serve →
    snapshot-staleness → authority → budget → organ-freshness → idempotency;
    pure; never executes; refusals carry explicit reasons."""
    return _dispatch_core(cache_dir, live, manifests, policy)


def mutant_staleness_implies_dispatch(cache_dir, live, manifests, policy):
    """§12 sim-3 named mutant: staleness-implies-dispatch."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"staleness_implies_dispatch"}))


def mutant_dispatch_anyway(cache_dir, live, manifests, policy):
    """§12 sim-6 named mutant: dispatch-anyway (dependency check dropped)."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"dispatch_anyway_on_missing_dep"}))


def mutant_silent_substitute(cache_dir, live, manifests, policy):
    """§12 sim-9 named mutant: silent-substitute (capability re-classified)."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"silent_substitute_capability"}))


def mutant_verdict_ignoring(cache_dir, live, manifests, policy):
    """§12 sim-10 named mutant: verdict-ignoring dispatcher."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"verdict_ignoring"}))


def mutant_skip_when_absent(cache_dir, live, manifests, policy):
    """§12 sim-11 named mutant: the objectives skip-when-absent limb shape
    (`is not None and` — the query.py:214-215 hole, §6.3)."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"skip_when_absent_rows_hash"}))


def mutant_planner_said_yes(cache_dir, live, manifests, policy):
    """§12 sim-12 named mutant: planner-said-yes-so-dispatch."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"planner_said_yes"}))


def mutant_null_hole_comparator(cache_dir, live, manifests, policy):
    """§12 sim-14 named mutant: null-hole-skipping comparator."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"null_hole_comparator"}))


def mutant_fallback_implies_permission(cache_dir, live, manifests, policy):
    """§12 sim-15 named mutant: fallback-implies-permission."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"fallback_implies_permission"}))


def mutant_order_swapped(cache_dir, live, manifests, policy):
    """§7.3 order mutant: budget checked BEFORE authority."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"order_budget_before_authority"}))


def mutant_trusts_row_key(cache_dir, live, manifests, policy):
    """§7.3 limb-6 named mutant: trusts the row's carried idempotency key
    instead of RE-DERIVING per the manifest discipline (SF1)."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          escapes=frozenset({"trust_row_idempotency_key"}))


def mutant_capability_keyed_dispatch(cache_dir, live, manifests, policy):
    """§5.2 named mutant routed through dispatch: the verdict joint keys on
    `capability` (softens `trusted-organ/*`)."""
    return _dispatch_core(cache_dir, live, manifests, policy,
                          verdict_fn=mutant_verdict_capability_keyed)


# ===========================================================================
# Seed helper
# ===========================================================================

def _seed(tmp_path, rows, manifests, *, snapshot=None, live_overrides=None):
    snapshot = snapshot or make_snapshot()
    cache_dir = tmp_path / "cache" / "scheduler-fixture"
    build_schedule_fixture(snapshot, rows, cache_dir)
    live = make_live(snapshot, manifests, **(live_overrides or {}))
    return cache_dir, live, manifests, make_policy(), snapshot


def _by_organ(outcome, organ):
    matches = [r for r in outcome.records if r["organ"] == organ]
    assert matches, f"no record for organ {organ!r}: {outcome.records}"
    return matches[0]


# ===========================================================================
# Machinery determinism + atomicity + purity (sim 15's N1/mid-fold arms)
# ===========================================================================

class TestMachineryDeterminism:
    def test_rebuild_reproduces_identical_store_and_hash(self, tmp_path):
        """Sim 15 N1-analog on the fixture machinery: rebuilding from the SAME
        snapshot reproduces the identical rows-hash AND identical store bytes;
        input row ORDER is irrelevant (total-ordered fold, §7.2). The real
        kernel's PYTHONHASHSEED subprocess triple is the W3 gate — this arm
        pins the fixture algebra it must reproduce."""
        snapshot = make_snapshot()
        rows = [make_row("organ-a", "collect"), make_row("organ-b", "report")]
        m1 = build_schedule_fixture(snapshot, rows, tmp_path / "c1")
        m2 = build_schedule_fixture(snapshot, list(reversed(rows)), tmp_path / "c2")
        assert m1["rows_hash"] == m2["rows_hash"]
        for name in ("snapshot.json", "schedule.jsonl", "schedule-manifest.json"):
            assert ((tmp_path / "c1" / name).read_bytes()
                    == (tmp_path / "c2" / name).read_bytes()), name
        # delete → rebuild-from-snapshot reproduces the hash (§12 sim 15).
        for name in ("snapshot.json", "schedule.jsonl", "schedule-manifest.json"):
            (tmp_path / "c1" / name).unlink()
        m3 = build_schedule_fixture(snapshot, rows, tmp_path / "c1")
        assert m3["rows_hash"] == m1["rows_hash"]

    def test_mid_fold_kill_leaves_prior_store_servable(self, tmp_path):
        """Sim 15 mid-fold-kill arm: the atomic-write idiom means a killed
        build leaves EITHER no store (safe fallback) OR the prior valid store
        (still serves) — never a torn half-store."""
        cache = tmp_path / "cache" / "scheduler-fixture"
        snapshot = make_snapshot()
        rows = [make_row("organ-a", "collect")]
        manifests = {"organ-a": make_organ_manifest("organ-a")}
        # kill with NO prior store: only a .tmp exists ⇒ missing ⇒ fallback.
        crashed_build(snapshot, rows, cache)
        live = make_live(snapshot, manifests)
        out = reference_dispatch(cache, live, manifests, make_policy())
        assert out.mode == "safe_fallback"
        assert out.would_dispatch() == []
        # valid store, then a killed REBUILD over it: old store still serves.
        build_schedule_fixture(snapshot, rows, cache)
        crashed_build(snapshot, [make_row("organ-z", "later")], cache)
        out2 = reference_dispatch(cache, live, manifests, make_policy())
        assert out2.mode == "dispatch"
        assert [r["organ"] for r in out2.would_dispatch()] == ["organ-a"]

    def test_dispatch_is_pure_no_writes_no_live_mutation(self, tmp_path):
        """§7.3: the dispatcher NEVER executes anything — the reference reads
        the store + declared live state and returns records; store bytes and
        the live structure are byte-identical after the call."""
        rows = [make_row("organ-a", "collect")]
        manifests = {"organ-a": make_organ_manifest("organ-a")}
        cache, live, manifests, policy, _ = _seed(tmp_path, rows, manifests)
        before_files = {p.name: p.read_bytes() for p in sorted(cache.iterdir())}
        before_live = copy.deepcopy(live)
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "dispatch"
        after_files = {p.name: p.read_bytes() for p in sorted(cache.iterdir())}
        assert after_files == before_files
        assert live == before_live


# ===========================================================================
# SIM 3 — stale organ (§12 row 3)
# ===========================================================================

def _check_sim3(dispatch_fn, tmp_path):
    """Stale organ ⇒ refusal WITH the staleness flag; NEVER would-dispatch
    (staleness is never auto-permission to run outside ceilings); the fresh
    organ is unaffected."""
    rows = [make_row("stale-organ", "collect"), make_row("fresh-organ", "collect")]
    manifests = {"stale-organ": make_organ_manifest("stale-organ", max_staleness=3600),
                 "fresh-organ": make_organ_manifest("fresh-organ", max_staleness=3600)}
    cache, live, manifests, policy, _ = _seed(
        tmp_path, rows, manifests,
        live_overrides={"organ_output_age_seconds": {"stale-organ": 7200,
                                                     "fresh-organ": 60}})
    out = dispatch_fn(cache, live, manifests, policy)
    assert out.mode == "dispatch"
    stale = _by_organ(out, "stale-organ")
    assert stale["decision"] == "refused", stale
    assert stale["staleness_flagged"] is True
    assert stale["reason"].startswith("stale_organ:")
    assert [r["organ"] for r in out.would_dispatch()] == ["fresh-organ"]
    return out, live, manifests


class TestSim3StaleOrgan:
    def test_stale_refused_flagged_never_auto_permission(self, tmp_path):
        _check_sim3(reference_dispatch, tmp_path)

    def test_watchdog_floor_fires_independently(self, tmp_path):
        """The floor trips for the stale organ REGARDLESS of the dispatch
        outcome — the floor function never reads the outcome (independence)."""
        out, live, manifests = _check_sim3(reference_dispatch, tmp_path)
        floors = derive_floors(manifests)
        assert floor_fires(floors, live, out) == {"stale-organ"}
        assert floor_fires(floors, live, None) == {"stale-organ"}

    def test_staleness_beats_nothing_authority_still_first(self, tmp_path):
        """A stale organ whose descriptor is ALSO gated refuses at AUTHORITY
        (limb 3 < limb 5): staleness can never override an authority verdict
        (sim 3's never-outside-ceilings clause meets the §7.3 order)."""
        rows = [make_row("stale-gated", "mutate", risk="fixture_gated")]
        manifests = {"stale-gated": make_organ_manifest("stale-gated")}
        cache, live, manifests, policy, _ = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organ_output_age_seconds": {"stale-gated": 9999}})
        out = reference_dispatch(cache, live, manifests, policy)
        rec = _by_organ(out, "stale-gated")
        assert rec["decision"] == "refused"
        assert rec["limb"] == "authority"
        assert rec["reason"] == "authority:always_gated"

    def test_mutant_staleness_implies_dispatch_bites(self, tmp_path):
        """The §12 sim-3 negative control MUST FAIL: the mutant turns staleness
        into would-dispatch (auto-permission outside ceilings)."""
        with pytest.raises(AssertionError):
            _check_sim3(mutant_staleness_implies_dispatch, tmp_path)

    def test_mutant_floor_consults_dispatch_bites(self, tmp_path):
        """Supplementary negative control: a floor that suppresses itself when
        the dispatcher already flagged the organ (dependence) fails the
        independence property."""
        out, live, manifests = _check_sim3(reference_dispatch, tmp_path)
        floors = derive_floors(manifests)
        with pytest.raises(AssertionError):
            assert mutant_floor_consults_dispatch(floors, live, out) == {"stale-organ"}


# ===========================================================================
# SIM 5 — organ crash (§12 row 5, incl. the S0 exit-1 finding)
# ===========================================================================

def _sim5_seed(tmp_path):
    rows = [make_row("crash-skip", "collect"),
            make_row("crash-noop", "collect"),
            make_row("crash-esc", "collect"),
            make_row("healthy-organ", "collect")]
    manifests = {
        "crash-skip": make_organ_manifest("crash-skip", fallback="skip"),
        "crash-noop": make_organ_manifest("crash-noop", fallback="safe_noop"),
        "crash-esc": make_organ_manifest("crash-esc", fallback="escalate"),
        "healthy-organ": make_organ_manifest("healthy-organ"),
    }
    health = {
        "crash-skip": {"probe_ran": False},                      # true crash
        "crash-noop": {"probe_ran": True, "exit_code": 1},       # honest failing
        "crash-esc": {"probe_ran": False},                       # true crash
        "healthy-organ": {"probe_ran": True, "exit_code": 0},
    }
    cache, live, manifests, policy, _ = _seed(
        tmp_path, rows, manifests, live_overrides={"organ_health": health})
    return cache, live, manifests, policy, health


class TestSim5OrganCrash:
    def test_manifest_fallback_honored_others_unaffected(self, tmp_path):
        """skip ⇒ refused; safe_noop ⇒ a safe_noop record; escalate ⇒ an
        escalation flag record — NONE would-dispatch; the healthy organ is
        untouched by its neighbors' failures."""
        cache, live, manifests, policy, _health = _sim5_seed(tmp_path)
        out = reference_dispatch(cache, live, manifests, policy)
        assert _by_organ(out, "crash-skip")["decision"] == "refused"
        assert _by_organ(out, "crash-skip")["reason"] == "health_crashed:fallback_skip"
        assert _by_organ(out, "crash-noop")["decision"] == "safe_noop"
        assert _by_organ(out, "crash-esc")["decision"] == "escalation_flagged"
        assert [r["organ"] for r in out.would_dispatch()] == ["healthy-organ"]

    def test_exit1_health_proof_is_unhealthy_not_crash(self, tmp_path):
        """The S0 finding (T2 brief): a health_proof that RAN and exited 1 is
        an honest FAILING probe — classified `unhealthy` (positive evidence),
        NEVER `crashed` (absence of evidence); the two classes stay distinct in
        the shadow record."""
        cache, live, manifests, policy, _health = _sim5_seed(tmp_path)
        out = reference_dispatch(cache, live, manifests, policy)
        assert _by_organ(out, "crash-noop")["health"] == "unhealthy"
        assert _by_organ(out, "crash-skip")["health"] == "crashed"
        assert classify_health({"probe_ran": True, "exit_code": 1}) == "unhealthy"
        assert classify_health({"probe_ran": False}) == "crashed"
        assert classify_health(None) == "crashed"

    def test_floors_still_derive_for_failing_organs(self, tmp_path):
        """§12 sim 5 "floors still derive": the floor set is manifest-derived
        and health-INDEPENDENT — a crashed organ keeps its watchdog floor."""
        _cache, _live, manifests, _policy, health = _sim5_seed(tmp_path)
        floors = derive_floors(manifests, health)
        assert set(floors) == {"crash-skip", "crash-noop", "crash-esc",
                               "healthy-organ"}

    def test_mutant_crash_suppresses_floor_bites(self, tmp_path):
        """The §12 sim-5 negative control MUST FAIL: the mutant drops the
        floors of non-healthy organs (silent watchdog-coverage loss)."""
        _cache, _live, manifests, _policy, health = _sim5_seed(tmp_path)
        with pytest.raises(AssertionError):
            floors = mutant_floor_crash_suppresses(manifests, health)
            assert set(floors) == {"crash-skip", "crash-noop", "crash-esc",
                                   "healthy-organ"}

    def test_mutant_exit1_lumped_as_crash_bites(self):
        """The S0-finding negative control MUST FAIL: a classifier that lumps
        exit-1 into `crashed` invents a crash where the probe honestly reported
        unhealth."""
        with pytest.raises(AssertionError):
            assert mutant_classify_exit1_as_crash(
                {"probe_ran": True, "exit_code": 1}) == "unhealthy"


# ===========================================================================
# SIM 6 — dependency failure (§12 row 6)
# ===========================================================================

def _check_sim6(dispatch_fn, tmp_path):
    """Work whose organ/capability dependency is unavailable is NOT chosen and
    the refusal carries the explicit dependency in its reason."""
    rows = [make_row("dependent-organ", "aggregate", deps=("organ:upstream-organ",)),
            make_row("cap-dependent", "fetch"),
            make_row("independent", "collect")]
    manifests = {
        "dependent-organ": make_organ_manifest("dependent-organ"),
        "cap-dependent": make_organ_manifest(
            "cap-dependent", dependencies=("mcp:alpha-service",)),
        "independent": make_organ_manifest("independent"),
    }
    cache, live, manifests, policy, _ = _seed(
        tmp_path, rows, manifests,
        live_overrides={"organs_available": ["dependent-organ", "cap-dependent",
                                            "independent"],   # upstream ABSENT
                        "capabilities_available": []})        # mcp dep ABSENT
    out = dispatch_fn(cache, live, manifests, policy)
    organ_dep = _by_organ(out, "dependent-organ")
    assert organ_dep["decision"] == "refused", organ_dep
    assert organ_dep["reason"] == "dependency_unavailable:organ:upstream-organ"
    cap_dep = _by_organ(out, "cap-dependent")
    assert cap_dep["decision"] == "refused", cap_dep
    assert cap_dep["reason"] == "dependency_unavailable:mcp:alpha-service"
    assert [r["organ"] for r in out.would_dispatch()] == ["independent"]


class TestSim6DependencyFailure:
    def test_unavailable_dependency_refused_with_explicit_reason(self, tmp_path):
        _check_sim6(reference_dispatch, tmp_path)

    def test_available_dependency_dispatches(self, tmp_path):
        """Control: with the dependency PRESENT the same row dispatches — the
        refusal above is attributable to the dependency alone."""
        rows = [make_row("dependent-organ", "aggregate",
                         deps=("organ:upstream-organ",))]
        manifests = {"dependent-organ": make_organ_manifest("dependent-organ")}
        cache, live, manifests, policy, _ = _seed(
            tmp_path, rows, manifests,
            live_overrides={"organs_available": ["dependent-organ",
                                                "upstream-organ"]})
        out = reference_dispatch(cache, live, manifests, policy)
        assert [r["organ"] for r in out.would_dispatch()] == ["dependent-organ"]

    def test_mutant_dispatch_anyway_bites(self, tmp_path):
        """The §12 sim-6 negative control MUST FAIL: the mutant dispatches the
        dependent work although its dependency is unavailable."""
        with pytest.raises(AssertionError):
            _check_sim6(mutant_dispatch_anyway, tmp_path)


# ===========================================================================
# SIM 9 — unavailable MCP (§12 row 9)
# ===========================================================================

def _check_sim9(dispatch_fn, tmp_path):
    """A declared capability whose MCP is absent ⇒ the work is skipped WITH a
    reason naming the capability, and the record preserves the ORIGINAL
    capability + descriptor — NEVER a silent re-classification."""
    rows = [make_row("mcp-organ", "sync"), make_row("plain-organ", "collect")]
    manifests = {
        "mcp-organ": make_organ_manifest("mcp-organ",
                                         permissions=("mcp:vault-read",)),
        "plain-organ": make_organ_manifest("plain-organ"),
    }
    cache, live, manifests, policy, _ = _seed(
        tmp_path, rows, manifests,
        live_overrides={"capabilities_available": ["mcp:other-available"]})
    out = dispatch_fn(cache, live, manifests, policy)
    rec = _by_organ(out, "mcp-organ")
    assert rec["decision"] == "refused", rec
    assert rec["reason"] == "capability_unavailable:mcp:vault-read"
    # identity preservation — the exact anti-silent-substitution clause:
    assert rec["capability"] == "mcp-organ/sync"
    assert rec["descriptor"]["capability"] == "mcp-organ/sync"
    assert not [r for r in out.would_dispatch() if r["organ"] == "mcp-organ"]
    assert [r["organ"] for r in out.would_dispatch()] == ["plain-organ"]


class TestSim9UnavailableMcp:
    def test_missing_mcp_skipped_with_reason_identity_preserved(self, tmp_path):
        _check_sim9(reference_dispatch, tmp_path)

    def test_mutant_silent_substitute_bites(self, tmp_path):
        """The §12 sim-9 negative control MUST FAIL: the mutant re-classifies
        the work to an available capability and would-dispatches it."""
        with pytest.raises(AssertionError):
            _check_sim9(mutant_silent_substitute, tmp_path)


# ===========================================================================
# SIM 10 — unauthorized effect (§12 row 10, N5) + §5.2 capability-blindness
# ===========================================================================

def _check_sim10(dispatch_fn, tmp_path):
    """A decision whose descriptor resolves to a gated/ceiling/undo-gap verdict
    NEVER would-dispatches; the refusal record carries the verdict."""
    rows = [
        make_row("gated-organ", "mutate", risk="fixture_gated"),
        make_row("propose-organ", "draft", risk="fixture_propose"),
        make_row("ceiling-organ", "spend", ceiling=("spending",)),
        make_row("undo-gap-organ", "rewrite", risk="fixture_mutating", undo="none"),
        make_row("clean-organ", "collect"),
    ]
    manifests = {r["organ"]: make_organ_manifest(r["organ"]) for r in rows}
    cache, live, manifests, policy, _ = _seed(tmp_path, rows, manifests)
    out = dispatch_fn(cache, live, manifests, policy)
    expected = {
        "gated-organ": "always_gated",
        "propose-organ": "propose_only",
        "ceiling-organ": "ceiling",
        "undo-gap-organ": "undo_gap",
    }
    for organ, verdict in expected.items():
        rec = _by_organ(out, organ)
        assert rec["decision"] == "refused", (organ, rec)
        assert rec["verdict"] == verdict
        assert rec["reason"] == f"authority:{verdict}"
    assert [r["organ"] for r in out.would_dispatch()] == ["clean-organ"]


class TestSim10UnauthorizedEffect:
    def test_gated_verdicts_never_would_dispatch(self, tmp_path):
        _check_sim10(reference_dispatch, tmp_path)

    def test_verdict_resolution_is_capability_blind(self):
        """§5.2: two descriptors identical in their enforcement members but
        differing in `capability` MUST resolve identically — operation names
        carry no authority."""
        policy = make_policy()
        plain = {"capability": "plain-organ/mutate", "risk_class": "fixture_gated",
                 "ceiling": [], "undo_contract": "none"}
        trusted = dict(plain, capability="trusted-organ/mutate")
        assert resolve_verdict(plain, policy) == resolve_verdict(trusted, policy)
        assert resolve_verdict(trusted, policy) == "always_gated"

    def test_mutant_verdict_ignoring_bites(self, tmp_path):
        """The §12 sim-10 negative control MUST FAIL: the mutant dispatches
        without consulting the verdict."""
        with pytest.raises(AssertionError):
            _check_sim10(mutant_verdict_ignoring, tmp_path)

    def test_mutant_capability_keyed_verdict_bites(self, tmp_path):
        """The §5.2 negative control MUST FAIL: a verdict function keying on
        `capability` softens `trusted-organ/*` and breaks blindness — and a
        dispatcher riding it would-dispatches a gated operation."""
        policy = make_policy()
        plain = {"capability": "plain-organ/mutate", "risk_class": "fixture_gated",
                 "ceiling": [], "undo_contract": "none"}
        trusted = dict(plain, capability="trusted-organ/mutate")
        with pytest.raises(AssertionError):
            assert (mutant_verdict_capability_keyed(plain, policy)
                    == mutant_verdict_capability_keyed(trusted, policy))
        # and through dispatch: the gated trusted-organ row escapes (N5 broken).
        rows = [make_row("trusted-organ", "mutate", risk="fixture_gated")]
        manifests = {"trusted-organ": make_organ_manifest("trusted-organ")}
        cache, live, manifests_d, pol, _ = _seed(tmp_path, rows, manifests)
        with pytest.raises(AssertionError):
            out = mutant_capability_keyed_dispatch(cache, live, manifests_d, pol)
            assert out.would_dispatch() == []


# ===========================================================================
# SIM 11 — forged scheduler decision (§12 row 11, §6.3, N3)
# ===========================================================================

def _forged_seed(tmp_path):
    rows = [make_row("organ-a", "collect"), make_row("organ-b", "report")]
    manifests = {"organ-a": make_organ_manifest("organ-a"),
                 "organ-b": make_organ_manifest("organ-b")}
    return _seed(tmp_path, rows, manifests)


def _check_sim11_absent_key(dispatch_fn, tmp_path):
    """§6.3 MANDATORY-PRESENT: a manifest with the rows-hash key REMOVED
    REFUSES — the absent key can never serve unbound rows."""
    cache, live, manifests, policy, _ = _forged_seed(tmp_path)
    man_path = cache / "schedule-manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    del manifest["rows_hash"]
    man_path.write_text(json.dumps(manifest, sort_keys=True, indent=1) + "\n",
                        encoding="utf-8")
    out = dispatch_fn(cache, live, manifests, policy)
    assert out.mode == "serve_refused", (out.mode, out.reason)
    assert out.reason == "rows_hash_key_absent"
    assert out.records == [] and out.would_dispatch() == []


class TestSim11ForgedDecision:
    @pytest.mark.parametrize("tamper", ["edit_content", "append_row", "drop_row"])
    def test_hand_edited_schedule_refuses(self, tmp_path, tamper):
        """A hand-edited schedule.jsonl (content edit / forged append / row
        drop) no longer reproduces the manifest rows-hash ⇒ REFUSE, no records
        served. Content edits bite because the fixture chain hashes FULL
        canonical row bytes (§6.3 strict shape)."""
        cache, live, manifests, policy, _ = _forged_seed(tmp_path)
        rows_path = cache / "schedule.jsonl"
        lines = rows_path.read_text(encoding="utf-8").splitlines()
        if tamper == "edit_content":
            lines[0] = lines[0].replace('"budget_units":1', '"budget_units":0')
        elif tamper == "append_row":
            lines.append(_canon(make_row("forged-organ", "exfiltrate")).decode("utf-8"))
        else:
            lines = lines[1:]
        rows_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "serve_refused", (out.mode, out.reason)
        assert out.reason == "rows_hash_mismatch"
        assert out.records == [] and out.would_dispatch() == []

    def test_manifest_with_rows_hash_key_removed_refuses(self, tmp_path):
        _check_sim11_absent_key(reference_dispatch, tmp_path)

    def test_tampered_snapshot_artifact_refuses(self, tmp_path):
        """The counterfactual-style mismatch limb (§7.3(1)): a snapshot.json
        that no longer matches the manifest's recorded snapshot_hash REFUSES."""
        cache, live, manifests, policy, _ = _forged_seed(tmp_path)
        snap_path = cache / "snapshot.json"
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        snapshot["budget_version"] = "budget-v2-forged"
        snap_path.write_text(json.dumps(snapshot, sort_keys=True, indent=1) + "\n",
                             encoding="utf-8")
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "serve_refused"
        assert out.reason == "snapshot_hash_mismatch"

    def test_mutant_skip_when_absent_bites(self, tmp_path):
        """THE §12 sim-11 negative control MUST FAIL: the objectives
        skip-when-absent limb shape (`is not None and`, query.py:214-215)
        serves a manifest whose rows-hash key was removed."""
        with pytest.raises(AssertionError):
            _check_sim11_absent_key(mutant_skip_when_absent, tmp_path)

    def test_shipped_cog3_store_tamper_refuses_end_to_end(self, tmp_path):
        """The serve-REFUSE PRECEDENT, live on shipped code (T2 brief): build a
        REAL objectives fixture graph via the cog3-rebuild.py CLI in a tmp
        root, verify an allowlisted reader CLI serves it (control), then FORGE
        a row and observe the reader REFUSE loudly (exit 2) and write NOTHING —
        the store-integrity idiom this corpus pins for the schedule store.
        (Both CLIs are driven as subprocesses — this file imports no fenced
        module.)"""
        cache = tmp_path / "cache" / "graph-store"
        roots = tmp_path / "directions.yml"
        roots.write_text(
            "# fixture Captain-direction roots (COG-4 T2 tamper precedent)\n"
            "directions:\n"
            "  - slug: fixture-direction\n"
            "    statement: \"keep the fixture cabinet healthy\"\n",
            encoding="utf-8")
        env = dict(os.environ)
        build = subprocess.run(
            [sys.executable, str(_COG3_REBUILD), "--roots", str(roots),
             "--cache", str(cache), "--cutoff", CUTOFF],
            capture_output=True, text=True, env=env)
        assert build.returncode == 0, build.stderr
        control_out = tmp_path / "inbox-control.md"
        control = subprocess.run(
            [sys.executable, str(_COG3_INBOX), "--cache", str(cache),
             "--now", NOW, "--out", str(control_out)],
            capture_output=True, text=True, env=env)
        assert control.returncode == 0, control.stderr
        assert control_out.exists()
        # forge: append a row the manifest never hashed.
        with (cache / "graph.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"node_id": "forged-node-1",
                                 "subject_key": "objective:forged",
                                 "kind": "objective",
                                 "statement": "forged row injected"}) + "\n")
        forged_out = tmp_path / "inbox-forged.md"
        forged = subprocess.run(
            [sys.executable, str(_COG3_INBOX), "--cache", str(cache),
             "--now", NOW, "--out", str(forged_out)],
            capture_output=True, text=True, env=env)
        assert forged.returncode == 2, (forged.returncode, forged.stderr)
        assert "rows-hash mismatch" in forged.stderr
        assert not forged_out.exists(), "a refused serve must write NOTHING"


# ===========================================================================
# SIM 12 — budget overflow at dispatch (§12 row 12, N4)
# ===========================================================================

def _check_sim12(dispatch_fn, tmp_path):
    """Cumulative would-dispatch cost exceeding the REMAINING budget at
    dispatch time REFUSES the overflowing row — even though planning admitted
    it (every row carries planner_admitted=True)."""
    rows = [make_row("organ-a", "collect", budget_units=3),
            make_row("organ-b", "report", budget_units=3),
            make_row("organ-c", "sweep", budget_units=5)]
    manifests = {r["organ"]: make_organ_manifest(r["organ"]) for r in rows}
    cache, live, manifests, policy, _ = _seed(
        tmp_path, rows, manifests, live_overrides={"remaining_budget": 7})
    out = dispatch_fn(cache, live, manifests, policy)
    assert [r["organ"] for r in out.would_dispatch()] == ["organ-a", "organ-b"]
    rec = _by_organ(out, "organ-c")
    assert rec["decision"] == "refused", rec
    assert rec["reason"] == "budget_overflow"
    assert rec["limb"] == "budget"
    assert rec["planner_admitted"] is True    # planning admitted it — refused anyway


class TestSim12BudgetOverflow:
    def test_overflow_refused_at_dispatch_despite_planner_admission(self, tmp_path):
        _check_sim12(reference_dispatch, tmp_path)

    def test_mutant_planner_said_yes_bites(self, tmp_path):
        """The §12 sim-12 negative control MUST FAIL: the mutant trusts the
        planner's admission and skips the live remaining-budget recheck."""
        with pytest.raises(AssertionError):
            _check_sim12(mutant_planner_said_yes, tmp_path)


# ===========================================================================
# SIM 14 — stale-snapshot dispatch (§12 row 14, N3)
# ===========================================================================

def _check_sim14_null_hole(dispatch_fn, tmp_path):
    """Recorded-null-but-live-exists MUST refuse (the built-without-store
    analog): a null in the snapshot can never skip the compare."""
    rows = [make_row("organ-a", "collect")]
    manifests = {"organ-a": make_organ_manifest("organ-a")}
    snapshot = make_snapshot(
        wake_input_hashes={"cortex_belief_store_hash": None})
    cache, live, manifests, policy, _ = _seed(
        tmp_path, rows, manifests, snapshot=snapshot)
    live["wake_input_hashes"]["cortex_belief_store_hash"] = "cortexhash-live-now"
    out = dispatch_fn(cache, live, manifests, policy)
    assert out.mode == "stale_snapshot", (out.mode, out.reason)
    assert out.reason == "stale_snapshot:cortex_belief_store_hash"
    assert out.would_dispatch() == []


class TestSim14StaleSnapshot:
    @pytest.mark.parametrize("family", list(_WAKE_INPUT_KEYS))
    def test_any_live_hash_mismatch_refuses(self, tmp_path, family):
        """Live cortex/objectives/organ-registry/services/health/failure/
        capability hash ≠ recorded ⇒ REFUSE, zero permission."""
        rows = [make_row("organ-a", "collect")]
        manifests = {"organ-a": make_organ_manifest("organ-a")}
        cache, live, manifests, policy, _ = _seed(tmp_path, rows, manifests)
        live["wake_input_hashes"][family] = "moved-" + str(
            live["wake_input_hashes"][family])
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "stale_snapshot"
        assert out.reason == f"stale_snapshot:{family}"
        assert out.would_dispatch() == []

    def test_recorded_null_but_live_exists_refuses(self, tmp_path):
        _check_sim14_null_hole(reference_dispatch, tmp_path)

    def test_live_null_but_recorded_exists_refuses(self, tmp_path):
        """The symmetric hole: a store that VANISHED since the snapshot (live
        None, recorded value) is a mismatch too."""
        rows = [make_row("organ-a", "collect")]
        manifests = {"organ-a": make_organ_manifest("organ-a")}
        cache, live, manifests, policy, _ = _seed(tmp_path, rows, manifests)
        live["wake_input_hashes"]["organ_registry_hash"] = None
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "stale_snapshot"
        assert out.reason == "stale_snapshot:organ_registry_hash"

    def test_matching_hashes_dispatch(self, tmp_path):
        """Control: with every recorded hash matching live, the row
        dispatches — the refusals above are attributable to the mismatch."""
        rows = [make_row("organ-a", "collect")]
        manifests = {"organ-a": make_organ_manifest("organ-a")}
        cache, live, manifests, policy, _ = _seed(tmp_path, rows, manifests)
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "dispatch"
        assert [r["organ"] for r in out.would_dispatch()] == ["organ-a"]

    def test_mutant_null_hole_comparator_bites(self, tmp_path):
        """The §12 sim-14 negative control MUST FAIL: the `is not None and`
        comparator skips the recorded-null compare and serves a mixed-epoch
        dispatch."""
        with pytest.raises(AssertionError):
            _check_sim14_null_hole(mutant_null_hole_comparator, tmp_path)


# ===========================================================================
# SIM 15 — scheduler restart/replay (§12 row 15, §7.4)
# ===========================================================================

def _corrupt_seeds(tmp_path):
    """The corrupt/missing-state seed family: (name, cache_dir) pairs."""
    manifests = {"organ-a": make_organ_manifest("organ-a")}
    rows = [make_row("organ-a", "collect")]
    snapshot = make_snapshot()
    seeds = []
    # (a) missing store entirely.
    missing = tmp_path / "missing-store"
    missing.mkdir()
    seeds.append(("missing_store", missing))
    # (b) corrupt manifest json.
    corrupt_man = tmp_path / "corrupt-manifest"
    build_schedule_fixture(snapshot, rows, corrupt_man)
    (corrupt_man / "schedule-manifest.json").write_text("NOT-JSON{{{",
                                                       encoding="utf-8")
    seeds.append(("corrupt_manifest", corrupt_man))
    # (c) corrupt rows jsonl (torn line).
    corrupt_rows = tmp_path / "corrupt-rows"
    build_schedule_fixture(snapshot, rows, corrupt_rows)
    (corrupt_rows / "schedule.jsonl").write_text('{"organ": "organ-a", "trunc',
                                                encoding="utf-8")
    seeds.append(("corrupt_rows", corrupt_rows))
    # (d) corrupt snapshot artifact.
    corrupt_snap = tmp_path / "corrupt-snapshot"
    build_schedule_fixture(snapshot, rows, corrupt_snap)
    (corrupt_snap / "snapshot.json").write_text("], garbage", encoding="utf-8")
    seeds.append(("corrupt_snapshot", corrupt_snap))
    # (e) mid-fold kill, no prior store (tmp only).
    killed = tmp_path / "killed-mid-fold"
    crashed_build(snapshot, rows, killed)
    seeds.append(("mid_fold_kill", killed))
    live = make_live(snapshot, manifests)
    return seeds, live, manifests


def _check_sim15(dispatch_fn, tmp_path):
    """Corrupt/missing snapshot & schedule ⇒ the FIXED SAFE SCHEDULE (the
    services manifest's own cadence) and NEVER permission: zero would-dispatch
    records, in every corrupt-state seed."""
    seeds, live, manifests = _corrupt_seeds(tmp_path)
    policy = make_policy()
    for name, cache in seeds:
        out = dispatch_fn(cache, live, manifests, policy)
        assert out.mode == "safe_fallback", (name, out.mode, out.reason)
        assert out.safe_schedule == live["services_cadence"], name
        assert out.would_dispatch() == [], (
            f"{name}: fallback granted permission — §7.4 forbids exactly this")


class TestSim15RestartReplay:
    def test_corrupt_or_missing_state_falls_back_never_permission(self, tmp_path):
        _check_sim15(reference_dispatch, tmp_path)

    def test_corruption_beats_row_level_state(self, tmp_path):
        """A corrupt store cannot be 'partially served': even with live state
        that would refuse anyway (hash mismatch), the outcome is the safe
        fallback — what cannot be parsed cannot be verified (§7.4)."""
        seeds, live, manifests = _corrupt_seeds(tmp_path)
        live["wake_input_hashes"]["organ_registry_hash"] = "moved-registry"
        policy = make_policy()
        _name, cache = seeds[2]                       # corrupt_rows
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "safe_fallback"

    def test_mutant_fallback_implies_permission_bites(self, tmp_path):
        """The §12 sim-15 negative control MUST FAIL: the mutant turns the safe
        fallback into would-dispatch grants for the fixed schedule."""
        with pytest.raises(AssertionError):
            _check_sim15(mutant_fallback_implies_permission, tmp_path)


# ===========================================================================
# §7.3 six-limb recheck ORDER battery (serve → staleness → authority →
# budget → freshness → idempotency)
# ===========================================================================

def _order_seed(tmp_path, row, *, live_overrides=None, shadow_replay=False):
    manifests = {row["organ"]: make_organ_manifest(row["organ"])}
    cache, live, manifests, policy, _ = _seed(
        tmp_path, [row], manifests, live_overrides=live_overrides)
    if shadow_replay:
        key = derive_idempotency_key(row, manifests[row["organ"]], live)
        live["shadow_log"].append({"idempotency_key": key})
    return cache, live, manifests, policy


def _check_order_authority_before_budget(dispatch_fn, tmp_path):
    """A row violating authority AND budget refuses at AUTHORITY (limb 3 < 4)."""
    row = make_row("both-organ", "mutate", risk="fixture_gated", budget_units=999)
    cache, live, manifests, policy = _order_seed(
        tmp_path, row, live_overrides={"remaining_budget": 1})
    out = dispatch_fn(cache, live, manifests, policy)
    rec = _by_organ(out, "both-organ")
    assert rec["limb"] == "authority", rec
    assert rec["reason"] == "authority:always_gated"


class TestSevenPointThreeLimbOrder:
    def test_serve_beats_stale_snapshot(self, tmp_path):
        """Forged rows + a moved live hash ⇒ the SERVE refusal wins (limb 1 <
        limb 2): integrity of the decision store is checked before epoch
        freshness."""
        cache, live, manifests, policy, _ = _forged_seed(tmp_path)
        (cache / "schedule.jsonl").write_text(
            _canon(make_row("forged-organ", "exfiltrate")).decode("utf-8") + "\n",
            encoding="utf-8")
        live["wake_input_hashes"]["organ_registry_hash"] = "moved-registry"
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "serve_refused"
        assert out.reason == "rows_hash_mismatch"

    def test_stale_snapshot_beats_row_limbs(self, tmp_path):
        """A stale snapshot refuses the WHOLE dispatch before any per-row limb
        (limb 2 < 3..6): even an authority-gated row never reaches limb 3."""
        row = make_row("gated-organ", "mutate", risk="fixture_gated")
        cache, live, manifests, policy = _order_seed(tmp_path, row)
        live["wake_input_hashes"]["services_manifest_hash"] = "moved-services"
        out = reference_dispatch(cache, live, manifests, policy)
        assert out.mode == "stale_snapshot"
        assert out.records == []

    def test_authority_before_budget(self, tmp_path):
        _check_order_authority_before_budget(reference_dispatch, tmp_path)

    def test_budget_before_freshness(self, tmp_path):
        row = make_row("bf-organ", "collect", budget_units=999)
        cache, live, manifests, policy = _order_seed(
            tmp_path, row,
            live_overrides={"remaining_budget": 1,
                            "organ_output_age_seconds": {"bf-organ": 99999}})
        out = reference_dispatch(cache, live, manifests, policy)
        rec = _by_organ(out, "bf-organ")
        assert rec["limb"] == "budget", rec

    def test_freshness_before_idempotency(self, tmp_path):
        row = make_row("fi-organ", "collect")
        cache, live, manifests, policy = _order_seed(
            tmp_path, row, shadow_replay=True,
            live_overrides={"organ_output_age_seconds": {"fi-organ": 99999}})
        out = reference_dispatch(cache, live, manifests, policy)
        rec = _by_organ(out, "fi-organ")
        assert rec["limb"] == "freshness", rec

    def test_authority_before_idempotency(self, tmp_path):
        row = make_row("ai-organ", "mutate", risk="fixture_gated")
        cache, live, manifests, policy = _order_seed(
            tmp_path, row, shadow_replay=True)
        out = reference_dispatch(cache, live, manifests, policy)
        rec = _by_organ(out, "ai-organ")
        assert rec["limb"] == "authority", rec

    def test_idempotency_replay_refused_and_rederived(self, tmp_path):
        """Limb 6 (SF1): a key already present in the shadow decision record
        refuses; the key is RE-DERIVED per the manifest discipline — a row
        carrying a forged 'fresh' key is refused anyway; a new wake derives a
        new key and dispatches; an in-run duplicate row replays too."""
        row = make_row("idem-organ", "collect",
                       idempotency_key="planner-claimed-fresh-key")
        cache, live, manifests, policy = _order_seed(
            tmp_path, row, shadow_replay=True)
        out = reference_dispatch(cache, live, manifests, policy)
        rec = _by_organ(out, "idem-organ")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "idempotency_replay"
        # a NEW wake id derives a new key ⇒ dispatches.
        live2 = dict(live, wake_id="wake-0002")
        out2 = reference_dispatch(cache, live2, manifests, policy)
        assert [r["organ"] for r in out2.would_dispatch()] == ["idem-organ"]
        # in-run duplicate: the same (organ, operation, wake) twice in one
        # schedule ⇒ the second is an idempotency replay.
        dup_rows = [make_row("idem-organ", "collect"),
                    make_row("idem-organ", "collect")]
        cache2 = tmp_path / "dup" / "cache"
        build_schedule_fixture(make_snapshot(), dup_rows, cache2)
        live3 = make_live(make_snapshot(), manifests)
        out3 = reference_dispatch(cache2, live3, manifests, policy)
        decisions = sorted(r["decision"] for r in out3.records)
        assert decisions == ["refused", "would_dispatch"]
        refused = [r for r in out3.records if r["decision"] == "refused"][0]
        assert refused["reason"] == "idempotency_replay"

    def test_mutant_order_swapped_bites(self, tmp_path):
        """The order negative control MUST FAIL: a dispatcher checking budget
        before authority records the wrong refusal for the dual-violation row."""
        with pytest.raises(AssertionError):
            _check_order_authority_before_budget(mutant_order_swapped, tmp_path)

    def test_mutant_trusts_row_key_bites(self, tmp_path):
        """The limb-6 negative control MUST FAIL: trusting the row's carried
        key lets a replayed decision re-dispatch under a forged 'fresh' key."""
        row = make_row("idem-organ", "collect",
                       idempotency_key="planner-claimed-fresh-key")
        cache, live, manifests, policy = _order_seed(
            tmp_path, row, shadow_replay=True)
        with pytest.raises(AssertionError):
            out = mutant_trusts_row_key(cache, live, manifests, policy)
            rec = _by_organ(out, "idem-organ")
            assert rec["decision"] == "refused"


# ===========================================================================
# REAL-CLI ARMS — LIVE on the landed dispatcher (W5 landing 2026-07-24)
# ===========================================================================

def _real_seed(tmp_path, rows, manifests, *, snapshot=None,
               live_overrides=None):
    """The `_seed` shape onto the REAL kernel store (the retired arms' seam):
    the SAME scenario content, built via the adapter's raw kernel-shaped
    writer; the corpus fixture policy rides the adapter's
    matrix_policy-shaped translation (wildcard verdict rows; undo_required ==
    act_with_undo over a declared "none" undo_contract)."""
    snapshot = snapshot or A.make_snapshot()
    cache_dir = tmp_path / "cache" / "scheduler-real"
    A.build_real_store(cache_dir, snapshot, rows)
    live = A.make_live(snapshot, manifests, **(live_overrides or {}))
    return cache_dir, live, manifests, A.fixture_policy()


def _real_run(tmp_path, cache_dir, live, manifests, policy, **kw):
    return A.run_cli(cache_dir, live, manifests, policy,
                     tmp_path / "real-adapter", **kw)


class TestRealDispatchCliArms:
    # RETIRED vacuity skips, all 10 arms (integrator corpus surgery per §13 +
    # the unit contradictions[] routes, W5 landing 2026-07-24): the guards'
    # RETIREMENT CONDITION — "retire the skip when
    # cabinet/scripts/cog4-dispatch-shadow.py lands — bind the named _check_*
    # property to the real CLI (subprocess adapter over its shadow-record
    # output), so the same seeds/asserts/mutant-escapes run against the landed
    # dispatcher" — was discharged by W5 x1 (7272db13, the §7.3 dispatch-shadow
    # CLI). The companion absence assertions (`_absent_then_skip`, deleted with
    # the guards) tripped RED as designed; each arm body is now the documented
    # activation: the SAME scenario seeds and the SAME asserts the reference
    # tier above pins (sims 3/5/6/9/10/11/12/14/15 + the §7.3 order battery),
    # re-seeded onto REAL kernel-shaped stores via `lib_cog4_dispatch_adapter`
    # and run against the landed CLI. The mutant-escape negative controls stay
    # where they always ran — against the reference variants above (a mutant is
    # a reference divergence; the CLI is pinned by the positive properties).
    # Pre-proven green out-of-band by test_cog4_dispatch_cli.py (W5 x1) before
    # this surgery.

    def test_real_cli_sim3_stale_organ(self, tmp_path):
        """LIVE (retired W5 landing): _check_sim3's seeds + asserts against
        the real CLI (§12 row 3) — stale organ ⇒ refusal WITH the staleness
        flag, NEVER would-dispatch; the fresh organ is unaffected."""
        rows = [A.make_row("stale-organ", "collect"),
                A.make_row("fresh-organ", "collect")]
        manifests = {
            "stale-organ": A.make_organ_manifest("stale-organ",
                                                 max_staleness=3600),
            "fresh-organ": A.make_organ_manifest("fresh-organ",
                                                 max_staleness=3600)}
        cache, live, manifests, policy = _real_seed(
            tmp_path, rows, manifests,
            live_overrides={"organ_output_age_seconds":
                            {"stale-organ": 7200, "fresh-organ": 60}})
        out = _real_run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "dispatch"
        stale = _by_organ(out, "stale-organ")
        assert stale["decision"] == "refused", stale
        assert stale["staleness_flagged"] is True
        assert stale["reason"].startswith("stale_organ:")
        assert [r["organ"] for r in out.would_dispatch()] == ["fresh-organ"]

    def test_real_cli_sim5_organ_crash(self, tmp_path):
        """LIVE (retired W5 landing): the sim-5 fallback/floor/exit-1
        properties (§12 row 5) against the real CLI + the real
        manifest-derived floors."""
        rows = [A.make_row("crash-skip", "collect"),
                A.make_row("crash-noop", "collect"),
                A.make_row("crash-esc", "collect"),
                A.make_row("healthy-organ", "collect")]
        manifests = {
            "crash-skip": A.make_organ_manifest("crash-skip",
                                                fallback="skip"),
            "crash-noop": A.make_organ_manifest("crash-noop",
                                                fallback="safe_noop"),
            "crash-esc": A.make_organ_manifest("crash-esc",
                                               fallback="escalate"),
            "healthy-organ": A.make_organ_manifest("healthy-organ")}
        health = {
            "crash-skip": {"probe_ran": False},                 # true crash
            "crash-noop": {"probe_ran": True, "exit_code": 1},  # honest fail
            "crash-esc": {"probe_ran": False},                  # true crash
            "healthy-organ": {"probe_ran": True, "exit_code": 0}}
        cache, live, manifests, policy = _real_seed(
            tmp_path, rows, manifests,
            live_overrides={"organ_health": health})
        out = _real_run(tmp_path, cache, live, manifests, policy)
        assert _by_organ(out, "crash-skip")["decision"] == "refused"
        assert _by_organ(out, "crash-skip")["reason"] == \
            "health_crashed:fallback_skip"
        assert _by_organ(out, "crash-noop")["decision"] == "safe_noop"
        assert _by_organ(out, "crash-esc")["decision"] == "escalation_flagged"
        assert [r["organ"] for r in out.would_dispatch()] == ["healthy-organ"]
        # the S0 exit-1 finding: RAN-and-exited-1 is `unhealthy` (positive
        # evidence), never `crashed` (absence) — distinct in the record.
        assert _by_organ(out, "crash-noop")["health"] == "unhealthy"
        assert _by_organ(out, "crash-noop")["reason"] == \
            "health_unhealthy:fallback_safe_noop"
        assert _by_organ(out, "crash-skip")["health"] == "crashed"
        # floors stay manifest-derived and health-INDEPENDENT (§12 row 5).
        floors = {name: (m["freshness_needs"]["expected_output"],
                         m["freshness_needs"]["max_staleness_seconds"])
                  for name, m in manifests.items()}
        assert set(floors) == {"crash-skip", "crash-noop", "crash-esc",
                               "healthy-organ"}

    def test_real_cli_sim6_dependency_failure(self, tmp_path):
        """LIVE (retired W5 landing): _check_sim6's seeds + asserts against
        the real CLI (§12 row 6) — unavailable organ/capability dependencies
        refuse with the explicit dependency in the reason; independent work
        dispatches."""
        rows = [A.make_row("dependent-organ", "aggregate",
                           deps=("organ:upstream-organ",)),
                A.make_row("cap-dependent", "fetch"),
                A.make_row("independent", "collect")]
        manifests = {
            "dependent-organ": A.make_organ_manifest("dependent-organ"),
            "cap-dependent": A.make_organ_manifest(
                "cap-dependent", dependencies=("mcp:alpha-service",)),
            "independent": A.make_organ_manifest("independent")}
        cache, live, manifests, policy = _real_seed(
            tmp_path, rows, manifests,
            live_overrides={"organs_available":
                            ["dependent-organ", "cap-dependent",
                             "independent"],            # upstream ABSENT
                            "capabilities_available": []})
        out = _real_run(tmp_path, cache, live, manifests, policy)
        organ_dep = _by_organ(out, "dependent-organ")
        assert organ_dep["decision"] == "refused", organ_dep
        assert organ_dep["reason"] == \
            "dependency_unavailable:organ:upstream-organ"
        cap_dep = _by_organ(out, "cap-dependent")
        assert cap_dep["decision"] == "refused", cap_dep
        assert cap_dep["reason"] == "dependency_unavailable:mcp:alpha-service"
        assert [r["organ"] for r in out.would_dispatch()] == ["independent"]

    def test_real_cli_sim9_unavailable_mcp(self, tmp_path):
        """LIVE (retired W5 landing): _check_sim9's seeds + asserts against
        the real CLI (§12 row 9) — absent MCP ⇒ refusal naming the
        capability; the record preserves the ORIGINAL capability + descriptor
        (the anti-silent-substitution clause)."""
        rows = [A.make_row("mcp-organ", "sync"),
                A.make_row("plain-organ", "collect")]
        manifests = {
            "mcp-organ": A.make_organ_manifest(
                "mcp-organ", permissions=("mcp:vault-read",)),
            "plain-organ": A.make_organ_manifest("plain-organ")}
        cache, live, manifests, policy = _real_seed(
            tmp_path, rows, manifests,
            live_overrides={"capabilities_available":
                            ["mcp:other-available"]})
        out = _real_run(tmp_path, cache, live, manifests, policy)
        rec = _by_organ(out, "mcp-organ")
        assert rec["decision"] == "refused", rec
        assert rec["reason"] == "capability_unavailable:mcp:vault-read"
        assert rec["capability"] == "mcp-organ/sync"
        assert rec["descriptor"]["capability"] == "mcp-organ/sync"
        assert [r["organ"] for r in out.would_dispatch()] == ["plain-organ"]

    def test_real_cli_sim10_unauthorized_effect(self, tmp_path):
        """LIVE (retired W5 landing): _check_sim10's seeds + asserts against
        the real CLI (§12 row 10/N5) — the verdicts now come from the REAL
        read-only authority joint (§7.3(3)) over the translated policy:
        gated/propose/ceiling/undo-gap NEVER would-dispatch; the clean row
        does."""
        rows = [
            A.make_row("gated-organ", "mutate", risk="fixture_gated"),
            A.make_row("propose-organ", "draft", risk="fixture_propose"),
            A.make_row("ceiling-organ", "spend", ceiling=("spending",)),
            A.make_row("undo-gap-organ", "rewrite", risk="fixture_mutating",
                       undo="none"),
            A.make_row("clean-organ", "collect")]
        manifests = {r["organ"]: A.make_organ_manifest(r["organ"])
                     for r in rows}
        cache, live, manifests, policy = _real_seed(tmp_path, rows, manifests)
        out = _real_run(tmp_path, cache, live, manifests, policy)
        expected = {
            "gated-organ": "always_gated",
            "propose-organ": "propose_only",
            "ceiling-organ": "ceiling",
            "undo-gap-organ": "undo_gap",
        }
        for organ, verdict in expected.items():
            rec = _by_organ(out, organ)
            assert rec["decision"] == "refused", (organ, rec)
            assert rec["verdict"] == verdict
            assert rec["reason"] == f"authority:{verdict}"
        assert [r["organ"] for r in out.would_dispatch()] == ["clean-organ"]

    def test_real_cli_sim11_forged_decision(self, tmp_path):
        """LIVE (retired W5 landing): the sim-11 tamper + absent-key seeds
        (§12 row 11/§6.3) against the real CLI over the KERNEL schedule
        store — the real chain bites on hand-edited row CONTENT; the absent
        rows-hash key can never serve unbound rows (MANDATORY-PRESENT)."""
        def fresh(tag):
            rows = [A.make_row("organ-a", "collect"),
                    A.make_row("organ-b", "report")]
            manifests = {"organ-a": A.make_organ_manifest("organ-a"),
                         "organ-b": A.make_organ_manifest("organ-b")}
            root = tmp_path / tag
            cache = root / "cache"
            A.build_real_store(cache, A.make_snapshot(), rows)
            live = A.make_live(A.make_snapshot(), manifests)
            return root, cache, live, manifests
        policy = A.fixture_policy()
        # (a) hand-edited row content ⇒ SERVE refusal, nothing served.
        root, cache, live, manifests = fresh("tamper")
        rows_path = cache / "schedule.jsonl"
        lines = rows_path.read_text(encoding="utf-8").splitlines()
        assert '"budget_units":1' in lines[0]
        lines[0] = lines[0].replace('"budget_units":1', '"budget_units":0')
        rows_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out = A.run_cli(cache, live, manifests, policy, root / "w")
        assert out.mode == "serve_refused", (out.mode, out.reason)
        assert out.reason == "rows_hash_mismatch"
        assert out.records == [] and out.would_dispatch() == []
        # (b) §6.3 MANDATORY-PRESENT: the rows-hash key removed ⇒ refusal.
        root, cache, live, manifests = fresh("absent-key")
        man_path = cache / "schedule-manifest.json"
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        del manifest["schedule_rows_hash"]
        man_path.write_text(json.dumps(manifest, sort_keys=True),
                            encoding="utf-8")
        out = A.run_cli(cache, live, manifests, policy, root / "w")
        assert out.mode == "serve_refused", (out.mode, out.reason)
        assert out.reason == "rows_hash_key_absent"
        assert out.records == [] and out.would_dispatch() == []
        # (c) a snapshot record that no longer matches epoch.snapshot_hash.
        root, cache, live, manifests = fresh("snap-tamper")
        snap_path = cache / "snapshot.json"
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        snapshot["scope"] = "forged-scope"
        snap_path.write_text(json.dumps(snapshot, sort_keys=True),
                             encoding="utf-8")
        out = A.run_cli(cache, live, manifests, policy, root / "w")
        assert out.mode == "serve_refused"
        assert out.reason == "snapshot_hash_mismatch"

    def test_real_cli_sim12_budget_overflow(self, tmp_path):
        """LIVE (retired W5 landing): _check_sim12's seeds + asserts against
        the real CLI (§12 row 12/N4) — cumulative would-dispatch cost beyond
        the remaining budget refuses the overflowing row even though planning
        admitted it; refused rows consume no budget."""
        rows = [A.make_row("organ-a", "collect", budget_units=3),
                A.make_row("organ-b", "report", budget_units=3),
                A.make_row("organ-c", "sweep", budget_units=5)]
        manifests = {r["organ"]: A.make_organ_manifest(r["organ"])
                     for r in rows}
        cache, live, manifests, policy = _real_seed(
            tmp_path, rows, manifests,
            live_overrides={"remaining_budget": 7})
        out = _real_run(tmp_path, cache, live, manifests, policy)
        assert [r["organ"] for r in out.would_dispatch()] == \
            ["organ-a", "organ-b"]
        rec = _by_organ(out, "organ-c")
        assert rec["decision"] == "refused", rec
        assert rec["reason"] == "budget_overflow"
        assert rec["limb"] == "budget"
        assert rec["planner_admitted"] is True   # admitted — refused anyway

    def test_real_cli_sim14_stale_snapshot(self, tmp_path):
        """LIVE (retired W5 landing): the sim-14 mismatch + null-hole seeds
        (§12 row 14/N3) against the real CLI — every moved wake-input family
        refuses; a recorded null NEVER skips the compare (the objectives
        `is not None and` hole stays closed); the symmetric live-null
        refuses too."""
        rows = [A.make_row("organ-a", "collect")]
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        # (a) every wake-input family: moved live hash ⇒ stale_snapshot.
        for family in A.WAKE_INPUT_KEYS:
            root = tmp_path / f"mm-{family}"
            cache = root / "cache"
            A.build_real_store(cache, A.make_snapshot(), rows)
            live = A.make_live(A.make_snapshot(), manifests)
            live["wake_input_hashes"][family] = "moved-" + str(
                live["wake_input_hashes"][family])
            out = A.run_cli(cache, live, manifests, A.fixture_policy(),
                            root / "w")
            assert out.mode == "stale_snapshot", (family, out.mode)
            assert out.reason == f"stale_snapshot:{family}"
            assert out.would_dispatch() == []
        # (b) recorded-null-but-live-exists refuses (the null hole).
        snapshot = A.make_snapshot(
            wake_input_hashes={"cortex_belief_store_hash": None})
        cache, live, manifests, policy = _real_seed(
            tmp_path, rows, manifests, snapshot=snapshot)
        live["wake_input_hashes"]["cortex_belief_store_hash"] = \
            "cortexhash-live-now"
        out = _real_run(tmp_path, cache, live, manifests, policy)
        assert out.mode == "stale_snapshot", (out.mode, out.reason)
        assert out.reason == "stale_snapshot:cortex_belief_store_hash"
        assert out.would_dispatch() == []
        # (c) the symmetric hole: live None against a recorded value.
        root = tmp_path / "live-null"
        cache = root / "cache"
        A.build_real_store(cache, A.make_snapshot(), rows)
        live = A.make_live(A.make_snapshot(), manifests)
        live["wake_input_hashes"]["organ_registry_hash"] = None
        out = A.run_cli(cache, live, manifests, A.fixture_policy(),
                        root / "w")
        assert out.mode == "stale_snapshot"
        assert out.reason == "stale_snapshot:organ_registry_hash"

    def test_real_cli_sim15_restart_replay(self, tmp_path):
        """LIVE (retired W5 landing): _check_sim15's corrupt/missing-state
        seeds (§12 row 15/§7.4) against the real CLI — the FIXED safe
        schedule, NEVER permission — plus the kernel N1 PYTHONHASHSEED triple
        on the rebuilt schedule (the real fold reproduces byte-identical
        artifacts; the CLI dispatches identically over each rebuild)."""
        manifests = {"organ-a": A.make_organ_manifest("organ-a")}
        rows = [A.make_row("organ-a", "collect")]
        snapshot = A.make_snapshot()
        seeds = []
        missing = tmp_path / "missing-store"
        missing.mkdir()
        seeds.append(("missing_store", missing))
        corrupt_man = tmp_path / "corrupt-manifest"
        A.build_real_store(corrupt_man, snapshot, rows)
        (corrupt_man / "schedule-manifest.json").write_text(
            "NOT-JSON{{{", encoding="utf-8")
        seeds.append(("corrupt_manifest", corrupt_man))
        corrupt_rows = tmp_path / "corrupt-rows"
        A.build_real_store(corrupt_rows, snapshot, rows)
        (corrupt_rows / "schedule.jsonl").write_text(
            '{"organ": "organ-a", "trunc', encoding="utf-8")
        seeds.append(("corrupt_rows", corrupt_rows))
        corrupt_snap = tmp_path / "corrupt-snapshot"
        A.build_real_store(corrupt_snap, snapshot, rows)
        (corrupt_snap / "snapshot.json").write_text("], garbage",
                                                    encoding="utf-8")
        seeds.append(("corrupt_snapshot", corrupt_snap))
        killed = tmp_path / "killed-mid-fold"
        A.crashed_build(snapshot, rows, killed)
        seeds.append(("mid_fold_kill", killed))
        live = A.make_live(snapshot, manifests)
        policy = A.fixture_policy()
        for name, cache in seeds:
            out = A.run_cli(cache, live, manifests, policy,
                            tmp_path / f"w-{name}")
            assert out.mode == "safe_fallback", (name, out.mode, out.reason)
            assert out.safe_schedule == live["services_cadence"], name
            assert out.would_dispatch() == [], (
                f"{name}: fallback granted permission — §7.4 forbids "
                "exactly this")
        # the kernel N1 triple on the REBUILT schedule: three PYTHONHASHSEED
        # values ⇒ ONE rows-hash and identical CLI outcomes per rebuild.
        fixture = _HERE / "fixtures" / "cog4" / "fold" / "burst.json"
        snap = json.loads(fixture.read_text(encoding="utf-8"))
        hashes, outcomes = set(), []
        for seed in ("0", "1", "2"):
            cache = tmp_path / f"n1-cache-{seed}"
            r = subprocess.run(
                [sys.executable, "-c",
                 "import sys\n"
                 f"sys.path.insert(0, {str(_REPO)!r})\n"
                 "from framework.scheduler.fold import build_schedule\n"
                 f"build_schedule({str(fixture)!r}, {str(cache)!r})\n"],
                capture_output=True, text=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed})
            assert r.returncode == 0, r.stderr
            manifest = json.loads(
                (cache / "schedule-manifest.json").read_text("utf-8"))
            hashes.add(manifest["schedule_rows_hash"])
            n1_live = {
                "wake_input_hashes": dict(snap["wake_input_hashes"]),
                "remaining_budget": 100, "wake_id": "wake-n1",
                "organ_output_age_seconds": {},
                "organ_health": {o["organ"]: {"probe_ran": True,
                                              "exit_code": 0}
                                 for o in snap["organs"]},
                "organs_available": [o["organ"] for o in snap["organs"]],
                "capabilities_available":
                    sorted(snap["capability_availability"]),
                "services_cadence": [],
            }
            n1_manifests = {o["organ"]: A.make_organ_manifest(o["organ"])
                            for o in snap["organs"]}
            out = A.run_cli(cache, n1_live, n1_manifests, policy,
                            tmp_path / f"n1-w-{seed}")
            assert out.mode == "dispatch"
            outcomes.append(sorted(
                (r2["organ"], r2["operation"], r2["decision"], r2["reason"])
                for r2 in out.records))
        assert len(hashes) == 1, hashes            # N1 determinism
        assert outcomes[0] == outcomes[1] == outcomes[2]

    def test_real_cli_six_limb_order(self, tmp_path):
        """LIVE (retired W5 landing): the §7.3 order battery bound to the
        real CLI's recorded limbs (serve → staleness → authority → budget →
        freshness → idempotency), incl. limb 6's SF1 re-derive law: a
        row-carried forged 'fresh' key is refused anyway, a new wake derives
        a new key and dispatches, an in-run duplicate replays."""
        def one_row_seed(tag, row, *, live_overrides=None,
                         shadow_replay=False):
            manifests = {row["organ"]: A.make_organ_manifest(row["organ"])}
            root = tmp_path / tag
            cache = root / "cache"
            A.build_real_store(cache, A.make_snapshot(), [row])
            live = A.make_live(A.make_snapshot(), manifests,
                               **(live_overrides or {}))
            keys = ()
            if shadow_replay:
                keys = (A.derive_idempotency_key(
                    row["organ"], row["operation"], live["wake_id"]),)
            return root, cache, live, manifests, keys
        policy = A.fixture_policy()
        # limb 1 < 2: forged rows + a moved live hash ⇒ SERVE refusal wins.
        root, cache, live, manifests, _k = one_row_seed(
            "serve-first", A.make_row("organ-a", "collect"))
        (cache / "schedule.jsonl").write_text(
            json.dumps(A.make_row("forged-organ", "exfiltrate"),
                       sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8")
        live["wake_input_hashes"]["organ_registry_hash"] = "moved-registry"
        out = A.run_cli(cache, live, manifests, policy, root / "w")
        assert out.mode == "serve_refused"
        assert out.reason == "rows_hash_mismatch"
        # limb 2 < 3..6: a stale snapshot refuses BEFORE any per-row limb.
        root, cache, live, manifests, _k = one_row_seed(
            "stale-first", A.make_row("gated-organ", "mutate",
                                      risk="fixture_gated"))
        live["wake_input_hashes"]["services_manifest_hash"] = \
            "moved-services"
        out = A.run_cli(cache, live, manifests, policy, root / "w")
        assert out.mode == "stale_snapshot"
        assert out.records == []
        # limb 3 < 4: authority AND budget violated ⇒ refuses at AUTHORITY.
        root, cache, live, manifests, _k = one_row_seed(
            "auth-budget", A.make_row("both-organ", "mutate",
                                      risk="fixture_gated",
                                      budget_units=999),
            live_overrides={"remaining_budget": 1})
        out = A.run_cli(cache, live, manifests, policy, root / "w")
        rec = _by_organ(out, "both-organ")
        assert rec["limb"] == "authority", rec
        assert rec["reason"] == "authority:always_gated"
        # limb 4 < 5: budget AND freshness violated ⇒ refuses at BUDGET.
        root, cache, live, manifests, _k = one_row_seed(
            "budget-fresh", A.make_row("bf-organ", "collect",
                                       budget_units=999),
            live_overrides={"remaining_budget": 1,
                            "organ_output_age_seconds":
                            {"bf-organ": 99999}})
        out = A.run_cli(cache, live, manifests, policy, root / "w")
        assert _by_organ(out, "bf-organ")["limb"] == "budget"
        # limb 5 < 6: freshness AND idempotency violated ⇒ FRESHNESS.
        root, cache, live, manifests, keys = one_row_seed(
            "fresh-idem", A.make_row("fi-organ", "collect"),
            live_overrides={"organ_output_age_seconds":
                            {"fi-organ": 99999}},
            shadow_replay=True)
        out = A.run_cli(cache, live, manifests, policy, root / "w",
                        shadow_seed_keys=keys)
        assert _by_organ(out, "fi-organ")["limb"] == "freshness"
        # limb 3 < 6: authority AND idempotency violated ⇒ AUTHORITY.
        root, cache, live, manifests, keys = one_row_seed(
            "auth-idem", A.make_row("ai-organ", "mutate",
                                    risk="fixture_gated"),
            shadow_replay=True)
        out = A.run_cli(cache, live, manifests, policy, root / "w",
                        shadow_seed_keys=keys)
        assert _by_organ(out, "ai-organ")["limb"] == "authority"
        # limb 6 (SF1): replay refused; the key is RE-DERIVED per the
        # manifest discipline (the row's forged 'fresh' key is ignored).
        row = A.make_row("idem-organ", "collect",
                         idempotency_key="planner-claimed-fresh-key")
        root, cache, live, manifests, keys = one_row_seed(
            "sf1", row, shadow_replay=True)
        out = A.run_cli(cache, live, manifests, policy, root / "w",
                        shadow_seed_keys=keys)
        rec = _by_organ(out, "idem-organ")
        assert rec["decision"] == "refused"
        assert rec["reason"] == "idempotency_replay"
        assert rec["limb"] == "idempotency"
        # a NEW wake id derives a new key ⇒ dispatches.
        live2 = dict(live, wake_id="wake-0002")
        out2 = A.run_cli(cache, live2, manifests, policy, root / "w2",
                         shadow_seed_keys=keys)
        assert [r["organ"] for r in out2.would_dispatch()] == ["idem-organ"]
        # in-run duplicate: the same (organ, operation) twice in one
        # schedule ⇒ the second is an idempotency replay.
        dup_rows = [A.make_row("idem-organ", "collect"),
                    A.make_row("idem-organ", "collect")]
        dup_cache = root / "dup-cache"
        A.build_real_store(dup_cache, A.make_snapshot(), dup_rows)
        live3 = A.make_live(A.make_snapshot(), manifests)
        out3 = A.run_cli(dup_cache, live3, manifests, policy, root / "w3")
        decisions = sorted(r["decision"] for r in out3.records)
        assert decisions == ["refused", "would_dispatch"]
        refused = [r for r in out3.records if r["decision"] == "refused"][0]
        assert refused["reason"] == "idempotency_replay"
