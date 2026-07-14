#!/usr/bin/env bash
# egg-publish-gate.sh — FAIL-CLOSED pre-publish gate over a fresh-cut egg
# export (PC-C). PRIVATE-SIDE PREP: this script publishes NOTHING and has no
# network capability; it only judges an export directory produced by
# cabinet/scripts/egg-export.sh.
#
# Checks, IN ORDER, each with a PASS/FAIL line (a missing tool is a FAIL,
# never a skip-pass):
#   (a) gitleaks detect over the export tree
#   (b) the export's own null-hatch.sh (Proof 1) run against the export bytes
#   (c) pytest framework/tests/test_no_launcher_hardcode.py inside the export
#   (d) real-value + colleague grep suite over the whole export — ANY hit
#       fails and prints a grouped report; colleague-name hits are the
#       per-person consent items the Captain must clear before any publish.
#       Sole exception: EXACT strings on the ADJUDICATED_ALLOWLIST (each
#       entry cites its ledger CG row) are masked before the pattern
#       re-test — every masked occurrence still prints ([adj] lines), is
#       persisted in the grouped report, and is annotated on the PASS line;
#       any OTHER banned token on the same line still fails. Patterns are
#       never relaxed.
#   (e) verdict: PUBLISH GATE: GREEN/RED
#
# PATTERN SOURCE (R166 — the tracked source carries pattern CLASSES only):
#   * GREP_PATTERNS below holds the GENERIC, captain-agnostic classes
#     (standalone 9+-digit id runs). No real name/employer/product value is
#     tracked in this file.
#   * The captain-SPECIFIC suite (name tokens, employer/product tokens,
#     colleague first names, home-path prefix) + any name-bearing
#     adjudicated-allowlist entries load at runtime from the UNTRACKED
#     per-captain file
#       instance/config/publish-scan-patterns.local
#     (tracked synthetic-placeholder twin: publish-scan-patterns.local.example;
#     gitignored; the egg is cut with `git archive` so an untracked file can
#     never ship). FAIL-CLOSED: a missing patterns file, one carrying no
#     `pattern` directives, or one whose pattern values still appear
#     verbatim among the synthetic template's DIRECTIVE lines (an unedited
#     copy scans for placeholders — a vacuous GREEN; template '#' prose is
#     never matched: real word-class values can sit inside ordinary English
#     words) ABORTS the gate (exit 2) — a publish scan is never vacuous.
#     EGG_GATE_PATTERNS_FILE overrides the location for TESTS ONLY (same
#     trust model as EGG_GATE_GREP).
#
# The grep ENGINE is pinned (EGG_GATE_GREP overrides; default /usr/bin/grep)
# and proven by a planted-sample self-test before any scan: ugrep/busybox
# front-ends match ZERO lines for the word-boundary ERE in (d) — a silent
# FAIL-OPEN — so any pattern kind that cannot fire on its planted sample
# aborts the whole gate (exit 2) instead of scanning blind.
#
# All checks run even after a failure so the Captain gets ONE complete
# report. The export directory itself is never modified (scratch work goes
# to mktemp; pytest runs with bytecode + cache writes disabled).
#
# THIS FILE NEVER SHIPS IN THE EGG (private-side prep — see the
# self-exclusion block in egg-export-manifest.txt). Since R166 it carries no
# real values itself; it stays excluded because the export tooling as a
# whole is private-side prep.
#
# Usage: bash cabinet/scripts/egg-publish-gate.sh --export /path/to/egg
# Exit:  0 = GREEN, 1 = RED, 2 = usage/self-test/pattern-config abort.
#        Publishing remains CG-7 Captain-gated either way.
set -euo pipefail

