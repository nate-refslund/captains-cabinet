"""framework.projection.kernel — the eight already-law-identical parts of the
two shipped projection instantiations, extracted (COG-4 contract §6.1; the
scheduler is the third instantiation that forces this parameterization).

EXTRACTION SOURCES (byte-verified at the W3 ground pin):
  (a) canonical bytes + digest — the recorder dialect, previously duplicated at
      framework/cortex/belief.py:67-75 (imported from the frozen recorder) and
      framework/objectives/model.py (replicated stdlib). Replicated HERE in
      stdlib for the same reason objectives replicated it: this tree imports
      STDLIB ONLY (§8.3 row 6 + the §8.4 closure pin), so the recorder module
      is unreachable by law. Byte parity with both shipped stores is the
      standing tripwire (test_cog4_kernel_parity.py).
  (b) the identity law — identity is a recorder digest of a CONTENT-EXCLUDED
      identity tuple (cortex compute_belief_id; objectives node_id/edge_id),
      never a build-time ULID. Identity survives content change/purge.
  (c) the chained rows-hash over RE-PARSED rows (A-m11), PARAMETERIZED by
      algebra + seed + total-order + row normalization — NOT one forced
      algebra: cortex = sha256-chain + domain seed + id-order
      (belief.py chained_hash/hash_canonical_rows); objectives = digest-list +
      empty seed + canonical-bytes order (graph.py _rows_chain). BOTH remain
      expressible byte-identically.
  (d) the manifest envelope shape {schema_version, epoch{...}, <store-hash>,
      counts...} (cortex fold-manifest; objectives graph-manifest).
  (e) atomic write — O_EXCL private tmp + fsync + os.replace
      (framework/cortex/engine.py:434-442 shape).
  (f) the verified SINGLE-READ serve (F4 no-window,
      framework/cortex/query.py:300-335 shape) + a parameterized REFUSE-limb
      runner. The rows-hash manifest key is MANDATORY-PRESENT (§6.3): an
      absent key REFUSES — closing, for every kernel adopter, the objectives
      `is not None and` skip-hole (framework/objectives/query.py:214-215).
  (g) the canonical-cutoff validator — the regex replicated at
      framework/cortex/query.py:66 and framework/objectives/graph.py:43,
      now ONE definition mirrored by both (parity-pinned by value).
  (h) the rollback grammar — cache-delete reversible-by-rebuild: every store
      this kernel writes is a pure function of declared inputs, so deleting
      the cache artifacts is always safe and a rebuild restores them
      byte-identically.

DOMAIN-SIDE BY LAW (§6.2 — parameters, never kernel policy): epoch-tuple
contents; REFUSE limb sets beyond the mandatory hash binding; supersession
algebra; derived-state timing; staleness axes; adapters/ingest; row shapes and
their normalization. The kernel holds NO domain vocabulary, NO clock, NO env
read, NO randomness beyond the private tmp-name nonce (e), and NO import
outside the stdlib.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u1 (C3 kernel extraction).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

# --- (c) the two shipped chain algebras (closed set — a third instantiation
# needing another algebra extends the kernel, never forks it) ----------------
ALGEBRA_SHA256_CHAIN = "sha256-chain"   # cortex: bytes seed, acc=sha256(acc||row)
ALGEBRA_DIGEST_LIST = "digest-list"     # objectives: str seed, chain=digest([chain,row])
ALGEBRAS = frozenset({ALGEBRA_SHA256_CHAIN, ALGEBRA_DIGEST_LIST})


# ===========================================================================
# (a) canonical bytes + recorder-dialect digest
# ===========================================================================

def canonical_bytes(value: Any) -> bytes:
    """Recorder-dialect canonical bytes: json.dumps(sort_keys, compact,
    ensure_ascii=False) -> utf-8. Byte-identical to
    framework.evidence.recorder._canonical / framework.cortex.belief
    .canonical_bytes / framework.objectives.model.canonical_bytes (G-F5 — one
    dialect; the cross-store byte-parity test is the standing tripwire)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    """Recorder-dialect sha256 hexdigest of the canonical bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# ===========================================================================
# (b) the identity law
# ===========================================================================

def identity_digest(identity: Any) -> str:
    """DETERMINISTIC identity: the recorder digest of a CONTENT-EXCLUDED
    identity tuple/dict — the law both shipped stores already obey (cortex
    belief_id = digest of {kind, subject_key, dimension, event_id,
    adapter_ordinal}; objectives node_id = digest([kind, subject_key])). The
    caller passes ONLY identity fields (what the record IS ABOUT), never claim
    content — identity must survive a content change or source purge. Never a
    build-time ULID (the pinned COG-2 sim-1 mutant class). What belongs in a
    domain's identity tuple is domain law (§6.2), not kernel policy."""
    return digest(identity)


