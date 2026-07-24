"""framework.organs.descriptor — capability → the ONE constitutional
effect/risk/undo descriptor, resolved from MANIFEST-DECLARED values only
(COG-4 §5.2, MF-A1).

THE MF-A1 LAW, mechanical: this module READS manifest-declared closed-set
values and NOTHING else — `action_type`, `risk_class`, `ceiling` and
`undo_contract` come verbatim FROM THE MANIFEST (organ-level `descriptor`
block, per-operation override for any subset of the four members). It never
derives, never classifies, never consults the matrix, and never imports the
action plane (no authority/acting/frontdoor/fidelity/missions/ovi/learning/
evolution import exists in this tree — boundary row 5 + the §8.4 closure
gate). Closed-set MEMBERSHIP (risk_class ∈ the 13, action_type ∈ the 30,
ceiling ⊆ the 6, N-d matrix consistency) is the schema/AX suite's law; the
ACTION_TYPES shadow-adapter leg that COMPUTES the compatibility tuple lives
cabinet-side in the parity unit (§5.3). What this module enforces is
STRUCTURAL and fail-closed: a member that is absent or mis-shaped after the
merge REFUSES — resolution never invents, defaults or silently drops a
constitutional value.

OPERATION NAMES CARRY ZERO AUTHORITY (§5.2, the corpus-pinned mutant class):
the capability string is an IDENTITY — it selects which declared values to
read (membership in `domain_operations`, override key in
`descriptor.operations`) and is echoed as observation identity. No predicate
here (or anywhere downstream — the corpus capability-blindness harness pins
it) keys a verdict on it: two operations declaring identical constitutional
members resolve to descriptors whose enforcement-relevant tuples are
IDENTICAL.

THE ONE-DESCRIPTOR LAW: a capability resolves through exactly ONE organ
manifest. Zero declarers refuse (never a silent substitute — the sim-9
spirit); multiple declarers refuse (ambiguity is a registry defect, not a
tie to break); a registry whose `domain_operations` surfaces are structurally
unreadable refuses (uniqueness cannot be PROVEN over a malformed registry).

`status_vocab` REFERENCES the existing closed 7-status effect enum (the
trajectory schema's :266 vocabulary — proposed|denied|attempted|verified|
failed|reversed|violation); reproduced by value here exactly like the W2
corpus reference, never a new enum (§5.2 "zero new enums").

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W4 u1 (organs package,
Fable-for-execution named unit).
"""
from __future__ import annotations

from typing import Any, Iterable

DESCRIPTOR_SCHEMA_VERSION = "cog4-organ-descriptor/v1"

# the four constitutional members of the §5.2 block (manifest-declared)
DESCRIPTOR_MEMBERS = ("action_type", "risk_class", "ceiling", "undo_contract")

# the 7-status effect enum, REFERENCED (trajectory v1 :266 — see docstring)
STATUS_VOCAB = ("proposed", "denied", "attempted", "verified", "failed",
                "reversed", "violation")


class DescriptorRefused(Exception):
    """Resolution refused — absent capability, ambiguous declarers, or a
    structurally missing/mis-shaped constitutional member. ALWAYS raised,
    never a None return: a refusal must be impossible to mistake for a
    descriptor."""


def _manifest_list(registry: Any) -> list[dict]:
    """Accept the two sanctioned shapes: the load_organ_registry() record
    (a dict carrying 'manifests') or an iterable of manifest dicts."""
    if isinstance(registry, dict):
        manifests = registry.get("manifests")
        if not isinstance(manifests, list):
            raise DescriptorRefused(
                "registry record carries no 'manifests' list — pass the "
                "load_organ_registry() record or an iterable of manifests")
        return manifests
    if isinstance(registry, Iterable) and not isinstance(registry, (str, bytes)):
        out = list(registry)
        if any(not isinstance(m, dict) for m in out):
            raise DescriptorRefused(
                "manifest iterable contains a non-mapping entry — refusing "
                "to resolve over a structurally unreadable registry")
        return out
    raise DescriptorRefused(
        f"unsupported registry shape {type(registry).__name__!r} — pass the "
        "load_organ_registry() record or an iterable of manifests")


def _organ_label(manifest: dict) -> str:
    name = manifest.get("name")
    return name if isinstance(name, str) and name else "<unnamed>"


def _declared_ops(manifest: dict) -> list[str]:
    """A manifest's declared operation ids, structurally read. Present-but-
    mis-shaped REFUSES (uniqueness over the registry cannot be proven past an
    unreadable declaration); an ABSENT declaration contributes nothing (its
    §4.2 required-when-organ status is schema/AX law, not ours)."""
    declared = manifest.get("domain_operations")
    if declared is None:
        return []
    if not isinstance(declared, list) or any(
            not isinstance(op, str) or not op for op in declared):
        raise DescriptorRefused(
            f"organ {_organ_label(manifest)!r}: domain_operations is "
            "structurally unreadable (must be a list of non-empty strings) — "
            "refusing to resolve over a malformed registry")
    return declared