usage() {
  cat <<'EOF'
egg-publish-gate.sh — fail-closed pre-publish gate over a fresh-cut export

  --export DIR   REQUIRED. An export directory produced by egg-export.sh
                 (must contain egg-manifest.json; must NOT contain .git).
  -h, --help     This help.

Runs: (a) gitleaks  (b) null-hatch  (c) no-launcher-hardcode pytest
      (d) real-value + colleague grep suite  (e) GREEN/RED verdict.
Gate (d)'s captain-specific patterns load from the UNTRACKED
instance/config/publish-scan-patterns.local (template: its .example twin);
a missing or pattern-less file aborts the gate — never a vacuous GREEN.
Publishing remains CG-7 Captain-gated regardless of a GREEN verdict.
EOF
}

fail() { echo "egg-publish-gate: FAIL — $*" >&2; exit 2; }

EXPORT_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --export) [ $# -ge 2 ] || fail "--export needs a value"; EXPORT_ARG="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "egg-publish-gate: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
done
[ -n "$EXPORT_ARG" ] || { echo "egg-publish-gate: --export DIR is required" >&2; usage >&2; exit 2; }
[ -d "$EXPORT_ARG" ] || fail "no such directory: $EXPORT_ARG"
EXPORT="$(cd "$EXPORT_ARG" && pwd -P)"

# gate ONLY fresh cuts: a .git dir means a live checkout (history carries
# personal/employer data — never the artifact); egg-manifest.json proves the
# tree came through egg-export.sh's exclusion/transform pass.
[ ! -e "$EXPORT/.git" ] || fail "$EXPORT contains .git — this is a checkout, not a fresh-cut export; never gate (or publish) a repo flip"
[ -f "$EXPORT/egg-manifest.json" ] || fail "$EXPORT has no egg-manifest.json — produce it with cabinet/scripts/egg-export.sh first"

# interpreter (null-hatch.sh's own resolver pattern; 3.12 preferred)
PY=""
for cand in python3.12 python3; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "no python interpreter found (need python3.12, or python3)"
[ "$PY" = "python3.12" ] || echo "egg-publish-gate: note — python3.12 not found, using $PY"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/egg-gate.XXXXXX")"
cleanup() { chmod -R u+rwX "$WORK" 2>/dev/null || true; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT
# reports OUTLIVE the run (the $WORK sandbox is deleted on exit) but never
# land inside the export — the artifact stays byte-clean
REPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/egg-gate-report.XXXXXX")"

# --- pinned grep engine + planted-sample self-test (fail-closed) ----------------
# Gate (d) is only as good as its grep. Non-BSD/GNU front-ends (ugrep shell
# wrappers, busybox) match ZERO lines for the word-boundary ERE below, which
# would print "[ok] 0 hits" over real residue — fail-open. Pin the engine,
# then PROVE each pattern kind fires on a planted sample before any scan.
# Override for testing only: EGG_GATE_GREP=/path/to/grep.
GREP="${EGG_GATE_GREP:-}"
if [ -z "$GREP" ]; then
  if [ -x /usr/bin/grep ]; then
    GREP=/usr/bin/grep
  else
    GREP="$(command -v grep)" || fail "no grep on PATH (and no /usr/bin/grep)"
  fi
fi

word_re() { printf '(^|[^[:alnum:]_])%s([^[:alnum:]_]|$)' "$1"; }
id_re()   { printf '(^|[^0-9A-Za-z])%s([^0-9A-Za-z]|$)' "$1"; }

# scan_hits KIND PAT TARGET — recursive scan; one "file:line:content" hit per
# output line (empty output = no hits). The single scan path shared by the
# self-test below and gate (d), so the self-test proves the real pipeline.
scan_hits() {
  case "$1" in
    sub)  "$GREP" -RIni -F -- "$2" "$3" 2>/dev/null || true ;;
    word) "$GREP" -RIniE -- "$(word_re "$2")" "$3" 2>/dev/null || true ;;
    id)   "$GREP" -RInE  -- "$(id_re "$2")" "$3" 2>/dev/null || true ;;
  esac
}

# rematches KIND PAT TEXT — exit 0 iff TEXT still matches PAT (same engine,
# same match semantics as scan_hits; used for the post-mask re-test)
rematches() {
  case "$1" in
    sub)  printf '%s\n' "$3" | "$GREP" -qiF -- "$2" ;;
    word) printf '%s\n' "$3" | "$GREP" -qiE -- "$(word_re "$2")" ;;
    id)   printf '%s\n' "$3" | "$GREP" -qE  -- "$(id_re "$2")" ;;
  esac
}

