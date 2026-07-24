"""framework.scheduler.snapshot — the versioned wake-snapshot builder (COG-4
§7.1/§2.1). EVERY input is a DECLARED parameter — paths, ledgers, versions,
scope and cutoff are all caller-injected (the CLIs own defaults, §4.4 layer
law: NO instance literal lives in this tree) — and the builder reads NOTHING
undeclared: no env, no clock, no randomness. Same inputs => byte-identical
snapshot (the record is canonical bytes; model.write_snapshot hashes them).

Input bindings (§2.1, the strict shapes — §6.3):
  * cortex — the `load_beliefs_verified`-BOUND manifest read: the verified
    single-read load must SUCCEED (it re-derives the store hash and binds it
    to fold-manifest.json's belief_store_hash) BEFORE that manifest value is
    recorded as the `cortex_belief_store_hash` wake input. A corrupt or
    absent store refuses (SnapshotError) — never an invented hash.
  * objectives — the PUBLIC serve surface ONLY (`serve_graph`; never a direct
    graph.jsonl read): the served manifest's `graph_rows_hash` + the epoch
    echo. A manifest carrying NO rows-hash refuses here — the objectives
    `is not None and` skip-hole does not propagate into this surface (§6.3).
  * services manifest — sha256 of the declared file's bytes.
  * organ registry — the declared organ list, hashed order-independently
    (sorted-manifests law, §4.4); per-organ starvation bounds ride it and
    surface as explicit snapshot rows (SF2/N2).
  * SF2 families — organ health, failure history (incl. the declared
    wakes_waiting wait state) and capability/MCP availability: declared
    ledger dicts, hashed; ABSENCE IS RECORDED HONESTLY by the caller passing
    the empty ledger it actually found — this builder never invents entries.

Missing/corrupt INPUTS fail loud here (no snapshot is built); missing/corrupt
snapshot or SCHEDULE state at dispatch time means the fixed safe schedule and
never permission (§7.4 — the dispatcher's law, not this builder's).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u2.
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.cortex.query import StoreCorruptError, load_beliefs_verified
from framework.objectives.query import ServeRefused, serve_graph
from framework.projection.kernel import require_canonical_cutoff
from framework.scheduler import model


def _cortex_belief_store_hash(cortex_cache_dir: Path) -> str:
    """The load_beliefs_verified-BOUND manifest read (§2.1): verify the store
    first (single read, hash bound to the manifest), then record the
    manifest's belief_store_hash as the wake input."""
    try:
        load_beliefs_verified(cortex_cache_dir)       # C-F15 bound read
    except StoreCorruptError as exc:
        raise model.SnapshotError(
            f"cortex store refused its verified read — {exc}") from None
    try:
        manifest = json.loads(
            (cortex_cache_dir / "fold-manifest.json").read_text(
                encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise model.SnapshotError(
            "cortex fold-manifest unreadable after a verified load — "
            f"{type(exc).__name__}") from None
    value = manifest.get("belief_store_hash") if isinstance(manifest, dict) \
        else None
    if not isinstance(value, str) or not value:
        raise model.SnapshotError(
            "cortex fold-manifest carries no belief_store_hash — refuse to "
            "record an invented wake input")
    return value


def _objectives_inputs(objectives_cache_dir: Path) -> tuple[str, dict]:
    """The serve-surface objectives read (§2.1): graph_rows_hash + the epoch
    echo, via serve_graph ONLY."""
    try:
        served = serve_graph(objectives_cache_dir)
    except ServeRefused as exc:
        raise model.SnapshotError(
            f"objectives serve refused — {exc}") from None
    except (OSError, ValueError) as exc:
        raise model.SnapshotError(
            "objectives store unreadable via the serve surface — "
            f"{type(exc).__name__}") from None
    manifest = served.get("manifest") or {}
    rows_hash = manifest.get("graph_rows_hash")
    if not isinstance(rows_hash, str) or not rows_hash:
        raise model.SnapshotError(
            "objectives graph-manifest carries no graph_rows_hash — the "
            "absent-key hole does not propagate into the snapshot (§6.3)")
    epoch = served.get("epoch")
    if not isinstance(epoch, dict):
        raise model.SnapshotError("objectives serve returned no epoch echo")
    return rows_hash, epoch


def build_snapshot(*, cortex_cache_dir, objectives_cache_dir,
                   services_manifest_path, organ_registry, organ_health,
                   failure_history, capability_availability,
                   budget_ceiling_units_per_wake, default_starvation_bound,
                   budget_version, posture_version, trust_table_version,
                   scheduler_policy_version, scope, cutoff) -> dict:
    """Assemble + validate one wake snapshot from DECLARED inputs (§7.1).
    Returns the snapshot dict (model.validate_snapshot-clean); the caller
    persists it via model.write_snapshot (atomic, canonical bytes)."""
    require_canonical_cutoff(cutoff, refuse=model.SnapshotError)
    if not isinstance(scope, str) or not scope:
        raise model.SnapshotError("scope must be a non-empty string")
    for name, value in (("organ_health", organ_health),
                        ("failure_history", failure_history),
                        ("capability_availability", capability_availability)):
        if not isinstance(value, dict):
            raise model.SnapshotError(
                f"SF2 family {name} must be a dict (pass the empty ledger "
                "you actually found — honest absence, never invention)")
    if not isinstance(organ_registry, list):
        raise model.SnapshotError("organ_registry must be a list of organ "
                                  "manifest excerpts")

    services_path = Path(services_manifest_path)
    try:
        services_hash = model.sha256_hex(services_path.read_bytes())
    except OSError as exc:
        raise model.SnapshotError(
            f"services manifest unreadable at {services_path} — "
            f"{type(exc).__name__}") from None

    objectives_rows_hash, objectives_epoch = _objectives_inputs(
        Path(objectives_cache_dir))

    snap = {
        "schema_version": model.SNAPSHOT_SCHEMA_VERSION,
        "scope": scope,
        "cutoff": cutoff,
        "wake_input_hashes": {
            "cortex_belief_store_hash":
                _cortex_belief_store_hash(Path(cortex_cache_dir)),
            "objectives_graph_rows_hash": objectives_rows_hash,
            "organ_registry_hash": model.organ_registry_hash(organ_registry),
            "services_manifest_hash": services_hash,
            "organ_health_hash": model.family_hash(organ_health),
            "failure_history_hash": model.family_hash(failure_history),
            "capability_availability_hash":
                model.family_hash(capability_availability),
        },
        "objectives_epoch": objectives_epoch,
        "budget_version": budget_version,
        "posture_version": posture_version,
        "trust_table_version": trust_table_version,
        "scheduler_policy_version": scheduler_policy_version,
        "scheduler_policy": {
            "default_starvation_bound": default_starvation_bound,
        },
        "budget": {
            "ceiling_units_per_wake": budget_ceiling_units_per_wake,
        },
        "organs": organ_registry,
        "organ_health": organ_health,
        "failure_history": failure_history,
        "capability_availability": capability_availability,
    }
    model.validate_snapshot(snap)                     # the §7.1 hard gate
    return snap
