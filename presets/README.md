# presets/ — Use-case configurations

A **preset** is a configuration overlay that adapts the Captain's Cabinet framework for a particular mode of operation. Presets define:

- Which agent archetypes pre-scaffold (work: CoS, CTO, CPO, CRO, COO; personal: coaches)
- Terminology defaults ("officer" vs "coach", "sprint" vs "cycle")
- Constitution and safety addenda specific to the use case
- Additional database schema beyond the framework base
- Default autonomy levels and hook defaults per use case
- Default skill sets and warroom conventions

A preset is **not** a separate codebase, a fork, or an alternate framework. It's a configuration overlay within one framework.

## Shipped presets

| Preset | Status | Description |
|--------|--------|-------------|
| `work/` | Active | Product-team shape: CoS / CTO / CPO / CRO / COO, Linear-or-Library backlog, Notion-or-Library business brain, product repo workspace. |
| `portfolio/` | Active | Portfolio shape: one persistent Chair (id `cos`, single Telegram bot) + one on-demand CEO officer per lane, generated from `agents/_lane-ceo.md.template` into `instance/agents/`. Functional depth via hats + hat graduation and Sonnet crew, not extra fulltime officers. |
| `step-network/` | Active | Multi-project pool shape: the work-preset officer roster shared across related projects, pre-warmed tmux session pool, single_ceo bot mode. |
| `personal/` | Placeholder | Coaching / life-operator shape. Empty until Phase 2 of the Cabinet v2 arc populates it. |
| `_template/` | Template | Skeleton for creating a new preset. Copy to `presets/<your-name>/` and customize. |

## Preset structure

Every preset follows this layout:

```
presets/<name>/
├── preset.yml              # Preset metadata (name, description, agent archetypes, autonomy, onboarding defaults)
├── terminology.yml         # Term mappings (e.g. "agent" → "officer")
├── constitution-addendum.md  # Preset-specific Constitution additions
├── safety-addendum.md      # Preset-specific safety rules + approved integrations
├── schemas.sql             # Additional database tables for this use case
├── agents/                 # Pre-scaffolded agent definitions (one .md per role)
│   ├── cos.md
│   ├── cto.md
│   └── ...
├── skills/                 # Preset-specific skill defaults
└── starter-spaces/         # Preset-specific Library starter Spaces + seed records (optional; see below)
```

Framework files in `framework/` plus the active preset's files compose into the runtime Cabinet state via `cabinet/scripts/load-preset.sh`.

## Library starter spaces (`starter-spaces/`)

A preset may ship Library Spaces pre-populated with seed records, so a fresh
deployment's Library ("Notion-or-Library business brain") starts useful
instead of empty. One YAML file per Space at
`presets/<slug>/starter-spaces/<space>.yml`:

- **Space fields** — `name` (unique natural key), `description`,
  `schema_json`, `starter_template`, `access_rules` — same shape as the
  legacy space-only JSON templates in `cabinet/starter-spaces/*.json`
  (installed by `install-starter-space.sh`; the YAML path supersedes it for
  presets and additionally seeds records).
- **`records:`** — a list of seed record stubs: `title`, `labels`,
  `schema_data`, `content_markdown` (may carry `[[wikilink]]` refs by exact
  title; the backlink index builds when a record is next saved via the
  dashboard). Template quality: generic org content with `<placeholders>` —
  no personal data, no real customer names.

Seed with:

```bash
bash cabinet/scripts/seed-library.sh [--preset <slug>] [--space <basename>] [--dry-run]
```

Defaults to the active preset. Idempotent by existence check: a Space is
matched by `name` and reused as-is (never overwritten); a record is matched
by (space, title) across all versions, so re-runs never duplicate seeds,
never overwrite edits, and never resurrect deleted records. Writes ride the
Library's own path (`cabinet/scripts/lib/library.sh`): parameterized inserts,
inline voyage-4-large embeddings (NULL + ILIKE fallback when Voyage is
unavailable), best-effort `cabinet_memory` queue.

Shipped: `work/starter-spaces/business-brain.yml` (Business Brain: start-here
index, product overview, customers & segments, decisions index, operating
principles) and `step-network/starter-spaces/business-brain.yml` (pool
flavor: project index + customers & partners, records tagged per project).
The officer loop-prompts' reflection ritual (`cabinet/loop-prompts/*.txt`)
instructs officers to land durable business/product/customer facts into the
seeded 'Business Brain' Space via the library MCP `library_create_record`.

## How the active preset is chosen

`instance/config/active-preset` — a flat file whose only content is the preset slug (e.g. `work`). The loader reads this at container start.

Default: `work`. Forkers who don't change this get the default work-preset behavior (a product-team cabinet: CoS/CTO/CPO/CRO/COO).

## Switching presets

1. Stop officers (cabinet/scripts/suspend-officer.sh on each)
2. Edit `instance/config/active-preset` to the new preset slug
3. Run `cabinet/scripts/load-preset.sh` manually, or restart the container
4. Resume officers

Schema migrations are additive-only (per Captain directive 2026-04-16) — switching presets preserves existing data. To wholesale reset, use `cabinet/scripts/reset-preset-schemas.sh` (opt-in, does NOT run automatically).

## Editing an existing preset

Preset source files (`presets/<slug>/...`) are NOT the runtime artifacts officers read. The loader assembles runtime state at session start:

- `presets/<slug>/constitution-addendum.md` → concatenated into `/tmp/cabinet-runtime/constitution.md`
- `presets/<slug>/safety-addendum.md` → concatenated into `/tmp/cabinet-runtime/safety-boundaries.md`
- `presets/<slug>/agents/*.md` → copied into `.claude/agents/*.md`

When you edit any preset source file mid-session, the runtime copies stay stale until either `load-preset.sh` runs again or officers restart. To propagate edits immediately:

```
bash cabinet/scripts/load-preset.sh
```

The loader is idempotent — safe to run at any time. Running officers won't pick up the change until their next post-compact refresh or restart, but at least the on-disk runtime state matches the source.

## Creating a new preset

```
cp -r presets/_template presets/my-new-preset
$EDITOR presets/my-new-preset/preset.yml
$EDITOR presets/my-new-preset/agents/*.md
# ...customize all _template files...
echo my-new-preset > instance/config/active-preset
# restart officers
```

See `memory/skills/evolved/create-preset.md` for the full skill.

## Inheritance / composition

Locked per Captain decision 2026-04-16: **flat only, no inheritance** until 3+ presets share structure and duplication becomes painful. A preset is self-contained; duplicate content across presets is accepted.
