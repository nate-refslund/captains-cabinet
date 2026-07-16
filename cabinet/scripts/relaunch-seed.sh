#!/bin/bash
# relaunch-seed.sh — builds the fresh-instance relaunch seed: a full
# safety-net archive of the OLD instance root, then a curated KEEP-only
# copy into a runtime root's shared/ tree (Captain ruling 2026-07-15: hatch
# a FRESH instance into the dev/runtime-split runtime, keeping searchable
# memory + org-brain, dropping governance sediment — full KEEP/DROP
# inventory: docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md;
# full procedure: docs/runbooks/fresh-instance-relaunch.md).
#
# THIS SCRIPT NEVER WRITES TO --old-root (default /Users/nate/captains-
# cabinet, the live tree) — read-only source, same discipline as runtime-
# provision.sh's own "never touches the live tree" contract. It writes
# ONLY to --runtime-root's shared/ subtree (composes with, and never
# duplicates, cabinet/scripts/runtime-provision.sh's own link_instance_data()
# — see that script's header for the full leaf-symlink scheme this seed
# is prepared for) and to --archive-path (a standalone tar.gz safety net).
#
# WHAT THIS SEEDS — an ALLOWLIST, never a wholesale copy of instance/. That
# is the load-bearing safety property: a DROP item (trust-ladder/posture
# state, roster.yml, roles/active, captain-*.md ledgers, world chronicle,
# launchd generated/, telegram-state, attention-queue, memory/tier3/**, ...)
# can only leak forward by being explicitly added to one of the blocks
# below, never by omission from an exclude list — this script simply never
# reads any DROP path in the first place.
#
#   1. cabinet/.env -> shared/cabinet.env, byte-for-byte EXCEPT the
#      configured --telegram-token-var line's VALUE (rotated to a
#      placeholder; the HQ chat id and every other secret carry unchanged).
#   2. instance/config/{extensions.yml,extra-mcps.json} -> shared/instance/
#      config/ (gitignored-but-real deployment-capability config named
#      KEEP by the manifest; each independently optional — never fabricated
#      if absent).
#   3. instance/memory/tier2/<officer>/*.md (TOP-LEVEL ONLY, via -maxdepth 1
#      -name '*.md' — an allowlist by construction, so it structurally
#      excludes that officer's reflections/, evolution-proposals/, AND
#      .session-state.json without needing to name them individually) for
#      EVERY officer bucket found on old-root (discovered by listing
#      instance/memory/tier2/*/ — deliberately NOT a hardcoded product/
#      officer-name list: this script lives under cabinet/scripts/, which
#      is framework layer per this repo's own product/captain-agnostic-
#      foundation rule, and discovery also just seeds whatever really
#      exists rather than an assumed-fixed roster) -> shared/instance/
#      memory/tier2/<officer>/, plus a .gitkeep + reflections/.gitkeep
#      skeleton per officer (matching the tracked skeleton shape). Because
#      instance/memory is a WHOLE-DIRECTORY seeded symlink in runtime-provision.sh
#      (INSTANCE_PERSISTENT_SEEDED_DIRS), whatever this step writes becomes
#      the ENTIRE instance/memory tree for every future release — the
#      top-level-only discipline here is the only thing standing between
#      "keep the product-brain" and "silently resurrect agent-reasoning
#      logs and session ephemera."
#   4. instance/fidelity/regression_corpus/{README.md,manifest.json,
#      cases/*.json} -> shared/instance/fidelity/regression_corpus/ (full
#      current-state capture). This path is ALREADY git-tracked, so a
#      fresh checkout mostly has it for free; this copy exists purely to
#      also catch locally-uncommitted corpus growth. NAMED GAP (found
#      while building this script, not fixed by it — out of scope to edit
#      the already-reviewed runtime-provision.sh from here): that script's
#      own leaf-symlink list does not yet reference instance/fidelity/, so
#      this seeded copy is NOT automatically wired into a provisioned
#      release today. Either commit the corpus growth to the branch before
#      cutover, reconcile this copy into the release by hand, or extend
#      runtime-provision.sh's leaf list in a follow-up — this script only
#      captures the data; it does not claim to wire it in.
#   5. shared/interfaces/product-specs/{060-stephie-banner-canvas-drag-
#      reposition,066-stephie-booking-front-door-v0-generalization}.md ->
#      shared/shared/interfaces/product-specs/ — this double "shared/
#      shared/interfaces" nesting is not a typo: it is the exact path
#      runtime-provision.sh's own link_instance_data() wildcard-discovery
#      block already scans (verified by reading that function's source
#      before writing this one).
#
# NOT this script's job — ships with any checkout automatically, git-
# TRACKED (see the manifest's own "how to read this manifest" §0
# tracked-vs-seeded distinction): instance/flavor-a/**, instance/officer-
# skills/*, instance/agents/cos.md, instance/tools/polads-sentry-triage.sh,
# instance/config/*.yml (the ~20 tracked operational-config files),
# instance/config/{contexts,projects}/*, memory/skills/*.md (non-evolved),
# memory/golden-evals/**, shared/backlog.md, shared/force-push-log.md,
# cabinet/world/{growth-ladders,morphology,show-grammar}.yml. This script
# does not copy any of these — no action needed for tracked content.
#
# TWO PATHS UNCLASSIFIED BY THE 2026-07-15 RULING, found while building
# this (flagged here rather than silently decided either way): the leaf
# .claude/settings.local.json and the runtime-series files shared/
# interfaces/{envelope-violations.jsonl,needs-ledger.jsonl} all appear in
# runtime-provision.sh's own INSTANCE_PERSISTENT_FILES list, but none of
# the three is named in either KEEP or DROP by the ruling or the manifest.
# Treated as DROP-by-caution here (same "runtime series, regenerate" shape
# as their named siblings) — not seeded by this script. Flag for the
# Captain to confirm, same as the manifest's own grey-area items.
#
# CONTAINMENT — ported from cabinet/scripts/hatch.sh's clean-room path-
# comparison idiom (lex_norm_path / resolve_for_compare below are copied
# near-verbatim from that file's "clean-room containment path helpers"
# section, credited inline, not reinvented): refuses, before any write, a
# --runtime-root or --archive-path whose directory resolves to, or nests
# under, the live tree — and, generalizing the same idiom, also refuses a
# --runtime-root or --archive-path directory that resolves to/under
# --old-root itself, so a sandbox rehearsal against a scratch old-root
# fixture is protected from the same class of self-inflicted mistake, not
# only the hardcoded production path.
#
# IDEMPOTENT (the seed half): re-running with the same arguments converges
# — directory leaves are written via `rsync -a --delete` or an equivalent
# remove-then-copy pass (stale content from a previous run's now-different
# keep-list is removed, not accumulated) and shared/cabinet.env is
# rewritten deterministically in full each run. The ARCHIVE half is
# intentionally the one exception: every run names a fresh, timestamped
# archive path by default (never silently overwrites a previous safety
# snapshot) — pass --archive-path explicitly for a fixed name instead.
#
# SECRETS DISCIPLINE: this script never echoes a secret VALUE to stdout,
# stderr, or any log — only variable NAMES and file paths, matching
# cabinet-doctor.sh's and docs/runbooks/dev-runtime-split-cutover.md's own
# existing convention.
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
LIVE_TREE="/Users/nate/captains-cabinet"

