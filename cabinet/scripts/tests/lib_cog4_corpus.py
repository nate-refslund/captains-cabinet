"""lib_cog4_corpus.py — the COG-4 W2 corpus CORE: wake-snapshot fixture schema,
canonical hashing, the reference fold simulator, the biting mutant registry, the
subprocess fold runners, and the scheduler-fold sim assert batteries (contract
cognitive-core-phase-4-contract-2026-07-23 §12 sims 1/2/4/7/8/13 + N1 + N2).

OWNERSHIP (W2 naming law): this file is authored and owned by the W2 T1 unit.
T2/T3 corpus units IMPORT it and may add their own `lib_cog4_corpus_*.py`
siblings — they never create or edit THIS file. Cross-unit shared constants
(artifact names, the manifest rows-hash key, the snapshot schema) live HERE so
parallel units never maintain duplicate pinned constants (§13).

WHAT THIS LIB IS (and is not): `framework/scheduler/` does not exist yet — the
corpus lands BEFORE the implementation (tests-first, §13). The REFERENCE FOLD
below is a fixture-machinery simulator implementing the contract's fold
semantics (§7.1-§7.2) over authored wake-snapshot data files, so every sim
assert + every §12 negative-control mutant is proven BITING NOW, on this tree,
with zero implementation present. It is NOT the implementation and never ships
outside the test surface. When W3 lands `framework.scheduler.fold`, the SAME
assert batteries run against the real surface via `real_runner()` /
`run_real_arm(...)` — the corpus is the executable spec the implementation
must satisfy UNMODIFIED (§13: builders never edit tests; contradictions route
to the integrator).

THE CORPUS-PINNED SNAPSHOT SHAPE (cog4-wake-snapshot/v1 — §7.1/§2.1; the
implementation binds to THESE names):
  schema_version            "cog4-wake-snapshot/v1"
  scope                     declared scope token
  cutoff                    canonical UTC second "YYYY-MM-DDTHH:MM:SSZ" (§7.1
                            replicated validator: hard-error otherwise)
  wake_input_hashes         the seven §7.1 wake-input hashes (see
                            WAKE_INPUT_HASH_KEYS). The four SF2-family hashes
                            are SELF-CONSISTENT: recomputable from the
                            snapshot's own family data via `family_hash`
                            (organ_registry_hash additionally sorts organs by
                            name first — the §4.4 sorted-manifests law).
  objectives_epoch          opaque declared epoch tuple echo (§2.1)
  budget_version, posture_version, trust_table_version,
  scheduler_policy_version  declared versioned parameters (§7.1 — never
                            env/clock reads; A-M6)
  scheduler_policy          {"default_starvation_bound": int} — the SF2
                            scheduler_policy default that applies when an
                            organ declares no starvation_bound (§2.1)
  budget                    {"ceiling_units_per_wake": int} — the external
                            hard ceiling bounding the fold (§7.2)
  organs                    the registry excerpt: [{organ, starvation_bound
                            (int|null — null ⇒ policy default), operations:
                            [{operation (§4.2 namespaced ^[a-z0-9_-]+/
                            [a-z0-9._-]+$), subject (str|null), urgency (int),
                            cost_units (int), trigger_due (bool), deps:
                            {organs: [], capabilities: []}, descriptor:
                            {…§5.2 echo…}}]}]
  organ_health              SF2 family: {organ: "pass"|"fail"}
  failure_history           SF2 family: {organ: {"wakes_waiting": int,
                            "recent_failures": [...]}} — wakes_waiting is the
                            declared runner-state starvation input (N2: the
                            bound AND the wait state are snapshot inputs,
                            never planner-invented)
  capability_availability   SF2 family: {capability: bool}

THE CORPUS-PINNED SCHEDULE ARTIFACTS (§7.2/§6.3; written under cache_dir):
  snapshot.json             the canonical snapshot RECORD (canonical bytes of
                            the snapshot; epoch.snapshot_hash = sha256 of
                            exactly these bytes)
  schedule.jsonl            one canonical-JSON decision row per line, emitted
                            in tie_break_key order (total order by canonical
                            bytes — §7.2). Row fields: organ, operation,
                            subject, descriptor, decision ("select"|"defer"),
                            reason, budget_units, deps, tie_break_key.
                            EXACTLY ONE row per eligible (organ, operation)
                            ([ROW-UNIQUE]); budget_units == that op's
                            snapshot-DECLARED cost_units ([ROW-COST-DECLARED])
                            and budget.selected_units sums the SELECTED rows'
                            declared costs ([BUDGET-DECLARED]) — the two
                            2026-07-23 review-escape laws, each with its own
                            biting mutant (double_decision, cost_misreport).
  schedule-manifest.json    {schema_version, epoch: {scheduler_version,
                            snapshot_hash, wake_input_hashes, scope, cutoff},
                            schedule_rows_hash (MANDATORY — §6.3: a manifest
                            omitting this key REFUSES at serve/dispatch; T2's
                            sim-11 owns that limb), counts, conflicts,
                            scheduler_policy_version (echo — sim 13),
                            budget {ceiling_units_per_wake, selected_units}}

THE CORPUS-PINNED ROWS-HASH ALGEBRA (§6.1(c) parameterization, pinned for the
schedule store): chain seed b"cog4-schedule/v1"; h0 = sha256(seed); per row in
FILE ORDER h_i = sha256(h_{i-1}.digest + canonical_bytes(row)); hex of the
final digest. Zero rows ⇒ hex(sha256(seed)) — the empty chain is still a
mandatory manifest value (sim 2).

Pure stdlib + no framework import (this lib must run on the bare tree and must
not itself reach any fenced module; the real surface is imported ONLY inside
`real_runner()` subprocess children, which is why the bare tree stays green).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-4 contract §12/§13, W2 T1).
"""
from __future__ import annotations

import collections
import copy
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import lib_cog4_ast_pins as _PINS

# --------------------------------------------------------------------------
# shared constants (cross-unit: T2/T3 import these, never redefine them)
# --------------------------------------------------------------------------
SCHEDULER_TREE_REL = _PINS.SCHEDULER_TREE_REL          # "framework/scheduler"
FOLD_MODULE = "framework.scheduler.fold"               # §7.2 build_schedule home
SNAPSHOT_MODULE = "framework.scheduler.snapshot"       # §7.1 build_snapshot home

SNAPSHOT_SCHEMA_VERSION = "cog4-wake-snapshot/v1"
MANIFEST_SCHEMA_VERSION = "cog4-schedule-manifest/v1"

SNAPSHOT_RECORD_FILE = "snapshot.json"
SCHEDULE_FILE = "schedule.jsonl"
MANIFEST_FILE = "schedule-manifest.json"
ARTIFACT_FILES = (SNAPSHOT_RECORD_FILE, SCHEDULE_FILE, MANIFEST_FILE)

# §6.3: the rows-hash limb is MANDATORY-PRESENT in the schedule manifest.
MANIFEST_ROWS_HASH_KEY = "schedule_rows_hash"
CHAIN_SEED = b"cog4-schedule/v1"

