# Phase 7 Log — Self-Improvement Completion

**Started:** 2026-05-26
**Branch:** `claude/convergence`
**Status:** **COMPLETE** ✅

## Goal

Close the evolutionary loops: hats graduate to permanent capabilities when they prove useful, experience records take a Reflexion-structured shape that future sessions can query, and recurring lessons get drafted into evolved-skill candidates Voyager-style.

## Delivered

### 7.1 — Hat graduation (`framework/roles/hat_graduation.py`)

When a hat has been used ≥5 times across ≥5 distinct missions and OVI didn't regress during the use window, the hat is a graduation candidate. The module reads the event ledger (no Postgres needed):

- Replay `role_hat_assigned` events, group by (role_slug, hat_slug) — count uses, distinct missions, capabilities-granted, first/last timestamps
- Replay `role_hat_promoted` events to exclude already-promoted hats
- Replay `ovi_snapshot_computed` events — find baseline (last snapshot before first hat use) and check no in-window snapshot dropped > 2% below baseline
- `propose_graduations()` emits `role_hat_promoted` events with `status: pending_captain_approval` for each candidate

Captain ratifies; CoS applies the change via existing `framework/roles/lifecycle.py` (moves capabilities from hat into role.charter.capabilities).

CLI: `python3 -m framework.roles.hat_graduation --dry-run --json`

### 7.2 — Structured experience records (`framework/learning/experience.py`)

Reflexion-style records with three structured fields beyond the body:

- `lesson_type` — one of: `blocker | optimization | pattern | anti_pattern | surprise`
- `trigger_signal` — short noun phrase that called the lesson into being (e.g. "PR rejected for missing tests")
- `applicability_scope` — one of: `this_task | this_mission | this_role | cabinet_wide`

Records are persisted as JSONL at `memory/experience_records/records-YYYY-MM-DD.jsonl` (append-only) and emit `experience_recorded` events so OVI's `learning_rate` component counts them.

CLI: `python3 -m framework.learning.experience --actor <slug> --lesson-type pattern --trigger-signal "X" --body "Y"`

### 7.3 — Voyager-style skill induction (`framework/learning/skill_induction.py`)

When 3+ experience records share `(lesson_type, trigger_signal)` AND `applicability_scope ∈ {this_role, cabinet_wide}`, the cluster is treated as evidence the lesson generalizes. The induction layer drafts a `memory/skills/evolved/induced-<lesson_type>-<slugified-signal>.md` file with:

- Frontmatter `status: draft`
- `induction:` metadata block (cluster_size, signal, lesson_type, scopes, actors, timestamps)
- Sample evidence snippets from the matched records
- Placeholder Procedure + Validation Scenarios sections (Captain/CoS fills in before promotion)

Idempotent: re-running overwrites the same draft file with refreshed evidence.

Emits `digest_published` event with `kind: skill_induction_draft` so the dashboard / Captain can see the queue.

Phase 7 ships *deterministic clustering* by exact `(lesson_type, trigger_signal)` match. Semantic/pgvector clustering is a deployment-specific extension (Phase 7.5).

CLI: `python3 -m framework.learning.skill_induction --min-cluster-size 3 --dry-run --json`

## Tests (19 new)

`framework/learning/tests/test_phase7.py`:

- **TestHatGraduation** (5 tests): no events → no candidates; below threshold; threshold met (with capabilities); already-promoted excluded; OVI regression blocks
- **TestExperienceRecords** (5 tests): valid record; invalid lesson_type rejected; invalid scope rejected; emits event; filter by actor/lesson_type
- **TestSkillInduction** (7 tests): no records → no clusters; below min_size; threshold met → cluster; narrow-scope excluded by default; draft written + event emitted; idempotent overwrite refreshes; sorted by size desc

Full suite: **582/582 pass** (was 563; +19 new Phase 7 tests).

## Files touched

- `framework/roles/hat_graduation.py` (NEW, ~180 lines)
- `framework/learning/__init__.py` (NEW, marker)
- `framework/learning/experience.py` (NEW, ~160 lines)
- `framework/learning/skill_induction.py` (NEW, ~210 lines)
- `framework/learning/tests/__init__.py` (NEW, marker)
- `framework/learning/tests/test_phase7.py` (NEW, 19 tests)
- `docs/convergence-analysis-2026-05-26/phase-7-log.md` (this file)

## Deferred / out-of-scope

- **Pgvector semantic clustering for skill induction** — Phase 7 uses exact-match `(lesson_type, trigger_signal)` clustering. Voyager's original semantic clustering belongs in a Phase 7.5 once an embedding pipeline exists for experience records. Cost-prohibitive without batching.
- **Captain DM on hat graduation proposal** — currently emits an event; Phase 3 deferred the Telegram delivery for proposals to a unified Captain-DM mechanism (Phase 8 / MacMini hardening will wire all proposal types — role evolution, hat graduation, skill induction — to one notification channel).
- **48h retro skill-induction integration** — the retro skill should call `induce_drafts()` and surface the queue. Single line; folded into Phase 9 retro audit.

## Resume signal

Phase 7 complete. Next: **Phase 8 — MacMini hardening** (code-signing runbook, watchdog hardening, UPS monitoring, backups, `--check` mode for setup-mac.sh).
