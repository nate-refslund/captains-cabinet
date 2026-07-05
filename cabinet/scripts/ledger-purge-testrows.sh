#!/bin/bash
# ledger-purge-testrows.sh — one-shot, Captain-gated purge of KNOWN-JUNK rows
# from the audit event ledger (events-*.jsonl + consequence-events-*.jsonl).
# Prepared 2026-07-04 (lane ledger); REFUSES to mutate anything until BOTH
# gates below hold.
# Reversible by design: full dated backup FIRST, verified before any rewrite.
#
# WHAT LEAKED (and why this script exists):
#   1. Fidelity test-fixture rows — pytest suites emitted through
#      framework/events/emitter.py with no CABINET_EVENT_LOG_DIR set, so the
#      JSONL write fell back to the DURABLE live ledger (the Store SQLite
#      mirror auto-skips under pytest; the JSONL write did not — fixed
#      2026-07-04 by the repo-root conftest.py fence + the emitter's
#      PYTEST_CURRENT_TEST redirect). Signature: payload.subject ==
#      "abc1234567" (the fixture case id). 1,969 rows at diagnosis, 1,996 at
#      prep time — they keep accruing until the fence is merged, which is
#      exactly why gate 2 requires the fence before purging.
#      SAME rows, SECOND family (2026-07-04 adversarial-review finding): the
#      leaking suites dual-emit — framework/fidelity/fidelity_events.py writes
#      each case to the org-event ledger (events-*.jsonl, subject under
#      payload) AND to the consequence ledger (consequence-events-*.jsonl,
#      subject at TOP level, via framework/fidelity/consequence.py, which
#      honours the same CABINET_EVENT_LOG_DIR and fell through to the same
#      live default). 1,996 fixture rows there at prep = ~85% of that family
#      (2,341 total) — and consequence-events is the GRADUATION READ PATH
#      (framework/fidelity/graduation.py autonomy-evidence math), so leaving
#      it polluted is worse than the org family. Criterion 1 therefore
#      applies to BOTH families, keyed per-family (payload.subject vs
#      top-level subject).
#   2. Junk work_item_completed rows — cabinet/scripts/hooks/on-subagent-stop.sh
#      emits work_item_completed for EVERY subagent stop (code reviewers,
#      explainer crews, ...), burying genuine work-graph completions.
#      Signature: payload.completed_by == "subagent" AND payload.task_ref NOT
#      matching ^(FW|PROD)-[0-9]+$. ~6,574 rows at diagnosis, 6,633 at prep.
#      (The hook's switch to the registered subagent_completed type is
#      germline — applied separately; this purge clears the historical
#      pollution only.)
#
# GATES for a mutating run (both required — fail-safe):
#   1. CABINET_PURGE_CONFIRM=1      — the Captain's explicit go signal.
#   2. Repo-root conftest.py fence  — merged + present in this checkout;
#      purging before the fence exists just invites the same rows back.
#
# MODES:
#   Preview (read-only, no gates — writes NOTHING, for the go/no-go call):
#     CABINET_PURGE_DRY_RUN=1 bash cabinet/scripts/ledger-purge-testrows.sh
#   Real run (Captain-gated):
#     CABINET_PURGE_CONFIRM=1 bash cabinet/scripts/ledger-purge-testrows.sh
#
# LEDGER LOCATION: CABINET_EVENT_LOG_DIR overrides (same contract as
# emitter.py) — this is how the test suite
# (cabinet/scripts/tests/test_ledger_purge_testrows.py) exercises the script
# against a temp fixture without ever touching the live ledger. Default is
# the durable live location.
#
# SCOPE — events-*.jsonl AND consequence-events-*.jsonl in the ledger dir.
# Criterion 2 (junk subagent completions) only ever matches the org family:
# work_item_completed is an org-event type — consequence rows are classified
# by the fixture-subject criterion ONLY, so a consequence row that merely
# *mentions* subagent fields can never be dropped. Deliberately NOT touched:
#   * config-drift-*.jsonl (different family, different producer — genuinely
#     unrelated to this incident);
#   * the org-runtime SQLite Store mirror (cabinet/cache/org-runtime.sqlite3):
#     the junk work_item_completed rows were mirrored there too — purged by
#     the SIBLING script cabinet/scripts/purge-sqlite-mirror.py (same gates,
#     same criteria, backup-first; prepared 2026-07-05, lane hygiene); the
#     fidelity fixture rows never reached the mirror (the Store mirror
#     auto-skips under pytest) but the sibling sweeps that criterion
#     defensively anyway; the consequence family has NO mirrors at all
#     (JSONL-only by F0 design — see
#     docs/fidelity-harness-plan-F0-F1-2026-06-18.md), so its cleanup is
#     complete once the JSONL is clean;
#   * Postgres org_events (only written when DATABASE_URL is set — separate
#     verified pass if ever needed).
#
# Kept rows are preserved BYTE-VERBATIM (no re-serialization) so remaining
# audit evidence — ordering, chainhash-referenced content — is untouched.
# Unparseable lines are never dropped (fail-safe: we only remove what we can
# positively identify as junk).
#
# LIVE-APPEND RACE GUARD: the running org appends to TODAY'S events file
# continuously (hooks fire every few minutes), and the fidelity harness
# appends to today's consequence-events file whenever it evaluates a case.
# A rewrite of an active file could clobber a row appended between our read
# and the atomic replace — and the lost row would not be in the backup
# either. So the rewrite SKIPS the current UTC day's file in BOTH families
# by default; their junk rows are simply caught by a later run (or set
# CABINET_PURGE_INCLUDE_TODAY=1 for a run with the org quiesced — killswitch
# on / launchd agents stopped). Historical day-files are append-dead, so
# rewriting them is race-free. (Residual sliver, accepted: a writer that
# resolved its filename just before UTC midnight can in principle append to
# the old day's file while we rewrite it — run the purge away from 00:00 UTC
# or quiesced.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Same resolution contract as framework/events/emitter.py::_event_log_dir()
LEDGER_DIR="${CABINET_EVENT_LOG_DIR:-$HOME/Library/Application Support/cabinet/events}"