# the seven §7.1 wake-input hashes (SF2 families marked *; self-consistent).
WAKE_INPUT_HASH_KEYS = (
    "cortex_belief_store_hash",
    "objectives_graph_rows_hash",
    "organ_registry_hash",            # * starvation bounds ride the registry
    "services_manifest_hash",
    "organ_health_hash",              # * SF2 health outcomes
    "failure_history_hash",           # * SF2 failure history (+ wakes_waiting)
    "capability_availability_hash",   # * SF2 capability/MCP availability
)
SF2_SELF_CONSISTENT = {
    "organ_health_hash": "organ_health",
    "failure_history_hash": "failure_history",
    "capability_availability_hash": "capability_availability",
}

DECISION_SELECT = "select"
DECISION_DEFER = "defer"
REASON_SELECTED = "selected"
REASON_BUDGET_EXHAUSTED = "budget_exhausted"
REASON_COST_CEILING = "cost_exceeds_ceiling"
REASON_CONFLICT_PREFIX = "conflict:"

ROW_FIELDS = ("organ", "operation", "subject", "descriptor", "decision",
              "reason", "budget_units", "deps", "tie_break_key")
EPOCH_KEYS = ("scheduler_version", "snapshot_hash", "wake_input_hashes",
              "scope", "cutoff")

# §4.2 namespaced operation id + §7.1 canonical cutoff (replicated validator).
OP_ID_RE = re.compile(r"^[a-z0-9_-]+/[a-z0-9._-]+$")
CUTOFF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# purity-harness env knob (corpus-only; NOT a real runtime flag).
ENV_KNOB = "COG4_CORPUS_KNOB"

_TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = _TESTS_DIR / "fixtures" / "cog4" / "fold"


# --------------------------------------------------------------------------
# canonical bytes + hashing
# --------------------------------------------------------------------------
def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def family_hash(obj) -> str:
    """Hash of one declared snapshot input family (canonical bytes)."""
    return sha256_hex(canonical_bytes(obj))


def organ_registry_hash(organs: list) -> str:
    """§4.4: canonical bytes over SORTED manifests — order-independent, so a
    registry listed in any order hashes identically."""
    return family_hash(sorted(organs, key=lambda o: o["organ"]))


def chained_rows_hash(rows: list) -> str:
    """The corpus-pinned §6.1(c) chain (seed + file order); see module doc."""
    h = hashlib.sha256(CHAIN_SEED)
    for row in rows:
        h = hashlib.sha256(h.digest() + canonical_bytes(row))
    return h.hexdigest()


def tie_break_key(organ: str, operation: str) -> str:
    """§7.2: tie-breaks total-ordered by canonical bytes of the identity."""
    return canonical_bytes([organ, operation]).decode("ascii")


# --------------------------------------------------------------------------
# snapshot validation + IO (fixtures are SELF-CONSISTENT: SF2 hashes recompute)
# --------------------------------------------------------------------------
def validate_snapshot(snap: dict) -> None:
    assert snap.get("schema_version") == SNAPSHOT_SCHEMA_VERSION, snap.get(
        "schema_version")
    assert isinstance(snap.get("scope"), str) and snap["scope"]
    assert CUTOFF_RE.fullmatch(snap.get("cutoff", "")), (
        f"non-canonical cutoff {snap.get('cutoff')!r} (§7.1 hard-error)")
    wih = snap.get("wake_input_hashes")
    assert isinstance(wih, dict) and set(wih) == set(WAKE_INPUT_HASH_KEYS), (
        f"wake_input_hashes keys {sorted(wih or ())} != §7.1 set")
    for key, val in wih.items():
        assert re.fullmatch(r"[0-9a-f]{64}", val), (key, val)
    for key in ("budget_version", "posture_version", "trust_table_version",
                "scheduler_policy_version"):
        assert isinstance(snap.get(key), int), key
    assert isinstance(snap.get("objectives_epoch"), dict)
    assert isinstance(
        snap.get("scheduler_policy", {}).get("default_starvation_bound"), int)
    assert isinstance(
        snap.get("budget", {}).get("ceiling_units_per_wake"), int)
    organs = snap.get("organs")
    assert isinstance(organs, list)
    names = [o["organ"] for o in organs]
    assert len(names) == len(set(names)), "duplicate organ names"
    for organ in organs:
        bound = organ.get("starvation_bound")
        assert bound is None or (isinstance(bound, int) and bound >= 1), organ
        for op in organ.get("operations", ()):
            assert OP_ID_RE.fullmatch(op["operation"]), (
                f"non-namespaced operation id {op['operation']!r} (§4.2)")
            assert op.get("subject") is None or isinstance(op["subject"], str)
            assert isinstance(op.get("urgency"), int)
            assert isinstance(op.get("cost_units"), int)
            assert isinstance(op.get("trigger_due"), bool)
            assert isinstance(op.get("deps"), dict)
            assert isinstance(op.get("descriptor"), dict)
    for fam in ("organ_health", "failure_history", "capability_availability"):
        assert isinstance(snap.get(fam), dict), fam
    # SF2 self-consistency: the four family hashes recompute from snapshot data.
    for hash_key, fam in SF2_SELF_CONSISTENT.items():
        assert wih[hash_key] == family_hash(snap[fam]), (
            f"{hash_key} does not recompute from snapshot {fam!r} data")
    assert wih["organ_registry_hash"] == organ_registry_hash(organs), (
        "organ_registry_hash does not recompute from the snapshot registry")


def refresh_sf2_hashes(snap: dict) -> None:
    """Recompute the four self-consistent hashes after mutating family data
    (the multi-wake harness edits failure_history between wakes — the wait
    state is a DECLARED snapshot input, so the harness plays the state
    carrier and re-declares honestly)."""
    wih = snap["wake_input_hashes"]
    for hash_key, fam in SF2_SELF_CONSISTENT.items():
        wih[hash_key] = family_hash(snap[fam])
    wih["organ_registry_hash"] = organ_registry_hash(snap["organs"])


def load_fixture(name: str) -> dict:
    snap = json.loads((FIXTURE_DIR / f"{name}.json").read_text("utf-8"))
    validate_snapshot(snap)
    return snap


def fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def write_snapshot(snap: dict, path: Path) -> str:
    """Write canonical snapshot bytes; return their sha256 (the record hash)."""
    validate_snapshot(snap)
    data = canonical_bytes(snap)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_hex(data)


# --------------------------------------------------------------------------
# eligibility (shared by reference + mutants)
# --------------------------------------------------------------------------
def eligible_ops(snap: dict) -> list:
    """Flatten eligible (organ, op) contexts. Eligible = trigger_due AND organ
    health pass AND every capability dep available AND every organ dep present
    + healthy. (Sims 5/6/9 fixtures — other units — exercise the failure
    arms; T1 fixtures keep those clean except where a sim seeds them.)"""
    health = snap.get("organ_health", {})
    caps = snap.get("capability_availability", {})
    by_name = {o["organ"]: o for o in snap["organs"]}
    out = []
    for organ in snap["organs"]:
        if health.get(organ["organ"]) != "pass":
            continue
        for op in organ.get("operations", ()):
            if not op["trigger_due"]:
                continue
            deps = op.get("deps", {})
            if not all(caps.get(c, False)
                       for c in deps.get("capabilities", ())):
                continue
            if not all(d in by_name and health.get(d) == "pass"
                       for d in deps.get("organs", ())):
                continue
            out.append({
                "organ": organ["organ"],
                "operation": op["operation"],
                "subject": op.get("subject"),
                "urgency": op["urgency"],
                "cost_units": op["cost_units"],
                "deps": deps,
                "descriptor": op["descriptor"],
                "tie_break_key": tie_break_key(organ["organ"],
                                               op["operation"]),
            })
    return out


