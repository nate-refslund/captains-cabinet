#!/usr/bin/env python3.12
"""update_bundle.py — digests, diff and plan for the Cabinet update path.

WHAT THIS IS FOR. An installed Cabinet is an unpacked export with no version
control in it: nothing in the tree can answer "what changed since the bytes I
am running". This module answers that from DECLARED data — a bundle manifest
cut at export time (per-file sha256), the manifest of the last bundle this
install applied, and the boundary + preserve declarations the install itself
ships. cabinet/scripts/cabinet-update.sh owns the flow; every computation that
decides what may be written, deleted or refused lives here, where it can be
tested.

FIVE DECISIONS, and why each is shaped the way it is.

1. THE DELETION SET IS MANIFEST-TO-MANIFEST, NEVER BUNDLE-TO-INSTALLED.
   A bundle is a scrubbed export: it contains no `instance/` path at all (the
   export manifest deletes 29 of them). Diffing "what the bundle has" against
   "what the install has" would therefore mark the operator's entire instance
   tree for deletion. So deletions are exactly
   `previous_manifest.files - new_manifest.files` — a path this install was
   SHIPPED once and is not shipped now. An install with no applied manifest
   (the first apply, and every install that has never taken an update) deletes
   NOTHING. That is not a gap; it is the only honest answer available.

2. THE PRESERVE SET IS DECLARED DATA, PARSED AT RUN TIME. It is the union of
   the shipped `cabinet/config/egg-preserve-set.txt` (generated at export time
   from the export manifest's own `delete instance/...` rules plus the
   interface ledgers the export EMPTIES), the bundle's copy of the same file,
   and `runtime-provision.sh lists` where that script is present. A path in the
   set is never written and never deleted. A bundle that SHIPS a preserved path
   is not an error and not silently dropped: it is reported as
   `skipped_preserved`, because an operator whose live veto ledger was not
   overwritten deserves to be told so.

3. THE LOCKED SET COMES FROM THE INSTALLED BOUNDARY SCRIPT, NOT THE BUNDLE.
   `germline-lock.sh` FILES/DIRS is parsed out of the array literals the way
   cabinet-doctor.sh §10 does — regex extraction, never `source` (the script
   runs `cd` and `case` logic on load). DIRS match by prefix, because the lock
   is applied with `chflags -R`. The bundle carries a `locked_set` field too;
   it is INFORMATIONAL. A bundle that could name its own boundary could widen
   it. Unparseable or absent ⇒ refuse: an empty locked set read as "nothing is
   locked" is the fail-open this whole path exists to avoid.

4. ABSENCE IS NEVER A PASS. Every parse here raises `BundleError` rather than
   returning an empty set. A preserve set that came back empty because a file
   was missing, or a locked set that came back empty because a regex drifted,
   would both read as "go ahead" — the degenerate end of exactly the class this
   program has paid for repeatedly.

5. A RECORD IS NEVER LOST TO THE ENVIRONMENT IT LANDS IN. The last section of
   this module is the updater's own state writer and event recorder (A5.15,
   A5.16). A refusal is written to `.updates/state.json` where every surface
   can read it, and an event the INSTALLED emitter will not accept — the
   measured case: an install cut before the update path existed does not know
   the type of the event announcing it — is held in `.updates/events.jsonl` and
   replayed by the next apply, at most once per COMPLETED replay and at least
   once across a crash (the boundary is stated where the replay is written, and
   the choice is deliberate). Neither path can raise: losing the record of what
   the updater did is worse than any error it could report.

Read-only except for `apply-plan` and `restore` (the two content writers, which
take an explicit snapshot directory) and the state/record writers named in 5,
which write only under `.updates/`.

Interpreter: python3.12 (this module is not on the locked hook's import path).
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

MANIFEST_SCHEMA = "cabinet-update-bundle/v1"
SNAPSHOT_SCHEMA = "cabinet-update-snapshot/v1"

#: The interface ledgers the export ships as header-only. Kept here as well as
#: in egg-export.sh because this side has to know them even when the exporter
#: is absent — the exporter does not ship (it is private-side prep), so an
#: installed Cabinet can only learn them from the generated preserve-set file
#: or from this constant.
HEADER_ONLY_INTERFACES = (
    "shared/interfaces/captain-vetoes.yml",
    "shared/interfaces/captain-rules-index.yaml",
    "shared/interfaces/captain-knowledge-classification.yml",
)

PRESERVE_SET_REL = "cabinet/config/egg-preserve-set.txt"
GERMLINE_LOCK_REL = "cabinet/scripts/germline-lock.sh"
RUNTIME_PROVISION_REL = "cabinet/scripts/runtime-provision.sh"
EGG_MANIFEST_REL = "egg-manifest.json"


class BundleError(RuntimeError):
    """The updater could not establish a fact. Never a synonym for "nothing to do"."""


# ---------------------------------------------------------------------------
# digests
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digests(root: Path) -> dict[str, str]:
    """Every regular file under `root`, repo-relative path -> sha256.

    Symlinks are skipped and reported by the caller's own verification: a
    bundle is a `git archive` cut plus file transforms, so a symlink in it is
    a packaging defect rather than content to copy.
    """

    root = root.resolve()
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            if full.is_symlink() or not full.is_file():
                continue
            files[str(full.relative_to(root))] = sha256_file(full)
    return files


# ---------------------------------------------------------------------------
# the locked set (INSTALLED germline-lock.sh FILES + DIRS)
# ---------------------------------------------------------------------------

_ARRAY_ENTRY = re.compile(r'^\s*"([^"]+)"')


def parse_locked_set(script: Path) -> dict[str, list[str]]:
    """FILES + DIRS out of the array literals, the cabinet-doctor.sh §10 way."""

    if not script.is_file():
        raise BundleError(
            f"locked-set source missing: {script} — refusing to apply without a "
            "boundary to check against"
        )
    text = script.read_text(encoding="utf-8", errors="replace").splitlines()
    out: dict[str, list[str]] = {}
    for name in ("FILES", "DIRS"):
        entries: list[str] = []
        raw_lines = 0
        inside = False
        for line in text:
            if not inside:
                if line.startswith(f"{name}=("):
                    inside = True
                continue
            if line.startswith(")"):
                break
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                raw_lines += 1
            match = _ARRAY_ENTRY.match(line)
            if match:
                entries.append(match.group(1))
        if not inside:
            raise BundleError(f"could not find the {name}=( ) array in {script}")
        if not entries:
            raise BundleError(f"{name}=( ) in {script} parsed to zero entries")
        if len(entries) != raw_lines:
            # The cabinet-doctor §10 drift tripwire, restated: a partial parse
            # is a SMALLER boundary, and a smaller boundary silently permits
            # exactly the writes this refusal exists for.
            raise BundleError(
                f"parser drift in {script}: extracted {len(entries)} of {raw_lines} "
                f"{name} entry lines (unquoted or single-quoted entries are invisible)"
            )
        out[name.lower()] = entries
    return out


def is_locked(rel: str, locked: dict[str, list[str]]) -> bool:
    if rel in locked.get("files", ()):
        return True
    for directory in locked.get("dirs", ()):
        if rel == directory or rel.startswith(directory.rstrip("/") + "/"):
            return True
    return False


# ---------------------------------------------------------------------------
# the preserve set
# ---------------------------------------------------------------------------

def _read_preserve_file(path: Path) -> list[str]:
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def parse_provision_lists(script: Path) -> list[str]:
    """The install's persistence declaration, through its own read interface.

    `runtime-provision.sh lists` prints `<kind> <path>` records and exists for
    exactly this caller. ASKING IT is the whole point: a second parser of the
    same declaration is a second thing to keep in step, and the copy is always
    the one that goes stale — which is what the amendment that added the
    subcommand set out to end.

    The text parse below is the documented FALLBACK, for an installed Cabinet
    whose script will not run on this box (no bash, a partial export, a
    provisioning script from a future version that exits non-zero on an
    argument it does not know). Either way an unparseable declaration RAISES:
    "no declaration" must never read as "nothing to preserve".
    """

    if not script.is_file():
        return []
    entries = _provision_lists_subcommand(script)
    if entries:
        return entries
    text = script.read_text(encoding="utf-8", errors="replace")
    entries: list[str] = []
    found = 0
    for name in (
        "INSTANCE_PERSISTENT_DIRS",
        "INSTANCE_PERSISTENT_SEEDED_DIRS",
        "INSTANCE_PERSISTENT_FILES",
    ):
        match = re.search(rf'^{name}="([^"]*)"', text, re.MULTILINE)
        if not match:
            continue
        found += 1
        entries.extend(part for part in match.group(1).split() if part)
    if found == 0:
        raise BundleError(
            f"{script} neither answers `lists` nor carries the "
            "INSTANCE_PERSISTENT_* declarations — an unreadable list must "
            "never read as an empty list"
        )
    return entries


def _provision_lists_subcommand(script: Path) -> list[str]:
    """`bash <script> lists` -> the declared paths. [] when it cannot answer."""

    try:
        completed = subprocess.run(
            ["bash", str(script), "lists"],
            capture_output=True, text=True, timeout=30, cwd=str(script.parent),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    entries: list[str] = []
    for line in completed.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        kind, rel = parts[0].strip(), parts[1].strip()
        if kind in ("dirs", "seeded_dirs", "files") and rel:
            entries.append(rel)
    return entries


def preserve_set(install_root: Path, bundle_tree: Path | None = None) -> list[str]:
    """The union, per the update contract. Absent on BOTH sides ⇒ refuse."""

    entries: list[str] = []
    sources = 0
    for candidate in (install_root / PRESERVE_SET_REL,
                      (bundle_tree / PRESERVE_SET_REL) if bundle_tree else None):
        if candidate is not None and candidate.is_file():
            sources += 1
            entries.extend(_read_preserve_file(candidate))
    if sources == 0:
        raise BundleError(
            f"no {PRESERVE_SET_REL} on either side — the updater cannot tell the "
            "operator's own data from shipped content, so it refuses rather than "
            "guessing"
        )
    entries.extend(parse_provision_lists(install_root / RUNTIME_PROVISION_REL))
    entries.extend(HEADER_ONLY_INTERFACES)
    return sorted(set(entries))


def is_preserved(rel: str, entries: Iterable[str]) -> bool:
    for entry in entries:
        entry = entry.rstrip("/")
        if not entry:
            continue
        if rel == entry or rel.startswith(entry + "/"):
            return True
        if ("*" in entry or "?" in entry or "[" in entry) and fnmatch.fnmatch(rel, entry):
            return True
    return False


# ---------------------------------------------------------------------------
# manifests
# ---------------------------------------------------------------------------

def build_manifest(
    tree: Path,
    source_sha: str,
    built_at: str,
    changelog: list[str],
    locked_set: dict[str, list[str]] | None,
    from_sha: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA,
        "source_sha": source_sha,
        "built_at": built_at,
        "from_sha": from_sha,
        "files": tree_digests(tree),
        "locked_set": locked_set or {"files": [], "dirs": []},
        "changelog": changelog,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BundleError(f"unreadable bundle manifest {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise BundleError(f"bundle manifest {path} is not an object")
    if document.get("schema_version") != MANIFEST_SCHEMA:
        raise BundleError(
            f"bundle manifest {path} has schema_version "
            f"{document.get('schema_version')!r}, expected {MANIFEST_SCHEMA!r}"
        )
    files = document.get("files")
    if not isinstance(files, dict) or not files:
        raise BundleError(f"bundle manifest {path} carries no files — refusing")
    for key in ("source_sha", "built_at"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            raise BundleError(f"bundle manifest {path} is missing {key}")
    return document


def verify_tree(tree: Path, manifest: dict[str, Any]) -> list[str]:
    """Per-file digest verification. Returns the mismatching paths."""

    bad: list[str] = []
    for rel, expected in sorted(manifest["files"].items()):
        candidate = tree / rel
        if not candidate.is_file() or candidate.is_symlink():
            bad.append(f"{rel}: missing from the bundle tree")
            continue
        actual = sha256_file(candidate)
        if actual != expected:
            bad.append(f"{rel}: sha256 {actual} != manifest {expected}")
    return bad


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

def build_plan(
    install_root: Path,
    bundle_tree: Path,
    manifest: dict[str, Any],
    previous_manifest: dict[str, Any] | None,
    preserve: list[str],
    locked: dict[str, list[str]],
) -> dict[str, Any]:
    new_files: dict[str, str] = manifest["files"]
    previous_files = set((previous_manifest or {}).get("files", {}))

    # THE RAW SETS FIRST — what this bundle would change and delete if nothing
    # were protected. The two filters below run over them in a fixed order, and
    # the order is the whole point: LOCKED beats PRESERVED.
    #
    # Two of the locked FILES are also in the generated preserve set
    # (`instance/config/egress.yml`, `instance/config/act-first-surfaces.yml`).
    # Filtering preserved paths first made a bundle that ships a changed copy of
    # either read as a routine `skipped_preserved` while the rest of the bundle
    # applied — the constitutional refusal §5 requires, downgraded to a note
    # nobody reads. Nothing was written either way, so the fail-closed property
    # held; the SIGNAL was lost, and a boundary nobody is told about is a
    # boundary that erodes.
    unchanged = 0
    raw_changed: list[str] = []
    for rel in sorted(new_files):
        installed = install_root / rel
        if installed.is_file() and not installed.is_symlink():
            if sha256_file(installed) == new_files[rel]:
                unchanged += 1
                continue
        raw_changed.append(rel)

    raw_deleted = [rel for rel in sorted(previous_files - set(new_files))
                   if (install_root / rel).exists()]

    locked_hits = sorted(
        rel for rel in set(raw_changed) | set(raw_deleted) if is_locked(rel, locked)
    )

    changed: list[str] = []
    deleted: list[str] = []
    skipped_preserved: list[str] = []
    for rel in raw_changed:
        (skipped_preserved if is_preserved(rel, preserve) else changed).append(rel)
    for rel in raw_deleted:
        (skipped_preserved if is_preserved(rel, preserve) else deleted).append(rel)
    return {
        "to_sha": manifest["source_sha"],
        "from_sha": installed_source_commit(install_root),
        "changed": changed,
        "deleted": deleted,
        "unchanged": unchanged,
        "skipped_preserved": sorted(set(skipped_preserved)),
        "locked_hits": locked_hits,
        "first_apply": previous_manifest is None,
    }


def installed_source_commit(install_root: Path) -> str | None:
    path = install_root / EGG_MANIFEST_REL
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = document.get("source_commit")
    return value if isinstance(value, str) and value.strip() else None


# ---------------------------------------------------------------------------
# the two writers
# ---------------------------------------------------------------------------

def snapshot(install_root: Path, plan: dict[str, Any], snapshot_dir: Path) -> dict[str, Any]:
    """Pre-images of every path the plan touches. Absent paths are RECORDED.

    A rollback that only restored bytes would leave every newly-created file
    behind — a tree that is neither the old one nor the new one. The absent
    list is what makes the restore exact.
    """

    tree_dir = snapshot_dir / "tree"
    present: list[str] = []
    absent: list[str] = []
    for rel in sorted(set(plan["changed"]) | set(plan["deleted"])):
        source = install_root / rel
        if source.is_file() and not source.is_symlink():
            target = tree_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            present.append(rel)
        else:
            absent.append(rel)
    record = {
        "schema_version": SNAPSHOT_SCHEMA,
        "from_sha": plan.get("from_sha"),
        "to_sha": plan.get("to_sha"),
        "present": present,
        "absent": absent,
    }
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "snapshot.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / (target.name + ".update-tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, target)


def apply_plan(
    install_root: Path,
    bundle_tree: Path,
    plan: dict[str, Any],
    kill_after: int | None = None,
) -> dict[str, Any]:
    """Write the changed paths and remove the deletion set. tmp + rename each.

    `kill_after` is the mid-apply kill seam: after N writes the process kills
    ITSELF with SIGKILL, leaving `state.json` at `applying` and the snapshot on
    disk. It exists so the resume path can be proven rather than asserted.
    """

    written = 0
    for rel in plan["changed"]:
        _atomic_copy(bundle_tree / rel, install_root / rel)
        written += 1
        if kill_after is not None and written >= kill_after:
            sys.stderr.write(
                f"update_bundle: test kill seam fired after {written} writes\n"
            )
            sys.stderr.flush()
            os.kill(os.getpid(), 9)
    removed = 0
    for rel in plan["deleted"]:
        target = install_root / rel
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return {"written": written, "removed": removed}


def restore(install_root: Path, snapshot_dir: Path) -> dict[str, Any]:
    record_path = snapshot_dir / "snapshot.json"
    if not record_path.is_file():
        raise BundleError(f"snapshot has no snapshot.json: {snapshot_dir}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema_version") != SNAPSHOT_SCHEMA:
        raise BundleError(f"unsupported snapshot schema in {record_path}")
    tree_dir = snapshot_dir / "tree"
    restored = 0
    for rel in record.get("present", []):
        source = tree_dir / rel
        if not source.is_file():
            raise BundleError(f"snapshot is incomplete — {rel} is not in {tree_dir}")
        _atomic_copy(source, install_root / rel)
        restored += 1
    removed = 0
    for rel in record.get("absent", []):
        target = install_root / rel
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return {"restored": restored, "removed": removed, "record": record}


# ---------------------------------------------------------------------------
# the durable state file, the recorder, and the deferred-record ingest
# ---------------------------------------------------------------------------
#
# TWO DEFECTS FROM THE FIRST APPLY ON A REAL INSTALL (2026-09-08), and the one
# shape that answers both: the updater must be able to write down what happened
# WITHOUT depending on anything the update itself is carrying.
#
# A5.15 — A REFUSAL WAS INVISIBLE. The first real apply refused exactly as
# designed (one constitutional path differed) and then left no state at all:
# `status --json` answered `phase: idle, last: null`, so the home card would
# have offered "Update ready" for that same bundle for ever, and the only
# record anywhere was one line in a log file. A refusal that nothing can read
# is the same silence the whole update path exists to end.
#
# A5.16 — THE LEDGER DID NOT KNOW THE EVENT KIND YET. The INSTALLED emitter
# predated the update path and raised `ValueError: Unknown event type:
# cabinet_update_refused`, so nothing was recorded there either. Two
# independent surfaces, silent on the same event. And this is not a one-off:
# the first apply on ANY install cut before the update path landed hits it,
# because the emitter that knows `cabinet_update_applied` arrives WITH the
# update it is supposed to announce — a bootstrap ordering hole, not a bug in
# the emitter. So the recorder holds the record in `<root>/.updates/
# events.jsonl` instead of losing it, and the next apply — running with the
# newer emitter already in place — replays it into the ledger exactly once.
#
# WHY ONCE IS BY ID AND NOT BY THE FILENAME. Renaming the sidecar after a
# successful ingest is the cheap half and it is not enough: a torn write, a
# partial ingest, or an operator restoring a copy of the file replays every row
# in it a second time. Each held record therefore carries its own id, the
# ingested ids are appended to a marker before the rename, and a row whose id
# is already in the marker is skipped. The rename is hygiene; the marker is the
# property.
#
# AND IT IS AT-LEAST-ONCE AT THE CRASH BOUNDARY — stated rather than glossed,
# because "exactly once" is a claim a reader will build on. The marker id is
# written AFTER the emit, so a crash in between replays that one row on the
# next pass and the ledger carries it twice. The other order was considered and
# rejected: marking first turns the same crash into a record that never reaches
# the ledger at all and can no longer be found, and this module's one guarantee
# is that no record is lost. A duplicate is visible, deduplicable by
# `deferred_record_id`, and recoverable; a hole is neither.

DEFERRED_EVENTS_REL = ".updates/events.jsonl"
INGESTED_IDS_REL = ".updates/events.ingested"
STATE_REL = ".updates/state.json"
STATE_LOCK_REL = ".updates/.state.lock"

#: Fields that survive a whole-document state write. `last_refusal` is here
#: because every other write to the state file REPLACES it: without the carry
#: a refusal would be forgotten the moment anything else happened, and the card
#: would offer the refused bundle again the next time some other apply landed.
CARRIED_STATE_FIELDS = ("last_refusal",)


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


#: Re-entrancy for `_state_lock`. flock(2) conflicts between two open file
#: DESCRIPTIONS, including two in the same process, so a nested acquire would
#: block against itself for the whole timeout. Nothing nests today; this is
#: what keeps that from becoming a fifteen-second hang the first time it does.
_STATE_LOCK_DEPTH = 0


@contextlib.contextmanager
def _state_lock(install_root: Path, timeout: float = 15.0):
    """Make the read-modify-write of `state.json` one indivisible step.

    A LOCK OF ITS OWN, not `.updates/.lock`: the caller that needs this most is
    the busy refusal, which runs precisely BECAUSE it could not take the
    updater lock. A refusal that had to hold that lock to write itself down
    could never be written at all — the record would be lost in exactly the
    case it exists for.

    Found in review 2026-09-08: `record_refusal` read the document, the updater
    it lost to finished and wrote `applied`, and the refusal wrote its stale
    copy back — `phase: applying` plus a snapshot name over an apply that had
    SUCCEEDED, which the next run reads as an interrupted apply and restores
    from, undoing it. The `phase != applying` guard is check-then-act, so it
    goes inside this too rather than beside it.

    FAIL-OPEN and bounded. A lock that cannot be taken — a read-only
    `.updates/`, a holder that never exits — must not cost the write: a state
    file that never got written is how an interrupted apply becomes
    unrecoverable, which is the same reason cabinet-update.sh keeps a direct
    write behind its helper. So this waits `timeout` seconds and then proceeds
    unlocked rather than hanging or raising."""

    global _STATE_LOCK_DEPTH
    if _STATE_LOCK_DEPTH:
        yield
        return
    import fcntl

    handle = None
    try:
        path = install_root / STATE_LOCK_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
    except OSError:
        handle = None
    if handle is not None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
    _STATE_LOCK_DEPTH += 1
    try:
        yield
    finally:
        _STATE_LOCK_DEPTH -= 1
        if handle is not None:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                os.close(handle)


def read_state(install_root: Path) -> dict[str, Any]:
    """The state document, or {} — never an exception. A state file that
    cannot be read is not a reason to lose the write that is about to happen."""

    path = install_root / STATE_REL
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def _write_state_document(install_root: Path, document: dict[str, Any]) -> dict[str, Any]:
    path = install_root / STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".update-tmp")
    tmp.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return document


def write_state(install_root: Path, document: dict[str, Any]) -> dict[str, Any]:
    """Replace the state document, carrying `CARRIED_STATE_FIELDS` forward.

    Under `_state_lock`: the carry is a read of the previous document, so this
    is a read-modify-write like every other writer here and races the same way."""

    with _state_lock(install_root):
        previous = read_state(install_root)
        merged = dict(document)
        for field in CARRIED_STATE_FIELDS:
            if field not in merged and field in previous:
                merged[field] = previous[field]
        return _write_state_document(install_root, merged)


def update_state(install_root: Path, **fields: Any) -> dict[str, Any]:
    """Merge fields into the state document without disturbing the rest."""

    with _state_lock(install_root):
        document = read_state(install_root)
        document.update(fields)
        return _write_state_document(install_root, document)


def deferred_events_path(install_root: Path) -> Path:
    return install_root / DEFERRED_EVENTS_REL


def _append_deferred(install_root: Path, event: dict[str, Any]) -> None:
    """One record, one line, one write(2) on an O_APPEND descriptor.

    Append-only and never rewritten: two updaters cannot interleave a partial
    line, and a reader that arrives mid-write sees whole records or nothing."""

    path = deferred_events_path(install_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(event, sort_keys=True) + "\n").encode("utf-8")
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(handle, line)
        os.fsync(handle)
    finally:
        os.close(handle)


def read_deferred_events(install_root: Path) -> list[dict[str, Any]]:
    return _read_event_rows(deferred_events_path(install_root))


def _read_event_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("id") and row.get("event_type"):
            rows.append(row)
    return rows


def _installed_emit(install_root: Path):
    """The INSTALLED emitter's `emit`, imported from the install root.

    Deliberately the install's copy and not this repository's: the whole point
    is to find out what the emitter ON THIS BOX accepts. `sys.path` is prefixed
    with the root because this module also runs from `<root>/.updates/run/lib/`,
    where the interpreter's own path entry points at the run directory."""

    root = str(install_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from framework.events.emitter import emit  # noqa: PLC0415  (deliberately late)

    return emit


def _is_version_skew(exc: BaseException) -> bool:
    """Is this the failure the NEXT UPDATE fixes by construction?

    Exactly two are, and they are the two A5.16 was written for: an emitter
    that does not know this event type yet (measured 2026-09-08 —
    `ValueError: Unknown event type: cabinet_update_refused`, because the
    emitter that knows the update events arrives WITH the update) and an
    install whose `framework/` has not arrived at all (`ImportError`).

    Everything else is a FAULT — a full disk, a permission, a ledger that will
    not open — and no update files it. The recorder catches all of them alike,
    which is correct and must stay that way: nothing may cost the record. What
    is not correct is telling the operator that a broken disk is a version
    number, which is what one sentence for both cases did. This is the whole of
    the difference, in one place, so no surface can classify it differently."""

    if isinstance(exc, ImportError):
        return True
    return isinstance(exc, ValueError) and "unknown event type" in str(exc).lower()


#: The refusal record's own fields, and the whole of what any reader uses.
REFUSAL_FIELDS = ("bundle", "reason", "paths", "ts", "door")

#: The three receipts the update path writes. The ledger is the SECOND channel
#: a refusal lands in; `state.json` is the first.
UPDATE_RECEIPT_TYPES = (
    "cabinet_update_applied",
    "cabinet_update_refused",
    "cabinet_update_rolled_back",
)


def _receipt_rows(install_root: Path, days: int = 30) -> list[dict[str, Any]]:
    """Every update receipt in the recent window, oldest first."""

    import datetime as _dt

    root = str(install_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from framework.events.emitter import replay  # noqa: PLC0415  (deliberately late)

    since = (_dt.datetime.now(_dt.timezone.utc)
             - _dt.timedelta(days=days)).isoformat()
    return replay(since=since, event_types=list(UPDATE_RECEIPT_TYPES))


def current_receipt_refusal(install_root: Path, days: int = 30) -> dict[str, Any] | None:
    """The LEDGER's current refusal, in `last_refusal` shape, or None.

    CURRENCY IS THE RECEIPT SPELLING OF `phase: refused`. A refusal is the news
    until something else happens TO THAT BUNDLE, so a later receipt about the
    same bundle overtakes it exactly as a later phase does. A receipt naming no
    bundle cannot be scoped to one and is not resolvable — `refuse_busy` with
    no sha writes one, and both readers reject such a record anyway.

    Fail-open like everything else on this path: a ledger this cannot read is
    silence, never a guess."""

    try:
        rows = _receipt_rows(install_root, days)
    except Exception:  # noqa: BLE001 — a ledger that cannot be read is silence
        return None
    newest = -1
    for index, row in enumerate(rows):
        if row.get("event_type") == "cabinet_update_refused":
            newest = index
    if newest < 0:
        return None
    payload = rows[newest].get("payload") or {}
    bundle = str(payload.get("to_sha") or "")
    if not bundle:
        return None
    for row in rows[newest + 1:]:
        if str((row.get("payload") or {}).get("to_sha") or "") == bundle:
            return None
    return {
        "bundle": bundle,
        "reason": str(payload.get("reason") or ""),
        "paths": [str(entry) for entry in (payload.get("locked_paths") or [])],
        "ts": str(rows[newest].get("created_at") or ""),
        "door": str(payload.get("door") or ""),
    }


def resolve_last_refusal(install_root: Path,
                         state: dict[str, Any] | None = None
                         ) -> tuple[dict[str, Any] | None, str]:
    """THE ONE REFUSAL EVERY SURFACE READS, and the channel it came from.

    A refusal is written down twice by one call — `state.json` and the ledger
    receipt — and either half can be the only one that survives: the state
    write can fail (`state_error`, below), the file can be truncated or
    removed, and an install whose emitter predates the update path refuses the
    event kind outright (A5.16). Until 2026-09-09 `status --json` read only the
    first, so the home card — whose only input is this report — could not see a
    refusal that reached only the second, and offered Apply on a bundle this
    box had already turned down for constitutional paths.

    The state file wins when it has a record: it is this box's account of
    itself, and the ledger may carry a row the sidecar replayed late. The
    briefing resolves the same two channels the same way in
    `run_briefing._update_resolved_refusal` — a deliberate twin rather than an
    import, because a briefing may not shell out and `framework/` does not
    import from `cabinet/`; the two are pinned against each other by
    `framework/frontdoor/tests/update_surface_oracle.json`, which both drive."""

    if state is None:
        state = read_state(install_root)
    record = state.get("last_refusal")
    if isinstance(record, dict) and record.get("bundle"):
        return record, "state"
    if state.get("phase") == "refused" and state.get("bundle"):
        # `record_refusal` writes `last_refusal` AND the top-level copy in one
        # indivisible step, so the two are the same record. A document carrying
        # only the second — truncated, hand-edited — used to be visible to the
        # briefing and invisible to the card, which reads `last_refusal` alone.
        return {field: state.get(field) for field in REFUSAL_FIELDS}, "state"
    record = current_receipt_refusal(install_root)
    return (record, "receipt") if record else (None, "")


def record_event(
    install_root: Path,
    event_type: str,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record an update event. NEVER raises, and never drops the record.

    The ledger first. Anything at all in the way of that — an event type this
    install's emitter does not know (the measured case), no `framework` at all,
    a ledger that will not open — and the identical record is held in the
    sidecar for the next apply to replay. The return says which happened, so
    the caller can say so out loud rather than reporting a success it did not
    have."""

    import uuid

    event = {
        "id": uuid.uuid4().hex,
        "event_type": event_type,
        "actor": actor,
        "payload": payload or {},
        "ts": _utc_now(),
    }
    outcome: dict[str, Any] = {"recorded": "ledger", "id": event["id"],
                               "event_type": event_type}
    try:
        _installed_emit(install_root)(event_type, actor, event["payload"])
    except Exception as exc:  # noqa: BLE001 — every failure keeps the record
        _append_deferred(install_root, event)
        outcome["recorded"] = "fallback"
        outcome["why"] = "%s: %s" % (type(exc).__name__, exc)
        outcome["fault"] = not _is_version_skew(exc)
    try:
        # `ledger_error` is the discriminator every surface reads, and it is a
        # fact about the LAST attempt rather than an alarm that sticks: a
        # ledger that starts working clears it, because a card still saying "go
        # and look at the disk" about a disk that is fine is the same defect as
        # the wrong label the other way.
        update_state(install_root,
                     event_fallback=deferred_events_path(install_root).is_file(),
                     ledger_error=outcome["why"] if outcome.get("fault") else "")
    except Exception as exc:  # noqa: BLE001 — the record is already safe; say
        # so out loud instead. `ledger_error` names a ledger that failed and
        # nothing named a STATE FILE that failed, which is the very failure
        # that leaves a refusal in the ledger alone.
        outcome["state_error"] = "%s: %s" % (type(exc).__name__, exc)
    return outcome


def record_refusal(
    install_root: Path,
    bundle: str,
    reason: str,
    paths: list[str],
    door: str,
    actor: str,
) -> dict[str, Any]:
    """A refusal, written where every surface can read it (A5.15).

    `last_refusal` is always set and survives later writes. `phase` moves to
    `refused` too — EXCEPT over an interrupted apply, and that exception is the
    whole care of this function: `phase: applying` plus a snapshot name is the
    only marker saying a tree is half-written and which snapshot puts it back.
    A busy refusal arriving while the first updater is still working would
    otherwise stamp `refused` over it and turn a recoverable interruption into
    a tree that is neither version with nothing left to say so."""

    refusal = {
        "bundle": bundle,
        "reason": reason,
        "paths": list(paths),
        "ts": _utc_now(),
        "door": door,
    }
    outcome = record_event(install_root, "cabinet_update_refused", actor, {
        "to_sha": bundle,
        "reason": reason,
        "locked_paths": list(paths),
        "door": door,
    })
    # One indivisible step, guard included: the winner may land between a read
    # and a write here, and a `phase` decided on a document that is already
    # stale is how a busy refusal reverted a completed apply (round-1 review).
    document: dict[str, Any] = {}
    try:
        with _state_lock(install_root):
            document = read_state(install_root)
            document["last_refusal"] = refusal
            if document.get("phase") != "applying":
                document["phase"] = "refused"
                document.update(refusal)
            _write_state_document(install_root, document)
    except Exception as exc:  # noqa: BLE001 — a refusal that cannot be written
        # down is exactly the silence A5.15 exists to end, and raising here
        # loses the receipt the ledger already took. So the call survives and
        # the missing half SAYS it is missing: `state_error` is `ledger_error`
        # the other way round, and `status --json` then resolves this refusal
        # from the receipt and tags it `receipt` rather than answering `none`.
        outcome["state_error"] = "%s: %s" % (type(exc).__name__, exc)
    outcome["refusal"] = refusal
    outcome["phase"] = document.get("phase")
    return outcome


def ingest_deferred_events(install_root: Path) -> dict[str, Any]:
    """Replay held records into the ledger, once each (A5.16).

    Runs on the next successful apply, AFTER the new tree is in place, so the
    emitter it reaches is the one that arrived with the update. Idempotent by
    record id: an id is written to the marker as soon as its row is accepted,
    so an ingest interrupted halfway does not replay what it already did, and a
    sidecar that comes back carrying the same rows is skipped rather than
    duplicated. Nothing here raises — a replay that cannot happen today leaves
    the sidecar exactly where it was for the apply after this one.

    THE BATCH IS TAKEN AWAY BEFORE IT IS READ. `_append_deferred` appends to
    whatever `events.jsonl` is at that moment, so draining the file in place
    and renaming it at the end retires every record that arrived while the
    drain ran — unreplayed, into a file nothing reads again (found in review,
    round 1). Renaming first means a concurrent hold opens a fresh sidecar; a
    batch this run could not finish keeps its `events.draining-*` name and is
    picked up by the next ingest rather than stranded.

    AT-LEAST-ONCE AT THE CRASH BOUNDARY, deliberately. The marker id is written
    after the emit, so a crash between the two replays that row next time and
    the ledger carries it twice; marking first would instead lose it for good.
    "Once each" here means once per completed replay — a duplicate is visible
    and deduplicable by `deferred_record_id`, and losing a record is the one
    thing this path exists to prevent."""

    report = {"ingested": 0, "already_recorded": 0, "failed": 0, "pending": 0}
    path = deferred_events_path(install_root)
    upd = path.parent
    # A drain that could not finish kept its working name. Picked up here
    # rather than stranded: the rows in it were held for a reason and the id
    # marker is what keeps them from being replayed twice.
    sources = sorted(upd.glob("events.draining-*.jsonl")) if upd.is_dir() else []
    if not sources and not path.is_file():
        return report

    marker = install_root / INGESTED_IDS_REL
    done = set()
    if marker.is_file():
        done = {line.strip() for line in
                marker.read_text(encoding="utf-8", errors="replace").splitlines()
                if line.strip()}
    # BEFORE the rename, deliberately: an install that cannot replay anything
    # today must leave the sidecar exactly where it was, under the name the
    # next apply looks for.
    try:
        emit = _installed_emit(install_root)
    except Exception as exc:  # noqa: BLE001
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
        return report

    # RENAME FIRST, then drain what was renamed (found in review, round 1).
    # Draining `events.jsonl` in place and renaming it at the end retires
    # every record appended while the drain was running — `_append_deferred`
    # is an O_APPEND write to whatever `events.jsonl` is at that moment, and
    # nothing ever reads `events.ingested-*.jsonl` again. Taking the batch
    # away first means a concurrent hold opens a FRESH sidecar, which the next
    # ingest finds.
    if path.is_file():
        batch = upd / ("events.draining-%s-%d.jsonl" % (_utc_now(), os.getpid()))
        try:
            os.replace(path, batch)
        except OSError as exc:
            report["error"] = "%s: %s" % (type(exc).__name__, exc)
            return report
        sources.append(batch)

    rows = [row for source in sources for row in _read_event_rows(source)]
    report["pending"] = len(rows)

    for row in rows:
        if row["id"] in done:
            report["already_recorded"] += 1
            continue
        payload = dict(row.get("payload") or {})
        # The ledger row's own timestamp is the INGEST, so the record carries
        # when it actually happened and which held record it came from — the
        # id the exactly-once property is keyed on, readable from the ledger.
        payload["deferred_record_id"] = row["id"]
        payload["recorded_at"] = row.get("ts") or ""
        try:
            emit(row["event_type"], row.get("actor") or "system", payload)
        except Exception as exc:  # noqa: BLE001
            report["failed"] += 1
            report["error"] = "%s: %s" % (type(exc).__name__, exc)
            continue
        handle = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(handle, (row["id"] + "\n").encode("utf-8"))
            os.fsync(handle)
        finally:
            os.close(handle)
        done.add(row["id"])
        report["ingested"] += 1

    if not report["failed"]:
        # Kept rather than deleted: a person looking for what happened during
        # the bootstrap hop should be able to find the records themselves.
        stamp, pid = _utc_now(), os.getpid()
        for index, source in enumerate(sources):
            try:
                os.replace(source, upd / ("events.ingested-%s-%d-%02d.jsonl"
                                          % (stamp, pid, index)))
            except OSError:
                pass
        # MEASURED, not assumed: a record held while this ran is still on disk,
        # and clearing the flag over it would be the same silent loss one
        # rename further along.
        held = deferred_events_path(install_root).is_file()
        fields: dict[str, Any] = {"event_fallback": held}
        if not held:
            fields["ledger_error"] = ""
        try:
            update_state(install_root, **fields)
        except OSError:
            pass
    return report


# ---------------------------------------------------------------------------
# the export-time preserve-set generator
# ---------------------------------------------------------------------------

def preserve_set_document(export_manifest: Path) -> str:
    """The bytes of `cabinet/config/egg-preserve-set.txt`, from declared data.

    Both halves are derived, never typed: the `delete instance/...` rules of
    the export manifest (which does NOT ship — it deletes itself from the egg,
    which is exactly why this file has to exist) and the interface ledgers the
    export empties. A generated file with zero rules is a refusal, not an
    empty file.
    """

    if not export_manifest.is_file():
        raise BundleError(f"export manifest not found: {export_manifest}")
    globs = []
    for line in export_manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("delete instance/"):
            value = line.split(" ", 1)[1].strip()
            if value:
                globs.append(value)
    if not globs:
        raise BundleError(
            f"{export_manifest} carries no 'delete instance/...' rules — the "
            "generated preserve set would be a green empty file"
        )
    lines = [
        "# egg-preserve-set.txt — paths an update must never write or delete.",
        "#",
        "# GENERATED at export time by cabinet/scripts/egg-export.sh",
        "# (transform preserve-set). Do not edit by hand: the authoring sources",
        "# are cabinet/scripts/egg-export-manifest.txt (its `delete instance/...`",
        "# rules) and the interface ledgers the export ships header-only. The",
        "# export manifest deletes ITSELF from the egg, so an installed Cabinet",
        "# has no other way to learn this set.",
        "#",
        "# Read at run time by cabinet/scripts/lib/update_bundle.py, unioned with",
        "# `runtime-provision.sh lists`. One path or glob per line; a directory",
        "# entry covers everything under it.",
        "",
        "# --- instance data the export never ships (delete instance/... rules) ---",
    ]
    lines.extend(sorted(set(globs)))
    lines.append("")
    lines.append("# --- interface ledgers the export ships header-only ---")
    lines.extend(HEADER_ONLY_INTERFACES)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _emit(document: Any) -> int:
    json.dump(document, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("manifest", help="write a bundle manifest for an export tree")
    p.add_argument("--tree", required=True)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--built-at", required=True)
    p.add_argument("--changelog-file")
    p.add_argument("--out", required=True)

    p = sub.add_parser("locked-set", help="parse germline-lock.sh FILES + DIRS")
    p.add_argument("--root", required=True)

    p = sub.add_parser("preserve-set", help="the run-time preserve set")
    p.add_argument("--root", required=True)
    p.add_argument("--bundle-tree")

    p = sub.add_parser("preserve-doc", help="generate egg-preserve-set.txt bytes")
    p.add_argument("--export-manifest", required=True)

    p = sub.add_parser("verify", help="per-file digest verification of a bundle tree")
    p.add_argument("--tree", required=True)
    p.add_argument("--manifest", required=True)

    p = sub.add_parser("plan", help="what an apply would change, delete and skip")
    p.add_argument("--root", required=True)
    p.add_argument("--tree", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--previous-manifest")
    p.add_argument("--out")

    p = sub.add_parser("snapshot", help="pre-image every path the plan touches")
    p.add_argument("--root", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--snapshot", required=True)

    p = sub.add_parser("apply-plan", help="write the plan (tmp + rename per file)")
    p.add_argument("--root", required=True)
    p.add_argument("--tree", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--kill-after", type=int)

    p = sub.add_parser("restore", help="restore a snapshot exactly")
    p.add_argument("--root", required=True)
    p.add_argument("--snapshot", required=True)

    p = sub.add_parser("stamp-identity", help="rewrite egg-manifest.json after an apply")
    p.add_argument("--root", required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--applied-at", required=True)
    p.add_argument("--from-sha")

    p = sub.add_parser("write-state", help="replace state.json, carrying the refusal record")
    p.add_argument("--root", required=True)
    p.add_argument("--state", required=True)

    p = sub.add_parser("record-event", help="record an update event, ledger or held")
    p.add_argument("--root", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--payload", default="{}")

    p = sub.add_parser("record-refusal", help="write the durable refusal and its event")
    p.add_argument("--root", required=True)
    p.add_argument("--bundle", default="")
    p.add_argument("--reason", required=True)
    p.add_argument("--paths", default="[]")
    p.add_argument("--door", default="terminal")
    p.add_argument("--actor", default="system")

    p = sub.add_parser("ingest-events", help="replay held records into the ledger, once")
    p.add_argument("--root", required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "manifest":
            tree = Path(args.tree)
            changelog: list[str] = []
            if args.changelog_file and Path(args.changelog_file).is_file():
                changelog = [
                    line.strip()
                    for line in Path(args.changelog_file).read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                    if line.strip()
                ]
            try:
                locked = parse_locked_set(tree / GERMLINE_LOCK_REL)
            except BundleError as exc:
                # INFORMATIONAL field: a bundle that cannot describe its own
                # boundary is still applicable, because the check that matters
                # reads the INSTALLED script. Say so rather than inventing [].
                locked = {"files": [], "dirs": [], "unparsed": str(exc)}
            document = build_manifest(
                tree, args.source_sha, args.built_at, changelog, locked
            )
            Path(args.out).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"{len(document['files'])} files")
            return 0

        if args.command == "locked-set":
            return _emit(parse_locked_set(Path(args.root) / GERMLINE_LOCK_REL))

        if args.command == "preserve-set":
            bundle = Path(args.bundle_tree) if args.bundle_tree else None
            for entry in preserve_set(Path(args.root), bundle):
                print(entry)
            return 0

        if args.command == "preserve-doc":
            sys.stdout.write(preserve_set_document(Path(args.export_manifest)))
            return 0

        if args.command == "verify":
            bad = verify_tree(Path(args.tree), load_manifest(Path(args.manifest)))
            for line in bad:
                print(line, file=sys.stderr)
            return 1 if bad else 0

        if args.command == "plan":
            root = Path(args.root)
            tree = Path(args.tree)
            manifest = load_manifest(Path(args.manifest))
            previous = (
                load_manifest(Path(args.previous_manifest))
                if args.previous_manifest and Path(args.previous_manifest).is_file()
                else None
            )
            plan = build_plan(
                root,
                tree,
                manifest,
                previous,
                preserve_set(root, tree),
                parse_locked_set(root / GERMLINE_LOCK_REL),
            )
            if args.out:
                Path(args.out).write_text(
                    json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            return _emit(plan)

        if args.command == "snapshot":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            return _emit(snapshot(Path(args.root), plan, Path(args.snapshot)))

        if args.command == "apply-plan":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            return _emit(
                apply_plan(Path(args.root), Path(args.tree), plan, args.kill_after)
            )

        if args.command == "restore":
            return _emit(restore(Path(args.root), Path(args.snapshot)))

        if args.command == "stamp-identity":
            root = Path(args.root)
            path = root / EGG_MANIFEST_REL
            document = {}
            if path.is_file():
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    document = {}
            if not isinstance(document, dict):
                document = {}
            document["source_commit"] = args.source_commit
            document["applied_at"] = args.applied_at
            if args.from_sha:
                document["applied_from"] = args.from_sha
            tmp = path.parent / (path.name + ".update-tmp")
            tmp.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(tmp, path)
            return 0

        if args.command == "write-state":
            document = json.loads(args.state)
            if not isinstance(document, dict):
                raise BundleError("--state must be a JSON object")
            write_state(Path(args.root), document)
            return 0

        if args.command == "record-event":
            payload = json.loads(args.payload or "{}")
            return _emit(record_event(Path(args.root), args.type, args.actor,
                                      payload if isinstance(payload, dict) else {}))

        if args.command == "record-refusal":
            paths = json.loads(args.paths or "[]")
            return _emit(record_refusal(
                Path(args.root), args.bundle, args.reason,
                [str(entry) for entry in paths] if isinstance(paths, list) else [],
                args.door, args.actor))

        if args.command == "ingest-events":
            return _emit(ingest_deferred_events(Path(args.root)))
    except BundleError as exc:
        print(f"update_bundle: {exc}", file=sys.stderr)
        return 3

    parser.error(f"unhandled command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