# ===========================================================================
# (c) the parameterized chained rows-hash
# ===========================================================================

def chained_rows_hash(rows: Iterable[Any], *, algebra: str, seed,
                      order_key: Callable[[Any], Any],
                      normalize: Optional[Callable[[Any], Any]] = None) -> str:
    """The chained hash over RE-PARSED rows (rows, never file bytes — A-m11),
    parameterized so BOTH shipped algebras stay expressible byte-identically:

      sha256-chain (cortex belief.py): seed is BYTES;
          acc = sha256(seed); for row: acc = sha256(acc || canonical(row));
          returns acc.hex(). Cortex order: belief_id; normalize: sorted
          derived collections (the hash_canonical_rows _sorted_row shape).
      digest-list (objectives graph.py _rows_chain): seed is STR ("" shipped);
          chain = seed; for row: chain = digest([chain, row]);
          returns chain. Objectives order: canonical_bytes of the row.

    Rows are totally ordered by `order_key` over the RAW rows (C-F3 — the sort
    makes the value invariant to arrival/set/dict iteration order under any
    PYTHONHASHSEED); `normalize` (domain-side, §6.2) is applied per row at
    hash time, never to the sort key. Seed-type confusion fails loud."""
    if algebra not in ALGEBRAS:
        raise ValueError(f"unknown chain algebra {algebra!r} (known: {sorted(ALGEBRAS)})")
    if normalize is None:
        normalize = lambda row: row  # noqa: E731 — identity, the objectives shape
    ordered = sorted(rows, key=order_key)
    if algebra == ALGEBRA_SHA256_CHAIN:
        if not isinstance(seed, bytes):
            raise ValueError("sha256-chain requires a BYTES domain seed "
                             f"(got {type(seed).__name__})")
        acc = hashlib.sha256(seed).digest()
        for row in ordered:
            acc = hashlib.sha256(acc + canonical_bytes(normalize(row))).digest()
        return acc.hex()
    if not isinstance(seed, str):
        raise ValueError("digest-list requires a STR seed (the shipped "
                         f"objectives seed is ''; got {type(seed).__name__})")
    chain = seed
    for row in ordered:
        chain = digest([chain, normalize(row)])
    return chain


# ===========================================================================
# (d) the manifest envelope shape
# ===========================================================================

