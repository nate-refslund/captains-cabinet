#!/bin/bash
# ledger-status-parity.sh — mechanical checker for NORTH-STAR gate G5
# (ledger status hygiene). The operative-egg ledger yml is THE execution-state
# surface (plan §9 names it authoritative); the plan-doc tables mirror a
# status cell per row. Drift between the two, out-of-contract status words,
# and silently-stalled in-flight rows were previously caught by review
# discipline only; this script makes all three MECHANICALLY checkable.
#
# WHAT IT CHECKS (all read-only; the only output is its own report lines on
# stdout — it writes no files, touches no network, reads only the doc pair):
#   1. STATUS PARITY: for every ledger id that also has a plan-doc table row
#      (first cell matches the A13 id regex [A-Z][A-Z0-9-]*[0-9-][A-Z0-9-]*),
#      the md row's Status cell must equal the yml row's status. The yml is
#      authoritative (plan §9) — a drift is reported as
#        <id>: md=<x> yml=<y>
#      Tables without a Status column (e.g. the §2/§3 prose tables) are
#      skipped — nothing to compare.
#   2. VOCABULARY: every yml status must be inside the §9 contract set
#        todo | in-flight | done | captain-gated
#      Encoded from docs/plans/operative-egg-plan-2026-07-07.md:331-332
#      ("statuses are `todo | in-flight | done | captain-gated`") — read
#      2026-07-11: the §9 prose legitimizes NO additional statuses, and the
#      yml header comment (line 3) pins the identical set.
#   3. STALENESS: in-flight rows whose last_update is older than 3 days AND
#      whose note carries no parked/parking/deliberate marker — a row nobody
#      owns and nobody parked. Deliberately-parked rows record the word in
#      their note (that IS the marker contract).
#
# OUTPUT: one line per finding, then a summary line:
#   LEDGER_STATUS GREEN (ids=N md_rows=M findings=0)   | exit 0
#   LEDGER_STATUS FINDINGS (n=K ids=N)                 | exit 1
# Usage errors exit 64. A ledger that fails to parse is itself a finding.
#
# FLAGS:
#   --root <dir>   check this tree instead of the repo this script lives in
#                  (test harness hook; expects the docs/plans pair inside)
#
# Style contract: bash 3.2 portable (no mapfile / assoc arrays), set -u,
# clean under `shellcheck -S warning`. Sibling: docs-track-code-sweep.sh
# (G6). Python via the cabinet-doctor.sh interpreter-selection pattern.

set -u

SELF_DIR=$(cd "$(dirname "$0")" && pwd -P) || exit 1
DEFAULT_ROOT=$(cd "$SELF_DIR/../.." && pwd -P) || exit 1

ROOT="$DEFAULT_ROOT"

usage() {
  echo "usage: ledger-status-parity.sh [--root <dir>]" >&2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --root)
      shift
      [ $# -gt 0 ] || { echo "error: --root needs a directory" >&2; exit 64; }
      ROOT=$(cd "$1" 2>/dev/null && pwd -P) || { echo "error: --root not a directory: $1" >&2; exit 64; }
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
  shift
done

LEDGER="$ROOT/docs/plans/operative-egg-ledger-2026-07-07.yml"
PLAN="$ROOT/docs/plans/operative-egg-plan-2026-07-07.md"
[ -f "$LEDGER" ] || { echo "error: ledger not found: $LEDGER" >&2; exit 64; }
[ -f "$PLAN" ]   || { echo "error: plan doc not found: $PLAN" >&2; exit 64; }

# Interpreter selection — same pattern as cabinet-doctor.sh: bare python3
# under launchd is the 3.9 system Python; the framework targets 3.12.
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3

"$PY" - "$LEDGER" "$PLAN" <<'PYEOF'
import datetime
import re
import sys

import yaml

ledger_path, plan_path = sys.argv[1], sys.argv[2]

# §9 contract set — docs/plans/operative-egg-plan-2026-07-07.md:331-332
# ("statuses are `todo | in-flight | done | captain-gated`"); the §9 prose
# legitimizes no additional statuses (read 2026-07-11), and the yml header
# comment (line 3) pins the same four words.
ALLOWED = {"todo", "in-flight", "done", "captain-gated"}

STALE_DAYS = 3
PARKED_RE = re.compile(r"\bpark(ed|ing)?\b|\bdeliberate", re.IGNORECASE)
ID_RE = re.compile(r"^[A-Z][A-Z0-9-]*[0-9-][A-Z0-9-]*$")  # the A13 id shape
SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")              # |---|---| rows
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")  # escaped \| stays inside its cell


def split_cells(stripped):
    """Split a md table row into cells, honoring escaped \\| pipes.

    (WORLD-AESTHETIC-GATE's title carries `--mechanical\\|--full\\|--calibrate`
    — a naive split('|') shifts every later cell and misreads the status.)
    """
    parts = CELL_SPLIT_RE.split(stripped)
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]

