"""COG-4 W4 u1 — the ORGANS PACKAGE unit battery (contract §4.4 registry +
§5.2/MF-A1 descriptor; NEW file — the W2 corpus is IMMUTABLE and untouched).

What this file proves, against the LANDED framework/organs package:
  * registry load/hash/epoch (§4.4): structural loads from a REQUIRED
    directory parameter; the registry hash is content-only + order-invariant;
    an organ edit CHANGES it (the honest epoch bump); rebuild reproduces it.
  * the canonical-bytes/digest REPLICA is byte-identical to the C3 kernel's
    (framework/projection/kernel.py (a)) — the standing parity tripwire the
    registry docstring promises (row 6 of the boundary manifest does not
    allowlist framework/organs as a projection importer, so the dialect is
    replicated, exactly the objectives/model.py precedent).
  * descriptor resolution (§5.2): manifest-DECLARED values verbatim
    (organ-level block + per-operation override), refusal on missing or
    mis-shaped members, the ONE-descriptor uniqueness law, and ZERO
    operation-name authority — demonstrated through the W2 corpus's own
    capability-blindness harness over descriptors THIS package resolved.
  * the N-b SUITE-level state_ownership sweep: the registry helper's output
    is line-for-line the W2 corpus reference sweep's (shape parity on
    identical input) and the fixture fleet is disjoint.
  * boundary disciplines, run NOW so the integrator's §13 pin surgery
    (folding the organs modules into test_cog4_scheduler_ast_pin's
    _SCHED_LANDED_MODULES per its RETIREMENT CONDITION) lands green: an AST
    import scan over the organs sources (stdlib | organs-internal | yaml
    ONLY; no subprocess/socket; no projection import; no action-plane
    import) and the subprocess transitive-closure sweep over all three
    modules against the FULL eight-tree reverse-forbidden set of boundary
    row 5.

Fixtures are §4.2-shaped per the amendment PROPOSAL text (the germline pair
is schg-locked, window unopened — CG-33): the genuinely non-software
garden-rota fixture IS the W2 t3 fixture (imported, not transcribed), and
every fixture is pushed through the W2 reference validator + the N-d matrix
consistency check at test time, so fixture drift from the corpus REDs here.

S0: python3.12, no DB, no network, deterministic. Provenance: authored per
the 2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan
continuous grant (COG-4 W4 u1, Fable-for-execution named unit).
"""
from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_cog4_organ_manifest as t3                      # noqa: E402 — the W2
# corpus reference validator/harness (same dir; binding fixtures to it is the
# point — corpus drift REDs here, and nothing in the corpus file is edited).
from framework.organs import descriptor as organ_descriptor  # noqa: E402
from framework.organs import registry as organ_registry      # noqa: E402
from framework.projection import kernel                      # noqa: E402 — test
# files ride the test_cog4_* allowlist glob on the projection row; the organs
# PACKAGE itself may not import the kernel (row 6), which is what the replica
# parity below exists to keep honest.

ORGANS_TREE = _REPO / "framework" / "organs"
ORGANS_MODULES = ("framework.organs", "framework.organs.registry",
                  "framework.organs.descriptor")
# boundary row 5 reverse_forbidden — the FULL eight-tree fenced set (§8.3)
FORBIDDEN_NS = ("framework.frontdoor", "framework.acting",
                "framework.authority", "framework.fidelity",
                "framework.missions", "framework.ovi",
                "framework.learning", "framework.evolution")


# ---------------------------------------------------------------------------
# fixtures — §4.2 shape per the proposal text; garden-rota IS the W2 t3 fixture
# ---------------------------------------------------------------------------

def garden_rota() -> dict:
    return t3._valid_organ_manifest()


