"""lib_cog5_corpus.py — the COG-5 W2 CROSS-UNIT SHARED CORE (T1-owned).

OWNERSHIP (the W2 naming law, contract §13): this file is authored and owned
by the W2 T1 unit (ARCHIVE/LINEAGE family). It is the ONE cross-unit surface
of the three parallel W2 corpus units: T2 (`lib_cog5_scoring*`) and T3
(`lib_cog5_boundary*`) IMPORT it under guards they wrote before it landed,
and neither ever creates or edits it. T1 additionally owns
`lib_cog5_archive*`; the three units never collide on a file.

WHY A SHARED CORE AT ALL: three vocabularies are genuinely cross-unit and a
silent fork of any of them is a defect the integrator would have to chase —
so they are written ONCE, here:

  1. the §6.2 `provenance` CLOSED enum {real_live, real_mined, synthetic,
     sim_replay} + the chain-of-custody stamp/count predicates,
  2. the §5.3 record_kind FIELD MAP — shadow {run, decision} lands in an
     archive-native `shadow_record_kind`; it NEVER populates trajectory
     `record_kind` (enum ["live","public_benchmark"],
     framework/schemas/cognitive-trajectory.v2.schema.json:32). The two
     vocabularies are disjoint and conflation is a mutant,
  3. the recorder-dialect canonical bytes + digest (a STDLIB REPLICA, never
     an import — §5.1/§5.2) and the archive record shape built on them.

PURE STDLIB, DELIBERATELY (a mergeability law, not a preference): T2's guard
is `except ModuleNotFoundError` — if THIS module raised ModuleNotFoundError
from an import of its own, T2 would silently bind `CORE = None` and its
companion absence assertion would RED with a misleading message. A pure
stdlib module cannot fail that way. Every framework binding this family needs
lives in `lib_cog5_archive_fixtures.py` / the test modules, never here.

BOUNDARY DISCIPLINE (why the kernel is REPLICATED, not imported): boundary
row 6 (`cabinet/config/boundary-manifest.yml`) allowlists the projection
kernel to cortex/objectives/scheduler internals, their CLIs, and the
`test_cog4_*`/`lib_cog4_*` test globs — the cog5 globs are DELIBERATELY
absent (contract §10, "deliberate ROW-6 non-extension"). So this core
replicates the recorder dialect in stdlib and carries its own parity
tripwire, which reads the kernel's function body from FILE BYTES (AST) and
never imports it — the COG-4 organs-registry replica precedent
(framework/organs/registry.py:24-29), named in the contract §5.2 as the
chosen path (rev-1 SF-4).

The §5.4 archive record shape and the append-chain PHYSICS (O_APPEND +
fsync + dir-fsync, prev_hash/sequence, anchors, pending.json heal, sealed
segments) live in `lib_cog5_archive_fixtures.py`; this core owns only the
record's VOCABULARY + identity helpers so T2/T3 can speak them too.

Synthetic corpora are sanctioned for plumbing + mutants (§8.1/§12); what
synthetic may NEVER do is open the league or ground a live-fitness claim —
`count_toward_minimums()` is the mechanical form of that law.

S0: interpreter python3.12; no DB, no network, no clock reads (every
timestamp in this family is a declared parameter).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 contract §12/§13, W2 T1).
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

# ===========================================================================
# (1) the §6.2 provenance vocabulary — the CLOSED enum, written once
# ===========================================================================
# THREE NAMES, ONE VALUE — deliberate. T3's cross-unit probe
# (`test_cog5_sim_boundary.py::TestSharedCorpusIntegration`) walks the names
# ("PROVENANCE", "LIB_COG5_CORPUS_PROVENANCE", "PROVENANCE_ENUM") and asserts
# the FIRST one it finds equals its own copy of the enum. Exposing all three
# with identical content means the probe binds whichever name the integrator
# later standardises on, and can never bind a stale alias.
PROVENANCE: tuple[str, ...] = ("real_live", "real_mined", "synthetic", "sim_replay")
LIB_COG5_CORPUS_PROVENANCE: tuple[str, ...] = PROVENANCE
PROVENANCE_ENUM: frozenset[str] = frozenset(PROVENANCE)

#: Only these two count toward any §6.2 league-opening minimum.
REAL_PROVENANCE: frozenset[str] = frozenset({"real_live", "real_mined"})

#: The NAMED real source classes (§5.3/§6.2 chain of custody). A `real_*`
#: provenance claimed by a row whose source class is not in here is
#: LAUNDERING.
SOURCE_CLASS_TO_PROVENANCE: dict[str, str] = {
    # (b) the already-real, cutoff-disciplined sources E2 mines
    "consequence_ledger": "real_mined",
    "fidelity_receipts": "real_mined",
    "instance_corpus": "real_mined",
    "verdict_inbox": "real_mined",
    # (a) the v2 emitter this phase builds
    "live_emission": "real_live",
    # generator/arena/sim outputs — never countable
    "generator": "synthetic",
    "arena": "synthetic",
    "sim": "sim_replay",
}

# RECORDED CROSS-UNIT DIVERGENCE (routed to the integrator, never papered
# over): T2 and T3 independently slugged two source classes differently —
# T2 spells the verdict-inbox class `verdict_inbox_labels` and the sim class
# `sim_replay`; T3 spells them `verdict_inbox` and `sim`. The contract §6.2
# names the sources in PROSE ("verdict-inbox labels", "sim") and pins only
# the PROVENANCE enum, which both units already agree on — so this is an
# un-pinned slug, not a semantic fork. The core canonicalises on the shorter
# instrument-shaped slugs and accepts both spellings so neither sibling
# breaks at the join. THIS ALIAS TABLE IS DEBT: when the integrator pins one
# spelling, the table dies and the losing spelling becomes an error.
SOURCE_CLASS_ALIASES: dict[str, str] = {
    "verdict_inbox_labels": "verdict_inbox",   # T2's spelling
    "sim_replay": "sim",                       # T2's spelling (a provenance
                                               # token reused as a source slug)
}

#: The source classes whose rows may ever count toward a §6.2 minimum.
NAMED_REAL_SOURCES: frozenset[str] = frozenset(
    name for name, prov in SOURCE_CLASS_TO_PROVENANCE.items()
    if prov in REAL_PROVENANCE
)

#: §6.3: every league/foundry output while the league is CLOSED carries this.
FITNESS_CLAIM_NONE = "none"

# The §6.2 recorded minimums (pinned identically by T2; duplicated here only
# so a single-unit tree still speaks them — the estate-constant drift
# tripwires that bind them to the shipped bytes live in T2's family).
MIN_REAL_TRAJECTORIES_PER_STRATUM = 10   # MIN_PAIRS (judge_calibration.py:92-94)
MIN_CAPTAIN_LABELS_PER_STRATUM = 10      # the same logic on the human channel
JUDGE_AGREEMENT_BAR = 0.80               # JUDGE_HARD_BAR
JUDGE_MIN_PAIRS = 10


def canonical_source_class(source_class: str) -> str:
    """Fold a sibling's spelling onto the canonical slug (see the recorded
    divergence above). Unknown classes pass through unchanged so the caller —
    not this helper — decides to refuse."""
    return SOURCE_CLASS_ALIASES.get(source_class, source_class)


def stamp_provenance(row: Mapping[str, Any], source_class: str) -> dict[str, Any]:
    """CHAIN OF CUSTODY (§6.2): `provenance` is stamped by the INGESTER from
    the source class. Any `provenance` a candidate/generator/league wrote on
    the row is OVERWRITTEN unconditionally — candidate code can never set or
    rewrite it (the §5.2 no-candidate-write-path WALL covers the field).

    An unknown source class raises — a row whose custody cannot be
    established is never ingested with a guessed provenance.
    """
    canonical = canonical_source_class(source_class)
    if canonical not in SOURCE_CLASS_TO_PROVENANCE:
        raise ValueError(
            f"unknown source class {source_class!r} — provenance cannot be "
            f"stamped; known: {sorted(SOURCE_CLASS_TO_PROVENANCE)}")
    stamped = dict(row)
    stamped["source_class"] = canonical
    stamped["provenance"] = SOURCE_CLASS_TO_PROVENANCE[canonical]
    return stamped


def provenance_violations(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Ingestion refusals + laundering findings, in row order.

    A row with missing / out-of-enum provenance REFUSES ingestion (§6.2) and
    never counts; a row claiming `real_*` from a non-real source class is
    LAUNDERING and is reported as such.
    """
    findings: list[str] = []
    for index, row in enumerate(rows):
        prov = row.get("provenance")
        if prov not in PROVENANCE_ENUM:
            findings.append(
                f"row {index}: provenance {prov!r} outside the closed enum "
                f"{PROVENANCE} — REFUSE ingestion")
            continue
        if prov in REAL_PROVENANCE:
            src = canonical_source_class(str(row.get("source_class")))
            if src not in NAMED_REAL_SOURCES:
                findings.append(
                    f"row {index}: LAUNDERING — provenance {prov!r} claimed "
                    f"from non-real source class {row.get('source_class')!r}")
    return findings


