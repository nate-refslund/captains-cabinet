#!/usr/bin/env python3
"""Read-only architecture budget census for the Cognitive Core program.

The census deliberately parses source instead of importing framework modules:
it must work in a gitless clean hatch and must never trigger runtime state,
environment, event, or connector side effects.

TWO LAWS, not one.

  * BUDGETS answer "how many?". Every class is pinned at observed==max with
    zero headroom, so a single unit of growth blocks. Mass is paid for with a
    temporary_allowances row (reason / owner / sunset / deletion_gate).
  * The EXPANSION REGISTRY answers "which, and was it adjudicated?". For the
    classes whose members the census can name, the contract's `expansions`
    list must stand in BIJECTION with the surplus:

        observed - baseline  ==  {row.member for row in expansions}

    exactly and disjointly, per class, against
    cabinet/config/architecture-baseline-sets.yml. An unregistered net-new
    member is RED; a row naming a member that is not observed (the stale
    copy-paste) is RED; a row naming a baseline member (the laundering edit)
    is RED; a BASELINE name the tree does not carry is RED (the pre-loaded
    inventory); two rows naming one member are refused at load.

The expansion row carries the adjudication fields (the blind arms that ran, the
written verdict, the merge that was refuted by path+symbol, and the consumer
that will read the output), and every one of them is schema-refused when
missing or empty. An allowance asks only reason/owner/sunset — declaration
without adjudication — which is why an expansion's line-mass once rode in as a
routine allowance row.

WHAT THE PREVIOUS VERSION OF THIS DOCSTRING GOT WRONG, kept because the wrong
sentence shipped in the public egg. It said flatly "an allowance CANNOT buy a
net-new set member", and an adversarial review falsified it BY EXECUTION on
2026-07-27: a genuinely net-new production module landed at ok=True with no
expansion row, paid for with ONE line in the baseline file plus an ordinary
temporary_allowances row — the twelfth on framework_production_modules. The
membership question and the count question are two separate costs, and the
sentence named only the count.

WHAT IS ENFORCED NOW, stated exactly so nothing reads as more than it is:

  * COUNT. No temporary_allowances row may name a bijection class at all —
    refused at contract load. The rows that were already live when that refusal
    landed are grandfathered by exact (phase, budget, additional) triple in
    LEGACY_BIJECTION_ALLOWANCES, so a legacy row cannot be edited upward or
    duplicated to buy a member either. The count of a bijection class therefore
    grows only by raising `maximum` in the contract: visible, permanent, and on
    the line the zero-headroom law is read from.
  * PRE-LOADING. A baseline name the tree does not carry is a failure, so an
    inventory cannot be written in one commit and consumed in a later one.
  * RENAMES, which are a documented FALSE POSITIVE and not a defect. A pure
    rename has zero net growth and still reds `unregistered set member` on the
    new path. The sanctioned remedy is a PAIRED baseline edit — remove the old
    member and add the new one in the SAME commit as the tree change — never an
    expansion row, which asks for two blind arms and a written adjudication for
    a move. The rule is stated in the baseline file's header, because friction
    with no stated remedy is how routine baseline edits get normalised, and the
    baseline is the one input this whole gate rests on.
  * SAME-COMMIT BASELINE GROWTH, which THIS script still cannot see and no
    longer has to. A baseline line added in the same commit as the file it
    names removes that file from the surplus, and the bijection cannot tell it
    from a line that was always there. Nothing here can: the census is gitless
    by design, so it has no "before" to compare against. That comparison now
    lives in cabinet/scripts/baseline-set-ratchet.py, a git-aware CI gate that
    reads the baseline at merge-base and at HEAD and refuses a NET addition
    while letting a paired rename through — see its docstring for the rules and
    for the residual IT names (a symbol-class swap). Removing a baseline line
    is still always safe here: it can only make the surplus larger.

COVERAGE, stated so nothing here reads as more than it is: bijection reaches
the six member classes named in BIJECTION_CLASSES. Growth in non-comment LINES
inside an existing module is a mass, not a set, and stays on allowances alone.
`adjudication` is shape-checked here and BOUND to its document (exists, and
names its member) by cabinet/scripts/tests/test_expansion_adjudication_binding.py,
which is source-side only because docs/plans and docs/proposals archive out of
the egg — a shipped copy would red a hatched cabinet for a document the export
deliberately removed.

Provenance: the 2026-07-27 two-model expansion-gate adjudication (Fable 5 +
Opus 5, blind, own clones), per the 2026-07-07 full-autonomy grant.
"""

from __future__ import annotations

import argparse
import ast
from datetime import date
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import sys
from typing import Any

import yaml


