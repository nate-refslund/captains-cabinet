#!/usr/bin/env bash
# bootstrap-project.sh — One-command product onboarding for the Cabinet.
#
# Phase 6 of the convergence plan. Clones a product repo, runs the stack
# detector, generates an `instance/config/projects/<slug>.yml`, and (when
# possible) infers + fills task-system + Telegram chat config. Captain
# reviews and tunes the generated YAML before activating the project.
#
# Usage:
#   bash cabinet/scripts/bootstrap-project.sh <repo-url> <project-slug> [--workspace DIR]
#   bash cabinet/scripts/bootstrap-project.sh \
#        https://github.com/owner/repo.git acme
#
# What it does (in order):
#   1. Clones the repo to $WORKSPACE/<slug>/ (default: ~/work/projects/<slug>/)
#   2. Runs `framework.products.stack_detector` to detect language/framework/
#      tests/db/deploy/ci.
#   3. Copies instance/config/projects/_template.yml → <slug>.yml.
#   4. Patches generated YAML with: project_name, project_slug, github_repo,
#      workspace_path, default tasks.system=github-issues + tasks.config.repo,
#      product_metadata fields from the detector.
#   5. Prints a structured summary and writes a "next steps" file with the
#      Captain-facing prompt template.
#
# Exits non-zero on clone failure or detector error.
# Idempotent: re-running on an existing slug refreshes the metadata
# (clone is a `git pull` if the workspace already exists).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Bug fix (R4): script lives at cabinet/scripts/, so repo root is two levels
# up. Convergence had only one ../ which resolved to cabinet/ and broke
# product onboarding paths.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# --- arg parsing ---
REPO_URL=""
SLUG=""
WORKSPACE="${WORKSPACE:-$HOME/work/projects}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      sed -n '1,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --workspace)
      shift
      WORKSPACE="$1"
      ;;
    --workspace=*)
      WORKSPACE="${1#--workspace=}"
      ;;
    -*)
      echo "bootstrap-project: unknown flag: $1" >&2
      exit 2
      ;;
    *)
      if [[ -z "$REPO_URL" ]]; then
        REPO_URL="$1"
      elif [[ -z "$SLUG" ]]; then
        SLUG="$1"
      else
        echo "bootstrap-project: unexpected positional arg: $1" >&2
        exit 2
      fi
      ;;
  esac
  shift
done

if [[ -z "$REPO_URL" ]] || [[ -z "$SLUG" ]]; then
  echo "Usage: $0 <repo-url> <project-slug> [--workspace DIR]" >&2
  exit 2
fi