def count_toward_minimums(rows: Iterable[Mapping[str, Any]]) -> int:
    """The §6.2 counting predicate: ONLY `real_live`/`real_mined` rows
    ingested from the NAMED real sources count toward any league-opening
    minimum. Synthetic and sim_replay rows count ZERO, always — this is the
    mechanical form of "synthetic may never open the league"."""
    total = 0
    for row in rows:
        if (row.get("provenance") in REAL_PROVENANCE
                and canonical_source_class(str(row.get("source_class")))
                in NAMED_REAL_SOURCES):
            total += 1
    return total


# ===========================================================================
# (2) the §5.3 record_kind FIELD MAP — two disjoint vocabularies
# ===========================================================================
#: framework/schemas/cognitive-trajectory{,.v2}.schema.json:32 — the trajectory
#: enum. The archive NEVER writes a shadow token into this field.
TRAJECTORY_RECORD_KIND: tuple[str, ...] = ("live", "public_benchmark")
TRAJECTORY_RECORD_KIND_FIELD = "record_kind"

#: cabinet/scripts/cog4-dispatch-shadow.py:847/:871/:875 — the shadow log's
#: own vocabulary, which lands in an archive-native field of its own.
SHADOW_RECORD_KIND: tuple[str, ...] = ("run", "decision")
SHADOW_RECORD_KIND_FIELD = "shadow_record_kind"