usage() {
  cat <<'EOF'
Usage: relaunch-seed.sh [flags]

Archives the old instance root in full (safety net), then writes a
curated KEEP-only subset into a runtime root's shared/ tree. See this
script's own header comment for exactly what is copied and why; the full
KEEP/DROP inventory lives in
docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md.

Flags:
  --old-root <path>          Old instance root to read FROM (read-only,
                              never written). Default: /Users/nate/captains-cabinet
  --runtime-root <path>      Runtime root to write shared/ data INTO.
                              Default: ~/.cabinet/runtime
  --archive-path <path>      Where to write the full-instance safety tar.
                              Default: a fresh ~/cabinet-relaunch-archive-
                              <UTC timestamp>.tar.gz every run.
  --telegram-token-var NAME  The cabinet/.env variable whose VALUE gets
                              rotated to a placeholder; every other line
                              (including the HQ chat id) carries unchanged.
                              Default: TELEGRAM_COS_TOKEN — the Chair/
                              cos-inbound officer's bot token. (There is no
                              single "TELEGRAM_BOT_TOKEN" variable in this
                              repo's schema; see cabinet/.env.example for
                              the real per-officer TELEGRAM_*_TOKEN names —
                              override this flag if a different officer's
                              token is the one actually in scope.)
  --skip-appsupport-archive  Skip archiving ~/Library/Application Support/
                              cabinet/ (still archives instance/ + cabinet/.env).
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

