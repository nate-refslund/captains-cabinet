"""The pure deterministic fold — source proto-beliefs -> resolved beliefs.

COG-2 UNIT 1 (deterministic-rebuild core). Plan:
docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §5.1 (pure env-free
fold), §5.2 (K vs supersession authority — A-B4), §5.3 (frontier law), §5.4
(supersession state machine), §6 (storage: JSONL + manifest).

PURITY: fold() is side-effect-free and env-free — no environment variable is a
fold input (A-M6). It reads no clock and no randomness (the identity mutant is
the only randomness seam, and it exists solely to fail the gate). Storage lives
behind write_projection(), the impure boundary.

SUPERSESSION AUTHORITY IS SOURCE ORDER, NOT K (A-B4): per-subject+dimension
supersession is decided in the source's own total order
(stream_rank, intra_stream_seq) — never observation_time, which can invert
against commit order under a long transaction. observation_time is a
query-fence axis only (exercised by a later unit).

Three MUTANT SEAMS (sim 1 negative controls) carry non-default values used ONLY
by the gate test to prove each control bites; every default is the correct law:
  * frontier_of(..., past_null=True)           — folds past a NULL event_id
  * fold(..., supersession_order="arrival")    — keys supersession on arrival
  * fold(..., supersession_order="observation_time")  — keys on the wrong axis
  * fold(..., identity="fresh_ulid")           — mints a build-time id

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

from framework.cortex import belief as _belief
from framework.cortex.belief import Belief, compute_belief_id, digest

# stream_rank enum — schema-frozen per engine version (§5.2). Part of the hash
# epoch tuple; a new adapter is an epoch bump, never a determinism regression.
RANK_TABLE: dict[str, int] = {
    "officer_tasks_outbox": 0,
    "consequence": 1,
    "envelope_file": 2,
}


# ---------------------------------------------------------------------------
# Frontier law (§5.3) — pure over already-read rows
# ---------------------------------------------------------------------------

def frontier_of(rows: Iterable[dict], *, past_null: bool = False) -> Optional[int]:
    """F = the last contiguous backfilled (non-NULL event_id) row id.

    Eligible outbox rows are event_id IS NOT NULL AND id <= F, where
    F = min(id WHERE event_id IS NULL) - 1 if any NULL exists, else max(id).
    The frontier NEVER advances past a NULL, so a late backfill can never land
    behind the frontier and be silently skipped.

    MUTANT SEAM (sim 1, C-F1): past_null=True computes F = max(id), ignoring the
    NULL gap — it folds rows stranded behind an un-backfilled event and is the
    frontier-past-NULL negative control. Never a production value."""
    ids = [int(r["id"]) for r in rows]
    if not ids:
        return None
    null_ids = [int(r["id"]) for r in rows if r.get("event_id") in (None, "")]
    if past_null or not null_ids:
        return max(ids)
    return min(null_ids) - 1


def eligible_rows(rows: list[dict], *, past_null: bool = False) -> list[dict]:
    """The rows behind the frontier with a backfilled event_id (§5.3)."""
    frontier = frontier_of(rows, past_null=past_null)
    if frontier is None:
        return []
    return [r for r in rows
            if r.get("event_id") not in (None, "") and int(r["id"]) <= frontier]


# ---------------------------------------------------------------------------
# Confidence — derived statically from the versioned trust table (§5.6)
# ---------------------------------------------------------------------------

def derive_confidence(producer_key: str, trust_table: dict) -> tuple[Optional[int], dict]:
    """(confidence_ppm_or_None, source_trust). Absent producer => absent
    confidence (unknown), NEVER 0 (never-a-score). source_trust always carries
    {table_version, producer_key}."""
    table_version = int(trust_table["table_version"])
    raw = trust_table.get("producers", {}).get(producer_key)
    confidence = int(raw) if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else None
    return confidence, {"table_version": table_version, "producer_key": producer_key}


# ---------------------------------------------------------------------------
# The fold
# ---------------------------------------------------------------------------

def _mint_identity(proto: dict, identity: str) -> str:
    if identity == "fresh_ulid":
        # MUTANT SEAM (sim 1): a build-time id — non-deterministic across builds.
        return hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    prov = proto["provenance"]
    return compute_belief_id(proto["kind"], proto["subject_key"],
                             proto["dimension"], prov["event_id"],
                             proto["adapter_ordinal"])


def _supersession_key(proto: dict, order: str):
    prov = proto["provenance"]
    if order == "arrival":
        return proto["_arrival"]                      # MUTANT: input order
    if order == "observation_time":
        # MUTANT: the query-fence axis, which can invert against commit order.
        return (proto.get("observation_time") or "", prov["stream_rank"],
                prov["intra_stream_seq"])
    # CORRECT (A-B4): the source's own total order.
    return (prov["stream_rank"], prov["intra_stream_seq"])


def fold(proto_beliefs: Iterable[dict], *, trust_table: dict,
         supersession_order: str = "source",
         identity: str = "deterministic") -> list[Belief]:
    """Pure fold: dedupe -> per-(subject,dimension) supersession by source order
    -> contradiction post-pass -> status -> confidence. Returns beliefs sorted
    by belief_id (canonical order); full-refold-only (incremental arrival and
    rebuild-from-zero are the same computation)."""
    # Stamp arrival index (the mutant seam's key) and mint identity + dedupe by
    # belief_id (which embeds event_id + adapter_ordinal — physical duplication
    # of a source row collapses; the entity/observation pair of one event does
    # not, since adapter_ordinal differs).
    staged: list[dict] = []
    seen: set[str] = set()
    for arrival, proto in enumerate(proto_beliefs):
        row = dict(proto)
        row["_arrival"] = arrival
        row["belief_id"] = _mint_identity(row, identity)
        if row["belief_id"] in seen:
            continue
        seen.add(row["belief_id"])
        staged.append(row)

    # Group by (subject_key, dimension); resolve supersession within each group.
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in staged:
        groups.setdefault((row["subject_key"], row["dimension"]), []).append(row)

    superseded_by: dict[str, Optional[str]] = {}
    supersedes: dict[str, tuple[str, ...]] = {}
    contradicts: dict[str, tuple[str, ...]] = {}
    for key in sorted(groups):
        chain = sorted(groups[key], key=lambda r: _supersession_key(r, supersession_order))
        for i, row in enumerate(chain):
            bid = row["belief_id"]
            nxt = chain[i + 1]["belief_id"] if i + 1 < len(chain) else None
            superseded_by[bid] = nxt
            supersedes[bid] = (chain[i - 1]["belief_id"],) if i > 0 else ()
            contradicts[bid] = ()
        # Contradiction post-pass (§5.5): independent current lineages (>1 head)
        # cross-link symmetrically. A single linear chain has exactly one head,
        # so the tasks stream yields no contradictions (declared, C-F10).
        heads = [r["belief_id"] for r in chain if superseded_by[r["belief_id"]] is None]
        if len(heads) > 1:
            for bid in heads:
                contradicts[bid] = tuple(sorted(h for h in heads if h != bid))

    beliefs: list[Belief] = []
    for row in staged:
        bid = row["belief_id"]
        claim = row.get("claim")
        confidence, source_trust = derive_confidence(
            row["provenance"]["producer"], trust_table)
        purged = bool(row.get("purged"))
        if purged:
            status = _belief.STATUS_SOURCE_PURGED
        elif superseded_by[bid] is not None:
            status = _belief.STATUS_SUPERSEDED
        elif contradicts[bid]:
            status = _belief.STATUS_CONTRADICTED
        else:
            status = _belief.STATUS_ASSERTED
        beliefs.append(Belief(
            belief_id=bid,
            kind=row["kind"],
            subject_key=row["subject_key"],
            dimension=row["dimension"],
            adapter_ordinal=row["adapter_ordinal"],
            claim=None if purged else claim,
            claim_digest=None if purged else (digest(claim) if claim is not None else None),
            source_time=row.get("source_time"),
            observation_time=row.get("observation_time"),
            confidence=confidence,
            source_trust=source_trust,
            provenance=row["provenance"],
            status=status,
            claim_completeness=(_belief.COMPLETENESS_PURGED if purged
                                else row.get("claim_completeness", _belief.COMPLETENESS_INLINE)),
            supersedes=supersedes[bid],
            superseded_by=superseded_by[bid],
            contradicts=contradicts[bid],
        ))
    beliefs.sort(key=lambda b: b.belief_id)
    return beliefs


# ---------------------------------------------------------------------------
# Storage boundary (§6) — atomic JSONL + fold manifest
# ---------------------------------------------------------------------------

def build_manifest(beliefs: list[Belief], *, trust_table: dict,
                   frontier: Optional[int], max_id: Optional[int],
                   frontier_blockers: Optional[list] = None,
                   source_set: Optional[list[str]] = None) -> dict:
    """The fold manifest (§6). Carries the hash EPOCH TUPLE (A-m13) + frontier
    lag + blockers; hashed separately from the belief store."""
    lag = (max_id - frontier) if (max_id is not None and frontier is not None) else None
    return {
        "schema_version": "cortex-fold-manifest/v1",
        "epoch": {
            "engine_version": _belief.ENGINE_VERSION,
            "trust_table_version": int(trust_table["table_version"]),
            "rank_table": RANK_TABLE,
            "source_set": sorted(source_set or ["officer_tasks_outbox"]),
            "frontier": frontier,
        },
        "belief_store_hash": _belief.chained_hash(beliefs),
        "belief_count": len(beliefs),
        "frontier": frontier,
        "max_id": max_id,
        "frontier_lag": lag,
        "frontier_blockers": frontier_blockers or [],
    }


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_projection(beliefs: list[Belief], manifest: dict, cache_dir: Path) -> dict:
    """Write beliefs.jsonl (canonical, belief_id order) + fold-manifest.json
    atomically under cache_dir. The SQLite query index is a LATER-unit concern
    (query API) — not built here. Returns paths."""
    cache_dir = Path(cache_dir)
    jsonl = cache_dir / "beliefs.jsonl"
    manifest_path = cache_dir / "fold-manifest.json"
    body = "".join(_belief.canonical_row(b) + "\n" for b in beliefs)
    _atomic_write(jsonl, body)
    _atomic_write(manifest_path,
                  json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return {"beliefs_jsonl": str(jsonl), "fold_manifest": str(manifest_path)}


def read_beliefs_jsonl(path: Path) -> list[dict]:
    """Parse a beliefs.jsonl back to row dicts (the rows-not-bytes verifier
    path — A-m11). Refuses a malformed line (fail-loud, never a silent skip)."""
    rows: list[dict] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ValueError(f"beliefs.jsonl line {lineno} is not valid JSON") from exc
    return rows