def delivery_run() -> dict:
    return {
        "name": "delivery-run",
        "version": "1.0.0",
        "kind": "organ",
        "action_types": ["investigation_run"],
        "risk_classes": ["read_only_dispatch"],
        "undo_contract": "none",
        "entrypoints": {},
        "inputs": ["delivery/drop-offs.yml", "delivery/driver-availability.yml"],
        "outputs": ["delivery/route-plan.json"],
        "domain_operations": ["delivery/route.plan", "delivery/window.confirm"],
        "descriptor": {
            "action_type": "investigation_run",
            "risk_class": "read_only_dispatch",
            "ceiling": [],
            "undo_contract": "none",
            "operations": {
                "delivery/window.confirm": {"undo_contract": "delete_window(1800)"},
            },
        },
        "permissions": ["files/read"],
        "idempotency": {"delivery/route.plan": "route-date",
                        "delivery/window.confirm": "drop-id + window"},
        "state_ownership": ["delivery/route-plan.json"],
        "cost_model": {"units_per_wake": 3},
        "freshness_needs": {"max_staleness_seconds": 86400,
                            "expected_output": "delivery/route-plan.json"},
        "trigger_policy": {"mode": "periodic", "parameters": {"interval_s": 43200}},
        "health_proof": {"probe": "route-plan parses", "expectation": "ok"},
        "fallback": "safe_noop",
        "dependencies": {"organs": [], "capabilities": ["files/read"]},
    }


def care_rota() -> dict:
    return {
        "name": "care-rota",
        "version": "1.0.0",
        "kind": "organ",
        "action_types": ["investigation_run"],
        "risk_classes": ["read_only_dispatch"],
        "undo_contract": "none",
        "entrypoints": {},
        "inputs": ["care/visit-requests.yml", "care/volunteer-hours.yml"],
        "outputs": ["care/visit-rota.json"],
        "domain_operations": ["care-rota/visit.assign", "care-rota/rota.compile"],
        "descriptor": {
            "action_type": "investigation_run",
            "risk_class": "read_only_dispatch",
            "ceiling": [],
            "undo_contract": "delete_window(3600)",
        },
        "permissions": ["files/read"],
        "idempotency": {"care-rota/visit.assign": "visit-id + week",
                        "care-rota/rota.compile": "week-of"},
        "state_ownership": ["care/visit-rota.json"],
        "cost_model": {"units_per_wake": 1},
        "starvation_bound": {"max_wakes": 4, "max_seconds": 604800},
        "freshness_needs": {"max_staleness_seconds": 604800,
                            "expected_output": "care/visit-rota.json"},
        "trigger_policy": {"mode": "event",
                           "parameters": {"trigger": "care/visit-requests.yml"}},
        "health_proof": {"probe": "visit-rota parses", "expectation": "ok"},
        "fallback": "escalate",
        "dependencies": {"organs": ["garden-rota"], "capabilities": ["files/read"]},
    }


FIXTURES = (garden_rota, delivery_run, care_rota)


def _write_fleet(root: Path, manifests: dict[str, dict]) -> Path:
    """Write {filename: manifest} into a fresh dir; .yml/.yaml via
    yaml.safe_dump, .json via json.dumps."""
    root.mkdir(parents=True, exist_ok=True)
    for filename, manifest in manifests.items():
        if filename.endswith(".json"):
            body = json.dumps(manifest, indent=1)
        else:
            body = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
        (root / filename).write_text(body, encoding="utf-8")
    return root


def _std_fleet(tmp_path: Path) -> Path:
    """The standard three-organ fleet across all three manifest spellings,
    plus a non-manifest bystander file (ignored by declaration)."""
    root = _write_fleet(tmp_path / "organs", {
        "garden-rota.yml": garden_rota(),
        "delivery-run.yaml": delivery_run(),
        "care-rota.json": care_rota(),
    })
    (root / "README.md").write_text("not a manifest\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# fixture grounding — bound to the W2 corpus reference (drift REDs here)
# ---------------------------------------------------------------------------
class TestFixtureGrounding:
    def test_garden_rota_is_the_w2_t3_fixture(self):
        assert garden_rota() == t3._valid_organ_manifest()

    @pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.__name__)
    def test_fixture_passes_the_reference_validator(self, fixture):
        assert t3.validate_organ_manifest(fixture()) == []

    @pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.__name__)
    def test_fixture_organ_level_descriptor_is_nd_consistent(self, fixture):
        block = dict(fixture()["descriptor"])
        block.pop("operations", None)
        assert t3.matrix_consistency_errors(block) == []

    def test_fixture_fleet_state_ownership_is_disjoint(self):
        assert t3.state_ownership_collisions(
            [f() for f in FIXTURES]) == []


