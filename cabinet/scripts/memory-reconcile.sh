#!/bin/bash
# memory-reconcile.sh — Nightly hash-based reconcile of watched knowledge
# files into Cabinet Memory (P3d, 2026-07-07).
#
# WHY: every capture hook is best-effort exit-0 BY DESIGN (a hook must never
# fail the officer tool call) — so a missed hook fire, a dead worker window,
# or an edit made outside an officer session leaves cabinet_memory silently
# stale, invisible until a recall miss. This job is the netting UNDER the
# hooks: recompute content hashes for the same watch list as
# post-file-write-memory.sh and queue-embed anything cabinet_memory does not
# hold current content for. The daily falsifier line (falsifier-report.py
# memory_ingestion) is the matching OBSERVABILITY half; this is the REPAIR
# half.
#
# COMPARISON LADDER (per row, spec P3d):
#   1. row carries metadata->>'content_sha256'  → compare hashes; differ ⇒ queue
#   2. row exists without a stored hash         → skip (source_id existence —
#      the row is hook-owned; hooks re-queue on every Write/Edit, so a
#      hook-captured row is current-by-construction at capture time)
#   3. no row                                    → queue
# Rows queued by THIS script carry content_sha256 (+ via: memory-reconcile),
# so reconcile-owned rows get true hash-drift detection on later nights.
#
# IDEMPOTENT: the memory-worker upserts via ON CONFLICT on the partial-unique
# index idx_cm_unique_source (source_type, source_id) WHERE superseded_by IS
# NULL — re-queues update in place, never duplicate.
#
# WATCH LIST — parity with post-file-write-memory.sh (grep it before
# extending either; the two lists stay in sync BY DESIGN, and
# test_bootstrap_memory_chain.py pins the hook⊆reconcile direction):
# tech-radar.md, product-specs/*.md, shared/backlog.md, tier2
# working-notes.md + reflections/*.md, memory/skills (evolved/ included),
# framework/constitution-base.md + safety-boundaries-base.md, the org vault
# corpus vault/**/*.md (source_type product_brain — the DB taxonomy name
# predates the 2026-07-16 vault rename; the legacy product-brain/ dir is
# still walked for un-migrated checkouts), and docs/**/*.md
# (source_type framework_doc — the docs tree joined the memory index
# 2026-07-17, vault wave).
#   NOTE — the hook twin lives in the schg-locked germline hooks dir: its
#   vault/ + docs/ watch patterns land via
#   patches/germline-vault-hook-watch-2026-07-17.patch (Captain unlock
#   ceremony; see docs/proposals/germline-vault-hook-watch-addendum-
#   2026-07-17.md). Until that ceremony THIS nightly walk is the coverage
#   netting for vault/ and docs/ writes.
#   DELIBERATE EXCEPTION — shared/interfaces/captain-decisions.md is NOT
#   reconciled here (2026-07-07): its entry-level ingest moved to the
#   captain-law append-interface wave, which stamps provenance-rich rows
#   under a date-slug source_id scheme ({trust: captain, writer: system});
#   replaying the legacy cd-<date>-<rownum> table parser would mint content
#   duplicates under a second id scheme. captain_decision liveness is
#   covered by the falsifier's WIRED-class ALERT — if that path goes quiet
#   for 7d it pages the digest, and extending this netting is the deliberate
#   follow-up, not a silent guess here.
#
# READ-ONLY against Postgres (one constant SELECT snapshot); the only writes
# are XADDs to the embed queue (cabinet:memory:embed_queue). Untrusted file
# content flows ONLY through jq --arg (memory_queue_embed) and awk ENVIRON —
# never interpolated into SQL/awk/shell program text.
#
# Run:       bash cabinet/scripts/memory-reconcile.sh
# Scheduled: fleet manifest row `memory-reconcile` in cabinet/services.yml
#            (03:30 daily), rendered via cabinet/scripts/generate-plists.py to
#            cabinet/launchd/generated/com.cabinet.memory-reconcile.plist.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

# launchd runs carry no login env — source cabinet/.env ourselves (set -a so
# memory_queue_embed's redis-cli + the worker downstream inherit). Secrets
# stay in the env file; nothing here echoes values.
set -a
source "$CABINET_ROOT/cabinet/.env" 2>/dev/null
set +a