# planted samples: each kind MUST fire exactly once — an engine that
# under-matches (ugrep: 0 word hits) OR over-matches (plain-substring: the
# embedded negative line would fire the word probe) fails the gate before
# any scan runs. Probe tokens are SYNTHETIC (R166: no real name may appear
# in this tracked source — engine semantics are token-agnostic).
# Runtime-only fixture; deleted with $WORK on exit.
SELFTEST_DIR="$WORK/grep-selftest"
mkdir -p "$SELFTEST_DIR"
printf '%s\n' \
  'planted sub sample: xqzsubprobex' \
  'planted word sample: qzwordprobe bounded here' \
  'planted word negative: embeddedqzwordprobetoken' \
  'planted id sample: 501234567890 standalone' \
  > "$SELFTEST_DIR/planted.txt"
ST_SUB="$(scan_hits sub qzsubprobe "$SELFTEST_DIR" | wc -l | tr -d ' ')"
ST_WORD="$(scan_hits word qzwordprobe "$SELFTEST_DIR" | wc -l | tr -d ' ')"
ST_ID="$(scan_hits id '[0-9]{9,}' "$SELFTEST_DIR" | wc -l | tr -d ' ')"
if [ "$ST_SUB" != "1" ] || [ "$ST_WORD" != "1" ] || [ "$ST_ID" != "1" ]; then
  fail "grep engine self-test failed (sub=$ST_SUB word=$ST_WORD id=$ST_ID, expected 1/1/1; GREP=$GREP) — this engine would scan fail-open or over-match; point EGG_GATE_GREP at a BSD/GNU grep"
fi

# --- gate (d) pattern suite (fail-closed load; R166) ------------------------------
# Kind semantics (mirroring the authoritative fixture leak audit in
# cabinet/scripts/tests/test_testburg_fixture.py — its BANNED_PATTERNS list
# is the plain-substring twin of this suite):
#   sub:  case-insensitive substring (distinctive tokens)
#   word: case-insensitive word-boundary (name tokens that are common English
#         substrings — an embedded participle must not drown the report). A
#         separate word:<name>s pattern covers hostname-shaped possessives
#         ('<Name>s-MacBook-Pro') that the bare word boundary deliberately
#         skips; embedded English stays ignored by the boundary.
#   id:   chat/board-id-shaped standalone decimal runs — 9+ digits,
#         UNBOUNDED like the authoritative _DIGIT_RUN guard (telegram
#         supergroup/channel ids are 13-digit runs; an upper bound is
#         fail-open for exactly that class). Boundaries exclude digits
#         embedded in hashes/hex. Epoch-millis and placeholder-id test
#         fixtures WILL hit: reword them at the source (underscored numeric
#         literals, shorter fakes) or adjudicate the exact string — never
#         relax the pattern.
#
# TRACKED patterns = GENERIC CLASSES ONLY (captain-agnostic, safe to ship).
# The line format below is a CONTRACT: cabinet-feedback.sh extracts it with
# sed 's/^GREP_PATTERNS="\(.*\)"$/\1/p' — keep it one line, double-quoted.
GREP_PATTERNS="id:[0-9]{9,}"

# Captain-specific patterns + name-bearing adjudications: UNTRACKED file.
PATTERNS_FILE_DEFAULT="instance/config/publish-scan-patterns.local"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
PATTERNS_FILE="${EGG_GATE_PATTERNS_FILE:-$ROOT/$PATTERNS_FILE_DEFAULT}"