if ! printf '%s' "$TELEGRAM_TOKEN_VAR" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; then
  echo "relaunch-seed.sh: --telegram-token-var '$TELEGRAM_TOKEN_VAR' is not a valid environment-variable name" >&2
  exit 64
fi

[ -d "$OLD_ROOT" ] || { echo "relaunch-seed.sh: --old-root '$OLD_ROOT' is not a directory" >&2; exit 1; }
OLD_ROOT="$(abs_path "$OLD_ROOT")"
# --dry-run must write NOTHING, not even an empty directory: only mkdir the
# runtime root ahead of abs_path when this is a real run. abs_path's own
# not-yet-existing-leaf fallback (see its "else" branch above) still
# resolves the common case correctly without it (the default
# ~/.cabinet/runtime is built from $HOME, which is always already
# absolute), and resolve_for_compare's containment guard walks up to the
# deepest existing ancestor on its own regardless.
[ "$DRY_RUN" = "1" ] || mkdir -p "$RUNTIME_ROOT"
RUNTIME_ROOT="$(abs_path "$RUNTIME_ROOT")"

# ---- containment guards (must run BEFORE any write below) -----------------
refuse_if_nested "--runtime-root"                "$RUNTIME_ROOT"            "$LIVE_TREE"
refuse_if_nested "--archive-path's directory"    "$(dirname "$ARCHIVE_PATH")" "$LIVE_TREE"
refuse_if_nested "--runtime-root"                "$RUNTIME_ROOT"            "$OLD_ROOT"
refuse_if_nested "--archive-path's directory"    "$(dirname "$ARCHIVE_PATH")" "$OLD_ROOT"

# Officer buckets are DISCOVERED from old-root's actual instance/memory/
# tier2/ directory listing, never a hardcoded roster — cabinet/scripts/ is
# framework layer (per this repo's own product/captain-agnostic-foundation
# rule, CLAUDE.md), so a fixed list naming specific products (e.g.
# "polads-ceo") does not belong here, and discovery is also simply more
# correct: it seeds whatever officer buckets really exist on old-root,
# including ones this script's author never anticipated.
#
# PRODUCT_SPECS is deliberately the one hardcoded, explicit allowlist in
# this script: these two files are individually-reviewed durable product
# requirements the 2026-07-15 ruling named specifically — NOT "every file
# under shared/interfaces/product-specs/", which would sweep in anything
# dropped there later without the same review.
PRODUCT_SPECS="060-stephie-banner-canvas-drag-reposition.md 066-stephie-booking-front-door-v0-generalization.md"

