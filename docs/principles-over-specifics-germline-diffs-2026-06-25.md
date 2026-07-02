# Germline diffs — PREPARED FOR NATE (do not auto-apply)

> **STATUS (updated 2026-06-25, "Apply!" granted):**
> - **`org-runtime-native.md` field-set → schema ref — APPLIED.** This file is NOT in the `pre-tool-use.sh` germline case list (only `brain-bridge.md` + `courses-of-action.md` are), so it was editable directly. The inline metadata enumeration is replaced with the schema pointer.
> - **`investigation_sources` companion config — APPLIED** at `instance/config/contexts/_default.yml` (carries today's six sources verbatim; portfolio-default inherited by lanes; no `slug:`/`capacity:` so it is inert to the context_slug cache).
> - **G-5 `courses-of-action.md §1` — STILL PENDING (germline-blocked).** `courses-of-action.md` IS in the germline case list, so the hook blocks officer/loop edits. The clean ready-to-paste §1 block is at `docs/germline-courses-of-action-ready-to-apply.md` — Nate applies it in one paste.
>
> The Current/Proposed blocks below are retained for reference + audit.

Part of the principles-over-specifics collapse (see `docs/principles-over-specifics-audit-2026-06-25.md`). These two edits land in **germline `.claude/rules/` files**, which the `pre-tool-use.sh` hook makes read-only for every officer and loop (germline set, `pre-tool-use.sh` ~line 936). **No officer/loop may edit its own judge** — so these are proposals; **only Nate applies them.**

The CLAUDE.md collapses (G-1..G-4, G-6, G-7, G-8, timezone) are already applied (CLAUDE.md is NOT germline — it is absent from the germline case list, so it was editable directly). What remains are the two germline items the audit flagged: **G-5** (`courses-of-action.md §1`) and the **`org-runtime-native.md` field-set**.

Both follow the same shape as the rest of the cleanup: replace an **enumeration-that-must-grow** (here, a hardcoded comms-shaped source list / a hardcoded metadata field-set) with **the bar/contract as principle**, and push the concrete inventory to **per-lane config** (`instance/config/`) and the **schema** (`framework/schemas-base.sql` / `framework/events/schema.sql`) — the layers that already own those facts and scale across presets.

> Note on `org-runtime-native.md`: it is **not literally in** the `pre-tool-use.sh` germline case list today (only `brain-bridge.md` and `courses-of-action.md` from `.claude/rules/` are). It is treated as germline here **conservatively** because it is a judge-adjacent org-runtime rule and the task scoped it as prepare-don't-edit. If you'd rather, this one is technically editable directly — your call. (If you do add it to the germline list while applying, that's a one-line change in `pre-tool-use.sh` line 936's `case` alternation.)

Nothing below has been written to the live files.

---

## G-5 — `.claude/rules/courses-of-action.md` §1 (investigation bar)

**Why.** §1 today hardcodes a **comms-shaped 6-source list** (full thread + To/CC, person intel, open commitments, task-board state, codebase pillar, drafting-lessons/captain-model). That list is correct for a reply-to-a-message situation but is an enumeration that will rot and mis-fit other lane situations (a deploy decision, a schema change, a calendar conflict each implicate a *different* source set). The durable thing is **the bar as a principle** — "assemble every source the situation implicates, and if you can't, name the gap instead of proposing." The concrete *source inventory per situation-type* belongs in **per-lane config** so each lane (and each future preset) declares its own without editing germline.

### Current text (lines 15-38)

```markdown
## 1. Investigation bar — gather, then propose

Before ANY proposal touching the Captain's world, assemble ALL of the
following that the situation implicates:

- **The full thread** — every message in the conversation, not just the
  latest, **plus the complete To/CC audience**. A reply drafted without the
  audience is malformed by definition.
- **Person intel** for each counterparty (via the brain MCP person-intel
  surface where configured).
- **Open commitments** in both directions (owed by / owed to the Captain)
  touching the person or topic.
- **Task-board state** — the lane's backlog and any tracked item this
  situation touches or should touch.
- **The codebase pillar** when the matter is technical — indexed
  architecture / commits / deployment / schema, not memory of the code.
- **Drafting lessons and the captain model** via the brain MCP — these
  inform tone and judgment and must never be quoted into anything outbound
  (see `.claude/rules/brain-bridge.md`).

**If the bar cannot be met** — a source is unreachable, intel is missing,
the thread is truncated — **say exactly what is missing instead of
proposing.** A named gap is useful; a proposal built on a partial view is
the recorded failure mode.
```

### Proposed replacement

```markdown
## 1. Investigation bar — gather, then propose

Before ANY proposal touching the Captain's world, assemble **every source the
situation implicates** — the complete picture, not the latest fragment. The
bar is a principle, not a fixed checklist: the sources a situation implicates
depend on the situation (a reply implicates the full thread + its complete
To/CC audience; a technical change implicates the indexed codebase pillar; a
commitment-touching matter implicates open commitments in both directions; a
tracked matter implicates the lane's board state; a counterparty matter
implicates that person's intel). Always gather tone/judgment inputs (drafting
lessons + the captain model via the brain MCP) — and **never quote them into
anything outbound** (see `.claude/rules/brain-bridge.md`).

The per-lane **source inventory** — which concrete sources each situation-type
implicates, and how to reach them — lives in the lane's config
(`instance/config/contexts/<lane>.yml` → `investigation_sources`, with a
portfolio-wide default). Consult it to instantiate the bar for the situation
at hand; it scales across lanes and presets without editing this germline rule.

**If the bar cannot be met** — a source is unreachable, intel is missing, the
thread is truncated — **say exactly what is missing instead of proposing.** A
named gap is useful; a proposal built on a partial view is the recorded
failure mode.
```

### Companion config to seed (NOT germline — Nate or an officer can add)

Add an `investigation_sources` block to the portfolio default + each lane context
(`instance/config/contexts/*.yml`). Suggested portfolio default, carrying exactly
today's six sources so nothing is lost:

```yaml
# instance/config/contexts/_default.yml (or each lane file)
investigation_sources:
  # situation-type -> sources the bar must assemble for it.
  message_reply:
    - full_thread_with_to_cc        # every message + complete To/CC audience
    - person_intel                  # brain MCP person-intel, each counterparty
    - open_commitments_both_ways    # owed-by / owed-to the Captain, this person/topic
  technical_change:
    - codebase_pillar               # indexed architecture/commits/deployment/schema
    - task_board_state              # lane backlog + the tracked item touched
  tracked_item:
    - task_board_state
    - open_commitments_both_ways
  # always, every situation (judgment inputs — never quoted outbound):
  always:
    - drafting_lessons
    - captain_model
```

---

## G-6 (germline companion) — `org-runtime-native.md` field-set → schema reference

**Why.** The rule enumerates a **metadata field-set** inline ("mission, node, owner role, acceptance criteria, evidence requirement, verifier role, risk level" + "role, mission, node, risk, evidence"). That set is owned by the **schema** (`org_events` / `claude_native_tasks` in `framework/schemas-base.sql` + `framework/events/schema.sql`). Duplicating it in prose means it rots the moment the schema gains/renames a field. The durable rule is the **contract** ("native Task is not Cabinet work until it carries the org-runtime metadata the schema requires"); the **field list** should be a pointer to the schema, which is the single source of truth.

### Current text (full file, lines 1-11)

```markdown
# Org Runtime Native Rule

Claude Code is the working surface. The org runtime is the durable truth.

- Use native Claude Code Tasks for active execution, but include Cabinet metadata so task hooks can project work into `org_events` and `claude_native_tasks`.
- Treat `org_events` as the first durable record for meaningful organizational transitions: mission changes, role work, task lifecycle, evidence, verification, policy decisions, and learning.
- Do not make `/tasks`, markdown notes, Redis state, Telegram text, or local memory the only source for a state transition.
- If a native Task lacks a mission, node, owner role, acceptance criteria, evidence requirement, verifier role, or risk level, add the missing metadata before relying on it as Cabinet work.
- `/tasks` is a compatibility projection until the cutover is complete; prefer mission/work-graph state for new work.
- Hooks and broker decisions should carry role, mission, node, risk, and evidence context whenever that context is available.
```

### Proposed replacement

```markdown
# Org Runtime Native Rule

Claude Code is the working surface. The org runtime is the durable truth.

- Use native Claude Code Tasks for active execution, but include the Cabinet
  metadata the org-runtime schema requires so task hooks can project work into
  `org_events` and `claude_native_tasks`. **The required field-set is owned by
  the schema** (`framework/schemas-base.sql` + `framework/events/schema.sql`) —
  consult it, don't re-enumerate it here. As of this writing it covers mission,
  node, owner role, acceptance criteria, evidence requirement, verifier role,
  and risk level; a native Task missing what the schema requires is not yet
  Cabinet work — add the metadata first.
- Treat `org_events` as the first durable record for meaningful organizational
  transitions (mission changes, role work, task lifecycle, evidence,
  verification, policy decisions, learning). Do not let `/tasks`, markdown
  notes, Redis state, Telegram text, or local memory be the ONLY source for a
  state transition.
- `/tasks` is a compatibility projection until cutover; prefer mission/work-graph
  state for new work. Hooks and broker decisions carry the schema's
  role/mission/node/risk/evidence context whenever it is available.
```

---

## Apply checklist (for Nate)

1. Apply the G-5 replacement to `.claude/rules/courses-of-action.md` §1.
2. Apply the G-6 replacement to `.claude/rules/org-runtime-native.md` (optionally add it to the `pre-tool-use.sh` germline case list while you're there, if you want it judge-protected).
3. Seed the `investigation_sources` block in `instance/config/contexts/*.yml` (companion config — not germline; safe for an officer to add once you OK the shape).
4. Nothing references the old prose by anchor, so no doc-sync fan-out is needed (verified by grep over `docs/ cabinet/ .claude/ presets/ framework/`).
