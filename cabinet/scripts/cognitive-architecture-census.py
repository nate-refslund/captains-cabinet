#!/usr/bin/env python3
"""Read-only architecture budget census for the Cognitive Core program.

The census deliberately parses source instead of importing framework modules:
it must work in a gitless clean hatch and must never trigger runtime state,
environment, event, or connector side effects.
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


def _pattern_set(path: Path, pattern: str) -> list[Path]:
    """Files matching `pattern` anywhere under `path`, DERIVED from the tree.

    Never a hand-maintained list: a new organ manifest or a new skill is a new
    file, and the pin reads the directory rather than a fourth list that can
    drift away from it. Nested matches count — a manifest parked one directory
    down is still a new decider.
    """

    if not path.exists():
        raise ContractError(f"set-pin directory is missing: {path}")
    return sorted(
        candidate
        for candidate in path.rglob(pattern)
        if candidate.is_file() and "__pycache__" not in candidate.parts
    )


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
            if not isinstance(budget.get("pattern"), str) or not budget["pattern"]:
                raise ContractError(f"set pin {name} requires pattern")
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
        allowance["_expired"] = sunset < (as_of or date.today())
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
    for index, row in enumerate(service_rows):
        if not isinstance(row, dict):
            raise ContractError(f"service row {index} must be a mapping")
        if "disabled" in row and not isinstance(row["disabled"], bool):
            raise ContractError(f"service row {index} disabled must be boolean")

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
    observed["duplicate_event_writer_sinks"] = len(
        _static_prefixed_callees(
            root / writer_budget["path"],
            writer_budget["symbol"],
            writer_budget["callee_prefix"],
        )
    )
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
    return {
        "schema_version": "cognitive-architecture-census/v1",
        "baseline_sha": contract["baseline_sha"],
        "as_of": evaluation_date.isoformat(),
        "observed": observed,
        "maximums": maximums,
        "failures": failures,
        "ok": not failures,
    }


def _human_report(report: dict[str, Any]) -> str:
    status = "PASS" if report["ok"] else "FAIL"
    lines = [f"cognitive architecture census: {status}"]
    for name, actual in report["observed"].items():
        lines.append(f"  {name}: {actual} <= {report['maximums'][name]}")
    for failure in report["failures"]:
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
