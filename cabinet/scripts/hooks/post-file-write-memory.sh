#!/bin/bash
# post-file-write-memory.sh — Queue Cabinet shared artifacts for re-embedding on Write/Edit
# Only re-embeds when the file is in a watched path. No-op otherwise.
# Runs in background — never blocks the tool call (best-effort: on error exit 0,
# failures bump cabinet:hook_failures:post-file-write-memory in Redis).
#
# Library mode: backfill-memory.sh sources this file with
# POST_FILE_WRITE_MEMORY_LIB=1 to reuse the pfwm_* parsing/queueing functions —
# backfill and live hook can never drift.
#
# Content-time rules (P2e): source_created_at is derived from CONTENT ONLY —
# captain-decision heading date, frontmatter date:/created:, first dated H2
# heading, or a date in the filename. NEVER file mtime (the wrong clock: mtime
# is when the file was last touched, not when the content happened). When no
# content time is derivable we pass "" (memory_queue_embed — lib-owned — stamps
# queue time for an empty arg; at hook-fire time that IS the edit observation
# time, an honest capture clock).

# ---------------------------------------------------------------
# Shared functions (pfwm_ = post-file-write-memory)
# ---------------------------------------------------------------

# Map a file path to its watched source_type. Echoes "" when not watched.
pfwm_source_type() {
  case "$1" in
    */shared/interfaces/captain-decisions.md)
      echo "captain_decisions_file"  # H2 entries parsed separately in pfwm_queue_captain_decisions
      ;;
    */shared/interfaces/captain-patterns.md)
      echo "captain_patterns_file"
      ;;
    */shared/interfaces/captain-intents.md)
      echo "captain_intents_file"
      ;;
    */shared/interfaces/tech-radar.md)
      echo "tech_radar"
      ;;
    */shared/interfaces/product-specs/*.md)
      echo "product_spec"
      ;;
    */shared/backlog.md)
      echo "working_note"
      ;;
    */instance/memory/tier2/*/working-notes.md)
      echo "working_note"
      ;;
    */instance/memory/tier2/*/reflections/*.md)
      echo "reflection"
      ;;
    */memory/skills/*.md|*/memory/skills/evolved/*.md)
      echo "skill"
      ;;
    */product-brain/*.md)
      echo "product_brain"  # org's own product corpus (any depth) — whole-file embed
      ;;
    */constitution/*.md)
      echo "framework_file"
      ;;
    *)
      echo ""  # Not a watched path
      ;;
  esac
}

# Trust tier for a source_type: captain-authored ledgers > officer working
# artifacts > everything else (derived).
pfwm_trust_for() {
  case "$1" in
    captain_decision|captain_decisions_file|captain_patterns_file|captain_intents_file)
      echo "captain" ;;
    working_note|reflection|skill|product_brain)
      echo "officer" ;;
    *)
      echo "derived" ;;
  esac
}

# Who is writing (metadata `writer`): CLAUDE_OFFICER first, then the legacy
# hook env names, then "unknown". No hardcoded personal names.
pfwm_writer() {
  echo "${CLAUDE_OFFICER:-${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}}"
}

# Derive a content timestamp for a file — NEVER mtime. Order:
#   1. YAML frontmatter date:/created: (first block only)
#   2. first '## 20YY-MM-DD' heading
#   3. a YYYY-MM-DD in the filename
# Echoes "<date>T00:00:00Z" or "" when honestly underivable.
pfwm_content_ts() {
  local f="$1" d=""
  d=$(awk 'NR==1{if($0!="---")exit; next} /^---/{exit} /^(date|created):/{print; exit}' "$f" 2>/dev/null \
    | grep -oE '20[0-9]{2}-[0-9]{2}-[0-9]{2}' | head -1)
  [ -z "$d" ] && d=$(grep -m1 -E '^## 20[0-9]{2}-[0-9]{2}-[0-9]{2}' "$f" 2>/dev/null \
    | grep -oE '20[0-9]{2}-[0-9]{2}-[0-9]{2}' | head -1)
  [ -z "$d" ] && d=$(basename "$f" | grep -oE '20[0-9]{2}-[0-9]{2}-[0-9]{2}' | head -1)
  [ -n "$d" ] && echo "${d}T00:00:00Z"
}

# Best-effort failure counter — a hook must never fail the officer tool call,
# but silent-zero was how the pipe-table bug went unnoticed. INCR is itself
# best-effort (errors swallowed).
pfwm_count_failure() {
  redis-cli -h "${MEM_REDIS_HOST:-${REDIS_HOST:-localhost}}" -p "${MEM_REDIS_PORT:-${REDIS_PORT:-6379}}" \
    INCR "cabinet:hook_failures:post-file-write-memory" > /dev/null 2>&1
}

# Parse captain-decisions.md as H2 entries ('## 2026-.. — Title' + bullet body)
# and queue each entry as its own versioned memory row.
#   source_type = captain_decision
#   source_id   = <date>-<slug-of-title>  (stable across re-runs → upsert)
#   text        = heading + body verbatim
#   source_created_at = the heading date (T00:00:00Z)
# Echoes the number of entries queued. Callers fall back to a whole-file embed
# when this echoes 0 (format drift must degrade, not silently drop the ledger).
pfwm_queue_captain_decisions() {
  local f="$1" writer="$2" queued=0
  local entry heading date title slug meta
  # Split on '^## ' headings: \036 (RS char) is emitted before each heading,
  # plus a trailing one so `read -d` doesn't drop the final entry.
  while IFS= read -r -d $'\036' entry; do
    case "$entry" in "## "*) ;; *) continue ;; esac  # skip preamble / non-entries
    heading="${entry%%$'\n'*}"
    date=$(printf '%s\n' "$heading" | grep -oE '20[0-9]{2}-[0-9]{2}-[0-9]{2}' | head -1)
    # Slug: heading minus '## ' and the date, sanitized to [a-z0-9-]
    title=$(printf '%s\n' "$heading" | sed -E 's/^##[[:space:]]*//; s/20[0-9]{2}-[0-9]{2}-[0-9]{2}//g')
    slug=$(printf '%s\n' "$title" | tr '[:upper:]' '[:lower:]' \
      | LC_ALL=C sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' | cut -c1-64)
    [ -z "$slug" ] && slug="entry"
    meta=$(jq -nc --arg date "$date" --arg writer "$writer" \
      '{date: $date, writer: $writer, trust: "captain"}')
    if [ -n "$date" ]; then
      memory_queue_embed "captain_decision" "${date}-${slug}" "captain" "captain" \
        "$entry" "$meta" "${date}T00:00:00Z" && queued=$((queued+1))
    else
      # Undated entry: still capture it; content time is honestly absent.
      memory_queue_embed "captain_decision" "undated-${slug}" "captain" "captain" \
        "$entry" "$meta" "" && queued=$((queued+1))
    fi
  done < <(awk '/^## /{printf "\036"} {print}' "$f"; printf '\036')
  echo "$queued"
}