# ---------------------------------------------------------------------------
# the replica parity tripwire (registry docstring promise, kept mechanical)
# ---------------------------------------------------------------------------
class TestKernelDialectParity:
    _PROBES = (
        {"name": "garden-rota", "note": "Håstrup æøå — non-ASCII stays raw"},
        {"b": [2, 1], "a": {"nested": {"z": None, "y": True}}},
        ["mixed", 3, 3.5, False, None, {"k": "v"}],
        {},
        "bare-string",
        7,
    )

    @pytest.mark.parametrize(
        "probe", _PROBES, ids=[f"probe{i}" for i in range(len(_PROBES))])
    def test_canonical_bytes_and_digest_match_the_kernel(self, probe):
        """The registry's stdlib replica MUST stay byte-identical to
        framework.projection.kernel (a) — one recorder dialect, two spellings,
        this tripwire the binding (the registry may not import the kernel:
        boundary row 6 allowlists cortex/objectives/scheduler + CLIs only)."""
        assert organ_registry.canonical_bytes(probe) == kernel.canonical_bytes(probe)
        assert organ_registry.digest(probe) == kernel.digest(probe)

    def test_registry_hash_recomputes_through_the_kernel(self, tmp_path):
        """Independent recomputation: the shipped registry_hash equals the
        kernel-dialect digest over the canonical-bytes-sorted manifest list —
        no private algebra hides in the registry."""
        record = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        expected = kernel.digest(
            sorted(record["manifests"], key=kernel.canonical_bytes))
        assert record["registry_hash"] == expected


# ---------------------------------------------------------------------------
# registry load / hash / epoch (§4.4)
# ---------------------------------------------------------------------------
class TestRegistryLoad:
    def test_loads_all_three_spellings_and_ignores_bystanders(self, tmp_path):
        record = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        assert record["schema_version"] == organ_registry.REGISTRY_SCHEMA_VERSION
        assert record["count"] == 3
        assert record["organs"] == ["care-rota", "delivery-run", "garden-rota"]
        # canonical-bytes total order, content-determined
        assert record["manifests"] == sorted(
            record["manifests"], key=organ_registry.canonical_bytes)
        # loaded content round-trips the fixtures exactly (yaml/json faithful)
        by_name = {m["name"]: m for m in record["manifests"]}
        for fixture in FIXTURES:
            man = fixture()
            assert by_name[man["name"]] == man

    def test_hash_is_content_only_and_order_invariant(self, tmp_path):
        a = organ_registry.load_organ_registry(_std_fleet(tmp_path / "a"))
        # same content, different filenames + different spellings per organ
        b_root = _write_fleet(tmp_path / "b" / "organs", {
            "zz-care.yml": care_rota(),
            "am-garden.json": garden_rota(),
            "mm-delivery.yml": delivery_run(),
        })
        b = organ_registry.load_organ_registry(b_root)
        assert a["registry_hash"] == b["registry_hash"]
        assert a["manifests"] == b["manifests"]

    def test_rebuild_reproduces_the_hash(self, tmp_path):
        first = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        again = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        assert first["registry_hash"] == again["registry_hash"]

    def test_an_organ_edit_is_an_honest_epoch_bump(self, tmp_path):
        """§4.4: ANY manifest edit changes the registry hash — never silent
        drift under an unchanged hash."""
        before = organ_registry.load_organ_registry(_std_fleet(tmp_path / "x"))
        edited = garden_rota()
        edited["cost_model"]["units_per_wake"] = 3          # 2 -> 3
        after = organ_registry.load_organ_registry(_write_fleet(
            tmp_path / "y" / "organs", {
                "garden-rota.yml": edited,
                "delivery-run.yaml": delivery_run(),
                "care-rota.json": care_rota(),
            }))
        assert before["registry_hash"] != after["registry_hash"]

    def test_missing_directory_refuses(self, tmp_path):
        with pytest.raises(organ_registry.OrganRegistryError,
                           match="not a directory"):
            organ_registry.load_organ_manifests(tmp_path / "absent")

    def test_unparseable_manifest_refuses_loudly(self, tmp_path):
        root = _std_fleet(tmp_path)
        (root / "broken.yml").write_text("kind: [unclosed\n", encoding="utf-8")
        with pytest.raises(organ_registry.OrganRegistryError,
                           match="broken.yml.*unparseable"):
            organ_registry.load_organ_manifests(root)

    def test_non_mapping_manifest_refuses(self, tmp_path):
        root = _std_fleet(tmp_path)
        (root / "list.json").write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(organ_registry.OrganRegistryError,
                           match="list.json.*not a mapping"):
            organ_registry.load_organ_manifests(root)

    def test_non_organ_kind_refuses(self, tmp_path):
        root = _std_fleet(tmp_path)
        channel = {"name": "outlook", "version": "1.0.0", "kind": "channel"}
        (root / "outlook.json").write_text(json.dumps(channel), encoding="utf-8")
        with pytest.raises(organ_registry.OrganRegistryError,
                           match="outlook.json.*not 'organ'"):
            organ_registry.load_organ_manifests(root)

    def test_missing_name_refuses(self, tmp_path):
        nameless = garden_rota()
        del nameless["name"]
        root = _write_fleet(tmp_path / "organs", {"x.yml": nameless})
        with pytest.raises(organ_registry.OrganRegistryError,
                           match="no non-empty string 'name'"):
            organ_registry.load_organ_manifests(root)

    def test_duplicate_names_refuse(self, tmp_path):
        root = _write_fleet(tmp_path / "organs", {
            "one.yml": garden_rota(),
            "two.json": garden_rota(),
        })
        with pytest.raises(organ_registry.OrganRegistryError,
                           match="duplicate organ name 'garden-rota'"):
            organ_registry.load_organ_manifests(root)

    def test_errors_never_claim_schema_validation(self, tmp_path):
        """The loader's honesty law: its refusals are STRUCTURAL — the word
        'schema' appears in its errors only to DISCLAIM ownership (the
        extension gate's law, not ours). A §4.2-invalid-but-structurally-
        readable manifest LOADS: validation is not this surface's claim while
        the CG-33 window is unopened."""
        underdeclared = {"name": "bare", "kind": "organ"}   # §4.2-invalid
        root = _write_fleet(tmp_path / "organs", {"bare.yml": underdeclared})
        loaded = organ_registry.load_organ_manifests(root)
        assert loaded == [underdeclared]

    def test_manifest_dir_parameter_has_no_default(self):
        """§4.4 layer law: framework holds NO default path — the directory is
        CLI-injected. Both public loaders take it as a required parameter."""
        for fn in (organ_registry.load_organ_manifests,
                   organ_registry.load_organ_registry):
            (param,) = inspect.signature(fn).parameters.values()
            assert param.default is inspect.Parameter.empty, fn.__name__

    def test_no_instance_literal_in_the_organs_sources(self):
        """§4.4/§7.6 layer law, source-level: no instance/ literal anywhere in
        the package (check-layer-separation.sh is the repo gate; this pins the
        law to the unit)."""
        for path in sorted(ORGANS_TREE.glob("*.py")):
            assert "instance/" not in path.read_text(encoding="utf-8"), path