def manifest_envelope(*, schema_version: str, epoch: dict, store_hash_key: str,
                      store_hash: str, counts: Optional[dict] = None,
                      extra: Optional[dict] = None) -> dict:
    """The manifest envelope both shipped stores already carry:
    {schema_version, epoch: {...}, <store_hash_key>: <hash>, counts..., extra
    domain fields...}. The store-hash member is MANDATORY at build time (the
    write-side twin of the (f) mandatory-present read limb — an envelope
    without its rows-hash cannot be constructed here). Epoch CONTENTS are
    domain law (§6.2); the kernel only requires the envelope shape. Collisions
    between extra/counts and envelope keys fail loud — a domain field may
    never silently shadow the hash it is bound by."""
    if not schema_version or not isinstance(schema_version, str):
        raise ValueError("schema_version must be a non-empty string")
    if not isinstance(epoch, dict):
        raise ValueError("epoch must be a dict (the domain's epoch tuple)")
    if not store_hash_key or not isinstance(store_hash_key, str):
        raise ValueError("store_hash_key must be a non-empty string")
    if not store_hash or not isinstance(store_hash, str):
        raise ValueError("store_hash must be a non-empty string (the envelope "
                         "is never built without its rows-hash)")
    manifest: dict = {"schema_version": schema_version, "epoch": epoch,
                      store_hash_key: store_hash}
    for name, block in (("counts", counts), ("extra", extra)):
        for key, value in (block or {}).items():
            if key in manifest:
                raise ValueError(f"{name} key {key!r} collides with an "
                                 "envelope member")
            manifest[key] = value
    return manifest


# ===========================================================================
# (e) atomic write — the engine.py:434-442 shape, verbatim discipline
# ===========================================================================

