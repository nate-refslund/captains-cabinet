"""lib_cog5_archive_fixtures.py — the COG-5 W2 T1 ARCHIVE/LINEAGE family
fixture core (contract cognitive-core-phase-5-contract-2026-07-24 §12 sims
1/9/10 + X1 + the §5.3 duplicate-tolerant ingest / record_kind field map /
P1 lock-fold rider).

OWNERSHIP (the W2 naming law, §13): T1 owns `lib_cog5_archive*` and the
cross-unit `lib_cog5_corpus.py` (imported below — the vocabulary lives there,
the physics lives here). T2 owns `lib_cog5_scoring*`, T3 owns
`lib_cog5_boundary*`; the three units never collide on a file.

WHAT THIS LIB IS (and is not): `framework/evolution/archive.py`, its optional
`emitter.py` split, and `cabinet/scripts/cog5-archive-restore.py` do NOT
exist yet — the corpus lands BEFORE the implementation (tests-first, §13).
`ReferenceArchive` below implements the contract's §5.2 PHYSICS over scratch
roots so every sim assert and every §12 negative-control mutant is proven
BITING NOW, on this tree, with zero implementation present. It is NOT the
implementation and never ships outside the test surface; when the real module
lands, the SAME assert batteries run against it (integrator corpus surgery
per §13 — builders never edit corpus; contradictions route to the
integrator).

THE SUBSTRATE DECISION MADE EXECUTABLE (§5.1, the load-bearing premise):
an archive is NOT a fourth kernel projection. The kernel's `chained_rows_hash`
SORTS by order_key and is deliberately arrival-order-INVARIANT (kernel.py
:118-130, C-F3) because a projection is a derive-at-compile CACHE; the
kernel's rollback grammar is cache-DELETE + rebuild (:325-344), and delete
forecloses R5. For an archive, ARRIVAL ORDER IS CONTENT (lineage,
pre-registration honesty) and the store is never deletable. So the chain here
is a SEQUENTIAL prev_hash chain (order-SENSITIVE), the physics comes from the
recorder (`_write_exact_event` :610-623 — O_APPEND + flush + fsync +
dir-fsync; the anchor shape :599-608; the pending.json exactly-once heal
:625-670), and rollback is a rehearsed RESTORE, never a delete.
`kernel_would_miss_reorder()` proves the premise rather than asserting it: it
runs the kernel's own sorted algebra over a reordered lineage and shows the
value is UNCHANGED — which is exactly why the archive could not have been a
projection.

REPLICA, NOT IMPORT: manifest-class artifacts (segment index, seals) are
written with a stdlib REPLICA of the kernel's atomic-write discipline
(private O_EXCL tmp sibling + flush + fsync + os.replace — kernel.py:184-199),
and the canonical dialect is replicated in `lib_cog5_corpus`. Neither
imports `framework.projection` — boundary row 6 deliberately does not
allowlist the cog5 globs (§5.2/§10, rev-1 SF-4); the parity tripwires read
the kernel's function bodies from FILE BYTES instead (the COG-4
organs-registry precedent, framework/organs/registry.py:24-29).

WALLS made executable (§5.2): the archive store token is only ever spelled
via `ARCHIVE_ROOT_DEFAULT_REL` (assembled at runtime — the assembled-token
discipline; boundary row 9 allowlists the cog5 test globs, so this is belt
and braces, not a requirement); no candidate write path exists in this lib
(candidates are DATA to it); every scratch root is a tmp_path.

Pure stdlib + `lib_cog5_corpus` + ONE sanctioned SHIPPED framework surface
(`framework.evolution.contracts`, already on the tree and already imported by
T3's family) used as the LIVE parity side for the canonical dialect — never
a future surface.

S0: interpreter python3.12; no DB, no network, no clock reads (every
timestamp is a declared parameter; children are local subprocesses with
explicit env).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 contract §12/§13, W2 T1).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog5_corpus as CORE  # noqa: E402  (the T1-owned shared vocabulary)

# --------------------------------------------------------------------------
# future surfaces this family's vacuity arms watch for (all ABSENT today)
# --------------------------------------------------------------------------
ARCHIVE_MODULE_REL = "framework/evolution/archive.py"
EMITTER_MODULE_REL = "framework/evolution/emitter.py"
RESTORE_CLI_REL = "cabinet/scripts/cog5-archive-restore.py"
LEAGUE_CLI_REL = "cabinet/scripts/cog5-league.py"

#: The §5.4 cabinet-default archive root, assembled (never a contiguous
#: literal in swept source — the assembled-token discipline).
ARCHIVE_ROOT_DEFAULT_REL = "shared/interfaces/" + "foundry/" + "archive"

#: The COG-4 shadow-log CLI the §5.3 P1 lock-fold rider edits in W4.
SHADOW_CLI_REL = "cabinet/scripts/cog4-dispatch-shadow.py"

# --------------------------------------------------------------------------
# on-disk layout of a reference archive root
# --------------------------------------------------------------------------
SEGMENT_DIR = "segments"
MANIFEST_NAME = "manifest.json"
ANCHOR_NAME = "anchor.json"
PENDING_NAME = "pending.json"
DEFAULT_ROWS_PER_SEGMENT = 8
DEFAULT_ANCHOR_EVERY = 4
DEFAULT_CUTOFF = "2026-07-24T00:00:00Z"

#: The fields `ReferenceArchive._prepare` STAMPS onto a row as it lands in the
#: store. Every one of them is either the row's POSITION in the chain
#: (`sequence`, `prev_hash`) or a pure DERIVATION of the rest of the row
#: (`record_id` = the content-excluded identity, `row_hash` = the digest) — so
#: removing them loses no content, which is what makes the dedup key's
#: invariance under them safe rather than a weakening (see `dedupe_key`).
CHAIN_FIELDS: frozenset[str] = frozenset(
    {"sequence", "prev_hash", "record_id", "row_hash"})


# ==========================================================================
# stdlib REPLICAS of the kernel's physical disciplines (never imports)
# ==========================================================================
def fsync_dir(path: Path) -> None:
    """Directory fsync — the recorder's `_fsync_dir` (:164-172) shape, so a
    freshly appended segment/manifest name is durable, not just its bytes."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # Directory fsync is unavailable on some filesystems; the recorder
        # tolerates it the same way. Never mask it into a silent success for
        # the FILE fsync, which is not optional.
        pass


def atomic_write(path: Path, data: str) -> None:
    """All-or-nothing write — the kernel (e) discipline (kernel.py:184-199)
    reimplemented stdlib-side: a private O_EXCL 0o600 tmp sibling takes the
    full payload, is flushed + fsynced, then os.replace()d over the target.
    A crash at ANY pre-replace point leaves the target byte-untouched."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def append_exact_line(path: Path, encoded: str) -> None:
    """The recorder's `_write_exact_event` discipline (:610-623): O_APPEND +
    O_NOFOLLOW, 0o600, write + flush + fsync, then dir-fsync. Append-only —
    the store is NEVER whole-file replaced (that is the kernel's cache
    premise, which §5.1 refuses for an archive)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_dir(path.parent)


def row_hash(row: Mapping[str, Any]) -> str:
    """Digest of the row with its own hash field excluded (the recorder's
    unsigned-digest shape)."""
    unsigned = {k: v for k, v in row.items() if k != "row_hash"}
    return CORE.digest(unsigned)


# ==========================================================================
# the reference archive — §5.2 physics over a scratch root
# ==========================================================================
class ArchiveError(RuntimeError):
    """Refusal raised by the disciplined reader/writer."""


