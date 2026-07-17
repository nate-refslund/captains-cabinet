# Library MCP Server — RETIRED (2026-07-16)

> **Library retirement (Captain-ratified 2026-07-16, closes memory-study
> Q4/C7):** this server is **deregistered** from `.mcp.json` and
> `.mcp.json.mac-native` — no officer or captain session boots it anymore
> (the `library` grants still listed in the germline `cabinet/mcp-scope.yml`
> are dangling-but-harmless until the next germline ceremony: an
> unregistered server grants nothing). Record content was exported to the
> vault archive (`cabinet/scripts/retire-library-export.py` →
> `vault/library-archive/`) and every record write is mirrored into
> `cabinet_memory`, so `memory_search` finds it. Tables stay in place,
> dormant — no destructive DDL. Full story:
> `docs/runbooks/library-retirement-2026-07-16.md`.

MCP server exposing The Library — Founder's Cabinet's structured-edit layer — as tool calls.

## Architecture

Delegates to `library.sh` via `child_process.exec`. All SQL injection safety, the cabinet_memory mirror queue, and JSON validation live in the Bash layer. The MCP server is a thin adapter. Since the retirement, record create/update writes NO per-record vector (the mirror queue is the search-continuity path); `library_search` ranks over legacy vectors where they exist with an ILIKE title fallback.

## Registration (deregistered 2026-07-16)

No longer present in `.mcp.json`. For one-off archaeology the server still runs standalone (below), or can be temporarily re-registered with the old block:

```json
"library": {
  "command": "bun",
  "args": ["run", "${CLAUDE_PROJECT_DIR}/cabinet/channels/library-mcp/index.ts"],
  "env": { "OFFICER_NAME": "${OFFICER_NAME:-captain-session}" }
}
```

The server reads `NEON_CONNECTION_STRING` (and, for legacy-vector search only, `VOYAGE_API_KEY`) from `cabinet/.env` at startup.

## Tools

| Tool | Description |
|------|-------------|
| `library_create_space` | Create or upsert a Space (collection) |
| `library_list_spaces` | List all Spaces |
| `library_create_record` | Create a record (vector-free since retirement; mirrored into cabinet_memory) |
| `library_update_record` | Update record, preserves version history (vector-free since retirement) |
| `library_get_record` | Fetch record + full version history |
| `library_search` | Search — legacy-vector cosine where vectors exist, ILIKE title fallback |
| `library_list_records` | List active records in a Space |
| `library_delete_record` | Soft-delete (data preserved) |
| `library_get_backlinks` | Records linking IN to a target via `[[wikilink]]` (Spec 045 Phase 1) |
| `library_graph_data` | `{nodes, edges, total_record_count}` JSON for the `/library/graph` view (Spec 045 Phase 2). Top-N by degree; optional `space_ids` filter; default `limit_nodes=500` (max 5000) |

## Running locally

```bash
OFFICER_NAME=cos bun run /opt/founders-cabinet/cabinet/channels/library-mcp/index.ts
```

## Testing with JSON-RPC

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | \
  OFFICER_NAME=cos bun run /opt/founders-cabinet/cabinet/channels/library-mcp/index.ts
```
