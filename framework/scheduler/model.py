"""framework.scheduler.model — the schedule-store records + corpus-pinned
vocabulary (COG-4 §7.1/§7.2/§6.3; the W2 fold corpus is the executable spec —
cabinet/scripts/tests/lib_cog4_corpus.py pins every name, shape and hash this
module implements; the implementation binds to THOSE names).

Warranted as a module (the "+model.py only if records genuinely warrant"
clause): snapshot, fold and serve all share this vocabulary — the snapshot
schema, the decision-row tuple, the manifest envelope keys, and the store hash
algebra — and holding it once here is what keeps the three surfaces free of
duplicate pinned constants (§13).

CANONICAL-BYTES DIALECT (deliberate, documented): the schedule store uses the
CORPUS-pinned ASCII canonical dialect — json.dumps(sort_keys, compact,
ensure_ascii=True) — NOT the kernel's recorder dialect (ensure_ascii=False,
framework/projection/kernel.py). The corpus batteries re-derive the manifest
rows-hash over the RE-PARSED rows with THEIR encoder ([ROWSHASH-VERIFIES]), so
the store's algebra is corpus law; the two dialects coincide on pure-ASCII
content and the schedule rows are canonically emitted, but the pinned dialect
is the corpus's. Likewise the rows-hash chains rows in FILE ORDER (the corpus
§6.1(c) pin) — NOT the kernel's sorted-by-order-key parameterization — so a
REORDERED-but-content-identical store still refuses at serve (the fold emits
rows in canonical tie-break order; file order IS the canonical order for an
honest store, and any deviation is a tamper).

Kernel bindings (§6.3 — the strict shapes): the cutoff validator is the
kernel's ((g), one definition); atomic writes ride kernel.atomic_write ((e));
the verified single-read serve rides kernel.verified_single_read ((f), in
serve.py). Domain law stays here (§6.2).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u2.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from framework.projection.kernel import atomic_write, require_canonical_cutoff

# --------------------------------------------------------------------------
# corpus-pinned vocabulary (lib_cog4_corpus.py is the spec for every name)
# --------------------------------------------------------------------------
SNAPSHOT_SCHEMA_VERSION = "cog4-wake-snapshot/v1"
MANIFEST_SCHEMA_VERSION = "cog4-schedule-manifest/v1"
SCHEDULER_VERSION = "cog4-scheduler/1"          # epoch.scheduler_version

SNAPSHOT_RECORD_FILE = "snapshot.json"
SCHEDULE_FILE = "schedule.jsonl"
MANIFEST_FILE = "schedule-manifest.json"
ARTIFACT_FILES = (SNAPSHOT_RECORD_FILE, SCHEDULE_FILE, MANIFEST_FILE)

# §7.5: the O_EXCL writer lock serializing builders per cache_dir (fold.py).
LOCK_FILE = "schedule.lock"

# §6.3: the rows-hash limb is MANDATORY-PRESENT in the schedule manifest.
MANIFEST_ROWS_HASH_KEY = "schedule_rows_hash"
CHAIN_SEED = b"cog4-schedule/v1"

# the seven §7.1 wake-input hashes (SF2 families marked by their family map).
WAKE_INPUT_HASH_KEYS = (
    "cortex_belief_store_hash",
    "objectives_graph_rows_hash",
    "organ_registry_hash",
    "services_manifest_hash",
    "organ_health_hash",
    "failure_history_hash",
    "capability_availability_hash",
)
SF2_SELF_CONSISTENT = {
    "organ_health_hash": "organ_health",
    "failure_history_hash": "failure_history",
    "capability_availability_hash": "capability_availability",
}

DECISION_SELECT = "select"
DECISION_DEFER = "defer"
DECISIONS = (DECISION_SELECT, DECISION_DEFER)
REASON_SELECTED = "selected"
REASON_BUDGET_EXHAUSTED = "budget_exhausted"
REASON_COST_CEILING = "cost_exceeds_ceiling"
REASON_CONFLICT_PREFIX = "conflict:"

ROW_FIELDS = ("organ", "operation", "subject", "descriptor", "decision",
              "reason", "budget_units", "deps", "tie_break_key")
EPOCH_KEYS = ("scheduler_version", "snapshot_hash", "wake_input_hashes",
              "scope", "cutoff")

# §4.2 namespaced operation id (the `/` separator keeps the flat central
# ACTION_TYPES vocabulary structurally un-collidable).
OP_ID_RE = re.compile(r"^[a-z0-9_-]+/[a-z0-9._-]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class SnapshotError(ValueError):
    """A wake-snapshot that violates the §7.1 declared-input schema — a hard
    error, never a silent skip (denial never masquerades as empty success)."""


# --------------------------------------------------------------------------
# canonical bytes + hashing (the corpus-pinned schedule-store dialect)
# --------------------------------------------------------------------------
def canonical_bytes(value: Any) -> bytes:
    """ASCII canonical JSON bytes — the corpus dialect (see module doc)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def family_hash(obj: Any) -> str:
    """Hash of one declared snapshot input family (canonical bytes)."""
    return sha256_hex(canonical_bytes(obj))