def map_shadow_record_kind(shadow_row: Mapping[str, Any]) -> dict[str, Any]:
    """§5.3 FIELD MAP: a shadow-log row's `record_kind` ∈ {run, decision}
    becomes the archive-native `shadow_record_kind`; the trajectory
    `record_kind` field is NOT written at all (the archive record is not a
    trajectory record, and the two enums are disjoint).

    An out-of-vocabulary shadow kind refuses — an unrecognised shadow token
    silently mapped would be exactly the conflation this map exists to stop.
    """
    kind = shadow_row.get(TRAJECTORY_RECORD_KIND_FIELD)
    if kind not in SHADOW_RECORD_KIND:
        raise ValueError(
            f"shadow record_kind {kind!r} outside {SHADOW_RECORD_KIND} — "
            f"refuse (never map an unknown shadow token)")
    mapped = {key: value for key, value in shadow_row.items()
              if key != TRAJECTORY_RECORD_KIND_FIELD}
    mapped[SHADOW_RECORD_KIND_FIELD] = kind
    return mapped


def record_kind_conflations(row: Mapping[str, Any]) -> list[str]:
    """The conflation detector (§5.3): the archive record must never carry a
    SHADOW token in the trajectory `record_kind` field, and never a
    TRAJECTORY token in `shadow_record_kind`. Either direction REDs."""
    findings: list[str] = []
    traj = row.get(TRAJECTORY_RECORD_KIND_FIELD)
    if traj is not None:
        if traj in SHADOW_RECORD_KIND:
            findings.append(
                f"CONFLATION: shadow token {traj!r} written into the "
                f"trajectory field {TRAJECTORY_RECORD_KIND_FIELD!r}")
        elif traj not in TRAJECTORY_RECORD_KIND:
            findings.append(
                f"trajectory {TRAJECTORY_RECORD_KIND_FIELD}={traj!r} outside "
                f"{TRAJECTORY_RECORD_KIND}")
    shadow = row.get(SHADOW_RECORD_KIND_FIELD)
    if shadow is not None and shadow not in SHADOW_RECORD_KIND:
        findings.append(
            f"CONFLATION: {SHADOW_RECORD_KIND_FIELD}={shadow!r} outside "
            f"{SHADOW_RECORD_KIND}"
            + (" (a trajectory token)" if shadow in TRAJECTORY_RECORD_KIND
               else ""))
    return findings


