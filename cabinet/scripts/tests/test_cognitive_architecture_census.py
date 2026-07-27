from __future__ import annotations

import importlib.util
from datetime import date
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "cabinet" / "scripts" / "cognitive-architecture-census.py"
CONTRACT = ROOT / "cabinet" / "config" / "cognitive-architecture-contract.yml"
BASELINE_SETS = ROOT / "cabinet" / "config" / "architecture-baseline-sets.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("cognitive_architecture_census", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _python_only(directory: str, names: list[str]) -> set[str]:
    """copytree filter: keep directories and *.py, drop everything else.

    The census reads cabinet/scripts for exactly one thing — module-level
    verdict vocabularies in production *.py — so the mutant tree needs nothing
    else, and `tests` is dropped because the census excludes it by definition.
    """

    base = Path(directory)
    return {
        name
        for name in names
        if name in {"__pycache__", "tests"}
        or (not (base / name).is_dir() and not name.endswith(".py"))
    }


def _copy_census_tree(tmp_path: Path) -> Path:
    dst = tmp_path / "gitless-cabinet"
    shutil.copytree(ROOT / "framework", dst / "framework")
    # Set-pin source DIRS (2026-07-27 expansion gate): copied so a mutant can
    # add a member the way a real landing would — a new manifest, a new skill
    # directory, a new production module carrying a vocabulary. cabinet/scripts
    # is copied .py-only (the census reads nothing else there) to keep ~8 MB
    # per mutant out of every parametrized case.
    for rel_dir in ("cabinet/config/organs", ".claude/skills"):
        shutil.copytree(
            ROOT / rel_dir,
            dst / rel_dir,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copytree(
        ROOT / "cabinet/scripts",
        dst / "cabinet/scripts",
        ignore=_python_only,
    )
    for rel in (
        "cabinet/config/cognitive-architecture-contract.yml",
        "cabinet/config/architecture-baseline-sets.yml",
        "cabinet/scripts/cognitive-architecture-census.py",
        "cabinet/services.yml",
        ".layer-separation-baseline",
        ".layer-separation-allowlist",
        ".claude/settings.json",
        ".gitignore",
    ):
        source = ROOT / rel
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return dst


def test_pinned_repository_matches_architecture_contract():
    census = _load_module()
    report = census.inspect_repository(ROOT)

    assert report["ok"] is True
    assert set(report["observed"]) == set(report["maximums"])
    assert all(
        report["observed"][name] <= report["maximums"][name]
        for name in report["observed"]
    )


@pytest.mark.parametrize(
    ("relative_path", "needle", "replacement", "budget"),
    (
        (
            "framework/events/emitter.py",
            "VALID_EVENT_TYPES = frozenset({",
            'VALID_EVENT_TYPES = frozenset({\n    "phase0_mutant_event",',
            "central_event_types",
        ),
        (
            "framework/authority/classifier.py",
            "_REVERSIBLE = {",
            '_REVERSIBLE = {\n    "phase0_mutant_action",',
            "central_action_types",
        ),
    ),
)
def test_central_vocabulary_growth_mutants_fail(
    tmp_path: Path,
    relative_path: str,
    needle: str,
    replacement: str,
    budget: str,
):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    path = tree / relative_path
    text = path.read_text()
    assert needle in text
    path.write_text(text.replace(needle, replacement, 1))

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert budget in {failure["budget"] for failure in report["failures"]}


def test_service_growth_mutant_fails_total_and_enabled_budgets(tmp_path: Path):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    services = tree / "cabinet" / "services.yml"
    services.write_text(
        services.read_text()
        + "\n  - name: phase0-mutant-service\n"
        + "    label: com.cabinet.phase0-mutant\n"
        + "    kind: cron\n"
        + "    command: true\n"
        + "    schedule: {interval_s: 3600}\n"
    )

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    failed = {failure["budget"] for failure in report["failures"]}
    assert {"services_total", "services_enabled"} <= failed


def _shrink_event_types(tree: Path) -> str:
    emitter = tree / "framework/events/emitter.py"
    text = emitter.read_text()
    assert '    "captain_goal_declared",\n' in text
    emitter.write_text(text.replace('    "captain_goal_declared",\n', "", 1))
    return "captain_goal_declared"


def test_legitimate_shrink_stays_green(tmp_path: Path):
    """A real deletion is not punished as growth.

    WIDENED 2026-07-27: the baseline must now DESCRIBE the tree — a name it
    carries that the tree does not is the pre-loaded-inventory red — so a
    legitimate shrink is green once the baseline line goes with the member. The
    property under test is unchanged; the mirror edit is the new cost, and the
    arm below proves the un-mirrored half reds instead of passing quietly.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    dropped = _shrink_event_types(tree)
    baseline_path = tree / "cabinet/config/architecture-baseline-sets.yml"
    baseline = yaml.safe_load(baseline_path.read_text())
    baseline["classes"]["central_event_types"].remove(dropped)
    baseline_path.write_text(yaml.safe_dump(baseline, sort_keys=False))

    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]
    assert report["observed"]["central_event_types"] < report["maximums"]["central_event_types"]


def test_a_shrink_that_leaves_the_baseline_stale_is_red(tmp_path: Path):
    """The other half of the arm above — the mirror edit is REQUIRED, not polite.

    Without this the widened test would only prove that the mirrored shrink is
    green, and a phantom check that silently tolerated the stale line would
    still pass every arm.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    dropped = _shrink_event_types(tree)

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert any(
        failure.get("member") == dropped and "does not carry" in failure["reason"]
        for failure in report["failures"]
    )


def test_later_static_reassignment_is_counted(tmp_path: Path):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    emitter = tree / "framework/events/emitter.py"
    emitter.write_text(
        emitter.read_text()
        + '\nVALID_EVENT_TYPES = VALID_EVENT_TYPES | {"phase0_late_mutant"}\n'
    )

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert "central_event_types" in {failure["budget"] for failure in report["failures"]}


@pytest.mark.parametrize(
    "suffix",
    (
        '\nVALID_EVENT_TYPES |= {"phase0_augmented_mutant"}\n',
        '\nVALID_EVENT_TYPES.add("phase0_call_mutant")\n',
        '\nphase0_alias = VALID_EVENT_TYPES\nphase0_alias.update({"phase0_alias_mutant"})\n',
    ),
)
def test_dynamic_or_mutating_enum_construction_fails_closed(tmp_path: Path, suffix: str):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    emitter = tree / "framework/events/emitter.py"
    emitter.write_text(emitter.read_text() + suffix)

    with pytest.raises(census.ContractError, match="protected enum"):
        census.inspect_repository(tree)


def test_census_check_runs_without_git_metadata(tmp_path: Path):
    tree = _copy_census_tree(tmp_path)
    assert not (tree / ".git").exists()

    proc = subprocess.run(
        [
            sys.executable,
            str(tree / "cabinet" / "scripts" / "cognitive-architecture-census.py"),
            "--root",
            str(tree),
            "--check",
            "--json",
        ],
        text=True,
        capture_output=True,
        cwd=tree,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["ok"] is True


def test_temporary_allowance_requires_owner_reason_sunset_and_deletion_gate(tmp_path: Path):
    census = _load_module()
    import yaml

    contract = tmp_path / "bad-contract.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["temporary_allowances"] = [{"phase": "COG-1"}]
    contract.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError, match="temporary allowance"):
        census.load_contract(contract)

    extra = tmp_path / "extra-contract.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["temporary_allowances"] = [
        {
            "phase": "COG-1",
            "budget": "central_action_types",
            "additional": 1,
            "reason": "bounded shadow pilot",
            "owner": "cognitive-core-program",
            "sunset": "2999-01-01",
            "deletion_gate": "retire pilot",
            "surprise": "forbidden",
        }
    ]
    extra.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(census.ContractError, match="keys must be exactly"):
        census.load_contract(extra)


