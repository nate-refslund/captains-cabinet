"""Tests for cabinet/scripts/purge-sqlite-mirror.py (2026-07-05 prep, lane
hygiene — the follow-up pass ledger-purge-testrows.sh's SCOPE block promised
for the org-runtime SQLite Store mirror).

Like the JSONL purge, this script is PREP ONLY until the Captain flips
CABINET_PURGE_CONFIRM=1 against the live mirror — so these tests are the only
execution it gets before that moment. They exercise it end-to-end against
TEMP fixture databases (never the live one, ORG_RUNTIME_DB always pinned to a
tmp path): both refuse-gates, the never-create-the-DB refusal, the read-only
dry-run, the exact junk criteria (identical to the JSONL purge's org family),
the FK-referenced fail-safe, the backup-first guarantee, append-only trigger
restoration, and idempotency.

Run shape mirrors cabinet/scripts/tests/test_ledger_purge_testrows.py:
subprocess against the real script, real python3, real sqlite3 — the fixture
DB is built through the REAL Store class (cabinet/scripts/lib/org_runtime.py)
so schema + append-only triggers are exactly what production carries.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS_DIR / "purge-sqlite-mirror.py"

# Import the real Store for fixture-building (schema fidelity — the fixture
# DB must carry the REAL append-only triggers the script drops/recreates).
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))
from org_runtime import Store  # noqa: E402


# --- fixture rows -------------------------------------------------------------
# Mirrors the REAL mirrored junk shapes (framework/events/emitter.py
# _write_to_store → Store.append_event with source="framework"): junk subagent
# completions carry completed_by=="subagent" with no FW-*/PROD-* task_ref
# (TASK-* is still junk per the exact criteria — only FW/PROD refs are genuine
# work-graph signal, matching test_ledger_purge_testrows.py).

DROP_ROWS = [
    # junk subagent completions (criterion 2)
    ("d1", "work_item_completed", "unknown",
     {"agent_type": "", "agent_id": "a1", "session_id": "s",
      "completed_by": "subagent"}),
    ("d2", "work_item_completed", "cos",
     {"task_ref": "TASK-99", "agent_type": "TASK-99 helper", "agent_id": "a2",
      "session_id": "s", "completed_by": "subagent"}),
    # fixture fidelity row (criterion 1 — defensive: expected 0 live, but a
    # forced-on mirror under pytest COULD have written these)
    ("d3", "fidelity_case_evaluated", "chair",
     {"subject": "abc1234567", "refs": ["abc1234567"]}),
]

KEEP_ROWS = [
    # genuine subagent completion — FW ref present (work-graph signal)
    ("k1", "work_item_completed", "cto",
     {"task_ref": "FW-12", "agent_type": "FW-12 builder", "agent_id": "a3",
      "session_id": "s", "completed_by": "subagent"}),
    # genuine framework-emitted completion (no completed_by marker at all)
    ("k2", "work_item_completed", "cos", {"task_id": "outcome-001-task-003"}),
    # unrelated event type
    ("k3", "mission_created", "cos", {"mission_id": "m-1"}),
    # genuine fidelity row — real subject, not the fixture literal
    ("k4", "fidelity_case_evaluated", "chair", {"subject": "case-real-01"}),
]


def _build_fixture(db_path: Path) -> None:
    """Fixture mirror DB through the REAL Store (schema + triggers)."""
    store = Store(path=db_path)
    for event_id, event_type, actor, payload in DROP_ROWS + KEEP_ROWS:
        store.append_event(
            event_type=event_type,
            lane_slug="captains-cabinet",
            aggregate_type="work_item",
            aggregate_id=payload.get("task_ref") or payload.get("subject") or "unknown",
            actor=actor,
            payload=payload,
            source="framework",
            event_id=event_id,
        )
    store.conn.close()


def _add_unparseable_row(db_path: Path, event_id: str = "u1") -> None:
    """Inject a row whose payload_json is NOT valid JSON (fail-safe target).

    Store.append_event always writes valid JSON, so go under it — triggers
    only guard UPDATE/DELETE, inserts are free.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO org_events (event_id, event_type, lane_slug,"
        " aggregate_type, aggregate_id, actor, source, payload_json,"
        " supersedes_event_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (event_id, "work_item_completed", "captains-cabinet", "work_item",
         "x", "unknown", "framework", "NOT-JSON{{{", None,
         "2026-06-18T15:00:00Z"),
    )
    conn.commit()
    conn.close()


