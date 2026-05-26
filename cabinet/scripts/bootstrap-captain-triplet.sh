#!/usr/bin/env bash
# bootstrap-captain-triplet.sh — Create empty Captain triplet files on cold deploy.
#
# Phase 3 of the convergence plan. The three Captain memory artifacts —
# captain-decisions.md, captain-patterns.md, captain-intents.md — live in
# `shared/interfaces/` and are gitignored (per-deployment runtime artifacts).
# On a fresh Cabinet deployment, these files don't exist, which means:
#
#   - captain-rule-encoder.sh appends to nothing (file created on first write)
#   - pre-captain-dm.sh's query.sh has nothing to match against
#   - CLAUDE.md's "Required Reading #9–11" points to missing files
#
# This script creates the files with a stable header so officers know what
# they are and how to read them. Safe to re-run: existing files are not
# overwritten — only missing ones are created.
#
# Usage:
#   bash cabinet/scripts/bootstrap-captain-triplet.sh
#   CABINET_ROOT=/path/to/cabinet bash cabinet/scripts/bootstrap-captain-triplet.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Bug fix (R5): script lives at cabinet/scripts/, so repo root is two levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
TRIPLET_DIR="$CABINET_ROOT/shared/interfaces"
mkdir -p "$TRIPLET_DIR"

created=0

_write_if_missing() {
  local file="$1" body="$2"
  if [ ! -e "$file" ]; then
    printf '%s' "$body" > "$file"
    created=$((created + 1))
    echo "  created: $file"
  else
    echo "  exists:  $file"
  fi
}

_write_if_missing "$TRIPLET_DIR/captain-decisions.md" \
"# Captain Decisions — Append-Only Log

Every Captain decision logged in real time during sessions. Each entry includes:

- **Decision:** what the Captain decided
- **Why:** the reasoning (most important field — never skip)
- **Affected:** specs / issues / files that this decision touches
- **Logged by:** officer slug + UTC timestamp

Officers with the \`logs_captain_decisions\` capability MUST log decisions during
Captain conversations. The post-tool-use.sh hook enforces this when an officer
ends a reply to the Captain without logging.

Read this file **before any design / UI / feature work** so you never re-introduce
something the Captain already killed.

---

<!-- Append entries below this line. Newest at the bottom (chronological). -->
"

_write_if_missing "$TRIPLET_DIR/captain-patterns.md" \
"# Captain Patterns — Standing Behaviors (4th improvement loop)

Explicit, durable behavioral rules the Captain has ratified. Each entry:

- **Pattern slug:** kebab-case id (e.g. \`always-thread-replies\`)
- **Rule:** the behavior verbatim
- **Why:** Captain's stated rationale OR Cabinet's inferred reason
- **How to apply:** concrete trigger + action
- **Captain evidence:** quoted DM + UTC timestamp
- **Encoded by:** auto (captain-rule-encoder.sh) or manually by an officer

The 4th-loop hook (\`captain-rule-encoder.sh\`) appends entries on every Captain
DM containing an encode-signal phrase. After the second sighting of the same
slug, the hook also broadcasts a cross-officer Redis trigger so other officers
re-read this file.

Read this file **before every Captain reply** — pattern violations are the
single most common source of Captain frustration.

---

<!-- Auto-encoded entries appear below the separator above. Manual edits are -->
<!-- welcome but should preserve the structured format so the query layer can -->
<!-- match against trigger + how-to-apply fields. -->
"

_write_if_missing "$TRIPLET_DIR/captain-intents.md" \
"# Captain Intents — Inferred Latent Goals (5th improvement loop)

What the Captain probably WANTS beyond the surface ask. Inferred from behavior,
not declared. Each entry:

- **Inferred goal:** the latent WHY in 1–2 sentences
- **Evidence:** Captain DMs / decisions / patterns that suggest it
- **Confidence:** low | medium | high
- **First observed:** UTC timestamp
- **Superseded by:** newer intent id (if revised)

Append-only — never overwrite a past inference. Confidence may be revised up or
down over time via supersession. CoS owns this file's integrity and audits it
during the 48h cross-officer retro.

Before composing any Captain-facing outbound (DM, briefing, proactive DM), do a
**pre-reply WHY scan**:

  1. Read the entries here that are relevant to the current context.
  2. Hypothesize: what would make this reply *delight* vs *frustrate*?
  3. Shape the reply around the WHY — the surface ask is the tip of the iceberg.
  4. If confidence is low and the inferred WHY would meaningfully change the
     reply, ASK one short clarifier instead of guessing.

---

<!-- Append entries below this line. Newest at the bottom. -->
"

echo ""
echo "bootstrap-captain-triplet: ${created} new file(s) created"
exit 0