def _contract_with_allowance(tmp_path: Path, sunset: str) -> Path:
    """A synthetic allowance for the two arithmetic arms below.

    RE-POINTED 2026-07-27 from `central_action_types` to `claude_skills`. Both
    arms test ALLOWANCE ARITHMETIC — one budget's effective maximum moves and
    its siblings do not; an expired row reds even inside the base budget — and
    neither has anything to do with which class was named. The fixture had to
    move because a temporary allowance may no longer name a bijection class at
    all, and a test fixture that names one would be encoding the refused shape
    as valid. `claude_skills` is the closest legal analogue: a small counted set
    pinned at observed==max, so both assertions keep their exact meaning.
    """

    import yaml

    path = tmp_path / f"allowance-{sunset}.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["temporary_allowances"].append(
        {
            "phase": "COG-1",
            "budget": "claude_skills",
            "additional": 2,
            "reason": "bounded shadow pilot",
            "owner": "cognitive-core-program",
            "sunset": sunset,
            "deletion_gate": "COG-1 pilot retired or composed",
        }
    )
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_live_allowance_raises_only_its_named_effective_budget(tmp_path: Path):
    census = _load_module()
    report = census.inspect_repository(
        ROOT,
        _contract_with_allowance(tmp_path, "2999-01-01"),
    )

    assert report["ok"] is True
    assert report["maximums"]["claude_skills"] == 23
    assert report["maximums"]["organ_manifests"] == 5
    assert report["maximums"]["central_event_types"] == 91


def test_expired_allowance_fails_even_when_observed_is_within_base_budget(tmp_path: Path):
    census = _load_module()
    report = census.inspect_repository(
        ROOT,
        _contract_with_allowance(tmp_path, "2000-01-01"),
    )

    assert report["ok"] is False
    assert any(
        failure["budget"] == "claude_skills"
        and failure["reason"] == "expired temporary allowance"
        for failure in report["failures"]
    )


@pytest.mark.parametrize(
    ("relative_path", "budget"),
    (
        (".layer-separation-baseline", "layer_debt_entries"),
        (".layer-separation-allowlist", "layer_allowlist_entries"),
    ),
)
def test_layer_budget_growth_mutants_fail(tmp_path: Path, relative_path: str, budget: str):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    path = tree / relative_path
    path.write_text(path.read_text() + "\nframework/phase0_mutant.py:FRAMEWORK_PATH_INSTANCE\n")

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert budget in {failure["budget"] for failure in report["failures"]}


@pytest.mark.parametrize(
    ("mutation", "budget"),
    (
        ("module", "framework_production_modules"),
        ("line", "framework_production_noncomment_lines"),
        ("compiler", "named_compiler_modules"),
        ("writer", "duplicate_event_writer_sinks"),
    ),
)
def test_structural_compaction_baseline_growth_mutants_fail(
    tmp_path: Path,
    mutation: str,
    budget: str,
):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    if mutation == "module":
        (tree / "framework" / "phase0_growth.py").write_text("VALUE = 1\n")
    elif mutation == "line":
        path = tree / "framework" / "evolution" / "contracts.py"
        path.write_text(path.read_text() + "\nPHASE0_GROWTH = 1\n")
    elif mutation == "compiler":
        (tree / "framework" / "phase0_compiler.py").write_text("VALUE = 1\n")
    else:
        path = tree / "framework" / "events" / "emitter.py"
        text = path.read_text()
        needle = "    _write_to_store(event)\n"
        assert needle in text
        path.write_text(text.replace(needle, needle + "    _write_to_phase0_mutant(event)\n", 1))

    report = census.inspect_repository(tree, as_of=date(2026, 7, 19))

    assert report["ok"] is False
    assert budget in {failure["budget"] for failure in report["failures"]}


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data.pop("ownership"),
        lambda data: data.pop("expansions"),
        lambda data: data.pop("declared_invariants"),
        lambda data: data.pop("enduring_architecture_gates"),
        lambda data: data.update({"unknown_section": {}}),
        lambda data: data["budgets"].pop("services_total"),
        lambda data: data["budgets"].update({"unknown_budget": {"path": "x", "maximum": 0}}),
        lambda data: data.update({"baseline_sha": "not-a-sha"}),
        lambda data: data["budgets"]["services_total"].update({"path": "../escape.yml"}),
    ),
)
def test_contract_is_closed_and_all_claimed_sections_are_required(tmp_path: Path, mutation):
    census = _load_module()
    import yaml

    data = yaml.safe_load(CONTRACT.read_text())
    mutation(data)
    path = tmp_path / "mutant-contract.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError):
        census.load_contract(path)


def test_non_boolean_disabled_flag_fails_closed(tmp_path: Path):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    services = tree / "cabinet/services.yml"
    import yaml

    data = yaml.safe_load(services.read_text())
    row = next(item for item in data["services"] if item.get("disabled") is True)
    row["disabled"] = "true"
    services.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError, match="disabled must be boolean"):
        census.inspect_repository(tree)