DRY_RUN="${CABINET_PURGE_DRY_RUN:-0}"

if [ "$DRY_RUN" != "1" ]; then
  # --- Gate 1: Captain go/no-go ----------------------------------------------
  if [ "${CABINET_PURGE_CONFIRM:-}" != "1" ]; then
    echo "REFUSED: CABINET_PURGE_CONFIRM=1 not set (Captain go/no-go gate)." >&2
    echo "This purge rewrites the audit ledger (backup-first, but still" >&2
    echo "Captain-gated). Preview first:" >&2
    echo "  CABINET_PURGE_DRY_RUN=1 bash $0" >&2
    echo "Then run for real:" >&2
    echo "  CABINET_PURGE_CONFIRM=1 bash $0" >&2
    exit 1
  fi

  # --- Gate 2: the test-ledger fence must be merged first --------------------
  # Purging while pytest can still write the live ledger just re-accretes the
  # same junk. The fence = repo-root conftest.py exporting
  # CABINET_EVENT_LOG_DIR/CABINET_UNDO_DIR to a session tmp dir (+ the
  # emitter-level PYTEST_CURRENT_TEST redirect). Grepping the conftest for the
  # env-var name is the cheap merged-in-this-checkout proxy.
  if ! grep -q "CABINET_EVENT_LOG_DIR" "$REPO_ROOT/conftest.py" 2>/dev/null; then
    echo "REFUSED: test-ledger fence not found at $REPO_ROOT/conftest.py." >&2
    echo "Merge the conftest fence (lane/ledger-0705) before purging — or the" >&2
    echo "same test rows will leak straight back into the ledger." >&2
    exit 1
  fi
fi

if [ ! -d "$LEDGER_DIR" ]; then
  echo "REFUSED: ledger dir not found: $LEDGER_DIR" >&2
  exit 1
