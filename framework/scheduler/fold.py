"""framework.scheduler.fold — the pure planner (COG-4 §7.2; the W2 fold corpus
is the executable spec — every law below is battery-pinned by
cabinet/scripts/tests/test_cog4_sim_fold.py via lib_cog4_corpus.run_real_arm).

`build_schedule(snapshot_path, cache_dir)` is a PURE FUNCTION of the snapshot
file: no env, no clock, no randomness (A-M6 — the purity batteries rebuild
under varied PYTHONHASHSEED and environments and demand byte-identical
artifacts), and it writes ONLY under cache_dir (sim 13 [SIM13-CACHE-ONLY]).
Decision inputs (charter §4.5 L116) all ride the snapshot: urgency, declared
cost model, dependency readiness, failure history (the declared wakes_waiting
wait state), starvation bounds (organ-declared or the scheduler_policy
default — both SNAPSHOT INPUTS, never planner-invented, N2), and the external
hard budget ceiling that BOUNDS the fold (sims 1/4).

Fold laws (each with a biting corpus mutant):
  * exactly ONE select|defer row per eligible (organ, operation), emitted in
    canonical tie_break_key order ([ROW-UNIQUE], sim-1 N1 triple);
  * rows carry the snapshot's DECLARED cost model ([ROW-COST-DECLARED]) and
    the manifest budget sums the SELECTED rows' declared costs
    ([BUDGET-DECLARED]) — never fold-invented costs;
  * zero eligible work => an EMPTY schedule, zero ceremony (sim 2) — the empty
    rows-chain is still a mandatory manifest value;
  * a declared cost above the ceiling defers with the cost reason; affordable
    work proceeds (sim 4);
  * starvation-critical operations (declared wait + 1 >= declared bound)
    promote ahead of pure urgency (sim 7 / N2);
  * two organs proposing operations on ONE subject is a CONFLICT: both
    surface as defer rows, the record is symmetric + sorted, never
    auto-resolved/LWW (sim 8);
  * subjects are OPAQUE (a self-targeting operation gets no special weight),
    the policy version is echoed INPUT-ONLY, and the fold writes only its
    cache (sim 13 — the six forbidden powers, §7.2).

Store discipline via the kernel (§6.3): every artifact is written with
kernel.atomic_write (O_EXCL tmp + fsync + os.replace); the manifest is built
through kernel.manifest_envelope so it can never exist without its MANDATORY
rows-hash; and all writers to one cache_dir are serialized by an O_EXCL
lockfile (§7.5) — the loser fails LOUD (ScheduleLockHeld), never corrupts, and
the atomic replace means a reader can never observe a partial artifact even
mid-rewrite.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u2.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from framework.projection.kernel import atomic_write, manifest_envelope
from framework.scheduler import model


class ScheduleLockHeld(RuntimeError):
    """Another writer holds the cache_dir lock (§7.5) — this builder LOSES
    LOUDLY. The store is untouched; retry after the winner finishes, or delete
    the cache (the rollback grammar) if a crashed writer left the lock."""


# --------------------------------------------------------------------------
# eligibility + the pure fold (snapshot-only inputs)
# --------------------------------------------------------------------------
def _eligible_ops(snap: dict) -> list:
    """Flatten eligible (organ, operation) contexts: trigger_due AND organ
    health pass AND every capability dep available AND every organ dep present
    + healthy (sims 5/6/9 exercise the failure arms on their own fixtures)."""
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
                "tie_break_key": model.tie_break_key(organ["organ"],
                                                     op["operation"]),
            })
    return out


def _bound_of(snap: dict, organ_name: str) -> int:
    """The declared starvation bound: the organ's own when declared, else the
    scheduler_policy default — BOTH snapshot inputs (SF2/N2)."""
    for organ in snap["organs"]:
        if organ["organ"] == organ_name:
            bound = organ.get("starvation_bound")
            if isinstance(bound, int):
                return bound
    return snap["scheduler_policy"]["default_starvation_bound"]


def _waiting_of(snap: dict, organ_name: str) -> int:
    """The DECLARED wait state (failure_history[*].wakes_waiting) — a snapshot
    input the state carrier re-declares per wake, never a planner memory."""
    return int(snap.get("failure_history", {})
               .get(organ_name, {}).get("wakes_waiting", 0))


def _row(ctx: dict, decision: str, reason: str) -> dict:
    return {
        "organ": ctx["organ"], "operation": ctx["operation"],
        "subject": ctx["subject"], "descriptor": ctx["descriptor"],
        "decision": decision, "reason": reason,
        "budget_units": ctx["cost_units"],       # the DECLARED cost, verbatim
        "deps": ctx["deps"],
        "tie_break_key": ctx["tie_break_key"],
    }


def _fold(snap: dict, snapshot_hash: str) -> tuple[list, dict]:
    """The pure §7.2 fold: validated snapshot -> (rows, manifest)."""
    ceiling = snap["budget"]["ceiling_units_per_wake"]
    pool = _eligible_ops(snap)

    # sim-8: subjects claimed by >= 2 distinct organs conflict — BOTH surface
    # as defer rows; the record is symmetric (input-order-free) + sorted.
    by_subject: dict = {}
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
            rows.append(_row(ctx, model.DECISION_DEFER,
                             model.REASON_CONFLICT_PREFIX + ctx["subject"]))

    # sim-7/N2: starvation-critical ops promote ahead of pure urgency; every
    # tie total-ordered by canonical bytes (N1 determinism).
    contenders = [c for c in pool if c["tie_break_key"] not in conflicted_ids]

    def _key(ctx):
        critical = (_waiting_of(snap, ctx["organ"]) + 1
                    >= _bound_of(snap, ctx["organ"]))
        return (0 if critical else 1, -ctx["urgency"], ctx["tie_break_key"])

    remaining = ceiling
    for ctx in sorted(contenders, key=_key):
        if ctx["cost_units"] > ceiling:
            rows.append(_row(ctx, model.DECISION_DEFER,
                             model.REASON_COST_CEILING))
        elif ctx["cost_units"] <= remaining:
            rows.append(_row(ctx, model.DECISION_SELECT,
                             model.REASON_SELECTED))
            remaining -= ctx["cost_units"]
        else:
            rows.append(_row(ctx, model.DECISION_DEFER,
                             model.REASON_BUDGET_EXHAUSTED))

    rows.sort(key=lambda r: r["tie_break_key"])
    selected = sum(1 for r in rows if r["decision"] == model.DECISION_SELECT)
    manifest = manifest_envelope(
        schema_version=model.MANIFEST_SCHEMA_VERSION,
        epoch={
            "scheduler_version": model.SCHEDULER_VERSION,
            "snapshot_hash": snapshot_hash,
            "wake_input_hashes": snap["wake_input_hashes"],
            "scope": snap["scope"],
            "cutoff": snap["cutoff"],
        },
        store_hash_key=model.MANIFEST_ROWS_HASH_KEY,
        store_hash=model.schedule_rows_hash(rows),
        extra={
            "counts": {"rows": len(rows), "selected": selected,
                       "deferred": len(rows) - selected,
                       "conflicts": len(conflicts)},
            "conflicts": conflicts,
            # sim-13: INPUT-ONLY echo — the fold cannot mutate its own policy.
            "scheduler_policy_version": snap["scheduler_policy_version"],
            "budget": {"ceiling_units_per_wake": ceiling,
                       "selected_units": ceiling - remaining},
        },
    )
    return rows, manifest


# --------------------------------------------------------------------------
# the §7.5 writer lock + the store write (cache_dir ONLY)
# --------------------------------------------------------------------------
def _acquire_lock(cache_dir: Path) -> Path:
    """O_EXCL writer lock per cache_dir (§7.5). The loser fails LOUD — never
    waits, never steals, never corrupts. A crash leaves the lockfile behind by
    design: the next writer fails loudly instead of racing debris, and the
    rollback grammar (delete the cache, rebuild from the snapshot) recovers."""
    lock = cache_dir / model.LOCK_FILE
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ScheduleLockHeld(
            f"schedule writer lock held: {lock} exists — another builder owns "
            "this cache_dir (§7.5); losers fail loud, never race. Retry after "
            "it finishes, or delete the cache to recover from a crashed "
            "writer (rollback grammar).") from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return lock


def build_schedule(snapshot_path, cache_dir) -> dict:
    """The §7.2 entry point: snapshot file -> the three schedule artifacts
    under cache_dir (snapshot.json record + schedule.jsonl + the manifest).
    Pure in its inputs; serialized per cache_dir; atomic per artifact. Returns
    the manifest (already bound to the rows it hashed)."""
    snapshot_path, cache_dir = Path(snapshot_path), Path(cache_dir)
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    model.validate_snapshot(snap)                     # §7.1 hard-error gate
    record = model.canonical_bytes(snap)
    snapshot_hash = model.sha256_hex(record)
    rows, manifest = _fold(snap, snapshot_hash)

    cache_dir.mkdir(parents=True, exist_ok=True)
    lock = _acquire_lock(cache_dir)
    try:
        atomic_write(cache_dir / model.SNAPSHOT_RECORD_FILE,
                     record.decode("ascii"))
        atomic_write(cache_dir / model.SCHEDULE_FILE,
                     "".join(model.canonical_bytes(r).decode("ascii") + "\n"
                             for r in rows))
        atomic_write(cache_dir / model.MANIFEST_FILE,
                     model.canonical_bytes(manifest).decode("ascii"))
    finally:
        lock.unlink(missing_ok=True)
    return manifest
