"""Tests for role lifecycle management."""

import os
import sys
from pathlib import Path

import pytest
from yaml import safe_load as _yaml_load

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.roles.lifecycle import (
    create_role, load_role, list_roles, adapt_role,
    assign_hat, get_active_hats, retire_role,
    get_effective_capabilities, get_lineage,
)
from framework.events.emitter import replay


@pytest.fixture(autouse=True)
def clean_env(tmp_path):
    """Point everything at temp directories."""
    os.environ["CABINET_ROOT"] = str(tmp_path)
    os.environ["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "events")
    os.environ.pop("DATABASE_URL", None)
    (tmp_path / "instance" / "roles" / "active").mkdir(parents=True)
    yield tmp_path


class TestCreateRole:
    def test_basic_creation(self):
        role = create_role("eng", "Engineering", "Build and ship product code")
        assert role["slug"] == "eng"
        assert role["title"] == "Engineering"
        assert role["status"] == "active"
        assert role["charter"] == "Build and ship product code"

    def test_creates_yaml_file(self, clean_env):
        create_role("eng", "Engineering", "Build things")
        f = clean_env / "instance" / "roles" / "active" / "eng.yml"
        assert f.exists()
        data = _yaml_load(f.read_text())
        assert data["slug"] == "eng"

    def test_emits_event(self):
        create_role("eng", "Engineering", "Build things")
        events = replay(event_types=["role_created"])
        assert len(events) == 1
        assert events[0]["payload"]["slug"] == "eng"

    def test_records_lineage(self):
        create_role("eng", "Engineering", "Build things")
        lineage = get_lineage("eng")
        assert len(lineage) == 1
        assert lineage[0]["adaptation_type"] == "created"

    def test_with_capabilities(self):
        role = create_role("eng", "Engineering", "Build", capabilities=["deploys_code", "reviews_code"])
        assert "deploys_code" in role["capabilities"]

    def test_with_authority_level(self):
        role = create_role("cos", "Chief of Staff", "Coordinate", authority_level="elevated")
        assert role["authority_level"] == "elevated"


class TestLoadRole:
    def test_load_existing(self):
        create_role("eng", "Engineering", "Build")
        role = load_role("eng")
        assert role is not None
        assert role["slug"] == "eng"

    def test_load_nonexistent(self):
        assert load_role("nonexistent") is None


class TestAdaptRole:
    def test_charter_change(self):
        create_role("eng", "Engineering", "Build things")
        updated = adapt_role("eng", "charter_change", "Expanded charter",
                             changes={"charter": "Build and maintain product code"})
        assert updated["charter"] == "Build and maintain product code"

    def test_add_capability(self):
        create_role("eng", "Engineering", "Build", capabilities=["deploys_code"])
        updated = adapt_role("eng", "capability_added", "Added review cap",
                             changes={"capability": "reviews_specs"})
        assert "reviews_specs" in updated["capabilities"]
        assert "deploys_code" in updated["capabilities"]

    def test_remove_capability(self):
        create_role("eng", "Engineering", "Build", capabilities=["a", "b"])
        updated = adapt_role("eng", "capability_removed", "Removed b",
                             changes={"capability": "b"})
        assert "b" not in updated["capabilities"]
        assert "a" in updated["capabilities"]

    def test_adaptation_records_lineage(self):
        create_role("eng", "Engineering", "Build")
        adapt_role("eng", "charter_change", "Expanded",
                   changes={"charter": "New charter"},
                   evidence="3 tasks required new scope",
                   rationale="Formalizing existing work")
        lineage = get_lineage("eng")
        assert len(lineage) == 2  # created + charter_change
        assert lineage[1]["evidence"] == "3 tasks required new scope"

    def test_adapt_nonexistent_raises(self):
        with pytest.raises(ValueError, match="Role not found"):
            adapt_role("nope", "charter_change", "x", changes={})


class TestHats:
    def test_assign_hat(self):
        create_role("product", "Product", "Define what to build")
        hat = assign_hat("product", "Activation Strategist",
                         "Focus on user activation funnel",
                         capabilities=["analyze_funnels"])
        assert hat["name"] == "Activation Strategist"

    def test_get_active_hats(self):
        create_role("product", "Product", "Define")
        assign_hat("product", "Strategist", "Focus on strategy")
        assign_hat("product", "Researcher", "Focus on research")
        hats = get_active_hats("product")
        assert len(hats) == 2

    def test_hat_with_mission(self):
        create_role("eng", "Engineering", "Build")
        hat = assign_hat("eng", "Onboarding Engineer", "Build onboarding",
                         mission_id="mission-123")
        assert hat["mission_id"] == "mission-123"

    def test_effective_capabilities_includes_hats(self):
        create_role("eng", "Engineering", "Build", capabilities=["deploys_code"])
        assign_hat("eng", "Analyst", "Analyze things", capabilities=["analyze_data"])
        caps = get_effective_capabilities("eng")
        assert "deploys_code" in caps
        assert "analyze_data" in caps


class TestRetireRole:
    def test_retire_moves_to_archive(self, clean_env):
        create_role("growth", "Growth", "Grow the product")
        retire_role("growth", "Merged into product role")
        assert not (clean_env / "instance" / "roles" / "active" / "growth.yml").exists()
        assert (clean_env / "instance" / "roles" / "archive" / "growth.yml").exists()

    def test_retired_role_preserves_data(self, clean_env):
        create_role("growth", "Growth", "Grow", capabilities=["seo", "ads"])
        retire_role("growth", "No longer needed")
        archive = _yaml_load(
            (clean_env / "instance" / "roles" / "archive" / "growth.yml").read_text()
        )
        assert archive["capabilities"] == ["seo", "ads"]
        assert archive["status"] == "retired"
        assert archive["retirement_reason"] == "No longer needed"

    def test_retire_emits_event(self):
        create_role("growth", "Growth", "Grow")
        retire_role("growth", "Merged")
        events = replay(event_types=["role_retired"])
        assert len(events) == 1

    def test_retire_records_lineage(self):
        create_role("growth", "Growth", "Grow")
        retire_role("growth", "Merged")
        lineage = get_lineage("growth")
        assert any(e["adaptation_type"] == "retired" for e in lineage)


class TestLineage:
    def test_lineage_is_append_only(self):
        create_role("eng", "Engineering", "Build")
        adapt_role("eng", "charter_change", "v2", changes={"charter": "v2"})
        adapt_role("eng", "capability_added", "added X", changes={"capability": "x"})
        lineage = get_lineage("eng")
        assert len(lineage) == 3  # created + 2 adaptations
        assert lineage[0]["adaptation_type"] == "created"
        assert lineage[1]["adaptation_type"] == "charter_change"
        assert lineage[2]["adaptation_type"] == "capability_added"

    def test_lineage_cross_role(self):
        create_role("eng", "Engineering", "Build")
        create_role("product", "Product", "Define")
        all_lineage = get_lineage()
        assert len(all_lineage) == 2
        eng_lineage = get_lineage("eng")
        assert len(eng_lineage) == 1
