"""No skeleton proposals — phase-1 unit U6 (contract §6, amendment A6.1).

Every sensor here is red on the pre-change tree for the reason its invariant
names, never for an import error:

  * ``test_skeleton_amendment_writes_no_file_and_records_a_gap`` — pre-change
    ``propose_one`` returns a Path and writes the skeleton yml.
  * ``test_three_runs_record_one_gap`` — pre-change three runs write three
    files and emit three ``role_charter_changed`` events, zero gaps.
  * ``test_every_shipped_template_routes_to_a_gap`` — pre-change every one of
    them lands on disk instead.
  * ``test_no_template_derived_amendment_is_auto_applicable`` (A6.1) — the
    ``quality_gap`` template's placeholders were written ``<TODO>`` with no
    colon, so ``_proposal_is_concrete`` accepted a template-derived
    ``add_quality_hat`` amendment as concrete. It is also the arm that goes
    red on the POST-change tree if the ``<TODO:`` markers are ever stripped
    from the templates (the withdrawn rider): stripping them makes
    ``add_hat`` and ``expand_authority`` auto-applicable.

``test_a_concrete_amendment_still_writes`` is a REGRESSION PIN, green in both
directions by design: the write path is not de-armed (Captain 2026-07-26).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.events.emitter import replay
from framework.learning import self_improvement_loop as sil
from framework.learning.capability_gaps import project_gaps
from framework.roles import evolution


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """One ledger and one cabinet root per test, so counts are exact."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    yield


def _slug() -> str:
    return "u6role" + uuid.uuid4().hex[:8]


def _pattern(role_slug: str, failure_type: str = "missing_skill", count: int = 3) -> dict:
    return {
        "role_slug": role_slug,
        "failure_type": failure_type,
        "count": count,
        "eval_names": ["e1", "e2", "e3"],
        "first_seen": "2026-09-01T00:00:00Z",
        "last_seen": "2026-09-05T00:00:00Z",
        "sample_failed_assertions": ["assertion_a", "assertion_b"],
    }


def _gaps_for(role_slug: str, failure_type: str) -> list:
    key = "evolution:{}:{}".format(role_slug, failure_type)
    return [g for g in project_gaps() if g.get("dedup_key") == key]


def _charter_events(proposal_id: str) -> list:
    return [
        e for e in replay(event_types=["role_charter_changed"])
        if (e.get("payload") or {}).get("proposal_id") == proposal_id
    ]


def _proposal_files(root: Path) -> list:
    # Asked of the module under test, never spelled out here: a framework file
    # that names the deployment's own directory layout is a layer coupling.
    return sorted(evolution._proposals_dir(str(root)).glob("*.yml"))


# ---------------------------------------------------------------------------
# §6 — a skeleton becomes a gap, never a file and never an announcement
# ---------------------------------------------------------------------------


def test_skeleton_amendment_writes_no_file_and_records_a_gap(tmp_path):
    slug = _slug()

    result = evolution.propose_one(_pattern(slug), cabinet_root=str(tmp_path))

    assert result is None, "a skeleton proposal must not be written"
    assert _proposal_files(tmp_path) == []
    assert _charter_events(slug + "-missing-skill") == []

    gaps = _gaps_for(slug, "missing_skill")
    assert len(gaps) == 1
    assert gaps[0]["kind"] == "skill"
    assert slug in gaps[0]["need"]
    assert gaps[0]["recorded_by"] == "role_evolution"


def test_three_runs_record_one_gap(tmp_path):
    slug = _slug()
    collected: list = []

    for _ in range(3):
        assert evolution.propose_one(
            _pattern(slug), cabinet_root=str(tmp_path), gaps_out=collected) is None

    assert _proposal_files(tmp_path) == []
    assert _charter_events(slug + "-missing-skill") == []
    assert len(_gaps_for(slug, "missing_skill")) == 1
    assert len(collected) == 3, "every pass reports the gap it observed"
    assert len({g["gap_id"] for g in collected}) == 1
    assert [g["existing_skeleton"] for g in collected] == [False, False, False]
    merged = [
        e for e in replay(event_types=["capability_gap_merged"])
        if (e.get("payload") or {}).get("recorded_by") == "role_evolution"
    ]
    assert merged == [], "a keyed gap is never a merge target"


@pytest.mark.parametrize("failure_type,gap_kind", [
    ("missing_skill", "skill"),
    ("wrong_authority", "authority"),
    ("scope_confusion", "information"),
    ("quality_gap", "skill"),
    ("runtime_error", "information"),
    ("unspecified", "information"),
    ("a_failure_type_no_template_knows", "information"),
])
def test_every_shipped_template_routes_to_a_gap(tmp_path, failure_type, gap_kind):
    slug = _slug()

    assert evolution.propose_one(
        _pattern(slug, failure_type), cabinet_root=str(tmp_path)) is None
    assert _proposal_files(tmp_path) == []

    gaps = _gaps_for(slug, failure_type)
    assert len(gaps) == 1
    assert gaps[0]["kind"] == gap_kind


