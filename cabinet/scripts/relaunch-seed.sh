#!/bin/bash
# relaunch-seed.sh — pre-cutover SAFETY ARCHIVE for the fresh-instance
# relaunch (Captain 100%-SCRATCH ruling, 2026-07-18: the fresh instance
# inherits NOTHING from the old one — it is produced entirely by
# hatch.sh --defaults, NOT by seeding old content). This script's ONE job is
# to capture a full, restorable backup of the old deployment BEFORE the
# cutover, so the switch stays reversible. It seeds nothing.
#
# Full procedure: docs/runbooks/fresh-instance-relaunch.md. The KEEP/DROP
# inventory that USED to drive a curated seed lives in
# docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md — now SUPERSEDED
# IN PART (see its dated header): under 100%-SCRATCH every former KEEP-of-
# live-content is DROP-from-seed, preserved only inside the archive this
# script writes, as the Flavor-B restore map if a future ruling wants any of
# it back.
#
# WHAT THIS DOES — two archive members, nothing else:
#   1. The ENTIRE old-root tree (default $HOME/captains-cabinet) as ONE
#      member: code, .git, instance/ (the org-brain/searchable memory under
#      instance/memory + every lane's tier2 knowledge), shared/interfaces/
#      (governance ledgers, world chronicle, product-specs), and the real,
#      un-rotated cabinet/.env — excluding only regenerable __pycache__/*.pyc
#      noise. This is the rollback net; nothing is lost.
#   2. ~/Library/Application Support/cabinet/ (the larger Mac-level state) as a
#      SECOND, separately-namespaced member — unless --skip-appsupport-archive.
# It seeds no runtime root, rotates no secret, and reads no "curated
# allowlist": there is nothing to get wrong about what carries forward,
# because nothing does. The fresh instance is materialized later by
# hatch.sh --defaults (see the runbook), not by this script.
#
# THIS SCRIPT NEVER WRITES TO --old-root (default the live tree) — it is a
# read-only source, same discipline as runtime-provision.sh's own "never
# touches the live tree" contract. It writes ONLY to --archive-path (a
# standalone tar.gz). --runtime-root is still parsed and containment-guarded
# (it names where the fresh instance is provisioned NEXT, per the runbook),
# but this archive-only script writes nothing into it.
#
# THE EXTERNAL OBSIDIAN VAULT (~/Obsidian/screenpipe-brain/**, manifest §1a)
# is deliberately NOT archived here: it is external to this repo, has its own
# obsidian-backup-*.tar.gz, and the ruling leaves it untouched. "The vault"
# that IS captured (inside the full old-root member) means the cabinet's own
# org-brain / searchable memory under instance/memory — NOT the external
# Obsidian store.
#
# CONTAINMENT — ported from cabinet/scripts/hatch.sh's clean-room path-
# comparison idiom (lex_norm_path / resolve_for_compare below are copied
# near-verbatim from that file's "clean-room containment path helpers"
# section, credited inline, not reinvented): refuses, before any write, an
# --archive-path (or --runtime-root) whose directory resolves to, or nests
# under, the live tree — and, generalizing the same idiom, also refuses one
# that resolves to/under --old-root itself, so a sandbox rehearsal against a
# scratch old-root fixture is protected from the same class of self-inflicted
# mistake, not only the hardcoded production path. THE REVERSE NESTING IS
# ALSO REFUSED: --old-root resolving to, or nesting under, --runtime-root — a
# defensive check kept from the seed era so no path this script touches can
# alias its own read-only source. Every user-supplied path is absolutized and
# lexically normalized BEFORE any guard runs (a relative --archive-path is
# prefixed with $PWD first), so the nesting comparison can never be defeated
# by a relative spelling that slips past the absolute-path case match.
#
# The ARCHIVE is intentionally NOT idempotent: every run names a fresh,
# timestamped archive path by default (never silently overwrites a previous
# safety snapshot) — pass --archive-path explicitly for a fixed name.
#
# SECRETS DISCIPLINE: this script never echoes a secret VALUE to stdout,
# stderr, or any log — only variable NAMES and file paths, matching
# cabinet-doctor.sh's and docs/runbooks/dev-runtime-split-cutover.md's own
# existing convention. The archive deliberately holds the real, un-rotated
# cabinet/.env (it is the rollback net) — no rotation happens anywhere now
# that this script is archive-only. The archive file itself is created
# mode-restricted (umask 077 + chmod 600) since it necessarily contains that
# secret.
#
# Usage:
#   relaunch-seed.sh [--old-root <path>] [--runtime-root <path>]
#                     [--archive-path <path>] [--telegram-token-var NAME]
#                     [--skip-appsupport-archive] [--dry-run]
#
# Exit codes: 0 success · 1 operational failure · 64 usage error.
set -euo pipefail

