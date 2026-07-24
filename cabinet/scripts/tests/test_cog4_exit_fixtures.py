"""test_cog4_exit_fixtures.py — W5 x2: THREE heterogeneous NON-SOFTWARE fixture
cabinets, end-to-end through the REAL COG-4 CLIs (contract §12 N8 / MR4).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §12 N8 —
"three genuinely non-software fixture Cabinets declare granular namespaced
operations WITHOUT adding a central action type and resolve to the SAME single
enforcement decision"; MR4 — extend the COG-3 exit-fixture #2 domain
(community garden + delivery, test_cog3_exit_fixtures.py — read, NEVER edited:
the landed corpus is immutable §13; this suite only ADDS) with an
organ/operation layer, plus TWO NEW genuinely non-software cabinets (the §12
candidate domains: physical-logistics/warehouse -> the harbourside goods-shed;
care-rota/community-ops -> the neighbourhood care rota).

THE THREE CABINETS (organ manifests are COMMITTED fixture data under
fixtures/cog4/cabinets/<cabinet>/ — the registry's real load surface):

  A. garden-delivery — the COG-3 fixture-#2 operation EXTENDED: the same
     roots/conflict/consequence seed vocabulary (harvest/logistics,
     maximize-yield vs reduce-waste, the steward's confirmed route replan)
     now carries organs `garden-rota` + `basket-delivery` declaring seven
     namespaced operations.
  B. harbor-warehouse — `quay-inventory` + `freight-round`: eight operations
     over shelves, pallets, cold-store readings, lorry rounds and bays.
  C. care-rota — `visit-rota` + `meal-round`: eight operations over
     neighbour visits, volunteer rounds, larder counts and donor letters.

EACH cabinet runs END-TO-END through the REAL CLIs (subprocess, tmp roots,
hermetic — the COG-3 exit-fixture idiom):
  §4.2 organ manifests (amendment-proposal shape, validated against the W2
  reference validator — the germline gate pair stays byte-untouched, window
  unopened) -> framework.organs.registry (real load + hash) ->
  framework.organs.descriptor.resolve_descriptor (the ONE descriptor per
  operation, manifest-declared values only) -> cog4-snapshot.py (declared
  inputs; real seeded cortex + objectives stores) -> cog4-schedule.py (the
  pure fold) -> cog4-dispatch-shadow.py (the §7.3 six-limb recheck) ->
  would_dispatch|refused shadow decisions. The descriptor dict is asserted
  BYTE-IDENTICAL from resolution through snapshot/fold/serve into the shadow
  record: ALL operations resolve through descriptors to the SAME single
  enforcement decision path — the §7.3 authority joint over
  risk_class/ceiling/undo_contract/verdict, never the operation name.

PER-CABINET LAWS asserted during the run:
  * ZERO central action types added — the three KEPT enum-growth mutants
    (§5.4) hold DURING the fixture run: census `central_action_types`
    maximum 30 == observed len(ACTION_TYPES); the consequence-event schema's
    closed enum == set(ACTION_TYPES) + null; the authority matrix loads with
    its totality validation green (13 risk classes). Every fixture operation
    id is namespaced (`/`) and NOT an ACTION_TYPES member.
  * §5.2 operation-name-authority mutant — the W2 capability-blindness
    harness runs over a same-descriptor operation pair per cabinet: the REAL
    dispatch records are capability-blind (identical descriptors ->
    identical decision+reason) and a capability-keyed mutant predicate is
    CAUGHT (violations non-empty). Cabinet A additionally exercises the W2
    corpus's own garden/water.plots mutant.
  * Trajectory v2 (§5.5) — records minted from the fixture shadow decisions
    (status proposed|denied — shadow mints nothing beyond intent) validate
    against the REAL Draft-2020-12 v2 schema via contracts.structural_issues;
    `domain_operation` carries the granular identity; the never-overload
    mutant (a namespaced id in `action_type`) FAILS validation per cabinet.
  * SF1 idempotency — cabinet A re-runs the dispatcher on the same wake:
    every previously would-dispatched operation refuses `idempotency_replay`;
    a fresh wake_id dispatches again (keys are context-bound, re-derived,
    never trusted from rows).

r14-style TOKEN SWEEP (the test_cog3_exit_fixtures.py §9 r14 idiom): the
committed fixture-cabinet files AND every in-test cabinet seed payload carry
none of the banned technical-domain tokens; the token list is ASSEMBLED FROM
PARTS so this file never itself trips a vocabulary sweep.

W2 corpus bindings (the executable spec — read via the established
test-imports-test idiom, test_cog4_organs_package.py precedent):
test_cog4_organ_manifest (the §4.2 reference validator, N-d matrix
consistency, the §5.2 blindness harness, the v2 effect reference) and
test_cog4_trajectory_v2 (the landed v2 envelope factory);
lib_cog4_dispatch_adapter (the real-CLI dispatch runner); lib_cog3_fixtures
(cortex/consequence seeding). No vacuity guards: every surface this battery
binds is landed on this branch — the suite is live from its first run.

S0: python3.12, file-seeded, no DSN, no network, deterministic (canonical
cutoffs, no clock reads; the dispatcher runs hermetic-joint). SHADOW ABSOLUTE:
nothing here executes anything — the dispatcher emits records only.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W5 x2 (non-software fixture
cabinets, Fable-for-execution named unit).
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as L                                    # noqa: E402
import lib_cog4_dispatch_adapter as ADP                          # noqa: E402
import test_cog4_organ_manifest as t3                            # noqa: E402
import test_cog4_trajectory_v2 as TV2                            # noqa: E402

from framework.authority import matrix as authority_matrix       # noqa: E402
from framework.authority.classifier import ACTION_TYPES          # noqa: E402
from framework.evolution import contracts as C                   # noqa: E402
from framework.organs.descriptor import resolve_descriptor       # noqa: E402
from framework.organs.registry import (                          # noqa: E402
    load_organ_registry, state_ownership_collisions)

_COG3_REBUILD = _REPO / "cabinet" / "scripts" / "cog3-rebuild.py"
_SNAPSHOT_CLI = _REPO / "cabinet" / "scripts" / "cog4-snapshot.py"
_SCHEDULE_CLI = _REPO / "cabinet" / "scripts" / "cog4-schedule.py"
_FIXTURE_ROOT = _HERE / "fixtures" / "cog4" / "cabinets"
_CENSUS_YML = _REPO / "cabinet" / "config" / "cognitive-architecture-contract.yml"
_CONSEQUENCE_SCHEMA = _REPO / "framework" / "schemas" / "consequence-event.schema.json"

CUTOFF = L.CUTOFF
TS = L.EVIDENCE_TS
_ASSUMPTIONS = ["declared-confounder-and-selection"]
_BUDGET_CEILING = 20            # fold ceiling — every fixture op fits (the
_REMAINING_BUDGET = 50          # dispatcher, not the planner, decides here)

WOULD = "would_dispatch"
REFUSED = "refused"
GREEN = "all_limbs_green"

# ===========================================================================
# THE THREE CABINETS — every cabinet-authored seed lives HERE (module level)
# so the token sweep covers it verbatim. Structural pipeline vocabulary
# (schema field names, closed-enum members) is the constitution's, not the
# cabinet's — and carries none of the banned tokens either way.
# ===========================================================================

CABINETS = {
    "garden-delivery": {
        "dir": "garden-delivery",
        "wake_id": "wake-garden-0001",
        # the COG-3 exit-fixture #2 seed vocabulary, EXTENDED (MR4)
        "roots": {
            "directions": {
                "harvest": {"statement": "grow more food each season"},
                "logistics": {"statement": "deliver every basket on time"}},
            "objectives": [
                {"slug": "maximize-yield", "root_ref": "harvest",
                 "conflicts_with": ["reduce-waste"]},
                {"slug": "reduce-waste", "root_ref": "harvest"}],
        },
        "workgraph": {"tasks": [
            {"task_id": 1, "actor": {"kind": "steward", "id": "market"},
             "action": "replan", "subject": "routes", "ts": TS,
             "target": "outcome/delivery-punctuality",
             "dimension": "punctuality", "expected_effect": "increase",
             "assumptions": _ASSUMPTIONS}]},
        "missions": {"missions": [
            {"slug": "delivery-punctuality", "dimension": "punctuality"}]},
        "consequence": {"action": "replan", "subject": "routes",
                        "verdict": "confirmed", "source": "verdict_human",
                        "actor_kind": "steward", "actor_id": "market"},
        "obs": None,
        "services_text": ("# village rounds\n"
                          "garden-rota: every morning\n"
                          "basket-delivery: twice a day\n"),
        "urgency": {
            "garden/water.plots": 3, "garden/mulch.spread": 1,
            "garden/rota.compile": 2, "delivery/route.replan": 4,
            "delivery/crate.relabel": 1, "delivery/household.note": 2,
            "delivery/postcard.mail": 1},
        "expected": {
            "garden/water.plots": (WOULD, GREEN),
            "garden/mulch.spread": (WOULD, GREEN),
            "garden/rota.compile": (WOULD, GREEN),
            "delivery/route.replan": (WOULD, GREEN),
            "delivery/crate.relabel": (REFUSED, "authority:undo_gap"),
            "delivery/household.note": (REFUSED, "authority:propose_only"),
            "delivery/postcard.mail": (REFUSED, "authority:ceiling")},
        "blind_pair": ("garden/water.plots", "garden/mulch.spread"),
    },
    "harbor-warehouse": {
        "dir": "harbor-warehouse",
        "wake_id": "wake-quay-0001",
        "roots": {
            "directions": {
                "stow": {"statement": "every crate leaves the quay dry and on time"},
                "tally": {"statement": "the ledger matches the shelves at dusk"}},
            "objectives": [
                {"slug": "swift-turnaround", "root_ref": "stow"},
                {"slug": "honest-tallies", "root_ref": "tally"}],
        },
        "workgraph": {"tasks": [
            {"task_id": 1, "actor": {"kind": "stevedore", "id": "foreman"},
             "action": "restack", "subject": "bay-three", "ts": TS,
             "target": "outcome/crate-turnaround", "dimension": "turnaround",
             "expected_effect": "increase", "assumptions": _ASSUMPTIONS}]},
        "missions": {"missions": [
            {"slug": "crate-turnaround", "dimension": "turnaround"}]},
        "consequence": None,
        "obs": {"subject": "outcome/crate-turnaround",
                "dimension": "turnaround", "effect": "increase",
                "suffix": "quay"},
        "services_text": ("# quay rounds\n"
                          "quay-inventory: every tide\n"
                          "freight-round: twice a day\n"),
        "urgency": {
            "warehouse/shelf.stocktake": 2, "warehouse/coldstore.reading": 5,
            "warehouse/pallet.rotate": 1, "freight/lorry.manifest": 3,
            "freight/bay.reshuffle": 2, "freight/crate.restack": 1,
            "freight/foreman.note": 2, "freight/harbourmaster.notice": 1},
        "expected": {
            "warehouse/shelf.stocktake": (WOULD, GREEN),
            "warehouse/coldstore.reading": (WOULD, GREEN),
            "warehouse/pallet.rotate": (WOULD, GREEN),
            "freight/lorry.manifest": (WOULD, GREEN),
            "freight/bay.reshuffle": (WOULD, GREEN),
            "freight/crate.restack": (REFUSED, "authority:undo_gap"),
            "freight/foreman.note": (REFUSED, "authority:propose_only"),
            "freight/harbourmaster.notice": (REFUSED, "authority:ceiling")},
        "blind_pair": ("warehouse/shelf.stocktake",
                       "warehouse/coldstore.reading"),
    },
    "care-rota": {
        "dir": "care-rota",
        "wake_id": "wake-care-0001",
        "roots": {
            "directions": {
                "warmth": {"statement": "every neighbour gets a knock and a meal"},
                "fairness": {"statement": "no volunteer carries two rounds alone"}},
            "objectives": [
                {"slug": "every-door-knocked", "root_ref": "warmth"},
                {"slug": "fair-rounds", "root_ref": "fairness"}],
        },
        "workgraph": {"tasks": [
            {"task_id": 1, "actor": {"kind": "warden", "id": "parish"},
             "action": "reshuffle", "subject": "rounds", "ts": TS,
             "target": "outcome/round-coverage", "dimension": "coverage",
             "expected_effect": "increase", "assumptions": _ASSUMPTIONS}]},
        "missions": {"missions": [
            {"slug": "round-coverage", "dimension": "coverage"}]},
        "consequence": None,
        "obs": {"subject": "outcome/round-coverage", "dimension": "coverage",
                "effect": "increase", "suffix": "care"},
        "services_text": ("# parish rounds\n"
                          "visit-rota: every morning\n"
                          "meal-round: midday and dusk\n"),
        "urgency": {
            "care/rota.compile": 2, "care/rota.audit": 1,
            "care/visit.assign": 4, "care/visit.swap": 1,
            "meals/round.plan": 3, "meals/larder.count": 2,
            "meals/kitchen.note": 1, "meals/donor.letter": 1},
        "expected": {
            "care/rota.compile": (WOULD, GREEN),
            "care/rota.audit": (WOULD, GREEN),
            "care/visit.assign": (WOULD, GREEN),
            "care/visit.swap": (REFUSED, "authority:undo_gap"),
            "meals/round.plan": (WOULD, GREEN),
            "meals/larder.count": (WOULD, GREEN),
            "meals/kitchen.note": (REFUSED, "authority:propose_only"),
            "meals/donor.letter": (REFUSED, "authority:ceiling")},
        "blind_pair": ("care/rota.compile", "care/rota.audit"),
    },
}


# ===========================================================================
# harness helpers (the COG-3 exit-fixture idiom + the W5 dispatch adapter)
# ===========================================================================

@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    """Isolated consequence-ledger dir (the D1 idiom, test_cog3_exit_fixtures
    events_dir mirrored) — only cabinet A folds ledger rows."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