# ---- Step 1: archive (always first — the safety net) -----------------------
do_archive() {
  echo "relaunch-seed.sh: archiving old instance -> $ARCHIVE_PATH"
  local has_env=0 has_appsupport=0
  local as_dir="$HOME/Library/Application Support/cabinet"
  [ -e "$OLD_ROOT/cabinet/.env" ] && has_env=1
  if [ "$SKIP_APPSUPPORT" != "1" ] && [ -d "$as_dir" ]; then has_appsupport=1; fi

  if [ "$has_env" != "1" ]; then
    echo "relaunch-seed.sh: WARN — $OLD_ROOT/cabinet/.env not found; archive will hold instance/ only for that half" >&2
  fi
  if [ "$SKIP_APPSUPPORT" = "1" ]; then
    echo "relaunch-seed.sh: --skip-appsupport-archive set; not archiving $as_dir"
  elif [ "$has_appsupport" != "1" ]; then
    echo "relaunch-seed.sh: NOTE — $as_dir not present on this host; nothing to archive there"
  fi

  if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would tar -czf $ARCHIVE_PATH -C \"$OLD_ROOT\" instance$( [ "$has_env" = 1 ] && printf ' cabinet/.env' )$( [ "$has_appsupport" = 1 ] && printf ' -C "%s" cabinet' "$HOME/Library/Application Support" )"
    return 0
  fi

  mkdir -p "$(dirname "$ARCHIVE_PATH")"
  if [ "$has_env" = 1 ] && [ "$has_appsupport" = 1 ]; then
    tar -czf "$ARCHIVE_PATH" -C "$OLD_ROOT" instance cabinet/.env -C "$HOME/Library/Application Support" cabinet
  elif [ "$has_env" = 1 ]; then
    tar -czf "$ARCHIVE_PATH" -C "$OLD_ROOT" instance cabinet/.env
  elif [ "$has_appsupport" = 1 ]; then
    tar -czf "$ARCHIVE_PATH" -C "$OLD_ROOT" instance -C "$HOME/Library/Application Support" cabinet
  else
    tar -czf "$ARCHIVE_PATH" -C "$OLD_ROOT" instance
  fi
  echo "relaunch-seed.sh: archive written: $ARCHIVE_PATH"
}

# ---- Step 2: seed (KEEP allowlist only) ------------------------------------

seed_cabinet_env() {
  local src="$OLD_ROOT/cabinet/.env" dst="$RUNTIME_ROOT/shared/cabinet.env"
  if [ ! -e "$src" ]; then
    echo "relaunch-seed.sh: NOTE — $src not found; shared/cabinet.env not written (a from-scratch runtime root legitimately has none yet)"
    return 0
  fi
  echo "relaunch-seed.sh: seeding cabinet/.env -> shared/cabinet.env (rotating \$$TELEGRAM_TOKEN_VAR's value; every other line, including the HQ chat id, unchanged)"
  if ! grep -qE "^${TELEGRAM_TOKEN_VAR}=" "$src"; then
    echo "relaunch-seed.sh: WARN — ${TELEGRAM_TOKEN_VAR}= not found in $src; nothing to rotate there (file will still be copied)" >&2
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would write $dst (mode 600), \$$TELEGRAM_TOKEN_VAR value -> placeholder"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  # Line-for-line rewrite: only the configured token var's VALUE changes;
  # every other line is copied byte-for-byte. No secret value is ever
  # echoed by this script — sed operates on the file directly. Written via
  # a umask-restricted subshell (not sed-then-chmod) so the file is never
  # briefly world/group-readable between creation and permission-tightening
  # — the same secrets-file discipline as the sibling cutover runbook's own
  # `install -m 600`.
  ( umask 077; sed -E "s/^(${TELEGRAM_TOKEN_VAR})=.*/\\1=__ROTATE_ME__/" "$src" > "$dst" )
  chmod 600 "$dst"
}

seed_config_leaf() {
  local rel="$1"
  local src="$OLD_ROOT/$rel" dst="$RUNTIME_ROOT/shared/$rel"
  if [ ! -e "$src" ]; then
    echo "relaunch-seed.sh: NOTE — $rel not present on old-root; skipping (never fabricated)"
    return 0
  fi
  echo "relaunch-seed.sh: seeding $rel -> shared/$rel"
  if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would copy $src -> $dst"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
}

