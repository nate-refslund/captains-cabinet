# Courses of Action §1 — READY TO PASTE (germline; only the Captain applies)

`.claude/rules/courses-of-action.md` is in the `pre-tool-use.sh` germline set
(line 936 case alternation), so no officer/loop may edit it — the hook blocks
the write. This is the clean, ready-to-paste §1 replacement so you apply it in
one move.

**Instruction:** open `.claude/rules/courses-of-action.md` and paste the
**Proposed** block below over **§1, lines 15–38** (from the `## 1. Investigation
bar — gather, then propose` heading through the `...recorded failure mode.`
paragraph, i.e. everything between the germline-note paragraph that ends on
line 13 and the `## 2.` heading on line 40). Leave §2, §3, and Scope untouched.

The companion config this replacement points at is **already applied** —
`instance/config/contexts/_default.yml → investigation_sources` (carries
today's six sources verbatim, so nothing is lost in the move).

---

## Current §1 (lines 15-38 — being replaced)

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

---

## Proposed §1 (PASTE THIS over lines 15-38)

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