fi

# BOTH contaminated families (2026-07-04 review fix — see header): the two
# globs are disjoint (a basename starts with "events-" or with
# "consequence-events-", never both). Built with a nullglob loop instead of
# concatenating two array expansions because macOS /bin/bash is 3.2, where
# expanding an EMPTY array as "${arr[@]}" under `set -u` aborts with
# "unbound variable" — the loop body simply never runs for an unmatched
# pattern, so a family may be absent (the test fixtures often have only one)
# without tripping the guard.
shopt -s nullglob
LEDGER_FILES=()
for f in "$LEDGER_DIR"/events-*.jsonl "$LEDGER_DIR"/consequence-events-*.jsonl; do
  LEDGER_FILES+=("$f")
done
shopt -u nullglob
if [ "${#LEDGER_FILES[@]}" -eq 0 ]; then
  echo "REFUSED: no events-*.jsonl / consequence-events-*.jsonl files in $LEDGER_DIR — nothing to purge." >&2
  exit 1
fi

BACKUP_DIR=""
if [ "$DRY_RUN" != "1" ]; then
  # --- (a) Backup FIRST, verify completeness before ANY mutation -------------
  # Sibling of the events dir (never inside it — replay() globs the events dir
  # non-recursively, but keeping backups out entirely is the cleaner invariant).
  # Timestamp has 1s resolution — two mutating runs in the same second would
  # otherwise share a BACKUP_DIR and cp would silently OVERWRITE the first
  # (pre-purge) snapshot with post-purge content, destroying the only rollback
  # copy (checkpoint-review finding, 2026-07-04). PID suffix + existence
  # refusal make every run's backup collision-proof.
  TS="$(date -u +%Y%m%d_%H%M%SZ)"
  BACKUP_DIR="$(dirname "$LEDGER_DIR")/ledger-backups/purge-$TS-$$/events"
  if [ -e "$BACKUP_DIR" ]; then
    echo "ABORT: backup dir already exists: $BACKUP_DIR — refusing to" >&2
    echo "overwrite an existing backup. Ledger untouched." >&2
    exit 1
  fi
  mkdir -p "$BACKUP_DIR"
  cp -p "${LEDGER_FILES[@]}" "$BACKUP_DIR/"

  # *.jsonl (not events-*.jsonl) so the verification spans BOTH backed-up
  # families — the cp above copied every file in LEDGER_FILES.
  SRC_ROWS="$(cat "${LEDGER_FILES[@]}" | wc -l | tr -d ' ')"
  BAK_ROWS="$(cat "$BACKUP_DIR"/*.jsonl | wc -l | tr -d ' ')"
  if [ "$SRC_ROWS" != "$BAK_ROWS" ]; then
    echo "ABORT: backup row count ($BAK_ROWS) != source row count ($SRC_ROWS)." >&2
    echo "Ledger untouched. Partial backup left at $BACKUP_DIR for inspection." >&2
    exit 1
  fi
  echo "backup: $SRC_ROWS rows -> $BACKUP_DIR"
fi

# --- (b)+(c) Filter + counts — python3 owns ALL row handling ------------------
# Row content never passes through shell parsing (no injection surface from
# ledger content); kept lines are written back byte-verbatim; each changed
# file is replaced atomically (tempfile in the same dir + os.replace).
LEDGER_DIR="$LEDGER_DIR" PURGE_DRY_RUN="$DRY_RUN" \
  PURGE_INCLUDE_TODAY="${CABINET_PURGE_INCLUDE_TODAY:-0}" python3 - <<'PY'
# NOTE: future-import keeps the X | Y annotations un-evaluated so this runs
# on the system python3 even below 3.10 (recorded gotcha: match the system
# Python, never assume 3.10+ union syntax is available at runtime).
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sys
import tempfile

ledger_dir = os.environ["LEDGER_DIR"]
dry_run = os.environ.get("PURGE_DRY_RUN") == "1"
include_today = os.environ.get("PURGE_INCLUDE_TODAY") == "1"