def test_propose_from_patterns_returns_written_proposals_only(tmp_path, monkeypatch):
    slug = _slug()
    monkeypatch.setattr(
        evolution, "detect_patterns",
        lambda **kw: [_pattern(slug), _pattern(slug, "wrong_authority")],
    )
    collected: list = []

    written = evolution.propose_from_patterns(
        cabinet_root=str(tmp_path), gaps_out=collected)

    assert written == []
    assert _proposal_files(tmp_path) == []
    assert len(collected) == 2
    assert {g["failure_type"] for g in collected} == {"missing_skill", "wrong_authority"}


def test_a_pre_existing_skeleton_file_is_reported_not_rewritten(tmp_path):
    """REGRESSION PIN for the report key: `skipped_skeleton` counts these."""
    slug = _slug()
    proposals = evolution._proposals_dir(str(tmp_path))
    proposals.mkdir(parents=True)
    stale = proposals / (slug + "-missing-skill.yml")
    stale.write_text("proposal_id: stale\n")
    collected: list = []

    assert evolution.propose_one(
        _pattern(slug), cabinet_root=str(tmp_path), gaps_out=collected) is None

    assert stale.read_text() == "proposal_id: stale\n", "the stale file is left alone"
    assert collected[0]["existing_skeleton"] is True


def test_a_concrete_amendment_still_writes(tmp_path, monkeypatch):
    """PIN, green in both directions: the write path is not de-armed."""
    slug = _slug()
    monkeypatch.setitem(evolution._SUGGESTION_TEMPLATES, "u6_concrete", {
        "kind": "add_hat",
        "rationale": "A fully specified adaptation with nothing left to fill in.",
        "hat_template": {
            "name": "concrete-hat",
            "description": "Concrete capability",
            "capabilities": ["concrete_capability"],
            "expires_at": None,
        },
    })

    path = evolution.propose_one(
        _pattern(slug, "u6_concrete"), cabinet_root=str(tmp_path))

    assert path is not None and path.exists()
    assert "concrete-hat" in path.read_text()
    assert len(_charter_events(slug + "-u6-concrete")) == 1
    assert _gaps_for(slug, "u6_concrete") == []


# ---------------------------------------------------------------------------
# A6.1 — no template-derived amendment is auto-applicable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failure_type", sorted(evolution._SUGGESTION_TEMPLATES))
def test_no_template_derived_amendment_is_auto_applicable(tmp_path, failure_type):
    """The markers are the fail-closed default; every template keeps one.

    Red on the post-change tree the moment a `<TODO:` marker is stripped from
    a template: `add_hat` / `expand_authority` carry no other held-back
    signal, so `_proposal_is_concrete` would accept them and auto-apply them.
    """
    amendment = evolution.draft_amendment(
        _pattern(_slug(), failure_type), cabinet_root=str(tmp_path))

    concrete, why = sil._proposal_is_concrete(amendment)

    assert concrete is False, "template-derived {} is auto-applicable: {}".format(
        failure_type, why)


def test_a_template_derived_proposal_on_disk_never_reaches_apply(tmp_path, monkeypatch):
    """PIN, green in both directions: the apply path refuses it even when
    something other than the generator puts the file on disk."""
    import yaml

    slug = _slug()
    amendment = evolution.draft_amendment(
        _pattern(slug), cabinet_root=str(tmp_path))
    proposals = evolution._proposals_dir(str(tmp_path))
    proposals.mkdir(parents=True)
    path = proposals / (amendment["proposal_id"] + ".yml")
    path.write_text(yaml.safe_dump(amendment, sort_keys=False))

    def bomb(*a, **kw):
        raise AssertionError("a template-derived amendment reached _apply_proposal")

    monkeypatch.setattr(sil, "_apply_proposal", bomb)
    monkeypatch.setattr(sil, "propose_from_patterns",
                        lambda **kw: [(path, {"role_slug": slug})])
    monkeypatch.setattr(sil, "propose_graduations", lambda **kw: [])
    monkeypatch.setattr(sil, "induce_drafts", lambda **kw: [])
    monkeypatch.setattr(sil, "_validation_gate",
                        lambda: (True, {"scenario_passed": True, "golden_passed": True}))

    summary = sil.run_loop()

    statuses = [r["status"] for r in summary["proposals"]["detail"]]
    assert statuses == ["pending_captain_approval"]
    assert summary["proposals"]["auto_applied"] == 0
    assert replay(event_types=["role_evolved"]) == []