# The live tree — hardcoded, deliberately NOT overridable by any flag or
# env var (an override here would defeat the one guarantee this script
# exists to make). Matches hatch.sh's own similar non-negotiable constants.
LIVE_TREE="${CABINET_LIVE_TREE:-$HOME/captains-cabinet}"

usage() {
  cat <<'EOF'
Usage: relaunch-seed.sh [flags]

Writes a full, restorable SAFETY ARCHIVE of the old instance root (plus the
Mac-level Application Support state) BEFORE a fresh-instance relaunch. It
SEEDS NOTHING — the fresh instance is produced entirely by hatch.sh
--defaults (see docs/runbooks/fresh-instance-relaunch.md). The archive is the
rollback net and the Flavor-B restore source.

Flags:
  --old-root <path>          Old instance root to read FROM (read-only,
                              never written). Default: $HOME/captains-cabinet
  --runtime-root <path>      Where the fresh instance will later be
                              provisioned (runtime-provision.sh init). Parsed
                              and containment-guarded here; this archive-only
                              script writes nothing into it.
                              Default: ~/.cabinet/runtime
  --archive-path <path>      Where to write the full-instance safety tar.
                              Default: a fresh ~/cabinet-relaunch-archive-
                              <UTC timestamp>.tar.gz every run.
  --telegram-token-var NAME  Accepted but INERT (no-op) — kept so existing
                              runbook invocations don't break. Nothing is
                              seeded or rotated now that this script is
                              archive-only. Default: TELEGRAM_COS_TOKEN.
  --skip-appsupport-archive  Skip archiving ~/Library/Application Support/
                              cabinet/ (still archives the full old-root).
  --dry-run                  Print the exact planned operations, write
                              nothing, exit 0.
  -h, --help                 This text.

Exit codes: 0 success · 1 operational failure · 64 usage error.
EOF
}

# ---- path helpers (ported near-verbatim from cabinet/scripts/hatch.sh's
# "clean-room containment path helpers" section — same functions, same
# behavior, credited here rather than reinvented) --------------------------

