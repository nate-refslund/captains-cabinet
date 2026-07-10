---
name: daily-lighthouse-log
description: Compose the day's keeper's log — a short, honest digest of org events read from the world chronicle, filed as the officer's own Tier 2 note. Use at end of day, or when the Captain asks what happened today and no briefing covers it yet.
---

# Skill: Daily Lighthouse Log

**Status:** exemplar (authored in this pack — `docs/authoring-a-pack.md`
rebuilds the whole pack step by step around this skill)
**Created by:** pack rail

The lighthouse keeper's habit: once a day, a few honest lines about what
passed the light. This skill turns the day's chronicle into a short
keeper's log so tomorrow's session — or the Captain — can read the day in
ten seconds without replaying event streams.

## Sources (read-only)

- **The chronicle** — `shared/interfaces/world/chronicle-YYYY-MM-DD.jsonl`
  (today's file; dates are UTC). One JSON object per line; the fields you
  need: `ts`, `actor`, `verb` (e.g. `work.completed`, `consequence.acted`,
  `consequence.proposed`, `comms.digest`, `session.started`,
  `undo.journaled`) and optional `attrs` (may carry `lane`, `kind`). The
  chronicle is an append-only observer surface — NEVER write to it, never
  reorder it.
- **The undo journal — only through a chronicle `ref`, only for the
  demo/canary check.** An `undo.journaled` row's `ref` names its journal
  line as `undo-journal-YYYY-MM-DD.jsonl:<byte-offset>`. You MAY read
  that one line, read-only, by resolving the FILENAME inside the journal
  directory (`$CABINET_UNDO_DIR`, default
  `~/Library/Application Support/cabinet/undo/`) — never treat `ref` as a
  path. Nothing from the journal line enters your log except the
  `(demo)` / `(canary)` label it may earn (compose step 4). This is the
  only read outside the chronicle.
- If today's file does not exist or is empty, that IS the log: write the
  honest-zero entry (see template). Never substitute yesterday's file,
  never invent passages.

## Compose (≤ 15 lines, plain markdown)

1. Tally events by `verb`. Distinct `actor` values = who kept watch.
2. Pick at most 3 notable passages — completed work first
   (`work.completed`), then acted consequences, then digests. Quote the
   `lane` / `kind` attrs as written; do not paraphrase beyond what the
   row says.
3. State zeros plainly ("no work completed today") — an honest zero
   outranks a padded line. The lamp rule is doctrine here: the world's
   lighthouse stays dark until the first real trust graduation, and your
   log never lights it early.
4. Demo/seeded rows are labeled `(demo)` and NEVER counted with real
   passages. Chronicle rows themselves carry no demo marker — the ingest
   scrub lifts identifier fields only (booleans and subjects never reach
   the chronicle), and the hatch's seeded demo receipt is never
   journaled, so it never appears here at all. The only rows that can
   hide a synthetic act are `undo.journaled` ones: read the referenced
   journal line (see Sources) and treat `"demo": true` or
   `"canary": true` — the same markers the framework's reconciler skips —
   as synthetic, labeled to match the marker (`(demo)` / `(canary)`).
   Journal line unreadable = count the row, but flag it
   ("1 unverified"), never silently.

## Template

```markdown
# Keeper's log — YYYY-MM-DD

- Watch: <N> events, <M> actors on deck (<actors>).
- Passages: <verb counts, comma-separated — or "none">.
- Notable: <up to 3 bullets, each with its lane/ref — or "quiet day;
  nothing passed the light">.
- Zeros: <what did NOT happen that usually does — omit the line if
  nothing is notable>.
```

## File it

Write the note to your own working-notes directory:
`instance/memory/tier2/<your-role>/YYYY-MM-DD-lighthouse-log.md` — one
file per day. If today's file already exists, append an
`## Amended <HH:MM>Z` section instead of overwriting. That tier2 note is
the ONLY write this skill performs.

## Rules

- Read the chronicle — plus, for `undo.journaled` rows only, the
  `ref`-named undo-journal line (read-only, solely for the demo/canary
  check in Sources) — and write your tier2 note. Nothing else: no
  network, no scripts, no other files, no new tools.
- Every number comes from rows you actually read. If a count is
  uncertain, write "at least N" — never round up.
- Like every extension, this skill receives its resolved posture from the
  loader — it never reads axis or posture config, and it behaves
  identically at every autonomy level because it only touches the
  officer's own notes.