DEFAULT_CONTRACT = Path("cabinet/config/cognitive-architecture-contract.yml")
DEFAULT_BASELINE_SETS = Path("cabinet/config/architecture-baseline-sets.yml")
# The classes whose MEMBERS the census can name, and therefore the classes the
# expansion registry can hold to a bijection. Deliberately code, not data: a
# silent narrowing of this set would disable the registry for a whole class
# while every remaining arm stayed green, so it is pinned by a test.
#
# Excluded, each with its reason:
#   framework_production_noncomment_lines — a mass, not a set.
#   named_compiler_modules — pinned at 1 behind a declared invariant; a second
#       one is already unreachable, and it is a subset of the module class.
#   layer_debt_entries / layer_allowlist_entries — shrink-only ratchets owned by
#       cabinet/scripts/check-layer-separation.sh, entry by Captain-ratified
#       entry.
BIJECTION_CLASSES = frozenset(
    {
        "central_event_types",
        "central_action_types",
        "services_total",
        "services_enabled",
        "framework_production_modules",
        "duplicate_event_writer_sinks",
    }
)
#: The temporary_allowances rows that name a BIJECTION class and are permitted,
#: pinned as exact (phase, budget, additional) triples. Everything else naming a
#: bijection class is refused at contract load.
#:
#: WHY THE TRIPLE AND NOT THE PHASE NAME. A permit keyed on the phase alone
#: leaves the row EDITABLE: bumping COG-3 from 12 to 13 would buy a module for
#: one character, which is the same purchase this refusal exists to stop. The
#: `additional` is therefore part of the key, and a triple may appear at most
#: once — a verbatim copy of a permitted row is a second purchase.
#:
#: WHY THESE ELEVEN AND NOT THE NINE THE REVIEW NAMED. The review that proved
#: the bypass counted nine rows totalling +38. Two more landed on
#: framework_production_modules before the fix (`personal-preset-live`,
#: `source-ownership-class`, +1 each, total +40 against base 206 = 246 observed).
#: Both are registered expansions, so their MEMBERSHIP was adjudicated; only
#: their count rode an allowance. They are grandfathered rather than refused
#: because refusing them would red master for work that was already reviewed —
#: and the widening is stated here rather than made silently, which is the
#: point.
#:
#: CLOSED AND SHRINK-ONLY: this set is a legacy carve-out, never a place to add.
#: A twelfth entry is a new author choosing the instrument being closed; the
#: pin is asserted verbatim by
#: cabinet/scripts/tests/test_cognitive_architecture_census.py so growing it
#: cannot be quiet.
LEGACY_BIJECTION_ALLOWANCES = frozenset(
    {
        ("COG-0", "framework_production_modules", 2),
        ("COG-1", "framework_production_modules", 1),
        ("COG-2", "framework_production_modules", 5),
        ("COG-3", "framework_production_modules", 12),
        ("COG-4", "framework_production_modules", 10),
        ("captain-availability-dial", "framework_production_modules", 1),
        ("captain-contact-liveness", "framework_production_modules", 2),
        ("channel-flatline-alarm", "framework_production_modules", 1),
        ("personal-preset-live", "framework_production_modules", 1),
        ("source-ownership-class", "framework_production_modules", 1),
        ("spend-meter-uncapped", "framework_production_modules", 4),
    }
)
REQUIRED_EXPANSION_FIELDS = {
    "member",
    "member_class",
    "gate_date",
    "models_run",
    "adjudication",
    "merge_refuted",
    "consumer",
    "provenance",
}
EXPECTED_BASELINE_SET_KEYS = frozenset({"schema_version", "snapshot_of", "classes"})
BASELINE_SETS_SCHEMA_VERSION = "architecture-baseline-sets/v1"
# merge_refuted opens with a grep-able anchor, never prose: both near-misses the
# program caught before this gate existed were answerable by grepping a named
# symbol (a proposed engine whose value was a join something already did; a
# "missing rung" that was a verdict already granted). Prose may follow the
# anchor; the anchor itself must resolve.
MERGE_REFUTED_ANCHOR = re.compile(
    r"^(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9_]+)"
    r"::(?P<symbol>[A-Za-z_][A-Za-z0-9_.]{2,})$"
)
REQUIRED_ALLOWANCE_FIELDS = {
    "phase",
    "budget",
    "additional",
    "reason",
    "owner",
    "sunset",
    "deletion_gate",
}
REQUIRED_BUDGETS = frozenset(
    {
        "central_event_types",
        "central_action_types",
        "services_total",
        "services_enabled",
        "layer_debt_entries",
        "layer_allowlist_entries",
        "framework_production_modules",
        "framework_production_noncomment_lines",
        "named_compiler_modules",
        "duplicate_event_writer_sinks",
        # ── SET PINS (2026-07-27 expansion-gate adjudication, D3) ─────────────
        # The mass budgets above rglob framework/ ONLY and count *.py ONLY, so
        # cabinet/scripts/**, cabinet/config/**, .claude/** and every non-.py
        # file cost ZERO — the contract recorded that blind spot in writing (a
        # JSON schema file "adds ZERO modules and ZERO lines") and BOTH live
        # expansion escapes landed inside it. The gate ruled SPLIT: no
        # line-mass budget in cabinet/scripts (measured to false-positive
        # daily, and a detector that fires on every routine change is disabled
        # within a week — worse than a miss), but SET pins on the specific
        # classes both blind arms named. Each counts a SET whose growth is a
        # new scheduled decider, a new decision surface an officer reads, a
        # new live hook, a new verdict word or a new durable store.
        "organ_manifests",
        "claude_skills",
        "claude_hook_wirings",
        "framework_verdict_vocabulary_members",
        "cabinet_script_verdict_vocabulary_members",
        "durable_store_units",
    }
)
#: Budgets whose observed value is "files matching `pattern` under `path`".
PATTERN_SET_BUDGETS = frozenset({"organ_manifests", "claude_skills"})
#: Budgets whose observed value is "static members of every module-level
#: declaration whose NAME matches `symbol_pattern`, across the production
#: Python files under `path`".
SYMBOL_SET_BUDGETS = frozenset(
    {
        "framework_verdict_vocabulary_members",
        "cabinet_script_verdict_vocabulary_members",
    }
)
EXPECTED_TOP_KEYS = frozenset(
    {
        "schema_version",
        "baseline_sha",
        "budgets",
        "temporary_allowances",
        "expansions",
        "ownership",
        "declared_invariants",
        "enduring_architecture_gates",
    }
)
EXPECTED_OWNERSHIP = {
    "authoritative_state": "domain_transaction",
    "cross_domain_delivery": "transactional_outbox",
    "world_model": "rebuildable_projection",
    "evidence": "existing_evidence_plane",
    "promotion": "existing_gate_only",
}
EXPECTED_INVARIANTS = frozenset(
    {
        "independent_physical_safety_enforcers",
        "no_global_database_bus_or_compiler",
        "no_self_minted_graduation_credit",
        "captain_rooted_objectives",
        "shadow_before_authority",
        "namespaced_operations_single_constitutional_effect",
    }
)
EXPECTED_ENDURING_ARCHITECTURE_GATES = frozenset(
    {
        "bash cabinet/scripts/verify-cognitive-architecture.sh",
    }
)


class ContractError(ValueError):
    """The architecture contract is malformed or internally inconsistent."""


