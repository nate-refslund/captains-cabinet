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


def _copy_census_tree(tmp_path: Path) -> Path:
    dst = tmp_path / "gitless-cabinet"
    shutil.copytree(ROOT / "framework", dst / "framework")
    for rel in (
        "cabinet/config/cognitive-architecture-contract.yml",
        "cabinet/config/architecture-baseline-sets.yml",
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
    data["expansions"] = expansions
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


def test_live_registry_carries_no_unregistered_surplus():
    census = _load_module()
    report = census.inspect_repository(ROOT)

    assert set(report["surplus_members"]) == set(census.BIJECTION_CLASSES)
    assert all(not members for members in report["surplus_members"].values()), (
        report["surplus_members"]
    )


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
