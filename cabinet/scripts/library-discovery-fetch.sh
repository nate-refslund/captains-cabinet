#!/usr/bin/env bash
# Library auto-population FETCH stage — runs at cabinet spawn (called from
# cabinet-spawn.sh / FW-080) before CRO officer starts.
#
# Pulls raw discovery material from external sources to /tmp/library-discovery/<project>/.
# CRO officer reads from there + writes Library records via library MCP at first activation
# (post-spawn playbook in memory/skills/evolved/library-discovery-sweep.md).
#
# Why split fetch vs. write: fetching uses git/curl (shell-friendly). Writing uses Library
# MCP (officer-session-only). This script handles the fetch; the playbook handles the write.
#
# Usage:
#   library-discovery-fetch.sh <project_id> <source_type> <source_arg>
#
#   library-discovery-fetch.sh "step-network" "website" "https://stepnetwork.dk"
#   library-discovery-fetch.sh "politiske-annoncer" "github" "stepnetwork/politiske-annoncer"
#   library-discovery-fetch.sh "stephie-mcp" "github" "stepnetwork/stephie-mcp"
#
# Output: /tmp/library-discovery/<project_id>/<source_type>.{md,json,raw}

set -euo pipefail

PROJECT_ID="${1:?Usage: library-discovery-fetch.sh <project_id> <source_type> <source_arg>}"
SOURCE_TYPE="${2:?source_type required: website | github | monday-export}"
SOURCE_ARG="${3:?source_arg required}"

OUT_DIR="/tmp/library-discovery/$PROJECT_ID"
mkdir -p "$OUT_DIR"

case "$SOURCE_TYPE" in
  website)
    echo "Fetching website: $SOURCE_ARG" >&2
    curl -sSL --max-time 30 "$SOURCE_ARG" > "$OUT_DIR/website-raw.html" 2>&1
    if command -v lynx >/dev/null 2>&1; then
      lynx -dump -nolist "$OUT_DIR/website-raw.html" > "$OUT_DIR/website.md" 2>&1
    else
      python3 -c "
import re, html, sys
with open('$OUT_DIR/website-raw.html') as f: raw = f.read()
text = re.sub(r'<script.*?</script>', '', raw, flags=re.DOTALL|re.IGNORECASE)
text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL|re.IGNORECASE)
text = re.sub(r'<[^>]+>', ' ', text)
text = html.unescape(text)
text = re.sub(r'\s+', ' ', text).strip()
with open('$OUT_DIR/website.md', 'w') as f: f.write(text[:50000])
" 2>&1
    fi
    echo "$OUT_DIR/website.md ($(wc -c < "$OUT_DIR/website.md" 2>/dev/null || echo 0) bytes)"
    ;;

  github)
    echo "Cloning GitHub repo: $SOURCE_ARG" >&2
    REPO_PATH="$OUT_DIR/repo"
    rm -rf "$REPO_PATH"
    if [ -n "${GITHUB_PAT:-}" ]; then
      git clone --depth 50 "https://x-access-token:${GITHUB_PAT}@github.com/${SOURCE_ARG}.git" "$REPO_PATH" 2>&1 | tail -3
    else
      git clone --depth 50 "https://github.com/${SOURCE_ARG}.git" "$REPO_PATH" 2>&1 | tail -3
    fi

    {
      echo "# Repo Discovery: $SOURCE_ARG"
      echo
      echo "## README"
      [ -f "$REPO_PATH/README.md" ] && cat "$REPO_PATH/README.md" | head -200 || echo "(no README.md)"
      echo
      echo "## ARCHITECTURE"
      for f in ARCHITECTURE.md docs/ARCHITECTURE.md docs/architecture.md ARCHITECTURE; do
        [ -f "$REPO_PATH/$f" ] && cat "$REPO_PATH/$f" | head -300 && break
      done
      echo
      echo "## Top-level structure"
      ls "$REPO_PATH" 2>&1 | head -40
      echo
      echo "## Recent commits (last 30)"
      (cd "$REPO_PATH" && git log --oneline -30 2>&1)
      echo
      echo "## Package config"
      for f in package.json pyproject.toml Cargo.toml go.mod Gemfile; do
        if [ -f "$REPO_PATH/$f" ]; then
          echo "### $f"
          head -100 "$REPO_PATH/$f"
          echo
        fi
      done
      echo "## Deploy config"
      for f in vercel.json fly.toml render.yaml Dockerfile docker-compose.yml; do
        if [ -f "$REPO_PATH/$f" ]; then
          echo "### $f"
          head -60 "$REPO_PATH/$f"
          echo
        fi
      done
    } > "$OUT_DIR/codebase.md"
    echo "$OUT_DIR/codebase.md ($(wc -c < "$OUT_DIR/codebase.md") bytes)"
    ;;

  monday-export)
    echo "Monday MCP export: must be done from CRO officer session (this is fetch-stage shell, no MCP)" >&2
    echo "Skipping — playbook handles Monday MCP at officer activation"
    touch "$OUT_DIR/monday-export.deferred"
    ;;

  *)
    echo "ERROR: unknown source_type '$SOURCE_TYPE'" >&2
    exit 2
    ;;
esac