def _merged_members(manifest: dict, capability: str) -> dict:
    """Organ-level §5.2 block + the per-operation override for `capability`
    (any subset of the four members). Fail-closed structural reading: an
    unknown key in a block this function CONSUMES refuses — a key we would
    silently drop could carry meaning we cannot see."""
    organ = _organ_label(manifest)
    block = manifest.get("descriptor")
    if not isinstance(block, dict):
        raise DescriptorRefused(
            f"organ {organ!r}: descriptor block is structurally "
            f"{'absent' if block is None else 'mis-shaped'} — cannot resolve "
            f"{capability!r} (missing fields refuse, never default)")
    unknown = sorted(set(block) - set(DESCRIPTOR_MEMBERS) - {"operations"})
    if unknown:
        raise DescriptorRefused(
            f"organ {organ!r}: descriptor block carries unknown keys "
            f"{unknown} — fail-closed structural read (a consumed block is "
            "never silently subsetted)")
    merged = {m: block[m] for m in DESCRIPTOR_MEMBERS if m in block}
    operations = block.get("operations")
    if operations is not None and not isinstance(operations, dict):
        raise DescriptorRefused(
            f"organ {organ!r}: descriptor.operations is not a mapping — "
            "structural read refused")
    override = (operations or {}).get(capability)
    if override is not None:
        if not isinstance(override, dict):
            raise DescriptorRefused(
                f"organ {organ!r}: descriptor.operations[{capability!r}] is "
                "not a mapping — structural read refused")
        unknown_o = sorted(set(override) - set(DESCRIPTOR_MEMBERS))
        if unknown_o:
            raise DescriptorRefused(
                f"organ {organ!r}: descriptor.operations[{capability!r}] "
                f"carries unknown keys {unknown_o} — fail-closed structural "
                "read")
        merged.update({m: override[m] for m in DESCRIPTOR_MEMBERS
                       if m in override})
    return merged


def _member_shape_errors(members: dict) -> list[str]:
    """Structural member shapes ONLY (strings non-empty; ceiling a list of
    non-empty strings). Vocabulary membership is schema/AX law — deliberately
    NOT checked here (MF-A1: this module never claims closed-set
    validation)."""
    errs: list[str] = []
    for m in ("action_type", "risk_class", "undo_contract"):
        if m not in members:
            errs.append(f"{m} missing")
        elif not isinstance(members[m], str) or not members[m]:
            errs.append(f"{m} mis-shaped (non-empty string required)")
    if "ceiling" not in members:
        errs.append("ceiling missing")
    elif not isinstance(members["ceiling"], list) or any(
            not isinstance(c, str) or not c for c in members["ceiling"]):
        errs.append("ceiling mis-shaped (list of non-empty strings required)")
    return errs


def _idempotency_discipline(manifest: dict, capability: str) -> str:
    """The manifest-declared idempotency-key discipline for THIS operation
    (§4.2 `idempotency`, keyed by declared op ids; §5.2 carries it in the
    descriptor block). Structurally unreadable/absent REFUSES — a descriptor
    without its declared key discipline would be a silent contract hole."""
    organ = _organ_label(manifest)
    idem = manifest.get("idempotency")
    if not isinstance(idem, dict):
        raise DescriptorRefused(
            f"organ {organ!r}: idempotency is structurally "
            f"{'absent' if idem is None else 'mis-shaped'} — cannot resolve "
            f"{capability!r} with its key discipline")
    discipline = idem.get(capability)
    if not isinstance(discipline, str) or not discipline:
        raise DescriptorRefused(
            f"organ {organ!r}: no idempotency discipline declared for "
            f"{capability!r} — missing fields refuse, never default")
    return discipline


def resolve_descriptor(registry: Any, capability: str) -> dict:
    """Resolve `capability` ("<domain>/<operation>") to THE one descriptor
    (§5.2) across the registry's manifests. See the module docstring for the
    three laws this implements (MF-A1 manifest-declared-only; zero
    operation-name authority; the ONE-descriptor uniqueness law).

    Returns {schema_version, capability, organ, action_type, risk_class,
    ceiling, undo_contract, status_vocab, idempotency_key_discipline} — every
    constitutional member a verbatim manifest value. Raises DescriptorRefused
    on every failure path; never returns a partial descriptor."""
    if not isinstance(capability, str) or not capability:
        raise DescriptorRefused(
            "capability must be a non-empty string operation id")
    manifests = _manifest_list(registry)
    declarers = [m for m in manifests if capability in _declared_ops(m)]
    if not declarers:
        raise DescriptorRefused(
            f"no organ declares {capability!r} — refusing (never a silent "
            "substitute descriptor)")
    if len(declarers) > 1:
        names = sorted(_organ_label(m) for m in declarers)
        raise DescriptorRefused(
            f"{capability!r} is declared by {len(declarers)} organs {names} "
            "— the ONE-descriptor law refuses ambiguity (a registry defect, "
            "not a tie to break)")
    manifest = declarers[0]
    members = _merged_members(manifest, capability)
    shape_errors = _member_shape_errors(members)
    if shape_errors:
        raise DescriptorRefused(
            f"organ {_organ_label(manifest)!r}: cannot resolve "
            f"{capability!r} — {'; '.join(sorted(shape_errors))} (structural "
            "refusal; closed-set membership stays schema/AX law)")
    return {
        "schema_version": DESCRIPTOR_SCHEMA_VERSION,
        "capability": capability,
        "organ": _organ_label(manifest),
        "action_type": members["action_type"],
        "risk_class": members["risk_class"],
        "ceiling": list(members["ceiling"]),
        "undo_contract": members["undo_contract"],
        "status_vocab": list(STATUS_VOCAB),
        "idempotency_key_discipline": _idempotency_discipline(
            manifest, capability),
    }