# --- adjudicated allowlist (RECORDED decision — never a silent pattern relax) ---
# EXACT strings masked out of hit content before a pattern re-test. An entry
# exists ONLY with a recorded adjudication row in
# docs/plans/operative-egg-ledger-2026-07-07.yml (lane captain-gated: the
# Captain ratifies or strikes it at the CG-7 publish review — publishing
# stays CG-7-blocked regardless of a GREEN verdict). Masked occurrences
# ALWAYS print ([adj] lines), land in the grouped report, and annotate the
# PASS line; any OTHER banned token on the same line still fails.
# TRACKED entries below are the two GENERIC all-zero constants only (they
# carry no personal value). Name-bearing adjudications — the CG-19 canonical
# install coordinate and the CG-20 authorship surname token at this
# deployment — are `allow <ROW> <string>` directives in the untracked
# patterns file (R166), each still requiring its recorded ledger row.
# Entry 1 — ledger row CG-21: git's canonical null object id (40 zeros), an
# intended PUBLIC CONSTANT in cabinet/scripts/git-hooks/pre-push (delete-ref
# detection) + cabinet/scripts/test-pre-push-hook.sh, both of which ship.
# Fixed-value mask: it can never hide a real chat/board id.
# Entry 2 — ledger row CG-22: the nil-UUID placeholder PREFIX (34 chars,
# through the fourth group + ten zeros) carried by the 19 all-zero
# sequential placeholder ids in cabinet/dashboard/src/lib/config.ts
# ('00000000-0000-0000-0000-0000000000NN') — synthetic by construction,
# same all-zero-constant class as CG-21. The dashes make the string
# impossible inside a real digit-run id, so the mask can never hide one.
ADJUDICATED_ALLOWLIST=(
  "0000000000000000000000000000000000000000"  # CG-21
  "00000000-0000-0000-0000-0000000000"  # CG-22
)
# ledger row per entry, INDEX-PARALLEL to ADJUDICATED_ALLOWLIST — the [adj]
# console lines + report header derive citations from here, so adding an
# entry adjudicated under a different row can never leave a stale hardcode
ADJUDICATED_ROWS=(
  "CG-21"
  "CG-22"
)

# --- load the captain-specific suite (fail-closed, data-only parse) -------------
# The file is DATA, never sourced: one directive per line —
#   pattern <kind>:<value>          kind in sub|word|id, value non-empty
#   allow <LEDGER-ROW> <string>     adjudicated exact-string mask entry
# '#' comment lines and blank lines are ignored. Anything else aborts,
# naming file:LINE-NUMBER only (never the content — a malformed line may
# carry a real value and must not smear into logs or reports).
[ -f "$PATTERNS_FILE" ] || fail "no captain-specific scan patterns configured — refusing to publish (create $PATTERNS_FILE_DEFAULT from ${PATTERNS_FILE_DEFAULT}.example and replace EVERY placeholder — verbatim template copies are refused; tests may point EGG_GATE_PATTERNS_FILE at a fixture)"

# Template-copy refusal (review fix on R166): an UNEDITED copy of the
# synthetic template satisfies the non-empty check below yet scans for
# placeholders, not real values — a vacuous GREEN. Any pattern value still
# appearing verbatim among a template twin's DIRECTIVE lines (the sibling
# <patterns-file>.example plus the tracked default template) aborts.
# '#' prose is stripped before matching — a real word-class value can sit
# inside an ordinary English word in template prose, and a prose match
# would refuse a correctly seeded live file. The abort names file:LINE and
# the template only — NEVER the value: on a half-edited file the flagged
# value may be a real one and must not smear into logs.
TEMPLATE_TWINS=("${PATTERNS_FILE}.example")
[ "${PATTERNS_FILE}.example" = "$ROOT/${PATTERNS_FILE_DEFAULT}.example" ] \
  || TEMPLATE_TWINS+=("$ROOT/${PATTERNS_FILE_DEFAULT}.example")
TWIN_SRCS=(); TWIN_DATA=(); TWIN_N=0
for tmpl in "${TEMPLATE_TWINS[@]}"; do
  [ -f "$tmpl" ] || continue
  tdata="$WORK/template-twin.$TWIN_N.data"
  "$GREP" -av '^#' -- "$tmpl" > "$tdata" || true  # all-comment twin => empty data
  TWIN_SRCS[$TWIN_N]="$tmpl"; TWIN_DATA[$TWIN_N]="$tdata"
  TWIN_N=$((TWIN_N + 1))
