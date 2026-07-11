#!/bin/bash
# test-activate-project.sh - hermetic project activation contract eval.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/cabinet/scripts/activate-project.sh"
TMP_DIR="$(mktemp -d)"
ROOT="$TMP_DIR/cabinet-root"
FIXTURE_REPO="$TMP_DIR/existing-repo"
DB="$TMP_DIR/org-runtime.sqlite3"
export CABINET_ROOT="$ROOT"
export ORG_RUNTIME_DB="$DB"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

echo "=== Project activation eval ==="

mkdir -p "$ROOT/cabinet" "$ROOT/instance/config/projects"
ln -s "$REPO_ROOT/cabinet/scripts" "$ROOT/cabinet/scripts"
cp "$REPO_ROOT/instance/config/projects/_template.yml" "$ROOT/instance/config/projects/_template.yml"
cat > "$ROOT/instance/config/platform.yml" <<'YAML'
captain_name: ExampleCaptain
captain_timezone: Europe/Copenhagen
YAML
git init "$FIXTURE_REPO" >/dev/null

bash "$SCRIPT" fixture --repo-path "$FIXTURE_REPO" --name "Fixture Project" --description "Activation fixture" --dry-run >/dev/null
[ ! -f "$ROOT/instance/config/projects/fixture.yml" ] \
  && pass "dry-run did not write project config" \
  || fail "dry-run wrote project config"

bash "$SCRIPT" fixture --repo-path "$FIXTURE_REPO" --name "Fixture Project" --description "Activation fixture" --activate >/dev/null

[ "$(tr -d '[:space:]' < "$ROOT/instance/config/active-project.txt")" = "fixture" ] \
  && pass "active project file set" \
  || fail "active project file not set"
[ -f "$ROOT/instance/config/product.yml" ] \
  && pass "product.yml assembled" \
  || fail "product.yml missing"
grep -q 'status: active' "$ROOT/instance/config/projects/fixture.yml" \
  && pass "activation status written to project config" \
  || fail "activation status missing"
[ -L "$ROOT/workspace/fixture" ] && [ "$(readlink "$ROOT/workspace/fixture")" = "$FIXTURE_REPO" ] \
  && pass "workspace mount symlink created" \
  || fail "workspace symlink missing or incorrect"

EVENT_COUNT="$(python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM org_events WHERE event_type IN ('project.activation_preflight','project.activated')").fetchone()[0])
PY
)"
[ "$EVENT_COUNT" = "2" ] \
  && pass "activation lifecycle emitted org_events" \
  || fail "expected 2 activation events, got $EVENT_COUNT"

echo "=== Project activation eval PASS ==="
