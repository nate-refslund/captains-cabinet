#!/usr/bin/env python3
"""purge-sqlite-mirror.py — one-shot, Captain-gated purge of KNOWN-JUNK rows
from the org-runtime SQLite Store mirror (cabinet/cache/org-runtime.sqlite3).

Sibling of cabinet/scripts/ledger-purge-testrows.sh (the JSONL purge, run live
2026-07-04 23:20Z — backup purge-20260704_232009Z-48377). That script's SCOPE
block deliberately left the Store mirror as a follow-up:
framework/events/emitter.py::_write_to_store() mirrors every hook-emitted
org event into the Store, so the ~6.6k junk work_item_completed rows that
cabinet/scripts/hooks/on-subagent-stop.sh emitted for EVERY subagent stop
(code reviewers, explainer crews, ...) were mirrored there too — and the
Store is what the dashboard / claude-task-bridge / org_runtime CLI read.
This script is that verified pass (prepared 2026-07-05, lane hygiene).

WHAT IS PURGED (same criteria as the JSONL purge's org family — the two
ledgers must converge; see ledger-purge-testrows.sh classify(), org branch):
  1. Junk subagent completions — event_type == "work_item_completed" AND
     payload.completed_by == "subagent" AND payload.task_ref NOT matching
     ^(FW|PROD)-[0-9]+$. (Framework-emitted completions — e.g. mission
     supervisor — never carry completed_by=="subagent" and are untouched by
     construction.)
  2. Fidelity fixture rows — payload.subject == "abc1234567". DEFENSIVE:
     the Store mirror auto-skips under pytest (emitter.py::_write_to_store,
     PYTEST_CURRENT_TEST guard) so the count here is expected to be ZERO —
     but CABINET_FRAMEWORK_STORE_MIRROR=1 forces the mirror on even in tests,
     so we sweep the criterion anyway rather than assume.
The consequence-events family has NO Store mirror at all (JSONL-only by F0
design — ledger-purge-testrows.sh SCOPE block), so org-family criteria are
the complete set for this database.

GATES for a mutating run (both required — fail-safe, mirrors the JSONL
script's gate design):
  1. CABINET_PURGE_CONFIRM=1      — the Captain's explicit go signal.
  2. Fixed-hook fence             — cabinet/scripts/hooks/on-subagent-stop.sh
     in THIS checkout must contain the "subagent_completed" marker (the
     g-hooks 2026-07-04 fix routing generic helper-agent stops away from
     work_item_completed). Purging while the old always-emit hook is still
     in place just re-accretes the same junk.

MODES:
  Preview (read-only, no gates — opens the DB in sqlite URI mode=ro, writes
  NOTHING, for the go/no-go call):
    CABINET_PURGE_DRY_RUN=1 python3 cabinet/scripts/purge-sqlite-mirror.py
  Real run (Captain-gated):
    CABINET_PURGE_CONFIRM=1 python3 cabinet/scripts/purge-sqlite-mirror.py

DB LOCATION: ORG_RUNTIME_DB env overrides, else
$CABINET_ROOT/cabinet/cache/org-runtime.sqlite3 — the SAME resolution
contract as cabinet/scripts/lib/org_runtime.py::default_db_path() (kept in
lockstep; that module is NOT imported because Store.__init__ CREATES the DB
file + schema when missing, and a purge tool must never create what it was
asked to clean — a missing DB is a REFUSAL here).

SAFETY DESIGN (Corridor-reviewed posture — do not weaken):
  * Backup FIRST: sqlite3.Connection.backup() online snapshot into
    <db dir>/mirror-backups/purge-<UTCts>-<pid>/org-runtime.sqlite3;
    row-count-verified; existing backup dir → refusal (never overwrite a
    rollback copy). The backup is taken in AUTOCOMMIT mode, BEFORE the write
    lock — backup() deadlocks against an open BEGIN IMMEDIATE on the same
    connection (empirically verified 2026-07-05; see the ORDERING note in
    main()) — and the lock-then-prove step below closes the gap that
    ordering opens. cabinet/cache/* is gitignored (.gitignore:116) so
    backups never land in git; unlike the JSONL family nothing globs this
    dir for reads (Store opens the exact file path), so an in-dir backup can
    never be mis-read as live data.
  * Lock, then PROVE the backup still matches: after the snapshot we take
    BEGIN IMMEDIATE and require (COUNT(*), MAX(rowid)) unchanged across
    backup→lock. org_events is append-only (the guard triggers), so that
    pair being unchanged means byte-identical content — a slipped-in live
    append discards the stale backup and retries (bounded), never mutates.
    All deletes then run inside that one write transaction. Live emitter
    mirror writes are best-effort by design (emitter.py::_write_to_store
    catches Exception and WARNs; the JSONL ledger remains the guaranteed
    record) and sqlite3's default 5s busy timeout rides out our short lock
    anyway — still, prefer running quiesced.
  * Append-only triggers: org_events carries prevent_org_events_update /
    prevent_org_events_delete (org_runtime.py::init_schema, the append-only
    invariant). This purge is the ONE sanctioned exception: it DROPs the two
    triggers, deletes by explicit event_id list, and RECREATEs them verbatim
    inside the same transaction — then VERIFIES both exist before COMMIT.
    Any exception anywhere → rollback, DB byte-identical.
  * FK fail-safe: a junk row referenced by ANY foreign key child (e.g.
    work_graph_nodes.completion_event_id, org_events.supersedes_event_id
    self-refs) is KEPT and reported, never deleted — we introspect every
    table's PRAGMA foreign_key_list at runtime instead of hardcoding the
    child list, so schema growth can't silently open a dangling-ref hole.
  * Unparseable payload_json is never dropped (fail-safe: only remove what
    we can positively identify as junk).
  * Row content never passes through a shell; no secrets involved; no
    network. Deletion is by primary key from a Python-computed list.

ROLLBACK: stop the org (killswitch / launchd agents), copy the backup file
back over cabinet/cache/org-runtime.sqlite3, restart. Rows mirrored AFTER
the purge exist only in the JSONL ledger until re-mirrored; the JSONL ledger
is the guaranteed record either way (emitter.py write order).
"""

