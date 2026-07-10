#!/usr/bin/env bash
# cabinet-feedback.sh — leak-scrubbed diagnostic bundle → prefilled GitHub
# issue, gated on the USER's explicit consent (Wave E contribution design,
# docs: DESIGN-contribution-donations-2026-07-10).
#
# WHAT IT DOES
#   1. Gathers: cabinet-doctor output (read-only prober; its own exit code is
#      recorded honestly), the newest hatch flight-log tail, and version info.
#   2. Scrubs: EVERY bundle line runs through the leak-scrub pattern suite.
#      Any line matching any pattern is replaced entirely with "[scrubbed]".
#   3. Reviews: prints the FULL redacted bundle to stdout for the user's eyes.
#   4. Posts (optional): opens a prefilled issue on the canonical repo via the
#      user's own `gh` auth — ONLY after an explicit interactive y/N consent.
#      --dry-run stops after (3) and never invokes gh at all.
#
# PATTERN SOURCE (reuse, never fork — scrub doctrine):
#   The suite is the GREP_PATTERNS line of cabinet/scripts/egg-publish-gate.sh,
#   extracted at runtime. FAIL-CLOSED: if the gate file is present but the
#   patterns cannot be extracted, this script refuses to build a bundle.
#   In packaged egg cuts the gate file is deliberately absent (it is
#   private-side prep, excluded by egg-export-manifest.txt); the scrub then
#   honestly announces baseline mode. A BASELINE suite (your $HOME path, your
#   username, email addresses, 9+-digit id runs) is ALWAYS applied in both
#   modes, and your review before consent is the final gate either way.
#   Match semantics mirror the gate's scan_hits/rematches contract (sub =
#   case-insensitive substring, word = case-insensitive word-boundary, id =
#   standalone digit-run) and are PROVEN by a planted-sample self-test before
#   any scan — a grep front-end that cannot fire aborts the run (never scans
#   blind). Samples are constructed at runtime from the loaded suite; no real
#   value appears in this file.
#
# CONSENT / PRIVACY CONTRACT (CG-7 discipline):
#   * Zero phone-home: no network of its own; the ONLY egress is `gh issue
#     create`, run with a fixed argv, after the consent prompt.
#   * Never posts non-interactively: stdin must be a TTY; piped "y" is refused.
#   * --dry-run never invokes gh — not even `gh auth status`.
#   * Honest failures: gh missing and gh unauthenticated each name themselves.
#
# SETUP NOTE: posting uses --label cabinet-feedback; the label must exist on
# the canonical repo (publication-day errand) or gh will fail honestly.
#
# Env seams (names-in-env doctrine; primarily for tests):
#   CABINET_FEEDBACK_ROOT   repo root override (default: two dirs above $0)
#   CABINET_FEEDBACK_GREP   grep engine override (default /usr/bin/grep —
#                           same pinning rationale as the publish gate)
#   HOME                    flight logs are discovered under $HOME/hatch-logs
#
# Usage: bash cabinet/scripts/cabinet-feedback.sh [--dry-run] [--title TEXT]
# Exit:  0 = posted (or dry-run complete); 1 = refused/aborted/honest failure;
#        2 = usage / fail-closed scrub error.
set -euo pipefail

