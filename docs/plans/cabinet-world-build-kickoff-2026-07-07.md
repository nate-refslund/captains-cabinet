# Cabinet World — build kickoff (ratified 2026-07-07)

**Status: Captain approved the full design 2026-07-07 ("I approve everything made"). This file is the handoff for the build session. Design is DONE — do not re-litigate it; build it.**

## Read first (authoritative, in order)
1. `~/cabinet-world-growth-design-2026-07-07.md` — growth model (§1–9), zoom/interiors/Post Office/universal inspect (§10), egg ontology (§11), fidelity/appearance + asset-order amendment (§12). **This is the spec.**
2. `~/cabinet-world-design-2026-07-06.md` — the chassis: events→animation grammar, engine/fork verdicts, cast/set design, E0–E4 plan, privacy/injection register. Where the two conflict, the 07-07 doc wins.
3. Mockup (approved look-and-feel for *structure*, not art): https://claude.ai/code/artifact/93df3500-e9f3-4e4b-a1bf-d95f4363f43c — zoom Z0–Z2, interiors, three-tab inspect. Real art = LimeZu packs, NOT this programmer art.

## Ratification record (all Captain-approved 2026-07-07)
- **morphology.yml v1 direction**: hardcode X→Y; pure function `world_at(T)=f_v(state_at(T))`; no LLM ledger→pixel; bases cadence-justified; rate-routing law; honest zeros; district anchors fixed. (The concrete morphology.yml file still lands via PR that the Captain merges — no auto-merge, ever.)
- **Expression seed**: minted at hatch; one Captain redream; freezes at first outcome ratification; retroactive seed for the mother cabinet (one-time, ledgered).
- **Captain-rename verb**: yes.
- **`/` flip criterion**: bake-off as written + two weeks of real defaulting.
- **Legend-Law amendment**: cite path = universal secondary gesture (right-click/long-press inspect at any zoom); Z0/Z1 primary click = navigation.
- **Post Office placement**: civic-anchor exception class, N=3, positions fixed in morphology.yml, each Captain-approved.
- **Egg ontology (§11)**: egg = cabinet-with-zero-events ONLY; officers = houses + lineage crests; crew = motes; supersedes chassis "crew eggs in nursery".
- **Asset order**: LimeZu ships in E1 day one (reverses Kenney-first).
- **Officer appearance channel (§12)**: seed-derived default; `captain.appearance_set` ledgered override; officer self-PROPOSE via variant-pack PR only.

## Captain's one noted gap
"Can't see the officers moving around and doing stuff." Correct — that is the event-driven show layer, impossible in a static mockup. E0/E1 deliver it from REAL data: Redis `cabinet:officer:activity:<slug>` is already a Sims-verb feed ({verb, object, since}, 5-min TTL); show-grammar.yml walks officers through scenes. **Treat visible live motion as the E1 acceptance headline.**