def _write_json(path, obj):
    """JSON is valid YAML — the COG-3 fixture idiom: quoted timestamps stay
    strings under the CLI's yaml.safe_load."""
    Path(path).write_text(json.dumps(obj), encoding="utf-8")
    return Path(path)


def _run(argv, what):
    proc = subprocess.run([sys.executable, *argv], capture_output=True,
                          text=True, cwd=str(_REPO))
    assert proc.returncode == 0, (
        f"{what} failed rc={proc.returncode}\nstdout: {proc.stdout}\n"
        f"stderr: {proc.stderr}")
    return proc


def _seed_cortex(cortex_dir, spec, events_dir):
    """Seed the sibling cortex store with the cabinet's vocabulary through the
    REAL fold + persist (never a hand-built view)."""
    protos = []
    if spec["consequence"] is not None:
        assert events_dir is not None, "cabinet with ledger rows needs events_dir"
        c = spec["consequence"]
        L.seed_consequence_ledger(events_dir, [L.consequence_row(
            c["action"], c["subject"], verdict=c["verdict"], source=c["source"],
            actor_kind=c["actor_kind"], actor_id=c["actor_id"], ts=TS)])
        protos += L.consequence_protos()
    if spec["obs"] is not None:
        o = spec["obs"]
        protos.append(L.observation_proto(
            o["subject"], o["dimension"],
            claim=L.observed_effect_claim(o["effect"]),
            seq=0, event_suffix=o["suffix"]))
    beliefs = L.fold_beliefs(protos)
    cortex_dir.mkdir(parents=True, exist_ok=True)
    L.persist_cortex_store(cortex_dir, beliefs)