# ===========================================================================
# (3) recorder-dialect canonical bytes — the STDLIB REPLICA + its tripwire
# ===========================================================================
ZERO_HASH = "0" * 64

#: Read as FILE BYTES by the parity tripwire; never imported (boundary row 6).
KERNEL_SOURCE_REL = "framework/" + "projection/kernel.py"
KERNEL_CANONICAL_FN = "canonical_bytes"


def canonical_bytes(value: Any) -> bytes:
    """Recorder-dialect canonical bytes — a STDLIB REPLICA, byte-identical to
    framework/projection/kernel.py::canonical_bytes and to
    framework.evidence.recorder._canonical (:144-152). Replicated rather than
    imported because boundary row 6 deliberately does not allowlist the cog5
    globs (§5.2/§10); `kernel_canonical_bytes_impl()` below is the standing
    byte-parity tripwire that keeps the replica honest.

    NOTE the dialect that is NOT this one: the scheduler store's
    ensure_ascii=True FILE-ORDER dialect is a DIFFERENT dialect and is never
    conflated with this one (§5.1).
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    """Recorder-dialect sha256 hexdigest of the canonical bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def content_fingerprint(value: Any) -> str:
    """The §5.3 duplicate-tolerance key: a CONTENT fingerprint, prefixed the
    way the shipped evolution contracts prefix theirs
    (framework/evolution/contracts.py:296-307). Dedup keys on THIS, never on
    an idempotency key — the P1 race means one key can legitimately appear
    twice, and two different bodies under one key are two different facts."""
    return "sha256:" + digest(value)


def repo_root() -> Path:
    """cabinet/scripts/tests/ -> the repo root (three parents up)."""
    return Path(__file__).resolve().parents[3]


def kernel_canonical_bytes_impl(root: Path | None = None):
    """Return the kernel's OWN `canonical_bytes`, compiled from its source
    BYTES — the parity tripwire's other side.

    Boundary-safe by construction: the function body is located with `ast`
    and executed in an isolated namespace containing only `json`. There is no
    import of the projection package anywhere in this family, so the cog2
    import-gate sweep sees exactly what the boundary intends (§10).

    Raises FileNotFoundError / LookupError loudly when the kernel or the
    function moves — a parity tripwire that silently no-ops is decoration.
    """
    source_path = (root or repo_root()) / KERNEL_SOURCE_REL
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == KERNEL_CANONICAL_FN:
            namespace: dict[str, Any] = {"json": json}
            exec(compile(ast.Module(body=[node], type_ignores=[]),
                         str(source_path), "exec"), namespace)
            return namespace[KERNEL_CANONICAL_FN]
    raise LookupError(
        f"{KERNEL_CANONICAL_FN}() not found at module scope in "
        f"{KERNEL_SOURCE_REL} — the replica parity tripwire has lost its "
        f"reference side; re-anchor it before trusting the replica")