seed_all_officer_memory() {
  local tier2_dir="$OLD_ROOT/instance/memory/tier2" officer_dir officer
  if [ ! -d "$tier2_dir" ]; then
    echo "relaunch-seed.sh: NOTE — no instance/memory/tier2 on old-root; nothing to seed there"
    return 0
  fi
  for officer_dir in "$tier2_dir"/*/; do
    [ -d "$officer_dir" ] || continue
    officer="$(basename "$officer_dir")"
    seed_officer_memory "$officer"
  done
}

seed_officer_memory() {
  local officer="$1"
  local src_dir="$OLD_ROOT/instance/memory/tier2/$officer"
  local dst_dir="$RUNTIME_ROOT/shared/instance/memory/tier2/$officer"
  if [ ! -d "$src_dir" ]; then
    echo "relaunch-seed.sh: NOTE — no instance/memory/tier2/$officer on old-root; skipping"
    return 0
  fi
  echo "relaunch-seed.sh: seeding instance/memory/tier2/$officer (top-level *.md only — reflections/, evolution-proposals/, .session-state.json excluded by construction)"
  if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would copy top-level *.md from $src_dir -> $dst_dir, create .gitkeep + reflections/.gitkeep"
    return 0
  fi
  mkdir -p "$dst_dir/reflections"
  # Converge (idempotent): drop any top-level *.md this destination
  # previously had that the source no longer has, before re-copying.
  find "$dst_dir" -maxdepth 1 -type f -name '*.md' -delete
  find "$src_dir" -maxdepth 1 -type f -name '*.md' -exec cp -p {} "$dst_dir/" \;
  : > "$dst_dir/.gitkeep"
  : > "$dst_dir/reflections/.gitkeep"
}

seed_regression_corpus() {
  local src="$OLD_ROOT/instance/fidelity/regression_corpus"
  local dst="$RUNTIME_ROOT/shared/instance/fidelity/regression_corpus"
  if [ ! -d "$src" ]; then
    echo "relaunch-seed.sh: NOTE — instance/fidelity/regression_corpus not present on old-root; skipping"
    return 0
  fi
  echo "relaunch-seed.sh: seeding instance/fidelity/regression_corpus (full current-state safety-net capture — see header NOTE: not yet wired into a release by runtime-provision.sh's own leaf list)"
  if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would rsync -a --delete $src/ -> $dst/"
    return 0
  fi
  mkdir -p "$dst"
  rsync -a --delete "$src/" "$dst/"
}

seed_product_specs() {
  local name src dst_dir="$RUNTIME_ROOT/shared/shared/interfaces/product-specs"
  for name in $PRODUCT_SPECS; do
    src="$OLD_ROOT/shared/interfaces/product-specs/$name"
    if [ ! -e "$src" ]; then
      echo "relaunch-seed.sh: NOTE — shared/interfaces/product-specs/$name not present on old-root; skipping"
      continue
    fi
    echo "relaunch-seed.sh: seeding shared/interfaces/product-specs/$name -> shared/shared/interfaces/product-specs/ (matches runtime-provision.sh's own wildcard-discovery path)"
    if [ "$DRY_RUN" = "1" ]; then
      echo "  [dry-run] would copy $src -> $dst_dir/$name"
      continue
    fi
    mkdir -p "$dst_dir"
    cp -p "$src" "$dst_dir/$name"
  done
}

main() {
  echo "relaunch-seed.sh: old-root=$OLD_ROOT runtime-root=$RUNTIME_ROOT archive-path=$ARCHIVE_PATH dry-run=$DRY_RUN"
  do_archive
  seed_cabinet_env
  seed_config_leaf "instance/config/extensions.yml"
  seed_config_leaf "instance/config/extra-mcps.json"
  seed_all_officer_memory
  seed_regression_corpus
  seed_product_specs
  if [ "$DRY_RUN" = "1" ]; then
    echo "relaunch-seed.sh: DRY RUN — nothing was written."
  else
    echo "relaunch-seed.sh: seed complete. Next: cabinet/scripts/runtime-provision.sh init/provision \"$RUNTIME_ROOT\" ... (see docs/runbooks/fresh-instance-relaunch.md)"
  fi
}
main