def _resolved_ops(reg):
    """Every declared operation resolved through the REAL descriptor surface —
    the ONE descriptor per capability (§5.2)."""
    out = {}
    for manifest in reg["manifests"]:
        for cap in manifest["domain_operations"]:
            out[cap] = resolve_descriptor(reg, cap)
    return out


def _organ_excerpts(reg, resolved, urgency):
    """The cabinet-side wake declaration: §4.2 manifests + resolved
    descriptors -> the snapshot's declared organ-registry excerpt rows (the
    fold's input shape). Urgency/trigger state is wake data the cabinet
    declares per run; costs/bounds/deps come verbatim from the manifests."""
    excerpts = []
    for manifest in reg["manifests"]:
        entry = {
            "organ": manifest["name"],
            "operations": [
                {"operation": cap,
                 "trigger_due": True,
                 "subject": None,
                 "urgency": urgency[cap],
                 "cost_units": manifest["cost_model"]["units_per_wake"],
                 "deps": {
                     "organs": list(manifest["dependencies"].get("organs", [])),
                     "capabilities": list(
                         manifest["dependencies"].get("capabilities", []))},
                 "descriptor": dict(resolved[cap])}
                for cap in manifest["domain_operations"]],
        }
        bound = manifest.get("starvation_bound")
        if isinstance(bound, dict) and "max_wakes" in bound:
            entry["starvation_bound"] = bound["max_wakes"]
        excerpts.append(entry)
    return excerpts