usage() {
  cat <<'EOF'
cabinet-feedback.sh — leak-scrubbed diagnostic bundle -> prefilled GitHub issue

  --dry-run      build + scrub + print the bundle and the would-be gh argv,
                 then exit WITHOUT invoking gh (not even auth checks)
  --title TEXT   issue title (default: "cabinet-feedback: diagnostic bundle
                 (<UTC date>)"); the title is scrub-checked too
  -h, --help     this help

Nothing is ever posted without an explicit interactive y/N consent.
EOF
}

die()  { echo "cabinet-feedback: $*" >&2; exit 2; }
bail() { echo "cabinet-feedback: $*" >&2; exit 1; }

DRY_RUN=0
TITLE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --title)   [ $# -ge 2 ] || die "--title needs a value"; TITLE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "cabinet-feedback: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
done
[ -n "$TITLE" ] || TITLE="cabinet-feedback: diagnostic bundle ($(date -u +%Y-%m-%d))"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="${CABINET_FEEDBACK_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd -P)}"
[ -d "$ROOT" ] || die "root not found: $ROOT"

# The canonical public repo — CG-19 adjudicated install coordinate (the exact
# string on the publish gate's ADJUDICATED_ALLOWLIST; never split or reword).
CANONICAL_REPO="nate-refslund/captains-cabinet"
ISSUE_LABEL="cabinet-feedback"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cabinet-feedback.XXXXXX")"
cleanup() { rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

# --- pinned grep engine (the publish gate's rationale: ugrep/busybox ---------
# front-ends under-match the word-boundary ERE — a silent fail-open) ----------
GREP="${CABINET_FEEDBACK_GREP:-}"
if [ -z "$GREP" ]; then
  if [ -x /usr/bin/grep ]; then
    GREP=/usr/bin/grep
  else
    GREP="$(command -v grep)" || die "no grep on PATH (and no /usr/bin/grep)"
  fi
fi

# Match-semantics twins of egg-publish-gate.sh (word_re/id_re) — the pattern
# LIST is never duplicated (extracted below); these builders are proven
# against it by the planted-sample self-test before any scan.
word_re() { printf '(^|[^[:alnum:]_])%s([^[:alnum:]_]|$)' "$1"; }
id_re()   { printf '(^|[^0-9A-Za-z])%s([^0-9A-Za-z]|$)' "$1"; }

# match_args KIND PAT — sets MATCH_FLAGS/MATCH_PAT: the ONE place the grep
# flag choice + effective pattern per kind lives (gate rematches shape, plus
# a local 'ere' kind used only by the baseline suite below). Both the line
# prober (line_matches — proven by the planted-sample self-test) and the
# file scanner (scrub_file) consume it, so the two paths cannot drift apart.
# -a (text mode) is LOAD-BEARING, not cosmetic: one NUL byte in a gathered
# bundle (crashed-process doctor output, a binary-tinged flight-log tail)
# otherwise flips grep into "Binary file ... matches" mode — no -n line
# numbers, so scrub_file would replace ZERO lines while still reporting a
# count: a silent fail-open with a false redaction receipt. -a forces
# byte-wise line scanning (tokens after a NUL on the same line still match)
# and only ever WIDENS what can match — never a pattern relaxation.
MATCH_FLAGS=""; MATCH_PAT=""
match_args() {
  case "$1" in
    sub)  MATCH_FLAGS="-aiF"; MATCH_PAT="$2" ;;
    word) MATCH_FLAGS="-aiE"; MATCH_PAT="$(word_re "$2")" ;;
    id)   MATCH_FLAGS="-aE";  MATCH_PAT="$(id_re "$2")" ;;
    ere)  MATCH_FLAGS="-aiE"; MATCH_PAT="$2" ;;
    *) return 1 ;;
  esac
}

# line_matches KIND PAT TEXT — exit 0 iff TEXT hits PAT
line_matches() {
  match_args "$1" "$2" || return 1
  printf '%s\n' "$3" | "$GREP" -q "$MATCH_FLAGS" -- "$MATCH_PAT"
}

# --- load the suite -----------------------------------------------------------
GATE="$ROOT/cabinet/scripts/egg-publish-gate.sh"
SPECS=()
SUITE_MODE="baseline"
if [ -f "$GATE" ]; then
  GATE_LINE="$(sed -n 's/^GREP_PATTERNS="\(.*\)"$/\1/p' "$GATE" | head -1)"
  [ -n "$GATE_LINE" ] || die "found $GATE but could not extract GREP_PATTERNS — fail-closed, refusing to build an under-scrubbed bundle (the gate may have been reformatted; fix the extraction, never skip it)"
  read -r -a SPECS <<< "$GATE_LINE"
  SUITE_MODE="full (publish-gate suite + baseline)"
else
  echo "cabinet-feedback: note — publish-gate pattern source not present (packaged egg cuts exclude it); applying the BASELINE scrub only. Review the bundle with extra care." >&2
fi
# Baseline suite — always on, both modes. One spec per array element, so a
# HOME containing spaces stays a single pattern.
if [ -n "${HOME:-}" ]; then
  SPECS+=("sub:$HOME")