# ── SET PINS (expansion-gate adjudication of record, 2026-07-27 — D3) ────────
# The mass budgets rglob framework/ and count *.py only, so cabinet/scripts/**,
# cabinet/config/**, .claude/** and every non-.py file were free — and both
# live expansion escapes landed in exactly those gaps. Each pin below gets a
# GROWTH mutant proving it goes RED and a SHRINK arm proving a legitimate
# removal stays green, because a pin that can only ratchet one way is a pin
# nobody can ever pay down.
#
# EVERY arm derives its target and its SIZE from the tree it is handed, never
# from a path or a count baked in here. That is not neatness: this suite also
# runs INSIDE THE EXPORTED EGG (test_egg_export.py drives
# verify-cognitive-architecture.sh through the export), and the egg deliberately
# ships one skill fewer. A +1 growth mutant is VACUOUS in any tree that starts
# below the ceiling — it passed there while proving nothing — and a shrink arm
# that names a file the export strips dies on FileNotFoundError. Both were
# caught by running this suite in the egg, and both are fixed by asking the
# contract for the live headroom and growing by headroom + 1.


def _grow_organ_manifests(tree: Path, count: int) -> None:
    for index in range(count):
        (tree / f"cabinet/config/organs/phase0-mutant-organ-{index}.yml").write_text(
            f"organ: phase0-mutant-{index}\noperations: []\n"
        )


def _grow_claude_skills(tree: Path, count: int) -> None:
    for index in range(count):
        skill = tree / f".claude/skills/phase0-mutant-skill-{index}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# phase0 mutant skill {index}\n")


def _grow_claude_hook_wirings(tree: Path, count: int) -> None:
    path = tree / ".claude/settings.json"
    data = json.loads(path.read_text())
    event = sorted(data["hooks"])[0]
    for index in range(count):
        data["hooks"][event][0]["hooks"].append(
            {"type": "command", "command": "bash", "args": [f"phase0-mutant-{index}.sh"]}
        )
    path.write_text(json.dumps(data, indent=2))


def _write_mutant_vocabulary(path: Path, count: int) -> None:
    members = ", ".join(f'"phase0_mutant_verdict_{index}"' for index in range(count))
    path.write_text(f"MUTANT_VERDICTS = ({members},)\n")


def _grow_framework_vocabulary(tree: Path, count: int) -> None:
    _write_mutant_vocabulary(tree / "framework/phase0_mutant_vocab.py", count)


def _grow_cabinet_script_vocabulary(tree: Path, count: int) -> None:
    _write_mutant_vocabulary(tree / "cabinet/scripts/phase0_mutant_vocab.py", count)


def _grow_durable_stores(tree: Path, count: int) -> None:
    path = tree / ".gitignore"
    added = "".join(f"\ninstance/phase0-mutant-store-{index}/" for index in range(count))
    path.write_text(path.read_text() + added + "\n")


GROWTH_MUTANTS = (
    (_grow_organ_manifests, "organ_manifests"),
    (_grow_claude_skills, "claude_skills"),
    (_grow_claude_hook_wirings, "claude_hook_wirings"),
    (_grow_framework_vocabulary, "framework_verdict_vocabulary_members"),
    (_grow_cabinet_script_vocabulary, "cabinet_script_verdict_vocabulary_members"),
    (_grow_durable_stores, "durable_store_units"),
)


@pytest.mark.parametrize(("mutate", "budget"), GROWTH_MUTANTS)
def test_set_pin_growth_mutants_fail(tmp_path: Path, mutate, budget: str):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)

    clean = census.inspect_repository(tree)
    assert clean["ok"] is True, clean["failures"]
    over_the_ceiling = clean["maximums"][budget] - clean["observed"][budget] + 1
    assert over_the_ceiling >= 1

    mutate(tree, over_the_ceiling)
    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert budget in {failure["budget"] for failure in report["failures"]}
    assert report["observed"][budget] > clean["maximums"][budget]


