#!/usr/bin/env python3.12
"""cog4-parity.py — the N9 outcome/evidence PARITY comparator (COG-4 §5.3, SF4;
foundry L188 "outcome/evidence parity holds", made mechanical).

THE ONE SANCTIONED DUAL-PLANE IMPORTER (§5.3, MF-A1; boundary-manifest row —
`cabinet/scripts/cog4-parity.py` is explicitly allowlisted for framework.organs
and DELIBERATELY absent from the framework.scheduler + schedule-store
allowlists). For every namespaced operation declared by the organ manifests in
`--manifest-dir`, it computes TWO INDEPENDENT tuples
`(risk_class, ceiling, undo_contract, shadow_verdict)` and compares them at
the END:

  * DESCRIPTOR PATH (leg a) — through the organs PUBLIC resolution surface
    ONLY: `load_organ_registry()` + `resolve_descriptor()`. The constitutional
    members are the manifest-declared values the descriptor resolution
    returns verbatim.
  * ACTION_TYPES PATH (leg b) — the shadowed compatibility adapter leg,
    computed cabinet-side HERE (MF-A1): the action_type is
    `classify_action(tool_name, tool_input)` where the injected `--tool-map`
    carries a tool mapping for the operation, ELSE the manifest's DECLARED
    compat member (leg b's OWN raw read of the §5.2 descriptor block +
    per-operation override — never leg a's output); risk_class is
    MATRIX-DERIVED via `risk_of()` over the loaded matrix policy's
    `risk_classes` mapping; ceiling is derived from the matrix policy's
    `ceiling_frozenset_map` (a hard-ceiling risk_class maps to its
    HARD_CEILING_TOUCHES member; a non-ceiling class derives the empty set),
    sanity-checked against `ceiling_members()` + `RISK_CLASSES`; the
    undo_contract is leg b's own raw merge of the declared blocks.

INDEPENDENCE LAW (§5.3; the §15 standing panel question): leg (b) NEVER reads
leg (a)'s output. Both legs share only the loaded INPUTS (the registry record's
raw manifests, the matrix policy, the injected tool map) and the pure
shadow-verdict derivation applied to each leg's OWN (risk_class, action_type).
The two parallel derivations are compared once, at the end — a derived leg
could never diverge; only independent legs make the N9 gate evidence.

SHADOW VERDICT (both legs, each from its OWN inputs) — the existing read-only
shadow joint (§7.3 idiom): cell state -> `resolve_verdict(verdicts, risk_class,
state, posture=, postures=)` over the loaded matrix policy tables.
  * HERMETIC mode (default — the deterministic record the N9 gate tracks):
    cell state = `graduation.evaluate((f"officer:{officer}", lane,
    action_type), ledger=<rows from --consequence-ledger, else []>,
    now=<--now, else evaluate's default>)`, folded through the same
    fail-closed mapping `read_cell_state` pins (policy_engine.py — evaluate
    exception -> "demote"; None -> "unmeasured"; out-of-vocabulary state ->
    "demote"; the vocabulary literal below mirrors policy_engine._CELL_STATES
    because the matrix CONFIDENCE_STATES symbol is outside this CLI's §8.4
    import pin). With no seeded ledger every cell is honestly "unmeasured" —
    byte-reproducible on any machine. Hermetic mode NEVER calls
    `_act_with_undo_gap` — its two probes (registered inverse, journal-dir
    writability) are call-time imports of framework.acting/framework.frontdoor
    plus live filesystem/env state: exactly what the §8.4 transitive-closure
    backstop forbids in this comparator's run closure and what a
    canonical-bytes record must exclude.
  * LIVE mode (`--live-state`) — the §7.3-faithful joint for operator use
    beside the dispatcher: cell state = `read_cell_state()` (live consequence
    ledger via $CABINET_EVENT_LOG_DIR), and an `act_with_undo` verdict takes
    the `_act_with_undo_gap` fall-through to "propose_only" when the undo
    plane is not mechanically viable (the policy-engine allow-branch law).
    Live mode MAY load the executor doors through that call-time probe and its
    record is machine-state-dependent — never track a live-mode record as the
    N9 artifact.

OUTPUT — `cog4-parity-record.json` (`--out`): canonical bytes (compact
separators, sort_keys, ensure_ascii=False, utf-8), rows sorted by operation,
ceilings emitted sorted (the record compares ceilings as SETS — order is
presentation): the exact reference shape `test_cog4_parity.py` gates
(schema "cog4-parity-record/v1"; non-empty rows; namespaced operation ids;
no duplicates; every leg carrying the four members). The record is written
ONLY when every operation resolved on BOTH legs — a partial record can never
masquerade as parity evidence. Divergent rows are still WRITTEN (the record
carries the evidence; the gate's divergent_rows checker REDs on it).

EXIT CODES: 0 — every operation resolved and ZERO divergent tuples (the N9
parity law holds over this input set); 2 — divergent tuples and/or
per-operation resolution failures (the list is printed; any divergence is a
STRUCTURAL BUILD FAILURE, never a warning); 3 — setup failure (unreadable
manifest dir / matrix / tool map / ledger; zero declared operations — a
vacuously green parity run is no evidence, the R-A non-empty idiom; or a
non-namespaced FLAT operation id — the §4.3 namespace law, mirrored from the
`test_cog4_parity.py` reference checker: a record carrying a flat id REDs
there as MALFORMED, so exit 0 must never vouch for one, and with organ-schema
validation PARKED (germline window) this comparator is the only guard on this
path — a flat id can literally equal an ACTION_TYPES member, the exact
collision the namespace grammar exists to prevent).

WRITES: only `--out`. No cache dir, no clock or env reads of its own, no
subprocess, no network. Layer law (§4.4): the manifest directory is
CLI-injected; this script owns its own defaults, framework holds none.

Imports are pinned symbol-for-symbol by `test_cog4_parity_ast_pin.py` /
`lib_cog4_ast_pins.parity_import_violations` (§8.4): stdlib | classify_action
| the matrix mapping-surface accessors (RISK_CLASSES, load_matrix,
matrix_policy, ceiling_members) | the four read-only policy_engine symbols +
graduation.evaluate the dispatcher pins | the organs PUBLIC registry /
descriptor surface. The comparator stays a comparator — never a resolver
anything in framework/ could grow to depend on, never an executor.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W4 v2 (parity CLI,
Fable-for-execution named unit).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority.classifier import classify_action  # noqa: E402
from framework.authority.matrix import (  # noqa: E402
    RISK_CLASSES, load_matrix, matrix_policy, ceiling_members)
from framework.authority.policy_engine import (  # noqa: E402
    risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap)
from framework.fidelity.graduation import evaluate  # noqa: E402
from framework.organs.registry import (  # noqa: E402
    OrganRegistryError, load_organ_registry)
from framework.organs.descriptor import (  # noqa: E402
    DescriptorRefused, resolve_descriptor)

RECORD_SCHEMA = "cog4-parity-record/v1"
TUPLE_MEMBERS = ("risk_class", "ceiling", "undo_contract", "shadow_verdict")

# Mirror of policy_engine._CELL_STATES / matrix CONFIDENCE_STATES — a LITERAL
# because neither symbol is on this CLI's §8.4 import pin (module docstring).
_CELL_STATES = frozenset(
    {"unmeasured", "propose_only", "eligible", "graduated", "demote"})


class SetupError(Exception):
    """A whole-run input defect (exit 3) — nothing comparable was produced."""


# ===========================================================================
# shared derivation machinery (pure; each leg passes its OWN inputs)
# ===========================================================================

class _VerdictContext:
    """The loaded matrix tables + identity/mode for shadow-verdict derivation.
    Pure data + pure calls; both legs use it with THEIR OWN
    (risk_class, action_type) — never with each other's outputs."""

    def __init__(self, policy: dict, officer: str, lane: str | None,
                 posture: str | None, live_state: bool,
                 ledger_rows: list[dict], now: datetime | None) -> None:
        self.policy = policy
        self.officer = officer
        self.lane = lane
        self.posture = posture
        self.live_state = live_state
        self.ledger_rows = ledger_rows
        self.now = now

    def cell_state(self, action_type: str) -> str:
        if self.live_state:
            return read_cell_state(self.officer, self.lane, action_type)
        # hermetic: evaluate's ledger/now test seams + the read_cell_state
        # fail-closed mapping mirrored (module docstring law).
        cell = (f"officer:{self.officer}", self.lane, action_type)
        try:
            result = evaluate(cell, ledger=self.ledger_rows, now=self.now)
        except Exception:
            return "demote"          # cannot read the evidence plane
        if result is None:
            return "unmeasured"      # the legitimate no-evidence case
        state = (result or {}).get("state")
        return state if state in _CELL_STATES else "demote"

    def shadow_verdict(self, risk_class: str, action_type: str) -> str:
        state = self.cell_state(action_type)
        verdict = resolve_verdict(
            self.policy.get("verdicts"), risk_class, state,
            posture=self.posture, postures=self.policy.get("postures"))
        if self.live_state and verdict == "act_with_undo":
            # the policy-engine allow-branch law: no mechanically viable undo
            # plane -> fall through to propose_only. LIVE mode only — the gap
            # probe imports the executor doors at call time (docstring law).
            if _act_with_undo_gap(action_type) is not None:
                verdict = "propose_only"
        return verdict


