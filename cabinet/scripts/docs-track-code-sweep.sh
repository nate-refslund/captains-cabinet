#!/bin/bash
# docs-track-code-sweep.sh — mechanical checker for NORTH-STAR gate G6
# ("docs must track the code"). The rule was previously enforced by review
# discipline only; this script makes the two MECHANICALLY checkable halves
# of it a gate. No semantic guessing — it never judges whether prose is
# stale, only whether a referenced path is dead.
#
# WHAT IT CHECKS (all read-only; the only output is its own report lines on
# stdout — it writes no files, touches no network, reads no secret VALUES;
# a path like cabinet/.env is only ever handled as a candidate STRING):
#   1. dead repo-path references in LIVING docs: any backtick-quoted or bare
#      token shaped like a repo path (first segment is a repo top-level
#      entry, last segment carries an extension — e.g. cabinet/scripts/foo.sh,
#      docs/plans/bar.md, framework/x/y.py) must exist at HEAD. Home-anchored
#      runs (~/...) and scheme URLs (http://...) are stripped before matching.
#   2. dead RELATIVE markdown links [text](rel/path.md) in the same living
#      set: #anchors stripped, scheme links (http/https/mailto/tel/data) and
#      absolute (/...) targets ignored; the target is resolved against the
#      doc's directory first, then repo-root as a fallback (both dead =
#      finding). Links that escape the repo root cannot be verified and are
#      skipped, not reported.
#
# SCOPE (the LIVING doc set): README* + CLAUDE.md at the root,
#   docs/runbooks/**/*.md, cabinet/docs/**/*.md, packs/**/*.md.
#   Dated historical archives (docs/plans/*, docs/proposals/*, docs/launch/*)
#   are EXCLUDED by construction — they are records of what was true when
#   written, not living docs, and must keep their original references.
#
# EXISTENCE ORACLE: when the scan root is itself a git toplevel, "exists"
#   means tracked at HEAD (git ls-tree — deterministic, ignores local litter);
#   otherwise a plain filesystem check (the pytest fixture-tree mode).
#
# ALLOWLIST: cabinet/scripts/docs-sweep-allowlist.txt (override with
#   --allowlist <path>) — one glob pattern per line, # comments. For
#   LEGITIMATE references to gitignored/runtime paths (secrets files with
#   tracked .example/.template twins, instance-hatch-created config, runtime
#   ledgers under shared/interfaces/). Every entry must say WHY.
#
# OUTPUT: one line per finding
#   <doc>:<line> -> <missing-path>
# then a summary line:
#   DOCS_SWEEP GREEN (files=N findings=0)      | exit 0
#   DOCS_SWEEP FINDINGS (n=K files=N)          | exit 1
# Usage errors exit 64.
#
# FLAGS:
#   --list-scope        print the scanned file list (repo-relative), exit 0
#   --allowlist <path>  use this allowlist instead of the default
#   --root <dir>        scan this tree instead of the repo this script
#                       lives in (test harness hook)
#
# Style contract: bash 3.2 portable (no mapfile / assoc arrays), set -u,
# clean under `shellcheck -S warning`. Referenced by NORTH-STAR G6; tests at
# cabinet/scripts/tests/test_docs_sweep.py.

set -u

SELF_DIR=$(cd "$(dirname "$0")" && pwd -P) || exit 1
DEFAULT_ROOT=$(cd "$SELF_DIR/../.." && pwd -P) || exit 1

ROOT="$DEFAULT_ROOT"
ALLOWLIST_FILE=""
LIST_SCOPE=0

usage() {
  echo "usage: docs-track-code-sweep.sh [--list-scope] [--allowlist <path>] [--root <dir>]" >&2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --list-scope)
      LIST_SCOPE=1
      ;;
    --allowlist)
      shift
      [ $# -gt 0 ] || { echo "error: --allowlist needs a path" >&2; exit 64; }
      ALLOWLIST_FILE="$1"
      [ -f "$ALLOWLIST_FILE" ] || { echo "error: allowlist not found: $ALLOWLIST_FILE" >&2; exit 64; }
      ;;
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

# Default allowlist rides next to this script only when scanning a tree that
# carries one at the conventional path (fixture trees may carry their own).
if [ -z "$ALLOWLIST_FILE" ] && [ -f "$ROOT/cabinet/scripts/docs-sweep-allowlist.txt" ]; then
  ALLOWLIST_FILE="$ROOT/cabinet/scripts/docs-sweep-allowlist.txt"
fi
ALLOW_PATTERNS=""
if [ -n "$ALLOWLIST_FILE" ]; then
  ALLOW_PATTERNS=$(cat "$ALLOWLIST_FILE")
fi

# ---------------------------------------------------------------- scope ----
scope_files() {
  (
    cd "$ROOT" || exit 1
    for f in README*; do
      [ -f "$f" ] && printf '%s\n' "$f"
    done
    if [ -f CLAUDE.md ]; then
      printf 'CLAUDE.md\n'
    fi
    for d in docs/runbooks cabinet/docs packs; do
      if [ -d "$d" ]; then
        find "$d" -type f -name '*.md' -print
      fi
    done
  ) | sort -u
}

SCOPE=$(scope_files)

if [ "$LIST_SCOPE" = 1 ]; then
  if [ -n "$SCOPE" ]; then
    printf '%s\n' "$SCOPE"
  fi
  exit 0
fi

# --------------------------------------------------- existence oracle ------
GIT_MODE=0
TRACKED=""
TOPLEVEL=$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null) || TOPLEVEL=""
if [ -n "$TOPLEVEL" ]; then
  TOPLEVEL=$(cd "$TOPLEVEL" && pwd -P) || TOPLEVEL=""