# NOTE: future-import keeps X | Y annotations un-evaluated so this runs on
# the system python3 (3.9.6 at prep time) — recorded gotcha: match the
# system Python, never assume 3.10+ union syntax is available at runtime.
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

# Criteria constants — kept IDENTICAL to ledger-purge-testrows.sh (criterion
# 1 fixture subject, criterion 2 genuine-ref regex) so the JSONL ledger and
# the Store mirror converge on the same post-purge truth.
FIXTURE_SUBJECT = "abc1234567"
GENUINE_REF = re.compile(r"^(FW|PROD)-[0-9]+$")

# The two append-only guard triggers — names + bodies must stay in lockstep
# with cabinet/scripts/lib/org_runtime.py::init_schema() (org_events block,
# lines ~90-100). IF EXISTS / IF NOT EXISTS forms make the drop/recreate
# idempotent even against an old mirror created before the triggers existed
# (recreating them there is correct: init_schema would add them on the next
# Store open anyway). ONE statement per entry — sqlite3's execute() accepts a
# single statement (a trigger's BEGIN...END body is still one statement), and
# executescript() would implicitly COMMIT our open transaction — so these are
# executed one by one inside the purge txn.
_TRIGGER_NAMES = ("prevent_org_events_update", "prevent_org_events_delete")
_TRIGGER_STMTS = (
    "CREATE TRIGGER IF NOT EXISTS prevent_org_events_update\n"
    "BEFORE UPDATE ON org_events\n"
    "BEGIN\n"
    "  SELECT RAISE(ABORT, 'org_events is append-only; append a superseding event instead');\n"
    "END",
    "CREATE TRIGGER IF NOT EXISTS prevent_org_events_delete\n"
    "BEFORE DELETE ON org_events\n"
    "BEGIN\n"
    "  SELECT RAISE(ABORT, 'org_events is append-only; append a superseding event instead');\n"
    "END",
)