def organ_registry_hash(organs: list) -> str:
    """§4.4 sorted-manifests law: canonical bytes over organs SORTED by name —
    order-independent, so a registry listed in any order hashes identically."""
    return family_hash(sorted(organs, key=lambda o: o["organ"]))


def schedule_rows_hash(rows: Iterable[Any]) -> str:
    """The corpus-pinned §6.1(c) chain for the schedule store: h0 =
    sha256(CHAIN_SEED); per row IN FILE ORDER h_i = sha256(h_{i-1}.digest +
    canonical_bytes(row)); hex of the final digest. Zero rows => the seeded
    empty chain (still a mandatory manifest value — sim 2)."""
    acc = hashlib.sha256(CHAIN_SEED)
    for row in rows:
        acc = hashlib.sha256(acc.digest() + canonical_bytes(row))
    return acc.hexdigest()


def tie_break_key(organ: str, operation: str) -> str:
    """§7.2: tie-breaks total-ordered by canonical bytes of the identity."""
    return canonical_bytes([organ, operation]).decode("ascii")


# --------------------------------------------------------------------------
# snapshot validation + atomic write
# --------------------------------------------------------------------------
def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SnapshotError(message)


def validate_snapshot(snap: dict) -> None:
    """§7.1 hard-error schema gate over a wake snapshot — the corpus
    validate_snapshot mirrored as framework law (every check identical; the
    error type is the scheduler's SnapshotError). SF2 family hashes and the
    registry hash must RECOMPUTE from the snapshot's own data — fixture or
    ledger drift can never be silent."""
    _require(isinstance(snap, dict), "snapshot is not an object")
    _require(snap.get("schema_version") == SNAPSHOT_SCHEMA_VERSION,
             f"schema_version {snap.get('schema_version')!r} != "
             f"{SNAPSHOT_SCHEMA_VERSION!r}")
    _require(isinstance(snap.get("scope"), str) and bool(snap["scope"]),
             "scope must be a non-empty string")
    require_canonical_cutoff(snap.get("cutoff"), refuse=SnapshotError)
    wih = snap.get("wake_input_hashes")
    _require(isinstance(wih, dict) and set(wih) == set(WAKE_INPUT_HASH_KEYS),
             f"wake_input_hashes keys {sorted(wih or ())} != the §7.1 set")
    for key, val in wih.items():
        _require(isinstance(val, str) and bool(_HEX64_RE.fullmatch(val)),
                 f"wake input hash {key} is not a 64-hex digest")
    for key in ("budget_version", "posture_version", "trust_table_version",
                "scheduler_policy_version"):
        _require(isinstance(snap.get(key), int), f"{key} must be an int")
    _require(isinstance(snap.get("objectives_epoch"), dict),
             "objectives_epoch must be an object (the declared epoch echo)")
    _require(isinstance(snap.get("scheduler_policy", {})
                        .get("default_starvation_bound"), int),
             "scheduler_policy.default_starvation_bound must be an int")
    _require(isinstance(snap.get("budget", {})
                        .get("ceiling_units_per_wake"), int),
             "budget.ceiling_units_per_wake must be an int")
    organs = snap.get("organs")
    _require(isinstance(organs, list), "organs must be a list")
    names = [o["organ"] for o in organs]
    _require(len(names) == len(set(names)), "duplicate organ names")
    for organ in organs:
        bound = organ.get("starvation_bound")
        _require(bound is None or (isinstance(bound, int) and bound >= 1),
                 f"organ {organ.get('organ')!r} starvation_bound must be null "
                 "or an int >= 1")
        for op in organ.get("operations", ()):
            _require(bool(OP_ID_RE.fullmatch(op.get("operation", ""))),
                     f"non-namespaced operation id {op.get('operation')!r} "
                     "(§4.2)")
            _require(op.get("subject") is None
                     or isinstance(op["subject"], str),
                     f"operation {op['operation']} subject must be null|str")
            _require(isinstance(op.get("urgency"), int),
                     f"operation {op['operation']} urgency must be an int")
            _require(isinstance(op.get("cost_units"), int),
                     f"operation {op['operation']} cost_units must be an int")
            _require(isinstance(op.get("trigger_due"), bool),
                     f"operation {op['operation']} trigger_due must be a bool")
            _require(isinstance(op.get("deps"), dict),
                     f"operation {op['operation']} deps must be an object")
            _require(isinstance(op.get("descriptor"), dict),
                     f"operation {op['operation']} descriptor must be an "
                     "object")
    for fam in SF2_SELF_CONSISTENT.values():
        _require(isinstance(snap.get(fam), dict),
                 f"SF2 family {fam} must be an object")
    for hash_key, fam in SF2_SELF_CONSISTENT.items():
        _require(wih[hash_key] == family_hash(snap[fam]),
                 f"{hash_key} does not recompute from snapshot {fam!r} data")
    _require(wih["organ_registry_hash"] == organ_registry_hash(organs),
             "organ_registry_hash does not recompute from the snapshot "
             "registry")


def write_snapshot(snap: dict, path) -> str:
    """Validate + atomically write the canonical snapshot bytes (kernel (e));
    return their sha256 — the record hash the fold's epoch will bind."""
    validate_snapshot(snap)
    data = canonical_bytes(snap)
    atomic_write(Path(path), data.decode("ascii"))
    return sha256_hex(data)
