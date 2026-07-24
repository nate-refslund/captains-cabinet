"""framework.organs.registry — STRUCTURAL organ-manifest loading + the
content-addressed registry hash (COG-4 §4.4).

STRUCTURAL READS, HONEST ERRORS — NEVER SCHEMA-VALIDATION CLAIMS: the germline
extension gate pair (the schema + validate-extension.sh) does NOT yet validate
organ manifests — the CG-33 amendment is FILED but the Captain window is
UNOPENED (docs/proposals/germline-amendment-extension-manifest-organ-
2026-07-23.md; PARK marker docs/plans/cog4-w4-u1-organ-schema-validation-
PARKED-2026-07-24.md). This loader therefore checks only what IT structurally
needs (a mapping, `kind: organ`, a non-empty unique `name`) and says so in its
errors; §4.2 field validation is the schema/AX suite's law once the window
lands, never re-minted here. A structurally unreadable file REFUSES loudly —
never a silent skip.

LAYER LAW (§4.4, the COG-3 §7.6 idiom): the manifest directory is a REQUIRED
caller parameter — no default path, no instance-layer path literal; the
cabinet-side CLIs own path defaults and inject them. Reads are bounded to the
given directory's TOP-LEVEL files (no recursion).

REGISTRY HASH = the recorder-dialect digest over the manifest list sorted by
canonical bytes — a pure function of manifest CONTENT (never paths, mtimes or
arrival order), so rebuilds reproduce it and ANY organ edit changes it: an
organ edit is an honest epoch bump, never silent drift (§4.4). The
canonical-bytes + digest pair is a small STDLIB REPLICA of the C3 kernel's
(framework/projection/kernel.py (a)) — replicated, not imported, because
boundary-manifest row 6 does not allowlist this tree as a projection-kernel
importer (the kernel is importable by cortex/objectives/scheduler internals +
their CLIs only; the same reason objectives/model.py replicated the recorder
dialect). Byte parity replica==kernel is a standing test tripwire
(test_cog4_organs_package.py), so the two spellings can never drift apart
silently.

The cross-manifest `state_ownership` disjointness sweep lives here as a PURE
helper (`state_ownership_collisions`) because it is a SUITE-LEVEL check by
necessity (§4.3 N-b): the per-file validator sees one manifest at a time, so
collision detection belongs to whoever holds ALL manifests — the registry and
the AX-suite sweep over it. Output is symmetric + sorted (the
assemble-collision law shape) and gates nothing here.

This module writes NOTHING (a read-only loader): no cache, no clock, no env
read, no subprocess, no network.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W4 u1 (organs package,
Fable-for-execution named unit).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml

REGISTRY_SCHEMA_VERSION = "cog4-organ-registry/v1"

# the manifest spellings of the ONE packaging surface (§4.1)
MANIFEST_SUFFIXES = (".yml", ".yaml", ".json")


class OrganRegistryError(ValueError):
    """A structural organ-registry defect. ALWAYS fatal — loading fails
    closed; a defective manifest directory never yields a partial registry."""


# ===========================================================================
# canonical bytes + digest — the recorder-dialect STDLIB REPLICA (see module
# docstring: row-6 boundary law; parity with framework/projection/kernel.py is
# a standing test tripwire)
# ===========================================================================

def canonical_bytes(value: Any) -> bytes:
    """Recorder-dialect canonical bytes: compact, sort_keys,
    ensure_ascii=False, utf-8 — byte-identical to the C3 kernel's (a) and to
    framework.objectives.model.canonical_bytes (the same replica idiom)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    """Recorder-dialect sha256 hexdigest of the canonical bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# ===========================================================================
# structural manifest reads
# ===========================================================================

def read_manifest_file(path) -> dict:
    """Parse ONE manifest file to a mapping — json for `.json`,
    yaml.safe_load for `.yml`/`.yaml`. Structural read only: unreadable,
    unparseable or non-mapping content REFUSES with the file named; nothing
    here claims §4.2 schema validity (module docstring law)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in MANIFEST_SUFFIXES:
        raise OrganRegistryError(
            f"{path.name}: not an organ-manifest spelling (expected one of "
            f"{list(MANIFEST_SUFFIXES)})")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OrganRegistryError(
            f"{path.name}: unreadable ({type(exc).__name__}) — structural "
            "read refused") from None
    try:
        loaded = (json.loads(text) if suffix == ".json"
                  else yaml.safe_load(text))
    except (ValueError, yaml.YAMLError) as exc:
        raise OrganRegistryError(
            f"{path.name}: unparseable ({type(exc).__name__}) — structural "
            "read refused, never a silent skip") from None
    if not isinstance(loaded, dict):
        raise OrganRegistryError(
            f"{path.name}: manifest is not a mapping "
            f"(got {type(loaded).__name__}) — structural read refused")
    return loaded


