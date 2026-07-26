#!/bin/bash
# bootstrap-roles.sh — seed the active officer roster into org_roles + instance/roles/active/
#
# Without this, mission compilation fails:
#   $ python3 cabinet/scripts/org-runtime.py roles list --product-slug X
#   []
#   $ ... outcome compile ...
#   unknown role for X: cos
#
# The cabinet has THREE places where role definitions live:
#   1. presets/<preset>/agents/<slug>.md     (Claude Code agent definitions,
#                                             copied to .claude/agents by
#                                             sync-agents.sh; instance/agents/
#                                             overlays for generated roles)
#   2. instance/roles/active/<slug>.yml      (durable role config + lineage
#                                             pointer; read by notify-officer,
#                                             captain-rule-encoder broadcast,
#                                             watchdog, etc.)
#   3. org_roles table in cabinet/cache/org-runtime.sqlite3 (Store ledger;
#                                             read by mission compiler when
#                                             assigning work-graph nodes)
#
# sync-agents.sh handles (1). This script handles (2) and (3). Idempotent +
# UPDATE-IN-PLACE: a role already seeded in either surface gets its
# roster-owned fields (title/model/capabilities/authority_level/officer_type)
# refreshed from the chosen roster (created_at preserved; org_roles updated
# through the Store with a proper role.updated event).
#
# ROSTER SOURCE — three paths, in precedence order:
#   --roster <yml>     explicit roster file (e.g. instance/config/roster.yml
#                      or instance/config/hq-instance.yml). The file must
#                      carry a top-level `roster:` block; per role (2-space
#                      key, 4-space fields):
#                        roster:
#                          cos:
#                            title: First Mate
#                            type: fulltime        # or consultant (default fulltime)
#                            model: claude-fable-5
#                            capabilities: [cap1, cap2]
#                            authority_level: captain_proxy
#                      Other per-role keys (telegram:, …) are ignored here —
#                      they belong to other consumers.
#   (no --roster)      if instance/config/roster.yml exists it is preferred
#                      automatically (the chosen source is printed).
#   built-in seed      otherwise the 5-officer functional seed (work preset:
#                      cos/cto/cpo/cro/coo). Unchanged behavior.
#
# PRUNE — roles in instance/roles/active/ that are NOT in the chosen roster:
#   default            WARN only (drift report).
#   --prune            retire them: yml moved to instance/roles/archive/ and
#                      org_roles state set to retired (role.retired event).
#
# Usage:
#   bash cabinet/scripts/bootstrap-roles.sh                       # uses active product slug
#   bash cabinet/scripts/bootstrap-roles.sh --product-slug X      # explicit override
#   bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml --prune

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

# Read active product slug from instance/config/active-project.txt unless
# overridden via --product-slug.
PRODUCT_SLUG=""
ROSTER_FILE=""
PRUNE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --product-slug) PRODUCT_SLUG="$2"; shift 2 ;;
    --product-slug=*) PRODUCT_SLUG="${1#--product-slug=}"; shift ;;
    --roster) ROSTER_FILE="$2"; shift 2 ;;
    --roster=*) ROSTER_FILE="${1#--roster=}"; shift ;;
    --prune) PRUNE=1; shift ;;
    -h|--help)
      sed -n '1,57p' "$0" | sed 's/^# \{0,1\}//' >&2
      exit 0
      ;;
    *) echo "[bootstrap-roles] unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$ROSTER_FILE" ] && [ ! -f "$ROSTER_FILE" ]; then
  echo "[bootstrap-roles] --roster file not found: $ROSTER_FILE" >&2
  exit 2
fi

# Roster-source preference: explicit --roster wins; otherwise a deployment-
# local instance/config/roster.yml (written by cabinet-init) is preferred
# over the built-in functional seed. Always print which source won.
if [ -n "$ROSTER_FILE" ]; then
  echo "[bootstrap-roles] roster source: $ROSTER_FILE (--roster)"