def _dispatch_manifest(manifest):
    """The dispatcher's declared organ-manifest input, derived from the §4.2
    manifest (the W2 dispatch-corpus shape, make_organ_manifest): packaging
    fields verbatim; the idempotency key discipline is the run-context
    key_fields derivation the corpus pins (§7.3 limb 6 re-derives keys over
    {organ, operation, wake_id} — a row-carried key is never trusted)."""
    return {
        "name": manifest["name"],
        "kind": manifest["kind"],
        "freshness_needs": dict(manifest["freshness_needs"]),
        "fallback": manifest["fallback"],
        "permissions": list(manifest["permissions"]),
        "dependencies": {
            "organs": list(manifest["dependencies"].get("organs", [])),
            "capabilities": list(
                manifest["dependencies"].get("capabilities", []))},
        "idempotency": {"key_fields": ["organ", "operation", "wake_id"]},
    }


def _capability_tokens(reg):
    caps = set()
    for manifest in reg["manifests"]:
        caps.update(manifest.get("permissions", []))
        caps.update(manifest["dependencies"].get("capabilities", []))
    return sorted(caps)


def _run_cabinet(tmp_path, spec, events_dir=None):
    """ONE cabinet end-to-end through the REAL CLIs. Returns everything the
    per-cabinet laws assert on."""
    cache_root = tmp_path / "cache"
    cortex_dir = cache_root / "cortex"
    objectives_dir = cache_root / "objectives"

    # (1) the real seeded substrate: cortex fold + objectives build (COG-3 CLI)
    _seed_cortex(cortex_dir, spec, events_dir)
    roots = _write_json(tmp_path / "roots.yml", spec["roots"])
    workgraph = _write_json(tmp_path / "workgraph.yml", spec["workgraph"])
    missions = _write_json(tmp_path / "missions.yml", spec["missions"])
    _run([str(_COG3_REBUILD), "--roots", str(roots), "--cache",
          str(objectives_dir), "--cutoff", CUTOFF, "--workgraph",
          str(workgraph), "--missions", str(missions)], "cog3-rebuild")

    # (2) organ manifests -> registry -> descriptors (the real organ surface)
    reg = load_organ_registry(_FIXTURE_ROOT / spec["dir"])
    resolved = _resolved_ops(reg)
    assert set(resolved) == set(spec["expected"]), (
        "fixture drift: declared operations != the expected-decision map")

    # (3) the declared snapshot inputs -> cog4-snapshot (real CLI)
    services = tmp_path / "services.yml"
    services.write_text(spec["services_text"], encoding="utf-8")
    excerpts = _write_json(tmp_path / "organ-excerpts.json",
                           _organ_excerpts(reg, resolved, spec["urgency"]))
    health = _write_json(tmp_path / "organ-health.json",
                         {m["name"]: "pass" for m in reg["manifests"]})
    failure = _write_json(tmp_path / "failure-history.json", {})
    caps = _write_json(tmp_path / "capability-availability.json",
                       {tok: True for tok in _capability_tokens(reg)})
    snap_proc = _run([str(_SNAPSHOT_CLI),
                      "--cache-root", str(cache_root),
                      "--cortex-cache-dir", str(cortex_dir),
                      "--objectives-cache-dir", str(objectives_dir),
                      "--services-manifest", str(services),
                      "--organ-registry", str(excerpts),
                      "--organ-health", str(health),
                      "--failure-history", str(failure),
                      "--capability-availability", str(caps),
                      "--budget-ceiling", str(_BUDGET_CEILING),
                      "--scope", spec["dir"],
                      "--cutoff", CUTOFF, "--json"], "cog4-snapshot")
    snap_result = json.loads(snap_proc.stdout.strip().splitlines()[-1])

    # (4) the pure fold -> schedule store (real CLI; kernel-bound serve echo)
    sched_proc = _run([str(_SCHEDULE_CLI), "--cache-root", str(cache_root),
                       "--json"], "cog4-schedule")
    sched = json.loads(sched_proc.stdout.strip().splitlines()[-1])
    n_ops = len(spec["expected"])
    assert sched["counts"] == {"rows": n_ops, "selected": n_ops,
                               "deferred": 0, "conflicts": 0}, sched
    assert sched["snapshot_hash"] == snap_result["snapshot_hash"]

    # (5) the §7.3 shadow dispatch (real CLI via the W5 adapter; hermetic
    # joint; the REAL matrix policy document — the same joint every cabinet
    # resolves through)
    snapshot_record = json.loads(
        (cache_root / "scheduler" / "wake-snapshot.json").read_text(
            encoding="utf-8"))
    live = {
        "wake_input_hashes": dict(snapshot_record["wake_input_hashes"]),
        "wake_id": spec["wake_id"],
        "remaining_budget": _REMAINING_BUDGET,
        "organ_output_age_seconds": {m["name"]: 0 for m in reg["manifests"]},
        "organ_health": {m["name"]: {"probe_ran": True, "exit_code": 0}
                         for m in reg["manifests"]},
        "organs_available": sorted(m["name"] for m in reg["manifests"]),
        "capabilities_available": _capability_tokens(reg),
    }
    dispatch_manifests = {m["name"]: _dispatch_manifest(m)
                          for m in reg["manifests"]}
    policy = authority_matrix.matrix_policy(authority_matrix.load_matrix())
    workdir = tmp_path / "dispatch"
    outcome = ADP.run_cli(cache_root / "scheduler", live, dispatch_manifests,
                          policy, workdir)
    return SimpleNamespace(reg=reg, resolved=resolved, outcome=outcome,
                           live=live, dispatch_manifests=dispatch_manifests,
                           policy=policy, workdir=workdir,
                           cache_dir=cache_root / "scheduler")