# Mac-native default (Docker exports REDIS_HOST=redis-<slug>; the bare
# `redis` hostname never resolves on Mac — same fix as record-experience.sh).
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"

source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh"

# Shared hook parsing library (pfwm_content_ts et al.) — same content-time
# derivation the live hook uses, so reconcile-minted rows carry CONTENT time,
# never file mtime (mtime is the wrong clock: a drifted file or reconcile
# re-queue would overwrite the hook's content-derived source_created_at via
# the worker's ON CONFLICT upsert, corrupting the --as-of fence + recency).
POST_FILE_WRITE_MEMORY_LIB=1 source "$CABINET_ROOT/cabinet/scripts/hooks/post-file-write-memory.sh"

: "${NEON_CONNECTION_STRING:?NEON_CONNECTION_STRING is required (cabinet/.env) — cannot snapshot cabinet_memory}"

log() { echo "[memory-reconcile $(date -u +%Y-%m-%dT%H:%M:%SZ)] $1"; }

# =============================================================
# 1. Snapshot current holdings: (source_type, source_id, stored hash)
#    ONE constant read-only SELECT — no untrusted input near the SQL.
# =============================================================
# PORTABLE mktemp (2026-07-28). `mktemp -t memory-reconcile` is a BSD/macOS
# idiom: GNU coreutils REQUIRES the template to end in at least three X's and
# fails outright with "too few X's in template". On Linux — the Docker
# deployment target, and CI — SNAP_TSV came back EMPTY, the snapshot redirect
# then failed on `> ""`, and the run aborted logging "cabinet_memory snapshot
# query failed", blaming the query for a temp-file error. So the nightly
# reconcile (cabinet/services.yml, 03:30 daily) queued NOTHING on every Linux
# deployment, with a plausible-looking log line. Explicit dir + X's is the one
# form both implementations accept identically.
SNAP_TSV="$(mktemp "${TMPDIR:-/tmp}/memory-reconcile.XXXXXX")"
trap 'rm -f "$SNAP_TSV"' EXIT

if ! psql "$NEON_CONNECTION_STRING" -X -q -t -A -F $'\t' -c "
  SELECT source_type, source_id, coalesce(metadata->>'content_sha256','')
  FROM cabinet_memory
  WHERE superseded_by IS NULL
    AND source_id IS NOT NULL
    AND source_type IN ('tech_radar','product_spec','working_note',
                        'reflection','skill','framework_file',
                        'product_brain','framework_doc')
" > "$SNAP_TSV" 2>/dev/null; then
  log "cabinet_memory snapshot query failed — aborting (nothing queued)"
  exit 1
fi

CHECKED=0; QUEUED=0; CURRENT=0; HOOK_OWNED=0; EMPTY=0; QFAIL=0