elif [ -f "$CABINET_ROOT/instance/config/roster.yml" ]; then
  ROSTER_FILE="$CABINET_ROOT/instance/config/roster.yml"
  echo "[bootstrap-roles] roster source: instance/config/roster.yml (auto-preferred; no --roster given)"
else
  echo "[bootstrap-roles] roster source: built-in functional seed (no --roster, no instance/config/roster.yml)"
fi

if [ -z "$PRODUCT_SLUG" ]; then
  ACTIVE_PROJECT_FILE="$CABINET_ROOT/instance/config/active-project.txt"
  if [ -f "$ACTIVE_PROJECT_FILE" ]; then
    PRODUCT_SLUG="$(tr -d '[:space:]' < "$ACTIVE_PROJECT_FILE")"
  fi
fi
if [ -z "$PRODUCT_SLUG" ]; then
  echo "[bootstrap-roles] no product slug — pass --product-slug or set instance/config/active-project.txt" >&2
  exit 1
fi

echo "[bootstrap-roles] product_slug=$PRODUCT_SLUG"
echo "[bootstrap-roles] CABINET_ROOT=$CABINET_ROOT"

# -----------------------------------------------------------------------------
# Role definitions — the 5 active officers + per-slug capabilities/authority.
# Capabilities mirror cabinet/officer-capabilities.conf where overlap exists;
# the slugs are the canonical set referenced by the mission compiler.
# -----------------------------------------------------------------------------

ACTIVE_DIR="$CABINET_ROOT/instance/roles/active"
mkdir -p "$ACTIVE_DIR"

# Update or retire an existing org_roles row through the same Store the
# `roles define` CLI path uses — appends a proper org_event (role.updated /
# role.retired) + lineage row, then bumps the org_roles row. org_events is
# append-only; never edit the ledger directly.
#   org_roles_sync update <product_slug> <slug> <title> <caps_csv> <auth>
#   org_roles_sync retire <product_slug> <slug>
org_roles_sync() {
  local op="$1" pslug="$2" slug="$3" title="${4:-}" caps="${5:-}" auth="${6:-}"
  OP="$op" PSLUG="$pslug" RSLUG="$slug" RTITLE="$title" RCAPS="$caps" RAUTH="$auth" \
  python3 - <<'PY'
import os
import sys

sys.path.insert(0, os.path.join(os.environ["CABINET_ROOT"], "cabinet", "scripts", "lib"))
from org_runtime import Store, as_json, insert_role_lineage, role_key, utc_now  # noqa: E402

op = os.environ["OP"]
pslug = os.environ["PSLUG"]
slug = os.environ["RSLUG"]
store = Store()
row = store.row(
    "SELECT * FROM org_roles WHERE product_slug = ? AND role_slug = ?", (pslug, slug)
)
if row is None:
    print(f"[bootstrap-roles] WARN {slug}: no org_roles row under product '{pslug}' — nothing to {op}")
    raise SystemExit(0)

now = utc_now()
if op == "update":
    title = os.environ["RTITLE"]
    caps = [c for c in os.environ["RCAPS"].split(",") if c]
    auth = os.environ["RAUTH"]
    # Store.row_to_dict already parses capabilities_json -> capabilities list.
    old_caps = row["capabilities"] or []
    changes = {}
    if row["role_name"] != title:
        changes["role_name"] = {"from": row["role_name"], "to": title}
    if old_caps != caps:
        changes["capabilities"] = {"from": old_caps, "to": caps}
    if row["authority_level"] != auth:
        changes["authority_level"] = {"from": row["authority_level"], "to": auth}
    if row["state"] != "active":
        changes["state"] = {"from": row["state"], "to": "active"}
    if not changes:
        print(f"[bootstrap-roles] {slug}: org_roles row already matches roster")
        raise SystemExit(0)
    new_version = int(row["version"]) + 1
    payload = {
        "product_slug": pslug,
        "role_slug": slug,
        "old_version": row["version"],
        "new_version": new_version,
        "changes": changes,
        "source": "bootstrap-roles.sh roster sync",
    }
    event = store.append_event(
        "role.updated", pslug, "org_role", role_key(pslug, slug), "bootstrap-roles.sh", payload
    )
    store.conn.execute(
        """
        UPDATE org_roles
           SET role_name = ?, capabilities_json = ?, authority_level = ?,
               state = 'active', version = ?, latest_event_id = ?, updated_at = ?
         WHERE product_slug = ? AND role_slug = ?
        """,
        (title, as_json(caps), auth, new_version, event["event_id"], now, pslug, slug),
    )
    insert_role_lineage(
        store, pslug, slug, event["event_id"], "role_updated",
        "Roster sync: " + ", ".join(sorted(changes)) + " refreshed from roster",
    )
    store.conn.commit()
    print(f"[bootstrap-roles] {slug}: org_roles row updated ({', '.join(sorted(changes))})")
elif op == "retire":
    if row["state"] == "retired":
        print(f"[bootstrap-roles] {slug}: org_roles row already retired")
        raise SystemExit(0)
    new_version = int(row["version"]) + 1
    payload = {
        "product_slug": pslug,
        "role_slug": slug,
        "old_version": row["version"],
        "new_version": new_version,
        "changes": {"state": {"from": row["state"], "to": "retired"}},
        "source": "bootstrap-roles.sh --prune",
    }
    event = store.append_event(
        "role.retired", pslug, "org_role", role_key(pslug, slug), "bootstrap-roles.sh", payload
    )
    store.conn.execute(
        """
        UPDATE org_roles
           SET state = 'retired', version = ?, latest_event_id = ?, updated_at = ?
         WHERE product_slug = ? AND role_slug = ?
        """,
        (new_version, event["event_id"], now, pslug, slug),
    )
    insert_role_lineage(
        store, pslug, slug, event["event_id"], "role_retired",
        "Retired by bootstrap-roles.sh --prune (not in roster)",
    )
    store.conn.commit()
    print(f"[bootstrap-roles] {slug}: org_roles state -> retired")
else:
    raise SystemExit(f"[bootstrap-roles] unknown org_roles_sync op: {op}")
PY
}