#: Values the parity tripwire compares over — non-ASCII, nesting, key order,
#: and the float/int edge the dialect must NOT silently alter.
PARITY_CORPUS: tuple[Any, ...] = (
    {"b": 1, "a": 2},
    {"unicode": "kø benhavn — ünïcodé ✅"},
    {"nested": {"z": [3, 2, 1], "a": {"deep": True}}},
    [{"k": None}, {"k": False}, {"k": 0.5}],
    {"empty_map": {}, "empty_list": [], "zero": 0},
    "a bare string",
    12345,
)


# ===========================================================================
# (4) the §5.4 archive record shape — observation-only, R5-shaped
# ===========================================================================
#: Every archive record carries these. The shape is deliberately
#: OBSERVATION-ONLY: it may NAME receipts (content-addressed refs) but never
#: asserts authenticity/credit/eligibility/fitness (foundry §3 L55).
ARCHIVE_RECORD_REQUIRED: tuple[str, ...] = (
    "record_id",        # content-EXCLUDED identity (survives a content change)
    "sequence",         # arrival order — IS content for an archive (§5.1)
    "prev_hash",        # the chain from ZERO_HASH
    "provenance",       # §6.2 closed enum, INGESTER-stamped
    "source_class",     # the named class custody was established from
    "payload_ref",      # content-addressed receipt REF, never inline authority
    "classification",   # recorded SEPARATELY from the decision
    "decision",         # allow/deny, recorded separately from classification
    "lineage",          # {parent_ids, generation, operator}
    "outcome_refs",     # resolved by the evidence plane OUTSIDE this record
    "fitness_claim",    # structurally "none" while the league is CLOSED
    "cutoff_ts",        # declared cutoff (canonical), never a clock read
)

ARCHIVE_DECISIONS: tuple[str, ...] = ("allow", "deny")
LINEAGE_REQUIRED: tuple[str, ...] = ("parent_ids", "generation", "operator")

#: Candidate outcomes the E1 archive must preserve — X1's "every lineage/
#: failure": winners, losers, and CRASHED runs all get a row.
CANDIDATE_OUTCOMES: tuple[str, ...] = ("ranked", "failed", "crashed")


def archive_identity(record: Mapping[str, Any]) -> str:
    """DETERMINISTIC, CONTENT-EXCLUDED identity (the kernel's identity law,
    replicated): the digest of what the record IS ABOUT — never its claim
    content, so identity survives a content change or a source purge, and
    never a build-time ULID (the pinned COG-2 sim-1 mutant class)."""
    return digest({
        "candidate_id": record.get("candidate_id"),
        "generation": (record.get("lineage") or {}).get("generation"),
        "source_class": record.get("source_class"),
        "run_id": record.get("run_id"),
    })


def archive_record(
    *,
    candidate_id: str,
    run_id: str,
    sequence: int,
    prev_hash: str,
    source_class: str,
    payload_ref: str,
    classification: str,
    decision: str,
    parent_ids: Iterable[str],
    generation: int,
    operator: str,
    outcome: str,
    outcome_refs: Iterable[str] = (),
    cutoff_ts: str = "2026-07-24T00:00:00Z",
    shadow_record_kind: str | None = None,
) -> dict[str, Any]:
    """Build a §5.4-shaped archive record with its provenance STAMPED from
    the source class (never accepted from the caller's payload)."""
    if decision not in ARCHIVE_DECISIONS:
        raise ValueError(f"decision {decision!r} not in {ARCHIVE_DECISIONS}")
    if outcome not in CANDIDATE_OUTCOMES:
        raise ValueError(f"outcome {outcome!r} not in {CANDIDATE_OUTCOMES}")
    body: dict[str, Any] = {
        "candidate_id": candidate_id,
        "run_id": run_id,
        "sequence": int(sequence),
        "prev_hash": prev_hash,
        "payload_ref": payload_ref,
        "classification": classification,
        "decision": decision,
        "lineage": {
            "parent_ids": list(parent_ids),
            "generation": int(generation),
            "operator": operator,
        },
        "outcome": outcome,
        "outcome_refs": list(outcome_refs),
        "fitness_claim": FITNESS_CLAIM_NONE,
        "cutoff_ts": cutoff_ts,
    }
    if shadow_record_kind is not None:
        body[SHADOW_RECORD_KIND_FIELD] = shadow_record_kind
    body = stamp_provenance(body, source_class)
    body["record_id"] = archive_identity(body)
    return body