# ===========================================================================
# the per-cabinet law bundle (shared by all three end-to-end tests)
# ===========================================================================

_ENFORCEMENT_MEMBERS = ("action_type", "risk_class", "ceiling", "undo_contract")


def _records_by_capability(outcome):
    recs = {}
    for rec in outcome.records:
        assert rec["capability"] not in recs, "duplicate decision record"
        recs[rec["capability"]] = rec
    return recs


def _assert_single_enforcement_path(res, spec):
    """The N8 core claim: every operation's shadow decision came from the ONE
    dispatcher path, driven by the descriptor that rode UNCHANGED from
    manifest resolution through snapshot -> fold -> serve -> record."""
    assert res.outcome.returncode == 0, res.outcome.stderr
    assert res.outcome.mode == "dispatch"
    recs = _records_by_capability(res.outcome)
    assert set(recs) == set(spec["expected"])
    for cap, (decision, reason) in spec["expected"].items():
        rec = recs[cap]
        assert (rec["decision"], rec["reason"]) == (decision, reason), (
            cap, rec["decision"], rec["reason"])
        # the planner admitted every row — refusals are the DISPATCHER's
        assert rec["planner_admitted"] is True
        # the ONE descriptor, byte-identical end-to-end (§5.2/§5.3)
        assert rec["descriptor"] == res.resolved[cap], cap
        assert rec["descriptor"]["organ"] in res.dispatch_manifests
    # SF1 keys are re-derived over the declared context, never row-trusted
    for cap, (decision, _r) in spec["expected"].items():
        if decision == WOULD:
            rec = recs[cap]
            assert rec["idempotency_key"] == ADP.derive_idempotency_key(
                rec["organ"], cap, spec["wake_id"])
    return recs


