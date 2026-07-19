from __future__ import annotations

import importlib.util
from datetime import date
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "cabinet" / "scripts" / "cognitive-architecture-census.py"
CONTRACT = ROOT / "cabinet" / "config" / "cognitive-architecture-contract.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("cognitive_architecture_census", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_census_tree(tmp_path: Path) -> Path:
    dst = tmp_path / "gitless-cabinet"
    shutil.copytree(ROOT / "framework", dst / "framework")
    for rel in (
        "cabinet/config/cognitive-architecture-contract.yml",
        "cabinet/scripts/cognitive-architecture-census.py",
        "cabinet/services.yml",
        ".layer-separation-baseline",
        ".layer-separation-allowlist",
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


def test_legitimate_shrink_stays_green(tmp_path: Path):
    census = _load_module()
    tree = _copy_census_tree(tmp_path)
    emitter = tree / "framework/events/emitter.py"
    text = emitter.read_text()
    assert '    "captain_goal_declared",\n' in text
    emitter.write_text(text.replace('    "captain_goal_declared",\n', "", 1))

    report = census.inspect_repository(tree)

    assert report["ok"] is True
    assert report["observed"]["central_event_types"] < report["maximums"]["central_event_types"]


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
    import yaml

    path = tmp_path / f"allowance-{sunset}.yml"
    data = yaml.safe_load(CONTRACT.read_text())
    data["temporary_allowances"].append(
        {
            "phase": "COG-1",
            "budget": "central_action_types",
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
    assert report["maximums"]["central_action_types"] == 32
    assert report["maximums"]["central_event_types"] == 91


def test_expired_allowance_fails_even_when_observed_is_within_base_budget(tmp_path: Path):
    census = _load_module()
    report = census.inspect_repository(
        ROOT,
        _contract_with_allowance(tmp_path, "2000-01-01"),
    )

    assert report["ok"] is False
    assert any(
        failure["budget"] == "central_action_types"
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


def test_report_is_path_independent_for_explicit_as_of_date(tmp_path: Path):
    census = _load_module()
    first = _copy_census_tree(tmp_path / "first")
    second = tmp_path / "second" / "same-bytes"
    shutil.copytree(first, second)

    first_report = census.inspect_repository(first, as_of=date(2026, 7, 19))
    second_report = census.inspect_repository(second, as_of=date(2026, 7, 19))

    assert first_report == second_report
    assert first_report["as_of"] == "2026-07-19"