@pytest.mark.parametrize(("mutate", "budget"), GROWTH_MUTANTS)
def test_growth_up_to_the_ceiling_is_still_green(tmp_path: Path, mutate, budget: str):
    """The mutant must red because it CROSSED the ceiling, not because it
    touched the file.

    Fills the headroom exactly and requires green. Without this arm, a growth
    mutant passing on a tree that starts below the ceiling would prove nothing —
    which is exactly what happened inside the export before these arms derived
    their size from the contract.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    clean = census.inspect_repository(tree)
    headroom = clean["maximums"][budget] - clean["observed"][budget]
    if headroom == 0:
        pytest.skip(f"{budget} has zero headroom in this tree — nothing to fill")

    mutate(tree, headroom)
    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]
    assert report["observed"][budget] == report["maximums"][budget]


def _unit_of(raw: str) -> str | None:
    line = raw.strip()
    if not line or line.startswith("#") or line.startswith("!"):
        return None
    pattern = line.rstrip("/").lstrip("/")
    parts: list[str] = []
    for segment in pattern.split("/"):
        if any(char in segment for char in "*?["):
            break
        parts.append(segment)
    return "/".join(parts) if parts else pattern


def _shrink_first_vocabulary(census, root: Path) -> None:
    """Collapse the first multi-member vocabulary the PIN ITSELF discovers.

    Located through the census's own discovery rather than a hardcoded
    file:symbol, so the arm survives any tree the suite is handed — including
    an export that strips whichever module a literal would have named.
    """

    import ast
    import re as _re

    pattern = _re.compile("VERDICT")
    for path in census._production_python_files(root):
        found = census.vocabulary_members(path, pattern)
        target = next((name for name, members in found.items() if len(members) > 1), None)
        if target is None:
            continue
        parsed = ast.parse(path.read_text(), filename=str(path))
        for statement in parsed.body:
            if not isinstance(statement, ast.Assign):
                continue
            if target not in [t.id for t in statement.targets if isinstance(t, ast.Name)]:
                continue
            lines = path.read_text().splitlines(keepends=True)
            path.write_text(
                "".join(lines[: statement.lineno - 1])
                + f'{target} = ("phase0_only_member",)\n'
                + "".join(lines[statement.end_lineno :])
            )
            return
    raise AssertionError(f"no multi-member verdict vocabulary under {root}")


def _shrink_organ_manifests(census, tree: Path) -> None:
    census._pattern_set(tree / "cabinet/config/organs", "*.yml")[0].unlink()


def _shrink_claude_skills(census, tree: Path) -> None:
    shutil.rmtree(census._pattern_set(tree / ".claude/skills", "SKILL.md")[0].parent)


def _shrink_claude_hook_wirings(census, tree: Path) -> None:
    path = tree / ".claude/settings.json"
    data = json.loads(path.read_text())
    for event in sorted(data["hooks"]):
        for entry in data["hooks"][event]:
            if entry["hooks"]:
                entry["hooks"].pop()
                path.write_text(json.dumps(data, indent=2))
                return
    raise AssertionError("no wired hook command to remove")


def _shrink_framework_vocabulary(census, tree: Path) -> None:
    _shrink_first_vocabulary(census, tree / "framework")


def _shrink_cabinet_script_vocabulary(census, tree: Path) -> None:
    _shrink_first_vocabulary(census, tree / "cabinet/scripts")


def _shrink_durable_stores(census, tree: Path) -> None:
    """Drop a gitignore line that is the SOLE declarer of its durability unit."""

    path = tree / ".gitignore"
    lines = path.read_text().splitlines(keepends=True)
    counts: dict[str, int] = {}
    for raw in lines:
        unit = _unit_of(raw)
        if unit is not None:
            counts[unit] = counts.get(unit, 0) + 1
    for index, raw in enumerate(lines):
        unit = _unit_of(raw)
        if unit is not None and counts[unit] == 1:
            path.write_text("".join(lines[:index] + lines[index + 1 :]))
            return
    raise AssertionError("no sole-declarer gitignore line to remove")


@pytest.mark.parametrize(
    ("mutate", "budget"),
    (
        (_shrink_organ_manifests, "organ_manifests"),
        (_shrink_claude_skills, "claude_skills"),
        (_shrink_claude_hook_wirings, "claude_hook_wirings"),
        (_shrink_framework_vocabulary, "framework_verdict_vocabulary_members"),
        (_shrink_cabinet_script_vocabulary, "cabinet_script_verdict_vocabulary_members"),
        (_shrink_durable_stores, "durable_store_units"),
    ),
)
def test_set_pin_legitimate_shrink_stays_green(tmp_path: Path, mutate, budget: str):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    before = census.inspect_repository(tree)["observed"][budget]

    mutate(census, tree)
    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]
    assert report["observed"][budget] < before
    assert report["observed"][budget] < report["maximums"][budget]


def test_set_pin_budgets_have_zero_headroom():
    """observed == maximum on every set pin, the law the whole census runs on.

    Stated as its own arm because a pin landed with slack does not bite until
    the slack is used up, and nothing else would notice.

    SOURCE-INSTANCE ONLY, the same scoping the phase twins declare for
    themselves. The exported egg is a DERIVED tree with declared deletions (it
    strips a skill), so it sits legitimately below the ceiling and the law is
    false there BY CONSTRUCTION — asserting it inside the export would be
    asserting that the export is a defect.
    """

    if not (ROOT / ".git").exists():
        pytest.skip("derived tree (no .git) — the zero-headroom law binds the source")

    census = _load_module()
    report = census.inspect_repository(ROOT)

    for budget in (
        "organ_manifests",
        "claude_skills",
        "claude_hook_wirings",
        "framework_verdict_vocabulary_members",
        "cabinet_script_verdict_vocabulary_members",
        "durable_store_units",
    ):
        assert report["observed"][budget] == report["maximums"][budget], budget


@pytest.mark.parametrize(
    "suffix",
    (
        '\nMUTANT_VERDICTS |= {"phase0_augmented"}\n',
        '\nMUTANT_VERDICTS.add("phase0_call")\n',
        "\nMUTANT_VERDICTS = _load_verdicts()\n",
        '\nMUTANT_VERDICTS = frozenset(x for x in ("a", "b"))\n',
        '\nMUTANT_VERDICT_A, MUTANT_VERDICT_B = "a", "b"\n',
        "\ndel MUTANT_VERDICTS\n",
    ),
)
def test_dynamic_or_mutated_satellite_vocabulary_fails_closed(tmp_path: Path, suffix: str):
    """A vocabulary the census cannot read statically is an ERROR, not a zero.

    Otherwise the cheapest way to grow a verdict set for free is to stop
    declaring it as a literal — the same evasion `static_enum` already refuses
    on the central enums.

    Written into a NEW cabinet/scripts module deliberately: appending to a
    framework module would also trip the zero-headroom line budget, and an arm
    two budgets can satisfy proves neither.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    (tree / "cabinet/scripts/phase0_mutant_vocab.py").write_text(
        'MUTANT_VERDICTS = {"seed"}\n' + suffix
    )

    with pytest.raises(census.ContractError):
        census.inspect_repository(tree)


def test_unreadable_vocabulary_elsewhere_is_not_an_error(tmp_path: Path):
    """The fail-closed rule is scoped to the NAMES the pin claims.

    A dynamic module-level constant that is not a verdict vocabulary must not
    take the whole census down — a gate that reds on unrelated code is a gate
    that gets switched off.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    (tree / "cabinet/scripts/phase0_mutant_unrelated.py").write_text(
        "MUTANT_UNRELATED = sorted({'a', 'b'})\n"
    )

    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data.pop("hooks"),
        lambda data: data.update({"hooks": []}),
        lambda data: data["hooks"].update({sorted(data["hooks"])[0]: {}}),
        lambda data: data["hooks"][sorted(data["hooks"])[0]][0].pop("hooks"),
        lambda data: data["hooks"][sorted(data["hooks"])[0]][0]["hooks"][0].pop("command"),
    ),
)
def test_mangled_hook_wiring_is_an_error_not_a_smaller_count(tmp_path: Path, mutation):
    """A pin that reads 0 on a mangled settings file rewards mangling it."""

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    path = tree / ".claude/settings.json"
    data = json.loads(path.read_text())
    mutation(data)
    path.write_text(json.dumps(data, indent=2))

    with pytest.raises(census.ContractError):
        census.inspect_repository(tree)


@pytest.mark.parametrize("relative_path", ("cabinet/config/organs", ".claude/skills"))
def test_missing_set_pin_directory_is_an_error_not_zero(tmp_path: Path, relative_path: str):
    """A contract path that silently reads zero is a DISABLED sensor.

    Removing the whole class is a real decision; it must delete the budget row,
    not quietly satisfy it forever.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    shutil.rmtree(tree / relative_path)

    with pytest.raises(census.ContractError, match="set-pin directory is missing"):
        census.inspect_repository(tree)