# lex_norm_path <path> — PURELY LEXICAL normalization, never touches the
# filesystem: collapses '//' runs and '.' segments, pops '..' normpath-
# style, strips the trailing '/'. Bash 3.2-safe.
lex_norm_path() (
  set -f
  local IFS='/' seg out="" abs=0 n
  local parts=()
  case "$1" in /*) abs=1 ;; esac
  for seg in $1; do
    case "$seg" in
      ''|'.') ;;
      '..')
        n=${#parts[@]}
        if [ "$n" -gt 0 ] && [ "${parts[$((n - 1))]}" != ".." ]; then
          unset "parts[$((n - 1))]"
        elif [ "$abs" = "0" ]; then
          parts+=("..")
        fi
        ;;
      *) parts+=("$seg") ;;
    esac
  done
  for seg in ${parts[@]+"${parts[@]}"}; do out="$out/$seg"; done
  if [ "$abs" = "1" ]; then
    printf '%s' "${out:-/}"
  else
    printf '%s' "${out#/}"
  fi
)

# resolve_for_compare <path> — lexical normalization, then PHYSICAL
# resolution of the deepest EXISTING ancestor (realpath) with the
# not-yet-existing remainder re-appended, so /tmp vs /private/tmp-style
# aliasing and symlinked spellings compare equal even when the leaf does
# not exist yet. A box without realpath falls back to the lexical form
# (over-refusing is fail-safe, never under-refusing).
resolve_for_compare() {
  local p head tail=""
  p="$(lex_norm_path "$1")"
  case "$p" in
    /*) ;;
    *) printf '%s' "$p"; return 0 ;;
  esac
  if ! command -v realpath >/dev/null 2>&1; then
    printf '%s' "$p"
    return 0
  fi
  head="$p"
  while [ "$head" != "/" ]; do
    if [ -e "$head" ]; then
      head="$(realpath "$head" 2>/dev/null || printf '%s' "$head")"
      if [ "$head" = "/" ]; then head=""; fi
      printf '%s%s' "$head" "$tail"
      return 0
    fi
    tail="/${head##*/}$tail"
    head="${head%/*}"
    if [ -z "$head" ]; then head="/"; fi
  done
  printf '%s' "$p"
}

# abs_path <path> — resolve to an absolute path without relying on GNU
# realpath (ported from runtime-provision.sh's own helper — same repo,
# same already-proven idiom, not reinvented).
abs_path() {
  local p="$1"
  if [ -d "$p" ]; then
    (cd "$p" && pwd)
  elif [ -e "$p" ]; then
    (cd "$(dirname "$p")" && printf '%s/%s' "$(pwd)" "$(basename "$p")")
  else
    local parent
    if parent="$(cd "$(dirname "$p")" 2>/dev/null && pwd)"; then
      printf '%s/%s' "$parent" "$(basename "$p")"
    else
      printf '%s' "$p"
    fi
  fi
}