# ---------------------------------------------------------------------------
# descriptor resolution (§5.2, MF-A1) + the refusal matrix
# ---------------------------------------------------------------------------
class TestDescriptorResolution:
    def test_organ_level_resolution_is_manifest_verbatim(self, tmp_path):
        record = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        d = organ_descriptor.resolve_descriptor(record, "care-rota/rota.compile")
        assert d["schema_version"] == organ_descriptor.DESCRIPTOR_SCHEMA_VERSION
        assert d["capability"] == "care-rota/rota.compile"
        assert d["organ"] == "care-rota"
        assert d["action_type"] == "investigation_run"
        assert d["risk_class"] == "read_only_dispatch"
        assert d["ceiling"] == []
        assert d["undo_contract"] == "delete_window(3600)"
        assert d["idempotency_key_discipline"] == "week-of"

    def test_per_operation_override_wins_for_its_members_only(self, tmp_path):
        record = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        d = organ_descriptor.resolve_descriptor(record, "garden/water.plots")
        assert d["undo_contract"] == "delete_window(3600)"   # the override
        assert d["risk_class"] == "read_only_dispatch"       # organ-level
        assert d["action_type"] == "investigation_run"       # organ-level
        assert d["idempotency_key_discipline"] == "bed-id + date"

    def test_registry_record_and_raw_manifest_list_resolve_identically(self, tmp_path):
        record = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        via_record = organ_descriptor.resolve_descriptor(
            record, "delivery/window.confirm")
        via_list = organ_descriptor.resolve_descriptor(
            record["manifests"], "delivery/window.confirm")
        assert via_record == via_list
        assert via_record["undo_contract"] == "delete_window(1800)"

    def test_status_vocab_is_the_referenced_seven_not_a_new_enum(self):
        assert organ_descriptor.STATUS_VOCAB == t3.STATUS_ENUM
        d = organ_descriptor.resolve_descriptor([care_rota()],
                                                "care-rota/visit.assign")
        assert d["status_vocab"] == list(t3.STATUS_ENUM)

    def test_resolution_echoes_declared_values_without_deriving(self):
        """MF-A1: the resolver reads DECLARED values — it never consults the
        matrix. A manifest declaring a different closed-set member resolves to
        exactly that member; declared-vs-derived CONSISTENCY (N-d) is the
        schema/AX suite's check, deliberately not re-minted in framework."""
        man = care_rota()
        man["descriptor"]["risk_class"] = "reversible"
        d = organ_descriptor.resolve_descriptor([man], "care-rota/rota.compile")
        assert d["risk_class"] == "reversible"

    def test_unknown_capability_refuses_never_substitutes(self, tmp_path):
        record = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="no organ declares 'garden/uninvented.op'"):
            organ_descriptor.resolve_descriptor(record, "garden/uninvented.op")

    def test_ambiguous_declarers_refuse(self):
        clone = garden_rota()
        clone["name"] = "garden-rota-clone"
        clone["state_ownership"] = ["garden/clone-plan.json"]
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match=r"declared by 2 organs.*garden-rota.*"
                                 r"garden-rota-clone"):
            organ_descriptor.resolve_descriptor(
                [garden_rota(), clone], "garden/rota.compile")

    def test_missing_descriptor_block_refuses(self):
        man = garden_rota()
        del man["descriptor"]
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="descriptor block is structurally absent"):
            organ_descriptor.resolve_descriptor([man], "garden/rota.compile")

    def test_missing_member_after_merge_refuses_by_name(self):
        man = garden_rota()
        del man["descriptor"]["undo_contract"]
        # water.plots still resolves (its override carries undo_contract)...
        d = organ_descriptor.resolve_descriptor([man], "garden/water.plots")
        assert d["undo_contract"] == "delete_window(3600)"
        # ...but rota.compile now lacks the member — refusal NAMES it.
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="undo_contract missing"):
            organ_descriptor.resolve_descriptor([man], "garden/rota.compile")

    def test_mis_shaped_ceiling_refuses(self):
        man = care_rota()
        man["descriptor"]["ceiling"] = "external_comms"      # str, not list
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="ceiling mis-shaped"):
            organ_descriptor.resolve_descriptor([man], "care-rota/rota.compile")

    @pytest.mark.parametrize("mutate, pattern", [
        (lambda m: m["descriptor"].__setitem__("surprise", 1),
         "unknown keys \\['surprise'\\]"),
        (lambda m: m["descriptor"]["operations"]["garden/water.plots"]
         .__setitem__("verdict", "shadow_ok"),
         "unknown keys \\['verdict'\\]"),
    ], ids=["block-unknown-key", "override-unknown-key"])
    def test_unknown_keys_in_consumed_blocks_fail_closed(self, mutate, pattern):
        man = garden_rota()
        mutate(man)
        with pytest.raises(organ_descriptor.DescriptorRefused, match=pattern):
            organ_descriptor.resolve_descriptor([man], "garden/water.plots")

    def test_malformed_domain_operations_anywhere_refuses_resolution(self):
        """Uniqueness cannot be PROVEN over a registry with an unreadable
        declaration — resolution refuses rather than resolving past it."""
        broken = delivery_run()
        broken["domain_operations"] = "banana"
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="'delivery-run'.*structurally unreadable"):
            organ_descriptor.resolve_descriptor(
                [garden_rota(), broken], "garden/rota.compile")

    def test_missing_idempotency_discipline_refuses(self):
        man = care_rota()
        del man["idempotency"]["care-rota/visit.assign"]
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="no idempotency discipline declared for "
                                 "'care-rota/visit.assign'"):
            organ_descriptor.resolve_descriptor([man], "care-rota/visit.assign")

    def test_non_string_capability_refuses(self):
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="non-empty string"):
            organ_descriptor.resolve_descriptor([garden_rota()], "")

    def test_unsupported_registry_shape_refuses(self):
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="unsupported registry shape"):
            organ_descriptor.resolve_descriptor(42, "garden/rota.compile")
        with pytest.raises(organ_descriptor.DescriptorRefused,
                           match="no 'manifests' list"):
            organ_descriptor.resolve_descriptor({}, "garden/rota.compile")