@pytest.mark.parametrize("relative_path", ("cabinet/config/organs", ".claude/skills"))
def test_set_pin_path_that_is_not_a_directory_is_an_error(tmp_path: Path, relative_path: str):
    """The ADJACENT degenerate end the missing-directory arm does not reach.

    `Path.rglob` over a regular file yields nothing, so a set-pin path that
    EXISTS but is not a directory read zero and PASSED — the same disabled
    sensor the arm above refuses, one step to the left. Proven by execution
    2026-07-27 before the fix: organ_manifests 0 <= 5, claude_skills 0 <= 21,
    census PASS.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    shutil.rmtree(tree / relative_path)
    (tree / relative_path).write_text("not a directory\n")

    with pytest.raises(census.ContractError, match="is not a directory"):
        census.inspect_repository(tree)


@pytest.mark.parametrize("suffix", (".yaml", ".json", ".yml"))
def test_organ_manifest_counts_every_runtime_spelling(tmp_path: Path, suffix: str):
    """A pin narrower than the runtime it guards is an ESCAPE, not a pin.

    `framework/organs/registry.py` declares MANIFEST_SUFFIXES = (".yml",
    ".yaml", ".json") and `load_organ_manifests` loads every one of them out of
    this directory, so a sixth organ named `.yaml` was a live registry member
    and a derived watchdog floor while the census still read
    `organ_manifests: 5 <= 5` (proven end to end on a committed tree,
    2026-07-27). Every spelling must cross the ceiling.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    clean = census.inspect_repository(tree)
    over = clean["maximums"]["organ_manifests"] - clean["observed"]["organ_manifests"] + 1
    assert over >= 1

    for index in range(over):
        (tree / f"cabinet/config/organs/phase0-spelling-{index}{suffix}").write_text(
            f"organ: phase0-spelling-{index}\noperations: []\n"
        )
    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert "organ_manifests" in {failure["budget"] for failure in report["failures"]}
    assert report["observed"]["organ_manifests"] > clean["maximums"]["organ_manifests"]


def test_organ_manifest_spellings_track_the_runtime_loader():
    """The contract's spelling list is DATA — bind it to its one declarer.

    Left unbound, the loader could gain a fourth spelling and the pin would
    silently stop covering the class while every other arm stayed green.
    """

    import re as _re

    census = _load_module()
    contract = census.load_contract(CONTRACT)
    declared = set(contract["budgets"]["organ_manifests"]["pattern"])

    source = (ROOT / "framework/organs/registry.py").read_text()
    match = _re.search(r"MANIFEST_SUFFIXES\s*=\s*\(([^)]*)\)", source)
    assert match is not None, "MANIFEST_SUFFIXES no longer resolvable"
    suffixes = _re.findall(r'"([^"]+)"', match.group(1))
    assert suffixes, "MANIFEST_SUFFIXES parsed empty"

    assert declared == {f"*{suffix}" for suffix in suffixes}


@pytest.mark.parametrize("bad", ([], "", ["*.yml", ""], ["*.yml", 3], 7))
def test_set_pin_pattern_must_be_a_non_empty_spelling_set(tmp_path: Path, bad):
    """An empty or mis-typed spelling list matches nothing and reads zero."""

    census = _load_module()
    import yaml

    data = yaml.safe_load(CONTRACT.read_text())
    data["budgets"]["organ_manifests"]["pattern"] = bad
    path = tmp_path / "bad-pattern.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError):
        census.load_contract(path)


def test_empty_durable_store_registry_is_an_error(tmp_path: Path):
    """The degenerate end: an emptied .gitignore must not certify zero stores."""

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    (tree / ".gitignore").write_text("# every store removed\n")

    with pytest.raises(census.ContractError, match="durable-store units"):
        census.inspect_repository(tree)