def archive_record_violations(row: Mapping[str, Any]) -> list[str]:
    """Every way an archive record can be malformed, in one place.

    Includes the observation-only laws: `fitness_claim` is structurally
    "none" while the league is CLOSED (§6.3), `payload_ref` is a
    content-addressed REF (the archive names receipts, never asserts them),
    and the two record_kind vocabularies never conflate (§5.3).
    """
    findings: list[str] = []
    for field in ARCHIVE_RECORD_REQUIRED:
        if field not in row:
            findings.append(f"missing required field {field!r}")
    findings.extend(provenance_violations([row]))
    findings.extend(record_kind_conflations(row))
    if row.get("fitness_claim") != FITNESS_CLAIM_NONE:
        findings.append(
            f"fitness_claim={row.get('fitness_claim')!r} — every archive/"
            f"league row ships {FITNESS_CLAIM_NONE!r} while the league is "
            f"CLOSED (§6.3)")
    ref = row.get("payload_ref")
    if not (isinstance(ref, str) and ref.startswith("sha256:")):
        findings.append(
            f"payload_ref={ref!r} is not a content-addressed ref — the "
            f"archive may NAME receipts, never inline authority")
    if row.get("decision") not in ARCHIVE_DECISIONS:
        findings.append(f"decision={row.get('decision')!r} not in "
                        f"{ARCHIVE_DECISIONS}")
    lineage = row.get("lineage")
    if not isinstance(lineage, Mapping):
        findings.append("lineage missing or not a mapping — X1 requires a "
                        "lineage row for EVERY candidate")
    else:
        for field in LINEAGE_REQUIRED:
            if field not in lineage:
                findings.append(f"lineage missing {field!r}")
    return findings


__all__ = [
    "PROVENANCE", "LIB_COG5_CORPUS_PROVENANCE", "PROVENANCE_ENUM",
    "REAL_PROVENANCE", "SOURCE_CLASS_TO_PROVENANCE", "SOURCE_CLASS_ALIASES",
    "NAMED_REAL_SOURCES", "FITNESS_CLAIM_NONE",
    "MIN_REAL_TRAJECTORIES_PER_STRATUM", "MIN_CAPTAIN_LABELS_PER_STRATUM",
    "JUDGE_AGREEMENT_BAR", "JUDGE_MIN_PAIRS",
    "canonical_source_class", "stamp_provenance", "provenance_violations",
    "count_toward_minimums",
    "TRAJECTORY_RECORD_KIND", "TRAJECTORY_RECORD_KIND_FIELD",
    "SHADOW_RECORD_KIND", "SHADOW_RECORD_KIND_FIELD",
    "map_shadow_record_kind", "record_kind_conflations",
    "ZERO_HASH", "KERNEL_SOURCE_REL", "KERNEL_CANONICAL_FN",
    "canonical_bytes", "digest", "content_fingerprint", "repo_root",
    "kernel_canonical_bytes_impl", "PARITY_CORPUS",
    "ARCHIVE_RECORD_REQUIRED", "ARCHIVE_DECISIONS", "LINEAGE_REQUIRED",
    "CANDIDATE_OUTCOMES", "archive_identity", "archive_record",
    "archive_record_violations",
]