def _add_fk_reference(db_path: Path, junk_event_id: str) -> None:
    """Make a work_graph_nodes row reference a junk event's event_id.

    Exercises the FK fail-safe: a referenced junk row must be KEPT (deleting
    it would orphan completion_event_id). Parent rows (outcome + mission) are
    built first so the fixture satisfies the whole FK chain.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO captain_outcomes (outcome_id, lane_slug, title,"
        " metric_name, target_value, state, proposed_by, created_at,"
        " updated_at) VALUES ('o1','captains-cabinet','t','m',1,'ratified',"
        "'captain','2026-06-18T15:00:00Z','2026-06-18T15:00:00Z')"
    )
    conn.execute(
        "INSERT INTO missions (mission_id, outcome_id, lane_slug, title,"
        " state, created_at, updated_at) VALUES ('m1','o1','captains-cabinet',"
        "'t','compiled','2026-06-18T15:00:00Z','2026-06-18T15:00:00Z')"
    )
    conn.execute(
        "INSERT INTO work_graph_nodes (node_id, mission_id, title, owner_role,"
        " status, completion_event_id, created_at) VALUES ('n1','m1','t',"
        "'cto','verified',?, '2026-06-18T15:00:00Z')",
        (junk_event_id,),
    )
    conn.commit()
    conn.close()


def _count_rows(db_path: Path) -> int:
    conn = sqlite3.connect("file:{}?mode=ro".format(db_path), uri=True)
    try:
        (n,) = conn.execute("SELECT COUNT(*) FROM org_events").fetchone()
        return n
    finally:
        conn.close()


def _event_ids(db_path: Path) -> set:
    conn = sqlite3.connect("file:{}?mode=ro".format(db_path), uri=True)
    try:
        return {r[0] for r in conn.execute("SELECT event_id FROM org_events")}
    finally:
        conn.close()


def _run(script: Path, db_path: Path, *, confirm: bool = False,
         dry_run: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Pin the script to THIS test's fixture DB; defensively pop every purge
    # flag so nothing leaks in from the outer session (same discipline as
    # test_ledger_purge_testrows.py::_run).
    env["ORG_RUNTIME_DB"] = str(db_path)
    env.pop("CABINET_ROOT", None)  # never let a live root leak into path resolution
    env.pop("CABINET_PURGE_CONFIRM", None)
    env.pop("CABINET_PURGE_DRY_RUN", None)
    if confirm:
        env["CABINET_PURGE_CONFIRM"] = "1"
    if dry_run:
        env["CABINET_PURGE_DRY_RUN"] = "1"
    return subprocess.run(
        [sys.executable, str(script)], env=env, capture_output=True,
        text=True, timeout=60,
    )


class TestRefuseGates:
    def test_refuses_without_confirm_flag(self, tmp_path):
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        before = _event_ids(db)
        result = _run(SCRIPT, db, confirm=False)
        assert result.returncode == 1
        assert "CABINET_PURGE_CONFIRM" in result.stderr
        # Nothing was touched — same rows, no backup dir.
        assert _event_ids(db) == before
        assert not (tmp_path / "mirror-backups").exists()

    def test_refuses_without_fixed_hook_fence(self, tmp_path):
        # Reproduce the REAL gate mechanism (no override backdoor): copy the
        # script into a fake repo layout whose subagent hook is the OLD
        # always-emit version (no subagent_completed marker) — repo root
        # derives from the script's own location, so the fence check fails
        # even with the confirm flag set.
        fake_repo = tmp_path / "repo"
        scripts_dir = fake_repo / "cabinet" / "scripts"
        hooks_dir = scripts_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        shutil.copy2(SCRIPT, scripts_dir / "purge-sqlite-mirror.py")
        (hooks_dir / "on-subagent-stop.sh").write_text(
            "#!/bin/bash\n# legacy hook: always emits work_item_completed\n"
        )
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        before = _event_ids(db)
        result = _run(scripts_dir / "purge-sqlite-mirror.py", db, confirm=True)
        assert result.returncode == 1
        assert "subagent" in result.stderr and "hook" in result.stderr
        assert _event_ids(db) == before
        assert not (tmp_path / "mirror-backups").exists()

    def test_real_repo_hook_has_the_fence(self):
        # The gate the previous test bypassed must HOLD in this checkout: the
        # g-hooks fix (generic stops → subagent_completed) is present. If this
        # fails, the hook regressed and the purge must not run.
        hook = SCRIPTS_DIR / "hooks" / "on-subagent-stop.sh"
        assert hook.exists()
        assert "subagent_completed" in hook.read_text()

    def test_refuses_on_missing_db_and_never_creates_it(self, tmp_path):
        # THE reason org_runtime.Store is not imported for path resolution:
        # Store.__init__ would CREATE the missing DB. The purge must refuse.
        db = tmp_path / "does-not-exist.sqlite3"
        result = _run(SCRIPT, db, confirm=True)
        assert result.returncode == 1
        assert "not found" in result.stderr
        assert not db.exists()

    def test_dry_run_on_missing_db_refuses_without_creating(self, tmp_path):
        db = tmp_path / "does-not-exist.sqlite3"
        result = _run(SCRIPT, db, dry_run=True)
        assert result.returncode == 1
        assert not db.exists()


class TestDryRun:
    def test_dry_run_previews_without_writing(self, tmp_path):
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        before = _event_ids(db)
        result = _run(SCRIPT, db, dry_run=True)  # note: NO confirm needed
        assert result.returncode == 0, result.stderr
        assert "DRY RUN" in result.stdout
        # counts visible for the Captain's go/no-go call: 7 rows, 3 junk
        assert "rows before:            7" in result.stdout
        assert "would drop (fixture subject=='abc1234567'): 1" in result.stdout
        assert "would drop (junk subagent work_item_completed):  2" in result.stdout
        assert "rows after:             4" in result.stdout
        # zero mutation, zero backup
        assert _event_ids(db) == before
        assert not (tmp_path / "mirror-backups").exists()


class TestPurge:
    def test_purges_exact_criteria_and_backs_up_first(self, tmp_path):
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        result = _run(SCRIPT, db, confirm=True)
        assert result.returncode == 0, result.stderr

        # before/after counts printed, per criterion
        assert "rows before:            7" in result.stdout
        assert "dropped (fixture subject=='abc1234567'): 1" in result.stdout
        assert "dropped (junk subagent work_item_completed):  2" in result.stdout
        assert "rows after:             4" in result.stdout

        # junk gone, genuine kept — by exact id set
        assert _event_ids(db) == {"k1", "k2", "k3", "k4"}

        # backup exists under the DB's own dir (gitignored cabinet/cache
        # pattern in production), holds the ORIGINAL 7 pre-purge rows
        backups = sorted((tmp_path / "mirror-backups").glob("purge-*/org-runtime.sqlite3"))
        assert len(backups) == 1
        assert _count_rows(backups[0]) == 7
        assert _event_ids(backups[0]) == {r[0] for r in DROP_ROWS + KEEP_ROWS}

    def test_append_only_triggers_survive_the_purge(self, tmp_path):
        # The purge borrows against the append-only invariant (drops the
        # guard triggers to delete) — it must hand the invariant back intact.
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        result = _run(SCRIPT, db, confirm=True)
        assert result.returncode == 0, result.stderr
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
            }
            assert {"prevent_org_events_update", "prevent_org_events_delete"} <= names
            # and they ENFORCE: UPDATE and DELETE both abort post-purge
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("UPDATE org_events SET actor='x' WHERE event_id='k1'")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM org_events WHERE event_id='k1'")
        finally:
            conn.close()

    def test_fk_referenced_junk_is_kept_and_reported(self, tmp_path):
        # d1 is junk AND referenced by work_graph_nodes.completion_event_id →
        # deleting it would orphan the node; the fail-safe keeps + reports it.
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        _add_fk_reference(db, "d1")
        result = _run(SCRIPT, db, confirm=True)
        assert result.returncode == 0, result.stderr
        assert "kept (junk but FK-referenced — never orphaned): 1" in result.stdout
        # d1 survived; the unreferenced junk (d2, d3) is gone
        assert _event_ids(db) == {"k1", "k2", "k3", "k4", "d1"}
        assert "dropped (junk subagent work_item_completed):  1" in result.stdout

    def test_unparseable_payload_is_never_dropped(self, tmp_path):
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        _add_unparseable_row(db, "u1")
        result = _run(SCRIPT, db, confirm=True)
        assert result.returncode == 0, result.stderr
        assert "unparseable payload_json kept (never dropped): 1" in result.stdout
        assert "u1" in _event_ids(db)

    def test_purge_is_idempotent(self, tmp_path):
        db = tmp_path / "org-runtime.sqlite3"
        _build_fixture(db)
        first = _run(SCRIPT, db, confirm=True)
        assert first.returncode == 0, first.stderr
        ids_after_first = _event_ids(db)

        second = _run(SCRIPT, db, confirm=True)
        assert second.returncode == 0, second.stderr
        # nothing junk left: 4 kept rows, zero drops, NO second backup taken
        assert "rows before:            4" in second.stdout
        assert "rows after:             4" in second.stdout
        assert "nothing to purge" in second.stdout
        assert _event_ids(db) == ids_after_first
        backups = sorted((tmp_path / "mirror-backups").glob("purge-*"))
        assert len(backups) == 1  # only the first (mutating) run backed up

    def test_clean_mirror_with_unparseable_row_reports_it_on_noop(self, tmp_path):
        # No-op fast path (nothing deletable) must STILL report an unparseable
        # row it kept — exercises the pre-pass reporting branch, and proves an
        # unparseable row is never mistaken for a deletable candidate.
        db = tmp_path / "org-runtime.sqlite3"
        store = Store(path=db)
        for event_id, event_type, actor, payload in KEEP_ROWS:
            store.append_event(
                event_type=event_type, lane_slug="captains-cabinet",
                aggregate_type="work_item", aggregate_id="x", actor=actor,
                payload=payload, source="framework", event_id=event_id,
            )
        store.conn.close()
        _add_unparseable_row(db, "u1")
        result = _run(SCRIPT, db, confirm=True)
        assert result.returncode == 0, result.stderr
        assert "nothing to purge" in result.stdout
        assert "unparseable payload_json kept (never dropped): 1" in result.stdout
        assert not (tmp_path / "mirror-backups").exists()
        assert "u1" in _event_ids(db)

    def test_clean_mirror_is_a_clean_noop(self, tmp_path):
        # A mirror with ONLY genuine rows: no backup, no mutation, exit 0.
        db = tmp_path / "org-runtime.sqlite3"
        store = Store(path=db)
        for event_id, event_type, actor, payload in KEEP_ROWS:
            store.append_event(
                event_type=event_type, lane_slug="captains-cabinet",
                aggregate_type="work_item", aggregate_id="x", actor=actor,
                payload=payload, source="framework", event_id=event_id,
            )
        store.conn.close()
        result = _run(SCRIPT, db, confirm=True)
        assert result.returncode == 0, result.stderr
        assert "nothing to purge" in result.stdout
        assert not (tmp_path / "mirror-backups").exists()
        assert _event_ids(db) == {"k1", "k2", "k3", "k4"}


class TestCriteriaParity:
    """The mirror purge and the JSONL purge must classify identically —
    ledger convergence is the whole point of the sibling script."""

    def test_task_ref_regex_matches_jsonl_script(self):
        # Load the module under its file path (dashes forbid a plain import).
        import importlib.util
        spec = importlib.util.spec_from_file_location("purge_sqlite_mirror", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.FIXTURE_SUBJECT == "abc1234567"
        # FW/PROD genuine; TASK-* and everything else junk — the exact
        # criterion 2 semantics of ledger-purge-testrows.sh
        assert mod.GENUINE_REF.match("FW-12")
        assert mod.GENUINE_REF.match("PROD-3")
        assert not mod.GENUINE_REF.match("TASK-99")
        assert not mod.GENUINE_REF.match("FW-12x")
        assert not mod.GENUINE_REF.match("")
        # classify() parity spot-checks against the JSONL org-family branch
        assert mod.classify("work_item_completed",
                            {"completed_by": "subagent"}) == "subagent"
        assert mod.classify("work_item_completed",
                            {"completed_by": "subagent", "task_ref": "FW-12"}) is None
        assert mod.classify("fidelity_case_evaluated",
                            {"subject": "abc1234567"}) == "fixture"
        assert mod.classify("mission_created", {"mission_id": "m-1"}) is None
