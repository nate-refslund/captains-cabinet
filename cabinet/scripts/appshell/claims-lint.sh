#!/bin/bash
# claims-lint.sh — forbidden-claims lint for the Hatch app shell (HATCH-APPSHELL-V05, spec 0 + 8).
#
# THE single implementation used by both appshell-gate.sh and
# test_appshell_build.py — no drift. Scans the given files for the eleven
# WORLD-ONBOARDING-V1B bar claims that v0.5 must never make.
#
# Fence rule: MARKDOWN files may quote the forbidden strings solely inside
# ONE block opened by a line matching ```forbidden-claims and closed by ```.
# Fence handling uses the FLAG form of awk (never the /a/,/b/ range form —
# the opening line matches both delimiters and can end the range on line
# one); fenced lines are BLANKED, not deleted, so reported line numbers stay
# true to the original file. Non-markdown files get no fence: the strings
# must not appear at all.
#
# Fence-structure guard (fail-closed; adversarial fix 2026-07-10): a fence
# that is opened but never closed would leave the strip flag set and blank
# every line below it — a silent bypass of the lint. Both malformations are
# therefore violations in their own right (pseudo-id FENCE):
#   - unterminated fence  => violation, AND stripping is DISABLED for that
#     file so nothing below the broken fence escapes the patterns;
#   - more than one fence => violation (the contract allows ONE block/file).
#
# Output: one "file:line: id: matched text" line per violation; any
# violation => exit 1; clean => exit 0. Aggressive by design: false
# positives are fixed by rephrasing or fencing (docs only), never by
# weakening a pattern — fix composition, never thresholds.
#
# Usage: bash cabinet/scripts/appshell/claims-lint.sh FILE|DIR ...
set -euo pipefail

# Deterministic multibyte matching (one pattern carries a UTF-8 comparison sign).
export LC_ALL=en_US.UTF-8

# The eleven patterns (id|ERE), case-insensitive via grep -i. F8 is assembled
# from two pieces so this file never matches its own pattern text.
F8_PAT='/api/'
F8_PAT="${F8_PAT}hatch"
PATTERNS=(
  'F1|zero[- ]terminal'
  'F2|zero[- ](commands|enter|typing)'
  'F3|at most one( native)? admin prompt'
  'F4|(≤|<=?|under|within)[[:space:]]*90[[:space:]]*min(ute)?s?'
  'F5|non[- ]technical captain'
  'F6|never re[- ]?hatch'
  'F7|zero hand[- ]edits'
  "F8|${F8_PAT}"
  'F9|byte[- ]identical'
  'F10|multi[- ]cabinet'
  'F11|(5|five)[- ]minute install'
)

violations=0

scan_file() {
  local f="$1"
  local content entry id pat hits
  local fence_info unterminated fences last_open second_open
  case "$f" in
    *.md|*.MD|*.markdown)
      # Fence-structure guard first (see header): count forbidden-claims
      # fence openings and detect an unterminated one. Ordinary ```lang
      # code blocks never touch the flag (open pattern is exact).
      fence_info="$(awk '/^```forbidden-claims[[:space:]]*$/{f=1; n++; lo=NR; if (n == 2) so=NR; next}
                         f && /^```[[:space:]]*$/{f=0; next}
                         END{print f+0, n+0, lo+0, so+0}' "$f")"
      read -r unterminated fences last_open second_open <<< "$fence_info"
      if [ "$fences" -gt 1 ]; then
        printf '%s:%s: FENCE: more than one forbidden-claims fence (the contract allows ONE block per file)\n' \
          "$f" "$second_open"
        violations=$((violations + 1))
      fi
      if [ "$unterminated" -eq 1 ]; then
        printf '%s:%s: FENCE: unterminated forbidden-claims fence (opened, not closed) — stripping disabled for this file, fail-closed\n' \
          "$f" "$last_open"
        violations=$((violations + 1))
        # Fail-closed: scan the RAW file so nothing below the broken fence
        # (nor inside it) escapes the patterns.
        content="$(cat "$f")"
      else
        # Flag-form fence strip; fenced lines blanked to keep line numbers true.
        content="$(awk '/^```forbidden-claims[[:space:]]*$/{f=1; print ""; next}
                        f && /^```[[:space:]]*$/{f=0; print ""; next}
                        f {print ""; next}
                        {print}' "$f")"
      fi
      ;;
    *)
      content="$(cat "$f")"
      ;;
  esac
  for entry in "${PATTERNS[@]}"; do
    id="${entry%%|*}"
    pat="${entry#*|}"
    hits="$(printf '%s\n' "$content" | grep -inE "$pat" || true)"
    [ -n "$hits" ] || continue
    while IFS= read -r line; do
      printf '%s:%s: %s: %s\n' "$f" "${line%%:*}" "$id" "${line#*:}"
      violations=$((violations + 1))
    done <<< "$hits"
  done
}

[ $# -ge 1 ] || { echo "usage: claims-lint.sh FILE|DIR ..." >&2; exit 2; }
for target in "$@"; do
  if [ -d "$target" ]; then
    while IFS= read -r f; do
      scan_file "$f"
    done < <(find "$target" -type f | sort)
  elif [ -f "$target" ]; then
    scan_file "$target"
  else
    echo "claims-lint: no such file: $target" >&2
    exit 2
  fi
done

if [ "$violations" -gt 0 ]; then
  echo "claims-lint: $violations forbidden-claim violation(s) — rephrase, or fence (markdown docs only); never weaken a pattern." >&2
  exit 1
fi
exit 0