# refuse_if_nested <flag-description> <candidate-dir> <protected-root> —
# refuse (exit 64), before any write, if <candidate-dir> resolves to, or
# nests under, <protected-root>.
refuse_if_nested() {
  local desc="$1" candidate="$2" protected="$3" cand_r prot_r
  cand_r="$(resolve_for_compare "$candidate")"
  prot_r="$(resolve_for_compare "$protected")"
  case "$cand_r" in
    "$prot_r"|"$prot_r"/*)
      echo "relaunch-seed.sh: refusing $desc ($candidate) — it resolves to, or nests under, $protected." >&2
      echo "                  This script never writes into that tree. Point $desc at a separate path." >&2
      exit 64
      ;;
  esac
}

# ---- arg parsing -----------------------------------------------------------
OLD_ROOT="$LIVE_TREE"
RUNTIME_ROOT="$HOME/.cabinet/runtime"
ARCHIVE_PATH=""
TELEGRAM_TOKEN_VAR="TELEGRAM_COS_TOKEN"
SKIP_APPSUPPORT=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --old-root) OLD_ROOT="${2:?--old-root requires a path}"; shift 2 ;;
    --runtime-root) RUNTIME_ROOT="${2:?--runtime-root requires a path}"; shift 2 ;;
    --archive-path) ARCHIVE_PATH="${2:?--archive-path requires a path}"; shift 2 ;;
    --telegram-token-var) TELEGRAM_TOKEN_VAR="${2:?--telegram-token-var requires a NAME}"; shift 2 ;;
    --skip-appsupport-archive) SKIP_APPSUPPORT=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "relaunch-seed.sh: unknown flag '$1'" >&2; usage >&2; exit 64 ;;
  esac
done

[ -n "$ARCHIVE_PATH" ] || ARCHIVE_PATH="$HOME/cabinet-relaunch-archive-$(date -u +%Y%m%d-%H%M%SZ).tar.gz"

# --telegram-token-var is INERT (archive-only) but its value is still
# validated as a well-formed env-var name — a malformed one is an operator
# mistake worth catching loudly even though nothing is rotated.
if ! printf '%s' "$TELEGRAM_TOKEN_VAR" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; then
  echo "relaunch-seed.sh: --telegram-token-var '$TELEGRAM_TOKEN_VAR' is not a valid environment-variable name" >&2
  exit 64
fi

[ -d "$OLD_ROOT" ] || { echo "relaunch-seed.sh: --old-root '$OLD_ROOT' is not a directory" >&2; exit 1; }
OLD_ROOT="$(abs_path "$OLD_ROOT")"
# Absolutize RUNTIME_ROOT WITHOUT touching the filesystem — no mkdir yet.
# The containment guards below must run before ANY write, including the
# mkdir that used to sit here unconditionally on a real run: review found
# it fires before the guards, so a refused invocation still created an
# empty directory (proven inside the live tree via three path shapes —
# direct, through a symlink, and through a lexical `..`) before exiting 64.
# Purely lexical: prefix a relative path with $PWD, then collapse
# '.'/'..'/'//'. resolve_for_compare (used inside the guards) already
# walks up to the deepest EXISTING ancestor and realpath-resolves it on its
# own, so it does not need RUNTIME_ROOT to exist yet.
case "$RUNTIME_ROOT" in
  /*) ;;
  *) RUNTIME_ROOT="$PWD/$RUNTIME_ROOT" ;;
esac
RUNTIME_ROOT="$(lex_norm_path "$RUNTIME_ROOT")"

# Absolutize ARCHIVE_PATH the SAME way, BEFORE the containment guards below
# (review high finding): dirname of a RELATIVE --archive-path stays relative,
# and resolve_for_compare returns a non-absolute input unchanged, so the
# `case` match against the absolute LIVE_TREE/OLD_ROOT is vacuous — a
# relative archive path with cwd inside old-root would slip past the guard
# and write the tar INSIDE the read-only source. Prefixing $PWD + lex-
# normalizing here makes refuse_if_nested see an absolute directory, so a
# relative spelling that resolves into old-root/live-tree is refused and one
# that resolves elsewhere is allowed. The default $HOME/... path is already
# absolute → this is a no-op for it.
case "$ARCHIVE_PATH" in
  /*) ;;
  *) ARCHIVE_PATH="$PWD/$ARCHIVE_PATH" ;;
esac
ARCHIVE_PATH="$(lex_norm_path "$ARCHIVE_PATH")"

# ---- containment guards (must run BEFORE any write below, including the
# mkdir a few lines down) ----------------------------------------------------
refuse_if_nested "--runtime-root"                "$RUNTIME_ROOT"            "$LIVE_TREE"
refuse_if_nested "--archive-path's directory"    "$(dirname "$ARCHIVE_PATH")" "$LIVE_TREE"
refuse_if_nested "--runtime-root"                "$RUNTIME_ROOT"            "$OLD_ROOT"
refuse_if_nested "--archive-path's directory"    "$(dirname "$ARCHIVE_PATH")" "$OLD_ROOT"
# Reverse direction (review finding #3): --old-root must never resolve to,
# or nest under, --runtime-root — a defense-in-depth check kept from the
# seed era so no path this script touches can ever alias its own read-only
# source, even though the seed writes that motivated it are now gone.
refuse_if_nested "--old-root"                    "$OLD_ROOT"                "$RUNTIME_ROOT"

# Guards passed — only now is it safe to create/resolve the runtime root.
# (This archive-only script writes nothing INTO the runtime root; it just
# materializes the dir so the runbook's next step — runtime-provision.sh
# init on the same path — has a real, resolved directory to point at.)
[ "$DRY_RUN" = "1" ] || mkdir -p "$RUNTIME_ROOT"
RUNTIME_ROOT="$(abs_path "$RUNTIME_ROOT")"

# ---- archive (the whole job now — the pre-cutover safety net) ---------------
do_archive() {
  echo "relaunch-seed.sh: archiving full old-root -> $ARCHIVE_PATH"
  local has_appsupport=0
  local as_dir="$HOME/Library/Application Support/cabinet"
  if [ "$SKIP_APPSUPPORT" != "1" ] && [ -d "$as_dir" ]; then has_appsupport=1; fi

  if [ ! -e "$OLD_ROOT/cabinet/.env" ]; then
    echo "relaunch-seed.sh: NOTE — $OLD_ROOT/cabinet/.env not found; the full-tree member simply won't contain it (a from-scratch old-root legitimately has none)" >&2
  fi
  if [ "$SKIP_APPSUPPORT" = "1" ]; then
    echo "relaunch-seed.sh: --skip-appsupport-archive set; not archiving $as_dir"
  elif [ "$has_appsupport" != "1" ]; then
    echo "relaunch-seed.sh: NOTE — $as_dir not present on this host; nothing to archive there"
  fi

  # The old-root is captured as ONE member via -C its parent + its basename,
  # so the archive holds it under a "<basename>/" prefix (e.g.
  # "captains-cabinet/..."). The Application Support half keeps its OWN
  # "Application Support/cabinet" member prefix (via -C "$HOME/Library",
  # never a bare "cabinet" via -C ".../Application Support") — a bare
  # "cabinet" member name would collide with, and merge into, the old-root's
  # own "cabinet/" subdir prefix inside the same tar (review finding #2:
  # extraction produced one merged dir mixing repo files with Application
  # Support files). Two similarly-named source trees, kept namespaced apart
  # on purpose. Only regenerable __pycache__/*.pyc noise is excluded; .git
  # is kept deliberately — this is a FULL backup and the point is to lose
  # nothing.
  local old_parent old_base
  old_parent="$(dirname "$OLD_ROOT")"
  old_base="$(basename "$OLD_ROOT")"

  if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would tar -czf $ARCHIVE_PATH --exclude '*/__pycache__' --exclude '*.pyc' -C \"$old_parent\" \"$old_base\"$( [ "$has_appsupport" = 1 ] && printf ' -C "%s" "Application Support/cabinet"' "$HOME/Library" )"
    return 0
  fi

  mkdir -p "$(dirname "$ARCHIVE_PATH")"
  # Created mode-restricted (umask 077) since the full-tree member contains
  # the real cabinet/.env; chmod 600 after in case --archive-path names a
  # pre-existing file (tar truncates but keeps its existing mode).
  ( umask 077
    if [ "$has_appsupport" = 1 ]; then
      tar -czf "$ARCHIVE_PATH" --exclude '*/__pycache__' --exclude '*.pyc' \
        -C "$old_parent" "$old_base" \
        -C "$HOME/Library" "Application Support/cabinet"
    else
      tar -czf "$ARCHIVE_PATH" --exclude '*/__pycache__' --exclude '*.pyc' \
        -C "$old_parent" "$old_base"
    fi
  )
  chmod 600 "$ARCHIVE_PATH"
  echo "relaunch-seed.sh: archive written: $ARCHIVE_PATH"
}

main() {
  echo "relaunch-seed.sh: old-root=$OLD_ROOT runtime-root=$RUNTIME_ROOT archive-path=$ARCHIVE_PATH dry-run=$DRY_RUN"
  do_archive
  if [ "$DRY_RUN" = "1" ]; then
    echo "relaunch-seed.sh: DRY RUN — nothing was written."
  else
    echo "relaunch-seed.sh: archive complete (archive-only — the fresh instance inherits nothing; it is produced by hatch.sh --defaults). Next: cabinet/scripts/runtime-provision.sh init \"$RUNTIME_ROOT\" ... then a fresh hatch (see docs/runbooks/fresh-instance-relaunch.md)."
  fi
}
main