done

SCAN_SPECS=()
for spec in $GREP_PATTERNS; do SCAN_SPECS+=("$spec"); done
LOCAL_PATTERN_N=0
DATA_LINE_N=0
# sanitize a scratch copy once: strip trailing whitespace + CR (CRLF safety)
sed -e 's/[[:space:]]*$//' "$PATTERNS_FILE" > "$WORK/patterns.data"
while IFS= read -r pline || [ -n "$pline" ]; do
  DATA_LINE_N=$((DATA_LINE_N + 1))
  case "$pline" in
    ''|'#'*) continue ;;
    'pattern '*)
      spec="${pline#pattern }"
      case "$spec" in
        sub:?*|word:?*|id:?*)
          pval="${spec#*:}"
          ti=0
          while [ "$ti" -lt "$TWIN_N" ]; do
            if "$GREP" -qaiF -- "$pval" "${TWIN_DATA[$ti]}"; then
              fail "pattern value at $PATTERNS_FILE:$DATA_LINE_N appears verbatim among the synthetic template's directives (${TWIN_SRCS[$ti]}) — an unedited template copy scans for placeholders, not real values; replace EVERY placeholder (the value is withheld from this message by design)"
            fi
            ti=$((ti + 1))
          done
          SCAN_SPECS+=("$spec"); LOCAL_PATTERN_N=$((LOCAL_PATTERN_N + 1)) ;;
        *) fail "unsupported pattern directive at $PATTERNS_FILE:$DATA_LINE_N (format: pattern <sub|word|id>:<value>)" ;;
      esac ;;
    'allow '*)
      arest="${pline#allow }"
      arow="${arest%% *}"
      aentry="${arest#* }"
      if [ -z "$arow" ] || [ -z "$aentry" ] || [ "$arest" = "$arow" ]; then
        fail "malformed allow directive at $PATTERNS_FILE:$DATA_LINE_N (format: allow <LEDGER-ROW> <exact-string>)"
      fi
      ADJUDICATED_ALLOWLIST+=("$aentry")
      ADJUDICATED_ROWS+=("$arow") ;;
    *)
      fail "unrecognized directive at $PATTERNS_FILE:$DATA_LINE_N (directives: pattern | allow; '#' for comments)" ;;
  esac
done < "$WORK/patterns.data"
[ "$LOCAL_PATTERN_N" -ge 1 ] || fail "$PATTERNS_FILE carries no 'pattern' directives — refusing a vacuous publish scan (fill it from ${PATTERNS_FILE_DEFAULT}.example)"

[ "${#ADJUDICATED_ALLOWLIST[@]}" -eq "${#ADJUDICATED_ROWS[@]}" ] \
  || fail "ADJUDICATED_ALLOWLIST/ADJUDICATED_ROWS length mismatch (${#ADJUDICATED_ALLOWLIST[@]} vs ${#ADJUDICATED_ROWS[@]}) — every entry needs its recorded ledger row"
# literal-masking contract: bash ${var//entry/} treats the entry as a glob
# pattern, so entries are constrained to glob-inert characters — fail closed
# on anything else rather than mask approximately. Row ids print into the
# [adj] console lines + report header, so they ride the same charset.
for entry in "${ADJUDICATED_ALLOWLIST[@]}"; do
  case "$entry" in
    *[!A-Za-z0-9./_-]*) fail "allowlist entry outside [A-Za-z0-9./_-] (literal masking contract): $entry" ;;
  esac
done
for row in "${ADJUDICATED_ROWS[@]}"; do
  case "$row" in
    *[!A-Za-z0-9./_-]*) fail "allowlist row id outside [A-Za-z0-9./_-]: $row" ;;
  esac
done

PASS_A=0; PASS_B=0; PASS_C=0; PASS_D=0
line() { printf '%s\n' "-------------------------------------------------------------------------"; }