# ===========================================================================
# leg (a) — the descriptor path (organs PUBLIC surface only)
# ===========================================================================

def descriptor_leg(registry: dict, operation: str,
                   ctx: _VerdictContext) -> tuple[dict, str]:
    """(leg tuple, organ name) via resolve_descriptor — manifest-declared
    constitutional members verbatim; verdict from the leg's OWN members."""
    desc = resolve_descriptor(registry, operation)
    return ({
        "risk_class": desc["risk_class"],
        "ceiling": sorted(desc["ceiling"]),
        "undo_contract": desc["undo_contract"],
        "shadow_verdict": ctx.shadow_verdict(
            desc["risk_class"], desc["action_type"]),
    }, desc["organ"])


# ===========================================================================
# leg (b) — the ACTION_TYPES path (raw manifests + classifier + matrix;
# NEVER leg a's output)
# ===========================================================================

def _leg_b_owner(manifests: list[dict], operation: str) -> dict:
    """Leg b's OWN single-declarer scan over the raw manifest list."""
    owners = []
    for manifest in manifests:
        declared = manifest.get("domain_operations")
        if isinstance(declared, list) and operation in declared:
            owners.append(manifest)
    if len(owners) != 1:
        raise DescriptorRefused(
            f"action_types leg: {operation!r} declared by {len(owners)} "
            "manifests — exactly one declarer required")
    return owners[0]


