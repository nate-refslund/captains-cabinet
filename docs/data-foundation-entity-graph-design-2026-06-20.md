# Data foundation: entity + link layer — design — 2026-06-20

Nate: the data foundation (storage AND retrieval) is the substrate everything
relies on — make it solid, scalable, high-quality, not over-engineered. And:
"is the data properly linked? person → interactions → projects → meetings …?"

## Grounded diagnosis (what exists today)
STORAGE — strong base, no link layer:
- Truth = markdown vault, well-organized: `3-People/{slug}/` (dossier +
  `conversations.md` with `<!--recip:{to,cc}-->` markers), `2-Meetings/`
  (frontmatter `participants: [[Person]]`, `meeting_id`), `4-Projects/`,
  `6-Commitments/`, `8-Archive/activities/`.
- Derived = one sqlite embeddings index: `chunks(id, path, heading, text, mtime,
  size, tokens, file_hash, chunk_idx, content_ts)` + FTS5(text). Indexes on
  path + mtime. Voyage embeddings + BM25 + recency + rerank. ~34k chunks.
- **The chunk has NO entity columns.** Its only structural links are `path`
  (folder) and `text`. The `[[wikilinks]]`, `participants`, `recip` to/cc — all
  the real edges — live in markdown and are NEVER parsed into the index.

RETRIEVAL — good semantic search, no graph traversal:
- `resolve_entity` is **person-only** (by its own admission). Projects, mail
  threads, group chats, meetings are not entities.
- `gather(person, topic)` = person-anchored vault chunk-search + live fetchers.
- No entity-card assembler, no edge traversal. "Ulrik → his meetings/projects/
  threads/commitments" is impossible structurally — only text-search-and-hope.

VERDICT: **organized, not linked.** The latent links are all captured; they are
just not promoted into a queryable layer.

## Design: a derived entity + edge graph (lean; markdown stays truth)
Add a small graph DERIVED from the markdown that already encodes the links. No
new source of truth, no graph DB — three sqlite tables alongside the chunk index.

1. **entities** `(entity_id, type, canonical_name, aliases[], profile_ref,
   first_ts, last_active_ts)`. type ∈ person | project | meeting | thread |
   group | org. Seed: people ← `3-People/`; projects ← `4-Projects/` + Monday
   products/epics + repo names; meetings ← `2-Meetings` (`meeting_id`); threads
   ← conversation/thread ids; groups ← Teams `chatId`; orgs ← dossier orgs.
   `resolve_entity(handle, type=None)` extends the existing person resolver to
   all types with alias expansion (dedup: one project ≠ three entities).

2. **edges** `(src, dst, edge_type, weight, first_ts, last_ts, evidence_ref)`.
   edge_type ∈ participated_in | in_thread | owns_commitment | touches_project |
   mentions | manages | … . DERIVED by extraction from data already present:
   - meeting `participants: [[X]]` → person↔meeting
   - `conversations.md` recip to/cc + per-message → person↔thread, person↔person
   - commitment frontmatter (person, subject) → person↔commitment, commitment↔project
   - any `[[wikilink]]` → typed edge; co-occurrence in a chunk → weak edge
   - git/Monday (optional later): author/assignee → person↔project
   Every edge carries `evidence_ref` (the note/line it came from) → traceable.

3. **chunk_entities** `(chunk_id, entity_id, role)` — the chunk↔entity backlink,
   derived at index time from the note's folder + frontmatter + `[[links]]` +
   recip. THIS is what makes retrieval entity-scoped instead of text-only:
   "all chunks linked to entity X", not "chunks whose text says X".

4. **entity_card(ref, type=None)** — the retrieval primitive. Resolve → traverse
   edges → assemble faceted, recency/salience-ranked:
   `{profile, relationship, recent_interactions[], activities[], communications[],
   commitments[], related_entities[], open_threads[]}`. Works UNIFORMLY for
   person | project | thread | group because all are entities with edges.
   `gather()` becomes: entity_card (structured backbone) + a semantic topic
   overlay for the long tail. The card is better context for the clone AND the
   direct answer to "Ulrik Kristensen → everything", "PolAds → everything",
   "the DPA thread with Lisa → everything".

## Why this is lean, not over-engineered
- Reuses the captured links (wikilinks/frontmatter/recip) — extraction, not new
  capture. Markdown stays the single source of truth; the graph is rebuildable.
- sqlite tables next to the existing index — NO graph DB, NO ML entity-linking,
  NO realtime graph service. Deterministic extraction at index time.
- Additive + backward-compatible: today's chunk search keeps working; the card
  layer sits on top. content_ts (the time clock) is reused for recency + the
  leak fence the fidelity harness needs.
- AVOID (explicit non-goals): Neo4j/ontologies, embedding the graph, fuzzy ML
  coref beyond the alias table, per-keystroke updates.

## Quality + scalability levers (the "solid" part)
- **Linkage coverage** (the new top metric): % of chunks with ≥1 entity edge.
  Today ~0 structural; target near-100% for people/meetings/threads (the links
  exist, just unparsed).
- **content_ts coverage** ~62% (honest NULLs) — raising it improves recency +
  time-fencing. Quality lever, already on pi-agent's radar.
- **alias/dedup quality** — one canonical entity per real-world thing.
- Scales: 34k chunks → ~10⁴ entities + ~10⁵ edges = trivial for sqlite.

## Build split (coordination — this is pi-agent's estate)
- ESTATE-SIDE (pi-agent owns `~/.screenpipe/pipes`): entities/edges/chunk_entities
  tables, the extraction pass at index time, `resolve_entity` typing, and
  `entity_card`. This is the real build; it must NOT collide with pi-agent's
  in-flight retrieval work → ship as this spec for pi-agent (Nate relays), or a
  coordinated co-build.
- CABINET-SIDE (me, no estate edits): once `entity_card` exists, the fidelity
  `gather_cutoff_context` consumes it (structured, leak-fenced) → richer clone
  context for the decision/reply cells. I can prototype the card CONSUMER against
  a stub now so the cabinet side is ready the moment the estate side lands.

## Migration
Additive only. Build the graph from a full index pass (rebuildable any time);
markdown unchanged; chunk search unchanged; card layer is new surface. Roll out
people+meetings+threads first (links are densest + cleanest), projects+groups next.