seed_role() {
  local slug="$1" title="$2" model="$3" caps="$4" auth="$5" otype="${6:-fulltime}"
  [ -z "$otype" ] && otype="fulltime"

  # ---- (2) instance/roles/active/<slug>.yml ----
  # New slugs are written fresh; existing slugs are UPDATED IN PLACE: the
  # roster owns title/model/capabilities/authority_level/officer_type and
  # refreshes them on every run (fixes split-brain like org "First Mate" vs
  # a stale yml "Chief of Staff"); created_at is preserved.
  local yml="$ACTIVE_DIR/$slug.yml"
  local created_at existed=0
  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ -f "$yml" ]; then
    existed=1
    local prior_created
    # sed (not colon-split awk) — the ISO timestamp value contains colons.
    prior_created="$(sed -n 's/^created_at:[[:space:]]*//p' "$yml" | head -1 | tr -d '[:space:]')"
    [ -n "$prior_created" ] && created_at="$prior_created"
  fi
  cat > "$yml" <<EOF
# instance/roles/active/$slug.yml — generated by bootstrap-roles.sh
# Roster-owned fields (title/model/capabilities/authority_level/officer_type)
# are refreshed from the roster on every bootstrap run. Lineage tracked in
# org_roles + role_* events; this file is the operational view.
slug: $slug
title: $title
product_slug: $PRODUCT_SLUG
status: active
model: $model
officer_type: $otype
authority_level: $auth
capabilities:
$(echo "$caps" | tr ',' '\n' | sed 's/^/  - /')
hats: []
created_at: $created_at
EOF
  if [ "$existed" = "1" ]; then
    echo "[bootstrap-roles] $slug: refreshed $yml from roster (update-in-place)"
  else
    echo "[bootstrap-roles] $slug: wrote $yml"
  fi

  # ---- (3) org_roles table ----
  # New slug: org_runtime.py CLI `roles define` — emits the proper
  # role.defined event + writes the Store SQLite. Existing slug: refresh
  # roster-owned fields via org_roles_sync (the define CLI refuses dupes).
  local exists
  exists="$(python3 "$CABINET_ROOT/cabinet/scripts/org-runtime.py" roles show \
    --product-slug "$PRODUCT_SLUG" --role "$slug" 2>/dev/null || true)"
  if [ -n "$exists" ] && [ "$exists" != "null" ]; then
    if ! org_roles_sync update "$PRODUCT_SLUG" "$slug" "$title" "$caps" "$auth"; then
      echo "[bootstrap-roles] WARN $slug: org_roles update failed (run manually to debug)"
    fi
    return 0
  fi

  # Build --capability args (one flag per capability — CLI takes single value).
  # The expansion below uses the bash-3.2-safe alternate-value form: macOS ships
  # /bin/bash 3.2, where a plain "${cap_args[@]}" on an EMPTY array aborts this
  # `set -euo pipefail` script with "unbound variable".  `caps` is validated
  # non-empty by the roster reader before seed_role runs, so the empty case is
  # currently unreachable — but the guard is one roster-parser change away from
  # load-bearing, and the failure mode (hatch dies mid-roster-seed) is expensive.
  local cap_args=()
  local IFS=','
  for c in $caps; do
    cap_args+=(--capability "$c")
  done
  unset IFS

  if python3 "$CABINET_ROOT/cabinet/scripts/org-runtime.py" roles define \
      --product-slug "$PRODUCT_SLUG" \
      --role "$slug" \
      --name "$title" \
      --charter "Bootstrap charter for $title. Refine via Captain ratification + role evolution proposals." \
      --authority-level "$auth" \
      ${cap_args[@]+"${cap_args[@]}"} \
      --state active \
      --actor bootstrap-roles.sh \
      >/dev/null 2>&1; then
    echo "[bootstrap-roles] $slug: org_roles row created"
  else
    echo "[bootstrap-roles] WARN $slug: org_runtime.py roles define failed (run manually to debug)"
  fi
}