fi
if [ -n "${USER:-}" ] && printf '%s' "$USER" | "$GREP" -qE '^[A-Za-z0-9_-]{3,}$'; then
  SPECS+=("word:$USER")
fi
SPECS+=('ere:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
SPECS+=('id:[0-9]{9,}')

# --- planted-sample self-test (fail-closed, runtime-constructed samples) ------
selftest() {
  local spec kind pat digits
  for spec in "${SPECS[@]}"; do
    kind="${spec%%:*}"; pat="${spec#*:}"
    case "$kind" in
      sub)
        line_matches sub "$pat" "planted x${pat}x sample" \
          || die "scrub self-test failed: sub pattern would not fire (engine=$GREP)" ;;
      word)
        line_matches word "$pat" "planted ${pat} sample" \
          || die "scrub self-test failed: word pattern would not fire (engine=$GREP)"
        # digits are [:alnum:]: an embedded token must NOT fire (over-match guard)
        if line_matches word "$pat" "planted00${pat}00sample"; then
          die "scrub self-test failed: word pattern over-matches embedded tokens (engine=$GREP)"
        fi ;;
      id)
        # id specs are digit-run REGEXES today (e.g. [0-9]{9,}), which the
        # generic runtime-built 10-digit run satisfies. A future LITERAL
        # all-digit id entry would not match that generic run, so plant the
        # pattern itself in that case; a miss still dies fail-closed here
        # rather than ever scanning blind.
        case "$pat" in
          *[!0-9]*) digits="$(printf '5%.0s' 1 2 3 4 5 6 7 8 9 0)" ;;  # built at runtime
          *)        digits="$pat" ;;
        esac
        line_matches id "$pat" "planted $digits sample" \
          || die "scrub self-test failed: id pattern would not fire (engine=$GREP)" ;;
      ere)
        line_matches ere "$pat" "planted user@example.com sample" \
          || die "scrub self-test failed: ere pattern would not fire (engine=$GREP)" ;;
      *) die "scrub self-test: unknown pattern kind '$kind' in suite" ;;
    esac
  done
}
selftest

# scrub_file IN OUT — every line of IN that hits ANY spec is replaced entirely
# with "[scrubbed]". Prints the number of scrubbed lines on stdout.
scrub_file() {
  local in="$1" out="$2" spec kind pat lines="$WORK/hitlines"
  : > "$lines"
  for spec in "${SPECS[@]}"; do
    kind="${spec%%:*}"; pat="${spec#*:}"
    match_args "$kind" "$pat" || continue   # same matcher the self-test proved
    "$GREP" -n "$MATCH_FLAGS" -- "$MATCH_PAT" "$in" 2>/dev/null \
      | cut -d: -f1 >> "$lines" || true
  done
  sort -un "$lines" > "$lines.u"
  # ZERO hits => the input passes through UNTOUCHED. The two-file awk below
  # must never see an empty hit list: NR==FNR would then hold for every line
  # of the SECOND file too, swallowing the entire bundle as hit-list records
  # (the clean-environment case — nothing to scrub — is exactly what broke).
  if [ ! -s "$lines.u" ]; then
    cp -- "$in" "$out"
    echo 0
    return 0
  fi
  awk 'NR==FNR { hit[$1]=1; next } { if (FNR in hit) print "[scrubbed]"; else print }' \
    "$lines.u" "$in" > "$out"
  wc -l < "$lines.u" | tr -d ' '
}

# --- title goes through the same suite (refuse rather than post a hole) -------
printf '%s\n' "$TITLE" > "$WORK/title"
TITLE_HITS="$(scrub_file "$WORK/title" "$WORK/title.scrubbed")"
[ "$TITLE_HITS" -eq 0 ] || bail "the issue title trips the leak-scrub suite — reword it (nothing was posted)"