def _bound_of(snap: dict, organ_name: str) -> int:
    for organ in snap["organs"]:
        if organ["organ"] == organ_name:
            bound = organ.get("starvation_bound")
            if isinstance(bound, int):
                return bound
    return snap["scheduler_policy"]["default_starvation_bound"]


def _waiting_of(snap: dict, organ_name: str) -> int:
    return int(snap.get("failure_history", {})
               .get(organ_name, {}).get("wakes_waiting", 0))


def _row(ctx: dict, decision: str, reason: str) -> dict:
    return {
        "organ": ctx["organ"], "operation": ctx["operation"],
        "subject": ctx["subject"], "descriptor": ctx["descriptor"],
        "decision": decision, "reason": reason,
        "budget_units": ctx["cost_units"], "deps": ctx["deps"],
        "tie_break_key": ctx["tie_break_key"],
    }


def _manifest(snap: dict, snapshot_hash: str, rows: list, conflicts: list,
              selected_units: int, scheduler_version: str,
              policy_version=None) -> dict:
    selected = sum(1 for r in rows if r["decision"] == DECISION_SELECT)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "epoch": {
            "scheduler_version": scheduler_version,
            "snapshot_hash": snapshot_hash,
            "wake_input_hashes": snap["wake_input_hashes"],
            "scope": snap["scope"],
            "cutoff": snap["cutoff"],
        },
        MANIFEST_ROWS_HASH_KEY: chained_rows_hash(rows),
        "counts": {"rows": len(rows), "selected": selected,
                   "deferred": len(rows) - selected,
                   "conflicts": len(conflicts)},
        "conflicts": conflicts,
        "scheduler_policy_version": (snap["scheduler_policy_version"]
                                     if policy_version is None
                                     else policy_version),
        "budget": {"ceiling_units_per_wake":
                   snap["budget"]["ceiling_units_per_wake"],
                   "selected_units": selected_units},
    }


# --------------------------------------------------------------------------
# THE REFERENCE FOLD (fixture machinery — the §7.2 semantics, pure)
# --------------------------------------------------------------------------
def reference_fold(snap: dict, snapshot_hash: str):
    """Pure fold: snapshot dict -> (rows, manifest). No env, no clock, no
    randomness (A-M6); conflicts symmetric+sorted, never auto-resolved (sim 8);
    starvation bounds honored from snapshot inputs (sim 7/N2); external hard
    ceiling bounds selection (sims 1/4); zero eligible ⇒ zero rows (sim 2);
    subjects are OPAQUE — a self-targeting op gets no special weight either
    way (sim 13); the policy version is echoed input-only (sim 13)."""
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    pool = eligible_ops(snap)

    # sim-8: two organs proposing operations on ONE subject = a conflict.
    # BOTH surface as defer rows; the record is symmetric (input-order-free)
    # + sorted (participants by canonical identity).
    by_subject = {}
    for ctx in pool:
        if ctx["subject"] is not None:
            by_subject.setdefault(ctx["subject"], []).append(ctx)
    conflicted_ids, conflicts = set(), []
    for subject in sorted(by_subject):
        group = by_subject[subject]
        if len({c["organ"] for c in group}) >= 2:
            for ctx in group:
                conflicted_ids.add(ctx["tie_break_key"])
            conflicts.append({
                "subject": subject,
                "participants": sorted([c["organ"], c["operation"]]
                                       for c in group),
            })

    rows = []
    for ctx in pool:
        if ctx["tie_break_key"] in conflicted_ids:
            rows.append(_row(ctx, DECISION_DEFER,
                             REASON_CONFLICT_PREFIX + ctx["subject"]))

    # sim-7/N2: starvation-critical ops (waiting+1 >= declared bound, bound a
    # SNAPSHOT INPUT with the scheduler_policy default when absent) are
    # promoted ahead of pure urgency; ties total-ordered by canonical bytes.
    contenders = [c for c in pool if c["tie_break_key"] not in conflicted_ids]

    def _key(ctx):
        critical = (_waiting_of(snap, ctx["organ"]) + 1
                    >= _bound_of(snap, ctx["organ"]))
        return (0 if critical else 1, -ctx["urgency"], ctx["tie_break_key"])

    remaining = ceiling
    for ctx in sorted(contenders, key=_key):
        if ctx["cost_units"] > ceiling:
            rows.append(_row(ctx, DECISION_DEFER, REASON_COST_CEILING))
        elif ctx["cost_units"] <= remaining:
            rows.append(_row(ctx, DECISION_SELECT, REASON_SELECTED))
            remaining -= ctx["cost_units"]
        else:
            rows.append(_row(ctx, DECISION_DEFER, REASON_BUDGET_EXHAUSTED))

    rows.sort(key=lambda r: r["tie_break_key"])
    manifest = _manifest(snap, snapshot_hash, rows, conflicts,
                         ceiling - remaining, "cog4-corpus-ref/1")
    return rows, manifest


# --------------------------------------------------------------------------
# THE §12 NEGATIVE-CONTROL MUTANTS (each must FAIL the exact named escape)
# --------------------------------------------------------------------------
def mutant_fold_dict_order(snap: dict, snapshot_hash: str):
    """sim-1 mutant: hash-order tie-break — selection order + emitted rows ride
    the salted str hash (PYTHONHASHSEED), so the C-F3 triple diverges. The raw
    salted hash is also EMBEDDED per row, so any seed change shows."""
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    pool = {c["tie_break_key"]: c for c in eligible_ops(snap)}
    rows, remaining = [], ceiling
    # iterate a SET (hash-order) instead of the canonical total order.
    for key in set(pool):
        ctx = pool[key]
        decision = (DECISION_SELECT if ctx["cost_units"] <= remaining
                    else DECISION_DEFER)
        if decision == DECISION_SELECT:
            remaining -= ctx["cost_units"]
        row = _row(ctx, decision,
                   REASON_SELECTED if decision == DECISION_SELECT
                   else REASON_BUDGET_EXHAUSTED)
        row["tie_break_key"] = f"{hash(key) & 0xFFFFFFFFFFFF:012x}"
        rows.append(row)                      # emitted in hash order, unsorted
    manifest = _manifest(snap, snapshot_hash, rows, [],
                         ceiling - remaining, "cog4-mutant-dict-order/1")
    return rows, manifest


def mutant_fold_idle_spin(snap: dict, snapshot_hash: str):
    """sim-2 mutant: on a quiet wake, invents a make-work no-op row instead of
    an EMPTY schedule (ceremony the contract forbids)."""
    rows, manifest = reference_fold(snap, snapshot_hash)
    if not rows:
        ctx = {"organ": "scheduler", "operation": "internal/idle-tick",
               "subject": None, "urgency": 0, "cost_units": 0,
               "deps": {"organs": [], "capabilities": []},
               "descriptor": {"capability": "internal/idle-tick"},
               "tie_break_key": tie_break_key("scheduler",
                                              "internal/idle-tick")}
        rows = [_row(ctx, DECISION_SELECT, "idle-spin")]
        manifest = _manifest(snap, snapshot_hash, rows, [], 0,
                             "cog4-mutant-idle-spin/1")
    return rows, manifest