def atomic_write(path, data: str) -> None:
    """All-or-nothing file write: a private O_EXCL 0o600 tmp sibling receives
    the full payload, is flushed + fsynced, then os.replace()d over the target
    — so a crash at ANY pre-replace point leaves the target byte-untouched,
    and the replace itself is atomic (no reader ever sees a partial). Tmp
    debris from a crash is inert (dot-prefixed, nonce-named) and is overwritten
    territory for the next rebuild, never a served artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


# ===========================================================================
# (f) verified single-read serve + the parameterized REFUSE-limb runner
# ===========================================================================

def read_jsonl_rows(path) -> list:
    """Parse a canonical JSONL store back to row values (the rows-not-bytes
    verifier path — A-m11; the engine.read_beliefs_jsonl shape). Refuses a
    malformed line (fail-loud, never a silent skip)."""
    rows: list = []
    for lineno, line in enumerate(
            Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ValueError(
                f"{Path(path).name} line {lineno} is not valid JSON") from exc
    return rows


def verified_single_read(cache_dir, *, store_filename: str,
                         manifest_filename: str, store_hash_key: str,
                         rows_hash: Callable[[list], str],
                         refuse: Callable[[str], Exception],
                         extra_limbs: Sequence[Callable[[dict, list],
                                                        Optional[str]]] = ()
                         ) -> tuple[str, list, dict]:
    """The SINGLE-READ core of serve-time store-hash binding (C-F15/F4, the
    cortex query.py:300-335 shape made kernel law). Reads the store EXACTLY
    ONCE, re-derives the chained hash from the RE-PARSED rows via the domain's
    `rows_hash` (a chained_rows_hash partial — algebra/seed/order/normalize
    stay domain-side, §6.2), binds it to the manifest's `store_hash_key`, and
    returns (verified_hash, the EXACT rows that were hashed, the manifest).

    F4 (TOCTOU no-window): the rows returned ARE the rows that were hashed —
    the caller serves from THESE and never re-reads the path (a two-read path
    has a window in which a concurrent os.replace lands between the reads,
    serving bytes that were never hashed — the objectives two-read shape this
    kernel retires at adoption).

    REFUSE limbs, in order, each raised via the domain's `refuse` factory
    (StoreCorruptError, ServeRefused, ... — the exception is domain law):
      1. manifest unreadable/unparseable;
      2. `store_hash_key` ABSENT or empty/non-string — MANDATORY-PRESENT
         (§6.3): the absent key REFUSES; a manifest that omits its rows-hash
         can never serve unbound rows (the objectives query.py:214-215
         `is not None and` skip-hole, closed for every adopter);
      3. store unreadable/malformed (incl. a row shape that breaks the
         domain's hash re-derivation);
      4. rows-hash mismatch (tampered/partial store);
      5. each `extra_limbs` callable — the parameterized limb runner: domain
         limbs (counterfactual manifest, mixed-epoch compare, ...) run in
         declared order against (manifest, rows) AFTER the hash binding and
         REFUSE by returning a message (None = pass)."""
    cache_dir = Path(cache_dir)
    try:
        manifest = json.loads(
            (cache_dir / manifest_filename).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise refuse(
            f"{manifest_filename} unreadable: {type(exc).__name__}") from None
    expected = manifest.get(store_hash_key) if isinstance(manifest, dict) else None
    if not isinstance(expected, str) or not expected:
        raise refuse(
            f"{manifest_filename} carries no {store_hash_key} — the rows-hash "
            "limb is MANDATORY-PRESENT (§6.3); an absent key refuses, never "
            "skips") from None
    try:
        rows = read_jsonl_rows(cache_dir / store_filename)   # the ONE read
        actual = rows_hash(rows)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise refuse(
            f"{store_filename} unreadable/malformed: "
            f"{type(exc).__name__}") from None
    if actual != expected:
        raise refuse(
            f"rows-hash mismatch (manifest {expected[:12]}… vs store "
            f"{actual[:12]}…) — refuse to serve, rebuild to recover") from None
    for limb in extra_limbs:
        message = limb(manifest, rows)
        if message is not None:
            raise refuse(message) from None
    return actual, rows, manifest


# ===========================================================================
# (g) the canonical-cutoff validator (one definition, mirrored by value)
# ===========================================================================

# The canonical stored-timestamp shape — the EXACT pattern replicated at
# framework/cortex/query.py:66 (_CANON_TS_RE) and framework/objectives/
# graph.py:43 (_CANON_CUTOFF_RE); the parity test pins all three equal.
CANONICAL_CUTOFF_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
CANONICAL_CUTOFF_RE = re.compile(CANONICAL_CUTOFF_PATTERN)


def is_canonical_cutoff(value: Any) -> bool:
    """True iff `value` is a canonical YYYY-MM-DDTHH:MM:SSZ cutoff string."""
    return isinstance(value, str) and bool(CANONICAL_CUTOFF_RE.match(value))


def require_canonical_cutoff(value: Any, *,
                             refuse: Callable[[str], Exception] = ValueError) -> str:
    """HARD-ERROR gate on the cutoff shape (the fence-open guard): a
    legal-but-non-canonical ISO string ('+00:00' offsets, fractional seconds)
    or garbage would fence OPEN — silently include/exclude the wrong boundary
    — so a non-canonical cutoff refuses via the domain's `refuse` factory
    instead of mis-fencing. Denial never masquerades as an empty success.
    Returns the validated cutoff. Whether a cutoff may be None/omitted is
    domain law (§6.2) — callers guard that before calling."""
    if not is_canonical_cutoff(value):
        raise refuse(
            f"non-canonical cutoff {value!r}: must be a canonical "
            "YYYY-MM-DDTHH:MM:SSZ timestamp (a non-canonical cutoff fences "
            "open — hard error, never a silent mis-fence)")
    return value


# ===========================================================================
# (h) the rollback grammar — cache-delete reversible-by-rebuild
# ===========================================================================

def rollback_delete(cache_dir, *, filenames: Sequence[str]) -> list[str]:
    """The kernel rollback grammar: every store written through (e) is a pure
    function of declared inputs, so rollback = DELETE the named cache
    artifacts (missing-ok — rollback is idempotent) and rebuild restores them
    byte-identically (proven per store by the delete→rebuild parity gates).
    Artifact names must be bare names INSIDE cache_dir — a rollback may never
    reach outside the cache it rolls back (fail-loud on traversal)."""
    cache_dir = Path(cache_dir)
    deleted: list[str] = []
    for name in filenames:
        parts = Path(name)
        if parts.is_absolute() or ".." in parts.parts:
            raise ValueError(
                f"rollback artifact {name!r} escapes the cache dir — the "
                "grammar deletes inside cache_dir only")
        target = cache_dir / parts
        if target.exists():
            target.unlink()
            deleted.append(str(target))
    return deleted