fi
if [ -n "$TOPLEVEL" ] && [ "$TOPLEVEL" = "$ROOT" ]; then
  if TRACKED=$(git -C "$ROOT" ls-tree -r --name-only HEAD 2>/dev/null); then
    GIT_MODE=1
  fi
fi

if [ "$GIT_MODE" = 1 ]; then
  TOPS=$(git -C "$ROOT" ls-tree --name-only HEAD 2>/dev/null)
else
  TOPS=$(ls -A "$ROOT")
fi

# exists at HEAD (git mode: tracked file, or tracked-dir prefix) / on disk.
# NB: feed the big lists via here-string, not `printf ... | grep -q`/`| awk`.
# grep -q and awk `exit` close their stdin on the first match, which sends
# SIGPIPE to the upstream printf — harmless today (no pipefail) but it spews
# "printf: write error: Broken pipe" into CI logs (obscures real failures)
# and would become an intermittent failure the moment anyone adds pipefail.
path_exists() {
  if [ "$GIT_MODE" = 1 ]; then
    grep -qxF -- "$1" <<<"$TRACKED" && return 0
    awk -v p="$1/" 'index($0, p) == 1 { found = 1; exit } END { exit found ? 0 : 1 }' <<<"$TRACKED"
  else
    [ -e "$ROOT/$1" ]
  fi
}

is_topdir() {
  grep -qxF -- "$1" <<<"$TOPS"
}

allowlisted() {
  [ -n "$ALLOW_PATTERNS" ] || return 1
  local pat
  while IFS= read -r pat; do
    case "$pat" in
      ''|'#'*) continue ;;
    esac
    # shellcheck disable=SC2053 # glob-match IS the allowlist contract
    if [[ "$1" == $pat ]]; then
      return 0
    fi
  done <<EOF
$ALLOW_PATTERNS
EOF
  return 1
}

# ------------------------------------------- check 1: dead path refs -------
scan_path_refs() {
  local f line cand last first
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    # strip home-anchored runs and scheme URLs, then extract path-shaped
    # tokens (line numbers preserved: sed is line-for-line).
    sed -E -e 's|~/[A-Za-z0-9_./@-]*| |g' \
           -e 's|[a-zA-Z][a-zA-Z0-9+.-]*://[^"[:space:])]*| |g' \
           "$ROOT/$f" \
      | grep -noE '\.?[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9_.@-]+)+' \
      | while IFS=: read -r line cand; do
          last=${cand##*/}
          case "$last" in
            *.*) ;;
            *) continue ;;   # no extension — not a file-shaped ref
          esac
          first=${cand%%/*}
          is_topdir "$first" || continue
          allowlisted "$cand" && continue
          path_exists "$cand" || printf '%s:%s -> %s\n' "$f" "$line" "$cand"
        done
  done <<EOF
$SCOPE
EOF
  return 0
}

# --------------------------------------- check 2: dead relative links ------
# pure-string ./.. normalizer (no realpath — targets may not exist, which is
# the point). Prints __OUT__ when the path escapes the repo root.
normalize_rel() {
  local input="$1" out="" seg
  local IFS='/'
  set -f
  # shellcheck disable=SC2086 # IFS=/ word-split IS the parse; glob off above
  for seg in $input; do
    case "$seg" in
      ''|'.') ;;
      '..')
        if [ -z "$out" ]; then
          set +f
          printf '__OUT__\n'
          return 0
        fi
        case "$out" in
          */*) out=${out%/*} ;;
          *)   out="" ;;
        esac
        ;;
      *)
        if [ -z "$out" ]; then out="$seg"; else out="$out/$seg"; fi
        ;;
    esac
  done
  set +f
  printf '%s\n' "$out"
}

scan_links() {
  local f d line raw tgt resolved rootres
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    d=$(dirname "$f")
    [ "$d" = "." ] && d=""
    grep -noE '\]\([^)]+\)' "$ROOT/$f" \
      | while IFS=: read -r line raw; do
          tgt=${raw#"]("}
          tgt=${tgt%")"}
          case "$tgt" in
            '<'*'>') tgt=${tgt#<}; tgt=${tgt%>} ;;
          esac
          tgt=${tgt%% *}          # drop "title" part
          tgt=${tgt%%#*}          # drop #anchor
          case "$tgt" in
            ''|/*) continue ;;                      # anchor-only / absolute
            *://*|mailto:*|tel:*|data:*) continue ;; # external
          esac
          resolved=$(normalize_rel "$d/$tgt")
          [ "$resolved" = "__OUT__" ] && continue   # escapes root: unverifiable
          allowlisted "$resolved" && continue
          path_exists "$resolved" && continue
          # tolerate repo-root-relative link style before flagging
          rootres=$(normalize_rel "$tgt")
          if [ "$rootres" != "__OUT__" ] && [ -n "$rootres" ]; then
            allowlisted "$rootres" && continue
            path_exists "$rootres" && continue
          fi
          printf '%s:%s -> %s\n' "$f" "$line" "$resolved"
        done
  done <<EOF
$SCOPE
EOF
  return 0
}

# ---------------------------------------------------------------- main -----
FINDINGS=$({ scan_path_refs; scan_links; } | awk '!seen[$0]++')

if [ -n "$SCOPE" ]; then
  N_FILES=$(printf '%s\n' "$SCOPE" | grep -c .)
else
  N_FILES=0
fi

if [ -n "$FINDINGS" ]; then
  printf '%s\n' "$FINDINGS"
  N=$(printf '%s\n' "$FINDINGS" | grep -c .)
  echo "DOCS_SWEEP FINDINGS (n=$N files=$N_FILES)"
  exit 1
fi

echo "DOCS_SWEEP GREEN (files=$N_FILES findings=0)"
exit 0
