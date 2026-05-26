#!/usr/bin/env bash
# check-layer-separation.sh — FINAL-C CI gate enforcing three-layer Cabinet
# dependency direction:
#
#   framework/  →  cannot reference  instance/  or  presets/
#   presets/    →  cannot import code from  instance/  (path-string overlay refs OK)
#   instance/   →  may reference anything
#
# This script is a **baseline-ratchet** gate, not a hard-fail. It captures
# today's known violations in `.layer-separation-baseline` (tracked in git).
# CI exits 0 when the live violation set is a subset of the baseline, and
# exits 1 when a new violation is detected that is not in the baseline.
# The baseline can only shrink, never grow — file deletions / cleanups can
# update it via `--update-baseline`, but additions must be reviewed.
#
# Detection rules (Python files only; .md / .yml / docstrings excluded):
#
#   framework/**/*.py
#     - `import instance` / `from instance ...` / `import presets` /
#       `from presets ...`  →  HARD violation (cannot exist in valid Python
#       anyway; included for defense-in-depth).
#     - String literals `"instance"` or `'instance'` or `"presets"` /
#       `'presets'` used in `Path(...) / "instance" / ...` style runtime
#       coupling  →  violation.
#
#   presets/**/*.py
#     - `import instance` / `from instance ...`  →  violation.
#     - String literal `"instance"` path components in `Path(...) / "instance"`
#       constructions are ALLOWED (overlay convention — presets can describe
#       where instance overlays live without taking a code dep).
#
# Comments (`# ...`), CLI help strings, and docstring text are excluded by
# checking that the offending token is not within a `#` comment or inside a
# triple-quoted block. We approximate the latter cheaply by ignoring lines
# whose stripped-content begins or ends with `"""`/`'''`.
#
# Usage:
#   bash cabinet/scripts/check-layer-separation.sh            # CI mode: exit 1 on new
#   bash cabinet/scripts/check-layer-separation.sh --report   # print all violations, exit 0
#   bash cabinet/scripts/check-layer-separation.sh --update-baseline
#                                                             # rewrite baseline to current set
#
# The baseline file format is one violation per line:
#   <path>:<rule_id>
# where <rule_id> is one of:
#   FRAMEWORK_IMPORTS_INSTANCE, FRAMEWORK_IMPORTS_PRESETS,
#   FRAMEWORK_PATH_INSTANCE,    FRAMEWORK_PATH_PRESETS,
#   PRESETS_IMPORTS_INSTANCE
# Line numbers are intentionally omitted so trivial file edits don't churn
# the baseline. The CI signal is "this file violates this rule" — once.

set -u
set -o pipefail

# Resolve repo root (this script lives at cabinet/scripts/).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BASELINE_FILE="${REPO_ROOT}/.layer-separation-baseline"

MODE="check"
case "${1:-}" in
  --report) MODE="report" ;;
  --update-baseline) MODE="update" ;;
  --help|-h)
    sed -n '2,40p' "$0"
    exit 0
    ;;
  "") ;;
  *)
    echo "[layer-sep] unknown arg: $1" >&2
    exit 2
    ;;
esac

# Collect violations into a sorted, deduped list of "path:rule_id".
# We scan with grep -nE and post-filter in awk to:
#   1) drop lines whose leading non-space character is `#`
#   2) drop lines that look like docstring delimiters
#   3) emit "path:rule_id" (line number stripped for stable baselines)
collect_violations() {
  local out
  out="$(mktemp)"

  # Run greps from inside REPO_ROOT so paths come out repo-relative.
  # That keeps the baseline portable across worktrees / CI checkouts.
  cd "$REPO_ROOT" || { rm -f "$out"; return 1; }

  # Rule: framework imports
  if [ -d "framework" ]; then
    grep -rnE '^[[:space:]]*(import|from)[[:space:]]+instance([[:space:]\.]|$)' \
         framework --include="*.py" 2>/dev/null \
      | awk -F: '{ path=$1; sub(/^[[:space:]]*/, "", $3); if ($3 !~ /^#/) print path ":FRAMEWORK_IMPORTS_INSTANCE" }' \
      >> "$out"

    grep -rnE '^[[:space:]]*(import|from)[[:space:]]+presets([[:space:]\.]|$)' \
         framework --include="*.py" 2>/dev/null \
      | awk -F: '{ path=$1; sub(/^[[:space:]]*/, "", $3); if ($3 !~ /^#/) print path ":FRAMEWORK_IMPORTS_PRESETS" }' \
      >> "$out"

    # Rule: framework path-string coupling. We look for the literal quoted
    # token "instance" or 'instance' (and same for "presets") and only count
    # it when the line is NOT a comment AND NOT a CLI help string AND NOT a
    # docstring delimiter line. We rely on the cheap heuristic that runtime
    # coupling uses Path(...) / "instance" / ... — these appear at code
    # indentation, not inside triple-quoted blocks. Comments in tests + help
    # strings are filtered by the awk pass.
    grep -rnE "(\"instance\"|'instance')" \
         framework --include="*.py" 2>/dev/null \
      | awk -F: '{
          path=$1;
          # Reconstruct the source line (fields 3..NF) — F:N: split eats colons
          src="";
          for (i=3; i<=NF; i++) { src = (i==3 ? $i : src ":" $i) }
          stripped=src; sub(/^[[:space:]]+/, "", stripped);
          # Exclude pure comment lines and likely-docstring lines
          if (stripped ~ /^#/) next;
          if (stripped ~ /^"""/ || stripped ~ /^'\''\'\''\'\''/) next;
          # Exclude CLI help= strings (argparse) — overlay convention reference
          if (src ~ /help[[:space:]]*=/) next;
          print path ":FRAMEWORK_PATH_INSTANCE";
        }' \
      >> "$out"

    grep -rnE "(\"presets\"|'presets')" \
         framework --include="*.py" 2>/dev/null \
      | awk -F: '{
          path=$1;
          src="";
          for (i=3; i<=NF; i++) { src = (i==3 ? $i : src ":" $i) }
          stripped=src; sub(/^[[:space:]]+/, "", stripped);
          if (stripped ~ /^#/) next;
          if (stripped ~ /^"""/ || stripped ~ /^'\''\'\''\'\''/) next;
          if (src ~ /help[[:space:]]*=/) next;
          print path ":FRAMEWORK_PATH_PRESETS";
        }' \
      >> "$out"
  fi

  # Rule: presets imports of instance (path-string overlays are allowed).
  if [ -d "presets" ]; then
    grep -rnE '^[[:space:]]*(import|from)[[:space:]]+instance([[:space:]\.]|$)' \
         presets --include="*.py" 2>/dev/null \
      | awk -F: '{ path=$1; sub(/^[[:space:]]*/, "", $3); if ($3 !~ /^#/) print path ":PRESETS_IMPORTS_INSTANCE" }' \
      >> "$out"
  fi

  sort -u "$out"
  rm -f "$out"
}