def _assert_enum_growth_walls(resolved):
    """The three KEPT §5.4 enum-growth mutants, asserted DURING the fixture
    run — plus the zero-growth law over the fixture vocabulary itself."""
    # (1) census: central_action_types maximum 30, observed == max
    census = yaml.safe_load(_CENSUS_YML.read_text(encoding="utf-8"))
    row = census["budgets"]["central_action_types"]
    assert row["maximum"] == 30
    assert row["path"] == "framework/authority/classifier.py"
    assert row["symbol"] == "ACTION_TYPES"
    assert len(ACTION_TYPES) == row["maximum"]          # observed == max
    # (2) consequence-event schema set-equality (the closed 30 + null mirror)
    schema = json.loads(_CONSEQUENCE_SCHEMA.read_text(encoding="utf-8"))
    enum = schema["properties"]["action_type"]["enum"]
    assert None in enum
    assert {e for e in enum if e is not None} == set(ACTION_TYPES)
    # (3) matrix totality: load_matrix() raises on any drift; the closed 13
    policy = authority_matrix.matrix_policy(authority_matrix.load_matrix())
    assert set(authority_matrix.RISK_CLASSES) == t3.RISK_CLASS_ENUM
    assert len(authority_matrix.RISK_CLASSES) == 13
    # zero growth: every fixture operation is namespaced, never a member
    for cap, descriptor in resolved.items():
        assert "/" in cap and cap not in ACTION_TYPES
        assert descriptor["action_type"] in ACTION_TYPES
        assert descriptor["risk_class"] in authority_matrix.RISK_CLASSES
        assert set(descriptor["ceiling"]) <= set(policy["hard_ceiling"])


def _blindness_pairs(res, spec):
    a, b = spec["blind_pair"]
    members_a = {m: res.resolved[a][m] for m in _ENFORCEMENT_MEMBERS}
    members_b = {m: res.resolved[b][m] for m in _ENFORCEMENT_MEMBERS}
    assert members_a == members_b, (
        "fixture drift: the blindness pair no longer shares one descriptor")
    return [(a, b, members_a)]


def _assert_capability_blindness(res, spec):
    """§5.2 per cabinet: the REAL dispatch decisions are operation-name-blind,
    and a capability-keyed mutant predicate is CAUGHT by the W2 harness."""
    pairs = _blindness_pairs(res, spec)
    recs = _records_by_capability(res.outcome)

    def real_dispatch_predicate(op, _descriptor):
        return (recs[op]["decision"], recs[op]["reason"])

    assert t3.capability_blindness_violations(
        real_dispatch_predicate, pairs) == []

    favored = spec["blind_pair"][0]

    def capability_keyed_mutant(op, descriptor):
        # THE §5.2 mutant shape (the W2 _capability_keyed_mutant idiom,
        # re-aimed at THIS cabinet's favored operation name)
        if op == favored:
            return "shadow_ok"
        return t3._reference_verdict(op, descriptor)

    violations = t3.capability_blindness_violations(
        capability_keyed_mutant, pairs)
    assert violations, "the capability-keyed mutant must be CAUGHT"