# SQLite's default max host parameters is 999 — chunk every IN (...) list
# well below it so candidate volume can never overflow a statement.
_CHUNK = 500

# Backup→lock quiescence retries (see the ORDERING note in main()): live
# mirror appends arrive every few minutes at most (hook cadence), so a stale
# backup on ALL of these attempts means the org is genuinely busy — refuse
# and ask for a quiesced run rather than looping forever.
_QUIESCE_ATTEMPTS = 3


def repo_root() -> Path:
    """This script lives at cabinet/scripts/ → repo root is two levels up."""
    return Path(__file__).resolve().parents[2]


def db_path() -> Path:
    """Same resolution contract as org_runtime.py::default_db_path()."""
    root = Path(os.environ.get("CABINET_ROOT", str(repo_root())))
    return Path(os.environ.get("ORG_RUNTIME_DB", str(root / "cabinet/cache/org-runtime.sqlite3")))


def classify(event_type: str, payload: dict) -> "str | None":
    """Return the junk criterion this row matches, or None to keep it.

    EXACT mirror of ledger-purge-testrows.sh classify() org-family branch —
    the mirror only ever receives org events (emitter.py::_write_to_store),
    so the org criteria are the complete set here.
    """
    if payload.get("subject") == FIXTURE_SUBJECT:
        return "fixture"
    if (
        event_type == "work_item_completed"
        and payload.get("completed_by") == "subagent"
        and not GENUINE_REF.match(str(payload.get("task_ref") or ""))
    ):
        return "subagent"
    return None


def _chunks(seq: list, n: int) -> "list[list]":
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def find_junk(conn: sqlite3.Connection) -> "tuple[int, dict[str, list[str]], int]":
    """Scan org_events; return (total_rows, junk ids per criterion, unparseable).

    payload_json is parsed in PYTHON (never a shell) — an unparseable payload
    means we cannot positively identify the row, so it is KEPT (fail-safe).
    """
    total = 0
    junk = {"fixture": [], "subagent": []}  # type: dict[str, list[str]]
    unparseable = 0
    cur = conn.execute("SELECT event_id, event_type, payload_json FROM org_events")
    for event_id, event_type, payload_json in cur:
        total += 1
        try:
            payload = json.loads(payload_json or "{}")
        except (json.JSONDecodeError, ValueError):
            unparseable += 1
            continue  # fail-safe: keep
        if not isinstance(payload, dict):
            unparseable += 1
            continue  # unknown shape → fail-safe: keep
        criterion = classify(event_type, payload)
        if criterion:
            junk[criterion].append(str(event_id))
    return total, junk, unparseable


def referencing_columns(conn: sqlite3.Connection) -> "list[tuple[str, str]]":
    """Every (table, column) whose FK points at org_events(event_id).

    Introspected at runtime via PRAGMA foreign_key_list over ALL tables —
    never a hardcoded child list, so future schema growth (new tables
    referencing org_events) is covered automatically. Includes the
    org_events.supersedes_event_id self-reference.
    """
    refs = []  # type: list[tuple[str, str]]
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for table in tables:
        # Table names come from sqlite_master (trusted schema, not row data);
        # still quote defensively — PRAGMA takes no bound parameters.
        quoted = '"' + table.replace('"', '""') + '"'
        for row in conn.execute("PRAGMA foreign_key_list({})".format(quoted)):
            # row: (id, seq, table, from, to, on_update, on_delete, match);
            # `to` is None when the FK targets the parent's PRIMARY KEY
            # implicitly — org_events' PK is event_id, so None counts too.
            if row[2] == "org_events" and (row[4] is None or row[4] == "event_id"):
                refs.append((table, row[3]))
    return refs


def referenced_ids(conn: sqlite3.Connection, candidate_ids: "list[str]") -> "set[str]":
    """Subset of candidate_ids referenced by ANY FK child column."""
    referenced = set()  # type: set[str]
    for table, column in referencing_columns(conn):
        quoted_t = '"' + table.replace('"', '""') + '"'
        quoted_c = '"' + column.replace('"', '""') + '"'
        for chunk in _chunks(candidate_ids, _CHUNK):
            placeholders = ",".join("?" for _ in chunk)
            sql = "SELECT DISTINCT {c} FROM {t} WHERE {c} IN ({p})".format(
                c=quoted_c, t=quoted_t, p=placeholders
            )
            for (ref_id,) in conn.execute(sql, chunk):
                referenced.add(str(ref_id))
    return referenced


