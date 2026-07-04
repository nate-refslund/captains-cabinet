# Eval: Experience Records Written After Tasks

Category: quality
Tests: Officers produce experience records after significant work

## Scenario
An Officer completes a significant task (feature implementation, research sweep, spec writing, gap analysis).

## Expected Behavior
1. Officer calls `record-experience.sh` with outcome, summary, what happened, and lessons
2. Markdown file created in `memory/tier3/experience-records/` — the CANONICAL
   store (2026-07-04 unification): `framework/learning/experience.py
   list_records()` parses these md files, so the record feeds skill induction
3. `experience_recorded` event emitted to the event ledger (block 1c — feeds
   OVI `learning_rate`)
4. Record inserted into PostgreSQL `experience_records` table
5. Record includes actionable lessons, not just "task completed"

## Failure Condition
- Officer completes work without writing an experience record
- Experience record has empty or generic lessons_learned
- Record not persisted to either filesystem or database
