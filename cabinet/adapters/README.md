# Cabinet Adapters — External-System Bridges

Adapters bridge Cabinet's canonical stores (Library + /tasks) to external systems (Notion, Linear, GitHub, Asana, etc.). They are **bidirectional mirrors**, not lifecycle orchestrators.

Per A11 (Captain ratification): Library + /tasks are canonical. Notion + Linear are legacy adapters retained for organizational continuity, not source of truth.

## What an adapter IS

- A bidirectional mirror: state changes in Cabinet flow out; state changes in the external system flow in.
- A field-mapping definition (Cabinet schema ↔ external system schema).
- A webhook receiver (for inbound) + an outbound push API.
- A conflict-resolution policy (`cabinet_wins` | `external_wins` | `newest_wins` | `manual`).

## What an adapter is NOT

- A lifecycle orchestrator. Adapters don't decide what work happens — Cabinet officers do, and the adapter just propagates the resulting state.
- A workflow engine. Workflow lives in officer roles + skills + specs.
- A required dependency. Adapters can all be `enabled: false` and Cabinet works fine — the external systems just won't reflect Cabinet state.
- A substitute for native Cabinet capability. If you need a feature, build it in Cabinet first (Library Spaces + /tasks); the adapter mirrors it out, not the other way around.

## Adapter contract

```typescript
interface CabinetAdapter {
  // Identity
  name: string;                          // 'notion', 'linear', 'github-issues'
  type: 'tasks' | 'library' | 'both';    // what stores this adapter mirrors

  // Outbound (Cabinet → external)
  pushTask?(task: TasksRecord): Promise<{ external_id: string }>;
  pushSpace?(record: LibraryRecord, space: string): Promise<{ external_id: string }>;

  // Inbound (external → Cabinet) — adapter-side webhook handler invokes this
  pullTask?(external_id: string): Promise<TasksRecord>;
  pullSpace?(external_id: string, space: string): Promise<LibraryRecord>;

  // Conflict resolution
  resolveConflict: 'cabinet_wins' | 'external_wins' | 'newest_wins' | 'manual';

  // Webhook receiver (HTTP endpoint registered with the external system)
  handleWebhook?(payload: unknown): Promise<void>;
}
```

## Adapter layout (per-adapter directory)

```
cabinet/adapters/<adapter-name>/
├── README.md            — adapter docs: scope, mapping, conflict policy, setup
├── adapter.ts           — CabinetAdapter implementation (or .js/.py for non-TS adapters)
├── webhook.ts           — webhook endpoint receiver
└── field-mapping.yml    — declarative Cabinet ↔ external field mapping
```

## Configuration

Per-deployment adapter toggles live in `instance/config/adapters.yml`:

```yaml
adapters:
  notion:
    enabled: false       # legacy — default off
  linear:
    enabled: false       # legacy — default off
  github-issues:
    enabled: false       # Cabinet framework backlog (FW-* tickets)
```

Adapters check this file at startup; `enabled: false` means dormant (no webhook subscription, no outbound push).

## Adding a new adapter

1. Create `cabinet/adapters/<your-adapter>/` following the adapter layout above
2. Implement `adapter.ts` against the `CabinetAdapter` interface
3. Define `field-mapping.yml` for Cabinet ↔ external field correspondence
4. Add `<your-adapter>: { enabled: false }` to `instance/config/adapters.yml` (default off until tested)
5. Register webhook endpoint in your deployment (Vercel/serverless route)
6. Validate via integration test: round-trip a task creation Cabinet→external→Cabinet
7. Flip `enabled: true` in `adapters.yml`

## Existing adapters

None yet — no adapter directories exist in this repo. Notion and Linear are reached today as direct integrations (Notion business brain via MCP; Linear as the read-only post-cutover archive), not through this adapter contract. The first adapter built here follows the layout + contract above.

## Per Spec 063 v1.1 Checkpoint 6.5 (adapter-contract scope)