# Slug list of the chosen roster — drives the drift warning + --prune pass.
ROSTER_SLUGS=""

if [ -n "$ROSTER_FILE" ]; then
  # ---- PORTFOLIO PATH: roster-driven seed from instance config ----
  # awk emits one TAB-separated line per role: slug \t title \t model \t
  # caps(csv) \t authority \t type. Same fixed-indent walking style as
  # load-preset.sh's list_hired_agents / peers.yml validator: top-level
  # `roster:` opens the section; any other top-level key closes it;
  # 2-space keys are role slugs; 4-space `key: value` lines are fields.
  echo "[bootstrap-roles] roster file: $ROSTER_FILE"
  ROSTER_TSV=$(awk '
    function emit() {
      if (slug != "") printf "%s\t%s\t%s\t%s\t%s\t%s\n", slug, title, model, caps, auth, otype
    }
    /^roster:[[:space:]]*$/ { section = 1; next }
    /^[A-Za-z_#-]/          { if (section && slug != "") { emit(); slug = "" } ; section = 0 }
    section && /^  [a-z0-9][a-z0-9-]*:[[:space:]]*$/ {
      emit()
      slug = $0; sub(/^  /, "", slug); sub(/:.*$/, "", slug)
      title = ""; model = ""; caps = ""; auth = ""; otype = ""
      next
    }
    section && slug != "" && /^    [a-z_]+:/ {
      line = $0; sub(/^    /, "", line)
      key = line; sub(/:.*$/, "", key)
      val = line; sub(/^[a-z_]+:[[:space:]]*/, "", val)
      sub(/[[:space:]]*(#.*)?$/, "", val)        # strip trailing comment
      gsub(/^"|"$/, "", val)
      if (key == "title")            title = val
      else if (key == "model")       model = val
      else if (key == "authority_level") auth = val
      else if (key == "type")        otype = val
      else if (key == "capabilities") {
        gsub(/[\[\]]/, "", val); gsub(/[[:space:]]/, "", val)
        caps = val
      }
      # other keys (telegram:, …) intentionally ignored
    }
    END { emit() }
  ' "$ROSTER_FILE")

  if [ -z "$ROSTER_TSV" ]; then
    echo "[bootstrap-roles] no roles found under 'roster:' in $ROSTER_FILE" >&2
    exit 2
  fi

  while IFS=$'\t' read -r slug title model caps auth otype; do
    [ -z "$slug" ] && continue
    if [ -z "$title" ] || [ -z "$model" ] || [ -z "$caps" ] || [ -z "$auth" ]; then
      echo "[bootstrap-roles] roster role '$slug' missing required field(s) — need title/model/capabilities/authority_level (got title='$title' model='$model' capabilities='$caps' authority_level='$auth')" >&2
      exit 2
    fi
    case "${otype:-fulltime}" in
      fulltime|consultant) : ;;
      *)
        echo "[bootstrap-roles] roster role '$slug' has invalid type '$otype' — must be fulltime or consultant" >&2
        exit 2
        ;;
    esac
    seed_role "$slug" "$title" "$model" "$caps" "$auth" "${otype:-fulltime}"
    ROSTER_SLUGS="$ROSTER_SLUGS $slug"
  done <<< "$ROSTER_TSV"
else
  # ---- DEFAULT PATH: built-in functional seed (unchanged; all fulltime) ----
  # Officer slug | Title                       | Model               | Capabilities                                                                                | Authority level
  seed_role cos "First Mate"                   claude-fable-5       "logs_captain_decisions,reviews_specs,reviews_implementations,validates_deployments"        captain_proxy
  seed_role cto "Chief Technology Officer"     claude-fable-5       "deploys_code,reviews_implementations,engineering_execution"                                 mission_executor
  seed_role cpo "Chief Product Officer"        claude-fable-5       "reviews_specs,product_strategy,backlog_management"                                          mission_executor
  seed_role cro "Chief Research Officer"       claude-sonnet-4-6    "reviews_research,market_intelligence,research_sweep"                                        mission_executor
  seed_role coo "Chief Operating Officer"      claude-sonnet-4-6    "validates_deployments,operational_health,quality_gate"                                      mission_executor
  ROSTER_SLUGS=" cos cto cpo cro coo"
fi

# -----------------------------------------------------------------------------
# Drift report + optional prune: active roles NOT in the chosen roster.
# Without --prune they are only WARNed (visible drift); with --prune the yml
# moves to instance/roles/archive/ and org_roles state goes to retired.
# -----------------------------------------------------------------------------
ARCHIVE_DIR="$CABINET_ROOT/instance/roles/archive"
for role_yml in "$ACTIVE_DIR"/*.yml; do
  [ -f "$role_yml" ] || continue
  slug="$(basename "$role_yml" .yml)"
  case "$ROSTER_SLUGS " in
    *" $slug "*) continue ;;   # in roster — keep
  esac
  if [ "$PRUNE" = "1" ]; then
    # The yml's own product_slug wins (the row may have been seeded under a
    # different active project than this run's).
    yml_pslug="$(awk -F': *' '$1=="product_slug"{print $2; exit}' "$role_yml" | tr -d '[:space:]')"
    yml_pslug="${yml_pslug:-$PRODUCT_SLUG}"
    mkdir -p "$ARCHIVE_DIR"
    mv "$role_yml" "$ARCHIVE_DIR/$slug.yml"
    echo "[bootstrap-roles] RETIRED $slug: not in roster — yml archived to instance/roles/archive/$slug.yml"
    if ! org_roles_sync retire "$yml_pslug" "$slug"; then
      echo "[bootstrap-roles] WARN $slug: org_roles retire failed (run manually to debug)"
    fi
  else
    echo "[bootstrap-roles] WARN drift: instance/roles/active/$slug.yml is NOT in the chosen roster — re-run with --prune to retire it"
  fi
done

echo "[bootstrap-roles] done. Verify:"
echo "  python3 cabinet/scripts/org-runtime.py roles list --product-slug $PRODUCT_SLUG"
echo "  ls $ACTIVE_DIR"