# Live-append race guard (see script header): the org appends to TODAY'S
# file in BOTH families while we run (hooks -> events-*, fidelity harness ->
# consequence-events-*); rewriting an active file could clobber a fresh row
# that is in neither the rewrite nor the backup. Skip them unless the
# operator asserts the org is quiesced (CABINET_PURGE_INCLUDE_TODAY=1).
_today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
today_basenames = {
    "events-{}.jsonl".format(_today),
    "consequence-events-{}.jsonl".format(_today),
}

# Criterion 1 — fidelity test-fixture rows (the pytest leak):
# exact subject match on the fixture case id, keyed PER FAMILY — the org
# family carries it at payload.subject; the consequence family carries it at
# the TOP level (framework/fidelity/consequence.py schema). This catches
# every row the leaking suites dual-emitted; genuine fidelity rows carry
# real case ids, never the fixture literal.
FIXTURE_SUBJECT = "abc1234567"

# Criterion 2 — junk subagent completions:
# on-subagent-stop.sh stamps completed_by=="subagent" on every row it emits
# (both payload branches). A completion is GENUINE work-graph signal only
# when it carries a real FW-*/PROD-* task ref; everything else from that
# hook is generic helper-agent noise. (Framework-emitted work_item_completed
# rows — e.g. mission supervisor — never carry completed_by=="subagent" and
# are untouched by construction.)
GENUINE_REF = re.compile(r"^(FW|PROD)-[0-9]+$")


def classify(event: dict, family: str) -> str | None:
    """Return the junk criterion this row matches, or None to keep it.

    family is "org" (events-*.jsonl) or "consequence"
    (consequence-events-*.jsonl) — the criteria are deliberately DISJOINT per
    family so neither can over-match the other's shapes:
      * consequence rows are junk ONLY on the top-level fixture subject
        (criterion 2 is an org-event shape; a consequence row that merely
        mentions completed_by/"work_item_completed" text is kept);
      * org rows are junk on payload.subject (criterion 1) or the junk
        subagent-completion shape (criterion 2).
    """
    if family == "consequence":
        if event.get("subject") == FIXTURE_SUBJECT:
            return "conseq_fixture"
        return None  # fail-safe: no other criterion applies to this family
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None  # unknown shape -> fail-safe: keep
    if payload.get("subject") == FIXTURE_SUBJECT:
        return "fixture"
    if (
        event.get("event_type") == "work_item_completed"
        and payload.get("completed_by") == "subagent"
        and not GENUINE_REF.match(str(payload.get("task_ref") or ""))
    ):
        return "subagent"
    return None


total_before = 0
total_after = 0
dropped = {"fixture": 0, "subagent": 0, "conseq_fixture": 0}
unparseable = 0
files_changed = 0
skipped_today = []  # (basename, junk_count) per skipped active file (≤1 per family)

# Disjoint globs (basename anchors differ) — sorted per family, org family
# first, so output ordering is deterministic for the operator and the tests.
_paths = sorted(glob.glob(os.path.join(ledger_dir, "events-*.jsonl"))) + sorted(
    glob.glob(os.path.join(ledger_dir, "consequence-events-*.jsonl"))
)

