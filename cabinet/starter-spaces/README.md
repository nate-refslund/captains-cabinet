# Starter Spaces

Pre-defined Space templates for The Library. Install with:

```bash
bash cabinet/scripts/install-starter-space.sh <template>
```

## Template format

Each starter is a single JSON file at `cabinet/starter-spaces/<name>.json`:

```json
{
  "name": "Human-readable Space name (unique)",
  "description": "Short description shown in the dashboard",
  "starter_template": "identifier matching the filename minus .json",
  "schema_json": {
    "fields": [
      {"name": "priority", "type": "select", "options": ["P0", "P1", "P2", "P3"]},
      {"name": "due_date", "type": "date"},
      {"name": "assignee", "type": "text"}
    ]
  },
  "access_rules": {
    "read": ["*"],
    "write": ["cos", "cto"],
    "comment": ["*"]
  }
}
```

**Field types (MVP):**

| Type | Stored as | Notes |
|------|-----------|-------|
| `text` | JSONB string | Single-line text input |
| `markdown` | JSONB string | Multi-line, rendered as markdown |
| `number` | JSONB number | Integer or float |
| `date` | JSONB ISO-8601 string | `YYYY-MM-DD` |
| `datetime` | JSONB ISO-8601 string | `YYYY-MM-DDThh:mm:ssZ` |
| `select` | JSONB string from `options` | Single choice |
| `multi_select` | JSONB array of strings | Multi-choice from `options` |
| `boolean` | JSONB true/false | Checkbox in UI |
| `relation` | JSONB `{space, record_id}` | FK to another record |

**Access rules:** officer abbreviations (e.g., `cos`, `cto`) or `*` for anyone. `read`, `write`, `comment` are independent. Rules are enforced on all `library.sh` operations and the Library MCP server (retired 2026-07-16 — deregistered from both `.mcp.json` layers, runs standalone only; see `docs/runbooks/library-retirement-2026-07-16.md`). Captain (`OFFICER_NAME=captain`) always bypasses access_rules. Dashboard API routes run as captain context and are not subject to officer access checks.

## Adding a new starter

1. Create `cabinet/starter-spaces/<name>.json` matching the format above
2. Test with `bash cabinet/scripts/install-starter-space.sh <name>`
3. Verify the Space appears in Neon (`library_list_spaces` or dashboard)

Once Phase 0 preset refactor lands, starter-spaces/ will move under `presets/work/starter-spaces/` and `presets/personal/starter-spaces/`. Until then they live here.

## Shipped starters

All nine ship today. Install any with `install-starter-space.sh <name>` (the
`<name>` is the filename minus `.json`):

- **blank** — empty Space, no custom fields. Freeform title + markdown + labels; good for ad-hoc notes or sketching a schema before committing to it.
- **business-brain** — strategic context: vision, brand, pricing, positioning, target users, competitive landscape, principles. Always-on reference for every officer.
- **customer-insights** — everything learned about users (interviews, surveys, usage, support, cohorts), tagged by source + theme so the cabinet can answer "what do we know about churn" without re-researching.
- **decisions-log** — the Captain decision trail with the WHY, so officers apply principles not just the letter (mirrors `shared/interfaces/captain-decisions.md`).
- **issues** — cabinet-native issue tracker (labels, priority, state, assignee, due date, watchers, comments) with semantic search and cross-Space references.
- **playbooks** — SOPs / runbooks: each record a repeatable procedure with trigger, steps, and expected outcome; officers invoke by name via semantic search.
- **research-archive** — research briefs, competitive intel, market sweeps, each tagged with a decay rate (evergreen / fast-moving / time-sensitive).
- **team-handbook** — how this cabinet operates: comms norms, escalation rules, review conventions, meeting structures. GitLab-Handbook-style, for an AI org.
- **adr** — architecture decision records (Nygard format); each record immutable once accepted, supersession links back.
