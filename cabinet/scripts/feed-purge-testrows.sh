#!/bin/bash
# feed-purge-testrows.sh — one-shot, Captain-gated purge of KNOWN-JUNK rows
# from the attention feed journal (feed-*.jsonl). Prepared 2026-07-16 (item
# (d), feed test-isolation leak); REFUSES to mutate anything until BOTH
# gates below hold. Sibling of cabinet/scripts/ledger-purge-testrows.sh
# (the 2026-07-04 events-family purge) — same safety pattern, one family.
# Reversible by design: full dated backup FIRST, verified before any rewrite.
#
# WHAT LEAKED (and why this script exists):
#   framework/acting/tests/test_actfirst_gate.py seeds an expired card with
#   subject "stale ask" and drives run_action_lane.py's card-expiry sweep,
#   which journals the demotion as a first-class feed row (H5, 2026-07-10)
#   via framework/attention/feed.py::append_event. With CABINET_FEED_DIR
#   unset, _feed_dir() falls back to the DURABLE live feed
#   (~/Library/Application Support/cabinet/feed) — so every fixture-less
#   local pytest run of that suite appended one phantom row:
#     {"kind": "demote", "situation_key": "slug:stale-ask",
#      "demote_reason": "card-expiry", ...}
#   124 rows of 545 total at prep time (2026-07-16), accrued 07-09..07-16.
#   Fixed the same day by extending the repo-root conftest.py fence to
#   export CABINET_FEED_DIR — which is exactly why gate 2 requires that
#   fence before purging: purging first just invites the rows back.
#
#   PROOF OF HARM, and a row we deliberately KEEP: on 2026-07-11 the live
#   orchestrator-triage saw the phantom situation as real and closed it
#   ({"kind": "closure", "situation_key": "slug:stale-ask",
#     "source": "orchestrator-triage", ...}). That closure was written by
#   the RUNNING SYSTEM, not a test — it is genuine ledger history (and the
#   correct terminal state for the phantom), so the criterion below never
#   matches it. Only rows the tests themselves wrote are removed.
#
# CRITERION (exact triple — fail-safe, nothing broader):
#   kind == "demote" AND situation_key == "slug:stale-ask"
#   AND demote_reason == "card-expiry"
#   "stale ask" is test-only vocabulary (sole occurrence in the tree is the
#   fixture at framework/acting/tests/test_actfirst_gate.py); genuine
#   demotes for cards with canonical refs carry hashed sit-* keys. Residual
#   over-match window (accepted, backup-recoverable): a genuinely ref-less
#   card whose subject slugifies to "stale-ask" would match — the 2026-07-16
#   live sweep found zero such rows (all 124 matches fixture-shaped, all 14
#   genuine demotes sit-*-keyed).
#
# GATES for a mutating run (both required — fail-safe):
#   1. CABINET_PURGE_CONFIRM=1      — the Captain's explicit go signal.
#   2. Repo-root conftest.py fence  — merged + present in this checkout
#      (grep for CABINET_FEED_DIR); purging before the fence exists just
#      invites the same rows back.
#
# MODES:
#   Preview (read-only, no gates — writes NOTHING, for the go/no-go call):
#     CABINET_PURGE_DRY_RUN=1 bash cabinet/scripts/feed-purge-testrows.sh
#   Real run (Captain-gated):
#     CABINET_PURGE_CONFIRM=1 bash cabinet/scripts/feed-purge-testrows.sh
#
# FEED LOCATION: CABINET_FEED_DIR overrides (same contract as
# framework/attention/feed.py::_feed_dir) — this is how the test suite
# (cabinet/scripts/tests/test_feed_purge_testrows.py) exercises the script
# against a temp fixture without ever touching the live feed. Default is
# the durable live location.
#
# WHY DROPPING ROWS IS SAFE FOR READERS: feed reads are BY SEQ, never by
# file/line order, and every consumer carries its own durable cursor
# (cursors/<id>.txt = last-consumed seq). A purged row is indistinguishable
# from a burned seq, which the read path already tolerates by design
# (feed.py module docstring). seq.txt and cursors/ are backed up but NEVER
# modified — seqs are never renumbered, so cursor state stays exact.
#
# LIVE-APPEND RACE GUARD (two layers):
#   * The rewrite SKIPS the current UTC day's file by default (the running
#     org appends there); its junk is caught by a later run, or set
#     CABINET_PURGE_INCLUDE_TODAY=1 for a run with the org quiesced.
#   * Belt-and-braces the feed family affords: every append serializes on
#     an exclusive flock of FEED_DIR/seq.txt (feed.py holds it across
#     allocate+write), so a mutating run takes that same flock for the
#     whole backup+rewrite window — even a mid-purge append can only land
#     before or after, never interleave. (Dry runs take no lock and create
#     nothing.)
#
# Kept rows are preserved BYTE-VERBATIM (no re-serialization); unparseable
# lines are never dropped (fail-safe: we only remove what we can positively
# identify as junk); each changed file is replaced atomically.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Same resolution contract as framework/attention/feed.py::_feed_dir()
FEED_DIR="${CABINET_FEED_DIR:-$HOME/Library/Application Support/cabinet/feed}"