for path in _paths:
    basename = os.path.basename(path)
    family = "consequence" if basename.startswith("consequence-events-") else "org"
    is_active_today = basename in today_basenames and not include_today
    if is_active_today:
        # Count-only pass: report the junk waiting here, but drop NOTHING and
        # never rewrite the file the live org is appending to.
        junk_here = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                total_before += 1
                total_after += 1  # nothing is dropped from the active file
                try:
                    event = json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    unparseable += 1
                    continue
                if not isinstance(event, dict):
                    unparseable += 1  # valid JSON, not an object — fail-safe: keep
                    continue
                if classify(event, family):
                    junk_here += 1
        skipped_today.append((basename, junk_here))
        continue

    kept_lines: list[str] = []
    file_dropped = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                kept_lines.append(line)  # preserve blanks verbatim
                continue
            total_before += 1
            try:
                event = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                unparseable += 1
                kept_lines.append(line)  # fail-safe: never drop unparseable
                total_after += 1
                continue
            if not isinstance(event, dict):
                # Valid JSON but not an object (bare array/number/string) —
                # cannot be positively identified as junk, so it takes the
                # same fail-safe path as an unparseable line (byte-verbatim
                # keep + counted). Mirrors purge-sqlite-mirror.py::find_junk;
                # without this guard classify() crashed with AttributeError
                # mid-iteration (regression test pins it).
                unparseable += 1
                kept_lines.append(line)  # byte-verbatim keep
                total_after += 1
                continue
            criterion = classify(event, family)
            if criterion:
                dropped[criterion] += 1
                file_dropped += 1
            else:
                kept_lines.append(line)  # byte-verbatim keep
                total_after += 1

    if file_dropped and not dry_run:
        # Atomic replace: same-dir tempfile + os.replace so a crash mid-write
        # can never leave a truncated ledger file behind. The dot-prefixed
        # temp name never matches replay()'s events-*.jsonl glob, so even a
        # crashed remnant can't be read as ledger.
        original_mode = os.stat(path).st_mode & 0o7777
        fd, tmp_path = tempfile.mkstemp(
            prefix=".purge-tmp-", dir=os.path.dirname(path)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.writelines(kept_lines)
            # mkstemp creates 0600 — restore the original mode so ledger
            # readability doesn't silently change after a purge.
            os.chmod(tmp_path, original_mode)
            os.replace(tmp_path, path)
        except BaseException:
            # Leave the original untouched; remove the temp remnant.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    if file_dropped:
        files_changed += 1
        print(
            f"{'would rewrite' if dry_run else 'rewrote'}: "
            f"{basename} (-{file_dropped} rows)"
        )

# One guard line PER skipped active file (at most one per family), so the
# operator sees exactly what junk is deferred in each.
for skipped_name, junk_count in skipped_today:
    print(
        f"skipped (active today-file, live-append race guard): "
        f"{skipped_name} — {junk_count} junk rows left for a later "
        f"run (or CABINET_PURGE_INCLUDE_TODAY=1 with the org quiesced)"
    )

mode = "DRY RUN — no files were modified" if dry_run else "PURGE APPLIED"
print(f"--- {mode} ---")
print(f"rows before:            {total_before}")
print(f"dropped (fixture subject=={FIXTURE_SUBJECT!r}): {dropped['fixture']}")
print(f"dropped (junk subagent work_item_completed):  {dropped['subagent']}")
print(f"dropped (consequence fixture subject=={FIXTURE_SUBJECT!r}): {dropped['conseq_fixture']}")
print(f"rows after:             {total_after}")
print(f"files {'needing rewrite' if dry_run else 'rewritten'}: {files_changed}")
if unparseable:
    print(f"unparseable lines preserved (never dropped): {unparseable}")

# Arithmetic self-check — if this ever fails, something in the loop is wrong
# and the operator must inspect before trusting the result.
if total_after + sum(dropped.values()) != total_before:
    print("ERROR: row arithmetic does not balance — inspect before trusting.",
          file=sys.stderr)
    sys.exit(1)
PY

if [ "$DRY_RUN" = "1" ]; then
  echo "dry run complete — re-run with CABINET_PURGE_CONFIRM=1 to apply."
else
  echo "purge complete. rollback: copy files back from $BACKUP_DIR"
  echo "NOTE: the org-runtime SQLite Store mirror (cabinet/cache/org-runtime.sqlite3)"
  echo "holds mirrored junk work_item_completed rows too — run the sibling pass:"
  echo "  CABINET_PURGE_DRY_RUN=1 python3 cabinet/scripts/purge-sqlite-mirror.py   # preview"
  echo "  CABINET_PURGE_CONFIRM=1 python3 cabinet/scripts/purge-sqlite-mirror.py   # apply"
fi