def _leg_b_declared(manifest: dict, operation: str, member: str) -> str:
    """The manifest's DECLARED `member` for this operation — leg b's own raw
    merge of the §5.2 organ-level block + per-operation override."""
    block = manifest.get("descriptor")
    if not isinstance(block, dict):
        raise DescriptorRefused(
            f"action_types leg: organ {manifest.get('name')!r} has no "
            "readable descriptor block to declare a compat member")
    value = block.get(member)
    operations = block.get("operations")
    if isinstance(operations, dict):
        override = operations.get(operation)
        if isinstance(override, dict) and member in override:
            value = override[member]
    if not isinstance(value, str) or not value:
        raise DescriptorRefused(
            f"action_types leg: organ {manifest.get('name')!r} declares no "
            f"usable {member!r} for {operation!r}")
    return value


def action_types_leg(manifests: list[dict], operation: str,
                     tool_map: dict, ctx: _VerdictContext) -> tuple[dict, str]:
    """(leg tuple, organ name) via the ACTION_TYPES compatibility adapter:
    classify_action where a tool mapping exists, else the declared compat
    member; matrix-derived risk_class; ceiling-map-derived ceiling."""
    manifest = _leg_b_owner(manifests, operation)
    organ = manifest.get("name") if isinstance(manifest.get("name"), str) else "<unnamed>"

    mapping = tool_map.get(operation)
    if mapping is not None:
        action_type = classify_action(
            mapping["tool_name"], mapping.get("tool_input"))
    else:
        action_type = _leg_b_declared(manifest, operation, "action_type")

    policy = ctx.policy
    risk_class = risk_of(action_type, policy.get("risk_classes"))
    if risk_class is None:
        raise DescriptorRefused(
            f"action_types leg: action_type {action_type!r} has no matrix "
            "risk_class (unknown/ambiguous maps to none) — the ACTION_TYPES "
            "path cannot produce a tuple for it")
    if risk_class not in RISK_CLASSES:
        raise DescriptorRefused(
            f"action_types leg: matrix-derived risk_class {risk_class!r} is "
            "outside the closed 13-member vocabulary — refusing a drifted "
            "matrix input")

    hard_ceiling = policy.get("hard_ceiling") or []
    cmap = policy.get("ceiling_frozenset_map") or {}
    if risk_class in hard_ceiling:
        member = cmap.get(risk_class)
        if not isinstance(member, str) or not member:
            raise DescriptorRefused(
                f"action_types leg: hard-ceiling class {risk_class!r} has no "
                "ceiling_frozenset_map member — refusing")
        ceiling = [member]
    else:
        ceiling = []
    if not set(ceiling) <= ceiling_members(policy):
        raise DescriptorRefused(
            f"action_types leg: derived ceiling {ceiling!r} outside the "
            "matrix ceiling vocabulary — refusing")

    return ({
        "risk_class": risk_class,
        "ceiling": sorted(ceiling),
        "undo_contract": _leg_b_declared(manifest, operation, "undo_contract"),
        "shadow_verdict": ctx.shadow_verdict(risk_class, action_type),
    }, organ)