# --- (a) gitleaks ---------------------------------------------------------------
line
echo "GATE (a) gitleaks secret scan over the export"
if command -v gitleaks >/dev/null 2>&1; then
  # run FROM the export with --source . so finding fingerprints are
  # export-relative (file:rule:line) — matchable by no-git entries in the
  # shipped .gitleaksignore (the commit-prefixed entries only cover git scans)
  if ( cd "$EXPORT" && gitleaks detect --no-git --redact --source . \
         --report-path "$REPORT_DIR/gitleaks-report.json" ); then
    PASS_A=1
    echo "GATE (a) gitleaks ................................. PASS"
  else
    echo "GATE (a) gitleaks ................................. FAIL (leaks found — report: $REPORT_DIR/gitleaks-report.json; findings above)"
  fi
else
  echo "GATE (a) gitleaks ................................. FAIL (binary not installed — fail-closed, never skip)"
  echo "        install: brew install gitleaks   (or a release from github.com/gitleaks/gitleaks)"
fi

# --- (b) null-hatch (Proof 1) over the export bytes -----------------------------
line
echo "GATE (b) null-hatch (Proof 1) against the export tree"
if [ -f "$EXPORT/cabinet/scripts/null-hatch.sh" ]; then
  # null-hatch archives `git HEAD` of the tree it runs from; the export has no
  # .git BY DESIGN, so stage the export bytes into a scratch git sandbox first
  # (throwaway identity, hermetic config — the sandbox is deleted on exit).
  # `git add -f .` is sandbox-only staging of already-exported bytes, so the
  # shipped .gitignore cannot silently drop files from the proof.
  echo "        staging export into scratch git sandbox (null-hatch archives HEAD; the export ships without .git)"
  mkdir -p "$WORK/tree"
  cp -R "$EXPORT/." "$WORK/tree/"
  if ( cd "$WORK/tree" \
       && export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
       && git init -q \
       && git add -f . \
       && git -c user.name=egg-gate -c user.email=egg-gate@localhost \
              -c commit.gpgsign=false commit -qm "egg-gate stage" \
       && PYTHON="$PY" bash cabinet/scripts/null-hatch.sh ); then
    PASS_B=1
    echo "GATE (b) null-hatch ............................... PASS"
  else
    echo "GATE (b) null-hatch ............................... FAIL (Proof 1 does not hold on the export)"
  fi
else
  echo "GATE (b) null-hatch ............................... FAIL (export has no cabinet/scripts/null-hatch.sh)"
fi

# --- (c) no-launcher-hardcode suite inside the export ----------------------------
line
echo "GATE (c) $PY -m pytest framework/tests/test_no_launcher_hardcode.py -q (cwd = export)"
if [ -f "$EXPORT/framework/tests/test_no_launcher_hardcode.py" ]; then
  if ( cd "$EXPORT" \
       && PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest \
            framework/tests/test_no_launcher_hardcode.py -q -p no:cacheprovider ); then
    PASS_C=1
    echo "GATE (c) no-launcher-hardcode ..................... PASS"
  else
    echo "GATE (c) no-launcher-hardcode ..................... FAIL"
  fi
else
  echo "GATE (c) no-launcher-hardcode ..................... FAIL (test file missing from export)"
fi

# --- (d) real-value + colleague grep suite ---------------------------------------
line
echo "GATE (d) real-value + colleague grep suite over the whole export"
echo "        suite: ${#SCAN_SPECS[@]} spec(s) = tracked generic classes + $LOCAL_PATTERN_N captain-specific from the patterns file"

# apply_allowlist KIND PAT MASKFILE — stdin: raw hits (file:line:content).
# Emits hits that still match after exact-string masking; diverts hits fully
# explained by the allowlist to MASKFILE (reported, never silently dropped).
apply_allowlist() {
  local kind="$1" pat="$2" maskfile="$3" hit rest masked entry
  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    rest="${hit#*:}"; rest="${rest#*:}"   # content after "file:line:"
    masked="$rest"
    for entry in "${ADJUDICATED_ALLOWLIST[@]}"; do
      masked="${masked//$entry/[ADJUDICATED]}"
    done
    if [ "$masked" = "$rest" ] || rematches "$kind" "$pat" "$masked"; then
      printf '%s\n' "$hit"
    else
      printf '%s\n' "$hit" >> "$maskfile"
    fi
  done
}