def mutant_fold_cost_ignore(snap: dict, snapshot_hash: str):
    """sim-4 mutant: ignores the declared cost model vs the external ceiling —
    a spiked-cost op is selected anyway (ceiling breached)."""
    rows, spent = [], 0
    for ctx in sorted(eligible_ops(snap),
                      key=lambda c: (-c["urgency"], c["tie_break_key"])):
        rows.append(_row(ctx, DECISION_SELECT, REASON_SELECTED))
        spent += ctx["cost_units"]
    rows.sort(key=lambda r: r["tie_break_key"])
    manifest = _manifest(snap, snapshot_hash, rows, [], spent,
                         "cog4-mutant-cost-ignore/1")
    return rows, manifest


def mutant_fold_starvation_prone(snap: dict, snapshot_hash: str):
    """sim-7/N2 mutant: pure-urgency weighting — the declared starvation bound
    (and the declared wait state) is ignored, so the seeded high-urgency organ
    starves past its bound under adversarial load."""
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    rows, remaining = [], ceiling
    for ctx in sorted(eligible_ops(snap),
                      key=lambda c: (-c["urgency"], c["tie_break_key"])):
        if ctx["cost_units"] > ceiling:
            rows.append(_row(ctx, DECISION_DEFER, REASON_COST_CEILING))
        elif ctx["cost_units"] <= remaining:
            rows.append(_row(ctx, DECISION_SELECT, REASON_SELECTED))
            remaining -= ctx["cost_units"]
        else:
            rows.append(_row(ctx, DECISION_DEFER, REASON_BUDGET_EXHAUSTED))
    rows.sort(key=lambda r: r["tie_break_key"])
    manifest = _manifest(snap, snapshot_hash, rows, [],
                         ceiling - remaining, "cog4-mutant-starvation/1")
    return rows, manifest


def mutant_fold_lww(snap: dict, snapshot_hash: str):
    """sim-8 mutant: LAST-WRITE-WINS auto-resolve — on a subject collision the
    later-in-registry op silently wins; the loser is DROPPED (no row) and no
    conflict is recorded."""
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    survivors = {}
    for ctx in eligible_ops(snap):        # registry order: later overwrites
        survivors[ctx["subject"] or ctx["tie_break_key"]] = ctx
    rows, remaining = [], ceiling
    for ctx in sorted(survivors.values(),
                      key=lambda c: (-c["urgency"], c["tie_break_key"])):
        if ctx["cost_units"] <= remaining:
            rows.append(_row(ctx, DECISION_SELECT, REASON_SELECTED))
            remaining -= ctx["cost_units"]
        else:
            rows.append(_row(ctx, DECISION_DEFER, REASON_BUDGET_EXHAUSTED))
    rows.sort(key=lambda r: r["tie_break_key"])
    manifest = _manifest(snap, snapshot_hash, rows, [],
                         ceiling - remaining, "cog4-mutant-lww/1")
    return rows, manifest


def mutant_fold_self_weight(snap: dict, snapshot_hash: str):
    """sim-13 mutant (self-weight-update fold), all three named escapes:
    (a) self-targeting ops (subject under scheduler/) get INFINITE weight;
    (b) the fold BUMPS scheduler_policy_version in its output (input-only law
    broken); (c) it writes a policy file OUTSIDE its cache (cwd-relative)."""
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    rows, remaining = [], ceiling

    def _key(ctx):
        self_targeting = (ctx["subject"] or "").startswith("scheduler/")
        return (0 if self_targeting else 1, -ctx["urgency"],
                ctx["tie_break_key"])

    for ctx in sorted(eligible_ops(snap), key=_key):
        if ctx["cost_units"] <= remaining:
            rows.append(_row(ctx, DECISION_SELECT, REASON_SELECTED))
            remaining -= ctx["cost_units"]
        else:
            rows.append(_row(ctx, DECISION_DEFER, REASON_BUDGET_EXHAUSTED))
    rows.sort(key=lambda r: r["tie_break_key"])
    bumped = snap["scheduler_policy_version"] + 1
    Path("scheduler-policy.json").write_bytes(          # escape (c): cwd write
        canonical_bytes({"scheduler_policy_version": bumped}))
    manifest = _manifest(snap, snapshot_hash, rows, [],
                         ceiling - remaining, "cog4-mutant-self-weight/1",
                         policy_version=bumped)         # escape (b)
    return rows, manifest


def mutant_fold_env_reading(snap: dict, snapshot_hash: str):
    """§7.1 A-M6 purity mutant: the fold reads the process ENVIRONMENT — a
    non-declared input — and folds it into ordering + the manifest."""
    knob = os.environ.get(ENV_KNOB, "")
    rows, manifest = reference_fold(snap, snapshot_hash)
    rows = sorted(rows, key=lambda r: (knob + r["tie_break_key"]) if knob
                  else r["tie_break_key"], reverse=bool(knob))
    manifest = dict(manifest)
    manifest["env_knob"] = knob
    manifest[MANIFEST_ROWS_HASH_KEY] = chained_rows_hash(rows)
    return rows, manifest


def mutant_fold_datetime_now(snap: dict, snapshot_hash: str):
    """§7.1 A-M6 purity mutant: the fold reads the CLOCK (datetime.now) — a
    non-declared input — and embeds it in the manifest."""
    import datetime
    rows, manifest = reference_fold(snap, snapshot_hash)
    manifest = dict(manifest)
    manifest["built_at"] = datetime.datetime.now().isoformat(
        timespec="microseconds")
    return rows, manifest


def mutant_fold_double_decision(snap: dict, snapshot_hash: str):
    """2026-07-23 review-escape mutant (ESCAPE 1, variant v_double_decision):
    emits BOTH a select row AND a defer row for the same (organ, operation) —
    the top selected op is decided twice. Every row is individually
    well-formed and honestly costed, and the manifest recomputes over the
    emitted rows (counts + rows-hash), so SET-based row accounting certifies
    it — only the exactly-one-row-per-eligible-op law ([ROW-UNIQUE]) bites."""
    rows, manifest = reference_fold(snap, snapshot_hash)
    top = next((r for r in rows if r["decision"] == DECISION_SELECT), None)
    if top is None:                    # no selected work: nothing to double
        return rows, manifest
    dup = dict(top)
    dup["decision"] = DECISION_DEFER
    dup["reason"] = REASON_BUDGET_EXHAUSTED
    rows.append(dup)
    rows.sort(key=lambda r: r["tie_break_key"])
    manifest = _manifest(snap, snapshot_hash, rows, manifest["conflicts"],
                         manifest["budget"]["selected_units"],
                         "cog4-mutant-double-decision/1")
    return rows, manifest


def mutant_fold_cost_misreport(snap: dict, snapshot_hash: str):
    """2026-07-23 review-escape mutant (ESCAPE 2, variant v_zero_budget_units):
    decouples REPORTED costs from the snapshot's declared cost model — selects
    EVERY affordable op (true cumulative cost may far exceed the ceiling)
    while writing budget_units=0 per row and selected_units=0 in the manifest,
    and still defers individually-spiked ops with the right reason (sim-4's
    reason checks stay green). The planner-side [CEILING] sum reads 0 <=
    ceiling, so only the declared-cost binding ([ROW-COST-DECLARED]) bites."""
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    rows = []
    for ctx in eligible_ops(snap):
        if ctx["cost_units"] > ceiling:
            row = _row(ctx, DECISION_DEFER, REASON_COST_CEILING)
        else:
            row = _row(ctx, DECISION_SELECT, REASON_SELECTED)
        row["budget_units"] = 0
        rows.append(row)
    rows.sort(key=lambda r: r["tie_break_key"])
    manifest = _manifest(snap, snapshot_hash, rows, [], 0,
                         "cog4-mutant-cost-misreport/1")
    return rows, manifest