def load_organ_manifests(manifest_dir) -> list[dict]:
    """Load every organ manifest from the TOP LEVEL of `manifest_dir`
    (REQUIRED parameter — §4.4 layer law: callers inject the path; framework
    holds no default). Files with non-manifest suffixes are ignored by
    declaration (a README beside the manifests is not a defect); every file
    WITH a manifest suffix must structurally read as an organ manifest:
    a mapping, `kind: organ` (structural identity — this is the ORGAN
    registry; any other kind here is a mis-deployment and refuses), and a
    non-empty string `name`, unique across the directory.

    Returns the manifests sorted by canonical bytes — the registry's total
    order (content-determined, so directory iteration order and filenames
    never leak into downstream hashes)."""
    root = Path(manifest_dir)
    if not root.is_dir():
        raise OrganRegistryError(
            f"organ manifest directory {str(root)!r} is not a directory — "
            "the registry loads nothing rather than inventing an empty fleet")
    manifests: list[dict] = []
    seen_names: dict[str, str] = {}
    for path in sorted(p for p in root.iterdir() if p.is_file()):
        if path.suffix.lower() not in MANIFEST_SUFFIXES:
            continue
        manifest = read_manifest_file(path)
        kind = manifest.get("kind")
        if kind != "organ":
            raise OrganRegistryError(
                f"{path.name}: kind is {kind!r}, not 'organ' — structural "
                "identity check (this directory is the organ registry's; "
                "schema-level kind law is the extension gate's, not ours)")
        name = manifest.get("name")
        if not isinstance(name, str) or not name:
            raise OrganRegistryError(
                f"{path.name}: organ manifest carries no non-empty string "
                "'name' — the registry cannot key it")
        if name in seen_names:
            raise OrganRegistryError(
                f"{path.name}: duplicate organ name {name!r} (already "
                f"declared by {seen_names[name]}) — one organ, one manifest")
        seen_names[name] = path.name
        manifests.append(manifest)
    return sorted(manifests, key=canonical_bytes)


def registry_hash(manifests: Iterable[dict]) -> str:
    """The wake-snapshot registry hash (§4.4): the recorder-dialect digest of
    the manifest list sorted by canonical bytes. Content-only and
    order-invariant — two loads of the same manifests hash identically
    whatever their filenames or arrival order; ANY manifest edit changes the
    hash (the honest epoch bump the snapshot consumes)."""
    return digest(sorted(manifests, key=canonical_bytes))


def load_organ_registry(manifest_dir) -> dict:
    """The public registry record: load + hash in one step.

    Returns {schema_version, manifest_dir, count, organs (sorted names),
    manifests (canonical-bytes order), registry_hash}. `manifest_dir` is
    echoed for provenance ONLY — the hash covers manifest CONTENT exclusively,
    so the record's hash is machine/path-independent."""
    manifests = load_organ_manifests(manifest_dir)
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "manifest_dir": str(manifest_dir),
        "count": len(manifests),
        "organs": sorted(m["name"] for m in manifests),
        "manifests": manifests,
        "registry_hash": registry_hash(manifests),
    }


# ===========================================================================
# the N-b SUITE-level disjointness sweep (pure helper — see module docstring)
# ===========================================================================

def state_ownership_collisions(manifests: Iterable[dict]) -> list[str]:
    """Two organs claiming one `state_ownership` path — detectable only
    ACROSS manifests (§4.3 N-b: the per-file validator sees one at a time).
    Pure and gate-free here: the AX-suite sweep over ALL organ manifests is
    the enforcement site; composition tooling reads it too. Output is
    symmetric + sorted (the assemble-collision law shape), matching the W2
    corpus reference sweep line-for-line. Structural read: a manifest without
    a list-shaped `state_ownership` contributes nothing (its §4.2 validity is
    schema/AX law, not ours)."""
    owners: dict[str, list[str]] = {}
    for manifest in manifests:
        name = manifest.get("name", "<unnamed>")
        paths = manifest.get("state_ownership")
        if not isinstance(paths, list):
            continue
        for path in paths:
            if isinstance(path, str):
                owners.setdefault(path, []).append(name)
    return sorted(
        f"state_ownership collision on {path!r}: {sorted(names)}"
        for path, names in owners.items() if len(names) > 1)