DRY_RUN="${CABINET_PURGE_DRY_RUN:-0}"

if [ "$DRY_RUN" != "1" ]; then
  # --- Gate 1: Captain go/no-go ----------------------------------------------
  if [ "${CABINET_PURGE_CONFIRM:-}" != "1" ]; then
    echo "REFUSED: CABINET_PURGE_CONFIRM=1 not set (Captain go/no-go gate)." >&2
    echo "This purge rewrites the attention feed journal (backup-first, but" >&2
    echo "still Captain-gated). Preview first:" >&2
    echo "  CABINET_PURGE_DRY_RUN=1 bash $0" >&2
    echo "Then run for real:" >&2
    echo "  CABINET_PURGE_CONFIRM=1 bash $0" >&2
    exit 1
  fi

  # --- Gate 2: the feed fence must be merged first ----------------------------
  # Purging while pytest can still write the live feed just re-accretes the
  # same junk. The fence = repo-root conftest.py exporting CABINET_FEED_DIR
  # to a session tmp dir. Grepping the conftest for the env-var name is the
  # cheap merged-in-this-checkout proxy (same idiom as the events purge).
  if ! grep -q "CABINET_FEED_DIR" "$REPO_ROOT/conftest.py" 2>/dev/null; then
    echo "REFUSED: feed test fence not found at $REPO_ROOT/conftest.py." >&2
    echo "Merge the conftest CABINET_FEED_DIR fence before purging — or the" >&2
    echo "same test rows will leak straight back into the feed." >&2
    exit 1
  fi
fi

if [ ! -d "$FEED_DIR" ]; then
  echo "REFUSED: feed dir not found: $FEED_DIR" >&2
  exit 1
fi

# nullglob loop, not array expansion — macOS /bin/bash is 3.2, where
# expanding an EMPTY array as "${arr[@]}" under `set -u` aborts (same
# recorded gotcha as the events purge).
shopt -s nullglob
FEED_FILES=()
for f in "$FEED_DIR"/feed-*.jsonl; do
  FEED_FILES+=("$f")
done
shopt -u nullglob
if [ "${#FEED_FILES[@]}" -eq 0 ]; then
  echo "REFUSED: no feed-*.jsonl files in $FEED_DIR — nothing to purge." >&2
  exit 1
fi

BACKUP_DIR=""
if [ "$DRY_RUN" != "1" ]; then
  # --- Backup FIRST, verify completeness before ANY mutation -----------------
  # Sibling of the feed dir (never inside it — _read_all_rows globs the feed
  # dir non-recursively, but keeping backups out entirely is the cleaner
  # invariant). PID suffix + existence refusal make every run's backup
  # collision-proof (checkpoint-review finding, 2026-07-04, inherited).
  TS="$(date -u +%Y%m%d_%H%M%SZ)"
  BACKUP_DIR="$(dirname "$FEED_DIR")/feed-backups/purge-$TS-$$/feed"
  if [ -e "$BACKUP_DIR" ]; then
    echo "ABORT: backup dir already exists: $BACKUP_DIR — refusing to" >&2
    echo "overwrite an existing backup. Feed untouched." >&2
    exit 1
  fi
  mkdir -p "$BACKUP_DIR"
  cp -p "${FEED_FILES[@]}" "$BACKUP_DIR/"
  # seq.txt + cursors/ ride along for a complete rollback unit (they are
  # never modified by this script — backup is belt-and-braces only).
  [ -f "$FEED_DIR/seq.txt" ] && cp -p "$FEED_DIR/seq.txt" "$BACKUP_DIR/"
  [ -d "$FEED_DIR/cursors" ] && cp -Rp "$FEED_DIR/cursors" "$BACKUP_DIR/"

  SRC_ROWS="$(cat "${FEED_FILES[@]}" | wc -l | tr -d ' ')"
  BAK_ROWS="$(cat "$BACKUP_DIR"/feed-*.jsonl | wc -l | tr -d ' ')"
  if [ "$SRC_ROWS" != "$BAK_ROWS" ]; then
    echo "ABORT: backup row count ($BAK_ROWS) != source row count ($SRC_ROWS)." >&2
    echo "Feed untouched. Partial backup left at $BACKUP_DIR for inspection." >&2
    exit 1
  fi
  echo "backup: $SRC_ROWS rows -> $BACKUP_DIR"
fi

# --- Filter + counts — python3 owns ALL row handling --------------------------
# Row content never passes through shell parsing (no injection surface from
# feed content); kept lines are written back byte-verbatim; each changed
# file is replaced atomically (tempfile in the same dir + os.replace).
FEED_DIR="$FEED_DIR" PURGE_DRY_RUN="$DRY_RUN" \
  PURGE_INCLUDE_TODAY="${CABINET_PURGE_INCLUDE_TODAY:-0}" python3 - <<'PY'
# NOTE: future-import keeps annotations un-evaluated so this runs on the
# system python3 even below 3.10 (recorded gotcha: match the system Python).
from __future__ import annotations

