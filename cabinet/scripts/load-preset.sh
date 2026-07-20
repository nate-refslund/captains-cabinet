#!/bin/bash
# load-preset.sh — Assemble the Cabinet runtime state from framework + preset + instance.
#
# Called at container/officer start. Safe to run multiple times — idempotent.
# The loader produces runtime artifacts at /tmp/cabinet-runtime/:
#   - constitution.md     (framework constitution-base + preset addendum)
#   - safety-boundaries.md (framework base + preset safety addendum)
#
# These are the files CLAUDE.md references at session start. The loader also:
# - Applies framework base schemas + preset schemas to Neon (idempotent)
# - Populates .claude/agents/ from presets/<slug>/agents/ (with instance overlay)
#
# Usage:
#   bash cabinet/scripts/load-preset.sh         # use active preset from instance/config/active-preset
#   bash cabinet/scripts/load-preset.sh <slug>  # force a specific preset (mostly for testing)

set -uo pipefail

# Resolve repo root from this script's location when CABINET_ROOT is unset.
# Script lives at cabinet/scripts/load-preset.sh, so repo root is two levels up.
# The container default (/opt/founders-cabinet) is gone — anyone running this
# in a container should export CABINET_ROOT explicitly (start-officer.sh does).
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)}"
# CABINET_RUNTIME_DIR override: tests point it at a scratch dir so a fixture
# run can never clobber the live /tmp/cabinet-runtime officers read (same
# override discipline as action_undo's CABINET_UNDO_DIR). Default unchanged.
RUNTIME_DIR="${CABINET_RUNTIME_DIR:-/tmp/cabinet-runtime}"
ACTIVE_PRESET_FILE="$CABINET_ROOT/instance/config/active-preset"

mkdir -p "$RUNTIME_DIR"

log() {
  echo "[load-preset $(date -u +%H:%M:%S)] $1" >&2
}

# ---------------------------------------------------------------
# CABINET_ID validator (Phase 1 CP9b)
# ---------------------------------------------------------------
# cabinet_id lands in every officer-produced record. Phase 1 default is
# 'main' (single-Cabinet deployments). Phase 2 adds a second Cabinet
# instance via CABINET_MODE=multi + per-instance CABINET_ID — if the
# env var is unset in multi mode the boot aborts rather than silently
# joining the 'main' namespace. In Phase 1 default mode, the validator
# only enforces character safety so the value is safe to inject into
# JSONL log lines.
CABINET_ID="${CABINET_ID:-main}"
CABINET_MODE="${CABINET_MODE:-single}"