class ReferenceArchive:
    """Append-only JSONL segments with a SEQUENTIAL prev_hash chain, periodic
    anchor attestation, sealed segments, and a pending.json exactly-once
    heal. Every write goes through the recorder discipline; every
    manifest-class artifact through the atomic-write replica.

    The store DECLARES what it holds — `row_count`, `chain_head` and the
    attestation cadence `anchor_every` in the manifest, plus the periodic
    `anchor.json` — and `verify_archive` reads every one of them back. A
    counter that is written and never read is not a detector."""

    def __init__(self, root: Path, *,
                 rows_per_segment: int = DEFAULT_ROWS_PER_SEGMENT,
                 anchor_every: int = DEFAULT_ANCHOR_EVERY) -> None:
        self.root = Path(root)
        self.rows_per_segment = int(rows_per_segment)
        self.anchor_every = int(anchor_every)
        (self.root / SEGMENT_DIR).mkdir(parents=True, exist_ok=True)
        if not (self.root / MANIFEST_NAME).exists():
            self._write_manifest({"segments": [], "seals": [],
                                  "chain_head": CORE.ZERO_HASH, "row_count": 0,
                                  "anchor_every": self.anchor_every})
        elif self.manifest().get("anchor_every") != self.anchor_every:
            # The attestation CADENCE is a declared property of the store, not
            # an assumption the verifier makes — so it travels through the
            # copy-out/RESTORE drill with the manifest.
            manifest = self.manifest()
            manifest["anchor_every"] = self.anchor_every
            self._write_manifest(manifest)

    # -- manifest -------------------------------------------------------
    def _write_manifest(self, manifest: Mapping[str, Any]) -> None:
        atomic_write(self.root / MANIFEST_NAME,
                     json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                indent=2) + "\n")

    def manifest(self) -> dict[str, Any]:
        return json.loads((self.root / MANIFEST_NAME).read_text(encoding="utf-8"))

    # -- segments -------------------------------------------------------
    def segment_path(self, index: int) -> Path:
        return self.root / SEGMENT_DIR / f"seg-{index:05d}.jsonl"

    def segment_indices(self) -> list[int]:
        seg_dir = self.root / SEGMENT_DIR
        return sorted(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl"))

    def open_segment_index(self) -> int:
        indices = self.segment_indices()
        return indices[-1] if indices else 0

    def _segment_rows(self, index: int) -> list[dict[str, Any]]:
        path = self.segment_path(index)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def rows(self) -> list[dict[str, Any]]:
        """Every row, in ARRIVAL order (segment index, then file order)."""
        out: list[dict[str, Any]] = []
        for index in self.segment_indices():
            out.extend(self._segment_rows(index))
        return out

    def chain_head(self) -> str:
        rows = self.rows()
        return rows[-1]["row_hash"] if rows else CORE.ZERO_HASH

    # -- append ---------------------------------------------------------
    def _prepare(self, record: Mapping[str, Any]) -> dict[str, Any]:
        rows = self.rows()
        event = dict(record)
        event["sequence"] = len(rows) + 1
        event["prev_hash"] = rows[-1]["row_hash"] if rows else CORE.ZERO_HASH
        event["record_id"] = CORE.archive_identity(event)
        event["row_hash"] = row_hash(event)
        return event

    def append(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Write-ahead (pending.json) -> append -> anchor -> clear pending.
        The write-ahead is what makes the heal exactly-once possible.

        HEAL-ON-OPEN IS THE CALLER'S OBLIGATION, and it is written down here
        because the eventual `framework/evolution/archive.py` reads this model
        as its reference. `append` does NOT call `heal()`: appending onto a
        store whose last commit was interrupted OVERWRITES the unreconciled
        pending.json, so the owed attestation is never minted and the store
        sits ANCHOR_MISSING. Whoever opens a store reconciles it first —
        `heal()` is idempotent and returns None when there is nothing to do,
        so calling it on every open is always safe.
        Bounded, deliberately: unlike the permanent unservability a
        non-completing heal used to cause, this state is TRANSIENT — the next
        on-cadence append mints an anchor and the store verifies again."""
        event = self._prepare(record)
        self._write_pending(event)
        self._commit(event)
        return event

    def _write_pending(self, event: Mapping[str, Any]) -> None:
        atomic_write(self.root / PENDING_NAME,
                     json.dumps({"event": dict(event)}, ensure_ascii=False,
                                sort_keys=True, indent=2) + "\n")

    def _commit(self, event: Mapping[str, Any]) -> None:
        self._append_only(event)
        if int(event["sequence"]) % self.anchor_every == 0:
            self.write_anchor(event)
        self._refresh_manifest()
        (self.root / PENDING_NAME).unlink(missing_ok=True)
        fsync_dir(self.root)

    def append_crashing(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Simulate a crash BETWEEN the write-ahead and the append: pending
        .json is durable, the segment never received the row."""
        event = self._prepare(record)
        self._write_pending(event)
        return event

    def append_crashing_after_commit(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Simulate a crash AFTER the append but BEFORE pending.json was
        cleared — the case a naive heal duplicates.

        It OMITS the anchor, so at an on-cadence sequence this models a state
        real `_commit` cannot reach: `_commit` mints the attestation BEFORE it
        refreshes the manifest, so a genuine crash this late would already
        have one. The divergence is strictly CONSERVATIVE (the heal is handed
        strictly more to reconcile than reality can leave it), which is why it
        stands; the parametrize id says `-anchor-omitted` so no reader mistakes
        it for the real durable state. `append_crashing_before_anchor` is the
        byte-exact pre-anchor window."""
        event = self._prepare(record)
        self._write_pending(event)
        self._append_only(event)
        self._refresh_manifest()
        return event

    def append_crashing_before_anchor(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Simulate a crash in the REAL window INSIDE `_commit`, between
        `append_exact_line` and `write_anchor`.

        The durable state this leaves is exact: the row is on disk and
        fsynced, no attestation was minted for it, the manifest was never
        refreshed, and pending.json is still there. At an ON-CADENCE sequence
        this is the state a heal that reconciles the row but forgets the
        attestation leaves permanently unservable — which is why the battery's
        heal arms are parametrised over the cadence position rather than
        crashing at one arbitrary sequence.
        """
        event = self._prepare(record)
        self._write_pending(event)
        self._append_only(event)
        return event

    def _append_only(self, event: Mapping[str, Any]) -> None:
        """The segment append alone — `_commit`'s first step, with none of the
        obligations that follow it. Shared by the two crash fixtures so they
        cannot drift from the real write path."""
        index = self.open_segment_index()
        if len(self._segment_rows(index)) >= self.rows_per_segment:
            self.seal_segment(index)
            index += 1
        append_exact_line(
            self.segment_path(index),
            json.dumps(event, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n")

    # -- the exactly-once heal (recorder :625-670 shape) ------------------
    def heal(self) -> dict[str, Any] | None:
        """Finish an interrupted append EXACTLY ONCE — and COMPLETELY.

        Returns the reconciled event when an unreconciled pending.json was
        found, and None when there was nothing to reconcile. The caller never
        infers an interruption from anything else.

        "Exactly once" governs the ROW. "Completely" governs everything
        `_commit` owes for that row: the periodic attestation and the manifest
        counters. A heal that reconciled only the row would leave a legitimate
        crash position (between the append and the anchor, at an on-cadence
        sequence) permanently unservable — see the exactly-once limb below.
        """
        pending_path = self.root / PENDING_NAME
        if not pending_path.is_file():
            return None
        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ArchiveError("pending_invalid") from exc
        event = pending.get("event") if isinstance(pending, dict) else None
        if not isinstance(event, dict):
            raise ArchiveError("pending_invalid")
        if event.get("row_hash") != row_hash(event):
            raise ArchiveError("pending_hash_mismatch")
        rows = self.rows()
        sequence = int(event["sequence"])
        if len(rows) == sequence - 1:
            expected_prev = rows[-1]["row_hash"] if rows else CORE.ZERO_HASH
            if event.get("prev_hash") != expected_prev:
                raise ArchiveError("pending_continuity")
            self._commit(event)
        elif len(rows) == sequence:
            # The append DID land before the crash — reconcile without
            # writing a second copy. This is the exactly-once limb.
            if rows[-1].get("row_hash") != event.get("row_hash"):
                raise ArchiveError("pending_conflict")
            if sequence % self.anchor_every == 0:
                # THE INTERRUPTED ATTESTATION. `_commit` mints the anchor
                # AFTER the segment append, so a crash in that window leaves a
                # row that landed ON a cadence point with no attestation for
                # it. Reconciling the row without also minting it hands back a
                # store that is permanently ANCHOR_MISSING — `verify_archive`
                # never ok, `safe_sequence` pinned to the last good seal, and
                # every row past that seal unservable FOREVER. Finishing an
                # interrupted append means finishing ALL of it.
                #
                # Idempotent by construction: the attestation is a pure
                # function of the reconciled event, so when the crash landed
                # LATER (anchor already written, pending not yet cleared) this
                # rewrites byte-identical content through the same atomic
                # replace.
                self.write_anchor(event)
            self._refresh_manifest()
            pending_path.unlink(missing_ok=True)
            fsync_dir(self.root)
        else:
            raise ArchiveError("pending_sequence")
        return event

    # -- anchors + seals --------------------------------------------------
    def write_anchor(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """Periodic attestation over the chain head (recorder :599-608 shape,
        minus the signer — signing is the recorder's, not the archive's).

        UNSIGNED, and that bound is load-bearing rather than incidental: the
        attestation is a pure digest over public fields, so minting one needs
        NO SECRET and anyone able to write the store can also write a
        self-consistent attestation for it. The anchor therefore defeats an
        editor who does not re-mint it — never one who does (`remint_anchor`,
        and the battery's declared known-limit arm). Closing that is exactly
        what SIGNING would buy, and nothing weaker.
        """
        payload = {
            "schema": "cog5-archive-anchor/1",
            "sequence": int(event["sequence"]),
            "chain_head": event["row_hash"],
            "cutoff_ts": event.get("cutoff_ts", DEFAULT_CUTOFF),
        }
        anchor = {**payload, "anchor_hash": CORE.digest(payload)}
        atomic_write(self.root / ANCHOR_NAME,
                     json.dumps(anchor, ensure_ascii=False, sort_keys=True,
                                indent=2) + "\n")
        return anchor

    def seal_segment(self, index: int) -> dict[str, Any]:
        """Close a segment at its declared bound: its chain head is sealed
        into the manifest AND into the next segment's genesis expectation.
        Seals bound the whole-store re-verify cost WITHOUT the recorder's
        mint cap (which R5 forbids — unbounded retention)."""
        rows = self._segment_rows(index)
        if not rows:
            raise ArchiveError(f"cannot seal empty segment {index}")
        body = {
            "segment": self.segment_path(index).name,
            "index": index,
            "rows": len(rows),
            "first_sequence": int(rows[0]["sequence"]),
            "last_sequence": int(rows[-1]["sequence"]),
            "chain_head": rows[-1]["row_hash"],
        }
        seal = {**body, "seal_hash": CORE.digest(body)}
        manifest = self.manifest()
        seals = [s for s in manifest.get("seals", []) if s.get("index") != index]
        seals.append(seal)
        manifest["seals"] = sorted(seals, key=lambda s: s["index"])
        self._write_manifest(manifest)
        return seal

    def seal_open_segment(self) -> dict[str, Any] | None:
        """Seal whatever is currently open (the first step of the rollback
        drill — seal, then copy out; NEVER delete)."""
        index = self.open_segment_index()
        if not self._segment_rows(index):
            return None
        sealed = {s["index"] for s in self.manifest().get("seals", [])}
        if index in sealed:
            return None
        return self.seal_segment(index)

    def _refresh_manifest(self) -> None:
        manifest = self.manifest()
        manifest["segments"] = [self.segment_path(i).name
                                for i in self.segment_indices()]
        manifest["row_count"] = len(self.rows())
        manifest["chain_head"] = self.chain_head()
        self._write_manifest(manifest)


# ==========================================================================
# verification — sim 9's four detections, each named
# ==========================================================================
def verify_archive(root: Path) -> dict[str, Any]:
    """Full chain + seal + STORE-LEVEL verification.

    Returns {"ok", "findings", "verified_rows", "last_good_seal",
    "safe_sequence"} — `safe_sequence` is the highest sequence a disciplined
    reader may serve: the last good SEAL's last_sequence when anything beyond
    it is broken (§12 sim 9, "serve refuses beyond the last good seal").

    THREE LAYERS, and each catches an escape the others cannot (the reason
    none of them is decoration):

      per-ROW   — BITFLIP / FORGED_PREV_HASH / SEQUENCE_GAP / TRUNCATED_TAIL.
                  Blind to a row DELETED at a record boundary: no link breaks,
                  the tail is still a whole record, and the sequence numbers
                  that remain are self-consistent.
      per-SEAL  — BROKEN_SEAL, both limbs. Covers only SEALED segments, so the
                  open segment (where every fresh row lands) is unattested.
      per-STORE — ROW_COUNT_MISMATCH / MANIFEST_HEAD_MISMATCH / ANCHOR_* .
                  The store ALREADY writes these two independent counters —
                  the manifest's declared row_count + chain_head, and the
                  periodic anchor (§5.2). Consulting them is what closes the
                  open-segment deletion: the manifest catches a tail edit that
                  did not also rewrite the manifest, and the anchor catches one
                  that DID — the attestation was minted at a cadence point
                  BEFORE the edit, and repairing the manifest does not touch
                  it. Conversely the manifest covers the rows PAST the last
                  anchor point, which the anchor by construction cannot see.
                  Neither subsumes the other.

    BOUNDED, NOT ABSOLUTE: the anchor is UNSIGNED here, so minting needs no
    secret. An editor who ALSO re-mints the attestation over the shortened
    chain produces a fully self-consistent store and is NOT caught. That is
    the DECLARED KNOWN LIMIT of this reference model — pinned in the battery
    by `test_known_limit_the_complete_editor_that_also_re_mints_the_anchor`,
    and closable only by SIGNING the attestation (deliberately out of scope,
    §5.2). What the layer claims is exactly what it delivers: it defeats every
    editor that stops at the manifest, which is what makes it non-redundant
    with the manifest — not unforgeability.

    The refusal boundary is deliberately unchanged by the store layer: a
    store-level finding flips `ok` to False, which pins `safe_sequence` to the
    last good SEAL — conservative, never over-serving.
    """
    root = Path(root)
    findings: list[str] = []
    manifest: dict[str, Any]
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "findings": [f"manifest_unreadable: {exc!r}"],
                "verified_rows": 0, "last_good_seal": None, "safe_sequence": 0}

    seals = {int(s["index"]): s for s in manifest.get("seals", [])}
    seg_dir = root / SEGMENT_DIR
    indices = sorted(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl"))

    prev = CORE.ZERO_HASH
    expected_sequence = 1
    verified_rows = 0
    last_good_seal: dict[str, Any] | None = None
    broken_at: int | None = None      # first bad sequence
    walked_rows = 0                   # every row PARSED off disk, good or bad
    last_sequence = 0                 # the last row's own sequence claim
    hash_by_sequence: dict[int, str] = {}

    for index in indices:
        path = seg_dir / f"seg-{index:05d}.jsonl"
        raw = path.read_text(encoding="utf-8")
        lines = raw.splitlines()
        # TRUNCATED TAIL: a segment whose final byte is not a newline lost
        # part of its last row — an append-only store always ends on one.
        if raw and not raw.endswith("\n"):
            findings.append(f"TRUNCATED_TAIL: {path.name} does not end on a "
                            f"record boundary")
            if broken_at is None:
                broken_at = expected_sequence + max(len(lines) - 1, 0)
        seg_rows: list[dict[str, Any]] = []
        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                seg_rows.append(json.loads(line))
            except ValueError:
                findings.append(f"TRUNCATED_TAIL: {path.name} line {lineno} "
                                f"is not parseable JSON (partial record)")
                if broken_at is None:
                    broken_at = expected_sequence
                break

        for row in seg_rows:
            if row.get("row_hash") != row_hash(row):
                findings.append(
                    f"BITFLIP: sequence {row.get('sequence')} row_hash does "
                    f"not match its content")
                if broken_at is None:
                    broken_at = int(row.get("sequence", expected_sequence))
            elif row.get("prev_hash") != prev:
                findings.append(
                    f"FORGED_PREV_HASH: sequence {row.get('sequence')} does "
                    f"not extend the chain (expected prev {prev[:12]}…)")
                if broken_at is None:
                    broken_at = int(row.get("sequence", expected_sequence))
            elif int(row.get("sequence", -1)) != expected_sequence:
                findings.append(
                    f"SEQUENCE_GAP: expected {expected_sequence}, found "
                    f"{row.get('sequence')}")
                if broken_at is None:
                    broken_at = expected_sequence
            else:
                verified_rows += 1
            walked_rows += 1
            last_sequence = int(row.get("sequence", last_sequence))
            if isinstance(row.get("row_hash"), str):
                hash_by_sequence[last_sequence] = row["row_hash"]
            prev = row.get("row_hash", prev)
            expected_sequence = int(row.get("sequence", expected_sequence)) + 1

        seal = seals.get(index)
        if seal is not None:
            body = {k: v for k, v in seal.items() if k != "seal_hash"}
            if seal.get("seal_hash") != CORE.digest(body):
                findings.append(f"BROKEN_SEAL: segment {index} seal_hash does "
                                f"not match its body")
                if broken_at is None:
                    broken_at = int(seal.get("first_sequence", expected_sequence))
            elif not seg_rows or seal.get("chain_head") != seg_rows[-1].get("row_hash"):
                findings.append(f"BROKEN_SEAL: segment {index} sealed chain "
                                f"head does not match the segment contents")
                if broken_at is None:
                    broken_at = int(seal.get("first_sequence", expected_sequence))
            elif seal.get("rows") != len(seg_rows):
                findings.append(f"BROKEN_SEAL: segment {index} sealed row "
                                f"count {seal.get('rows')} != {len(seg_rows)}")
                if broken_at is None:
                    broken_at = int(seal.get("first_sequence", expected_sequence))
            elif broken_at is None:
                last_good_seal = seal

    # -- per-STORE: the two detectors the store already writes ---------------
    # Both are computed and persisted on every commit (`_refresh_manifest`)
    # and were, before this layer existed, never read back — which is exactly
    # how a row deleted from the UNSEALED open segment verified clean.
    declared_rows = manifest.get("row_count")
    if not isinstance(declared_rows, int) or isinstance(declared_rows, bool):
        findings.append(
            f"ROW_COUNT_MISMATCH: manifest declares no usable row_count "
            f"({declared_rows!r}); the store walks {walked_rows} rows")
    elif declared_rows != walked_rows:
        findings.append(
            f"ROW_COUNT_MISMATCH: manifest declares {declared_rows} rows, the "
            f"store walks {walked_rows}")

    declared_head = manifest.get("chain_head")
    walked_head = hash_by_sequence.get(last_sequence, CORE.ZERO_HASH) \
        if walked_rows else CORE.ZERO_HASH
    if declared_head != walked_head:
        findings.append(
            f"MANIFEST_HEAD_MISMATCH: manifest declares chain head "
            f"{str(declared_head)[:12]}…, the store's last row carries "
            f"{walked_head[:12]}…")

    findings.extend(_anchor_findings(root, manifest, last_sequence,
                                     hash_by_sequence))

    ok = not findings
    if ok:
        safe_sequence = expected_sequence - 1
    else:
        safe_sequence = int(last_good_seal["last_sequence"]) if last_good_seal else 0
    return {"ok": ok, "findings": findings, "verified_rows": verified_rows,
            "last_good_seal": last_good_seal, "safe_sequence": safe_sequence}


def _anchor_findings(root: Path, manifest: Mapping[str, Any], last_sequence: int,
                     hash_by_sequence: Mapping[int, str]) -> list[str]:
    """§5.2's periodic ATTESTATION, read back at last.

    `write_anchor` fires every `anchor_every` sequences and pins the chain head
    AT THAT POINT. That makes it the one detector a tail editor cannot satisfy
    by rewriting the MANIFEST: the attestation was minted before the edit and
    names a sequence the shrunken store no longer reaches.

    Say the bound out loud rather than implying it is absolute: this
    attestation is UNSIGNED, so minting one needs no secret. An editor who
    ALSO re-mints it over the shortened chain escapes every check below. That
    is a declared known limit of the reference model (pinned by the battery's
    known-limit arm), and SIGNING — the recorder's, deliberately out of scope
    here — is the only thing that would close it.

    Three named escapes, none of which the other layers see:
      ANCHOR_MISSING            — attestation due and absent (a store that
                                  stopped attesting, or a restore that dropped
                                  the anchor on the floor).
      ANCHOR_SEQUENCE_MISMATCH  — the store no longer stands where its own
                                  attestation says it stood.
      FORGED_ANCHOR             — the attestation LIES: either its anchor_hash
                                  does not match its body (the crude forge), or
                                  it is internally self-consistent but names a
                                  chain head the walked chain never had (the
                                  re-signed forge — only the anchor-vs-chain
                                  limb catches that one, exactly as with seals).
    """
    findings: list[str] = []
    anchor_every = manifest.get("anchor_every")
    if not isinstance(anchor_every, int) or isinstance(anchor_every, bool) \
            or anchor_every <= 0:
        anchor_every = DEFAULT_ANCHOR_EVERY
    anchor_path = Path(root) / ANCHOR_NAME
    # The cadence point the store should currently stand attested at.
    attest_point = (max(last_sequence, 0) // anchor_every) * anchor_every

    if attest_point < anchor_every:
        # No attestation is due yet. One being PRESENT means the store shrank
        # below its own first cadence point.
        if anchor_path.is_file():
            findings.append(
                f"ANCHOR_SEQUENCE_MISMATCH: an attestation exists but the "
                f"store only reaches sequence {last_sequence}, below its "
                f"first cadence point {anchor_every}")
        return findings

    if not anchor_path.is_file():
        findings.append(
            f"ANCHOR_MISSING: the store reaches sequence {last_sequence} but "
            f"carries no {ANCHOR_NAME} attestation for sequence {attest_point}")
        return findings
    try:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        findings.append(f"FORGED_ANCHOR: {ANCHOR_NAME} is unreadable: {exc!r}")
        return findings
    if not isinstance(anchor, dict):
        findings.append(f"FORGED_ANCHOR: {ANCHOR_NAME} is not an attestation "
                        f"object")
        return findings

    body = {k: v for k, v in anchor.items() if k != "anchor_hash"}
    if anchor.get("anchor_hash") != CORE.digest(body):
        findings.append("FORGED_ANCHOR: anchor_hash does not match its body")
        return findings
    attested_sequence = anchor.get("sequence")
    if attested_sequence != attest_point:
        findings.append(
            f"ANCHOR_SEQUENCE_MISMATCH: the attestation stands at sequence "
            f"{attested_sequence!r}, the store's cadence point is "
            f"{attest_point}")
        return findings
    walked = hash_by_sequence.get(attest_point)
    if anchor.get("chain_head") != walked:
        findings.append(
            f"FORGED_ANCHOR: the attestation names chain head "
            f"{str(anchor.get('chain_head'))[:12]}… at sequence "
            f"{attest_point}, the walked chain carries {str(walked)[:12]}…")
    return findings


def serve_rows(root: Path, *, skip_verify: bool = False) -> list[dict[str, Any]]:
    """The disciplined serve: verify first, and REFUSE to serve past the last
    good seal when anything is broken.

    `skip_verify=True` is the sim-9 NEGATIVE CONTROL — the reader that skips
    verification and serves past corruption. It exists so the test can prove
    the verification is load-bearing rather than decorative.
    """
    root = Path(root)
    rows: list[dict[str, Any]] = []
    seg_dir = root / SEGMENT_DIR
    for index in sorted(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl")):
        for line in (seg_dir / f"seg-{index:05d}.jsonl").read_text(
                encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                if skip_verify:
                    continue       # the mutant shrugs the partial row off
                break
    if skip_verify:
        return rows
    result = verify_archive(root)
    if result["ok"]:
        return rows
    return [r for r in rows if int(r.get("sequence", 0)) <= result["safe_sequence"]]


# ==========================================================================
# corruption injectors (sim 9) — each names the escape it creates
# ==========================================================================
def corrupt_truncate_tail(root: Path, *, drop_bytes: int = 40) -> None:
    """Chop bytes off the last segment so its final record is partial."""
    seg_dir = Path(root) / SEGMENT_DIR
    index = max(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl"))
    path = seg_dir / f"seg-{index:05d}.jsonl"
    raw = path.read_bytes()
    path.write_bytes(raw[:max(len(raw) - drop_bytes, 0)])


def corrupt_bitflip_row(root: Path, *, sequence: int) -> None:
    """Alter a row's CONTENT in place, leaving its recorded row_hash stale."""
    _rewrite_row(root, sequence, lambda row: {**row, "classification": "public"})


def corrupt_forge_prev_hash(root: Path, *, sequence: int) -> None:
    """The SOPHISTICATED forge: rewrite prev_hash AND recompute row_hash so
    the row is internally self-consistent. Only the chain-LINK check (and the
    seal) can catch it — which is the point of keeping both."""
    def forge(row: dict[str, Any]) -> dict[str, Any]:
        forged = {**row, "prev_hash": "f" * 64}
        forged["row_hash"] = row_hash(forged)
        return forged
    _rewrite_row(root, sequence, forge)


def corrupt_break_seal(root: Path, *, index: int = 0,
                       resign: bool = False) -> None:
    """Tamper a sealed chain head in the manifest.

    `resign=False` leaves the seal_hash stale (the crude break, caught by the
    seal's own self-consistency limb). `resign=True` RECOMPUTES the seal_hash
    over the lie — a self-consistent seal that no longer matches the segment
    it claims to attest, which only the seal-vs-segment limb can catch. Both
    limbs are exercised so neither is decoration.
    """
    path = Path(root) / MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for seal in manifest.get("seals", []):
        if int(seal["index"]) == index:
            seal["chain_head"] = "0" * 63 + "1"
            if resign:
                body = {k: v for k, v in seal.items() if k != "seal_hash"}
                seal["seal_hash"] = CORE.digest(body)
    atomic_write(path, json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                  indent=2) + "\n")


def corrupt_drop_open_segment_tail(root: Path, *, rows: int = 1) -> int:
    """THE ESCAPE THE PER-ROW AND PER-SEAL LAYERS CANNOT SEE: delete whole
    records from the tail of the UNSEALED open segment, cleanly at a record
    boundary.

    Nothing local is disturbed — no link is broken (the deleted rows were the
    only ones pointing forward), the file still ends on a newline so the
    truncated-tail detector is silent, and no seal covers the open segment.
    Only the store's own declared counters know the store is now short.
    Returns the number of rows removed.
    """
    seg_dir = Path(root) / SEGMENT_DIR
    index = max(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl"))
    path = seg_dir / f"seg-{index:05d}.jsonl"
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    keep = lines[:max(len(lines) - int(rows), 0)]
    path.write_text(("\n".join(keep) + "\n") if keep else "", encoding="utf-8")
    return len(lines) - len(keep)


def corrupt_strip_manifest_declaration(root: Path, *,
                                       field: str = "row_count") -> None:
    """A manifest that stops DECLARING one of its counters. Fail-closed: an
    absent declaration must never read as agreement."""
    path = Path(root) / MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.pop(field, None)
    atomic_write(path, json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                  indent=2) + "\n")


def repair_manifest_counters(root: Path) -> dict[str, Any]:
    """THE THOROUGH EDITOR'S TOOL: recompute the manifest's declared
    `row_count`/`chain_head` from what is NOW on disk, so the manifest agrees
    with the shortened store.

    This is what defeats the manifest layer, and it is why the periodic
    attestation is not redundant with it: the anchor was minted at a cadence
    point BEFORE the edit, and repairing the manifest does not touch it.

    That is the whole of the non-redundancy claim, and it does NOT claim the
    anchor is unforgeable. `remint_anchor` below is the editor that goes one
    step further and escapes — the declared known limit, pinned by the
    battery's known-limit arm.
    """
    root = Path(root)
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    seg_dir = root / SEGMENT_DIR
    rows: list[dict[str, Any]] = []
    for index in sorted(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl")):
        for line in (seg_dir / f"seg-{index:05d}.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    manifest["row_count"] = len(rows)
    manifest["chain_head"] = rows[-1]["row_hash"] if rows else CORE.ZERO_HASH
    atomic_write(root / MANIFEST_NAME,
                 json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                            indent=2) + "\n")
    return manifest


def remint_anchor(root: Path) -> dict[str, Any]:
    """THE COMPLETE EDITOR'S SECOND TOOL: re-mint the attestation over what is
    NOW on disk, at the shortened store's OWN cadence point.

    This is not a forgery in the `corrupt_forge_anchor` sense — nothing here
    lies. It is a perfectly well-formed attestation for the store as it now
    stands, produced with nothing but public knowledge, because minting needs
    NO SECRET in this model (`write_anchor` is a pure digest over public
    fields; §5.2's shape "minus the signer").

    Composed with `corrupt_drop_open_segment_tail` + `repair_manifest_counters`
    it is the E4 editor: the store verifies CLEAN and the dropped row is
    silently gone. That is the reference model's DECLARED KNOWN LIMIT, pinned
    by `test_known_limit_the_complete_editor_that_also_re_mints_the_anchor` so
    a reader cannot mistake this model for the real thing. A SIGNED anchor is
    what would buy the difference.

    Returns the attestation written, or the empty dict when the shortened
    store no longer reaches its first cadence point (nothing to attest).
    """
    root = Path(root)
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    anchor_every = manifest.get("anchor_every")
    if not isinstance(anchor_every, int) or isinstance(anchor_every, bool) \
            or anchor_every <= 0:
        anchor_every = DEFAULT_ANCHOR_EVERY
    seg_dir = root / SEGMENT_DIR
    rows: list[dict[str, Any]] = []
    for index in sorted(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl")):
        for line in (seg_dir / f"seg-{index:05d}.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    point = (len(rows) // anchor_every) * anchor_every
    if point < anchor_every:
        (root / ANCHOR_NAME).unlink(missing_ok=True)
        return {}
    attested = rows[point - 1]
    payload = {
        "schema": "cog5-archive-anchor/1",
        "sequence": point,
        "chain_head": attested["row_hash"],
        "cutoff_ts": attested.get("cutoff_ts", DEFAULT_CUTOFF),
    }
    anchor = {**payload, "anchor_hash": CORE.digest(payload)}
    atomic_write(root / ANCHOR_NAME,
                 json.dumps(anchor, ensure_ascii=False, sort_keys=True,
                            indent=2) + "\n")
    return anchor


def corrupt_forge_anchor(root: Path, *, resign: bool = False) -> None:
    """Tamper the periodic attestation's chain head.

    `resign=False` leaves `anchor_hash` stale (the crude forge, caught by the
    anchor's own self-consistency limb). `resign=True` RECOMPUTES it over the
    lie — an internally self-consistent attestation that no longer matches the
    chain it claims to attest, which only the anchor-vs-chain limb can catch.
    Both limbs are exercised so neither is decoration (the seal pattern).
    """
    path = Path(root) / ANCHOR_NAME
    anchor = json.loads(path.read_text(encoding="utf-8"))
    anchor["chain_head"] = "0" * 63 + "1"
    if resign:
        body = {k: v for k, v in anchor.items() if k != "anchor_hash"}
        anchor["anchor_hash"] = CORE.digest(body)
    atomic_write(path, json.dumps(anchor, ensure_ascii=False, sort_keys=True,
                                  indent=2) + "\n")


def corrupt_drop_anchor(root: Path) -> None:
    """Delete the attestation outright — the shape a restore that forgets to
    carry `anchor.json` produces."""
    (Path(root) / ANCHOR_NAME).unlink(missing_ok=True)


def _rewrite_row(root: Path, sequence: int,
                 transform: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    seg_dir = Path(root) / SEGMENT_DIR
    for path in sorted(seg_dir.glob("seg-*.jsonl")):
        lines = path.read_text(encoding="utf-8").splitlines()
        changed = False
        out: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            row = json.loads(line)
            if int(row.get("sequence", -1)) == sequence:
                row = transform(row)
                changed = True
            out.append(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")))
        if changed:
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
            return
    raise ArchiveError(f"sequence {sequence} not found to corrupt")


# ==========================================================================
# sim 10 — the seal + independently rehearsed RESTORE drill
# ==========================================================================
def seal_and_copy_out(archive: ReferenceArchive, dest: Path) -> dict[str, Any]:
    """Rollback step 1 (§5.2/§16): SEAL the open segment, then copy the store
    out. The source is never deleted — deleting would forge the
    observation-only history and foreclose R5."""
    archive.seal_open_segment()
    dest = Path(dest)
    (dest / SEGMENT_DIR).mkdir(parents=True, exist_ok=True)
    for path in sorted((archive.root / SEGMENT_DIR).glob("seg-*.jsonl")):
        atomic_write(dest / SEGMENT_DIR / path.name,
                     path.read_text(encoding="utf-8"))
    atomic_write(dest / MANIFEST_NAME,
                 (archive.root / MANIFEST_NAME).read_text(encoding="utf-8"))
    _copy_anchor(archive.root, dest)
    return archive_report(archive.root)


def _copy_anchor(src: Path, dest: Path) -> None:
    """The ATTESTATION travels with the store. A copy-out/restore that left it
    behind would hand over a store whose §5.2 attestation is simply missing —
    which `verify_archive` now names (ANCHOR_MISSING) rather than tolerating."""
    anchor = Path(src) / ANCHOR_NAME
    if anchor.is_file():
        atomic_write(Path(dest) / ANCHOR_NAME, anchor.read_text(encoding="utf-8"))


def restore(copy_root: Path, new_root: Path) -> dict[str, Any]:
    """Rollback step 2: an INDEPENDENT re-read into a fresh root, verified.
    Never an in-place cache rebuild."""
    copy_root, new_root = Path(copy_root), Path(new_root)
    (new_root / SEGMENT_DIR).mkdir(parents=True, exist_ok=True)
    for path in sorted((copy_root / SEGMENT_DIR).glob("seg-*.jsonl")):
        atomic_write(new_root / SEGMENT_DIR / path.name,
                     path.read_text(encoding="utf-8"))
    atomic_write(new_root / MANIFEST_NAME,
                 (copy_root / MANIFEST_NAME).read_text(encoding="utf-8"))
    _copy_anchor(copy_root, new_root)
    return archive_report(new_root)


def archive_report(root: Path) -> dict[str, Any]:
    """The comparable restore evidence: every chain head, the row count, and
    the ORDERED lineage identity list (so a reorder is visible even if the
    multiset is unchanged)."""
    root = Path(root)
    verification = verify_archive(root)
    seg_dir = root / SEGMENT_DIR
    rows: list[dict[str, Any]] = []
    heads: list[str] = []
    for index in sorted(int(p.stem.split("-")[1]) for p in seg_dir.glob("seg-*.jsonl")):
        seg: list[dict[str, Any]] = []
        for line in (seg_dir / f"seg-{index:05d}.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                try:
                    seg.append(json.loads(line))
                except ValueError:
                    break
        if seg:
            heads.append(seg[-1]["row_hash"])
        rows.extend(seg)
    return {
        "ok": verification["ok"],
        "findings": verification["findings"],
        "row_count": len(rows),
        "chain_head": rows[-1]["row_hash"] if rows else CORE.ZERO_HASH,
        "segment_chain_heads": heads,
        "lineage_order": [r.get("record_id") for r in rows],
        "lineage_ids": sorted(str(r.get("record_id")) for r in rows),
        "candidate_ids": sorted(str(r.get("candidate_id")) for r in rows),
    }


def restore_dropping_row(copy_root: Path, new_root: Path, *,
                         sequence: int) -> dict[str, Any]:
    """NEGATIVE CONTROL (sim 10): a restore that silently loses one lineage
    row. Verification must catch it — a dropped row is exactly the failure
    the drill exists to make impossible."""
    report = restore(copy_root, new_root)
    _drop_row(Path(new_root), sequence)
    return {**archive_report(new_root), "pre_mutation": report}


def restore_reordering_rows(copy_root: Path, new_root: Path) -> dict[str, Any]:
    """NEGATIVE CONTROL (sim 10): a restore that preserves every row but
    REORDERS two of them. For an archive, arrival order IS content — this
    must be detected (and would be invisible to the kernel's order-invariant
    algebra; see `kernel_would_miss_reorder`)."""
    restore(copy_root, new_root)
    seg_dir = Path(new_root) / SEGMENT_DIR
    path = sorted(seg_dir.glob("seg-*.jsonl"))[0]
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) >= 2:
        lines[0], lines[1] = lines[1], lines[0]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return archive_report(new_root)


def _drop_row(root: Path, sequence: int) -> None:
    seg_dir = root / SEGMENT_DIR
    for path in sorted(seg_dir.glob("seg-*.jsonl")):
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        kept = [l for l in lines if int(json.loads(l).get("sequence", -1)) != sequence]
        if len(kept) != len(lines):
            path.write_text(("\n".join(kept) + "\n") if kept else "",
                            encoding="utf-8")
            return
    raise ArchiveError(f"sequence {sequence} not found to drop")


def kernel_would_miss_reorder(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Run the KERNEL'S OWN sorted algebra (compiled from its source bytes,
    never imported — boundary row 6) over a lineage and its reversal.

    Returns {"in_order", "reversed", "archive_in_order", "archive_reversed"}.
    The kernel values are EQUAL (it sorts by order_key — deliberately
    arrival-order-invariant, C-F3) while the archive's sequential chain
    differs. That inequality IS the §5.1 substrate decision, demonstrated
    rather than asserted.
    """
    canonical = CORE.kernel_canonical_bytes_impl()
    import hashlib

    def kernel_chain(seq: Iterable[Mapping[str, Any]]) -> str:
        # kernel.py:118-130 sha256-chain, with its defining SORT
        ordered = sorted(seq, key=lambda r: r["record_id"])
        acc = hashlib.sha256(b"").digest()
        for row in ordered:
            acc = hashlib.sha256(acc + canonical(dict(row))).digest()
        return acc.hex()

    def archive_chain(seq: Iterable[Mapping[str, Any]]) -> str:
        acc = CORE.ZERO_HASH
        for row in seq:
            acc = CORE.digest({"prev": acc, "row": dict(row)})
        return acc

    forward = list(rows)
    backward = list(reversed(forward))
    return {
        "in_order": kernel_chain(forward),
        "reversed": kernel_chain(backward),
        "archive_in_order": archive_chain(forward),
        "archive_reversed": archive_chain(backward),
    }


# ==========================================================================
# sim 1 — the E1 run (≥20 seeded candidates vs the eval substrate)
# ==========================================================================
#: sim #1's PARAMETER (never the sim count — the recorded count-trap).
E1_MIN_CANDIDATES = 20
E1_DEFAULT_CANDIDATES = 24


def seeded_candidates(count: int = E1_DEFAULT_CANDIDATES) -> list[dict[str, Any]]:
    """Seeded prompt/retrieval candidates. Deterministic ids and families;
    three of them are seeded to FAIL evaluation and two to CRASH, so X1's
    "every lineage/failure preserved" has real failures to preserve."""
    out: list[dict[str, Any]] = []
    for i in range(count):
        kind = "prompt" if i % 2 == 0 else "retrieval"
        out.append({
            "candidate_id": f"cand-{i:03d}-{kind}",
            "kind": kind,
            "generation": 1 + (i % 3),
            "parent_ids": [] if i < 3 else [f"cand-{(i - 3):03d}-"
                                            f"{'prompt' if (i - 3) % 2 == 0 else 'retrieval'}"],
            "seeded_failure": i % 7 == 3,
            "seeded_crash": i % 11 == 5,
        })
    return out


def eval_substrate(cases: int = 5) -> list[dict[str, Any]]:
    """A stand-in for the existing fidelity/scenario eval substrate: declared
    cases, no clock, no network. Synthetic — sanctioned for plumbing and
    mutants (§8.1), and mechanically incapable of counting toward the §6.2
    minimums (its rows ingest as `synthetic`)."""
    return [{"case_id": f"case-{i:02d}", "weight": 1 + i} for i in range(cases)]


def score_candidate(candidate: Mapping[str, Any], substrate: Sequence[Mapping[str, Any]],
                    *, seed: int) -> float:
    """Deterministic machine score in [0,1) — a digest of declared inputs.
    No RNG, no clock, and no dependence on dict/set iteration order."""
    total = 0.0
    weight_sum = 0.0
    for case in substrate:
        h = CORE.digest({"candidate": candidate["candidate_id"],
                         "case": case["case_id"], "seed": seed})
        total += (int(h[:8], 16) / 0xFFFFFFFF) * case["weight"]
        weight_sum += case["weight"]
    return total / weight_sum


def run_e1(archive: ReferenceArchive, candidates: Sequence[Mapping[str, Any]],
           substrate: Sequence[Mapping[str, Any]], *, seed: int,
           run_id: str = "e1-run-0001",
           drop_failed: bool = False,
           live_surface: Path | None = None,
           mutate_live: bool = False) -> dict[str, Any]:
    """The E1 run: evaluate every candidate against the substrate and archive
    a lineage row for EACH — winners, losers, and crashed runs alike (X1).

    `drop_failed=True` is the sim-1 NEGATIVE CONTROL (the archive drops a
    failed candidate). `mutate_live=True` is the X1 negative control (the run
    writes into the live surface it must only observe).
    """
    if mutate_live and live_surface is not None:
        (Path(live_surface) / "services.yml").write_text(
            "mutated by the E1 run\n", encoding="utf-8")

    results: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("seeded_crash"):
            outcome, score = "crashed", None
        elif candidate.get("seeded_failure"):
            outcome, score = "failed", score_candidate(candidate, substrate, seed=seed)
        else:
            outcome, score = "ranked", score_candidate(candidate, substrate, seed=seed)
        results.append({"candidate": candidate, "outcome": outcome, "score": score})

    archived = 0
    for result in results:
        if drop_failed and result["outcome"] in ("failed", "crashed"):
            continue                      # the mutant's silent lineage loss
        candidate = result["candidate"]
        archive.append(CORE.archive_record(
            candidate_id=candidate["candidate_id"],
            run_id=run_id,
            sequence=0,                   # assigned by the archive
            prev_hash=CORE.ZERO_HASH,     # assigned by the archive
            source_class="arena",
            payload_ref=CORE.content_fingerprint(
                {"candidate": candidate["candidate_id"], "run": run_id}),
            classification="internal",
            decision="allow" if result["outcome"] == "ranked" else "deny",
            parent_ids=candidate.get("parent_ids", []),
            generation=candidate.get("generation", 1),
            operator="e1-generator",
            outcome=result["outcome"],
            outcome_refs=[f"evidence:{candidate['candidate_id']}"],
            cutoff_ts=DEFAULT_CUTOFF,
        ))
        archived += 1

    return {
        "run_id": run_id,
        "seed": seed,
        "candidates": len(candidates),
        "archived": archived,
        "ranked": rank_from_results(results),
        "chain_head": archive.chain_head(),
    }


def rank_from_results(results: Sequence[Mapping[str, Any]]) -> list[str]:
    """Total, deterministic order: score DESC then candidate_id ASC; unscored
    (crashed) candidates rank last but are never dropped."""
    scored = [r for r in results if r.get("score") is not None]
    unscored = [r for r in results if r.get("score") is None]
    ordered = sorted(scored, key=lambda r: (-float(r["score"]),
                                            str(r["candidate"]["candidate_id"])))
    tail = sorted(unscored, key=lambda r: str(r["candidate"]["candidate_id"]))
    return [str(r["candidate"]["candidate_id"]) for r in ordered + tail]


def rerank_from_archive(root: Path, *, substrate_cases: int = 5,
                        seed: int = 20260724,
                        hash_dependent: bool = False) -> list[str]:
    """Re-rank purely from the ARCHIVE + the seeds — the sim-1 determinism
    claim. `hash_dependent=True` is the NEGATIVE CONTROL: it lets set
    iteration order (which varies with PYTHONHASHSEED) decide ties/order."""
    substrate = eval_substrate(substrate_cases)
    rows = [r for r in serve_rows(Path(root))]
    results = []
    for row in rows:
        candidate = {"candidate_id": row["candidate_id"]}
        score = (None if row.get("outcome") == "crashed"
                 else score_candidate(candidate, substrate, seed=seed))
        results.append({"candidate": candidate, "score": score,
                        "outcome": row.get("outcome")})
    if hash_dependent:
        # The escape: order decided by traversing a SET of ids.
        return [cid for cid in {str(r["candidate"]["candidate_id"]) for r in results}]
    return rank_from_results(results)


RERANK_DRIVER = """\
import json, sys
sys.path.insert(0, {tests_dir!r})
import lib_cog5_archive_fixtures as FIX
print(json.dumps(FIX.rerank_from_archive({root!r}, hash_dependent={hash_dependent!r})))
"""


def rerank_under_hashseeds(root: Path, seeds: Sequence[str], *,
                           hash_dependent: bool = False) -> list[list[str]]:
    """Run `rerank_from_archive` in SUBPROCESSES under distinct
    PYTHONHASHSEED values (the §12 sim-1 / sim-8 triple-run discipline —
    hash randomisation is fixed at interpreter start, so it can only be
    exercised out-of-process)."""
    out: list[list[str]] = []
    for seed in seeds:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "PYTHONHASHSEED": str(seed),
               "HOME": os.environ.get("HOME", "/tmp")}
        code = RERANK_DRIVER.format(tests_dir=str(_HERE), root=str(root),
                                    hash_dependent=hash_dependent)
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, env=env, timeout=120)
        if proc.returncode != 0:
            raise ArchiveError(f"rerank subprocess failed (PYTHONHASHSEED="
                               f"{seed}): {proc.stderr.strip()[:400]}")
        out.append(json.loads(proc.stdout))
    return out


def fingerprint_tree(root: Path) -> dict[str, str]:
    """Byte-identity fingerprint over a tree (X1 part (i): the quiescent live
    surfaces an E-run could plausibly touch must be byte-identical after)."""
    root = Path(root)
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = CORE.digest(
                path.read_bytes().decode("utf-8", "replace"))
    return out


def chain_heads_prefix_preserved(before: Sequence[str],
                                 after: Sequence[str]) -> bool:
    """X1 part (ii): ADDITIVE-ONLY — every pre-run chain head remains a
    prefix of the post-run heads (nothing pre-existing modified or deleted)."""
    return list(after[:len(before)]) == list(before)


# ==========================================================================
# §5.3 — duplicate-tolerant ingest + the record_kind field map
# ==========================================================================
def shadow_rows_with_p1_race() -> list[dict[str, Any]]:
    """The P1 shape (review :218): two dispatchers racing ONE log each record
    `would_dispatch` for the SAME idempotency key. Row 0 and row 1 are
    byte-identical bodies (the true duplicate); row 2 shares the key but is a
    DIFFERENT decision (a genuinely distinct fact that must NOT be collapsed).
    """
    base = {"record_kind": "decision", "idempotency_key": "idem-0001",
            "decision": "would_dispatch", "wake_id": "wake-7",
            "manifest": "organ-a"}
    return [
        dict(base),
        dict(base),                                     # the raced duplicate
        {**base, "decision": "would_skip"},             # same key, other fact
        {"record_kind": "run", "mode": "shadow", "reason": "scheduled",
         "wake_id": "wake-7"},
    ]


def strip_chain_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """A row's CONTENT — what it says — with the chain stamps the store added
    when it landed removed (`CHAIN_FIELDS`)."""
    return {key: value for key, value in row.items() if key not in CHAIN_FIELDS}


def dedupe_key(row: Mapping[str, Any], mode: str = "content", *,
               ordinal: int = 0) -> str:
    """The ingest's dedup key under each mode — ONE definition, so the keys
    derived from the TARGET STORE cannot drift from the keys derived from
    incoming candidates (a drift there would silently re-admit everything).

    CHAIN-FIELD INVARIANT, and that is what makes the "ONE definition" claim
    hold when the target store is the DURABLE lineage archive rather than a
    list held in memory. `ReferenceArchive.append` stamps `sequence`,
    `prev_hash`, `record_id` and `row_hash` onto every row it takes, so a row
    read back out of the store is not byte-identical to the row that went in.
    Fingerprinting the row as-read would give it a different key from the same
    fact arriving again — and the whole log would be re-admitted on every
    cycle, which is precisely the MF-2 defect the store-seeded dedup exists to
    close, re-entering through the durable door.

    So the CONTENT key is taken over the row's content, with the store's own
    stamps removed. It loses nothing: those four are position or derivation
    (`CHAIN_FIELDS`), never content. The invariance is deliberately narrow —
    change any content field and the key changes — so this is not a blunt
    instrument that could collapse two genuinely different facts.
    """
    if mode == "content":
        return CORE.content_fingerprint(strip_chain_fields(row))
    if mode == "key":
        return str(row.get("idempotency_key"))
    if mode == "none":
        return f"unique-{ordinal}-{uuid.uuid4().hex}"
    raise ValueError(f"unknown dedupe mode {mode!r}")


def ingest_shadow_rows(rows: Iterable[Mapping[str, Any]], *,
                       source_class: str = "sim",
                       dedupe: str = "content",
                       store: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """§5.3 ingest: field-map the shadow `record_kind`, stamp provenance from
    the SOURCE CLASS, and dedupe by CONTENT FINGERPRINT — recording the
    duplication honestly rather than hiding it.

    `store` is the rows ALREADY HELD BY THE TARGET STORE. §5.3 routes shadow
    accrual through a PERIODIC organ manifest (§11.2), so re-reading a log
    that is still accruing is the NORMAL cadence, not an edge case: cycle 2
    necessarily re-presents every row cycle 1 already took. Dedup keyed only
    within one call therefore re-admits the whole log every cycle.

    WHY THE STORE AND NOT A CALLER-THREADED `seen` SET: this family already
    paid for that answer. `shadow_append_racy` is the recorded P1 defect —
    a caller deciding what to skip from a snapshot it holds OUTSIDE the
    authority, and `shadow_append_folded` is the fix: derive the skip set from
    the STORE, at use. A threaded `seen` set is process-lifetime state that a
    restart silently empties (re-admitting the entire log) and that two
    ingesters cannot share; the store is append-only, durable, and the single
    authority on what has already been taken. So the dedup index is SEEDED
    from the store's own rows, through the same `dedupe_key` the candidates
    go through. `ShadowIngestor` below is the disciplined caller that holds
    the store across cycles; passing `store=()` is a genuine FIRST cycle, not
    an escape — an empty store has no fingerprints to key against.

    THE STORE MAY BE THE DURABLE LINEAGE ARCHIVE, and the API says so rather
    than hoping no caller tries it: rows read back from a `ReferenceArchive`
    carry the chain stamps `append` added, and `dedupe_key` is invariant under
    exactly those (`CHAIN_FIELDS`). So seeding from `serve_rows(archive_root)`
    — or from a restored copy of it — admits each fact exactly once, the same
    as seeding from the in-memory rows. Without that invariance the durable
    path would silently re-admit the whole log every cycle while the in-memory
    path looked correct.

    `dedupe="key"` and `dedupe="none"` are the NEGATIVE CONTROLS: keying on
    the idempotency key collapses two genuinely different facts (data loss);
    no dedup lets the raced duplicate land twice.
    """
    ingested: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for ordinal, present in enumerate(store):
        seen[dedupe_key(present, dedupe, ordinal=ordinal)] = 1
    for row in rows:
        mapped = CORE.map_shadow_record_kind(row)
        mapped = CORE.stamp_provenance(mapped, source_class)
        key = dedupe_key(mapped, dedupe, ordinal=len(ingested))
        if key in seen:
            seen[key] += 1
            duplicates.append({"fingerprint": key, "occurrence": seen[key],
                               "candidate_row": mapped})
            continue
        seen[key] = 1
        ingested.append(mapped)
    return {"ingested": ingested, "duplicates": duplicates,
            "counts": {"ingested": len(ingested),
                       "duplicates_recorded": len(duplicates)}}


class ShadowIngestor:
    """The §5.3/§11.2 PERIODIC ingest cycle, idempotent by construction.

    Holds the target store across cycles and keys every cycle's dedup against
    it, so re-reading an accruing shadow log admits each fact exactly once no
    matter how many times the organ manifest fires. `duplicates` accumulates
    the honest record of what was re-presented and refused.
    """

    def __init__(self, *, source_class: str = "sim",
                 dedupe: str = "content") -> None:
        self.source_class = source_class
        self.dedupe = dedupe
        self.rows: list[dict[str, Any]] = []
        self.duplicates: list[dict[str, Any]] = []

    def ingest(self, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        result = ingest_shadow_rows(rows, source_class=self.source_class,
                                    dedupe=self.dedupe, store=self.rows)
        self.rows.extend(result["ingested"])
        self.duplicates.extend(result["duplicates"])
        return result


def conflating_field_map(shadow_row: Mapping[str, Any]) -> dict[str, Any]:
    """NEGATIVE CONTROL (§5.3): the conflation — the shadow token is left in
    the TRAJECTORY `record_kind` field instead of the archive-native one."""
    return dict(shadow_row)


# ==========================================================================
# the P1 lock-fold rider (§5.3) — read+check+append under ONE lock
# ==========================================================================
def _acquire(lock: Path) -> int:
    try:
        return os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ArchiveError(f"lock held: {lock}") from None


def shadow_append_folded(path: Path, new_rows: Sequence[Mapping[str, Any]], *,
                         dedupe_field: str = "idempotency_key") -> list[str]:
    """The RIDER's target property: the replay/dedupe READ happens INSIDE the
    same lock hold as the append, so two dispatchers cannot each observe a
    pre-write log and both append the same key.

    Returns the keys actually appended.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    fd = _acquire(lock)
    try:
        existing = _read_keys(path, dedupe_field)
        appended: list[str] = []
        payload = ""
        for row in new_rows:
            key = str(row.get(dedupe_field))
            if key in existing:
                continue
            existing.add(key)
            appended.append(key)
            payload += json.dumps(row, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")) + "\n"
        if payload:
            append_exact_line(path, payload)
        return appended
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def shadow_append_racy(path: Path, new_rows: Sequence[Mapping[str, Any]], *,
                       observed_keys: set[str],
                       dedupe_field: str = "idempotency_key") -> list[str]:
    """NEGATIVE CONTROL — TODAY'S SHAPE (cog4-dispatch-shadow.py:859-861 reads
    the replay keys, then :877 calls `append_shadow_log`, which takes the lock
    only for its own write): the caller decides what to skip from a snapshot
    it read OUTSIDE the lock. Two dispatchers each holding a pre-write
    snapshot both append the same key.

    The interleaving is passed in explicitly (`observed_keys`) rather than
    threaded, so the race is reproduced DETERMINISTICALLY — a flaky race test
    proves nothing.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    fd = _acquire(lock)
    try:
        appended: list[str] = []
        payload = ""
        for row in new_rows:
            key = str(row.get(dedupe_field))
            if key in observed_keys:          # the STALE snapshot decides
                continue
            appended.append(key)
            payload += json.dumps(row, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")) + "\n"
        if payload:
            append_exact_line(path, payload)
        return appended
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def _read_keys(path: Path, field: str) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get(field), str):
                keys.add(row[field])
    return keys


def read_log_keys(path: Path, field: str = "idempotency_key") -> list[str]:
    """Every key present in the log, in file order (duplicates included)."""
    out: list[str] = []
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row, dict) and isinstance(row.get(field), str):
                out.append(row[field])
    return out


def shadow_cli_append_folds_read(root: Path | None = None) -> bool:
    """Structural probe of the SHIPPED shadow CLI: does `append_shadow_log`
    perform the replay/dedupe read itself (i.e. under its own lock hold)?

    Today: False — `read_shadow_log` is called at the CLI call site
    (:859-861) BEFORE `append_shadow_log` takes the lock (:625-655). The W4
    rider makes this True. Implemented by AST over file bytes so it reports
    the structure rather than a grep impression.
    """
    import ast as _ast
    source = ((root or CORE.repo_root()) / SHADOW_CLI_REL).read_text(encoding="utf-8")
    tree = _ast.parse(source)
    for node in tree.body:
        if isinstance(node, _ast.FunctionDef) and node.name == "append_shadow_log":
            called = {n.func.id for n in _ast.walk(node)
                      if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)}
            takes_keys = any(a.arg not in ("path", "new_rows")
                             for a in list(node.args.args) + list(node.args.kwonlyargs))
            return "read_shadow_log" in called or takes_keys
    raise ArchiveError("append_shadow_log() not found in the shadow CLI — the "
                       "P1 rider probe has lost its anchor; re-anchor it")


__all__ = [
    "ARCHIVE_MODULE_REL", "EMITTER_MODULE_REL", "RESTORE_CLI_REL",
    "LEAGUE_CLI_REL", "ARCHIVE_ROOT_DEFAULT_REL", "SHADOW_CLI_REL",
    "SEGMENT_DIR", "MANIFEST_NAME", "ANCHOR_NAME", "PENDING_NAME",
    "DEFAULT_ROWS_PER_SEGMENT", "DEFAULT_ANCHOR_EVERY", "DEFAULT_CUTOFF",
    "CHAIN_FIELDS", "strip_chain_fields",
    "fsync_dir", "atomic_write", "append_exact_line", "row_hash",
    "ArchiveError", "ReferenceArchive", "verify_archive", "serve_rows",
    "corrupt_truncate_tail", "corrupt_bitflip_row", "corrupt_forge_prev_hash",
    "corrupt_break_seal", "corrupt_drop_open_segment_tail",
    "corrupt_strip_manifest_declaration", "repair_manifest_counters",
    "corrupt_forge_anchor", "corrupt_drop_anchor", "remint_anchor",
    "seal_and_copy_out", "restore", "archive_report",
    "restore_dropping_row", "restore_reordering_rows",
    "kernel_would_miss_reorder",
    "E1_MIN_CANDIDATES", "E1_DEFAULT_CANDIDATES", "seeded_candidates",
    "eval_substrate", "score_candidate", "run_e1", "rank_from_results",
    "rerank_from_archive", "rerank_under_hashseeds", "fingerprint_tree",
    "chain_heads_prefix_preserved",
    "shadow_rows_with_p1_race", "dedupe_key", "ingest_shadow_rows",
    "ShadowIngestor", "conflating_field_map",
    "shadow_append_folded", "shadow_append_racy", "read_log_keys",
    "shadow_cli_append_folds_read",
]
