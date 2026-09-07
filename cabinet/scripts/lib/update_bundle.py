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

FOUR DECISIONS, and why each is shaped the way it is.

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

Read-only except for `apply-plan` and `restore`, which are the two writers and
take an explicit snapshot directory.

Interpreter: python3.12 (this module is not on the locked hook's import path).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
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
    """`runtime-provision.sh lists` as data — the three declared list variables.

    Parsed from the assignments rather than executed: this runs on an installed
    Cabinet where sourcing a provisioning script would be an odd thing to do
    for a read. An unparseable list raises; it never reads as an empty list.
    """

    if not script.is_file():
        return []
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
            f"{script} carries none of the INSTANCE_PERSISTENT_* lists — an "
            "unparseable list must never read as an empty list"
        )
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

    changed: list[str] = []
    unchanged = 0
    skipped_preserved: list[str] = []
    for rel in sorted(new_files):
        if is_preserved(rel, preserve):
            skipped_preserved.append(rel)
            continue
        installed = install_root / rel
        if installed.is_file() and not installed.is_symlink():
            if sha256_file(installed) == new_files[rel]:
                unchanged += 1
                continue
        changed.append(rel)

    deleted: list[str] = []
    for rel in sorted(previous_files - set(new_files)):
        if is_preserved(rel, preserve):
            skipped_preserved.append(rel)
            continue
        if (install_root / rel).exists():
            deleted.append(rel)

    locked_hits = sorted(
        rel for rel in set(changed) | set(deleted) if is_locked(rel, locked)
    )
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
    except BundleError as exc:
        print(f"update_bundle: {exc}", file=sys.stderr)
        return 3

    parser.error(f"unhandled command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