FOLDS = {
    "reference": reference_fold,
    "dict_order": mutant_fold_dict_order,
    "idle_spin": mutant_fold_idle_spin,
    "cost_ignore": mutant_fold_cost_ignore,
    "starvation_prone": mutant_fold_starvation_prone,
    "lww": mutant_fold_lww,
    "self_weight": mutant_fold_self_weight,
    "env_reading": mutant_fold_env_reading,
    "datetime_now": mutant_fold_datetime_now,
    "double_decision": mutant_fold_double_decision,
    "cost_misreport": mutant_fold_cost_misreport,
}


# --------------------------------------------------------------------------
# builders + subprocess runners
# --------------------------------------------------------------------------
def build_with(fold_name: str, snapshot_path, cache_dir) -> None:
    """The in-child build entry: load the snapshot file, run the named fold,
    write the three schedule artifacts under cache_dir."""
    snapshot_path, cache_dir = Path(snapshot_path), Path(cache_dir)
    snap = json.loads(snapshot_path.read_text("utf-8"))
    validate_snapshot(snap)
    record = canonical_bytes(snap)
    snapshot_hash = sha256_hex(record)
    rows, manifest = FOLDS[fold_name](snap, snapshot_hash)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / SNAPSHOT_RECORD_FILE).write_bytes(record)
    (cache_dir / SCHEDULE_FILE).write_bytes(
        b"".join(canonical_bytes(r) + b"\n" for r in rows))
    (cache_dir / MANIFEST_FILE).write_bytes(canonical_bytes(manifest))


def _run_child(code: str, *, hashseed: int, extra_env=None, cwd=None):
    env = dict(os.environ)
    env.pop(ENV_KNOB, None)
    env["PYTHONHASHSEED"] = str(hashseed)
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, "-c", code], env=env,
                          cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True)


def corpus_runner(fold_name: str):
    """A subprocess runner for a NAMED corpus fold (reference or mutant):
    runner(snapshot_path, cache_dir, *, hashseed=1, extra_env=None, cwd=None).
    Each build is a fresh child so PYTHONHASHSEED genuinely varies (C-F3)."""
    assert fold_name in FOLDS, fold_name

    def _runner(snapshot_path, cache_dir, *, hashseed=1, extra_env=None,
                cwd=None):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(_TESTS_DIR)!r})\n"
            "import lib_cog4_corpus as C\n"
            f"C.build_with({fold_name!r}, {str(snapshot_path)!r}, "
            f"{str(cache_dir)!r})\n")
        r = _run_child(code, hashseed=hashseed, extra_env=extra_env, cwd=cwd)
        assert r.returncode == 0, (
            f"corpus fold {fold_name!r} child failed rc={r.returncode}\n"
            f"{r.stderr}")
    return _runner


def real_runner(repo: Path):
    """The REAL-surface runner: subprocess-imports framework.scheduler.fold
    and calls build_schedule(snapshot_path, cache_dir) per the §7.2 signature.
    Used by the guarded real arms — retire their vacuity skips onto this the
    moment the planner tree lands."""
    def _runner(snapshot_path, cache_dir, *, hashseed=1, extra_env=None,
                cwd=None):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(repo)!r})\n"
            f"from {FOLD_MODULE} import build_schedule\n"
            f"build_schedule({str(snapshot_path)!r}, {str(cache_dir)!r})\n")
        r = _run_child(code, hashseed=hashseed, extra_env=extra_env, cwd=cwd)
        assert r.returncode == 0, (
            f"real fold child failed rc={r.returncode}\n{r.stderr}")
    return _runner


@functools.lru_cache(maxsize=4)
def real_surface_import_probe(repo_str: str):
    """(returncode, stderr) of a child `import framework.scheduler.fold` —
    the ARMED proof for the vacuity guards: on the bare tree this fails with
    ModuleNotFoundError; the moment the tree lands it stops failing (and the
    companion absence assertion has already gone RED)."""
    r = _run_child(
        f"import sys\nsys.path.insert(0, {repo_str!r})\n"
        f"import {FOLD_MODULE}\n", hashseed=0)
    return r.returncode, r.stderr