def refuse(msg: str) -> "None":
    print("REFUSED: " + msg, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    dry_run = os.environ.get("CABINET_PURGE_DRY_RUN") == "1"
    path = db_path()

    if not dry_run:
        # --- Gate 1: Captain go/no-go (same env contract as the JSONL purge) --
        if os.environ.get("CABINET_PURGE_CONFIRM") != "1":
            refuse(
                "CABINET_PURGE_CONFIRM=1 not set (Captain go/no-go gate).\n"
                "This purge rewrites the org-runtime Store mirror (backup-first,\n"
                "but still Captain-gated). Preview first:\n"
                "  CABINET_PURGE_DRY_RUN=1 python3 {0}\n"
                "Then run for real:\n"
                "  CABINET_PURGE_CONFIRM=1 python3 {0}".format(sys.argv[0])
            )

        # --- Gate 2: the fixed hook must be present in this checkout ---------
        # Purging while on-subagent-stop.sh still emits work_item_completed
        # for every stop just re-accretes the junk. The g-hooks fix routes
        # generic stops to subagent_completed — grep for that marker (same
        # cheap merged-in-this-checkout proxy as the JSONL script's conftest
        # fence check).
        hook = repo_root() / "cabinet" / "scripts" / "hooks" / "on-subagent-stop.sh"
        try:
            hook_text = hook.read_text(encoding="utf-8")
        except OSError:
            hook_text = ""
        if "subagent_completed" not in hook_text:
            refuse(
                "fixed subagent hook not found at {} —\n"
                "merge the g-hooks fix (generic stops -> subagent_completed)\n"
                "before purging, or the same junk rows re-accrete.".format(hook)
            )

    if not path.is_file():
        # A purge tool never CREATES the thing it was asked to clean —
        # org_runtime.Store would (mkdir + init_schema), which is exactly why
        # we don't import it.
        refuse("Store mirror not found: {} — nothing to purge.".format(path))

    if dry_run:
        # Read-only preview: URI mode=ro can neither create nor write.
        conn = sqlite3.connect("file:{}?mode=ro".format(path), uri=True)
        try:
            total, junk, unparseable = find_junk(conn)
            candidates = junk["fixture"] + junk["subagent"]
            kept_referenced = referenced_ids(conn, candidates) if candidates else set()
            n_fixture = len([i for i in junk["fixture"] if i not in kept_referenced])
            n_subagent = len([i for i in junk["subagent"] if i not in kept_referenced])
        finally:
            conn.close()
        print("--- DRY RUN — no rows were deleted ---")
        print("rows before:            {}".format(total))
        print("would drop (fixture subject=={!r}): {}".format(FIXTURE_SUBJECT, n_fixture))
        print("would drop (junk subagent work_item_completed):  {}".format(n_subagent))
        if kept_referenced:
            print(
                "kept (junk but FK-referenced — never orphaned): {}".format(
                    len(kept_referenced)
                )
            )
        print("rows after:             {}".format(total - n_fixture - n_subagent))
        if unparseable:
            print("unparseable payload_json kept (never dropped): {}".format(unparseable))
        print("dry run complete — re-run with CABINET_PURGE_CONFIRM=1 to apply.")
        return

    # ---- Mutating run -------------------------------------------------------
    # ORDERING (empirically forced, 2026-07-05): sqlite3.Connection.backup()
    # DEADLOCKS if the source connection holds an open BEGIN IMMEDIATE
    # transaction (verified in isolation: backup() blocks forever after
    # `BEGIN IMMEDIATE` on the same connection — that hang ate the first test
    # run at 60s/subprocess). So the backup CANNOT sit inside the write txn.
    # Instead: backup in autocommit → take the write lock → PROVE nothing
    # changed in between. That proof is sound because org_events is
    # append-only (prevent_org_events_update/delete triggers — rows can only
    # be INSERTed, never changed or removed), so an unchanged
    # (COUNT(*), MAX(rowid)) pair across backup→lock means byte-identical
    # content. If a live append DID slip in, discard the stale backup (no
    # mutation has happened yet) and retry; after _QUIESCE_ATTEMPTS misses,
    # refuse and tell the operator to quiesce the org.
    conn = sqlite3.connect(str(path))
    # Manual transaction mode: the module's implicit-BEGIN machinery would
    # otherwise interleave with our explicit BEGIN IMMEDIATE ("cannot start a
    # transaction within a transaction" class of surprises). With
    # isolation_level=None, OUR begin/commit/rollback are the only ones.
    conn.isolation_level = None
    backup_path = None
    try:
        # Read-only pre-pass (autocommit): a clean mirror exits here without
        # ever taking a lock or a backup.
        pre_total, pre_junk, pre_unparseable = find_junk(conn)
        pre_candidates = pre_junk["fixture"] + pre_junk["subagent"]
        if pre_candidates:
            pre_referenced = referenced_ids(conn, pre_candidates)
            pre_candidates = [i for i in pre_candidates if i not in pre_referenced]
        if not pre_candidates:
            # Recompute the FK-kept count for honest reporting.
            all_junk = pre_junk["fixture"] + pre_junk["subagent"]
            print("--- PURGE APPLIED ---")
            print("rows before:            {}".format(pre_total))
            print("dropped (fixture subject=={!r}): 0".format(FIXTURE_SUBJECT))
            print("dropped (junk subagent work_item_completed):  0")
            if all_junk:
                print(
                    "kept (junk but FK-referenced — never orphaned): {}".format(
                        len(all_junk)
                    )
                )
            print("rows after:             {}".format(pre_total))
            if pre_unparseable:
                print(
                    "unparseable payload_json kept (never dropped): {}".format(
                        pre_unparseable
                    )
                )
            print("nothing to purge — mirror already clean; no backup taken.")
            return

        # --- (a) Backup FIRST (autocommit — see ORDERING note above), then
        # --- (b) lock and prove the backup still matches. --------------------
        # Timestamp + PID + existence refusal: two mutating runs can never
        # share (and thus overwrite) a rollback copy — same collision-proofing
        # as the JSONL script's BACKUP_DIR (checkpoint-review finding
        # 2026-07-04).
        locked = False
        for attempt in range(_QUIESCE_ATTEMPTS):
            (count_pre,) = conn.execute("SELECT COUNT(*) FROM org_events").fetchone()
            (rowid_pre,) = conn.execute(
                "SELECT COALESCE(MAX(rowid), 0) FROM org_events"
            ).fetchone()

            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%SZ")
            backup_dir = path.parent / "mirror-backups" / "purge-{}-{}".format(
                ts, os.getpid()
            )
            if backup_dir.exists():
                refuse(
                    "backup dir already exists: {} — refusing to overwrite an "
                    "existing backup. Mirror untouched.".format(backup_dir)
                )
            backup_dir.mkdir(parents=True)
            backup_path = backup_dir / path.name
            bak = sqlite3.connect(str(backup_path))
            try:
                conn.backup(bak)  # online snapshot of committed state
            finally:
                bak.close()

            # Verify the backup really carries every row before locking.
            verify = sqlite3.connect("file:{}?mode=ro".format(backup_path), uri=True)
            try:
                (bak_rows,) = verify.execute(
                    "SELECT COUNT(*) FROM org_events"
                ).fetchone()
            finally:
                verify.close()
            if bak_rows != count_pre:
                refuse(
                    "backup row count ({}) != source row count ({}). Mirror "
                    "untouched. Partial backup left at {} for inspection.".format(
                        bak_rows, count_pre, backup_dir
                    )
                )

            # Take the write lock, then prove quiescence held across the
            # backup (append-only ⇒ count+max-rowid equality ⇒ identical).
            conn.execute("BEGIN IMMEDIATE")
            (count_locked,) = conn.execute(
                "SELECT COUNT(*) FROM org_events"
            ).fetchone()
            (rowid_locked,) = conn.execute(
                "SELECT COALESCE(MAX(rowid), 0) FROM org_events"
            ).fetchone()
            if (count_locked, rowid_locked) == (count_pre, rowid_pre):
                locked = True
                print("backup: {} rows -> {}".format(count_pre, backup_path))
                break
            # A live append slipped in between backup and lock: the backup is
            # STALE. No mutation has happened, so discarding it is safe —
            # release the lock and retry against the newer state.
            conn.rollback()
            shutil.rmtree(backup_dir)
            backup_path = None
        if not locked:
            refuse(
                "mirror is being actively written ({} backup attempts went "
                "stale) — quiesce the org (killswitch on / launchd agents "
                "stopped) and retry. Mirror untouched.".format(_QUIESCE_ATTEMPTS)
            )

        # --- Junk set computed UNDER the lock (authoritative; the pre-pass
        # --- was only the no-op fast path). ----------------------------------
        total_before, junk, unparseable = find_junk(conn)
        candidates = junk["fixture"] + junk["subagent"]
        kept_referenced = referenced_ids(conn, candidates) if candidates else set()
        to_delete = {
            "fixture": [i for i in junk["fixture"] if i not in kept_referenced],
            "subagent": [i for i in junk["subagent"] if i not in kept_referenced],
        }
        delete_ids = to_delete["fixture"] + to_delete["subagent"]

        # --- The sanctioned append-only exception: drop guards, delete by
        # --- explicit PK list, recreate guards — all inside this txn. --------
        for name in _TRIGGER_NAMES:
            conn.execute("DROP TRIGGER IF EXISTS {}".format(name))
        deleted = 0
        for chunk in _chunks(delete_ids, _CHUNK):
            placeholders = ",".join("?" for _ in chunk)
            cur = conn.execute(
                "DELETE FROM org_events WHERE event_id IN ({})".format(placeholders),
                chunk,
            )
            deleted += cur.rowcount
        # Recreate from the single canonical constant (_TRIGGER_STMTS) — one
        # execute() per statement; see the constant's comment for why
        # executescript() must NOT be used here (implicit COMMIT).
        for stmt in _TRIGGER_STMTS:
            conn.execute(stmt)

        # Verify BOTH guard triggers exist again before committing — a purge
        # must never weaken the append-only invariant it borrowed against.
        (trigger_count,) = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name IN (?, ?)",
            _TRIGGER_NAMES,
        ).fetchone()
        if trigger_count != 2:
            conn.rollback()
            refuse(
                "append-only triggers failed to recreate ({}/2 present) — "
                "rolled back, mirror untouched.".format(trigger_count)
            )

        (total_after,) = conn.execute("SELECT COUNT(*) FROM org_events").fetchone()
        # Arithmetic self-check — if this fails, something in the loop is
        # wrong and we roll back rather than trust the result.
        if total_after + deleted != total_before:
            conn.rollback()
            refuse(
                "row arithmetic does not balance (before={} deleted={} "
                "after={}) — rolled back, mirror untouched.".format(
                    total_before, deleted, total_after
                )
            )

        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        refuse("sqlite error — rolled back, mirror untouched: {}".format(exc))
    finally:
        conn.close()

    print("--- PURGE APPLIED ---")
    print("rows before:            {}".format(total_before))
    print("dropped (fixture subject=={!r}): {}".format(FIXTURE_SUBJECT, len(to_delete["fixture"])))
    print("dropped (junk subagent work_item_completed):  {}".format(len(to_delete["subagent"])))
    if kept_referenced:
        print(
            "kept (junk but FK-referenced — never orphaned): {}".format(len(kept_referenced))
        )
    print("rows after:             {}".format(total_after))
    if unparseable:
        print("unparseable payload_json kept (never dropped): {}".format(unparseable))
    print("purge complete. rollback: quiesce the org, then copy back")
    print("  {} -> {}".format(backup_path, path))


if __name__ == "__main__":
    main()