TOTAL_HITS=0
REPORT="$REPORT_DIR/real-value-report.txt"
MASKFILE="$REPORT_DIR/allowlisted-masked.txt"
: > "$REPORT"
: > "$MASKFILE"
for spec in "${SCAN_SPECS[@]}"; do
  kind="${spec%%:*}"
  pat="${spec#*:}"
  raw="$(scan_hits "$kind" "$pat" "$EXPORT")"
  hits=""
  adj_n=0
  if [ -n "$raw" ]; then
    hits="$(printf '%s\n' "$raw" | apply_allowlist "$kind" "$pat" "$MASKFILE")"
    raw_n="$(printf '%s\n' "$raw" | wc -l | tr -d ' ')"
    kept_n=0
    [ -z "$hits" ] || kept_n="$(printf '%s\n' "$hits" | wc -l | tr -d ' ')"
    adj_n=$((raw_n - kept_n))
  fi
  if [ -n "$hits" ]; then
    n="$(printf '%s\n' "$hits" | wc -l | tr -d ' ')"
    TOTAL_HITS=$((TOTAL_HITS + n))
    {
      echo "== pattern ($kind) '$pat' — $n hit(s) =="
      printf '%s\n' "$hits"
      echo
    } >> "$REPORT"
    echo "  [HIT] ($kind) '$pat' — $n hit(s); first 10:"
    # || true + 2>/dev/null: head closing the pipe early must not kill the
    # gate (SIGPIPE) nor smear "printf: write error" over the report
    printf '%s\n' "$hits" 2>/dev/null | head -10 | cut -c1-200 | sed -e 's|^'"$EXPORT"'/|        |' || true
  else
    echo "  [ok ] ($kind) '$pat' — 0 hits"
  fi
  if [ "$adj_n" -gt 0 ]; then
    echo "  [adj] ($kind) '$pat' — $adj_n hit(s) masked by adjudicated allowlist (ledger row(s): ${ADJUDICATED_ROWS[*]}; listed in report)"
  fi
done
MASKED_N="$(wc -l < "$MASKFILE" | tr -d ' ')"
if [ "$MASKED_N" -gt 0 ]; then
  {
    echo "== adjudicated allowlist — $MASKED_N pattern-hit(s) masked, NOT counted as failures =="
    echo "   entries: ${ADJUDICATED_ALLOWLIST[*]} — ledger row(s): ${ADJUDICATED_ROWS[*]}; Captain ratifies or strikes at CG-7"
    cat "$MASKFILE"
    echo
  } >> "$REPORT"
fi
if [ "$TOTAL_HITS" -eq 0 ]; then
  PASS_D=1
  if [ "$MASKED_N" -gt 0 ]; then
    echo "GATE (d) real-value grep suite .................... PASS (0 hits outside the adjudicated allowlist; $MASKED_N masked — see report)"
  else
    echo "GATE (d) real-value grep suite .................... PASS (0 hits)"
  fi
else
  echo "GATE (d) real-value grep suite .................... FAIL ($TOTAL_HITS hit(s))"
  echo "        full grouped report: $REPORT"
  echo "        colleague-name hits are per-person CONSENT items for the Captain:"
  echo "        each needs explicit consent or redaction before any public cut."
fi

# --- (e) verdict ------------------------------------------------------------------
line
FAILED=$(( (1 - PASS_A) + (1 - PASS_B) + (1 - PASS_C) + (1 - PASS_D) ))
if [ "$FAILED" -eq 0 ]; then
  echo "PUBLISH GATE: GREEN (4/4 checks passed)"
else
  echo "PUBLISH GATE: RED ($FAILED/4 checks failed)"
fi
echo "reports: $REPORT_DIR"
echo "publishing remains CG-7 Captain-gated regardless of GREEN"
line
[ "$FAILED" -eq 0 ]