# Validate slug
if ! [[ "$SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]] || [[ "${#SLUG}" -gt 32 ]]; then
  echo "bootstrap-project: slug must be kebab-case, alphanumeric, 1-32 chars, start with letter/digit" >&2
  exit 2
fi

CLONE_DIR="$WORKSPACE/$SLUG"
PROJECT_YML="$CABINET_ROOT/instance/config/projects/$SLUG.yml"
TEMPLATE_YML="$CABINET_ROOT/instance/config/projects/_template.yml"

echo "=== bootstrap-project: $SLUG ==="
echo "  repo:      $REPO_URL"
echo "  workspace: $CLONE_DIR"
echo "  config:    $PROJECT_YML"
echo ""

# --- 1. Clone or pull ---
mkdir -p "$WORKSPACE"
if [[ -d "$CLONE_DIR/.git" ]]; then
  echo "[1/4] Updating existing clone ($CLONE_DIR)..."
  (cd "$CLONE_DIR" && git pull --ff-only 2>&1 | tail -5) || {
    echo "bootstrap-project: git pull failed; clone may be in a dirty state" >&2
    exit 1
  }
else
  echo "[1/4] Cloning $REPO_URL ..."
  git clone --depth 50 "$REPO_URL" "$CLONE_DIR" 2>&1 | tail -5
fi

# --- 2. Detect stack ---
echo ""
echo "[2/4] Detecting stack..."
METADATA_JSON="$(cd "$CABINET_ROOT" && python3 -m framework.products.stack_detector "$CLONE_DIR" --json)"
echo "$METADATA_JSON" | python3 -c '
import json, sys
m = json.load(sys.stdin)
for k, v in m.items():
    if isinstance(v, list):
        print(f"  {k:15} {chr(44).join(v) if v else \"(none)\"}")
    else:
        print(f"  {k:15} {v}")
'

# --- 3. Generate project YAML ---
echo ""
echo "[3/4] Generating $PROJECT_YML ..."
if [[ -f "$PROJECT_YML" ]]; then
  echo "  (project YAML already exists — refreshing product_metadata only)"
fi

# Best-effort GitHub owner/repo extraction from the URL.
# Supports: https://github.com/owner/repo[.git], git@github.com:owner/repo[.git]
GITHUB_REPO_INFERRED=""
if [[ "$REPO_URL" =~ github.com[/:]([^/]+/[^/.]+)(\.git)?$ ]]; then
  GITHUB_REPO_INFERRED="${BASH_REMATCH[1]%.git}"
fi

PROJECT_YML="$PROJECT_YML" \
TEMPLATE_YML="$TEMPLATE_YML" \
SLUG="$SLUG" \
REPO_URL="$REPO_URL" \
GITHUB_REPO_INFERRED="$GITHUB_REPO_INFERRED" \
CLONE_DIR="$CLONE_DIR" \
METADATA_JSON="$METADATA_JSON" \
python3 - <<'PY'
import json
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    print("bootstrap-project: PyYAML required (pip install pyyaml)")
    raise SystemExit(1)

project_yml = Path(os.environ["PROJECT_YML"])
template_yml = Path(os.environ["TEMPLATE_YML"])
slug = os.environ["SLUG"]
metadata = json.loads(os.environ["METADATA_JSON"])

# Start from template OR existing project YAML if present
if project_yml.exists():
    with open(project_yml) as f:
        config = yaml.safe_load(f) or {}
else:
    with open(template_yml) as f:
        config = yaml.safe_load(f) or {}

# Patch only fields the bootstrapper owns; preserve any Captain-set fields.
config.setdefault("project_name", slug)
config["project_slug"] = slug
if not config.get("github_repo"):
    config["github_repo"] = os.environ.get("GITHUB_REPO_INFERRED") or ""
config["workspace_path"] = os.environ["CLONE_DIR"]

# Tasks block default → github-issues using the same repo
tasks = config.get("tasks") or {}
if not tasks.get("system"):
    tasks["system"] = "github-issues"
    tasks.setdefault("auth_env", "")
    tasks.setdefault("config", {})
if tasks.get("system") == "github-issues":
    tasks.setdefault("config", {})
    if not tasks["config"].get("repo"):
        tasks["config"]["repo"] = os.environ.get("GITHUB_REPO_INFERRED") or ""
config["tasks"] = tasks

# Stack detector always wins for product_metadata (re-runnable refresh)
config["product_metadata"] = metadata

with open(project_yml, "w") as f:
    yaml.safe_dump(config, f, sort_keys=False, default_flow_style=False)
print(f"  wrote: {project_yml}")
PY

# --- 4. Emit Captain-facing exploration prompt ---
echo ""
echo "[4/4] Captain-facing exploration prompt:"
echo ""
SUMMARY="$(python3 -c '
import json, os
m = json.loads(os.environ["METADATA_JSON"])
parts = []
if m.get("languages"):       parts.append(f"languages: {chr(44).join(m[\"languages\"])}")
if m.get("frameworks"):      parts.append(f"frameworks: {chr(44).join(m[\"frameworks\"])}")
if m.get("databases"):       parts.append(f"databases: {chr(44).join(m[\"databases\"])}")
if m.get("deploy_targets"):  parts.append(f"deploy: {chr(44).join(m[\"deploy_targets\"])}")
print(" | ".join(parts) if parts else "(no stack signals detected — empty or unfamiliar repo)")
')"

cat <<EOF
The Cabinet has explored the $SLUG product.

  Repo:      $REPO_URL
  Workspace: $CLONE_DIR
  Stack:     $SUMMARY

Open questions for the Captain:
  - What's the first outcome you want pursued? (declare in instance/config/outcomes.yml)
  - Is github-issues the right task system, or do you want to point tasks.system at
    Monday / Jira / Linear / Asana? (edit $PROJECT_YML)
  - Any role-charter adjustments to handle this stack? (frameworks: $SUMMARY)

To activate this project as the Cabinet's current focus, run:
  echo "$SLUG" > instance/config/active-project.txt

Then ratify an outcome in instance/config/outcomes.yml and the mission supervisor
will route work to officers on its next 5-minute tick.
EOF

exit 0
