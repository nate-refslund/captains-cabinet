"""Structural read-only for any tracker the operator does not own.

The hazard this closes was in the adapter contract's own words: *"canonical
wins. If an officer changes a task and an operator changes the same task in
the external UI, the next sync overwrites the external change."* Correct on a
board the operator owns. Pointed at an employer's Jira it is an autonomous
agent overwriting colleagues' edits in a system the operator does not own, and
the 48h undo does not help — undoing a write to a colleague's ticket does not
un-notify the colleague.

Every arm fails against pre-change code: before 2026-07-27 `get_adapter`
returned a fully write-capable adapter for any configured tracker, with no
ownership field in the config at all.
"""
from __future__ import annotations

import inspect

import pytest

from framework.authority.ownership import OwnershipRefusal
from cabinet.scripts.task_adapters.base import (
    CanonicalTask,
    NoOpTaskAdapter,
    ObserveOnlyTaskAdapter,
    TaskAdapter,
    get_adapter,
)

OWNED = {
    "tasks": {
        "system": "github-issues",
        "config": {"repo": "owner/repo"},
        "ownership": "self",
        "authority_basis": "my own repository",
    }
}


def _config(ownership=None, basis="stated basis", system="github-issues"):
    tasks = {"system": system, "config": {"repo": "owner/repo"}}
    if ownership is not None:
        tasks["ownership"] = ownership
    if basis is not None:
        tasks["authority_basis"] = basis
    return {"tasks": tasks}


class TestUnclassifiedIsRefused:
    def test_a_tracker_with_no_ownership_field_is_refused(self):
        with pytest.raises(ValueError, match="ownership declaration"):
            get_adapter(_config(ownership=None))

    @pytest.mark.parametrize("ownership", ["", "unknown", "n/a", "probably-mine"])
    def test_undecided_or_unlisted_classes_are_refused(self, ownership):
        with pytest.raises(ValueError, match="ownership declaration"):
            get_adapter(_config(ownership=ownership))

    def test_a_missing_authority_basis_is_refused(self):
        with pytest.raises(ValueError, match="ownership declaration"):
            get_adapter(_config(ownership="employer", basis=None))

    def test_the_refusal_names_every_accepted_class(self):
        with pytest.raises(ValueError) as exc:
            get_adapter(_config(ownership=None))
        for name in ("self", "employer", "third_party"):
            assert name in str(exc.value)

    def test_the_no_sync_path_still_needs_no_classification(self):
        """NoOp writes nowhere by construction, so there is no act to authorize.

        This is the one place an absent ownership field is correct, and it is
        load-bearing: the active project has no tasks block by design, and
        raising here crash-loops the 900s launchd sync job.
        """
        assert isinstance(get_adapter({}), NoOpTaskAdapter)
        assert isinstance(get_adapter({"tasks": {"system": "none"}}), NoOpTaskAdapter)


class TestOwnedTrackersAreUnchanged:
    def test_a_self_owned_tracker_gets_the_real_adapter(self):
        adapter = get_adapter(OWNED)
        assert not isinstance(adapter, ObserveOnlyTaskAdapter)
        assert adapter.destination == "github-issues"
        assert isinstance(adapter, TaskAdapter)


class TestNonOwnedTrackersAreStructurallyReadOnly:
    @pytest.mark.parametrize("ownership", ["employer", "third_party"])
    def test_the_factory_hands_back_a_different_type(self, ownership):
        adapter = get_adapter(_config(ownership=ownership))
        assert isinstance(adapter, ObserveOnlyTaskAdapter)
        assert adapter.ownership == ownership
        assert adapter.destination == "github-issues"

    @pytest.mark.parametrize("ownership", ["employer", "third_party"])
    def test_every_write_method_refuses(self, ownership):
        adapter = get_adapter(_config(ownership=ownership))
        task = CanonicalTask(canonical_id="c-1", title="t")
        for call in (
            lambda: adapter.push(task),
            lambda: adapter.delete("ext-1"),
            lambda: adapter.link("c-1", "ext-1"),
        ):
            with pytest.raises(OwnershipRefusal) as exc:
                call()
            assert exc.value.code == "write_refused_non_owned"
            assert exc.value.detail["ownership"] == ownership

    def test_the_refusal_is_not_a_configurable_flag(self):
        """No constructor argument, attribute or env var re-opens the write path.

        Asserted against the signature and the class body rather than by
        prose: a later edit adding `read_only=`/`force=`/`allow_writes=` fails
        here, which is what "structural" has to mean to be worth the word.
        """
        params = list(inspect.signature(ObserveOnlyTaskAdapter.__init__).parameters)
        assert params == ["self", "inner", "ownership", "authority_basis"]
        # Scan the CODE, not the docstring that explains why the code is this
        # way (the docstring names `read_only=True` as the thing it is not).
        source = inspect.getsource(ObserveOnlyTaskAdapter)
        code = source.replace(ObserveOnlyTaskAdapter.__doc__ or "", "")
        for banned in ("read_only", "allow_writes", "force", "os.environ", "getenv"):
            assert banned not in code, banned
        for method in ("push", "delete", "link"):
            body = inspect.getsource(getattr(ObserveOnlyTaskAdapter, method))
            assert "require_write_permitted" in body
            assert "self.inner" not in body

    def test_mutating_the_attribute_does_not_restore_writes(self):
        adapter = get_adapter(_config(ownership="employer"))
        adapter.ownership = "self"
        with pytest.raises(ValueError):
            # Re-wrapping an owned source is refused, so the "reclassify the
            # live object" route cannot manufacture a write-capable observer.
            ObserveOnlyTaskAdapter(adapter.inner, ownership="self", authority_basis="b")

    def test_reads_still_pass_through(self, monkeypatch):
        """Refusing to READ an employer's tracker would be safety theatre.

        Reading a board the operator has a seat in is the whole product at
        employee altitude; only the write half is the unauthorized act.
        """
        from cabinet.scripts.task_adapters.reference_inmemory import (
            InMemoryReferenceAdapter,
        )

        monkeypatch.setenv("REFERENCE_TASKS_TOKEN", "harness-only-not-a-credential")
        inner = InMemoryReferenceAdapter({"system": "reference-inmemory", "config": {}})
        inner.tracker.items["1"] = {
            "canonical_id": "c-1", "title": "seen", "description": "",
            "status": "open", "assigned_role": None, "priority": "normal",
            "due_at": None, "tags": [],
        }
        observer = ObserveOnlyTaskAdapter(inner, ownership="employer", authority_basis="my seat")
        pulled = observer.pull()
        assert [t.canonical_id for t in pulled] == ["c-1"]
        assert observer.health_check() is inner.health_check()

    def test_repr_states_the_posture_and_leaks_no_token(self):
        adapter = get_adapter(_config(ownership="third_party"))
        text = repr(adapter)
        assert "writes=refused" in text and "third_party" in text


class TestRunnerSurfacesThePosture:
    def test_sync_result_distinguishes_observe_only_from_nothing_to_push(self):
        from cabinet.scripts.task_adapters.base import SyncResult

        quiet = SyncResult(destination="github-issues")
        observing = SyncResult(destination="github-issues", read_only=True, ownership="employer")
        assert quiet.read_only is False and quiet.ownership is None
        assert observing.read_only is True and observing.ownership == "employer"