# ---------------------------------------------------------------------------
# §5.2 — operation names carry ZERO authority (the corpus harness, run over
# descriptors THIS package resolved)
# ---------------------------------------------------------------------------
class TestOperationNameCarriesNoAuthority:
    def _notice_board(self) -> dict:
        """A fixture organ declaring TWO operations under ONE organ-level
        block and no overrides — the §5.2 identical-constitutional-tuple
        setup, using the corpus harness's own hard-ceiling favored/unfavored
        pair (garden/water.plots is the name the corpus mutant favors)."""
        return {
            "name": "notice-board",
            "version": "1.0.0",
            "kind": "organ",
            "action_types": ["external_email"],
            "risk_classes": ["external_comms"],
            "undo_contract": "none",
            "entrypoints": {},
            "inputs": ["board/queue.yml"],
            "outputs": ["board/posted.json"],
            "domain_operations": ["garden/water.plots", "warehouse/pick.route"],
            "descriptor": {
                "action_type": "external_email",
                "risk_class": "external_comms",
                "ceiling": ["external_comms"],
                "undo_contract": "none",
            },
            "permissions": ["comms/post"],
            "idempotency": {"garden/water.plots": "bed-id + date",
                            "warehouse/pick.route": "route-id"},
            "state_ownership": ["board/posted.json"],
            "cost_model": {"units_per_wake": 1},
            "freshness_needs": {"max_staleness_seconds": 86400,
                                "expected_output": "board/posted.json"},
            "trigger_policy": {"mode": "on_demand", "parameters": {}},
            "health_proof": {"probe": "posted parses", "expectation": "ok"},
            "fallback": "skip",
            "dependencies": {"organs": [], "capabilities": ["comms/post"]},
        }

    def test_identical_declarations_resolve_to_identical_tuples(self):
        man = self._notice_board()
        assert t3.validate_organ_manifest(man) == []         # §4.2-true fixture
        a = organ_descriptor.resolve_descriptor([man], "garden/water.plots")
        b = organ_descriptor.resolve_descriptor([man], "warehouse/pick.route")
        tuple_a = (a["risk_class"], tuple(a["ceiling"]), a["undo_contract"])
        tuple_b = (b["risk_class"], tuple(b["ceiling"]), b["undo_contract"])
        assert tuple_a == tuple_b
        assert a["capability"] != b["capability"]            # identity differs,
        # authority members do not — the name is observation identity ONLY.

    def test_corpus_blindness_harness_over_resolved_descriptors(self):
        """The W2 §5.2 mutant, re-armed over THIS package's output: a lawful
        verdict predicate is capability-blind across our resolved descriptors;
        the corpus's capability-keyed mutant diverges and is CAUGHT."""
        man = self._notice_board()
        resolved = organ_descriptor.resolve_descriptor([man], "garden/water.plots")
        pairs = [("garden/water.plots", "warehouse/pick.route", {
            "risk_class": resolved["risk_class"],
            "ceiling": list(resolved["ceiling"]),
            "undo_contract": resolved["undo_contract"],
        })]
        assert t3.capability_blindness_violations(
            t3._reference_verdict, pairs) == []
        caught = t3.capability_blindness_violations(
            t3._capability_keyed_mutant, pairs)
        assert caught and "keys on the operation name" in caught[0]

    def test_package_sources_hold_no_capability_keyed_predicate(self):
        """Belt over the law's own text: nothing in the organs sources
        compares a capability/operation name to pick an authority outcome —
        the only capability uses are membership lookup + identity echo. This
        scan pins the absence of a `== "<domain>/<op>"` literal-comparison
        predicate anywhere in the package."""
        for path in sorted(ORGANS_TREE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                for comparator in list(node.comparators) + [node.left]:
                    if (isinstance(comparator, ast.Constant)
                            and isinstance(comparator.value, str)
                            and "/" in comparator.value
                            and comparator.value.count("/") == 1
                            and " " not in comparator.value):
                        pytest.fail(
                            f"{path.name}: comparison against namespaced-id "
                            f"literal {comparator.value!r} — operation names "
                            "carry no authority (§5.2)")


# ---------------------------------------------------------------------------
# N-b — the SUITE-level state_ownership sweep (shape-parity with the corpus)
# ---------------------------------------------------------------------------
class TestStateOwnershipSweep:
    def test_disjoint_fleet_is_clean_and_matches_the_corpus_sweep(self, tmp_path):
        record = organ_registry.load_organ_registry(_std_fleet(tmp_path))
        ours = organ_registry.state_ownership_collisions(record["manifests"])
        corpus = t3.state_ownership_collisions(record["manifests"])
        assert ours == corpus == []

    def test_collision_reds_symmetric_sorted_and_corpus_identical(self):
        grabby = delivery_run()
        grabby["state_ownership"] = ["garden/rota-plan.json"]   # garden's path
        fleet = [garden_rota(), grabby, care_rota()]
        ours = organ_registry.state_ownership_collisions(fleet)
        assert ours == t3.state_ownership_collisions(fleet)      # line-for-line
        assert len(ours) == 1
        assert "garden/rota-plan.json" in ours[0]
        assert "delivery-run" in ours[0] and "garden-rota" in ours[0]
        assert ours == sorted(ours)

    def test_helper_is_structural_about_mis_shaped_ownership(self):
        """A manifest without a list-shaped state_ownership contributes
        nothing (its §4.2 validity is schema/AX law) — the sweep still
        catches collisions among the readable declarations."""
        broken = care_rota()
        broken["state_ownership"] = "care/visit-rota.json"       # not a list
        grabby = delivery_run()
        grabby["state_ownership"] = ["garden/rota-plan.json"]
        out = organ_registry.state_ownership_collisions(
            [garden_rota(), grabby, broken])
        assert len(out) == 1 and "garden/rota-plan.json" in out[0]


# ---------------------------------------------------------------------------
# boundary disciplines — run NOW so the §13 integrator pin surgery lands green
# ---------------------------------------------------------------------------
class TestOrgansBoundaryDisciplines:
    def test_ast_import_law_stdlib_yaml_internal_only(self):
        """Every import in framework/organs is stdlib | organs-internal |
        yaml. In particular: NO framework.projection (row 6 — the replica
        exists precisely because this import is not allowlisted), NO
        action-plane tree (row 5 reverse law), NO subprocess/socket."""
        stdlib = frozenset(sys.stdlib_module_names)
        for path in sorted(ORGANS_TREE.glob("*.py")):
            rel = path.relative_to(_REPO).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:                       # relative = internal
                        continue
                    names = [base]
                else:
                    continue
                for name in names:
                    top = name.split(".", 1)[0]
                    ok = (top in stdlib
                          or name == "yaml"
                          or name == "framework.organs"
                          or name.startswith("framework.organs."))
                    assert ok, f"{rel}: forbidden import {name!r}"
                    assert top not in ("subprocess", "socket"), rel
                    assert not name.startswith("framework.projection"), (
                        f"{rel}: the organs tree is NOT an allowlisted "
                        "projection importer (row 6) — the replica is the law")

    @pytest.mark.parametrize("module", ORGANS_MODULES)
    def test_transitive_closure_reaches_no_fenced_tree(self, module):
        """The exact scan the integrator's retired guard will run once the
        organs modules fold into _SCHED_LANDED_MODULES (test_cog4_scheduler_
        ast_pin RETIREMENT CONDITION) — proven green NOW, over the FULL
        eight-tree reverse-forbidden set of boundary row 5 (a superset of the
        scheduler pin's six)."""
        code = "\n".join([
            "import sys, json",
            f"import {module}",
            f"FZ = {FORBIDDEN_NS!r}",
            "loaded = sorted(m for m in sys.modules "
            "if any(m == f or m.startswith(f + '.') for f in FZ))",
            "print(json.dumps(loaded))",
        ])
        r = subprocess.run([sys.executable, "-c", code], cwd=str(_REPO),
                           capture_output=True, text=True)
        assert r.returncode == 0, (module, r.stderr)
        assert json.loads(r.stdout) == [], (
            f"{module} closure reached a fenced tree: {r.stdout}")

    def test_package_root_is_import_inert(self):
        """`import framework.organs` binds NO submodule (the projection/
        scheduler idiom the package docstring declares) — subprocess-proven so
        this test never depends on this process's import history."""
        code = "\n".join([
            "import sys",
            "import framework.organs",
            "leaked = [m for m in sys.modules "
            "if m.startswith('framework.organs.')]",
            "print(leaked)",
            "assert leaked == [], leaked",
            "assert 'yaml' not in sys.modules, 'root import pulled yaml'",
        ])
        r = subprocess.run([sys.executable, "-c", code], cwd=str(_REPO),
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