def test_durable_store_units_collapse_globs_to_one_store(tmp_path: Path):
    """Two globs under one directory are ONE store, the preflight's own rule.

    Without this the pin would fire on every added glob and be switched off
    inside a week — the failure mode the same gate refused for line mass.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    path = tree / ".gitignore"
    before = census.inspect_repository(tree)["observed"]["durable_store_units"]
    existing = next(
        (line for line in path.read_text().splitlines() if _unit_of(line) is not None),
        None,
    )
    assert existing is not None
    path.write_text(path.read_text() + f"\n{_unit_of(existing)}/*.phase0mutant\n")

    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]
    assert report["observed"]["durable_store_units"] == before


def test_negated_gitignore_rule_is_not_a_store(tmp_path: Path):
    """A negation re-includes a TRACKED file, which survives a fresh worktree."""

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    path = tree / ".gitignore"
    before = census.inspect_repository(tree)["observed"]["durable_store_units"]
    path.write_text(path.read_text() + "\n!instance/phase0-mutant-tracked.yml\n")

    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]
    assert report["observed"]["durable_store_units"] == before


@pytest.mark.parametrize(
    ("budget", "key"),
    (
        ("organ_manifests", "pattern"),
        ("claude_skills", "pattern"),
        ("framework_verdict_vocabulary_members", "symbol_pattern"),
        ("cabinet_script_verdict_vocabulary_members", "symbol_pattern"),
    ),
)
def test_set_pin_budget_requires_its_own_key(tmp_path: Path, budget: str, key: str):
    census = _load_module()
    import yaml

    data = yaml.safe_load(CONTRACT.read_text())
    data["budgets"][budget].pop(key)
    path = tmp_path / f"missing-{budget}.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError):
        census.load_contract(path)


def test_report_is_path_independent_for_explicit_as_of_date(tmp_path: Path):
    census = _load_module()
    first = _copy_census_tree(tmp_path / "first")
    second = tmp_path / "second" / "same-bytes"
    shutil.copytree(first, second)

    first_report = census.inspect_repository(first, as_of=date(2026, 7, 19))
    second_report = census.inspect_repository(second, as_of=date(2026, 7, 19))

    assert first_report == second_report
    assert first_report["as_of"] == "2026-07-19"


# ---------------------------------------------------------------------------
# The EXPANSION REGISTRY — permanent both-ways calibration.
#
# The registry's honest steady state is EMPTY: the baseline is the tree as it
# stood when the registry landed, so there is no live surplus to name. Nothing
# live therefore exercises it, and a registry that has never been seen to reject
# is not a registry. These arms are the calibration anchor — the same idiom the
# adapter conformance suite uses (the reference must pass everything, the
# template must fail everything; a suite that cannot tell them apart tests
# nothing). A synthetic member that is NOT registered must go RED, and the SAME
# tree with the SAME member registered must go GREEN.
#
# Every arm below lifts the COUNT ceiling by exactly one first, so the only
# thing that can red these trees is the registry — never the zero-headroom
# ratchet standing in for a check that is not actually running.
# ---------------------------------------------------------------------------

SYNTHETIC_MEMBER = "census_fixture_unadjudicated_event"
SYNTHETIC_CLASS = "central_event_types"
BASELINE_MEMBER = "captain_goal_declared"


def _plant_synthetic_member(tree: Path) -> None:
    emitter = tree / "framework/events/emitter.py"
    text = emitter.read_text()
    needle = "VALID_EVENT_TYPES = frozenset({"
    assert needle in text
    emitter.write_text(text.replace(needle, f'{needle}\n    "{SYNTHETIC_MEMBER}",', 1))


def _expansion_row(**overrides):
    row = {
        "member": SYNTHETIC_MEMBER,
        "member_class": SYNTHETIC_CLASS,
        "gate_date": "2026-07-27",
        "models_run": ["fixture-arm-a", "fixture-arm-b"],
        "adjudication": "docs/plans/cognitive-core-phase-4-contract-2026-07-23.md",
        "merge_refuted": (
            "framework/events/emitter.py::VALID_EVENT_TYPES no shipped event carries "
            "this fixture's meaning"
        ),
        "consumer": "framework/watchdog/registry.py",
        "provenance": "permanent calibration fixture for the expansion registry",
    }
    row.update(overrides)
    return row


def _rewrite_contract(tree: Path, expansions, *, lift_ceilings: bool = True) -> None:
    """Rewrite the copied tree's contract, lifting the two COUNT ceilings the
    planted member consumes (one event type, one non-comment line) by exactly
    one each. Both must move: the point of these arms is that the ONLY thing
    which can red the tree is the registry, never a zero-headroom ratchet
    standing in for a check that is not actually running."""

    path = tree / "cabinet/config/cognitive-architecture-contract.yml"
    data = yaml.safe_load(path.read_text())
    # APPEND, never replace (2026-07-27). The copied tree carries the real
    # framework/, so every LIVE expansion member is present in it; dropping the
    # live rows would make each of those members an unregistered surplus and
    # every arm below would fail for a reason it does not name. Each arm still
    # measures exactly its own synthetic row.
    data["expansions"] = list(data.get("expansions") or []) + list(expansions)
    if lift_ceilings:
        data["budgets"]["central_event_types"]["maximum"] += 1
        data["budgets"]["framework_production_noncomment_lines"]["maximum"] += 1
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _tree_with_synthetic_member(tmp_path: Path, expansions) -> Path:
    tree = _copy_census_tree(tmp_path)
    _plant_synthetic_member(tree)
    _rewrite_contract(tree, expansions)
    return tree


def test_unregistered_set_member_is_red(tmp_path: Path):
    """NEGATIVE control: net-new member, count ceiling lifted, no row -> RED."""

    census = _load_module()
    tree = _tree_with_synthetic_member(tmp_path, [])

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert report["observed"]["central_event_types"] <= report["maximums"]["central_event_types"]
    assert {
        (failure["budget"], failure["member"], failure["reason"])
        for failure in report["failures"]
    } == {(SYNTHETIC_CLASS, SYNTHETIC_MEMBER, "unregistered set member")}


def test_registered_set_member_is_green(tmp_path: Path):
    """POSITIVE control: the same tree, the same member, one adjudicated row."""

    census = _load_module()
    tree = _tree_with_synthetic_member(tmp_path, [_expansion_row()])

    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]
    assert report["surplus_members"][SYNTHETIC_CLASS] == [SYNTHETIC_MEMBER]


def test_expansion_row_naming_an_absent_member_is_red(tmp_path: Path):
    """The stale copy-paste: a row survives the member it was written for."""

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    _rewrite_contract(tree, [_expansion_row()], lift_ceilings=False)

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert any(
        failure.get("member") == SYNTHETIC_MEMBER
        and failure["reason"] == "expansion row names a member that is not present"
        for failure in report["failures"]
    )


def test_expansion_row_naming_a_baseline_member_is_red(tmp_path: Path):
    """The laundering edit: pay for a member the baseline already covers."""

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    _rewrite_contract(
        tree, [_expansion_row(member=BASELINE_MEMBER)], lift_ceilings=False
    )

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert any(
        failure.get("member") == BASELINE_MEMBER
        and failure["reason"] == "expansion row names a baseline member"
        for failure in report["failures"]
    )


def test_two_rows_for_one_member_are_refused(tmp_path: Path):
    census = _load_module()
    path = tmp_path / "duplicate-rows.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["expansions"] = [_expansion_row(), _expansion_row(gate_date="2026-07-28")]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError, match="duplicate expansion row"):
        census.load_contract(path)


@pytest.mark.parametrize("dropped", sorted(_expansion_row()))
def test_expansion_schema_refuses_every_missing_field(tmp_path: Path, dropped: str):
    """Under-specification fails — one arm per field, so no field can be quietly
    dropped from the forcing question later."""

    census = _load_module()
    row = _expansion_row()
    row.pop(dropped)
    path = tmp_path / f"missing-{dropped}.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["expansions"] = [row]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError, match="expansion keys must be exactly"):
        census.load_contract(path)


def test_expansion_schema_refuses_an_extra_field(tmp_path: Path):
    """Over-specification fails too — the closed-key law runs both directions."""

    census = _load_module()
    path = tmp_path / "extra-field.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["expansions"] = [_expansion_row(surprise="forbidden")]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError, match="expansion keys must be exactly"):
        census.load_contract(path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"member": "   "}, "expansion requires non-empty member"),
        ({"provenance": ""}, "expansion requires non-empty provenance"),
        ({"member_class": "framework_production_noncomment_lines"}, "member_class must be one of"),
        ({"member_class": "not_a_class"}, "member_class must be one of"),
        ({"gate_date": "27-07-2026"}, "gate_date must be YYYY-MM-DD"),
        ({"models_run": ["only-one-arm"]}, "at least two independently-run arms"),
        ({"models_run": "two, honest"}, "at least two independently-run arms"),
        ({"models_run": ["same-arm", " Same-Arm "]}, "arms must be distinct"),
        ({"models_run": ["ok-arm", ""]}, "entries must be non-empty strings"),
        ({"adjudication": "/etc/passwd.md"}, "must be a relative, confined"),
        ({"adjudication": "../outside/gate.md"}, "must be a relative, confined"),
        ({"adjudication": "docs/plans/gate.txt"}, "must name the written adjudication"),
        (
            {"merge_refuted": "nothing existing does this, I checked"},
            "must OPEN with a <path>::<symbol> anchor",
        ),
        (
            {"merge_refuted": "framework/events/emitter.py no symbol here"},
            "must OPEN with a <path>::<symbol> anchor",
        ),
        (
            {"merge_refuted": "framework/events/emitter.py::ab too short a symbol"},
            "must OPEN with a <path>::<symbol> anchor",
        ),
        ({"consumer": "/absolute/consumer.py"}, "must be a relative, confined"),
    ),
)
def test_expansion_field_shapes_are_refused_at_load(tmp_path: Path, overrides, message):
    census = _load_module()
    path = tmp_path / "bad-shape.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["expansions"] = [_expansion_row(**overrides)]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError, match=message):
        census.load_contract(path)


@pytest.mark.parametrize(
    ("overrides", "reason_fragment"),
    (
        (
            {"merge_refuted": "framework/no_such_module.py::SOME_SYMBOL prose"},
            "merge_refuted names a path that is absent",
        ),
        (
            {"merge_refuted": "framework/events/emitter.py::NOT_A_REAL_SYMBOL_HERE prose"},
            "merge_refuted symbol is absent from the file it names",
        ),
        ({"consumer": "framework/no_such_consumer.py"}, "consumer resolves to neither"),
        ({"consumer": SYNTHETIC_MEMBER}, "consumer must READ the output"),
        ({"consumer": "framework/events/emitter.py"}, "consumer must READ the output"),
    ),
)
def test_expansion_bindings_must_resolve_against_the_tree(
    tmp_path: Path, overrides, reason_fragment: str
):
    """merge_refuted is answered by grep or not at all, and a consumer that is
    the member or its own declaring file is not a consumer."""

    census = _load_module()
    tree = _tree_with_synthetic_member(tmp_path, [_expansion_row(**overrides)])

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert any(
        reason_fragment in failure["reason"] for failure in report["failures"]
    ), report["failures"]


def test_a_declared_service_name_is_an_acceptable_consumer(tmp_path: Path):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    _plant_synthetic_member(tree)
    services = yaml.safe_load((tree / "cabinet/services.yml").read_text())["services"]
    _rewrite_contract(tree, [_expansion_row(consumer=services[0]["name"])])

    report = census.inspect_repository(tree)

    assert report["ok"] is True, report["failures"]


def test_bijection_classes_are_pinned(tmp_path: Path):
    """A silent narrowing of the covered classes would disable the registry for a
    whole class while every other arm stayed green."""

    census = _load_module()

    assert census.BIJECTION_CLASSES == frozenset(
        {
            "central_event_types",
            "central_action_types",
            "services_total",
            "services_enabled",
            "framework_production_modules",
            "duplicate_event_writer_sinks",
        }
    )
    assert set(yaml.safe_load(BASELINE_SETS.read_text())["classes"]) == set(
        census.BIJECTION_CLASSES
    )


def test_live_registry_matches_the_live_surplus_exactly():
    """INVERTED 2026-07-27: the registry stopped being empty.

    The previous assertion — no surplus at all — was the honest state while the
    registry held nothing, and it became literally wrong when the first
    adjudicated expansion landed. Asserting the BIJECTION instead is strictly
    stronger: an unregistered member still fails, and so does a row that outlives
    the member it was written for, which the "empty" form could never catch.
    """

    census = _load_module()
    report = census.inspect_repository(ROOT)
    contract = census.load_contract(ROOT / "cabinet/config/cognitive-architecture-contract.yml")

    assert set(report["surplus_members"]) == set(census.BIJECTION_CLASSES)
    registered: dict[str, set[str]] = {name: set() for name in census.BIJECTION_CLASSES}
    for row in contract["expansions"]:
        registered[row["member_class"]].add(row["member"])
    assert {
        name: set(members) for name, members in report["surplus_members"].items()
    } == registered
    assert report["ok"] is True, report["failures"]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data.pop("classes"),
        lambda data: data.pop("snapshot_of"),
        lambda data: data.update({"unexpected": 1}),
        lambda data: data.update({"schema_version": "architecture-baseline-sets/v0"}),
        lambda data: data.update({"snapshot_of": "not-a-sha"}),
        lambda data: data["classes"].pop("services_total"),
        lambda data: data["classes"].update({"invented_class": ["x"]}),
        lambda data: data["classes"].update({"central_event_types": []}),
        lambda data: data["classes"].update({"central_event_types": ["dup", "dup"]}),
        lambda data: data["classes"].update({"central_event_types": ["ok", "  "]}),
    ),
)
def test_baseline_sets_are_closed_and_fail_shut(tmp_path: Path, mutation):
    census = _load_module()
    data = yaml.safe_load(BASELINE_SETS.read_text())
    mutation(data)
    path = tmp_path / "mutant-baseline.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError):
        census.load_baseline_sets(path)


def test_duplicate_service_names_fail_closed(tmp_path: Path):
    """Two rows under one name would shrink the member set below the row count
    and hide a service from the registry while the count budget still read it."""

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    services = tree / "cabinet/services.yml"
    data = yaml.safe_load(services.read_text())
    data["services"][1]["name"] = data["services"][0]["name"]
    services.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(census.ContractError, match="duplicate service names"):
        census.inspect_repository(tree)


# ── The allowance bypass, closed 2026-07-27 ──────────────────────────────────
# An adversarial review proved BY EXECUTION that four shipped files asserted
# something false: "an allowance CANNOT buy a net-new set member". It landed a
# genuinely net-new production module at ok=True with `expansions` naming
# nothing new, paying for it with ONE line in architecture-baseline-sets.yml
# plus an ordinary temporary_allowances row. Membership and count are two
# separate costs and the claim named only the count.
#
# Every arm below was run against the PRE-CHANGE census first and observed to
# PASS there — a bypass arm that never fails on the broken code is a fixture
# asserting the bypass, not a test of the fix.

BYPASS_PROBE_MODULE = "framework/phase0_bypass_probe.py"


def _allowance_row(phase: str, budget: str, additional: int) -> dict:
    return {
        "phase": phase,
        "budget": budget,
        "additional": additional,
        "reason": "arm for the bijection-allowance refusal",
        "owner": "orchestrator",
        "sunset": "2027-01-19",
        "deletion_gate": "the arm is deleted with the refusal it proves",
    }


def _write_contract(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "mutant-contract.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def _live_bijection_rows(data: dict, census) -> list[dict]:
    return [
        row
        for row in data["temporary_allowances"]
        if row["budget"] in census.BIJECTION_CLASSES
    ]


def test_legacy_bijection_allowances_are_pinned_verbatim():
    """The carve-out is CLOSED — a twelfth entry is the instrument being closed.

    Pinned as (phase, budget, additional) triples rather than phase names: a
    permit keyed on the name alone leaves the row editable, and bumping COG-3
    from 12 to 13 would buy a module for one character.
    """

    census = _load_module()

    assert census.LEGACY_BIJECTION_ALLOWANCES == frozenset(
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
    assert all(
        budget in census.BIJECTION_CLASSES
        for _, budget, _ in census.LEGACY_BIJECTION_ALLOWANCES
    )


def test_the_live_bijection_class_allowances_are_still_accepted():
    """A fix that reds master for already-reviewed work is not a fix.

    Also holds the carve-out to SHRINK-ONLY in both directions: the pin must
    equal the live rows exactly, so deleting a row without deleting its permit
    would leave a re-usable permit behind, and adding a row without amending
    the permit is refused at load.
    """

    census = _load_module()
    contract = census.load_contract(CONTRACT, as_of=date(2026, 7, 27))
    live = [
        (row["phase"], row["budget"], row["additional"])
        for row in contract["temporary_allowances"]
        if row["budget"] in census.BIJECTION_CLASSES
    ]

    assert len(live) == 11
    assert len(set(live)) == len(live)
    assert set(live) == set(census.LEGACY_BIJECTION_ALLOWANCES)


@pytest.mark.parametrize(
    "budget",
    sorted(
        {
            "central_event_types",
            "central_action_types",
            "services_total",
            "services_enabled",
            "framework_production_modules",
            "duplicate_event_writer_sinks",
        }
    ),
)
def test_a_new_allowance_on_a_bijection_class_is_refused_at_load(
    tmp_path: Path, budget: str
):
    census = _load_module()
    data = yaml.safe_load(CONTRACT.read_text())
    data["temporary_allowances"].append(_allowance_row("phase0-new-row", budget, 1))

    with pytest.raises(census.ContractError, match="names the bijection class"):
        census.load_contract(_write_contract(tmp_path, data))


def test_a_grandfathered_row_cannot_be_edited_upward(tmp_path: Path):
    census = _load_module()
    data = yaml.safe_load(CONTRACT.read_text())
    rows = _live_bijection_rows(data, census)
    assert rows, "no live bijection-class allowance to mutate"
    rows[0]["additional"] += 1

    with pytest.raises(census.ContractError, match="names the bijection class"):
        census.load_contract(_write_contract(tmp_path, data))


def test_a_grandfathered_row_cannot_be_copied(tmp_path: Path):
    """The permit is consumed once. A verbatim copy is a second purchase."""

    census = _load_module()
    data = yaml.safe_load(CONTRACT.read_text())
    rows = _live_bijection_rows(data, census)
    assert rows, "no live bijection-class allowance to copy"
    data["temporary_allowances"].append(dict(rows[0]))

    with pytest.raises(census.ContractError, match="duplicates a grandfathered"):
        census.load_contract(_write_contract(tmp_path, data))


def test_an_allowance_on_a_mass_budget_is_still_accepted(tmp_path: Path):
    """The refusal must bite on SETS only.

    Without this arm the refusal could be over-broad — blocking the line-mass
    allowance every landing legitimately writes — and every other arm would
    still be green.
    """

    census = _load_module()
    data = yaml.safe_load(CONTRACT.read_text())
    data["temporary_allowances"].append(
        _allowance_row("phase0-mass-row", "framework_production_noncomment_lines", 5)
    )

    contract = census.load_contract(
        _write_contract(tmp_path, data), as_of=date(2026, 7, 27)
    )

    assert any(
        row["phase"] == "phase0-mass-row" for row in contract["temporary_allowances"]
    )


@pytest.mark.parametrize(
    "member_class",
    sorted(
        {
            "central_event_types",
            "central_action_types",
            "services_total",
            "services_enabled",
            "framework_production_modules",
            "duplicate_event_writer_sinks",
        }
    ),
)
def test_a_baseline_member_the_tree_does_not_carry_is_red(
    tmp_path: Path, member_class: str
):
    """The pre-load half, which the allowance refusal does not reach.

    `observed - baseline` silently ignores a baseline name with no tree member,
    so the inventory could be written in one commit — moving no count and
    reddening nothing — and consumed in a later one, each file arriving already
    excused from the surplus.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    clean = census.inspect_repository(tree)
    assert clean["ok"] is True, clean["failures"]

    path = tree / "cabinet" / "config" / "architecture-baseline-sets.yml"
    data = yaml.safe_load(path.read_text())
    data["classes"][member_class].append("phase0_phantom_preload")
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert {
        (failure["budget"], failure["member"])
        for failure in report["failures"]
        if "does not carry" in failure["reason"]
    } == {(member_class, "phase0_phantom_preload")}