# =============================================================
# 2. Reconcile one file: hash → ladder → queue when stale/missing
# =============================================================
reconcile_file() {
  local st="$1" f="$2"
  [ -f "$f" ] || return 0
  local rel="${f#"$CABINET_ROOT"/}"
  CHECKED=$((CHECKED + 1))

  local content
  content=$(cat "$f")
  if [ -z "$(printf '%s' "$content" | tr -d '[:space:]')" ]; then
    EMPTY=$((EMPTY + 1))            # memory_queue_embed refuses these anyway
    return 0
  fi
  # Hash EXACTLY the string that gets queued ($(cat) strips trailing
  # newlines), so tonight's stored hash equals a later night's recompute.
  local sha
  sha=$(printf '%s' "$content" | shasum -a 256 | awk '{print $1}')

  # Lookup via awk ENVIRON field-equality — paths never touch program text.
  local row
  row=$(RS_T="$st" RS_I="$rel" \
    awk -F '\t' '$1==ENVIRON["RS_T"] && $2==ENVIRON["RS_I"] {print "FOUND:" $3; exit}' \
    "$SNAP_TSV")

  case "$row" in
    "FOUND:$sha")                    # stored hash matches — current
      CURRENT=$((CURRENT + 1)); return 0 ;;
    "FOUND:")                        # exists, no hash — hook-owned (ladder 2)
      HOOK_OWNED=$((HOOK_OWNED + 1)); return 0 ;;
    FOUND:*)                         # hash drift (ladder 1)
      ;;
    "")                              # missing (ladder 3)
      ;;
  esac

  local meta ts
  # TRUST MUST RIDE ALONG (2026-07-28). memory_embed's upsert does
  # `metadata = EXCLUDED.metadata` — a full REPLACE, not a merge — so whatever
  # this queues IS the row's final metadata. Queuing only {sha, via} therefore
  # stripped the trust tier and writer off every file it touched, and
  # memory_search renders a trust-less row as `derived`
  # (COALESCE(...metadata->>'trust'..., 'derived')): a captain-tier or
  # officer-tier artifact came back from recall labelled derived. Measured on
  # the live store: 146/146 rows carrying `via: memory-reconcile` had no
  # `trust` and no `writer` key at all. pfwm_trust_for is the SAME resolver the
  # hook and backfill use, so all three writers now agree per source_type.
  meta=$(jq -nc --arg sha "$sha" --arg trust "$(pfwm_trust_for "$st")" \
    --arg writer "${CLAUDE_OFFICER:-system}" \
    '{content_sha256: $sha, via: "memory-reconcile", trust: $trust, writer: $writer}')
  # Content-derived time ONLY (frontmatter/dated-heading/filename) — "" when
  # honestly underivable (memory_queue_embed stamps queue time for ""), NEVER
  # mtime (P2e content-time rule; see post-file-write-memory.sh header).
  ts="$(pfwm_content_ts "$f")"
  if memory_queue_embed "$st" "$rel" "" "" "$content" "$meta" "$ts"; then
    QUEUED=$((QUEUED + 1))
  else
    QFAIL=$((QFAIL + 1))
  fi
}

# =============================================================
# 3. Walk the watch list (post-file-write-memory.sh parity)
# =============================================================
reconcile_file tech_radar "$CABINET_ROOT/shared/interfaces/tech-radar.md"
reconcile_file working_note "$CABINET_ROOT/shared/backlog.md"

while IFS= read -r f; do reconcile_file product_spec "$f"; done \
  < <(find "$CABINET_ROOT/shared/interfaces/product-specs" -type f -name '*.md' 2>/dev/null)

while IFS= read -r f; do reconcile_file working_note "$f"; done \
  < <(find "$CABINET_ROOT/instance/memory/tier2" -type f -name 'working-notes.md' 2>/dev/null)

while IFS= read -r f; do reconcile_file reflection "$f"; done \
  < <(find "$CABINET_ROOT/instance/memory/tier2" -type f -path '*/reflections/*' -name '*.md' 2>/dev/null)

while IFS= read -r f; do reconcile_file skill "$f"; done \
  < <(find "$CABINET_ROOT/memory/skills" -type f -name '*.md' 2>/dev/null)

while IFS= read -r f; do reconcile_file framework_file "$f"; done \
  < <(ls "$CABINET_ROOT"/framework/constitution-base.md \
        "$CABINET_ROOT"/framework/safety-boundaries-base.md 2>/dev/null)

# Org vault corpus (the cabinet vault; legacy product-brain/ still walked for
# un-migrated checkouts). source_type stays product_brain — the cabinet_memory
# row taxonomy predates the vault rename and renaming it would orphan every
# existing row's (source_type, source_id) upsert identity.
while IFS= read -r f; do reconcile_file product_brain "$f"; done \
  < <(find "$CABINET_ROOT/vault" "$CABINET_ROOT/product-brain" \
        -type f -name '*.md' 2>/dev/null)

# Framework docs tree (plans/proposals/runbooks/specs) — joined the memory
# index 2026-07-17 (vault wave): officers must be able to recall the org's
# own reference docs, not only re-read them by path.
while IFS= read -r f; do reconcile_file framework_doc "$f"; done \
  < <(find "$CABINET_ROOT/docs" -type f -name '*.md' 2>/dev/null)

# =============================================================
# 4. Summary (one line/night — the services.yml expected floor)
# =============================================================
log "checked=$CHECKED queued=$QUEUED current=$CURRENT hook-owned=$HOOK_OWNED empty=$EMPTY queue-failures=$QFAIL"

if [ "$QFAIL" -gt 0 ]; then
  log "some queue pushes failed (redis unreachable?) — exiting non-zero so launchd surfaces it"
  exit 1
fi
exit 0