findings = []

# ---- load the yml (parse failure is itself a finding — the surface is dead)
try:
    with open(ledger_path) as fh:
        doc = yaml.safe_load(fh)
    entries = doc["entries"]
except Exception as exc:  # noqa: BLE001 — any parse death is the finding
    print(f"LEDGER-PARSE: {ledger_path}: {exc}")
    print("LEDGER_STATUS FINDINGS (n=1 ids=0)")
    sys.exit(1)

yml_status = {}
for e in entries:
    yml_status[str(e.get("id"))] = str(e.get("status"))

# ---- check 2: vocabulary --------------------------------------------------
for e in entries:
    status = str(e.get("status"))
    if status not in ALLOWED:
        findings.append(
            f"{e.get('id')}: status '{status}' not in the §9 set "
            "{todo|in-flight|done|captain-gated}"
        )

# ---- check 3: staleness ---------------------------------------------------
today = datetime.date.today()
for e in entries:
    if str(e.get("status")) != "in-flight":
        continue
    raw = str(e.get("last_update") or "")
    try:
        last = datetime.date.fromisoformat(raw)
    except ValueError:
        findings.append(f"{e.get('id')}: in-flight with unparseable last_update '{raw}'")
        continue
    age = (today - last).days
    if age <= STALE_DAYS:
        continue
    note = str(e.get("note") or "")
    if PARKED_RE.search(note):
        continue
    findings.append(
        f"{e.get('id')}: in-flight stale (last_update={raw}, {age}d old, "
        "no parked/deliberate marker in note)"
    )

# ---- check 1: md status-cell parity ---------------------------------------
with open(plan_path) as fh:
    lines = fh.read().splitlines()

md_rows = 0
status_col = None
for i, line in enumerate(lines):
    stripped = line.strip()
    if not stripped.startswith("|"):
        continue
    if SEP_RE.match(stripped):
        continue
    cells = split_cells(stripped)
    if i + 1 < len(lines) and SEP_RE.match(lines[i + 1]):
        # header row: (re)locate this table's Status column
        status_col = None
        for j, cell in enumerate(cells):
            if cell.lower() == "status":
                status_col = j
        continue
    first = cells[0]
    if not ID_RE.match(first):
        continue
    md_rows += 1
    if first not in yml_status:
        continue  # id coverage is the A13 gate's job, not this checker's
    if status_col is None or status_col >= len(cells):
        continue  # table carries no status cell — nothing to compare
    md = cells[status_col]
    if md != yml_status[first]:
        findings.append(f"{first}: md={md} yml={yml_status[first]}")

# ---- report ----------------------------------------------------------------
for f in findings:
    print(f)
if findings:
    print(f"LEDGER_STATUS FINDINGS (n={len(findings)} ids={len(yml_status)})")
    sys.exit(1)
print(f"LEDGER_STATUS GREEN (ids={len(yml_status)} md_rows={md_rows} findings=0)")
sys.exit(0)
PYEOF