if ! [[ "$CABINET_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  log "ERROR: CABINET_ID='$CABINET_ID' contains invalid characters (allowed: [a-zA-Z0-9_-])"
  exit 1
fi

if [ "$CABINET_MODE" = "multi" ] && [ "$CABINET_ID" = "main" ]; then
  log "ERROR: CABINET_MODE=multi requires an explicit CABINET_ID (got the default 'main')."
  log "       Set CABINET_ID=<this-cabinet-slug> in the instance env before loading."
  exit 1
fi

export CABINET_ID CABINET_MODE

# ---------------------------------------------------------------
# peers.yml validation (Phase 2 CP3)
# ---------------------------------------------------------------
# If instance/config/peers.yml exists, validate its schema at boot so
# bad config fails loud instead of surfacing as cryptic MCP errors.
# Schema: per peer (indented at 2 spaces), required keys are role,
# endpoint, capacity, trust_level, consented_by_captain, allowed_tools.
# In single-Cabinet mode this file is informational — it's a placeholder
# for the Personal Cabinet. In multi mode every peer must be validated.
PEERS_FILE="$CABINET_ROOT/instance/config/peers.yml"
if [ -f "$PEERS_FILE" ]; then
  python3 - "$PEERS_FILE" "$CABINET_MODE" <<'PY' 2>&1
import re, sys
path, mode = sys.argv[1], sys.argv[2]
text = open(path).read()

# Extract peer entries: top-level 'peers:' block, then 2-space-indented peer ids.
peers = {}
current = None
last_list_key = None  # tracks the most-recently-declared list-valued key
                      # for yaml-list-continuation; not hardcoded to allowed_tools
for raw in text.splitlines():
    line = raw.rstrip()
    if not line or line.lstrip().startswith('#'):
        continue
    if re.match(r'^peers:\s*$', line):
        continue
    m = re.match(r'^  ([A-Za-z][A-Za-z0-9_-]*):\s*$', line)
    if m:
        current = m.group(1)
        peers[current] = {}
        last_list_key = None
        continue
    if current is None:
        continue
    mk = re.match(r'^\s{4,}([a-z_]+):\s*(.*)$', line)
    if mk:
        k, v = mk.group(1), mk.group(2).strip().strip('"\'')
        if v.startswith('[') and v.endswith(']'):
            peers[current][k] = [x.strip() for x in v[1:-1].split(',') if x.strip()]
            last_list_key = k
        elif v.lower() in ('true', 'false'):
            peers[current][k] = v.lower() == 'true'
            last_list_key = None
        elif v == '' or v == '>':
            # Empty value means either a list-will-follow or a folded-scalar.
            # For a folded scalar like notes: >, subsequent indented content
            # lines are absorbed as the value (not parsed as keys).
            if k in ('allowed_tools',):  # add other list-typed keys here if added to schema
                peers[current][k] = peers[current].get(k, [])
                last_list_key = k
            else:
                # Treat as folded-scalar start; following deeper-indented lines
                # belong to this key. last_list_key=None so continuation-line
                # regex below won't try to parse them as list items.
                peers[current][k] = ''
                last_list_key = None
        elif v:
            peers[current][k] = v
            last_list_key = None
    elif last_list_key is not None and re.match(r'^\s{4,}- (.+)$', line):
        # List-continuation for the most-recently-seen list key (not
        # hardcoded to allowed_tools — so new list fields can be added
        # to schema without reintroducing the yaml-drift bug).
        item = re.match(r'^\s{4,}- (.+)$', line).group(1).strip().strip('"\'')
        peers[current].setdefault(last_list_key, []).append(item)

# Validate each peer
REQUIRED = ['role', 'endpoint', 'capacity', 'trust_level', 'consented_by_captain', 'allowed_tools']
CAPACITIES = {'work', 'personal'}
TRUST = {'low', 'medium', 'high'}
# VALID_TOOLS must stay in sync with cabinet/mcp-server/server.py TOOLS registry.
# Update both files when a Cabinet MCP tool is added/removed.
VALID_TOOLS = {'identify', 'presence', 'availability', 'send_message', 'request_handoff'}

problems = []
for pid, p in peers.items():
    for r in REQUIRED:
        if r not in p:
            problems.append(f"peer '{pid}' missing required field: {r}")
    if 'capacity' in p and p['capacity'] not in CAPACITIES:
        problems.append(f"peer '{pid}' invalid capacity: {p['capacity']}")
    if 'trust_level' in p and p['trust_level'] not in TRUST:
        problems.append(f"peer '{pid}' invalid trust_level: {p['trust_level']}")
    if 'consented_by_captain' in p and not isinstance(p['consented_by_captain'], bool):
        problems.append(f"peer '{pid}' consented_by_captain must be boolean")
    if 'allowed_tools' in p:
        unknown = [t for t in p['allowed_tools'] if t not in VALID_TOOLS]
        if unknown:
            problems.append(f"peer '{pid}' unknown allowed_tools: {unknown}")

if problems:
    print(f"[peers.yml] {len(problems)} problem(s):", file=sys.stderr)
    for pr in problems:
        print(f"  - {pr}", file=sys.stderr)
    # In multi-mode, fail boot. In single-mode, warn and continue.
    if mode == 'multi':
        sys.exit(1)
    sys.exit(0)

active = [pid for pid, p in peers.items() if p.get('consented_by_captain')]
print(f"[peers.yml] {len(peers)} peer(s) parsed, {len(active)} with consented_by_captain=true", file=sys.stderr)
PY
  validator_exit=$?
  if [ "$validator_exit" -ne 0 ] && [ "$CABINET_MODE" = "multi" ]; then
    log "ERROR: peers.yml validation failed (multi-Cabinet mode). Fix config and retry."
    exit 1
  fi
fi

# ---------------------------------------------------------------
# Materialize the governance twins (Perfect Cabinet Wave B, day-1 legibility)
# ---------------------------------------------------------------
# posture.yml + trust-ladder.yml are the Captain-readable governance state.
# Absent files already resolve to the same consent-safe defaults in code
# (posture.py -> guardian; trust_ladder.py -> the would-like-to floor), but an
# absent file SHOWS nothing — so on first boot we materialize the shipped
# .example twins (guardian ruling / floor ladder) to make day-one governance
# state visible and editable. ABSENT-ONLY by construction: an existing file is
# NEVER overwritten (these paths are germline-listed and may be schg-locked on
# a ruled deployment — the lock skips absent paths, so the copy below can only
# ever create, never collide with the boundary). Idempotent across re-runs.
# load-preset.sh is the one step BOTH hatch.sh (step 6) and the manual runbook
# path run, so every hatch route materializes the same state.
for _gov_pair in \
  "posture.yml.example:posture.yml" \
  "trust-ladder.yml.example:trust-ladder.yml"; do
  _gov_example="$CABINET_ROOT/instance/config/${_gov_pair%%:*}"
  _gov_target="$CABINET_ROOT/instance/config/${_gov_pair##*:}"
  # -L beside -e: a DANGLING symlink pre-planted at the target fails -e but
  # must still count as present — cp would otherwise create the file THROUGH
  # the link at a symlink-chosen path (review nit 2026-07-10).
  if [ -e "$_gov_target" ] || [ -L "$_gov_target" ]; then
    log "Governance path present, untouched: ${_gov_pair##*:} (never overwritten)"
  elif [ -f "$_gov_example" ]; then
    if cp "$_gov_example" "$_gov_target" 2>/dev/null; then
      log "Materialized ${_gov_pair##*:} from its .example twin (consent-safe default: guardian posture / floor ladder — see docs/how-your-cabinet-is-governed.md)"
    else
      log "WARN: could not materialize ${_gov_pair##*:} (copy failed); absent file resolves the same safe default in code"
    fi
  else
    log "WARN: ${_gov_pair%%:*} missing — nothing to materialize (absent file resolves the safe default in code)"
  fi
done
unset _gov_pair _gov_example _gov_target

# ---------------------------------------------------------------
# Determine active preset
# ---------------------------------------------------------------
if [ -n "${1:-}" ]; then
  ACTIVE_PRESET="$1"
else
  if [ -f "$ACTIVE_PRESET_FILE" ]; then
    ACTIVE_PRESET=$(cat "$ACTIVE_PRESET_FILE" | tr -d '[:space:]')
  else
    # Default for forkers who haven't set anything
    ACTIVE_PRESET="work"
    log "WARN: $ACTIVE_PRESET_FILE not found — defaulting to 'work'"
  fi
fi

PRESET_DIR="$CABINET_ROOT/presets/$ACTIVE_PRESET"
if [ ! -d "$PRESET_DIR" ]; then
  log "ERROR: active preset '$ACTIVE_PRESET' not found at $PRESET_DIR"
  exit 1
fi

# Reject _template as an active preset — it's a scaffolding skeleton
if [ "$ACTIVE_PRESET" = "_template" ]; then
  log "ERROR: _template is not a loadable preset. Copy it to presets/<your-slug>/ first."
  exit 1
fi

# Reject empty presets (e.g. personal/ is a placeholder until Phase 2)
if [ ! -f "$PRESET_DIR/preset.yml" ]; then
  log "ERROR: preset '$ACTIVE_PRESET' is not populated (no preset.yml). Populate it first or switch to a populated preset."
  exit 1
fi

log "Loading preset: $ACTIVE_PRESET"

# ---------------------------------------------------------------
# Assemble constitution = framework base + preset addendum
# ---------------------------------------------------------------
CONSTITUTION_TMP="$RUNTIME_DIR/.constitution.md.tmp.$$"
{
  cat "$CABINET_ROOT/framework/constitution-base.md"
  echo ""
  echo "---"
  echo ""
  echo "# Preset Addendum: $ACTIVE_PRESET"
  echo ""
  if [ -f "$PRESET_DIR/constitution-addendum.md" ]; then
    # Skip the first `# ...` heading from the addendum (we just wrote one above)
    awk 'NR==1 && /^# / {next} {print}' "$PRESET_DIR/constitution-addendum.md"
  fi
} > "$CONSTITUTION_TMP"
mv "$CONSTITUTION_TMP" "$RUNTIME_DIR/constitution.md"
log "Assembled constitution → $RUNTIME_DIR/constitution.md ($(wc -l < "$RUNTIME_DIR/constitution.md") lines)"

# ---------------------------------------------------------------
# Assemble safety boundaries = framework base + preset addendum
# ---------------------------------------------------------------
SAFETY_TMP="$RUNTIME_DIR/.safety-boundaries.md.tmp.$$"
{
  cat "$CABINET_ROOT/framework/safety-boundaries-base.md"
  echo ""
  echo "---"
  echo ""
  echo "# Preset Safety Addendum: $ACTIVE_PRESET"
  echo ""
  if [ -f "$PRESET_DIR/safety-addendum.md" ]; then
    awk 'NR==1 && /^# / {next} {print}' "$PRESET_DIR/safety-addendum.md"
  fi
} > "$SAFETY_TMP"
mv "$SAFETY_TMP" "$RUNTIME_DIR/safety-boundaries.md"
log "Assembled safety boundaries → $RUNTIME_DIR/safety-boundaries.md"

# ---------------------------------------------------------------
# Apply framework base + preset schemas (idempotent)
# Phase 1 CP1 (Captain 2026-04-16): no contexts DB table. YAML files at
# instance/config/contexts/*.yml are source of truth. Target tables carry
# a context_slug column; validation in pre-tool-use hook (CP2).
# ---------------------------------------------------------------

# Product Neon schemas (external)
# Dependency order mirrors cabinet-bootstrap.sh schema_apply_list (the
# ordering source of truth — mirror list additions in BOTH scripts, Docs Must
# Track the Code): 037 + 044 alter library_records after library.sql creates
# it; 041 alters officer_tasks after 038; 042 widens officer_tasks.type after
# 039 (adds the 'reminder' kind the Captain-arm stamps). R098: 044 is the sole
# DDL adding embedded_at, which cabinet/dashboard/src/lib/library.ts INSERTs —
# omitting it broke library record create/update on fresh-hatch DBs. 046
# (embed-seam provenance singleton) runs last in the loop; the COG-1
# identity-GUC step + 047 outbox DDL follow the loop as a discrete gated
# block (identity ordered BEFORE 047 — see below; 047 is deliberately NOT a
# loop member because its apply is conditional on the identity step, and the
# matching cabinet-bootstrap.sh schema_apply_list addition is a recorded
# COG-1 follow-up). memory_embedding_stamp --if-absent then writes
# its one row — first deploy only, an existing stamp is
# never overwritten (R4 follow-up wiring, 2026-07-15).
# The work-store connection string may live ONLY in the cabinet/.env FILE:
# the Mac-native provision-local-postgres.sh writes it there (set_env_key) and
# never exports it, so on that path $NEON_CONNECTION_STRING is empty in the
# process env and the whole schema-apply block below was silently skipped
# (zero cabinet tables -> `relation "officer_tasks" does not exist` days later).
# Derive it from .env when the env var is empty, using the same grep/cut the
# sibling setup-mac.sh Step 3.5 uses (never `source`; tolerate a quoted value;
# treat the result as a single quoted psql arg). #57 fresh-hatch fix.
CONN="${NEON_CONNECTION_STRING:-}"
if [ -z "$CONN" ] && [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  CONN="$(grep -E '^NEON_CONNECTION_STRING=' "$CABINET_ROOT/cabinet/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  CONN="${CONN%\"}"; CONN="${CONN#\"}"   # tolerate a quoted value
fi
if [ -n "$CONN" ]; then
  for schema in \
    "$CABINET_ROOT/cabinet/sql/cabinet_memory.sql" \
    "$CABINET_ROOT/cabinet/sql/library.sql" \
    "$CABINET_ROOT/cabinet/sql/037-library-phase-a.sql" \
    "$CABINET_ROOT/cabinet/sql/044-library-embedding-hardening.sql" \
    "$CABINET_ROOT/cabinet/sql/contexts-neon-phase1.sql" \
    "$CABINET_ROOT/cabinet/sql/cabinet-id-neon-phase1.sql" \
    "$CABINET_ROOT/cabinet/sql/cabinet-id-neon-phase1b.sql" \
    "$CABINET_ROOT/cabinet/sql/session-memories-context-slug.sql" \
    "$CABINET_ROOT/cabinet/sql/2026-04-17-spec-034-provisioning-schema.sql" \
    "$CABINET_ROOT/cabinet/sql/038-officer-tasks.sql" \
    "$CABINET_ROOT/cabinet/sql/041-tasks-due-at.sql" \
    "$CABINET_ROOT/cabinet/sql/039-linear-to-tasks-schema.sql" \
    "$CABINET_ROOT/cabinet/sql/042-tasks-reminder-kind.sql" \
    "$CABINET_ROOT/cabinet/sql/045-org-runtime-slice.sql" \
    "$CABINET_ROOT/cabinet/sql/046-embedding-meta.sql"; do
    if [ -f "$schema" ]; then
      if psql "$CONN" -q -f "$schema" > /dev/null 2>&1; then
        log "Applied framework schema (neon): $(basename "$schema")"
      else
        log "WARN: failed to apply $schema to Neon (Cabinet will still boot; fix before new records)"
      fi
    fi
  done

  # ------------------------------------------------------------------
  # COG-1 identity GUC + outbox DDL (cognitive-core-phase-1-contract-
  # 2026-07-20.md §5.2/§8.2). ORDER IS LOAD-BEARING: the identity step runs
  # BEFORE the outbox DDL so a fresh hatch can never reach the capture
  # trigger's fail-closed identity RAISE on its first task write — which is
  # also why the DDL apply below is GATED on the identity step succeeding.
  # Identity value: CABINET_ID env (framework/missions/compiler.py
  # convention, tracked default 'main'), falling back to cabinet/.env
  # exactly like CONN above. The value lands in the DATABASE via
  # ALTER DATABASE ... SET (binds at backend session start, survives
  # pooling); it is never a tracked literal in any SQL/code file.
  # Idempotent: re-running converges the DB setting to the environment's
  # value (the env IS the identity authority on this box).
  # 047 applies STRICT + single-transaction (-v ON_ERROR_STOP=1 -1) — unlike
  # the fail-soft loop above: the capture trigger is live inside every
  # officer_tasks transaction from the moment 047 lands (§5.1), so a PARTIAL
  # apply on a fresh hatch could brick live task verbs while a fail-soft
  # rc-0 logged "Applied" over the breakage. All-or-nothing: any statement
  # failure routes rc!=0 to the WARN branch below and no partial-047 state
  # can exist. 047 is fully idempotent, and the COG-1 harness
  # (cabinet/scripts/tests/lib_cog1_harness.py apply_047) applies it in
  # EXACTLY this mode on PG17 — the green suite is the evidence.
  # ------------------------------------------------------------------
  COG1_CABINET_ID="${CABINET_ID:-}"
  if [ -z "$COG1_CABINET_ID" ] && [ -f "$CABINET_ROOT/cabinet/.env" ]; then
    COG1_CABINET_ID="$(grep -E '^CABINET_ID=' "$CABINET_ROOT/cabinet/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
    COG1_CABINET_ID="${COG1_CABINET_ID%\"}"; COG1_CABINET_ID="${COG1_CABINET_ID#\"}"
  fi
  COG1_CABINET_ID="${COG1_CABINET_ID:-main}"
  # Injection fence beneath the server-side format(%I/%L) quoting: the value
  # must match the safe identity shape before it is interpolated anywhere.
  if printf '%s' "$COG1_CABINET_ID" | grep -Eq '^[A-Za-z0-9_.-]{1,64}$'; then
    if psql "$CONN" -q -c "DO \$cog1id\$ BEGIN EXECUTE format('ALTER DATABASE %I SET app.cabinet_id = %L', current_database(), '$COG1_CABINET_ID'); END \$cog1id\$;" > /dev/null 2>&1; then
      log "Provisioned database identity GUC app.cabinet_id (COG-1 step, ordered before the outbox DDL)"
      if psql "$CONN" -q -v ON_ERROR_STOP=1 -1 -f "$CABINET_ROOT/cabinet/sql/047-officer-tasks-outbox.sql" > /dev/null 2>&1; then
        log "Applied framework schema (neon): 047-officer-tasks-outbox.sql"
      else
        log "WARN: failed to apply 047-officer-tasks-outbox.sql (outbox capture not installed; task verbs unaffected — fix and re-run preset load)"
      fi
    else
      log "WARN: could not provision app.cabinet_id — SKIPPING 047-officer-tasks-outbox.sql so task writes never hit the fail-closed identity refusal (fix identity, re-run preset load)"
    fi
  else
    log "WARN: CABINET_ID '$COG1_CABINET_ID' fails the safe shape ([A-Za-z0-9_.-], max 64) — SKIPPING the identity step AND 047-officer-tasks-outbox.sql"
  fi

  # EMBED-SEAM stamp (R4 follow-up, 2026-07-15 — ends 046's dormant-ship):
  # ensure cabinet_embedding_meta records the provider/model/dims the store
  # was built with, so cabinet-doctor's dims-drift probe has a stamped row to
  # compare against. --if-absent: only an unstamped store gains a row (first
  # deploy after the wiring / fresh estate); an existing stamp is PROVENANCE
  # and is never overwritten here — this runs at EVERY officer start, so an
  # unconditional upsert would re-bless a config flip and silently erase the
  # doctor's DIMS DRIFT WARN (re-stamping belongs to the re-embed organ, or a
  # captain after a verified full backfill). Values ride the stamp's
  # parameterized psql -v seam. Subshell isolation keeps memory.sh's .env
  # back-fill out of the loader's environment (caller-set values win inside
  # it). Fail-soft like the schema arms above — never blocks preset load.
  if ( source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh" > /dev/null 2>&1 && \
       memory_embedding_stamp --if-absent > /dev/null 2>&1 ); then
    log "Ensured cabinet_embedding_meta stamp (first deploy inserts; existing provenance preserved)"
  else
    log "WARN: failed to stamp cabinet_embedding_meta — doctor dims-drift probe reports SKIP until stamped (next run retries)"
  fi

  # Preset-specific schemas (Neon)
  if [ -f "$PRESET_DIR/schemas.sql" ]; then
    if psql "$CONN" -q -f "$PRESET_DIR/schemas.sql" > /dev/null 2>&1; then
      log "Applied preset schema: $ACTIVE_PRESET/schemas.sql"
    else
      log "WARN: failed to apply preset schema"
    fi
  fi
else
  log "WARN: no work-store connection string in env or cabinet/.env — skipping Neon schema application"
fi

# Cabinet postgres schemas (internal) — additive migrations for Phase 1+
if [ -n "${DATABASE_URL:-}" ]; then
  for schema in \
    "$CABINET_ROOT/cabinet/sql/contexts-cabinet-phase1.sql" \
    "$CABINET_ROOT/cabinet/sql/cabinet-id-phase1.sql" \
    "$CABINET_ROOT/cabinet/sql/cabinet-id-phase1b.sql"; do
    if [ -f "$schema" ]; then
      if psql "$DATABASE_URL" -q -f "$schema" > /dev/null 2>&1; then
        log "Applied framework schema (cabinet-pg): $(basename "$schema")"
      else
        log "WARN: failed to apply $schema to cabinet postgres"
      fi
    fi
  done
else
  log "WARN: DATABASE_URL not set — skipping cabinet postgres schema application"
fi

# ---------------------------------------------------------------
# Populate .claude/agents/ from preset + instance overlay
# ---------------------------------------------------------------
AGENTS_DIR="$CABINET_ROOT/.claude/agents"
mkdir -p "$AGENTS_DIR"

# 1. Copy preset agents (baseline). Single source of truth for the
# hired-vs-scaffold distinction is `cabinet/mcp-scope.yml`: agents
# listed under `agents:` are hired (copied to .claude/agents/), agents
# under `scaffolds:` are staged but not activated. The SCAFFOLD banner
# inside role-def .md files is now advisory-only for human readers;
# the loader does not inspect it. This keeps a single authoritative
# list instead of three drift-prone ones (per Apr 17 review).
MCP_SCOPE_FILE="$CABINET_ROOT/cabinet/mcp-scope.yml"

# Extract hired agent slugs from `agents:` section. Awk walks sections
# and emits only the direct children of `agents:` (two-space indent,
# trailing colon). Tolerates comments and the universal:/cabinet: keys.
list_hired_agents() {
  [ -f "$MCP_SCOPE_FILE" ] || return
  awk '
    /^agents:[[:space:]]*$/     { section = "agents"; next }
    /^scaffolds:[[:space:]]*$/  { section = "scaffolds"; next }
    /^[A-Za-z]/                 { section = "" }
    section == "agents" && /^  [A-Za-z][A-Za-z0-9_-]*:[[:space:]]*$/ {
      name = $0
      sub(/^  /, "", name)
      sub(/:.*$/, "", name)
      print name
    }
  ' "$MCP_SCOPE_FILE"
}

if [ -d "$PRESET_DIR/agents" ]; then
  if [ ! -f "$MCP_SCOPE_FILE" ]; then
    log "ERROR: $MCP_SCOPE_FILE missing — cannot determine hired agents. Skipping agent population."
  else
    HIRED=$(list_hired_agents)
    if [ -z "$HIRED" ]; then
      log "WARN: no agents listed in $MCP_SCOPE_FILE under 'agents:' — skipping."
    else
      copied=0
      skipped=0
      drifted=0
      for src in "$PRESET_DIR/agents"/*.md; do
        [ -f "$src" ] || continue
        basename=$(basename "$src")
        [ "$basename" = "TEMPLATE.md" ] && continue
        slug="${basename%.md}"
        # Copy iff the slug is in the hired list from mcp-scope.yml.
        if echo "$HIRED" | grep -qx "$slug"; then
          # Clobber guard (audit finding #5, 2026-07-07): .claude/agents/ is
          # derived + gitignored, so a hand-edited target would be silently
          # and invisibly destroyed by this cp. Refuse the overwrite when ALL
          # of: (a) no instance overlay exists for this slug (an overlay wins
          # below anyway, so preset clobber is harmless), (b) the target
          # differs from the preset source, and (c) the target's sha256
          # differs from the last-generated marker (.<slug>.md.gen.sha —
          # written after every loader copy; if the marker is missing we
          # cannot prove the drift is loader-made, so we protect it).
          # The drifted content is preserved at <slug>.md.clobbered-backup
          # (non-.md suffix so Claude Code never registers it as an agent).
          # Resolution: move the hand edits into instance/agents/<slug>.md
          # (the overlay slot) or delete the drifted target, then re-run.
          target="$AGENTS_DIR/$basename"
          overlay="$CABINET_ROOT/instance/agents/$basename"
          marker="$AGENTS_DIR/.$basename.gen.sha"
          if [ -f "$target" ] && [ ! -f "$overlay" ] && ! cmp -s "$src" "$target"; then
            target_sha=$(shasum -a 256 "$target" | awk '{print $1}')
            marker_sha=$(cat "$marker" 2>/dev/null || true)
            if [ "$target_sha" != "$marker_sha" ]; then
              cp "$target" "$target.clobbered-backup"
              log "WARN: REFUSING to overwrite $target — it differs from both the preset source and the last loader-generated copy, and no instance overlay exists (instance/agents/$basename). Hand edits preserved in place + backed up to $basename.clobbered-backup. Move the edits into instance/agents/$basename (the overlay slot) or delete the drifted file, then re-run load-preset."
              drifted=$((drifted + 1))
              continue
            fi
          fi
          cp "$src" "$target"
          shasum -a 256 "$target" | awk '{print $1}' > "$marker"
          copied=$((copied + 1))
        else
          skipped=$((skipped + 1))
        fi
      done
      log "Populated agents from preset: $copied hired (per mcp-scope.yml), $skipped staged, $drifted drift-protected (NOT overwritten)"

      # Partition hired slugs by whether a role definition exists in the
      # ACTIVE preset ∪ instance overlay. mcp-scope.yml is shared across
      # deployments (e.g. the functional five stay listed for the Mini's
      # work preset while hq runs portfolio), so a hired slug with no
      # definition here is NOT an error — but it must not become an
      # expected-active ghost in Redis, and a stale .claude/agents/<slug>.md
      # derived from a previously-active preset must not keep booting it.
      HIRED_DEFINED=""
      HIRED_MISSING=""
      for slug in $HIRED; do
        if [ -f "$PRESET_DIR/agents/$slug.md" ] || [ -f "$CABINET_ROOT/instance/agents/$slug.md" ]; then
          HIRED_DEFINED="$HIRED_DEFINED $slug"
        else
          HIRED_MISSING="$HIRED_MISSING $slug"
          # Delete ONLY the stale derived copy for this hired slug —
          # .claude/agents/ is generated (gitignored); other files untouched.
          if [ -f "$AGENTS_DIR/$slug.md" ]; then
            rm -f "$AGENTS_DIR/$slug.md"
            log "Removed stale derived agent .claude/agents/$slug.md (no definition in preset '$ACTIVE_PRESET' ∪ instance overlay)"
          fi
        fi
      done
      if [ -n "$HIRED_MISSING" ]; then
        log "INFO: hired in mcp-scope.yml but no role definition in preset '$ACTIVE_PRESET' ∪ instance overlay — skipped (not expected-active):$HIRED_MISSING"
      fi

      # Mark every DEFINED hired agent as expected-active in Redis so
      # officer-supervisor auto-respawns them after restart + sends Captain
      # the restart-alert. Single source of truth stays mcp-scope.yml
      # `agents:` ∩ available definitions; this is just propagation into
      # Redis so the supervisor's existing expected-active mechanism applies
      # to preset-loaded rosters, not only to officers explicitly created
      # via create-officer.sh (which sets the key in Step 8).
      if command -v redis-cli >/dev/null 2>&1; then
        REDIS_HOST_LP="${REDIS_HOST:-127.0.0.1}"
        REDIS_PORT_LP="${REDIS_PORT:-6379}"
        marked=0
        for slug in $HIRED_DEFINED; do
          if redis-cli -h "$REDIS_HOST_LP" -p "$REDIS_PORT_LP" SET "cabinet:officer:expected:$slug" "active" >/dev/null 2>&1; then
            marked=$((marked + 1))
          fi
        done
        log "Marked $marked preset-hired agents as expected-active in Redis"
      fi
    fi
  fi
fi

# 2. Instance overrides (take precedence). Also refresh the generated-copy
# marker so the clobber guard above compares future targets against what the
# loader ACTUALLY last wrote (the overlay), not the preset baseline.
if [ -d "$CABINET_ROOT/instance/agents" ]; then
  for src in "$CABINET_ROOT/instance/agents"/*.md; do
    [ -f "$src" ] || continue
    basename=$(basename "$src")
    cp "$src" "$AGENTS_DIR/$basename"
    shasum -a 256 "$AGENTS_DIR/$basename" | awk '{print $1}' > "$AGENTS_DIR/.$basename.gen.sha"
    log "Instance agent override: $basename"
  done
fi

# 3. Role-registry parity check (W6/§4.3-4, 2026-07-09). Now that
# .claude/agents/ reflects the loaded preset, surface any drift against the
# evolution loop's live registry (instance/roles/active/) — the second boot
# surface behind the flag-gated CABINET_BOOT_ROLES_ACTIVE wire in
# lib/officer-boot.sh. WARN-ONLY here (a preset load must not brick on a
# registry finding); the audit's exit code gates the FLAG FLIP, not the load.
if [ -x "$CABINET_ROOT/cabinet/scripts/audit-role-parity.sh" ]; then
  _rp_out=$(mktemp /tmp/role-parity.XXXXXX)
  if CABINET_ROOT="$CABINET_ROOT" bash "$CABINET_ROOT/cabinet/scripts/audit-role-parity.sh" >"$_rp_out" 2>&1; then
    log "Role-registry parity: OK (instance/roles/active/ agrees with .claude/agents/)"
  else
    log "WARN: role-registry parity drift — do NOT flip CABINET_BOOT_ROLES_ACTIVE=1 until resolved:"
    while IFS= read -r _rp_line; do log "  $_rp_line"; done < "$_rp_out"
  fi
  rm -f "$_rp_out"
fi

# 4. Measurement corpus seed (audit #27). The framework ships
# framework/measurement/{role_evals,scenarios}/ EMPTY (egg row R006); the
# runners discover an INSTANCE seed dir (instance/measurement/<kind>) so
# per-role evals + org scenarios actually run. Without this copy the role-eval
# runner returns [] forever and the scenario safety-gate passes vacuously.
# Idempotent (cp -f overwrites); silent when a preset ships no measurement seed.
for _mk in role_evals scenarios; do
  _src="$PRESET_DIR/measurement/$_mk"
  _dst="$CABINET_ROOT/instance/measurement/$_mk"
  if [ -d "$_src" ]; then
    mkdir -p "$_dst"
    if cp -f "$_src"/*.py "$_dst"/ 2>/dev/null; then
      log "Seeded measurement/$_mk from preset '$ACTIVE_PRESET'"
    fi
  fi
done

log "Preset '$ACTIVE_PRESET' loaded successfully"