violations="$(collect_violations)"
violation_count=0
if [ -n "$violations" ]; then
  violation_count="$(printf '%s\n' "$violations" | wc -l | tr -d ' ')"
fi

case "$MODE" in
  report)
    if [ -z "$violations" ]; then
      echo "[layer-sep] CLEAN — no cross-layer violations detected."
      exit 0
    fi
    echo "[layer-sep] ${violation_count} violation(s):"
    printf '%s\n' "$violations" | sed 's/^/  /'
    exit 0
    ;;

  update)
    # Rewrite baseline to match current state. Intended for cleanup PRs that
    # remove violations — running this in a PR that ADDS violations would be
    # caught at review (baseline diff is a +N change).
    if [ -z "$violations" ]; then
      : > "$BASELINE_FILE"
      echo "[layer-sep] baseline cleared (0 violations)."
    else
      printf '%s\n' "$violations" > "$BASELINE_FILE"
      echo "[layer-sep] baseline rewritten with ${violation_count} entries → ${BASELINE_FILE}"
    fi
    exit 0
    ;;

  check)
    if [ ! -f "$BASELINE_FILE" ]; then
      echo "[layer-sep] WARNING: ${BASELINE_FILE} missing — treating empty baseline." >&2
      baseline=""
    else
      baseline="$(sort -u "$BASELINE_FILE" | grep -vE '^[[:space:]]*(#|$)' || true)"
    fi

    # New violations = current minus baseline.
    new_violations="$(comm -23 \
      <(printf '%s\n' "$violations") \
      <(printf '%s\n' "$baseline"))"

    # Removed violations = baseline minus current (informational only).
    fixed_violations="$(comm -13 \
      <(printf '%s\n' "$violations") \
      <(printf '%s\n' "$baseline"))"

    new_count=0
    if [ -n "$new_violations" ]; then
      new_count="$(printf '%s\n' "$new_violations" | wc -l | tr -d ' ')"
    fi
    fixed_count=0
    if [ -n "$fixed_violations" ]; then
      fixed_count="$(printf '%s\n' "$fixed_violations" | wc -l | tr -d ' ')"
    fi

    baseline_count=0
    if [ -n "$baseline" ]; then
      baseline_count="$(printf '%s\n' "$baseline" | wc -l | tr -d ' ')"
    fi

    echo "[layer-sep] baseline=${baseline_count}  current=${violation_count}  new=${new_count}  fixed=${fixed_count}"

    if [ "$fixed_count" -gt 0 ]; then
      echo "[layer-sep] FIXED (run --update-baseline to ratchet down):"
      printf '%s\n' "$fixed_violations" | sed 's/^/  - /'
    fi

    if [ "$new_count" -gt 0 ]; then
      echo "[layer-sep] NEW VIOLATIONS (not in baseline):" >&2
      printf '%s\n' "$new_violations" | sed 's/^/  + /' >&2
      echo "[layer-sep] FAIL — layer separation regressed. Either remove the" >&2
      echo "          violation or, if intentional, justify in PR and run" >&2
      echo "          \`bash cabinet/scripts/check-layer-separation.sh --update-baseline\`" >&2
      echo "          (Captain approval required to grow the baseline.)" >&2
      exit 1
    fi

    echo "[layer-sep] OK — no new layer-separation violations."
    exit 0
    ;;
esac