import datetime
import fcntl
import glob
import json
import os
import sys
import tempfile

feed_dir = os.environ["FEED_DIR"]
dry_run = os.environ.get("PURGE_DRY_RUN") == "1"
include_today = os.environ.get("PURGE_INCLUDE_TODAY") == "1"

# Live-append race guard layer 1 (see script header): skip the file the
# running org is appending to unless the operator asserts a quiesce.
_today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
today_basename = "feed-{}.jsonl".format(_today)

# Layer 2: for mutating runs, hold the SAME exclusive flock feed.py's
# append_event holds across allocate+write (FEED_DIR/seq.txt), so no append
# can interleave with the backup-verified read and the atomic replace.
# Dry runs must not create seq.txt (a dry run writes NOTHING), so the lock
# is taken only when mutating — by which point seq.txt exists in any feed
# that has ever been appended to (and O_CREAT is harmless if not).
lock_fd = None
if not dry_run:
    lock_fd = os.open(os.path.join(feed_dir, "seq.txt"),
                      os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)


def is_junk(row: dict) -> bool:
    """The exact leaked-fixture triple — nothing broader (fail-safe).

    The 2026-07-11 orchestrator-triage CLOSURE row for the same
    situation_key is kind=="closure" and therefore never matches: it is
    genuine system output (see script header), kept deliberately.
    """
    return (
        row.get("kind") == "demote"
        and row.get("situation_key") == "slug:stale-ask"
        and row.get("demote_reason") == "card-expiry"
    )


total_before = 0
total_after = 0
dropped = 0
unparseable = 0
files_changed = 0
skipped_today = []  # (basename, junk_count)

for path in sorted(glob.glob(os.path.join(feed_dir, "feed-*.jsonl"))):
    basename = os.path.basename(path)
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    total_before += len(lines)

    if basename == today_basename and not include_today:
        junk_here = 0
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and is_junk(row):
                junk_here += 1
        total_after += len(lines)
        if junk_here:
            skipped_today.append((basename, junk_here))
        continue

    kept_lines = []
    file_dropped = 0
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            # Unparseable -> fail-safe keep + counted (mirrors the events
            # purge; the feed read path skips garbage lines by design).
            unparseable += 1
            kept_lines.append(line)  # byte-verbatim keep
            total_after += 1
            continue
        if not isinstance(row, dict):
            # Valid JSON but not a row object (e.g. a bare list) — same
            # fail-safe keep, and COUNTED so the operator sees it (parity
            # with the events purge's non-dict handling).
            unparseable += 1
            kept_lines.append(line)  # byte-verbatim keep
            total_after += 1
            continue
        if is_junk(row):
            dropped += 1
            file_dropped += 1
        else:
            kept_lines.append(line)  # byte-verbatim keep
            total_after += 1

    if file_dropped and not dry_run:
        # Atomic replace: same-dir tempfile + os.replace so a crash
        # mid-write can never leave a truncated feed file behind. The
        # dot-prefixed temp name never matches _read_all_rows()'s
        # feed-*.jsonl glob, so even a crashed remnant can't be read as
        # feed.
        original_mode = os.stat(path).st_mode & 0o7777
        fd, tmp_path = tempfile.mkstemp(
            prefix=".purge-tmp-", dir=os.path.dirname(path)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.writelines(kept_lines)
            # mkstemp creates 0600 — restore the original mode so feed
            # readability doesn't silently change after a purge.
            os.chmod(tmp_path, original_mode)
            os.replace(tmp_path, path)
        except BaseException:
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

for skipped_name, junk_count in skipped_today:
    print(
        f"skipped (active today-file, live-append race guard): "
        f"{skipped_name} — {junk_count} junk rows left for a later "
        f"run (or CABINET_PURGE_INCLUDE_TODAY=1 with the org quiesced)"
    )

mode = "DRY RUN — no files were modified" if dry_run else "PURGE APPLIED"
print(f"--- {mode} ---")
print(f"rows before:            {total_before}")
print(f"dropped (demote/slug:stale-ask/card-expiry): {dropped}")
print(f"rows after:             {total_after}")
print(f"files {'needing rewrite' if dry_run else 'rewritten'}: {files_changed}")
if unparseable:
    print(f"unparseable lines preserved (never dropped): {unparseable}")

# Arithmetic self-check — if this ever fails, something in the loop is wrong
# and the operator must inspect before trusting the result.
if total_after + dropped != total_before:
    print("ERROR: row arithmetic does not balance — inspect before trusting.",
          file=sys.stderr)
    sys.exit(1)

if lock_fd is not None:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
PY

if [ "$DRY_RUN" = "1" ]; then
  echo "dry run complete — re-run with CABINET_PURGE_CONFIRM=1 to apply."
else
  echo "purge complete. rollback: copy files back from $BACKUP_DIR"
  echo "(seq.txt and cursors/ were backed up but never modified — feed reads"
  echo "are by seq, so purged rows are indistinguishable from burned seqs.)"
fi