# ===========================================================================
# comparison + record
# ===========================================================================

def _leg_tuple(leg: dict) -> tuple:
    return (leg["risk_class"], tuple(sorted(leg["ceiling"])),
            leg["undo_contract"], leg["shadow_verdict"])


def divergences(rows: list[dict]) -> list[str]:
    """Every row whose two legs disagree, diverging members named — ceiling
    compared as a SET, the other three exactly (the W2 reference law)."""
    out = []
    for row in rows:
        a, b = row["descriptor_path"], row["action_types_path"]
        if _leg_tuple(a) == _leg_tuple(b):
            continue
        diverging = []
        for member in TUPLE_MEMBERS:
            va, vb = a[member], b[member]
            if member == "ceiling":
                va, vb = sorted(va), sorted(vb)
            if va != vb:
                diverging.append(
                    f"{member}: descriptor={va!r} vs action_types={vb!r}")
        out.append(f"{row['operation']!r} DIVERGES on " + "; ".join(diverging))
    return out


def canonical_record_bytes(record: dict) -> bytes:
    return json.dumps(record, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


# ===========================================================================
# inputs
# ===========================================================================

def _load_tool_map(path: str | None) -> dict:
    if path is None:
        return {}
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupError(f"tool map {path!r} unreadable: {exc}") from None
    if not isinstance(loaded, dict):
        raise SetupError("tool map must be a JSON object keyed by operation")
    for op, mapping in loaded.items():
        if (not isinstance(mapping, dict)
                or not isinstance(mapping.get("tool_name"), str)
                or not mapping["tool_name"]
                or not isinstance(mapping.get("tool_input"), (dict, type(None)))):
            raise SetupError(
                f"tool map entry {op!r} must be "
                "{{'tool_name': <non-empty str>, 'tool_input': <object|null>}}")
    return loaded


def _load_ledger_rows(path: str | None) -> list[dict]:
    if path is None:
        return []
    rows: list[dict] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SetupError(f"consequence ledger {path!r} unreadable: {exc}") from None
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise SetupError(
                f"consequence ledger {path!r} line {i}: not JSON ({exc})") from None
        if not isinstance(row, dict):
            raise SetupError(
                f"consequence ledger {path!r} line {i}: row is not an object")
        rows.append(row)
    return rows


def _declared_operations(manifests: list[dict]) -> list[str]:
    """The sorted union of declared operation ids. A present-but-mis-shaped
    declaration is a SETUP failure — enumeration over a malformed registry
    would silently drop coverage. A FLAT (non-namespaced) id is refused the
    same way (the §4.3 namespace law, mirrored from the reference checker's
    `record_errors`): the record it would produce REDs downstream as
    MALFORMED, so producing it behind exit 0 is fail-open — and with
    organ-schema validation PARKED (germline window unopened), nothing
    upstream enforces the grammar for this comparator."""
    ops: set[str] = set()
    for manifest in manifests:
        declared = manifest.get("domain_operations")
        if declared is None:
            continue
        if not isinstance(declared, list) or any(
                not isinstance(op, str) or not op for op in declared):
            raise SetupError(
                f"organ {manifest.get('name')!r}: domain_operations is not a "
                "list of non-empty strings — cannot enumerate coverage")
        flat = sorted(op for op in declared if "/" not in op)
        if flat:
            raise SetupError(
                f"organ {manifest.get('name')!r}: non-namespaced operation "
                f"id(s) {flat} — every declared id must be a "
                "'<domain>/<operation>' id (§4.3 namespace law; the record a "
                "flat id produces REDs under the test_cog4_parity.py "
                "reference checker, and a flat id can collide with an "
                "ACTION_TYPES member)")
        ops.update(declared)
    return sorted(ops)


# ===========================================================================
# main
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cog4-parity.py",
        description="COG-4 §5.3 N9 parity comparator — descriptor path vs "
                    "ACTION_TYPES path, two independent tuples per operation.")
    p.add_argument("--manifest-dir", required=True,
                   help="organ-manifest directory (CLI-injected, §4.4 layer law)")
    p.add_argument("--out", default="cog4-parity-record.json",
                   help="record path (default: ./cog4-parity-record.json)")
    p.add_argument("--tool-map", default=None,
                   help="JSON {operation: {tool_name, tool_input}} — where a "
                        "mapping exists, classify_action drives the "
                        "ACTION_TYPES leg")
    p.add_argument("--matrix", default=None,
                   help="explicit authority-matrix.yml (default: the framework floor)")
    p.add_argument("--officer", default="cos",
                   help="graduation-cell officer identity (default: cos)")
    p.add_argument("--lane", default=None,
                   help="graduation-cell lane (default: none)")
    p.add_argument("--posture", default=None,
                   choices=("guardian", "earn_up", "sovereign"),
                   help="verdict-table posture (default: the guardian root table)")
    p.add_argument("--consequence-ledger", default=None,
                   help="JSONL rows for graduation.evaluate's ledger seam "
                        "(hermetic mode; default: empty ledger)")
    p.add_argument("--now", default=None,
                   help="ISO timestamp pinning evaluate's clock (hermetic mode)")
    p.add_argument("--live-state", action="store_true",
                   help="use the LIVE shadow joint (read_cell_state + the "
                        "act_with_undo gap fall-through) — machine-state-"
                        "dependent; never track a live-mode record")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.live_state and (args.consequence_ledger or args.now):
            raise SetupError(
                "--live-state reads the live joint; --consequence-ledger/"
                "--now are hermetic-mode seams — pick one mode")
        now = None
        if args.now is not None:
            try:
                now = datetime.fromisoformat(args.now)
            except ValueError as exc:
                raise SetupError(f"--now is not ISO-8601: {exc}") from None
            if now.tzinfo is None:
                raise SetupError("--now must carry a timezone offset")
        tool_map = _load_tool_map(args.tool_map)
        ledger_rows = _load_ledger_rows(args.consequence_ledger)
        try:
            data = load_matrix(args.matrix) if args.matrix else load_matrix()
            policy = matrix_policy(data)
        except Exception as exc:
            raise SetupError(f"authority matrix unusable: {exc}") from None
        try:
            registry = load_organ_registry(args.manifest_dir)
        except OrganRegistryError as exc:
            raise SetupError(f"organ registry unusable: {exc}") from None
        manifests = registry["manifests"]
        operations = _declared_operations(manifests)
        if not operations:
            raise SetupError(
                "zero declared operations — a vacuously green parity run is "
                "no evidence (R-A non-empty idiom)")
        unknown = sorted(set(tool_map) - set(operations))
        if unknown:
            raise SetupError(
                f"tool map names undeclared operations {unknown} — a mapping "
                "for an operation no organ declares is a defect")
    except SetupError as exc:
        print(f"[cog4-parity] SETUP FAILURE: {exc}", file=sys.stderr)
        return 3

    ctx = _VerdictContext(policy, args.officer, args.lane, args.posture,
                          args.live_state, ledger_rows, now)

    rows: list[dict] = []
    failures: list[str] = []
    for operation in operations:
        try:
            leg_a, organ_a = descriptor_leg(registry, operation, ctx)
            leg_b, organ_b = action_types_leg(manifests, operation, tool_map, ctx)
            if organ_a != organ_b:
                raise DescriptorRefused(
                    f"internal: leg organs disagree ({organ_a!r} vs {organ_b!r})")
            rows.append({"operation": operation, "organ": organ_a,
                         "descriptor_path": leg_a, "action_types_path": leg_b})
        except DescriptorRefused as exc:
            failures.append(f"{operation!r} UNRESOLVED: {exc}")

    diverging = divergences(rows)

    if failures:
        print(f"[cog4-parity] {len(failures)} operation(s) UNRESOLVED — no "
              "record written (a partial record is not parity evidence):")
        for line in failures:
            print(f"  {line}")
        for line in diverging:
            print(f"  {line}")
        return 2

    record = {"schema": RECORD_SCHEMA, "rows": rows}
    out = Path(args.out)
    out.write_bytes(canonical_record_bytes(record))

    if diverging:
        print(f"[cog4-parity] PARITY BROKEN — {len(diverging)} divergent "
              f"tuple(s) across {len(rows)} operation(s) "
              "(structural build failure, never a warning):")
        for line in diverging:
            print(f"  {line}")
        print(f"[cog4-parity] record (with the divergence evidence): {out}")
        return 2

    print(f"[cog4-parity] OK — {len(rows)} operation(s), two independent "
          f"legs each, zero divergent tuples; record: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