def _normalized_repo_path(value: str) -> str:
    """`./x` and `x` name the SAME path; string equality says they do not.

    Every disjointness comparison in this module goes through here. The
    consumer check was plain `==` until 2026-07-27, so `./framework/x.py`
    passed where `framework/x.py` was refused — a self-referencing consumer
    bought with two characters, measured on the live contract.
    """

    return PurePosixPath(value.strip()).as_posix()


def _confined_relative_path(value: str, what: str) -> str:
    """Reject absolute or escaping paths before anything resolves them."""

    pure = PurePosixPath(value)
    if not value.strip() or pure.is_absolute() or ".." in pure.parts:
        raise ContractError(f"{what} must be a relative, confined repository path")
    return value


def _validate_expansions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Schema-refuse every under- and over-specified expansion row.

    Structural only: nothing here touches the tree, so `load_contract` stays
    usable without a repository root. Tree resolution (does the refuted symbol
    exist, does the consumer resolve, is the member actually surplus) happens in
    `inspect_repository`.
    """

    expansions = raw["expansions"]
    if not isinstance(expansions, list):
        raise ContractError("expansions must be a list")
    seen: set[tuple[str, str]] = set()
    for expansion in expansions:
        if not isinstance(expansion, dict) or set(expansion) != REQUIRED_EXPANSION_FIELDS:
            raise ContractError(
                "expansion keys must be exactly member, member_class, gate_date, "
                "models_run, adjudication, merge_refuted, consumer, and provenance"
            )
        for field in ("member", "adjudication", "merge_refuted", "consumer", "provenance"):
            if not isinstance(expansion[field], str) or not expansion[field].strip():
                raise ContractError(f"expansion requires non-empty {field}")
        if expansion["member_class"] not in BIJECTION_CLASSES:
            raise ContractError(
                f"expansion member_class must be one of {sorted(BIJECTION_CLASSES)}"
            )
        key = (expansion["member_class"], expansion["member"])
        if key in seen:
            raise ContractError(
                f"duplicate expansion row for {key[0]} member {key[1]} — a surplus "
                "member is named by exactly one row"
            )
        seen.add(key)
        try:
            date.fromisoformat(expansion["gate_date"])
        except (TypeError, ValueError) as exc:
            raise ContractError("expansion gate_date must be YYYY-MM-DD") from exc
        models = expansion["models_run"]
        if not isinstance(models, list) or len(models) < 2:
            raise ContractError(
                "expansion models_run must list at least two independently-run arms"
            )
        if not all(isinstance(model, str) and model.strip() for model in models):
            raise ContractError("expansion models_run entries must be non-empty strings")
        if len({model.strip().casefold() for model in models}) != len(models):
            raise ContractError(
                "expansion models_run arms must be distinct — one model run twice "
                "is one opinion and an echo, not two"
            )
        adjudication = expansion["adjudication"].strip()
        _confined_relative_path(adjudication, "expansion adjudication")
        if not adjudication.endswith(".md"):
            raise ContractError(
                "expansion adjudication must name the written adjudication document (.md)"
            )
        anchor = MERGE_REFUTED_ANCHOR.match(expansion["merge_refuted"].split()[0])
        if anchor is None:
            raise ContractError(
                "expansion merge_refuted must OPEN with a <path>::<symbol> anchor, "
                "never prose — the merge question is answered by grep or not at all"
            )
        _confined_relative_path(anchor.group("path"), "expansion merge_refuted path")
        _confined_relative_path(expansion["consumer"].strip(), "expansion consumer")
    return expansions


def load_baseline_sets(path: Path) -> dict[str, frozenset[str]]:
    """Load the per-class member sets the registry measures surplus against."""

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ContractError("architecture baseline sets must be a mapping")
    if raw.get("schema_version") != BASELINE_SETS_SCHEMA_VERSION:
        raise ContractError("unsupported architecture baseline-sets schema_version")
    if set(raw) != EXPECTED_BASELINE_SET_KEYS:
        raise ContractError(
            f"baseline-set keys must be exactly {sorted(EXPECTED_BASELINE_SET_KEYS)}"
        )
    if (
        not isinstance(raw["snapshot_of"], str)
        or re.fullmatch(r"[0-9a-f]{40}", raw["snapshot_of"]) is None
    ):
        raise ContractError("baseline-set snapshot_of must be a 40-character lowercase git SHA")
    classes = raw["classes"]
    if not isinstance(classes, dict) or set(classes) != set(BIJECTION_CLASSES):
        raise ContractError(
            f"baseline-set classes must be exactly {sorted(BIJECTION_CLASSES)}"
        )
    resolved: dict[str, frozenset[str]] = {}
    for name, members in classes.items():
        if not isinstance(members, list) or not members:
            raise ContractError(f"baseline set {name} must be a non-empty list")
        if not all(isinstance(member, str) and member.strip() for member in members):
            raise ContractError(f"baseline set {name} members must be non-empty strings")
        if len(set(members)) != len(members):
            raise ContractError(f"baseline set {name} contains duplicate members")
        resolved[name] = frozenset(members)
    return resolved


def _non_comment_line_count(path: Path) -> int:
    return sum(
        1
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _eval_static(node: ast.AST, names: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        values = {_eval_static(element, names) for element in node.elts}
        if not all(isinstance(value, str) for value in values):
            raise ContractError("enum contains a non-string member")
        return values
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _eval_static(node.left, names)
        right = _eval_static(node.right, names)
        if not isinstance(left, set) or not isinstance(right, set):
            raise ContractError("enum union contains a non-set operand")
        return left | right
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"frozenset", "set"}
        and len(node.args) == 1
        and not node.keywords
    ):
        value = _eval_static(node.args[0], names)
        if not isinstance(value, set):
            raise ContractError(f"{node.func.id} enum value is not a set")
        return value
    raise ContractError(f"unsupported static enum expression: {ast.dump(node)}")


def static_enum(path: Path, symbol: str) -> frozenset[str]:
    """Resolve a module-level set/frozenset without importing the module."""

    tree = ast.parse(path.read_text(), filename=str(path))
    names: dict[str, Any] = {}
    aliases: set[str] = set()
    protected_seen = False
    mutators = {"add", "clear", "difference_update", "discard", "intersection_update", "pop", "remove", "symmetric_difference_update", "update"}
    for statement in tree.body:
        if isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
            if statement.target.id == symbol or statement.target.id in aliases:
                raise ContractError(f"protected enum {symbol} uses augmented mutation")
        if isinstance(statement, ast.Delete):
            for target in statement.targets:
                if isinstance(target, ast.Name) and (target.id == symbol or target.id in aliases):
                    raise ContractError(f"protected enum {symbol} is deleted")
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            func = statement.value.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in ({symbol} | aliases)
                and func.attr in mutators
            ):
                raise ContractError(f"protected enum {symbol} uses mutating call {func.attr}")
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                continue
            name = statement.targets[0].id
            value_node = statement.value
        else:
            if not isinstance(statement.target, ast.Name) or statement.value is None:
                continue
            name = statement.target.id
            value_node = statement.value
        if isinstance(value_node, ast.Name) and value_node.id in ({symbol} | aliases):
            aliases.add(name)
        else:
            aliases.discard(name)
        try:
            names[name] = _eval_static(value_node, names)
        except ContractError:
            if name == symbol or name in aliases:
                raise
            continue
        if name == symbol:
            value = names[name]
            if not isinstance(value, set):
                raise ContractError(f"{symbol} is not a static set")
            protected_seen = True
    if not protected_seen:
        raise ContractError(f"could not resolve static enum {symbol} in {path}")
    return frozenset(names[symbol])


def _production_python_files(path: Path) -> list[Path]:
    return sorted(
        candidate
        for candidate in path.rglob("*.py")
        if "tests" not in candidate.parts and "__pycache__" not in candidate.parts
    )


def _pattern_set(path: Path, pattern: str | list[str]) -> list[Path]:
    """Files matching ANY of `pattern` anywhere under `path`, DERIVED from the tree.

    Never a hand-maintained list: a new organ manifest or a new skill is a new
    file, and the pin reads the directory rather than a fourth list that can
    drift away from it. Nested matches count — a manifest parked one directory
    down is still a new decider.

    A LIST of patterns, not one, because a class whose runtime accepts several
    spellings is only pinned if the pin accepts all of them: organ manifests
    load from `framework/organs/registry.py::MANIFEST_SUFFIXES` (.yml, .yaml,
    .json), so a `*.yml`-only pin was defeated by naming the sixth organ
    `.yaml` — a live organ in the registry, free, proven by execution
    2026-07-27. The spellings are contract DATA so widening stays a data edit.

    NOT-A-DIRECTORY is an ERROR, exactly like a missing one. `Path.rglob` over
    a regular file yields nothing, so a contract path pointed at a file read
    ZERO and passed — the disabled sensor this function's own docstring says it
    refuses.
    """

    if not path.exists():
        raise ContractError(f"set-pin directory is missing: {path}")
    if not path.is_dir():
        raise ContractError(f"set-pin path is not a directory: {path}")
    patterns = [pattern] if isinstance(pattern, str) else list(pattern)
    matched = {
        candidate
        for one in patterns
        for candidate in path.rglob(one)
        if candidate.is_file() and "__pycache__" not in candidate.parts
    }
    return sorted(matched)


def _durable_store_units(path: Path) -> frozenset[str]:
    """The durable-store SET, derived from `.gitignore` exactly as the deploy
    preflight already derives it.

    `.gitignore` IS the store registry: a fresh `git worktree` contains tracked
    files and nothing else, so every positively-ignored path is precisely what
    the cabinet accumulates at runtime and must be carried across a deploy.
    `cabinet/scripts/state-persistence-preflight.py` reads it that way and says
    why in its own words — it "does NOT add a fourth hand-maintained list", it
    DERIVES the set. This pin reuses both of that reader's rules verbatim:
    negations and comments are skipped (a negation only re-includes a TRACKED
    file, which survives a fresh worktree by definition), and each pattern is
    reduced to its durability UNIT — the deepest wildcard-free prefix, so
    `memory/logs/*.jsonl` and `memory/logs/*.log` are ONE store, not two.

    Counting raw lines instead was measured and rejected: 38 of the 39 commits
    that touched `.gitignore` in 30 days would have fired, which is the daily
    false-positive the same gate refused for cabinet/scripts line mass. Units
    move only when a NEW store appears.
    """

    units: set[str] = set()
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        pattern = line.rstrip("/").lstrip("/")
        parts: list[str] = []
        for segment in pattern.split("/"):
            if any(char in segment for char in "*?["):
                break
            parts.append(segment)
        units.add("/".join(parts) if parts else pattern)
    if not units:
        raise ContractError(f"{path} yielded no durable-store units")
    return frozenset(units)


def _claude_hook_wirings(path: Path) -> int:
    """Count LIVE Claude-Code hook commands wired in a settings file.

    The wiring — not the script on disk — is what makes a hook fire, so the
    pin counts entries under `hooks.<Event>[].hooks[]`. Every shape is
    validated: a malformed or renamed section must be an ERROR, never a
    silently smaller count (a pin that reads 0 on a mangled file is a pin that
    rewards mangling the file).
    """

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ContractError(f"claude settings is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("claude settings must be a JSON object")
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        raise ContractError("claude settings must declare a hooks mapping")
    total = 0
    for event, entries in sorted(hooks.items()):
        if not isinstance(entries, list):
            raise ContractError(f"claude hook event {event} must hold a list")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ContractError(f"claude hook entry {event}[{index}] must be a mapping")
            commands = entry.get("hooks")
            if not isinstance(commands, list):
                raise ContractError(f"claude hook entry {event}[{index}] requires a hooks list")
            for command in commands:
                if not isinstance(command, dict) or not isinstance(command.get("command"), str):
                    raise ContractError(
                        f"claude hook command under {event} must declare a string command"
                    )
            total += len(commands)
    return total


def _static_vocabulary(node: ast.AST, names: dict[str, frozenset[Any]]) -> frozenset[Any]:
    """Resolve a declared vocabulary to its member set without importing it.

    Deliberately WIDER than `_eval_static`, which fails closed on a non-string
    member because a central enum may only hold strings. A satellite verdict
    vocabulary is a tuple here, a dict there, and one of them carries a None
    member — so this resolver accepts any hashable literal, a dict's KEYS, and
    a bare scalar (one member: three shipped verdict tokens are declared as
    lone constants). Anything it cannot read statically RAISES: a vocabulary
    built at import time would otherwise cost the pin nothing.
    """

    if isinstance(node, ast.Constant):
        try:
            hash(node.value)
        except TypeError as exc:
            raise ContractError("vocabulary member is not hashable") from exc
        return frozenset({node.value})
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        members: set[Any] = set()
        for element in node.elts:
            members |= _static_vocabulary(element, names)
        return frozenset(members)
    if isinstance(node, ast.Dict):
        keys: set[Any] = set()
        for key in node.keys:
            if key is None:
                raise ContractError("vocabulary dict uses ** unpacking")
            keys |= _static_vocabulary(key, names)
        return frozenset(keys)
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _static_vocabulary(node.left, names) | _static_vocabulary(node.right, names)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"frozenset", "set", "tuple", "list", "dict"}
        and len(node.args) <= 1
        and not node.keywords
    ):
        if not node.args:
            return frozenset()
        return _static_vocabulary(node.args[0], names)
    raise ContractError(f"unsupported static vocabulary expression: {ast.dump(node)}")


_VOCABULARY_MUTATORS = frozenset(
    {
        "add",
        "append",
        "clear",
        "difference_update",
        "discard",
        "extend",
        "intersection_update",
        "pop",
        "popitem",
        "remove",
        "setdefault",
        "symmetric_difference_update",
        "update",
    }
)


def vocabulary_members(path: Path, symbol_pattern: re.Pattern[str]) -> dict[str, frozenset[Any]]:
    """Every module-level vocabulary in `path` whose NAME matches the pattern.

    Discovery is by NAME against the tree, so a vocabulary added in a file the
    census has never heard of is found on the run it lands. Mutation is
    refused for the same reason `static_enum` refuses it on the central enums:
    an in-place `.add()` grows the vocabulary while the literal stays pinned.
    """

    tree = ast.parse(path.read_text(), filename=str(path))
    names: dict[str, frozenset[Any]] = {}
    found: dict[str, frozenset[Any]] = {}
    for statement in tree.body:
        if isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
            if symbol_pattern.search(statement.target.id):
                raise ContractError(
                    f"vocabulary {statement.target.id} in {path} uses augmented mutation"
                )
        if isinstance(statement, ast.Delete):
            for target in statement.targets:
                if isinstance(target, ast.Name) and symbol_pattern.search(target.id):
                    raise ContractError(f"vocabulary {target.id} in {path} is deleted")
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            func = statement.value.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and symbol_pattern.search(func.value.id)
                and func.attr in _VOCABULARY_MUTATORS
            ):
                raise ContractError(
                    f"vocabulary {func.value.id} in {path} uses mutating call {func.attr}"
                )
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value_node = statement.value
        else:
            targets = [statement.target]
            value_node = statement.value
        if value_node is None:
            continue
        for target in targets:
            if isinstance(target, (ast.Tuple, ast.List)):
                for element in target.elts:
                    if isinstance(element, ast.Name) and symbol_pattern.search(element.id):
                        raise ContractError(
                            f"vocabulary {element.id} in {path} is declared by unpacking"
                        )
                continue
            if not isinstance(target, ast.Name):
                continue
            try:
                resolved = _static_vocabulary(value_node, names)
            except ContractError:
                if symbol_pattern.search(target.id):
                    raise
                names.pop(target.id, None)
                continue
            names[target.id] = resolved
            if symbol_pattern.search(target.id):
                found[target.id] = resolved
    return found


def _vocabulary_member_count(root: Path, symbol_pattern: str) -> int:
    pattern = re.compile(symbol_pattern)
    return sum(
        len(members)
        for path in _production_python_files(root)
        for members in vocabulary_members(path, pattern).values()
    )


def _static_prefixed_callees(path: Path, symbol: str, prefix: str) -> frozenset[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol
        ),
        None,
    )
    if target is None:
        raise ContractError(f"could not resolve function {symbol} in {path}")
    return frozenset(
        node.func.id
        for node in ast.walk(target)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id.startswith(prefix)
    )


def load_contract(path: Path, *, as_of: date | None = None) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ContractError("architecture contract must be a mapping")
    if raw.get("schema_version") != "cognitive-architecture-contract/v1":
        raise ContractError("unsupported architecture contract schema_version")
    if set(raw) != EXPECTED_TOP_KEYS:
        raise ContractError(f"architecture contract keys must be exactly {sorted(EXPECTED_TOP_KEYS)}")
    if not isinstance(raw.get("baseline_sha"), str) or re.fullmatch(r"[0-9a-f]{40}", raw["baseline_sha"]) is None:
        raise ContractError("baseline_sha must be a 40-character lowercase git SHA")
    budgets = raw.get("budgets")
    if not isinstance(budgets, dict) or set(budgets) != REQUIRED_BUDGETS:
        raise ContractError(f"architecture contract budgets must be exactly {sorted(REQUIRED_BUDGETS)}")
    for name, budget in budgets.items():
        if not isinstance(budget, dict):
            raise ContractError(f"budget {name} must be a mapping")
        if not isinstance(budget.get("path"), str) or not budget["path"]:
            raise ContractError(f"budget {name} requires path")
        pure_path = PurePosixPath(budget["path"])
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise ContractError(f"budget {name} path must be relative and confined")
        maximum = budget.get("maximum")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
            raise ContractError(f"budget {name} requires a non-negative integer maximum")
        expected_keys = {"path", "maximum"}
        if name in {"central_event_types", "central_action_types"}:
            expected_keys.add("symbol")
            if not isinstance(budget.get("symbol"), str) or not budget["symbol"].isidentifier():
                raise ContractError(f"budget {name} requires a Python symbol")
        if name == "named_compiler_modules":
            expected_keys.add("pattern")
            if not isinstance(budget.get("pattern"), str) or not budget["pattern"]:
                raise ContractError("named_compiler_modules requires pattern")
        if name in PATTERN_SET_BUDGETS:
            expected_keys.add("pattern")
            # One spelling or several: a class the runtime loads under several
            # suffixes is only pinned when every spelling is named (the
            # organ-manifest escape, 2026-07-27). An EMPTY list would match
            # nothing and read zero, so it is refused like a missing key.
            raw_pattern = budget.get("pattern")
            spellings = [raw_pattern] if isinstance(raw_pattern, str) else raw_pattern
            if (
                not isinstance(spellings, list)
                or not spellings
                or not all(isinstance(one, str) and one.strip() for one in spellings)
            ):
                raise ContractError(
                    f"set pin {name} requires pattern — a non-empty string or a "
                    "non-empty list of non-empty strings"
                )
        if name in SYMBOL_SET_BUDGETS:
            expected_keys.add("symbol_pattern")
            if not isinstance(budget.get("symbol_pattern"), str) or not budget["symbol_pattern"]:
                raise ContractError(f"set pin {name} requires symbol_pattern")
            try:
                re.compile(budget["symbol_pattern"])
            except re.error as exc:
                raise ContractError(f"set pin {name} symbol_pattern is not a regex") from exc
        if name == "duplicate_event_writer_sinks":
            expected_keys.update({"symbol", "callee_prefix"})
            if not isinstance(budget.get("symbol"), str) or not budget["symbol"].isidentifier():
                raise ContractError("duplicate_event_writer_sinks requires a Python symbol")
            if not isinstance(budget.get("callee_prefix"), str) or not budget["callee_prefix"]:
                raise ContractError("duplicate_event_writer_sinks requires callee_prefix")
        if set(budget) != expected_keys:
            raise ContractError(f"budget {name} keys must be exactly {sorted(expected_keys)}")

    if raw.get("ownership") != EXPECTED_OWNERSHIP:
        raise ContractError("ownership declaration diverges from the Phase-0 contract")
    declared = raw.get("declared_invariants")
    if not isinstance(declared, list) or set(declared) != EXPECTED_INVARIANTS or len(declared) != len(EXPECTED_INVARIANTS):
        raise ContractError("declared_invariants must be the closed Phase-0 invariant set")
    gates = raw.get("enduring_architecture_gates")
    if (
        not isinstance(gates, list)
        or set(gates) != EXPECTED_ENDURING_ARCHITECTURE_GATES
        or len(gates) != len(EXPECTED_ENDURING_ARCHITECTURE_GATES)
    ):
        raise ContractError("enduring_architecture_gates must be the closed portable gate set")

    allowances = raw.get("temporary_allowances", [])
    if not isinstance(allowances, list):
        raise ContractError("temporary_allowances must be a list")
    legacy_seen: set[tuple[str, str, int]] = set()
    for allowance in allowances:
        if not isinstance(allowance, dict) or set(allowance) != REQUIRED_ALLOWANCE_FIELDS:
            raise ContractError(
                "temporary allowance keys must be exactly phase, budget, additional, "
                "reason, owner, sunset, and deletion_gate"
            )
        if allowance["budget"] not in budgets:
            raise ContractError(f"temporary allowance names unknown budget {allowance['budget']}")
        additional = allowance["additional"]
        if not isinstance(additional, int) or isinstance(additional, bool) or additional <= 0:
            raise ContractError("temporary allowance additional must be a positive integer")
        for field in ("phase", "reason", "owner", "deletion_gate"):
            if not isinstance(allowance[field], str) or not allowance[field].strip():
                raise ContractError(f"temporary allowance requires non-empty {field}")
        try:
            sunset = date.fromisoformat(allowance["sunset"])
        except (TypeError, ValueError) as exc:
            raise ContractError("temporary allowance sunset must be YYYY-MM-DD") from exc
        # An allowance may not name a class whose MEMBERS the registry can see.
        # Refused at LOAD rather than reported as a failure: a census that
        # merely reds can be argued with, and this instrument is the one an
        # adversarial review proved buys a net-new member for one data line.
        if allowance["budget"] in BIJECTION_CLASSES:
            legacy_key = (allowance["phase"], allowance["budget"], allowance["additional"])
            if legacy_key not in LEGACY_BIJECTION_ALLOWANCES:
                raise ContractError(
                    f"temporary allowance {allowance['phase']!r} names the bijection "
                    f"class {allowance['budget']} — an allowance pays for MASS and asks "
                    "only reason/owner/sunset, so it may not pay for a class whose "
                    "members the expansion registry names. Raise the budget maximum "
                    "visibly and register the member as an expansion."
                )
            if legacy_key in legacy_seen:
                raise ContractError(
                    f"temporary allowance {allowance['phase']!r} duplicates a "
                    f"grandfathered bijection-class row on {allowance['budget']} — the "
                    "legacy carve-out is consumed once, never copied"
                )
            legacy_seen.add(legacy_key)
        allowance["_expired"] = sunset < (as_of or date.today())
    _validate_expansions(raw)
    return raw


def _effective_maximum(contract: dict[str, Any], budget_name: str) -> tuple[int, list[str]]:
    maximum = contract["budgets"][budget_name]["maximum"]
    expired: list[str] = []
    for allowance in contract.get("temporary_allowances", []):
        if allowance["budget"] != budget_name:
            continue
        if allowance.get("_expired"):
            expired.append(allowance["phase"])
        else:
            maximum += allowance["additional"]
    return maximum, expired


def _bijection_failures(
    contract: dict[str, Any],
    member_sets: dict[str, frozenset[str]],
    baseline_sets: dict[str, frozenset[str]],
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """observed - baseline == the registered members, exactly and disjointly.

    Four distinct lies, four distinct reds. The registry is not a presence
    check: nothing here asks whether a row EXISTS, only whether the rows and the
    surplus are the same set — which a copied row or a touched file cannot
    satisfy. Editing the BASELINE can, and that is the honest limit of the
    assertion: a member listed as pre-existing is not surplus, so the bijection
    holds trivially. What the arms below reach is everything except a baseline
    line written in the same commit as the member it excuses.

    The fourth arm is about the BASELINE, not the rows. `observed - baseline`
    silently ignores a baseline name the tree does not carry, so before
    2026-07-27 an inventory could be written into the baseline file in one
    commit — moving no count, reddening nothing — and the files consumed in a
    later one, each arriving pre-excused from the surplus. A baseline name with
    no tree member is therefore a failure. It is a hard red and not a warning
    because the remedy is always a SAFE edit: deleting a baseline line can only
    make the surplus larger, never smaller, so nothing is bought by fixing it —
    and a report nobody has to act on is the disabled sensor this program keeps
    finding in its own tests.
    """

    rows_by_class: dict[str, set[str]] = {}
    for expansion in contract["expansions"]:
        rows_by_class.setdefault(expansion["member_class"], set()).add(expansion["member"])

    surplus: dict[str, list[str]] = {}
    failures: list[dict[str, Any]] = []
    for name in sorted(BIJECTION_CLASSES):
        observed_members = member_sets[name]
        baseline_members = baseline_sets[name]
        registered = rows_by_class.get(name, set())
        class_surplus = observed_members - baseline_members
        surplus[name] = sorted(class_surplus)
        for member in sorted(class_surplus - registered):
            failures.append(
                {
                    "budget": name,
                    "member": member,
                    "reason": "unregistered set member",
                }
            )
        for member in sorted(registered - observed_members):
            failures.append(
                {
                    "budget": name,
                    "member": member,
                    "reason": "expansion row names a member that is not present",
                }
            )
        for member in sorted(registered & baseline_members):
            failures.append(
                {
                    "budget": name,
                    "member": member,
                    "reason": "expansion row names a baseline member",
                }
            )
        for member in sorted(baseline_members - observed_members):
            failures.append(
                {
                    "budget": name,
                    "member": member,
                    "reason": "baseline names a member the tree does not carry",
                }
            )
    return surplus, failures


def _expansion_binding_failures(
    root: Path,
    contract: dict[str, Any],
    budgets: dict[str, Any],
    service_names: set[str],
) -> list[dict[str, Any]]:
    """Resolve the two fields that must survive a hostile reading.

    `merge_refuted` is answered by grep or not at all: the anchor's file must
    exist and must contain the symbol it names, so a merge question cannot be
    closed with prose. `consumer` must be a path that exists or a service the
    fleet manifest declares, and must be neither the member itself nor the file
    that declares it — "name the consumer before adding the producer" is not
    satisfied by the producer naming itself.

    WHAT `consumer` IS, said plainly because the sentence above overclaims it:
    an EXISTENCE-AND-DISJOINTNESS check, never a USE check. Nothing here reads
    the named file, parses it, or asks whether it imports, calls or otherwise
    consumes the member. Any path that exists in the tree satisfies it —
    `.git/config` does, measured — as does any name in the fleet manifest. It
    stops the producer from naming ITSELF, and stops the field being empty. A
    real use check would have to resolve the member's public symbols and find a
    reference to one of them; that is not what this does, and a reader who
    believed otherwise would be trusting a check that was never written.

    The disjointness half was ALSO defeatable until 2026-07-27: the comparison
    was plain string equality, so `./framework/x.py` passed where
    `framework/x.py` was refused. Both sides now normalise through
    `_normalized_repo_path`.
    """

    failures: list[dict[str, Any]] = []
    for expansion in contract["expansions"]:
        member = expansion["member"]
        member_class = expansion["member_class"]
        anchor = MERGE_REFUTED_ANCHOR.match(expansion["merge_refuted"].split()[0])
        refuted_path = root / anchor.group("path")
        symbol = anchor.group("symbol")
        if not refuted_path.is_file():
            failures.append(
                {
                    "budget": member_class,
                    "member": member,
                    "reason": f"merge_refuted names a path that is absent: {anchor.group('path')}",
                }
            )
        elif symbol not in refuted_path.read_text(encoding="utf-8", errors="ignore"):
            failures.append(
                {
                    "budget": member_class,
                    "member": member,
                    "reason": f"merge_refuted symbol is absent from the file it names: {symbol}",
                }
            )
        consumer = _normalized_repo_path(expansion["consumer"])
        forbidden = {
            _normalized_repo_path(member),
            _normalized_repo_path(budgets[member_class]["path"]),
        }
        if consumer in forbidden:
            failures.append(
                {
                    "budget": member_class,
                    "member": member,
                    "reason": "consumer must READ the output — not the member itself "
                    "and not the file that declares it",
                }
            )
        elif consumer not in service_names and not (root / consumer).exists():
            failures.append(
                {
                    "budget": member_class,
                    "member": member,
                    "reason": f"consumer resolves to neither a repository path nor a "
                    f"declared service: {consumer}",
                }
            )
    return failures


def inspect_repository(
    root: Path,
    contract_path: Path | None = None,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    path = contract_path or root / DEFAULT_CONTRACT
    if not path.is_absolute():
        path = root / path
    evaluation_date = as_of or date.today()
    contract = load_contract(path, as_of=evaluation_date)
    budgets = contract["budgets"]

    event_budget = budgets["central_event_types"]
    action_budget = budgets["central_action_types"]
    event_types = static_enum(root / event_budget["path"], event_budget["symbol"])
    action_types = static_enum(root / action_budget["path"], action_budget["symbol"])
    services = yaml.safe_load((root / budgets["services_total"]["path"]).read_text())
    service_rows = services.get("services") if isinstance(services, dict) else None
    if not isinstance(service_rows, list):
        raise ContractError("cabinet services manifest must contain a services list")
    service_names: list[str] = []
    for index, row in enumerate(service_rows):
        if not isinstance(row, dict):
            raise ContractError(f"service row {index} must be a mapping")
        if "disabled" in row and not isinstance(row["disabled"], bool):
            raise ContractError(f"service row {index} disabled must be boolean")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ContractError(f"service row {index} requires a non-empty name")
        service_names.append(name)
    # Two rows under one name would make the member set smaller than the row
    # count and hide a service from the registry while the count budget still
    # read it — the set and the count must describe the same fleet.
    if len(set(service_names)) != len(service_names):
        raise ContractError("cabinet services manifest contains duplicate service names")

    observed = {
        "central_event_types": len(event_types),
        "central_action_types": len(action_types),
        "services_total": len(service_rows),
        "services_enabled": sum(not bool(row.get("disabled", False)) for row in service_rows),
        "layer_debt_entries": _non_comment_line_count(
            root / budgets["layer_debt_entries"]["path"]
        ),
        "layer_allowlist_entries": _non_comment_line_count(
            root / budgets["layer_allowlist_entries"]["path"]
        ),
    }
    production_files = _production_python_files(
        root / budgets["framework_production_modules"]["path"]
    )
    observed["framework_production_modules"] = len(production_files)
    observed["framework_production_noncomment_lines"] = sum(
        _non_comment_line_count(path) for path in production_files
    )
    compiler_budget = budgets["named_compiler_modules"]
    observed["named_compiler_modules"] = len(
        [
            path
            for path in (root / compiler_budget["path"]).rglob(compiler_budget["pattern"])
            if "tests" not in path.parts and "__pycache__" not in path.parts
        ]
    )
    writer_budget = budgets["duplicate_event_writer_sinks"]
    writer_sinks = _static_prefixed_callees(
        root / writer_budget["path"],
        writer_budget["symbol"],
        writer_budget["callee_prefix"],
    )
    observed["duplicate_event_writer_sinks"] = len(writer_sinks)
    # ── SET PINS (D3) — the surfaces the mass budgets above cannot see ───────
    # `.gitignore` is ALREADY the durable-store registry, so the store set is
    # DERIVED from it rather than hand-maintained as a fourth list.
    observed["durable_store_units"] = len(
        _durable_store_units(root / budgets["durable_store_units"]["path"])
    )
    observed["claude_hook_wirings"] = _claude_hook_wirings(
        root / budgets["claude_hook_wirings"]["path"]
    )
    for name in sorted(PATTERN_SET_BUDGETS):
        observed[name] = len(
            _pattern_set(root / budgets[name]["path"], budgets[name]["pattern"])
        )
    for name in sorted(SYMBOL_SET_BUDGETS):
        observed[name] = _vocabulary_member_count(
            root / budgets[name]["path"], budgets[name]["symbol_pattern"]
        )

    member_sets: dict[str, frozenset[str]] = {
        "central_event_types": frozenset(event_types),
        "central_action_types": frozenset(action_types),
        "services_total": frozenset(service_names),
        "services_enabled": frozenset(
            row["name"] for row in service_rows if not bool(row.get("disabled", False))
        ),
        "framework_production_modules": frozenset(
            path.relative_to(root).as_posix() for path in production_files
        ),
        "duplicate_event_writer_sinks": frozenset(writer_sinks),
    }
    if set(member_sets) != set(BIJECTION_CLASSES):
        raise ContractError("member sets diverge from the declared bijection classes")

    failures: list[dict[str, Any]] = []
    maximums: dict[str, int] = {}
    for name, actual in observed.items():
        maximum, expired = _effective_maximum(contract, name)
        maximums[name] = maximum
        if expired:
            failures.append(
                {
                    "budget": name,
                    "observed": actual,
                    "maximum": maximum,
                    "reason": "expired temporary allowance",
                    "phases": expired,
                }
            )
        if actual > maximum:
            failures.append(
                {
                    "budget": name,
                    "observed": actual,
                    "maximum": maximum,
                    "reason": "budget exceeded",
                }
            )

    baseline_sets = load_baseline_sets(root / DEFAULT_BASELINE_SETS)
    surplus, bijection_failures = _bijection_failures(contract, member_sets, baseline_sets)
    failures.extend(bijection_failures)
    failures.extend(_expansion_binding_failures(root, contract, budgets, set(service_names)))
    return {
        "schema_version": "cognitive-architecture-census/v1",
        "baseline_sha": contract["baseline_sha"],
        "as_of": evaluation_date.isoformat(),
        # The observed members themselves, so the git-aware baseline ratchet
        # (cabinet/scripts/baseline-set-ratchet.py) can ask THIS derivation what
        # a tree holds instead of growing a second copy of it. Reported, never
        # enforced here — the bijection above is what enforces.
        "member_sets": {name: sorted(members) for name, members in member_sets.items()},
        "observed": observed,
        "maximums": maximums,
        "surplus_members": surplus,
        "failures": failures,
        "ok": not failures,
    }


def _human_report(report: dict[str, Any]) -> str:
    status = "PASS" if report["ok"] else "FAIL"
    lines = [f"cognitive architecture census: {status}"]
    for name, actual in report["observed"].items():
        lines.append(f"  {name}: {actual} <= {report['maximums'][name]}")
    for name, members in sorted(report["surplus_members"].items()):
        if members:
            lines.append(f"  registered expansion in {name}: {', '.join(members)}")
    for failure in report["failures"]:
        if "member" in failure:
            lines.append(
                f"  BLOCK {failure['budget']}: {failure['reason']} [{failure['member']}]"
            )
        else:
            lines.append(
                f"  BLOCK {failure['budget']}: {failure['reason']} "
                f"({failure['observed']} > {failure['maximum']})"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--check", action="store_true", help="exit non-zero on a breach")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        help="evaluate allowance sunsets on YYYY-MM-DD (defaults to the local date)",
    )
    args = parser.parse_args(argv)
    try:
        report = inspect_repository(args.root, args.contract, as_of=args.as_of)
    except (OSError, SyntaxError, ContractError, yaml.YAMLError) as exc:
        print(f"cognitive architecture census error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_human_report(report))
    return 1 if args.check and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
