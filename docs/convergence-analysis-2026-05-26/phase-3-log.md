# Phase 3 Log — Captain Intent Layer

**Started:** 2026-05-26
**Branch:** `claude/convergence`
**Status:** **COMPLETE** ✅ (with two follow-ups deferred — see bottom)

## Goal

Wire the Captain triplet (decisions/patterns/intents) deeply into the existing hooks: 4th-loop two-count + cross-officer broadcast, 5th-loop pre-reply WHY scan, and a cold-deploy bootstrap. Make REPO_ROOT resolution work on both Docker (/opt/founders-cabinet) and Mac-native.

## Audit findings (3.1)

The pre-existing hooks already do **most** of the work:

- `cabinet/scripts/hooks/captain-rule-encoder.sh` (Spec 048 v2 Phase 1) — detects encode signals, appends to `captain-patterns.md`, fires an async classifier (Sonnet) for verification, and triggers draft generators.
- `cabinet/scripts/hooks/pre-captain-dm.sh` (Spec 042 Phase 2) — captures Telegram DM, transcribes voice, dedupes 60s windows, runs `captain-rules/query.sh` to surface relevant patterns/intents/decisions into the officer's pre-prompt context. This **is** the 5th-loop pre-reply WHY scan when `query.sh` returns intent matches.
- `cabinet/scripts/hooks/captain-reply-refine.sh` (157 lines) — PreToolUse hook on Telegram replies; gates reply quality.

**Real gaps the convergence plan calls for and that didn't yet exist:**

1. **Two-count rule** — encoder logged every encode signal on first sighting; never escalated. Spec 048's two-sighting threshold + cross-officer broadcast was a doc statement, not in code.
2. **Cross-officer broadcast** — `notify-officer.sh` was never invoked from the encoder on pattern repeat.
3. **REPO_ROOT Mac-native fallback** — both hooks hard-defaulted to `/opt/founders-cabinet`. On Mac, REPO_ROOT must be inferred from the script path.
4. **Triplet bootstrap** — no script to create the gitignored files on cold deploy; encoder relied on file existing OR appending (which works), but a fresh Cabinet had stub-free files that broke `query.sh`'s retrieval.

## Delivered

### 3.2 — captain-rule-encoder.sh: two-count rule + broadcast

Layered on top of the existing encoder logic:

- New `RULE_COUNT` from `redis-cli INCR cabinet:patterns:seen:$RULE_ID`, with a 30-day TTL set on first sighting so stale rule_ids don't accumulate.
- On second+ sighting (`RULE_COUNT >= 2`), the encoder iterates `instance/roles/active/*.yml` and calls `bash notify-officer.sh <slug> "Pattern $RULE_ID encoded for the $RULE_COUNT-th time — re-read shared/interfaces/captain-patterns.md before next Captain DM."` for every officer other than the encoding officer.
- Self-broadcast skipped (`[ "$target_slug" = "$OFFICER" ] && continue`).
- Best-effort: every Redis or notify failure falls through silently — pattern encoding still happens.

### 3.3 — pre-captain-dm.sh: REPO_ROOT auto-detect

The existing hook is feature-complete for the 5th-loop pre-reply WHY scan via `query.sh`. Added a Mac-native fallback to REPO_ROOT resolution so the hook works in both Docker and `start-officer-mac.sh` contexts:

```bash
if [ -z "${REPO_ROOT:-}" ]; then
  if [ -d "/opt/founders-cabinet" ]; then
    REPO_ROOT="/opt/founders-cabinet"
  else
    REPO_ROOT="${CABINET_ROOT:-$(cd "$SELF_DIR/../../.." 2>/dev/null && pwd)}"
  fi
fi
```

Same pattern applied to `captain-rule-encoder.sh`.

### 3.4 — Triplet bootstrap

- `cabinet/scripts/bootstrap-captain-triplet.sh` — Creates the three Captain triplet files in `shared/interfaces/` with stable, opinionated headers explaining each file's role and format. Idempotent — re-running prints "exists:" rather than overwriting.
- Each file's header documents the 4th- or 5th-loop discipline tied to it, mirroring CLAUDE.md so officers read the same contract in two places.
- The triplet files remain gitignored (per `.gitignore:65` — `shared/interfaces/**/*.md`); this script is the canonical creator.

## Deferred follow-ups

Two pieces of the convergence plan's Phase 3 are NOT shipped in this phase:

1. **Postgres mirror of the triplet** — would index patterns/intents/decisions for `captain-rules/query.sh` to do faster retrieval. Today `query.sh` reads the .md files directly with grep/text search. Acceptable for current scale; revisit when triplet > ~10 KB per file. Tracked: convergence Phase 8 / database integration.

2. **48h retro Captain-intent ledger scan** — CoS's 48h cross-officer retro should scan `captain-decisions.md` since the last retro, extract latent-goal patterns, and append candidates to `captain-intents.md`. The retro skill exists (`memory/skills/cross-officer-retro.md`); wiring the scan step requires reading the skill and adding instructions. Skill ownership is CoS; folded into Phase 7 (self-improvement completion).

## Test gates (PASS)

- bash -n on edited hooks (captain-rule-encoder, pre-captain-dm) + bootstrap — clean
- Full suite: **537/537 pass** (no regression from hook changes)
- Bootstrap smoke: invoked on convergence worktree → 3 new files created, ~750–1150 bytes each with structured headers ✅
- Re-running bootstrap → "exists:" for all three → idempotent ✅

## Files touched

- `cabinet/scripts/hooks/captain-rule-encoder.sh` — added REPO_ROOT fallback + two-count rule + cross-officer broadcast
- `cabinet/scripts/hooks/pre-captain-dm.sh` — added REPO_ROOT fallback
- `cabinet/scripts/bootstrap-captain-triplet.sh` — NEW
- `docs/convergence-analysis-2026-05-26/phase-3-log.md` — this file

## Resume signal

Phase 3 complete (modulo two follow-ups folded into later phases). Next: **Phase 4 — Latest CC adoption** (Skills authored, Tool Search verified, Agent Teams flag honored, /loop /goal patterns documented).