## Build order (dependency-gated; from §7 + §10.7 deltas)
1. **E0a — census keyframe writer (START HERE, ~0.5–1d).** Daily ~45-int census → `shared/interfaces/world-chronicle.jsonl` (falsifier-series discipline: append-only, flock, PII-free ints/enums only). Every un-censused day = permanent replay fog for file-count surfaces. Writer gets its own services.yml row + windmill. Census reads are FENCED LOCAL READS ONLY (`sqlite3 -readonly`, wc, ls, jq; never projection tables — they're 0 rows; memory via falsifier memory_ingestion block, no DB creds).
2. **E0b — world-chronicle daemon** (chassis E0): merge SQLite org_events (rowid cursor, read-only, busy-retry) + Redis presence/heartbeat/killswitch (plain XREAD, NEVER consumer groups) + consequence/undo JSONL + memory/logs tail → normalize to verbs → `chronicle-YYYY-MM-DD.jsonl` (monotonic ingest ids, secret/PII scrub AT INGEST) → XADD `cabinet:world:chronicle` MAXLEN + pub/sub poke + presence snapshot. Gate: same chronicle twice → frame-identical render (seeded PRNG keyed on event id; no Date.now/Math.random in render path).
3. **E1 — the Wardroom** (~6–10d + 3–4d camera): `/world` route + `/api/world/stream` SSE (clone tasks-stream pattern) in cabinet/dashboard; PixiJS pure renderer + deterministic TS director; **LimeZu assets from day one** (Captain buys packs — see Captain to-dos); quantized camera {0.5,1,2}+scene-swap, screen-space labels (Z2 legibility rules §10.6), **three-tab WHAT/NOW/PROOF inspect card built once here**, URL state `?z&x&y&in&sel(opaque)&at=`, killswitch break-through, morphology.yml v1 + binding-executor validator + auto-legend, `codex:` required on every entry. CI ratchets at route creation: no write server-actions under /world, text-only rendering, CSP. Gate: **the bake-off** (5 incident drills + "who is doing what right now in 10s at Z2" + "what is this object via secondary-click").
4. **E1.5 — emitter track** (parallel, each its own reviewed germline window): **PO-0 mail.* field-allowlist schema + CI PII injection tests FIRST (P0 — blocks all mail emitters; org_events is undeletable = GDPR)**, then PO-1 `mail.sent` in channel.py (~½d), subagent_started + parent chain + agent_type, role_created/retired; then PO-2/4/5/6 per §10.7 table.
5. **E2 — town + growth morphology + Post Office + replay** (rebudgeted 3.5–4.5wk, §10.7). Then E3 self-building (gated on loop-throughput evidence), E4 broadcast.

## Non-negotiable doctrine (enforce in code/CI, not discipline)
Renderer never writes; ledgers→world one-way; grammar files are the ONLY path to pixels; NO grammar change auto-merges (cosmetic included); privacy = two response schemas (T0–T3, kiosk fields absent-not-blanked, server-side); pids/slugs never in URLs/DOM (opaque handles); every binding declares scope/tier/replay/codex; volume ≠ structure (>1 event/day sources → textures only); honest zeros render prominent; era-pinned replay default; reserved salience palette dual-coded (red = killswitch/frozen ONLY); asset conformance gate (palette/grid/alpha) before any sprite enters the manifest; realpath containment for world assets; all world text renders as textContent.

## Run it as a cabinet mission
`mission-compile`: lane = system-self; CTO owns code; Chair owns grammar/narration taste; Captain merges grammar PRs + emitter germline windows. Worktree per the repo's convention (branch off current work; note `feat/fidelity-harness-design` is active with parallel sessions — coordinate, don't clobber; push per repo rules).

## Captain to-dos (only these)
1. **Buy LimeZu packs** (~$8: Modern Interiors + Modern Exteriors + Character Generator, limezu.itch.io) and drop them where the build session says — payment needs you. ✅ **DONE + INSTALLED 2026-07-08**: packs classified and installed to `cabinet/dashboard/public/world-assets/` (gitignored binaries; manifest.json v2 populated with 380 content-addressed 16px rows — interiors/office/exteriors/characters; gate GREEN). Farm + Serene Village staged under `staged-future/` with NO manifest rows (E2 inventory). The RPG-Maker-MV zips are 48px-only and superseded — **no repurchase needed**: the owned standard `modernexteriors-win` already ships the 16px originals; MV 48px sheets staged at `staged-future/mv-exteriors/` and must never get manifest rows (they'd pass the gate's 16-divisibility check while being semantically 3×-scaled). Character Generator app not needed — premade 16x16 sheets cover officer avatars (work/walk/idle/sleep per `Spritesheet_animations_GUIDE.png`).
2. **Merge morphology.yml v1 PR** when the build session opens it (the design tables are pre-approved; the merge is the founding grammar-as-law act).
3. Bake-off participation when E1 is ready (the 10-second drills are scored on you noticing).

## Context for the new session
Full design provenance: 3 ultracode panels (10 + 6 + 6 agents, all Fable 5) in session `3b93af29-5936-4d19-85be-ed80e482feb8` workflow journals (`wf_9f0810ed-54c`, `wf_62fdc913-bea`); chassis panel in session `8c780681` (`wf_b8495711-642`). Recon facts current as of 2026-07-07: org_events 137,089 rows; memory 619; evolved skills 9; captain rules 38; cells_graduated 0; intake pending 14; 4 officers (cos/polads-ceo/stephie-ceo/comms-officer); Mini hatch scheduled the night of 07-07 — verify whether it happened and whether its seed/island events need the retroactive-seed act.