def _assert_trajectory_v2(res, spec, cabinet_key):
    """§5.5 per cabinet: v2 records minted from the fixture shadow decisions
    validate against the REAL Draft-2020-12 schema; domain_operation carries
    the granular identity; the never-overload mutant fails."""
    recs = _records_by_capability(res.outcome)
    effects = []
    for i, cap in enumerate(sorted(recs), start=1):
        rec = recs[cap]
        descriptor = rec["descriptor"]
        # would-rows carry the dispatcher's re-derived key; refused rows never
        # reached limb 6, so the mint derives the SAME context-bound key the
        # dispatcher would have (a row-carried key is never trusted, SF1)
        key = rec.get("idempotency_key") or ADP.derive_idempotency_key(
            rec["organ"], cap, spec["wake_id"])
        effects.append({
            "effect_id": f"effect-{i:04d}",
            "action_type": descriptor["action_type"],
            "domain_operation": {"organ": rec["organ"], "operation": cap},
            "enforcement_descriptor": {
                "capability": descriptor["capability"],
                "action_type": descriptor["action_type"],
                "risk_class": descriptor["risk_class"],
                "ceiling": list(descriptor["ceiling"]),
                "undo_contract": descriptor["undo_contract"],
            },
            # shadow decisions mint INTENT ONLY: proposed | denied — nothing
            # was attempted, nothing executed (§7.3 shadow-absolute)
            "status": "proposed" if rec["decision"] == WOULD else "denied",
            "idempotency_key": key,
            "requested_at": "2026-07-19T11:54:00Z",
            "decision_at": "2026-07-19T12:00:00Z",
            "observed_at": "2026-07-19T12:15:00Z",
            "classification_receipt_ref": {
                "ref": "receipt:classification", "digest": TV2._DIGEST},
            "authority_decision_ref": {
                "ref": "receipt:authorization", "digest": TV2._DIGEST},
            "effect_receipt_ref": {
                "ref": "receipt:effect", "digest": TV2._DIGEST},
            "undo_receipt_ref": {
                "ref": "receipt:undo", "digest": TV2._DIGEST},
        })
    assert len(effects) == len(spec["expected"])

    # every minted effect satisfies the W2 reference law too (granular id in
    # domain_operation; bare closed-30 compat member in action_type)
    for effect in effects:
        assert t3.v2_effect_errors(effect) == [], effect["effect_id"]
        assert effect["domain_operation"]["operation"] == \
            effect["enforcement_descriptor"]["capability"]
        assert "/" not in effect["action_type"]

    record = TV2.v2_record()                     # the landed W4 envelope
    record["trajectory_id"] = f"trajectory-{cabinet_key}-0001"
    record["authority_scope"] = {"cabinet_id": f"cabinet-{cabinet_key}",
                                 "scope_kind": "cabinet"}
    record["effects"] = effects
    issues = C.structural_issues(record)         # the REAL v2 validator
    assert issues == (), [f"{i.path}: {i.message}" for i in issues]

    # the never-overload mutant (§5.5, charter L184): a namespaced id in
    # action_type must FAIL the real schema — per cabinet
    mutant = copy.deepcopy(record)
    mutant["effects"][0]["action_type"] = \
        mutant["effects"][0]["enforcement_descriptor"]["capability"]
    assert C.structural_issues(mutant) != (), (
        "a namespaced id in action_type must fail v2 validation")


def _assert_cabinet_laws(res, spec, cabinet_key):
    recs = _assert_single_enforcement_path(res, spec)
    _assert_enum_growth_walls(res.resolved)
    _assert_capability_blindness(res, spec)
    _assert_trajectory_v2(res, spec, cabinet_key)
    return recs


# ===========================================================================
# fixture-data validation — the §4.2 amendment shape through the W2 reference
# ===========================================================================

@pytest.mark.parametrize("cabinet_key", sorted(CABINETS))
def test_fixture_manifests_validate_against_the_amendment_reference(cabinet_key):
    """Every committed organ manifest passes the W2 §4.2 reference validator
    (the germline pair stays byte-untouched — window unopened; the proposal
    text is the build target per §4.5); state_ownership is disjoint (N-b);
    every resolved descriptor is matrix-consistent (N-d)."""
    spec = CABINETS[cabinet_key]
    reg = load_organ_registry(_FIXTURE_ROOT / spec["dir"])
    assert reg["count"] == 2, "two organs per fixture cabinet"
    for manifest in reg["manifests"]:
        assert t3.validate_organ_manifest(manifest) == [], manifest["name"]
    assert state_ownership_collisions(reg["manifests"]) == []
    assert t3.state_ownership_collisions(reg["manifests"]) == []
    resolved = _resolved_ops(reg)
    assert set(resolved) == set(spec["expected"])
    for cap, descriptor in sorted(resolved.items()):
        assert t3.matrix_consistency_errors(descriptor) == [], cap
        assert descriptor["status_vocab"] == list(t3.STATUS_ENUM)


# ===========================================================================
# the three end-to-end cabinets (N8/MR4)
# ===========================================================================