def test_removing_a_baseline_member_is_still_caught_as_surplus(tmp_path: Path):
    """The remedy for a stale baseline line must stay a SAFE edit.

    Deleting a line can only make the surplus larger, which is what makes the
    hard red above affordable. This arm proves the direction: a deleted
    baseline line reds as an unregistered member, never as green.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    path = tree / "cabinet" / "config" / "architecture-baseline-sets.yml"
    data = yaml.safe_load(path.read_text())
    dropped = data["classes"]["central_event_types"].pop()
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    report = census.inspect_repository(tree)

    assert report["ok"] is False
    assert any(
        failure.get("member") == dropped
        and failure["reason"] == "unregistered set member"
        for failure in report["failures"]
    )


def test_the_reproduced_bypass_no_longer_lands(tmp_path: Path):
    """The review's exact reproduction, end to end.

    A genuinely net-new production module, paid for with ONE baseline line and
    an ordinary allowance row, and no new expansion row. On the pre-change
    census this returned ok=True with zero failures.
    """

    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    (tree / BYPASS_PROBE_MODULE).write_text(
        '"""Synthetic net-new production module."""\n\n\ndef probe() -> int:\n    return 1\n'
    )

    baseline_path = tree / "cabinet" / "config" / "architecture-baseline-sets.yml"
    baseline = yaml.safe_load(baseline_path.read_text())
    baseline["classes"]["framework_production_modules"].append(BYPASS_PROBE_MODULE)
    baseline_path.write_text(yaml.safe_dump(baseline, sort_keys=False))

    contract_path = tree / "cabinet" / "config" / "cognitive-architecture-contract.yml"
    contract = yaml.safe_load(contract_path.read_text())
    contract["temporary_allowances"].append(
        _allowance_row("phase0-bypass-probe", "framework_production_modules", 1)
    )
    contract["temporary_allowances"].append(
        _allowance_row(
            "phase0-bypass-probe", "framework_production_noncomment_lines", 5
        )
    )
    contract_path.write_text(yaml.safe_dump(contract, sort_keys=False))
    assert BYPASS_PROBE_MODULE in baseline_path.read_text()
    assert "phase0-bypass-probe" in contract_path.read_text()

    with pytest.raises(census.ContractError, match="names the bijection class"):
        census.inspect_repository(tree)
