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
DEFAULT_CUTOFF = "2026-07-24T00:00:00Z"


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
    manifest-class artifact through the atomic-write replica."""

    def __init__(self, root: Path, *,
                 rows_per_segment: int = DEFAULT_ROWS_PER_SEGMENT,
                 anchor_every: int = 4) -> None:
        self.root = Path(root)
        self.rows_per_segment = int(rows_per_segment)
        self.anchor_every = int(anchor_every)
        (self.root / SEGMENT_DIR).mkdir(parents=True, exist_ok=True)
        if not (self.root / MANIFEST_NAME).exists():
            self._write_manifest({"segments": [], "seals": [],
                                  "chain_head": CORE.ZERO_HASH, "row_count": 0})

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
        The write-ahead is what makes the heal exactly-once possible."""
        event = self._prepare(record)
        self._write_pending(event)
        self._commit(event)
        return event

    def _write_pending(self, event: Mapping[str, Any]) -> None:
        atomic_write(self.root / PENDING_NAME,
                     json.dumps({"event": dict(event)}, ensure_ascii=False,
                                sort_keys=True, indent=2) + "\n")

    def _commit(self, event: Mapping[str, Any]) -> None:
        index = self.open_segment_index()
        if len(self._segment_rows(index)) >= self.rows_per_segment:
            self.seal_segment(index)
            index += 1
        append_exact_line(
            self.segment_path(index),
            json.dumps(event, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n")
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
        cleared — the case a naive heal duplicates."""
        event = self._prepare(record)
        self._write_pending(event)
        index = self.open_segment_index()
        if len(self._segment_rows(index)) >= self.rows_per_segment:
            self.seal_segment(index)
            index += 1
        append_exact_line(
            self.segment_path(index),
            json.dumps(event, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n")
        self._refresh_manifest()
        return event

    # -- the exactly-once heal (recorder :625-670 shape) ------------------
    def heal(self) -> dict[str, Any] | None:
        """Finish an interrupted append EXACTLY ONCE.

        Returns the reconciled event when an unreconciled pending.json was
        found, and None when there was nothing to reconcile. The caller never
        infers an interruption from anything else.
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
            self._refresh_manifest()
            pending_path.unlink(missing_ok=True)
            fsync_dir(self.root)
        else:
            raise ArchiveError("pending_sequence")
        return event

    # -- anchors + seals --------------------------------------------------
    def write_anchor(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """Periodic attestation over the chain head (recorder :599-608 shape,
        minus the signer — signing is the recorder's, not the archive's)."""
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
    """Full chain + seal verification.

    Returns {"ok", "findings", "verified_rows", "last_good_seal",
    "safe_sequence"} — `safe_sequence` is the highest sequence a disciplined
    reader may serve: the last good SEAL's last_sequence when anything beyond
    it is broken (§12 sim 9, "serve refuses beyond the last good seal").
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

    ok = not findings
    if ok:
        safe_sequence = expected_sequence - 1
    else:
        safe_sequence = int(last_good_seal["last_sequence"]) if last_good_seal else 0
    return {"ok": ok, "findings": findings, "verified_rows": verified_rows,
            "last_good_seal": last_good_seal, "safe_sequence": safe_sequence}


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
    return archive_report(archive.root)


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


def ingest_shadow_rows(rows: Iterable[Mapping[str, Any]], *,
                       source_class: str = "sim",
                       dedupe: str = "content") -> dict[str, Any]:
    """§5.3 ingest: field-map the shadow `record_kind`, stamp provenance from
    the SOURCE CLASS, and dedupe by CONTENT FINGERPRINT — recording the
    duplication honestly rather than hiding it.

    `dedupe="key"` and `dedupe="none"` are the NEGATIVE CONTROLS: keying on
    the idempotency key collapses two genuinely different facts (data loss);
    no dedup lets the raced duplicate land twice.
    """
    ingested: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for row in rows:
        mapped = CORE.map_shadow_record_kind(row)
        mapped = CORE.stamp_provenance(mapped, source_class)
        if dedupe == "content":
            key = CORE.content_fingerprint(mapped)
        elif dedupe == "key":
            key = str(mapped.get("idempotency_key"))
        elif dedupe == "none":
            key = f"unique-{len(ingested)}-{uuid.uuid4().hex}"
        else:
            raise ValueError(f"unknown dedupe mode {dedupe!r}")
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
    "DEFAULT_ROWS_PER_SEGMENT", "DEFAULT_CUTOFF",
    "fsync_dir", "atomic_write", "append_exact_line", "row_hash",
    "ArchiveError", "ReferenceArchive", "verify_archive", "serve_rows",
    "corrupt_truncate_tail", "corrupt_bitflip_row", "corrupt_forge_prev_hash",
    "corrupt_break_seal", "seal_and_copy_out", "restore", "archive_report",
    "restore_dropping_row", "restore_reordering_rows",
    "kernel_would_miss_reorder",
    "E1_MIN_CANDIDATES", "E1_DEFAULT_CANDIDATES", "seeded_candidates",
    "eval_substrate", "score_candidate", "run_e1", "rank_from_results",
    "rerank_from_archive", "rerank_under_hashseeds", "fingerprint_tree",
    "chain_heads_prefix_preserved",
    "shadow_rows_with_p1_race", "ingest_shadow_rows", "conflating_field_map",
    "shadow_append_folded", "shadow_append_racy", "read_log_keys",
    "shadow_cli_append_folds_read",
]