# Queue one watched file (requires memory.sh sourced + CABINET_ROOT set).
# captain-decisions.md → per-entry parse with whole-file fallback on 0 entries;
# everything else → whole-file embed with content-derived time + writer/trust
# metadata. Returns non-zero on failure (caller counts it).
pfwm_queue_watched_file() {
  local f="$1" writer="$2"
  local st content rel ts trust meta n
  st="$(pfwm_source_type "$f")"
  [ -z "$st" ] && return 1
  [ ! -f "$f" ] && return 1
  content=$(cat "$f") || return 1
  [ -z "$(printf '%s' "$content" | tr -d '[:space:]')" ] && return 0

  if [ "$st" = "captain_decisions_file" ]; then
    n="$(pfwm_queue_captain_decisions "$f" "$writer")"
    [ "${n:-0}" -gt 0 ] && return 0
    # zero entries parsed → fall through to the whole-file fallback embed
  fi

  rel="${f#${CABINET_ROOT}/}"
  ts="$(pfwm_content_ts "$f")"  # "" when underivable — NEVER mtime
  trust="$(pfwm_trust_for "$st")"
  meta=$(jq -nc --arg officer "$writer" --arg writer "$writer" --arg trust "$trust" \
    '{edited_by: $officer, writer: $writer, trust: $trust}')
  memory_queue_embed "$st" "$rel" "$writer" "" "$content" "$meta" "$ts"
}

# ---------------------------------------------------------------
# Library mode gate — backfill-memory.sh stops here.
# ---------------------------------------------------------------
if [ "${POST_FILE_WRITE_MEMORY_LIB:-0}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

# ---------------------------------------------------------------
# Hook body
# ---------------------------------------------------------------
HOOK_INPUT=$(cat)
WRITER="$(pfwm_writer)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"

# Extract file path (Write uses .file_path, Edit uses .file_path too)
FILE_PATH=$(echo "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE_PATH" ] && exit 0

SOURCE_TYPE="$(pfwm_source_type "$FILE_PATH")"
[ -z "$SOURCE_TYPE" ] && exit 0  # Not a watched path

# Background: source env + memory lib, queue embed. Never fails the tool call.
(
  set -a
  source "$CABINET_ROOT/cabinet/.env" 2>/dev/null
  set +a
  source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh" 2>/dev/null

  if ! declare -f memory_queue_embed > /dev/null; then
    pfwm_count_failure
    exit 0
  fi

  [ ! -f "$FILE_PATH" ] && exit 0
  pfwm_queue_watched_file "$FILE_PATH" "$WRITER" || pfwm_count_failure
) > /dev/null 2>&1 &

exit 0