def test_cabinet_a_garden_delivery_end_to_end(tmp_path, events_dir):
    """Cabinet A — the COG-3 exit-fixture #2 operation EXTENDED with the organ
    layer (MR4), plus the SF1 idempotency-replay arm and the W2 corpus's own
    garden/water.plots capability-keyed mutant."""
    spec = CABINETS["garden-delivery"]
    res = _run_cabinet(tmp_path, spec, events_dir=events_dir)
    _assert_cabinet_laws(res, spec, "garden-delivery")

    # the W2 corpus's OWN §5.2 mutant (favors garden/water.plots) is caught
    # on this cabinet's pair — the fixture binds the corpus harness verbatim
    assert t3.capability_blindness_violations(
        t3._capability_keyed_mutant, _blindness_pairs(res, spec)) != []

    # SF1 replay (limb 6): the same wake re-dispatched against the same
    # shadow log refuses every previously granted operation; authority
    # refusals are unchanged (the earlier limbs still decide first)
    out2 = ADP.run_cli(res.cache_dir, res.live, res.dispatch_manifests,
                       res.policy, res.workdir)
    assert out2.mode == "dispatch"
    recs2 = _records_by_capability(out2)
    for cap, (decision, reason) in spec["expected"].items():
        if decision == WOULD:
            assert (recs2[cap]["decision"], recs2[cap]["reason"]) == \
                (REFUSED, "idempotency_replay"), cap
        else:
            assert (recs2[cap]["decision"], recs2[cap]["reason"]) == \
                (decision, reason), cap

    # a FRESH wake dispatches again — keys are context-bound, re-derived
    live3 = dict(res.live, wake_id="wake-garden-0002")
    out3 = ADP.run_cli(res.cache_dir, live3, res.dispatch_manifests,
                       res.policy, res.workdir)
    recs3 = _records_by_capability(out3)
    for cap, (decision, reason) in spec["expected"].items():
        assert (recs3[cap]["decision"], recs3[cap]["reason"]) == \
            (decision, reason), cap

    # the shadow log carries the appended run + decision records (§7.3) —
    # the dispatcher's ONLY write surface
    log_rows = [json.loads(line) for line in
                (res.workdir / "shadow-log.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]
    kinds = {row.get("record_kind") for row in log_rows}
    assert kinds == {"run", "decision"}
    assert sum(1 for row in log_rows if row.get("record_kind") == "run") == 3


def test_cabinet_b_harbor_warehouse_end_to_end(tmp_path):
    """Cabinet B — the NEW physical-logistics cabinet (harbourside goods-shed):
    eight operations, five would-dispatch, three refused, one shared
    enforcement path."""
    spec = CABINETS["harbor-warehouse"]
    res = _run_cabinet(tmp_path, spec)
    _assert_cabinet_laws(res, spec, "harbor-warehouse")


def test_cabinet_c_care_rota_end_to_end(tmp_path):
    """Cabinet C — the NEW community-operations cabinet (neighbourhood care
    rota): eight operations across visits and meals, same single enforcement
    decision path."""
    spec = CABINETS["care-rota"]
    res = _run_cabinet(tmp_path, spec)
    _assert_cabinet_laws(res, spec, "care-rota")


# ===========================================================================
# the r14-style token sweep — fixture data carries no technical-domain
# vocabulary (contract §12 N8 "zero software vocabulary, token-grepped")
# ===========================================================================

def _banned_tokens():
    """Assembled from parts so THIS file never itself trips a vocabulary
    sweep (the test_cog3_exit_fixtures.py §9 r14 idiom)."""
    parts = [
        ("co", "de"), ("dep", "loy"), ("ser", "ver"), ("a", "pi"),
        ("d", "b"), ("data", "base"), ("soft", "ware"), ("s", "ql"),
        ("end", "point"), ("back", "end"), ("front", "end"),
        ("dock", "er"), ("kuber", "netes"), ("dev", "ops"),
        ("py", "thon"), ("java", "script"), ("g", "it"), ("ht", "tp"),
    ]
    return ["".join(p) for p in parts]


def _token_hits(text, where):
    hits = []
    lowered = text.lower()
    for tok in _banned_tokens():
        if re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", lowered):
            hits.append((where, tok))
    return hits


def test_fixture_data_carries_no_technical_vocabulary():
    """The N8 sweep: every committed fixture-cabinet file AND every in-test
    cabinet seed payload (roots/workgraph/missions/services/urgency/expected
    vocabulary) is free of the banned technical-domain tokens."""
    hits = []
    files = sorted(p for p in _FIXTURE_ROOT.rglob("*") if p.is_file())
    assert len(files) == 6, "three cabinets, two organ manifests each"
    for path in files:
        hits += _token_hits(path.read_text(encoding="utf-8"),
                            str(path.relative_to(_REPO)))
    hits += _token_hits(json.dumps(CABINETS, sort_keys=True),
                        "test_cog4_exit_fixtures.CABINETS")
    assert hits == [], f"technical vocabulary leaked into fixture data: {hits}"


def test_fixture_operation_ids_are_namespaced_and_uncollidable():
    """The §4.2 separator law over ALL committed cabinet operations: every id
    is namespaced and can never collide with the flat central vocabulary."""
    for spec in CABINETS.values():
        reg = load_organ_registry(_FIXTURE_ROOT / spec["dir"])
        for manifest in reg["manifests"]:
            for cap in manifest["domain_operations"]:
                assert t3.DOMAIN_OP_RE.fullmatch(cap), cap
                assert cap not in ACTION_TYPES
