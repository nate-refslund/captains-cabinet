"""SOV-8 apply-watch tests — 72h rollback DECISIONS (module executes nothing)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.learning import apply_watch  # noqa: E402

APPLIED = "2026-07-05T00:00:00Z"
IN_WINDOW = "2026-07-06T00:00:00Z"    # +24h
PAST_WINDOW = "2026-07-08T00:00:01Z"  # +72h + 1s


@pytest.fixture()
def root(tmp_path):
    return tmp_path / "cab"


def _no_reds(applied_at, now):
    return []


class TestRecordAndMerge:
    def test_record_apply_row(self, root):
        row = apply_watch.record_apply(
            "pack-abc", applied_at=APPLIED,
            revert_plan="git -c core.hooksPath=/dev/null apply -R v.patch",
            sha256="deadbeef", root=root)
        assert row["status"] == "watching"
        assert row["watch_until"] == "2026-07-08T00:00:00Z"
        on_disk = apply_watch.watch_path(root).read_text()
        assert "pack-abc" in on_disk

    def test_last_write_wins_per_pack(self, root):
        apply_watch.record_apply("pack-abc", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        assert apply_watch.mark("pack-abc", "closed", root=root,
                                now=PAST_WINDOW) is not None
        merged = apply_watch._merged(apply_watch.watch_path(root))
        assert merged["pack-abc"]["status"] == "closed"

    def test_mark_unknown_or_bad_status_is_none(self, root):
        assert apply_watch.mark("pack-ghost", "closed", root=root) is None
        apply_watch.record_apply("pack-abc", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        assert apply_watch.mark("pack-abc", "exploded", root=root) is None


class TestEvaluate:
    def test_red_inside_window_decides_rollback(self, root):
        apply_watch.record_apply(
            "pack-red", applied_at=APPLIED,
            revert_plan="git -c core.hooksPath=/dev/null apply -R v.patch",
            root=root)
        decisions = apply_watch.evaluate(
            now=IN_WINDOW, root=root,
            red_signals_fn=lambda a, n: ["kind frozen after apply: pm_write"])
        assert decisions == [{
            "pack_id": "pack-red", "decision": "rollback",
            "reason": "kind frozen after apply: pm_write",
            "revert_plan": "git -c core.hooksPath=/dev/null apply -R v.patch",
        }]
        # ledger transitioned — idempotent on re-run
        assert apply_watch.evaluate(now=IN_WINDOW, root=root,
                                    red_signals_fn=lambda a, n: ["x"]) == []

    def test_clean_past_window_closes(self, root):
        apply_watch.record_apply("pack-ok", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        decisions = apply_watch.evaluate(now=PAST_WINDOW, root=root,
                                         red_signals_fn=_no_reds)
        assert decisions[0]["decision"] == "close"
        assert decisions[0]["revert_plan"] is None
        merged = apply_watch._merged(apply_watch.watch_path(root))
        assert merged["pack-ok"]["status"] == "closed"

    def test_clean_inside_window_keeps_watching(self, root):
        apply_watch.record_apply("pack-w", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        decisions = apply_watch.evaluate(now=IN_WINDOW, root=root,
                                         red_signals_fn=_no_reds)
        assert decisions[0]["decision"] == "watch"
        merged = apply_watch._merged(apply_watch.watch_path(root))
        assert merged["pack-w"]["status"] == "watching"

    def test_broken_red_probe_reads_as_no_signal(self, root):
        apply_watch.record_apply("pack-p", applied_at=APPLIED,
                                 revert_plan="p", root=root)

        def broken(applied_at, now):
            raise OSError("probe down")

        decisions = apply_watch.evaluate(now=IN_WINDOW, root=root,
                                         red_signals_fn=broken)
        assert decisions[0]["decision"] == "watch"

    def test_default_red_signals_sees_freeze_and_red_canary(
            self, root, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
        from framework.frontdoor import action_undo
        action_undo.record_canary_receipt("task_status_move", green=False,
                                          now=IN_WINDOW)
        reds = apply_watch._default_red_signals(APPLIED, PAST_WINDOW)
        assert any("red canary receipt" in r for r in reds)
        # a green receipt alone is not a red signal
        monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo2"))
        action_undo.record_canary_receipt("task_status_move", green=True,
                                          now=IN_WINDOW)
        assert apply_watch._default_red_signals(APPLIED, PAST_WINDOW) == []

    def test_evaluate_never_mutates_tree(self, root):
        # decisions only: nothing outside the watch ledger is written
        apply_watch.record_apply("pack-x", applied_at=APPLIED,
                                 revert_plan="p", root=root)
        before = {p for p in root.rglob("*") if p.is_file()}
        apply_watch.evaluate(now=IN_WINDOW, root=root, red_signals_fn=_no_reds)
        after = {p for p in root.rglob("*") if p.is_file()}
        assert before == after