# --------------------------------------------------------------------------
# artifact readers + the combined N1 hash
# --------------------------------------------------------------------------
def read_rows(cache_dir: Path) -> list:
    text = (Path(cache_dir) / SCHEDULE_FILE).read_text("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def read_manifest(cache_dir: Path) -> dict:
    return json.loads((Path(cache_dir) / MANIFEST_FILE).read_text("utf-8"))


def assert_artifacts_present(cache_dir: Path) -> None:
    missing = [f for f in ARTIFACT_FILES if not (Path(cache_dir) / f).exists()]
    assert not missing, f"[N1-ARTIFACTS] schedule artifacts missing: {missing}"


def combined_artifact_hash(cache_dir: Path) -> str:
    """The N1 instrument: one hash covering schedule.jsonl +
    schedule-manifest.json + the snapshot record (length-prefixed concat)."""
    assert_artifacts_present(cache_dir)
    h = hashlib.sha256()
    for name in ARTIFACT_FILES:
        data = (Path(cache_dir) / name).read_bytes()
        h.update(len(data).to_bytes(8, "big") + data)
    return h.hexdigest()


def selected_rows(rows: list) -> list:
    return [r for r in rows if r["decision"] == DECISION_SELECT]


def defer_rows(rows: list) -> list:
    return [r for r in rows if r["decision"] == DECISION_DEFER]


# --------------------------------------------------------------------------
# the assert batteries (runner-parameterized: live = corpus folds NOW,
# real arm = the same battery over real_runner() at retirement)
# --------------------------------------------------------------------------
def assert_schedule_wellformed(snap: dict, cache_dir: Path) -> None:
    """§7.2 row tuple + the EXACTLY-ONE-row-per-eligible-op law + the
    declared-cost binding (rows and the manifest budget carry the snapshot's
    DECLARED cost model — [CEILING] sums row costs, so this binding is what
    makes the ceiling gate bite cost-misreporting folds) + §6.3 mandatory
    rows-hash + epoch completeness + snapshot-record binding. Shared by every
    sim battery."""
    rows, manifest = read_rows(cache_dir), read_manifest(cache_dir)
    for row in rows:
        missing = [f for f in ROW_FIELDS if f not in row]
        assert not missing, f"[ROW-TUPLE] row missing {missing}: {row}"
        assert row["decision"] in (DECISION_SELECT, DECISION_DEFER), row
        assert isinstance(row["reason"], str) and row["reason"], (
            f"[ROW-REASON] empty reason: {row}")
    pool = eligible_ops(snap)
    eligible = {(c["organ"], c["operation"]) for c in pool}
    emitted = {(r["organ"], r["operation"]) for r in rows}
    assert emitted == eligible, (
        f"[ROWSET] decision rows {sorted(emitted)} != eligible ops "
        f"{sorted(eligible)} (no invented work, no dropped work)")
    # 2026-07-23 review ESCAPE 1: sets alone certify a fold double-emitting
    # decisions. With [ROWSET] equality, len == len forces EXACTLY ONE
    # select|defer row per eligible op.
    dupes = sorted(op for op, n in collections.Counter(
        (r["organ"], r["operation"]) for r in rows).items() if n > 1)
    assert len(rows) == len(eligible), (
        f"[ROW-UNIQUE] {len(rows)} decision rows over {len(eligible)} "
        f"eligible ops — every eligible op yields EXACTLY ONE select|defer "
        f"row (duplicated: {dupes})")
    # 2026-07-23 review ESCAPE 2: [CEILING] sums the fold's OWN reported
    # budget_units, so a fold writing 0s defeats it. Bind every row (and the
    # manifest budget echo) to the snapshot's DECLARED cost model.
    declared_cost = {(c["organ"], c["operation"]): c["cost_units"]
                     for c in pool}
    for row in rows:
        identity = (row["organ"], row["operation"])
        assert row["budget_units"] == declared_cost[identity], (
            f"[ROW-COST-DECLARED] row {identity} reports budget_units="
            f"{row['budget_units']} but the snapshot declares cost_units="
            f"{declared_cost[identity]} — rows carry the snapshot's DECLARED "
            "cost model, never fold-invented costs (§7.2)")
    assert manifest["budget"]["selected_units"] == sum(
        declared_cost[(r["organ"], r["operation"])]
        for r in rows if r["decision"] == DECISION_SELECT), (
        "[BUDGET-DECLARED] manifest budget.selected_units != the sum of the "
        "SELECTED rows' snapshot-declared costs (honest accounting, §7.2)")
    assert MANIFEST_ROWS_HASH_KEY in manifest, (
        f"[ROWSHASH-PRESENT] manifest omits the MANDATORY {MANIFEST_ROWS_HASH_KEY} "
        "key (§6.3 — the absent-key limb REFUSES at serve; T2 sim-11)")
    assert manifest[MANIFEST_ROWS_HASH_KEY] == chained_rows_hash(rows), (
        "[ROWSHASH-VERIFIES] manifest rows-hash does not recompute over the "
        "RE-PARSED rows (A-m11)")
    epoch = manifest.get("epoch", {})
    missing = [k for k in EPOCH_KEYS if k not in epoch]
    assert not missing, f"[EPOCH] epoch missing {missing}"
    record = (Path(cache_dir) / SNAPSHOT_RECORD_FILE).read_bytes()
    assert epoch["snapshot_hash"] == sha256_hex(record), (
        "[SNAPHASH] epoch.snapshot_hash != sha256(snapshot record bytes)")
    assert epoch["wake_input_hashes"] == snap["wake_input_hashes"], "[WIH]"
    assert epoch["scope"] == snap["scope"], "[EPOCH-SCOPE]"
    assert epoch["cutoff"] == snap["cutoff"], "[EPOCH-CUTOFF]"
    assert manifest["counts"]["rows"] == len(rows), "[COUNTS]"


def assert_ceiling_respected(snap: dict, cache_dir: Path) -> None:
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    spent = sum(r["budget_units"] for r in selected_rows(read_rows(cache_dir)))
    assert spent <= ceiling, (
        f"[CEILING] selected cost {spent} exceeds the external hard ceiling "
        f"{ceiling} (§7.2: externally supplied ceilings BOUND the fold)")


def assert_n1_triple(runner, snapshot_path: Path, workdir: Path,
                     seeds=(0, 1, 4242)) -> None:
    """N1: identical combined artifact hash across 3 subprocess rebuilds under
    3 distinct PYTHONHASHSEED values from the SAME wake-snapshot (C-F3);
    delete→rebuild reproduces the hash; covers all three artifacts."""
    workdir = Path(workdir)
    hashes = {}
    for seed in seeds:
        cache = workdir / f"triple-seed{seed}"
        runner(snapshot_path, cache, hashseed=seed)
        assert_artifacts_present(cache)
        hashes[seed] = combined_artifact_hash(cache)
    assert len(set(hashes.values())) == 1, (
        f"[N1-TRIPLE] chained schedule hash diverges across PYTHONHASHSEED "
        f"seeds {seeds}: {hashes} (nondeterministic fold)")
    # delete→rebuild-from-snapshot reproduces the hash.
    import shutil
    cache = workdir / f"triple-seed{seeds[0]}"
    shutil.rmtree(cache)
    runner(snapshot_path, cache, hashseed=seeds[-1])
    assert combined_artifact_hash(cache) == hashes[seeds[-1]], (
        "[N1-REBUILD] delete→rebuild from the same snapshot did not "
        "reproduce the schedule hash")


def assert_sim1_burst(runner, snapshot_path: Path, workdir: Path) -> None:
    """sim 1: many organs ready in one wake, budget-constrained →
    deterministic selection + ceilings respected; the N1 triple holds on the
    burst fixture."""
    snap = json.loads(Path(snapshot_path).read_text("utf-8"))
    assert_n1_triple(runner, snapshot_path, Path(workdir) / "n1")
    cache = Path(workdir) / "burst"
    runner(snapshot_path, cache)
    assert_schedule_wellformed(snap, cache)
    assert_ceiling_respected(snap, cache)
    assert selected_rows(read_rows(cache)), (
        "[SIM1-NONEMPTY] burst wake with eligible work + budget selected "
        "nothing")


def assert_sim2_quiet(runner, snapshot_path: Path, workdir: Path) -> None:
    """sim 2: zero eligible work → EMPTY schedule, zero ceremony, no invented
    work (the empty rows-chain is still manifest-bound)."""
    snap = json.loads(Path(snapshot_path).read_text("utf-8"))
    assert not eligible_ops(snap), "fixture defect: quiet wake has eligible ops"
    cache = Path(workdir) / "quiet"
    runner(snapshot_path, cache)
    rows = read_rows(cache)
    assert rows == [], (
        f"[SIM2-EMPTY] quiet wake produced {len(rows)} row(s) — invented "
        f"work: {[(r['organ'], r['operation']) for r in rows]}")
    manifest = read_manifest(cache)
    assert manifest["counts"]["rows"] == 0, "[SIM2-COUNTS]"
    assert manifest[MANIFEST_ROWS_HASH_KEY] == chained_rows_hash([]), (
        "[SIM2-EMPTY-CHAIN] empty schedule must still bind the empty chain")


def assert_sim4_cost_spike(runner, snapshot_path: Path, workdir: Path) -> None:
    """sim 4: an organ whose declared cost model spikes above the ceiling is
    DEFERRED with the cost reason; affordable work still proceeds."""
    snap = json.loads(Path(snapshot_path).read_text("utf-8"))
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    spiked = {(c["organ"], c["operation"]) for c in eligible_ops(snap)
              if c["cost_units"] > ceiling}
    assert spiked, "fixture defect: no spiked-cost op in the cost-spike seed"
    cache = Path(workdir) / "spike"
    runner(snapshot_path, cache)
    rows = read_rows(cache)
    chosen = {(r["organ"], r["operation"]) for r in selected_rows(rows)}
    assert not (chosen & spiked), (
        f"[SIM4-CEILING] spiked-cost op(s) {sorted(chosen & spiked)} were "
        f"SELECTED above the ceiling {ceiling} (cost-ignoring fold)")
    deferred = {(r["organ"], r["operation"]): r["reason"]
                for r in defer_rows(rows)}
    for op in sorted(spiked):
        assert deferred.get(op) == REASON_COST_CEILING, (
            f"[SIM4-REASON] spiked op {op} not deferred with "
            f"{REASON_COST_CEILING!r}: {deferred.get(op)!r}")
    assert chosen, "[SIM4-PROCEEDS] affordable work was not selected"
    assert_ceiling_respected(snap, cache)


def run_starvation_series(runner, snap: dict, target_organ: str,
                          workdir: Path, k_max: int):
    """Multi-wake harness (sim 7): plays the runner-state carrier — writes a
    self-consistent snapshot per wake, folds, then advances the DECLARED wait
    state (failure_history[*].wakes_waiting) for eligible-but-unselected
    organs (selected organs reset). Returns (chosen_wake|None, waits_seen)."""
    snap = copy.deepcopy(snap)
    workdir = Path(workdir)
    waits_seen = []
    for wake in range(1, k_max + 1):
        refresh_sf2_hashes(snap)
        snap_path = workdir / f"wake{wake:02d}" / "snapshot-in.json"
        write_snapshot(snap, snap_path)
        cache = workdir / f"wake{wake:02d}" / "cache"
        runner(snap_path, cache)
        chosen = {r["organ"] for r in selected_rows(read_rows(cache))}
        waits_seen.append(_waiting_of(snap, target_organ))
        if target_organ in chosen:
            return wake, waits_seen
        for organ in snap["organs"]:
            name = organ["organ"]
            hist = snap["failure_history"].setdefault(
                name, {"wakes_waiting": 0, "recent_failures": []})
            if name in chosen:
                hist["wakes_waiting"] = 0
            elif any(op["trigger_due"] for op in organ.get("operations", ())):
                hist["wakes_waiting"] = int(hist.get("wakes_waiting", 0)) + 1
    return None, waits_seen


def assert_sim7_starvation(runner, snap: dict, target_organ: str,
                           workdir: Path) -> None:
    """sim 7 / N2: the seeded high-urgency organ under adversarial competing
    load is chosen within its DECLARED starvation bound (organ-declared, or
    the scheduler_policy default when absent — both snapshot inputs)."""
    bound = _bound_of(snap, target_organ)
    chosen_wake, waits = run_starvation_series(
        runner, snap, target_organ, workdir, k_max=bound + 3)
    assert chosen_wake is not None and chosen_wake <= bound, (
        f"[SIM7-BOUND] organ {target_organ!r} (declared bound {bound}) was "
        f"chosen at wake {chosen_wake} (waits seen {waits}) — starved past "
        "its declared bound (N2)")


def starvation_variants(base_snap: dict, target_organ: str):
    """The three N2 bound variants over the same adversarial fixture, proving
    the bound is a SNAPSHOT INPUT: declared 3 (base), declared 5, and absent →
    the scheduler_policy default (4). Yields (label, snap, expected_bound)."""
    declared = _bound_of(base_snap, target_organ)
    yield f"declared-{declared}", copy.deepcopy(base_snap), declared
    alt = copy.deepcopy(base_snap)
    for organ in alt["organs"]:
        if organ["organ"] == target_organ:
            organ["starvation_bound"] = declared + 2
    yield f"declared-{declared + 2}", alt, declared + 2
    dflt = copy.deepcopy(base_snap)
    for organ in dflt["organs"]:
        if organ["organ"] == target_organ:
            organ["starvation_bound"] = None
    yield ("policy-default-"
           f"{dflt['scheduler_policy']['default_starvation_bound']}"), dflt, \
        dflt["scheduler_policy"]["default_starvation_bound"]


def make_swapped_registry(snap: dict) -> dict:
    """sim-8 symmetry twin: the SAME snapshot with the organs list reversed.
    Because organ_registry_hash sorts first (§4.4), every wake-input hash is
    unchanged — only the record bytes (list order) differ."""
    twin = copy.deepcopy(snap)
    twin["organs"] = list(reversed(twin["organs"]))
    refresh_sf2_hashes(twin)
    assert twin["wake_input_hashes"] == snap["wake_input_hashes"], (
        "registry hash must be order-independent (sorted-manifests law)")
    return twin


def _conflict_view(cache_dir: Path):
    rows = read_rows(cache_dir)
    manifest = read_manifest(cache_dir)
    return rows, manifest.get("conflicts", []), manifest


def assert_sim8_contradiction(runner, snap: dict, workdir: Path) -> None:
    """sim 8: two organs proposing conflicting operations on one subject —
    BOTH surfaced, conflict recorded symmetric+sorted, never auto-resolved /
    LWW (the assemble-collision law analog)."""
    workdir = Path(workdir)
    subjects = {}
    for ctx in eligible_ops(snap):
        if ctx["subject"] is not None:
            subjects.setdefault(ctx["subject"], []).append(
                (ctx["organ"], ctx["operation"]))
    contested = {s: ops for s, ops in subjects.items()
                 if len({o for o, _ in ops}) >= 2}
    assert contested, "fixture defect: no contested subject in the seed"

    snap_a = workdir / "a" / "snapshot-in.json"
    snap_b = workdir / "b" / "snapshot-in.json"
    write_snapshot(snap, snap_a)
    write_snapshot(make_swapped_registry(snap), snap_b)
    cache_a, cache_b = workdir / "a" / "cache", workdir / "b" / "cache"
    runner(snap_a, cache_a)
    runner(snap_b, cache_b)

    for cache in (cache_a, cache_b):
        rows, conflicts, _ = _conflict_view(cache)
        emitted = {(r["organ"], r["operation"]): r for r in rows}
        recorded = {c["subject"]: c for c in conflicts}
        for subject, ops in sorted(contested.items()):
            for op in ops:
                assert op in emitted, (
                    f"[SIM8-BOTH] conflicting op {op} on {subject!r} was "
                    "DROPPED from the schedule record (auto-resolve/LWW)")
                row = emitted[op]
                assert row["decision"] == DECISION_DEFER and \
                    row["reason"] == REASON_CONFLICT_PREFIX + subject, (
                        f"[SIM8-NEVER-RESOLVED] conflicting op {op} was "
                        f"{row['decision']}/{row['reason']!r} — a conflict is "
                        "surfaced, never auto-resolved")
            assert subject in recorded, (
                f"[SIM8-RECORDED] no conflict record for {subject!r}")
            assert recorded[subject]["participants"] == sorted(
                [list(op) for op in ops]), (
                f"[SIM8-SORTED] participants for {subject!r} not "
                f"canonical-sorted: {recorded[subject]['participants']}")

    # symmetry: input registry ORDER cannot change the decision content.
    rows_a, conf_a, man_a = _conflict_view(cache_a)
    rows_b, conf_b, man_b = _conflict_view(cache_b)
    assert rows_a == rows_b, (
        "[SIM8-SYMMETRIC] decision rows differ across registry input order")
    assert conf_a == conf_b, (
        "[SIM8-SYMMETRIC] conflict records differ across registry input order")
    assert man_a["counts"] == man_b["counts"], "[SIM8-SYMMETRIC] counts differ"
    # the wake isn't poisoned: non-conflicted work still proceeds.
    assert selected_rows(rows_a), (
        "[SIM8-PROCEEDS] non-conflicted eligible work was not selected")


def prepare_sim13_sandbox(snap: dict, workdir: Path):
    """sim-13 seed: the snapshot + DECOY writable state OUTSIDE the cache —
    a scheduler policy file and an organ-registry dir. Returns (snap_path,
    cache_dir, pre_state) where pre_state fingerprints every non-cache path."""
    workdir = Path(workdir)
    snap_path = workdir / "snapshot-in.json"
    write_snapshot(snap, snap_path)
    (workdir / "scheduler-policy.json").write_bytes(canonical_bytes(
        {"scheduler_policy_version": snap["scheduler_policy_version"]}))
    registry = workdir / "organ-registry.d"
    registry.mkdir(parents=True, exist_ok=True)
    (registry / "registry.json").write_bytes(canonical_bytes(snap["organs"]))
    cache_dir = workdir / "cache"
    return snap_path, cache_dir, dir_state(workdir, exclude=cache_dir)


def dir_state(root: Path, exclude: Path) -> dict:
    root, exclude = Path(root), Path(exclude)
    state = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and exclude not in path.parents and path != exclude:
            state[str(path.relative_to(root))] = sha256_hex(path.read_bytes())
    return state


def check_sim13_cache_only(workdir: Path, cache_dir: Path, pre_state) -> None:
    post = dir_state(workdir, exclude=cache_dir)
    assert post == pre_state, (
        "[SIM13-CACHE-ONLY] the fold touched state OUTSIDE its cache_dir "
        f"(changed/new: {sorted(set(post.items()) ^ set(pre_state.items()))})"
        " — the fold writes ONLY its cache (§7.2 forbidden power 5)")


def check_sim13_policy_echo(snap: dict, cache_dir: Path) -> None:
    manifest = read_manifest(cache_dir)
    assert manifest.get("scheduler_policy_version") == \
        snap["scheduler_policy_version"], (
            "[SIM13-POLICY-ECHO] scheduler_policy_version is INPUT-ONLY: "
            f"snapshot={snap['scheduler_policy_version']} but manifest="
            f"{manifest.get('scheduler_policy_version')} (self-weight-update)")


def check_sim13_no_self_weight(snap: dict, cache_dir: Path) -> None:
    rows = read_rows(cache_dir)
    chosen = {(r["organ"], r["operation"]) for r in selected_rows(rows)}
    self_ops = {(c["organ"], c["operation"]) for c in eligible_ops(snap)
                if (c["subject"] or "").startswith("scheduler/")}
    neutral = {(c["organ"], c["operation"]) for c in eligible_ops(snap)} \
        - self_ops
    assert self_ops and neutral, "fixture defect: need self + neutral ops"
    by_op = {(c["organ"], c["operation"]): c for c in eligible_ops(snap)}
    top_neutral = max(neutral, key=lambda op: by_op[op]["urgency"])
    assert top_neutral in chosen and not (chosen & self_ops), (
        f"[SIM13-NO-SELF-WEIGHT] self-targeting op(s) {sorted(chosen & self_ops)} "
        f"outranked higher-urgency neutral work {top_neutral} — self-"
        "prioritization carries no special weight (§12 sim 13)")


def assert_sim13_self_prioritization(runner, snap: dict,
                                     workdir: Path) -> None:
    """sim 13: fold writes only its cache; self-targeting ops carry no special
    weight; the policy version is input-only."""
    snap_path, cache_dir, pre_state = prepare_sim13_sandbox(snap, workdir)
    runner(snap_path, cache_dir, cwd=Path(workdir))
    check_sim13_cache_only(workdir, cache_dir, pre_state)
    check_sim13_policy_echo(snap, cache_dir)
    check_sim13_no_self_weight(snap, cache_dir)


def assert_env_invariance(runner, snapshot_path: Path, workdir: Path) -> None:
    """A-M6 purity: the artifacts are invariant under environment changes —
    an env-reading fold REDs here."""
    workdir = Path(workdir)
    hashes = {}
    for knob in ("alpha", "beta"):
        cache = workdir / f"env-{knob}"
        runner(snapshot_path, cache, hashseed=1, extra_env={ENV_KNOB: knob})
        hashes[knob] = combined_artifact_hash(cache)
    assert hashes["alpha"] == hashes["beta"], (
        f"[PURITY-ENV] fold output depends on the process environment "
        f"({ENV_KNOB} alpha vs beta): {hashes} — the environment is not a "
        "declared snapshot input (§7.1 A-M6)")


def assert_clock_invariance(runner, snapshot_path: Path,
                            workdir: Path) -> None:
    """A-M6 purity: two sequential rebuilds (distinct wall-clock instants)
    are byte-identical — a datetime.now-reading fold REDs here."""
    workdir = Path(workdir)
    hashes = []
    for tag in ("t0", "t1"):
        cache = workdir / f"clock-{tag}"
        runner(snapshot_path, cache, hashseed=1)
        hashes.append(combined_artifact_hash(cache))
    assert hashes[0] == hashes[1], (
        "[PURITY-CLOCK] two rebuilds of the SAME snapshot differ — the fold "
        "reads the clock (datetime.now), a non-declared input (§7.1 A-M6)")


# --------------------------------------------------------------------------
# THE REAL-ARM REGISTRY — the exact batteries the guarded real-surface tests
# retire ONTO. Every arm body is exercised LIVE today (runner=reference), so
# the retirement path is itself proven before the implementation exists.
# --------------------------------------------------------------------------
def _arm_sim7(runner, workdir):
    base = load_fixture("starvation")
    for label, snap, _bound in starvation_variants(base, "ledger-audit"):
        assert_sim7_starvation(runner, snap, "ledger-audit",
                               Path(workdir) / label)


REAL_ARMS = {
    "sim1_burst": lambda runner, wd: assert_sim1_burst(
        runner, fixture_path("burst"), wd),
    "sim2_quiet": lambda runner, wd: assert_sim2_quiet(
        runner, fixture_path("quiet"), wd),
    "sim4_cost_spike": lambda runner, wd: assert_sim4_cost_spike(
        runner, fixture_path("cost-spike"), wd),
    "sim7_starvation": _arm_sim7,
    "sim8_contradiction": lambda runner, wd: assert_sim8_contradiction(
        runner, load_fixture("contradiction"), wd),
    "sim13_self_prioritization": lambda runner, wd:
        assert_sim13_self_prioritization(
            runner, load_fixture("self-prioritization"), wd),
    "purity_env": lambda runner, wd: assert_env_invariance(
        runner, fixture_path("burst"), wd),
    "purity_clock": lambda runner, wd: assert_clock_invariance(
        runner, fixture_path("burst"), wd),
    "n1_determinism": lambda runner, wd: assert_n1_triple(
        runner, fixture_path("burst"), wd),
}


def run_real_arm(name: str, workdir: Path, runner=None, repo: Path = None):
    """Run one arm battery. runner=None ⇒ the REAL surface (the retirement
    call: `run_real_arm(name, tmp_path, repo=_REPO)`)."""
    if runner is None:
        assert repo is not None, "repo required to build the real runner"
        runner = real_runner(repo)
    REAL_ARMS[name](runner, Path(workdir))