# --- gather --------------------------------------------------------------------
RAW="$WORK/bundle.raw"
{
  echo "# cabinet-feedback diagnostic bundle"
  echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## versions"
  uname -sm 2>/dev/null || echo "uname: unavailable"
  if command -v python3.12 >/dev/null 2>&1; then
    python3.12 --version 2>&1
  elif command -v python3 >/dev/null 2>&1; then
    python3 --version 2>&1
  else
    echo "python3: not found"
  fi
  if git -C "$ROOT" rev-parse --short HEAD >/dev/null 2>&1; then
    echo "checkout: $(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?') @ $(git -C "$ROOT" rev-parse --short HEAD)"
  else
    echo "checkout: not a git checkout"
  fi
  if [ -f "$ROOT/egg-manifest.json" ]; then
    echo "egg-manifest.json: present (packaged egg cut)"
  fi
  echo
  echo "## cabinet-doctor"
} > "$RAW"

DOCTOR="$ROOT/cabinet/scripts/cabinet-doctor.sh"
if [ -f "$DOCTOR" ]; then
  echo "cabinet-feedback: running cabinet-doctor (read-only prober; may take a minute)..." >&2
  DOCTOR_RC=0
  bash "$DOCTOR" >> "$RAW" 2>&1 || DOCTOR_RC=$?
  echo "(cabinet-doctor exit code: $DOCTOR_RC)" >> "$RAW"
else
  echo "(cabinet-doctor.sh not found at $DOCTOR)" >> "$RAW"
fi

{
  echo
  echo "## hatch flight log (newest, last 60 lines)"
} >> "$RAW"
NEWEST=""
for f in "${HOME:-/nonexistent}"/hatch-logs/*/flight.log; do
  [ -f "$f" ] || continue
  if [ -z "$NEWEST" ] || [ "$f" -nt "$NEWEST" ]; then NEWEST="$f"; fi
done
if [ -n "$NEWEST" ]; then
  { echo "source: $NEWEST"; tail -n 60 "$NEWEST"; } >> "$RAW"
else
  echo "(no flight logs found under \$HOME/hatch-logs)" >> "$RAW"
fi

# --- scrub -----------------------------------------------------------------------
OUT="$WORK/bundle.redacted"
SCRUBBED_N="$(scrub_file "$RAW" "$OUT.body")"
{
  echo "> Auto-redacted by cabinet-feedback — scrub suite: $SUITE_MODE;"
  echo "> $SCRUBBED_N line(s) replaced with [scrubbed]. Reviewed by the user"
  echo "> before posting (explicit consent required; --dry-run never posts)."
  echo
  cat "$OUT.body"
} > "$OUT"

# --- review ----------------------------------------------------------------------
echo
echo "---8<--- redacted bundle (exactly what would be posted) ---------------"
cat "$OUT"
echo "---8<--- end of bundle ------------------------------------------------"
echo "cabinet-feedback: $SCRUBBED_N line(s) redacted by the leak-scrub suite ($SUITE_MODE)"

GH_ARGV=(gh issue create --repo "$CANONICAL_REPO" --title "$TITLE" --label "$ISSUE_LABEL" --body-file "$OUT")

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "DRY RUN — nothing was posted; gh was not invoked."
  printf 'would run:'
  printf ' %q' "${GH_ARGV[@]}"
  printf '\n'
  exit 0
fi

# --- honest gh preflight -----------------------------------------------------------
command -v gh >/dev/null 2>&1 \
  || bail "gh is not installed — install the GitHub CLI (https://cli.github.com) or use --dry-run and file the bundle by hand"
gh auth status >/dev/null 2>&1 \
  || bail "gh is not authenticated — run: gh auth login   (nothing was posted)"

# --- explicit interactive consent (never scriptable past) ---------------------------
if [ ! -t 0 ]; then
  bail "consent requires an interactive terminal (stdin is not a TTY) — re-run interactively, or use --dry-run and file the bundle yourself (nothing was posted)"
fi
printf 'Post this bundle as a new issue on %s (title: %s)? [y/N] ' "$CANONICAL_REPO" "$TITLE" >&2
IFS= read -r REPLY || REPLY=""
case "$REPLY" in
  y|Y|yes|YES|Yes) ;;
  *) bail "aborted by user — nothing was posted" ;;
esac

# --- post (fixed argv; gh's own error surfaces honestly) ----------------------------
"${GH_ARGV[@]}"
echo "cabinet-feedback: issue created (bundle as reviewed above)."
