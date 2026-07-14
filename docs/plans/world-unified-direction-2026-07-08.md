# World-Unified — Ratified Direction (2026-07-08)

**Role of this doc:** the design-phase record for the Cabinet World UNIFIED ISLAND wave — one island, two
districts (Harvestholm village = cabinet self-work · Lantern Quay harbor = mission/product work). It carries
(I) the full spec v1 + Captain ruling addendum, (II) the feasibility verification run against the live estate,
and (III) the mockup + gate evidence. Ledger rows `WORLD-UNIFIED-{V1,V2,V3}` (todo, alpha lane) land alongside
this doc; the build phase re-reads this file before every commit. The 07-06 chassis, 07-07 growth design and
07-08 world-alive direction are LAW underneath; this doc sits inside them.

## Captain rulings recap (2026-07-08, all binding)

1. **Unified frame ratified:** ONE island, TWO districts — Harvestholm village (memory / skills / retros /
   apoptosis / brain organs as buildings) inland-north; Lantern Quay harbor (outcomes as cargo assembled on
   berths, shipped toward per-lane islands across the water on milestones) on the south coast.
   **Charterhouse rejected** (too guarded).
2. **Locked doctrine:** one continuous world, LOD zoom only, ≤2 render levels (island + the Great-House
   wardroom roof-cutaway). World render **READ-ONLY** — interactions may only navigate / inspect / deep-link
   to EXISTING gated surfaces; never a new actuator.
3. **Commute spec:** dominant-focus window 2–3 min; a visible 20–30 s walk on the one road with a
   thought-bubble ("I should ⟨verb⟩ …") from a closed verb→phrase table.
4. **Far islands:** product mini-districts, wiki-explorable (Obsidian-graph feel), library-with-real-queries,
   task visualization — **STAGED**: v1 island+commute+mailbox-view · v2 product districts+task viz ·
   v3 library-query.
5. **Four-library taxonomy** (post-design addendum, binding): home-house library (agent memory/skills) ·
   product-island library (that product's corpus only) · harbor library (the shipping record — *proposed
   interpretation of the Captain's "something third", flagged as an open call*) · **Charter Hall** (the
   Captain's decisions/intents/grants — officers visibly walk here to consult).
6. **Mailbox STRICTLY READ-ONLY:** the crossroads post shows pending items on click (view only); answering
   happens on existing external surfaces (HQ Chair). No embedded actuation anywhere in spec/mockups/roadmap.

## Evidence at ratification

- **Renders:** `unified-world.png` (1920×1280, 60×40 tiles @2×, neutral day) + `unified-close.png`
  (1584×1200, @3× crossroads crop) from the deterministic `compose_unified.py` (fnv1a-seeded, LimeZu sheets
  only, merging the proven world-reimagine d1+d2 recipes). Review gallery: `gallery-v2.html` (scratchpad,
  session-delivered).
- **Aesthetic gates (mechanical, thresholds untouched):** both renders `ok:true, 0 errors, 0 warnings` —
  palette foreign-mass 2.25% / 1.42% (fail >5%), flat_mass 0.229 / 0.283 (fail >0.379), dominant_share
  0.226 / 0.246 (fail >0.3166), busy_cv 0.95 / 1.11 (warn floor 0.41). Prior flags (palette_coherence,
  clustering) were fixed as composition defects — round-0's global dusk tint and uniform prop scatter were
  rebuilt, calibrations never edited.
- **Blind critic:** 7.5/10 after 2 rounds — good bones, honest composition; the dusk money shot is deferred
  until the grade passes palette at law alphas.
- **Feasibility (live estate):** classifier **FEASIBLE — CONFIRMED on 18,114 real events, 0.4% cargo
  ambiguity** (resolved by the Captain-ratified product-wins tie-break); interactive plumbing **FEASIBLE —
  all surfaces live, 2 nuances, 0 hard blockers**. Full run in Part II.

## Open calls awaiting Captain ruling (also in the gallery ask-section)

1. **P1 source of record** — dashboard decision-queue store or Chair binder queue for
   `pending_captain_items` (design assumes same surface; if not, pick ONE).
2. **Sensor-fog (P8)** — ratify weather's single honest binding (chronicle-staleness fog) or keep weather
   purely decorative forever.
3. **Retired-lane render** — reef-buoy at the stepnetwork anchor, or remove retired lanes entirely.
4. *(interpretation to confirm)* harbor library = "shipping record" reading of the Captain's "something third".

---

# PART I — THE SPEC (v1, verbatim)

# CABINET WORLD — THE UNIFIED ISLAND
## Harvestholm & Lantern Quay · one island, two districts · spec v1 (2026-07-08)

**Ratified frame (Captain, 2026-07-08):** ONE island, TWO districts. **Harvestholm** (village, inland-north) = cabinet self-work — memory / skills / retros / apoptosis / brain organs as buildings. **Lantern Quay** (harbor, south coast) = mission & product work — outcomes as cargo assembled on berths, shipped toward per-lane islands across the water when milestones hit. Charterhouse rejected (too guarded). This spec merges the d1 + d2 sections of `world-reimagine/directions.md` into one geography and grounds **every element in a data source that exists on disk today**, marking anything else `[NEW v1] / [v1.5] / [v2] / [v3]`.

**Inputs (all read today):** `world-reimagine/directions.md` (spine §0 + d1/d2, carried verbatim where unchanged) · `docs/plans/world-alive-direction-2026-07-08.md` + merged `cabinet/world/{morphology,show-grammar}.yml` v2 · `docs/plans/cabinet-world-build-kickoff-2026-07-07.md` (doctrine) · `cabinet/scripts/world-census.py` (E0a fields) · `cabinet/scripts/world-chronicle.py` (E0b verbs/attrs/presence) · `cabinet/dashboard/src/lib/world/{types.ts,director.ts,growth.ts}` + `/api/world/{stream,grammar}` · `instance/config/outcomes.yml` (10 outcomes: 6 active / 2 achieved / 1 retired / 1 draft; lanes polads · stephie · stepnetwork · system-self) · roster (4 officers: cos "Chair", polads-ceo, stephie-ceo, comms-officer) · `cabinet/scripts/world-aesthetic/` gate thresholds + calibrations.

---

## 0. LOCKED DOCTRINE (inherited, not re-litigated)

- **One continuous world.** Camera = pan + LOD zoom only (integer NN ×1/×2/×3). Never a scene swap. **≤2 render levels:** the outdoor island, plus ONE interior — the Great House wardroom revealed by roof-cutaway in place at ≥×3 (the shipped Wardroom scene becomes this cutaway; the separate `street`/`island` scenes of grammar v2 retire into the continuous world).
- **World render is READ-ONLY.** Interactions may only navigate / inspect / deep-link to EXISTING gated surfaces. The mailbox click *shows* pending items and embeds/links the existing card surface — never a new actuator. Library queries are GET-only against existing search. Renderer never writes (observer-class doctrine; CI ratchets stand).
- **Grammar as law:** every new pixel enters via `cabinet/world/{show-grammar,morphology}.yml` v3 PR; no auto-merge; binding-validator + asset-gate green; codex on every entry.
- **Determinism:** all variation `fnv1a(stableId[+salt])` + logical tick; wall clock enters only as `snapshot.clock` data. `world_at(T) = f_v(state_at(T))`.
- **Info-laws:** world IS the chart (numbers only in inspect cards); change is the signal; cause is witnessed; **one truth, one place** (single mailbox, single noticeboard). Rate-routing: >1 event/day sources drive TEXTURE only. Honest zeros render prominent. Reserved salience palette (green verified / amber blocked / red killswitch-only / grey unmeasured / purple captain-gated), dual-coded.
- **Glance budget (max 5 at far zoom):** ① crossroads mailbox flag · ② bodies + lit windows + chimney smoke · ③ cargo-fill gradient along the quay · ④ the dark lighthouse anomaly · ⑤ sky clock. Killswitch red-wash overrides everything.
- **Growth math:** `tier(S, base) = clamp(floor(log2(S/base+1)), 0, 7)` (`lib/world/growth.ts`, unit-pinned). Land radius `R = 24 + 6·floor(log10(org_events_total+1))` → **54 today** (155,784 events). Hysteresis: tier changes hold 2 daily keyframes; scaffold overlay until confirmed.
- **Runtime passes:** blob shadows + S/E wall darkening; day/night multiply tint (dawn `#ffd9a0`, dusk `#ff9e7a→#7a6a9e`, night `#25315e` @55–65%) + additive lamp pools `#ffcf8a` r≈3 tiles; y-sorted depth with LimeZu layer-1/2/3 slices. Runtime micro-accents only for signal states (4-px mailbox flag, red wash).

---

## 1. GEOGRAPHY — one island, one road, one honest sea

```
                         N  (all anchors compass-fixed; morphology law — never mirror/rotate)
  ~ ~ ~ T T T T T T T T T T T T T T T T T T T T T ~ ~ ~      T tree-wall (N/E/W rims; SEA is the
  ~ ~ T T . meadow . c c . c c . c c . c c . orch T ~ ~        one open edge — where value goes)
  ~ T T . law-plot .  G G G G G G  . observatory . T ~ ~     c officer cottages (×4, roof seeded)
  ~ T . library . . . G G G G G G . . workshop . . T ~       G GREAT HOUSE (HQ, roof-cutaway ≥×3)
  ~ T . . composter . plaza(well) . pens+barn . silo T ~     orch orchard (org age)
  ~ T . firepit . . . kitchen-garden(scarecrow) . . T ~      ← HARVESTHOLM, on the rise (+2 terraces)
  ~ ~ T . fields . . ledge==ramp==ledge . fields . T ~ ~
  ~ ~ T . . . . . . . . ║ . . hedgerows . meadow T ~ ~       ║ THE ROAD (~40 tiles, cobble t3)
  ~ ~ ~ . meadow . . . .║. . . . . . . . . . . ~ ~ ~
  ~ ~ ~ . . [CROSSROADS: mailbox + noticeboard + post-kiosk] ~    ← midpoint, tile ~20 of the road
  ~ ~ ~ . hedgerows . . ║ . . . flower verge . . ~ ~ ~
  ~ ~ . . warehouse . . ║ . . harbormaster hut . . ~ ~
  ~ = = = = = = = = QUAY (stone, E–W) = = = = = = = ~        ← LANTERN QUAY
  ~ ~ [sys berths]. pier║pier .[polads berths].[stephie b.] ~
  ~ ~ j packet-dock . . ~ ~ . c c cargo rows c c . . L ~     j packet-boat dock  L LIGHTHOUSE (DARK)
  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~        on the breakwater point SE
        ⛵→                          ⛵→
   [stephie isle SW]  open sea   [polads isle SE]   (+ a reef-buoy at the retired stepnetwork anchor)
```

**Why this shape (R12 — geography argues the metaphor):**
- **Village inland-north on a gentle rise** (two soft grass terraces + one ledge/ramp line — farm terrain banding, no cliff kit needed): the org's interior life sits above and behind, lamplit and sheltered by the tree-wall. Morning light (dawn tint) reaches the village fields first.
- **Harbor on the south coast**: the sea owns the south edge — the ONE unwalled side, because outward is where product value leaves. Dusk (the money hour) belongs to the quay: lamplighter, black water, cargo silhouettes.
- **ONE cobble road, ~40 tiles, village plaza → quay plaza** — *the commute stage*. Every dominant-focus switch is a witnessed 20–30 s walk down or up this road (§3). Road wear state (dirt→gravel→cobble→flagstone-center) binds `subagents_lifetime` tier (t3 today → cobble), same binding family as the existing plaza-path morphology entry.
- **Crossroads at the midpoint** (road tile ~20): the island's civic hinge — the ONE mailbox (Captain surface), the ONE noticeboard (chronicle surface), and the post-kiosk (honest-zero mail counter). News and approvals land where the two working lives meet; every courier walk and every commute passes it.
- **Offshore per-lane isles** SE/SW beyond the breakwater, sized by product maturity (§6). `system-self` deliberately has NO isle — self-work ships *inland*: its completed cargo is carted UP the road into the village (§5.6). The main island IS the system-self product.
- **Negative space:** 30–40% meadow/hedgerow/flower verge between districts (R4) — also load-bearing for the clustering gate's open-space ratio (§12).
- Production canvas: island fits radius R=54; mockups compress to a representative **60×48-tile** core (portrait-leaning to give the road its length).

---

## 2. DISTRICT ROSTERS

### 2.1 HARVESTHOLM (village = the cabinet working on itself)
Aesthetic: d1 pastoral (Modern Farm kit). Ground identity: yard tan-dirt, tilled soil, mulch, grass+flowers (R1 three-pass painting).

| Building | Organ | Binding (source, TODAY's value) | Render |
|---|---|---|---|
| **Great House** (HQ, on the knoll) | the org itself; wardroom | presence snapshot (SSE); chimney smoke = chronicle flowed last 10 min (`iidHigh` delta) | Largest farmhouse; roof-cutaway ≥×3 reveals the SHIPPED Wardroom interior (desks, table, kettle, bookshelf, noticeboard-pins, lamps — reuse as-is); posture pennant on the gable pole (1/2/3 tails = earn_up/guardian/sovereign, shape-coded not hue-coded; census `org_posture`) |
| **Memory Library** | vault/memory organ | `memory_rows_total` 1,170 → t3 (census, via falsifier block) | Long-windowed hall; shelf-fill bands 3/7 visible through glass; journal stacks = `tier2_note_files` 37 → t3. [v3] inspect panel runs GET-only library search (§11) |
| **Skill Workshop** | evolved skills | `evolved_skills` 9 → t3 (census file-count) | Workbench shed; ≤ tier·4 hung-tool pips (9 today); `skill.promoted` chronicle verb = door open + fresh shavings that day (texture) |
| **Retro Circle / Firepit** | self-improvement loops | `ev_self_improvement_loop_completed` (census lifetime → stone-ring tier); `loop.started/completed` chronicle verbs (today = fire LIT) | Log-seat ring + firepit between plaza and fields; fire burns only on a day a loop actually completed — honest cold ashes otherwise |
| **Apoptosis Composter** | sunset/retirement organ | `services_rows_disabled` (census, from services.yml `enabled: false`) + retired outcomes (`outcomes.yml status: retired` = 1) | Compost bays behind the barn; bay-fill = composted-things count; a tarped hand-cart parks here when an outcome is retired (§5.6). Honest small: codex "apoptosis is in REPORT_ONLY soak — nothing self-composts yet". [v2] per-kill events when apoptosis arms |
| **Brain Observatory** | fidelity/falsifier organ | `falsifier_series_lines` 569-class → tier (census); `fidelity.evaluated/scored` chronicle verbs; `cells_accumulating` (census) | Small dome on the east rise; dome slit OPEN + telescope tracking on days fidelity cases scored; pinned star-charts = cells_accumulating; codex cites the exact census keys |
| **Officer cottages** (×4) | roles | `ev_role_defined` 4 (census); roster slugs | One cottage per defined role, birth-order slots on the north lane; roof palette `fnv1a(slug,'roof')%3`; uniform size (per-officer census is dark — codex says so); night TTL-expired officers sleep here |
| **Pens + Barn + Silo** | services fleet | `services_rows_total` / `services_rows_disabled` (census) | d1 husbandry: each service = an animal out grazing; disabled = empty ghost-framed pen with cold lamp |
| **Outbuilding sequence** | repo output | `commits_total` 1,011 → t3 (census `git rev-list`) | t1 coop → t2 silo → t3 barn → t4 stable → …; scaffold overlay while hysteresis holds |
| **Kitchen garden + scarecrow** | eval health | `golden_evals_delta` −4 → t0 (census, seed 25) | Exactly one weathered scarecrow while delta ≤0 — honest; freshly patched hat on a pass day (chronicle `fidelity.scored`) |
| **Law plot** | captain law | `captain_rules` 38 → t3, `captain_vetoes_total` (census) | Small fenced plot NW: rule-posts upgrade wood→stone by tier; veto stones laid at the fence line; inspect cites counts |
| **Orchard + meadow** | org age | `org_events_total` → R, tree-ring/orchard thickness (felt, never read) | d1 verbatim |

### 2.2 LANTERN QUAY (harbor = the org shipping product)
Aesthetic: d2 trade-harbor (street-kit masonry + farm planks + modular brick). Quay stone = sidewalk tiles; pier planks south.

| Element | Meaning | Binding (source, TODAY) | Render |
|---|---|---|---|
| **Berths** (one per ACTIVE outcome — 6 today) | ratified missions | `instance/config/outcomes.yml` (`status: active`; count also cross-checked by census `outcomes_total`) | Chalk-framed berth rectangles on the quay, grouped by lane (system-self at the road mouth, polads E, stephie W). New ratification → berth chalked + mooring cleat overnight |
| **Cargo stacking = real progress** | per-outcome completion | **v1:** aggregate stage = `work_completed` tier (census, 6,708 → t3 → stage 3/7) with codex "aggregate until per-outcome stamps flow". **v1.5:** per-berth stage from chronicle `work.completed` records carrying `attrs.outcome` — the attr is ALREADY in the E0b allowlist (`ORG_EVENT_ATTRS` includes `lane`, `outcome` — `world-chronicle.py:123`); emitters just have to stamp it (§10) | 7-stage crate/barrel/sack stack recipe per berth (accumulation grammar, distinct from village growth); nearly-full = glance-readable ripeness gradient along the quay |
| **Berth work-tables** | mission work made visible | presence verbs + §3 focus classifier; officer→berth = `attrs.outcome`/`presence.object` when identifier-present, else the officer's lane anchor berth (`owner_role` from outcomes.yml; codex honest about the fallback) | Quay-classified officers work OUTDOORS at a crate-desk beside their berth (no second interior — ≤2 render levels holds); `deploying/shipping` = carry a crate pier-ward |
| **Harbormaster's hut** | coordination of shipping | roster: cos/"Chair" owns 10 system-self nodes; `coordinating` verb | Small hut with ledger-window at the road mouth; the Chair's quay station; ≥2 officers `coordinating` while quay-classified → they meet at the hut's bollard table (grammar group_scenes extension) |
| **Packet-boat dock** (W jetty) | incoming Captain approvals | `pending_captain_items` int on the SSE snapshot — **[NEW v1]**, the ONE sanctioned new feed (spine §0): E0b lifts a COUNT (int only, PII-free by schema) from the store backing the existing decision-queue/card surface | On count-increase: packet boat glides in → courier walks dock → road → crossroads → raises the mailbox flag (witnessed cause). On decrease: courier returns a stamped envelope to the dock. Boat idle-moored when 0 pending |
| **Warehouse** | shipped archive | `outcomes.yml status: achieved` (2 today) + `comms.digest` chronicle verbs + `packs_dirs` 5 → dock crates (census) | Shore-road warehouse; inspect lists achieved outcomes (name + achieved date from the yml comments/keyframe diff); the 5 inherited pack-crates stack outside (existing morphology entry carried over) |
| **THE LIGHTHOUSE** (breakwater point SE) | graduation | `cells_graduated` **0** (census) | NEVER lit until the first graduation; tallest silhouette, farthest from the warm lights; first graduation = first beam sweep, then steady (state, not fireworks). Inspect: *"No light has ever been earned. cells_graduated = 0."* Composed sprite (silo body + lamp head) — the one bespoke composite; interim silo stand-in already law (morphology v2 `island_harbor_beacon`) |
| **Pier** | reach | `commits_total` tier (shared with village outbuildings — pier length = 2+tier segments) | d2 verbatim; 5 segments today |
| **Ducks, tide, quay wear** | org age | `org_events_total` log10 (texture) | d2 verbatim: duck flotilla, foam line advances at dusk/recedes at dawn (logical clock), stone polish on walked spans |

### 2.3 THE CROSSROADS (midpoint civic cluster — one truth, one place)
| Element | Surface | Binding |
|---|---|---|
| **Mailbox** (THE Captain surface) | pending Captain decisions | `pending_captain_items` **[NEW v1]**: flag up (runtime 4-px accent) when >0; envelope pips ≤5 in the slot. **Click → read-only panel listing pending items, embedding/deep-linking the EXISTING gated card surface** (dashboard decision queue) — never a new actuator |
| **Noticeboard** | chronicle | SSE chronicle tail (200 records, PII-scrubbed at ingest): pin density `min(12, ceil(events_today/250))` (census `events_today`; TEXTURE class); salient kinds get witnessed courier pin-walks — v1 fixed salient set {`mission.created`, `trust.transition`, `skill.promoted`, `trust.unfrozen`}; [v2] salience config file |
| **Post-kiosk** | mail organ | `ev_mail_family` (census) — honest 0 until PO-1 emitters land: "counter closed" shutter down; codex names PO-1 |
| **Pippin** | charm | naps at the crossroads; trails any courier; points at the quay ducks (Dogs/Ducks sheets, seeded) — `decorative: true` |

---

## 3. THE COMMUTE — dominant-focus classifier + the walk

The signature mechanic: an officer's avatar LIVES in the district their actual work currently belongs to, and switching is a visible walk down the one road. All inputs exist today.

**3.1 Inputs (per officer, all from the SSE payload):**
- `presence.verb / object / since / hb_ttl_s` (Redis `cabinet:officer:activity:<slug>`, 5-min TTL, via E0b snapshot).
- Chronicle tail records for `actor == slug` (src `org_events` / `consequence` / `toollog`), each with `verb`, `kind`, and PII-safe `attrs` — **`attrs.lane` and `attrs.outcome` are already allowlisted fields** (`world-chronicle.py:123-125`).

**3.2 Classification (pure function, per record → vote):**
- **QUAY vote:** `attrs.lane ∈ {polads, stephie, stepnetwork, sensed, …}` (any lane with a `instance/config/projects/*.yml` entry — product lanes); or verb ∈ {`work.completed`, `work.assigned`, `task.created`, `task.completed`, `mission.created`} with lane ≠ system-self; or presence verb ∈ {deploying, shipping}.
- **VILLAGE vote:** `attrs.lane ∈ {system-self, captains-cabinet}`; or verb ∈ {`loop.started`, `loop.completed`, `skill.promoted`, `fidelity.evaluated`, `fidelity.scored`, `trust.transition`, `trust.unfrozen`, `policy.shadowed`, `world.grammar_gap`}. (Presence verbs are the hook-stamped desk vocabulary — working/editing/reviewing/deploying/coordinating etc. — and are district-neutral on their own; only `deploying`/`shipping` carry an intrinsic quay vote above. District leaning comes from the chronicle's lane/verb evidence, which is the honest signal.)
- Neutral (no vote): `session.*`, `comms.*`, `tool.call` without lane, unknown. **Exception:** `work.*`/`task.*` carrying `attrs.lane: system-self` votes VILLAGE (self-missions assemble on a quay berth but their *work* is village-classified only when it is loop/skill/fidelity-shaped; mission-node execution stays QUAY — the berth is where mission work happens regardless of lane; see 3.6).

**3.3 Dominant focus (window + hysteresis — no ping-pong):**
- Window **150 s** (Captain: 2–3 min), recency-weighted (`w = 0.5^(age/75s)`), evaluated every 15 s on the logical tick.
- Presence verb counts as one standing vote per evaluation (it is the freshest signal).
- **Switch rule:** target district ≠ current AND target share ≥ **0.6** of weighted votes AND that condition held for **2 consecutive evaluations** AND ≥ **180 s min-dwell** since last arrival. Otherwise stay.
- While walking: classifier suspended (no mid-road U-turns; re-evaluate on arrival). TTL-expired (no verb): stay where you are and run the district's idle program; night TTL-expired → walk to cottage, sleep.
- Deterministic: same chronicle + presence in → same walks out (fnv1a-free; it's pure aggregation).

**3.4 The walk (20–30 s, the point of the whole road):**
- Road ≈ 40 tiles; existing journey machinery at `TICKS_PER_TILE = 3` × 250 ms = 0.75 s/tile → full commute ≈ 30 s; from a mid-map station ≈ 20 s. No new engine work — retarget through road waypoints (village-plaza → ledge-ramp → crossroads → quay-plaza).
- **Thought-bubble:** DOM chip (text-as-DOM law) above the walker: **"I should 〈verb-gloss〉 · 〈lane〉"** from a CLOSED verb→phrase table (e.g. `reviewing→"review the queue"`, `deploying→"ship this"`, `coordinating→"sync the crew"`, `loop.completed→"write up the retro"`, `work.assigned→"pick up the task"`), lane suffix only when `attrs.lane` present. Closed table + identifier-safe lane slug = deterministic, zero free text, zero PII. The gloss is the REAL verb that flipped the classifier — never invented.
- Officers passing at the crossroads face each other for 4 ticks (seeded, from relative x) — small life, no claim.
- Couriers share the road: mail walks (packet dock↔mailbox) and salient-pin walks (§2.3) — cause witnessed on the same stage.

**3.5 Work staging per district:**
- **Village-classified:** desk verbs at the Great-House cutaway desks (existing Wardroom director law verbatim — micro-loops, kettle, bookshelf, group table). Retro flavor: ≥2 village-classified officers `coordinating` → firepit ring seats instead of the indoor table (day only; grammar addition).
- **Quay-classified:** verbs map to quay stations — desk-verbs → berth work-table (their outcome's berth, fallback lane anchor); `reviewing` → harbormaster ledger-window; `deploying/shipping` → carry crate to pier/boat; `coordinating` ≥2 → hut bollard table.

**3.6 Honesty codex (inspect on any walking officer):** "District = dominant class of this officer's last 150 s of chronicled verbs (window/thresholds cited); the walk is a re-classification, not a claim the officer 'went somewhere'."

---

## 4. ORG-STATE MAPPING — the full glance table

| Org fact | World element | Glance / linger / inspect | Feed status |
|---|---|---|---|
| Officer presence + verb | avatars at village desks / quay berths / on the road; verbs per §3.5 | Glance: bodies; linger: walks | **EXISTS** (SSE presence) |
| Dominant focus switch | the 20–30 s commute walk + thought bubble | Linger (the show) | **EXISTS** (derived §3; no new plumbing) |
| Pending Captain decisions | crossroads mailbox flag + envelope pips; packet-boat arrival + courier walk | Glance ① | **[NEW v1]** `pending_captain_items` int on snapshot |
| Active outcomes (6) | quay berths, lane-grouped | Glance ③ count | **EXISTS** (`outcomes.yml`) |
| Outcome progress | 7-stage cargo stack per berth | Glance ③ gradient | v1 aggregate (**EXISTS**: census `work_completed` tier) → **[v1.5]** per-berth via `attrs.outcome` stamps |
| Outcome achieved | ceremony: boat ships the stack to the lane's isle (or hand-cart up the road for system-self); warehouse ledger row appears | Return-visit delta + linger ceremony | **EXISTS** (status flip between keyframes / yml re-read; deterministic on the delta) |
| Outcome retired | stack tarped grey overnight → cart to the composter next keyframe | Linger | **EXISTS** (`outcomes.yml`) |
| cells_graduated = 0 | **the dark lighthouse** | Glance ④ anomaly | **EXISTS** (census) |
| Memory (t3) | library shelf bands + cutaway bookshelf (`tier2_note_files` journals) | Mid-zoom | **EXISTS** (census) |
| Evolved skills (t3, 9) | workshop hung-tool pips | Mid-zoom | **EXISTS** (census) |
| Self-improvement loops | firepit lit today / stone-ring tier lifetime | Mid-zoom + felt | **EXISTS** (census `ev_self_improvement_loop_completed` + chronicle `loop.*`) |
| Apoptosis / retirements | composter bays + tarped cart | Inspect-tier | **EXISTS** (services disabled + outcomes retired); [v2] per-kill events when armed |
| Fidelity / falsifier | observatory dome slit + star-charts (`cells_accumulating`) | Mid-zoom | **EXISTS** (census + chronicle `fidelity.*`) |
| Services health | pens: animals out = running; ghost pen = disabled | Glance-ish ("the chickens are out") | **EXISTS** (census services rows) |
| Commits (t3) | village outbuilding sequence + pier length | Return-visit delta | **EXISTS** (census) |
| Captain law | law-plot posts (rules t3) + veto stones | Inspect | **EXISTS** (census) |
| Eval health | scarecrow state | Inspect + charm | **EXISTS** (census `golden_evals_delta`) |
| Chronicle volume | noticeboard pin density (`events_today`); chimney smoke (10-min flow) | Linger texture | **EXISTS** (census + `iidHigh`) |
| Salient events | courier pin-walks on the road | Linger (cause witnessed) | v1 fixed set (**EXISTS**); [v2] salience config |
| Mail organ | post-kiosk shutter (honest 0) | Inspect | **EXISTS** (census `ev_mail_family` = 0 until PO-1) |
| Org posture | Great-House pennant tails (shape-coded) | Inspect | **EXISTS** (census enum) |
| Org age / scale | R=54 land, road wear, orchard ring, duck flotilla, quay polish | Felt, never read | **EXISTS** (census totals; texture class) |
| Logical clock | sky tint + lamp pools + lamplighter + tide line | Glance ⑤ | **EXISTS** (snapshot `clock`) |
| Killswitch | freeze mid-stride + red wash + lamps die + animals stop | Glance override | **EXISTS** (snapshot flag) |
| Per-lane product maturity | offshore isle size/detail | Glance (silhouette) → [v2] explorable | v1 proxy **EXISTS** (per-lane outcomes); [v2] per-lane census block |
| Grammar coverage | HUD legend gauge (chrome, not world-space) | HUD | **EXISTS** (`codexCoverage`) |

---

## 5. CEREMONIES (all deterministic on state deltas — no invented drama)

1. **Ratification:** new `status: active` outcome → overnight a berth is chalked + cleat set (next keyframe).
2. **Progress:** cargo stage-up renders the added crates with a brief stack-settle bob (grammar anim), only on a real stage delta.
3. **Shipment (achieved, product lane):** stack transfers to the moored boat over one linger scene → boat sails toward the lane's isle → isle gains its building next keyframe → warehouse ledger row. All from the status flip; era-pinned replayable.
4. **Shipment (achieved, system-self):** hand-cart loaded at the berth, walked UP the road through the crossroads into the village — self-work ships inward. Village building/tier affected is whatever the outcome's census surface moves.
5. **Retirement:** tarp overnight → cart to composter → berth cleared next keyframe.
6. **First graduation (someday):** the lighthouse lights — one beam sweep night, steady thereafter. The biggest visual event in the world's life (already law in morphology v2 codex).
7. **Approvals:** packet boat + courier + flag (§2.2); flag drop when the count returns to 0.

---

## 6. OFFSHORE LANE ISLES — product mini-districts across the water

- **Anchors fixed at birth** (compass ring order, locked in morphology): polads SE, stephie SW; retired stepnetwork = a reef-buoy at its reserved anchor (honest: "lane dormant by Captain ruling"); future lanes take the next ring slot. `system-self` = the main island (codex states it).
- **v1 (silhouettes, EXISTS):** isle land size = `tier(lane_outcomes_lifetime, base=1)` and building count = achieved outcomes per lane — both parsed from `outcomes.yml` (lane encoded in outcome id). Rendered as real terrain + 1–3 cottages/warehouse silhouettes + a jetty; NOT explorable yet; inspect card cites the counts. Glance read: "polads isle is bigger — more has shipped there."
- **[v2] (product maturity, real):** census gains a per-lane block via the SAME fenced-local-read discipline: `git -C <checkout> rev-list --count HEAD` per `instance/config/projects/<lane>.yml` path (fixed argv), per-lane brain/product-corpus row counts via the falsifier/memory block if per-scope counts are exposed, per-lane `ev_*` splits GROUP'd by `attrs.lane`. Isle then grows like the main island: buildings by commit tier, lit windows by lane deploy activity. Isles become **explorable** (pan across water at ×2/×3 — still one continuous world) as wiki-style mini-districts: lots = work-graph nodes (task viz), colors by node state from work-graph events; Obsidian-graph-feel link lines rendered as footpaths between related lots.
- **[v3]:** isle library annex — inspect panel issues GET-only queries to the existing product search (dashboard `/api/library` + brain codebase pillar), rendering results in the card (never in world space).

---

## 7. DAY/NIGHT + WEATHER HOOKS

**Clock (EXISTS — `snapshot.clock`, server-stamped, Captain-timezone):** buckets dawn 06–08 / day 08–18 / dusk 18–21 / night 21–06 (grammar v2 `night` block verbatim).
- **Dawn:** gold tint hits the village first (east rise); sprinklers arc ONLY over field plots/berths that advanced since yesterday's keyframe (growth witnessed); tide recedes one tile.
- **Day:** neutral; work legible; commutes at full contrast.
- **Dusk (money hour):** ramp tint; **the Lamplighter** — least-recently-active officer (deterministic from presence `since`) walks the quay igniting lamps in sequence; tide advances one tile; village windows warm.
- **Night:** `#25315e` @55–65% + lamp pools; cottage windows glow for sleeping officers; desk lamps pool over late workers; the lighthouse stays DARK (never give the zero a night light).
- Sky/tint drives ambience only — never state, never morphology (law).

**Weather (UNBOUND cosmetic — spine ruling carried):** one weather state per logical day, seeded `fnv1a('wx:'+date) % {clear:5, breeze:3, drizzle:2, fog:1}` weights; drives leaf-fall density, foam richness, drizzle streak overlay, fog alpha band at the shoreline. `decorative: true`, codex says "weather is seeded flavor, bound to nothing". Killswitch is NEVER weather-coded (red wash only; dual-coding law).
- **[v3] one honest binding candidate (proposal, not law):** *sensor fog* — if the world-chronicle heartbeat is stale (>2 days, the doctor's DEAD threshold), fog rolls in and stays: replay fog made literal. Needs Captain ratification since it promotes weather from decor to signal.

---

## 8. GROWTH STORY (return-visit deltas)

- **Day-0 (any fresh deployment):** 24-radius islet; Great House + well + board + mailbox + bare quay with zero berths; no cottages ("an egg has no streets"); dark lighthouse already standing — ambition visible from birth.
- **Today (this deployment):** R=54; village at t3 (coop+silo+barn built, library 3/7, workshop 9 tools, ring-of-stones firepit, 4 cottages); road cobbled; 6 berths at stage-3 aggregate cargo; 2 warehouse ledger rows; 5 dock crates; polads/stephie isles as small silhouettes; reef-buoy at stepnetwork anchor; lighthouse dark.
- **Next deltas the Captain will actually see:** commits t4 → stable scaffolding (2-keyframe hysteresis) then built + pier segment 6 staked→planked; each new ratified outcome → berth chalked overnight; first per-outcome stamps [v1.5] → the cargo gradient becomes REAL per-mission truth; first achieved-outcome boat sail → isle building #next; memory t4 → new shelf band; first armed apoptosis kill → the composter's first real mound; `cells_graduated` 0→1 → the light.
- Village gains a NEW building only when a new ORGAN ships in the org (building set is closed in morphology; adding one = grammar PR — the org literally cannot grow a building it didn't earn).
- Land/orchard/ducks/wear creep with log10(events) — felt, never read.

---

## 9. ZOOM STORY + INTERACTION LAW (read-only, LOD only)

- **FAR ×1:** whole island: warm village on the rise N, lamplit quay S, the road a pale thread between; the 5 glance signals only. Stranger's read: *"a farm that thinks and a harbor that ships — and a lighthouse that has never been lit."*
- **MID ×2:** district identities; berth stacks individually; commuters with bubbles; couriers; animals; isles resolve silhouettes.
- **CLOSE ×3:** verbs legible; crop/crate species; Pippin; inspect everywhere; over the Great House → roof-cutaway (the shipped Wardroom, verbatim).
- **Interaction law (LOCKED):** primary click = navigate only (pan/zoom-to; isle click pans across water). Secondary click = universal WHAT/NOW/PROOF inspect card citing the exact census/chronicle field (existing three-tab card). Mailbox card lists pending items + embeds/links the EXISTING card surface. Library/isle-library cards [v3] run existing GET-only search. NO world interaction mutates anything, ever — no approve buttons, no task edits, no new actuators. `sel` stays opaque; no slugs/pids in URLs; all text is DOM.

---

## 10. FEEDS & PLUMBING LEDGER (exhaustive)

**Runs today with ZERO new plumbing:** SSE presence + verbs + killswitch + clock; chronicle tail (verbs, `attrs.lane` where already stamped); census keyframes (all §2/§4 tiers); `outcomes.yml` berth/isle/warehouse reads; grammar status. The commute classifier, both districts, ceremonies 1/2/5, day/night, weather, and v1 isles need only these.

| # | Plumbing item | Size | Stage |
|---|---|---|---|
| P1 | `pending_captain_items: int` on the SSE snapshot (E0b lifts a count from the store backing the existing decision-queue card surface; int-only, PII-free by schema) | ~½ d | **v1** (the only new feed v1 needs) |
| P2 | Emitters stamp `outcome:`/`lane:` into org_events payloads for `work_item_*` (+ consequence rows) — chronicle allowlist ALREADY lifts them (`world-chronicle.py:123`); zero chronicle-schema change | small, per-emitter germline window | **v1.5** → true per-berth cargo |
| P3 | Per-lane census block (per-repo `git rev-list` via `projects/*.yml` paths; per-lane `ev_*` GROUP BY `attrs.lane`; per-scope memory counts if exposed) — same fenced-local-read discipline as E0a | ~1 d + validator | **v2** → isle maturity + explorable districts |
| P4 | Chronicle salience config (which kinds pin the board / trigger courier walks) | tiny | **v2** (v1 uses the fixed 4-kind set) |
| P5 | Work-graph node-state read for isle task-viz lots (from work-graph events; projections are 0-row — read events, never projections) | ~1–2 d | **v2** |
| P6 | GET-only library/product search pass-through into inspect cards (existing `/api/library` + brain codebase pillar; authed, read-only) | ~1 d | **v3** |
| P7 | Apoptosis per-kill events (when REPORT_ONLY arms) → composter ceremonies | rides that project | **v2/v3** |
| P8 | *Sensor-fog* binding (weather → chronicle staleness) | tiny | **v3, needs Captain ratification** |

---

## 11. STAGED DELIVERY (Captain-ratified staging)

- **V1 — island + commute + mailbox-view:** unified continuous island replaces the v2 `street`/`island` scene-swaps (wardroom survives as the cutaway); both district rosters on EXISTS feeds; commute classifier + walk + bubbles; crossroads mailbox with P1 + click-through panel; berths with aggregate cargo (honest codex); ceremonies 1/2/5/7; day/night + seeded weather; isles as sized silhouettes; dark lighthouse. Grammar v3 PR carries every entry (Captain merge = the door).
- **V2 — product districts + task viz:** P2 per-berth truth + shipment ceremonies 3/4; P3 isle maturity; isles explorable as wiki mini-districts with work-graph task lots (P5); salience config (P4).
- **V3 — library-query:** P6 real queries from the Memory Library + isle annexes; Obsidian-graph link-path explore; P7/P8 as they ratify.

---

## 12. AESTHETIC-GATE COMPLIANCE (mechanical gates MUST pass — fix composition, never thresholds)

Prior mockups flagged `palette_coherence` + `clustering`. Root causes and the composition rules that fix them (thresholds from committed calibrations, `cabinet/scripts/world-aesthetic/calibration/*.json`):

**Palette (`PALETTE_FOREIGN_MASS`, fail >5% foreign vs 516 calibrated 5-bit bins, neighbor_radius 1):**
- The prime suspect is the full-frame dusk gradient lerp (`#ff9e7a→#7a6a9e`) + wide additive glows pushing large pixel mass off the LimeZu-native bins. Rules: (a) native sheet colors dominate every frame — grades are multiply-only at the documented law alphas (≤0.22 night; dawn 0.06; dusk 0.10 per grammar v2), never a hue-replacing lerp across the whole frame; (b) additive lamp pools stay small-radius (r≈3 tiles, alpha 0.15) and few; (c) sky-color washes confined to edge vignette bands, not midfield; (d) HUD/label rects declared via `--ui-rects` (sanctioned chrome), never used to hide world pixels. Run the gate at BOTH the neutral-day and dusk renders; if dusk trips, cut grade coverage/alpha — composition iteration, not calibration edits.

**Clustering (map: fail R>0.5376 or open_ratio<0.5943 · image: fail flat_mass>0.379 or dominant_share>0.3166; busy_cv warn <0.4101):**
- **Designed clumping (map R ≤ ~0.45):** props always in purposeful clusters — crate stacks TOUCHING at berths, barrels against walls, benches at tables, tools at the workbench, pens fenced tight. No uniform sprinkling of scatter-decor; flower/tuft variation is TERRAIN texture (flat layer), not prop entities.
- **Real clearings (open_ratio ≥ ~0.6):** the meadow belt, road corridor, quad/plaza voids, and open water keep ≥60% of cells >4 tiles from any prop — the §1 negative-space law is load-bearing here, keep it.
- **No flat voids (flat_mass, dominant_share):** R1 three-pass ground painting EVERYWHERE (base variation ×3-4 tiles, mid patches, micro-texture); the SEA is the biggest dominant-color risk in a harbor frame — cap open water at ≲30% of any world-shot frame, texture it (wave variation tiles, foam shore rows, dusk reflection shimmer lines, duck flotilla) so no single RGB exceeds ~31% and 8-px blocks aren't channel-flat.
- Emit `world.map.json` + `labels.json` from the compositor and run BOTH sides: `python3.12 cabinet/scripts/world-aesthetic/world-aesthetic-gate.py --mechanical --map … --render … --labels …` (labels chrome-flagged; obey label budget per zoom). A frame that fails is rejected before the Captain ever sees it; `--full` judge run for the final candidate.

---

## 13. ASSET + MOCKUP PLAN (reuse, don't rebuild)

- **Sheets:** exactly the d1 + d2 verified tables (directions.md) — farm terrains/props/crops/trees/animals for Harvestholm; street sidewalk/modular/lamps/boat + plank/pier + composed lighthouse for Lantern Quay; `Room_Builder`/office/Conference for the cutaway; `Premade_Character_01..20`; mailbox singles at the crossroads. No Serene Village (dialect law), no 48px MV sheets.
- **Compositor:** `compose_unified.py` in this dir, built by MERGING `world-reimagine/compose_d1.py` (village terrain/buildings/crops/animals recipes) + `compose_d2.py` (quay stone, modular stacks, boats, lamps, lighthouse composite, dusk passes) — both already deterministic (fnv1a LCG, no random/time) and pointing at the live asset root; reuse their extracted-tile knowledge (`p4_*/p5_*/v-*/c-*/recon_*` probes) rather than re-scanning sheets.
- **Renders:**
  1. `unified-world.png` — 1920×1536 @2x (60×48 tiles), **dusk 19:30**: village warm on the rise, lamplighter mid-quay, cargo gradient, mailbox flag UP at the crossroads with ONE officer mid-commute + thought bubble, packet boat inbound, dark lighthouse, both isles on the horizon water. The money shot IS the thesis: two working lives, one road.
  2. `unified-close-crossroads.png` — 1600×1200 @6x, **dawn**: mailbox + noticeboard + shuttered post-kiosk, courier arriving from the pier, commuter passing toward the quay, Pippin asleep.
  3. `unified-close-quay.png` — 1600×1200 @6x, **night**: berth stacks under lamp pools, harbormaster window lit, lighthouse dark against the water.
- Every render ships with `world.map.json` + `labels.json` + a green `--mechanical` gate log BEFORE Captain review (integration contract, world-aesthetic README).

---

## 14. OPEN QUESTIONS (Captain, only these)

1. **P1 source of record:** which store should E0b count for `pending_captain_items` — the dashboard decision-queue backing store, or the Chair's binder queue? (Design assumes they are the same surface; if not, pick ONE — one truth, one place.)
2. **Sensor-fog (P8):** ratify weather's single honest binding, or keep weather purely decorative forever?
3. **Retired-lane render:** reef-buoy at the stepnetwork anchor acceptable, or remove retired lanes from the map entirely?

---
## CAPTAIN RULING ADDENDUM (2026-07-08, post-design — BINDING for compose + deliver)
FOUR-LIBRARY TAXONOMY (distinct knowledge places, each backed by its real corpus, never blended):
1. Home-house library (village): agent memory / learnings / skills — backed by cabinet memory + skill store.
2. Product-island library (per offshore island): THAT product's brain/corpus only.
3. Harbor library: the SHIPPING RECORD — outcomes, missions, work-graph history, chronicle archive (proposed interpretation of Captain's "something third"; flag as open-call in gallery).
4. CHARTER HALL / Manor (village hill, distinct building): the Captain's decisions / intentions / directions / standing grants — backed by captain-decisions.md + rulings. Officers visibly walk here to consult.
MAILBOX: STRICTLY READ-ONLY ruled — crossroads post shows pending items on click (view only); answering happens on existing external surfaces; no embedded actuation, remove any "maybe answer" affordance from spec/mockups/roadmap.

---

# PART II — FEASIBILITY VERIFICATION (verbatim)

# Unified World — Feasibility Verification (live estate, read-only)

Date: 2026-07-08. Verifier ran against the LIVE estate: 18,114 real chronicle
events (2026-07-07 + 07-08), live Redis, live dashboard :3100, live brain/memory
search. Repro: `python3.12 classify_test.py` (this dir).

## Verdict summary

| Mechanism | Verdict |
|---|---|
| (1) verb→district classifier | **FEASIBLE — CONFIRMED on 18,114 real events; 0.4% cargo ambiguity** |
| (2) interactive layer plumbing | **FEASIBLE — all surfaces exist and are live; 2 nuances, 0 hard blockers** |

---

## (1) Verb→district classifier

### The classification rule (as tested)

Classify by **BENEFICIARY** — where does the artifact land? Priority order:

1. **`attrs.lane`** (consequence/undo/org events, when present):
   `system-self` → Harvestholm; `polads|stephie|personal|adhoc|comms` → Lantern Quay.
2. **Verb family**: `loop.*`, `trust.*`, `skill.promoted`, `fidelity.*`,
   `role.*`, `world.grammar_gap`, `gap.family` → Harvestholm (cabinet organs).
   `mission.created`, `work.*` → Lantern Quay.
3. **Lifecycle verbs** (`session.*`, `comms.notified`, `policy.shadowed`,
   `org.other`, `crew.completed`) → **ambient** (presence layer: officer
   motion/heartbeat, never district cargo).
4. **Toollog beneficiary resolution** (`tool.call`, 5,292 of the sample):
   resolve `ref` byte-offset into `memory/logs/YYYY-MM-DD.jsonl`, extract
   `file_path` args + paths in `command`, **excluding leading `cd <dir>`
   boilerplate** (officer prompts open every Bash with `cd <repo>`; cwd votes
   only when nothing else does). Path prefix map:
   - Cabinet estate → Harvestholm: `~/captains-cabinet`,
     `/opt/founders-cabinet`, `~/Library/Application Support/cabinet`,
     `~/.cabinet`, cabinet-scoped scratchpads.
   - Product/Nate estate → Lantern Quay: `~/v0-politiske-annoncer`
     (polads), `jobdanmark-v2`, `dev-tasks`, `~/obsidian/screenpipe-brain` +
     `~/.screenpipe` (Nate's brain = mission side — the cabinet serving Nate).
   - No path at all (redis-cli probes, `date`, `gh` reads) → **ambient**
     ("probe-no-artifact": motion, not cargo — this is the raw commute signal).
5. **`claude_task.*`**: chronicle is thin, but the org_events payload carries
   `cwd` — resolved read-only (`file:...?mode=ro`) → beneficiary path.
6. **Actor fallback**: `polads-ceo|stephie-ceo` → Quay;
   `self_improvement_loop|graduation-sweep|apoptosis-sweep|memory-worker` → Harvestholm.

**Tie-break (Captain-ratified beneficiary rule):** on a genuine path-vote tie
(cabinet + product artifacts in one command), **product estate wins** — mission
work routinely touches cabinet ledgers/scratch as bookkeeping; the reverse
(cabinet self-work producing product artifacts) does not happen. This resolves
all 10 remaining ambiguous events (0.4%).

### Measured split (18,114 events, 2 live days)

```
all events:   ambient 85.2% | harvestholm 10.9% | lantern-quay 3.8% | ambiguous 0.1%
cargo only:   harvestholm 74.1% (1,981) | lantern-quay 25.5% (682) | ambiguous 0.4% (10)
```

Reason breakdown: beneficiary-path 2,452 (91.7% of resolved cargo), lane 72,
verb-family 16, org-event-cwd 10, tool-kind 76 (mcp__brain/SendMessage → Quay),
consequence-default 41, actor 154.

Spot-check (manual, samples verified correct): Quay hits are vault/screenpipe/
polads-repo writes by comms-officer/cos; Harvestholm hits are cabinet-repo
edits — including by polads-ceo (beneficiary correctly beats actor: yesterday's
polads-ceo work WAS cabinet self-build).

### Ambiguous cases (before tie-break, all 10)

- 5× `cos` Bash touching `v0-politiske-annoncer` + scratchpad, or
  `~/.screenpipe` + cabinet repo in one command → product-wins tie-break: Quay.
- 5× `polads-ceo` Bash with tied cwd-only votes → product-wins: Quay.

### Commute signal — verified real

Per-officer dominant-district windows over live 07-08 data (30-min buckets,
cargo events only): comms-officer 22 active windows / 2 commutes,
cos 22 / 2, polads-ceo 21 / 2, stephie-ceo 7 / 0, cto 4 / 0. The signal is
clean, not thrashing — a visible 20–30s walk per district switch is viable.
At the spec'd 2–3-min dominance window, add hysteresis (switch only after N
consecutive minutes of new-district majority) to avoid walk-thrash;
presentation-layer only, no data gap.

### Load-bearing integration point (the one that matters)

**Classification MUST run at ingest, inside `cabinet/scripts/world-chronicle.py`**,
where the raw payload is in hand (toollog paths, org_events cwd, consequence
lane). The published chronicle is PII-scrubbed thin — beneficiary paths are
structurally absent downstream. Change (Deliver phase, repo write):

- In each `normalize_*()`, compute `district ∈ {harvestholm, lantern-quay, ambient}`
  from the raw row and emit it as one more allowlisted attr. The value is a
  closed enum → passes the identifier guard; it is a pure function of the
  source row → **preserves the E0 determinism gate** (re-chronicling yields
  byte-identical records). Raw paths/free text still never leave ingest.
- Renderer + census consume `attrs.district`; no renderer-side DB/toollog access
  (keeps the render path cred-free, matching /api/world/grammar doctrine).

Honest caveats:
- The 2-day corpus is cabinet-sprint-biased (74/26). During product sprints the
  ratio will invert; the harbor will honestly look quiet during village sprints.
- `attrs.lane` exists on only 72/18k events today — never rely on lane alone.
- `actor=unknown` on consequence/toollog rows (584 events) — beneficiary/lane
  still classifies them; only avatar attribution suffers, not district.

---

## (2) Interactive layer plumbing

### Dashboard — live, embed-ready

Next.js on **:3100** (services.yml row `dashboard`, keepalive, verified
`GET /api/health` live; auth-gated → `/login`; `/display` is read-only
unauthenticated by design). **A `/world` page already exists** (E1 Wardroom)
with exactly the right chassis:

- `GET /api/world/stream` — SSE: `cabinet:world:presence` snapshot + chronicle
  tail (200) via Redis Pub/Sub on `cabinet:world:updated`, 15s keepalive,
  polling fallback. **GET-only by doctrine, CI-ratchet pinned** ("the world
  never grows a write path"). Officer slugs → opaque `sel` handles
  (sha256-derived) — URL-deep-link discipline already established; district
  camera deep-links should reuse it.
- `GET /api/world/grammar` — grammar law + legend + census keyframes from
  `shared/interfaces/world-chronicle.jsonl` (2 keyframe rows live).
- Live Redis spine confirmed: `cabinet:world:presence` (4 officers present,
  hb TTLs), `cabinet:world:chronicle` stream + heartbeat key.

### Mailbox → pending cards (v1)

- **Pending cards live in Redis**: `cabinet:action:<pid>` where
  `pid = <officer>|action-card|<slug>|<ts>` (10+ live keys observed). Value =
  card JSON: `cid`, `lane`, `subject`, `situation`, `steps[]`. Producer:
  `framework/acting/run_action_lane.py`; undo pointers under `cabinet:undo:<pid>`.
- **Approval surface** = Telegram HQ Chair reply grammar
  (`framework/frontdoor/binder_wire.py`: pid markers in the presented message;
  approve/edit/skip/veto verbs; approve executes via
  `framework/frontdoor/action_exec.py`). Nothing else approves.
- **Integration**: extend the **existing** `GET /api/world/stream` snapshot
  with pending-card summaries (read-only Redis SCAN `cabinet:action:*` + GET) —
  no new route, no new actuator, no write path; mailbox click renders card
  content in-world and **links out to the HQ Chair Telegram chat to act**.
- **Nuance (not a blocker):** Telegram has **no per-message deep link into a
  bot DM** — `t.me/<ExampleChairBot>` opens the chat, not the specific card message.
  Mitigation: the card body is fully rendered in-world from Redis; Telegram is
  only the act surface. (Card JSON free text stays in the authed dashboard
  response — same trust tier as `/tasks` — and must NEVER be copied into the
  chronicle forever-file.)

### Library / brain / product queries (v3, GET-only)

All entrypoints exist and were probed live:

| Surface | Entrypoint | Verified |
|---|---|---|
| Cabinet Library | `POST /api/library/search` → `searchRecords` (SELECT-only); deep links `/library/[spaceId]/[recordId]`, `/library/graph`; MCP twin `cabinet/channels/library-mcp` (`library_search`, `library_get_record`) | route read, handler is read-only search |
| Cabinet memory | `cabinet/scripts/search-memory.sh "<q>" [--as-of TS]` → psql SELECT on Neon, blended vec+lex+recency, content-time fence | **live probe returned hits** (note: default `--min-score 0.45` is strict; embedding may degrade to lexical when Voyage is keyless — still functional) |
| Nate brain | `python3.12 ~/.screenpipe/pipes/embeddings/search.py "<q>" --json` (hybrid, 0-Self excluded); richer MCP: `~/.screenpipe/pipes/brain-mcp/server.py` (`search_brain`, `gather_context`, `read_note` with 0-Self privacy fence) | **live probe returned JSON hits** |
| Product brain | repo `product-brain/` (architecture.md; decisions/ + incidents/ currently sparse) + vault `9-Codebases/{PolAds,STEPhie,stepnetwork-dk,Toolbox,...}` via `search.py --filter 9-Codebases/` | dirs confirmed; PolAds pillar populated |

Nuance: `/api/library/search` is **POST** (query in body) though semantically
read-only. Calling the existing POST route from the world UI is "navigate to an
existing gated surface" and fine; the world's OWN routes stay GET-only per the
ratchet. Do not add write verbs to any world route.

### Aesthetic gate (build-phase constraint, recorded)

`cabinet/scripts/world-aesthetic/gates/`: hard-error checks are
`PALETTE_FOREIGN_MASS` (palette_coherence — declare the palette from the actual
LimeZu sheets used, don't mix foreign-toned tiles) and `CLUSTER_SCATTER` /
`CLUSTER_NO_CLEARING` / `CLUSTER_FLAT_VOID` (clustering — props must clump with
deliberate clearings; no uniform scatter, no flat empty bands). Prior mockup
failures are composition defects: fix by clustering props and unifying tile
sources in `compose_d1.py`/`compose_d2.py` (world-reimagine dir), not by
touching thresholds.

---

## Blockers

**None hard.** Ranked flags:

1. **Ingest change required** — district classification only works inside
   `world-chronicle.py` (raw payload); downstream-only classification loses
   91.7% of the signal. Additive, determinism-safe, but it is a germline-adjacent
   repo write → Deliver phase with tests mirroring `test_world_chronicle.py`.
2. **No Telegram per-message deep link** for bot-DM cards — chat-level link
   only; card content must render in-world (it can, from Redis).
3. **Corpus skew** — 74/26 village/harbor split reflects the current cabinet
   sprint; expect inversion during product sprints. Not a defect, but set
   Captain expectations: the harbor earns its cargo.

---

# PART III — MOCKUP + GATE EVIDENCE (2026-07-08)

**Renders (deterministic compositor `compose_unified.py`, fnv1a-seeded LCG — no `random`/wall-clock; LimeZu
sheets only, merging the proven `world-reimagine/compose_d1.py` (Harvestholm) + `compose_d2.py` (Lantern Quay)
recipes):** `unified-world.png` 1920×1280 (60×40 tiles @2×, neutral day) · `unified-close.png` 1584×1200
(@3× crossroads crop). Renders + compositor + gate JSONs live in the session scratchpad `world-unified/`;
review gallery `gallery-v2.html` delivered to the Captain the same session.

**Mechanical aesthetic gate** (`cabinet/scripts/world-aesthetic/world-aesthetic-gate.py --mechanical`,
committed calibrations, thresholds untouched — findings JSON `gate-world.json` / `gate-close.json`):

| Render | Result | palette foreign-mass | flat_mass | dominant_share | busy_cv |
|---|---|---|---|---|---|
| `unified-world.png` | **ok:true** · 0 err / 0 warn | 2.25% (fail >5%) | 0.229 (fail >0.379) | 0.226 (fail >0.3166) | 0.95 (warn <0.41) |
| `unified-close.png` | **ok:true** · 0 err / 0 warn | 1.42% (fail >5%) | 0.283 (fail >0.379) | 0.246 (fail >0.3166) | 1.11 (warn <0.41) |

Map-side gates (edge_continuity / connectivity / scale_lint / label_overlap) ran as skipped on the mockups
(no `--map`/`--labels` emitted by the mockup compositor); the v1 build compositor MUST emit
`world.map.json` + `labels.json` and run BOTH sides green before any Captain review (spec §12 contract).

**How the prior flags were fixed (composition, not thresholds):** round-0 tripped `palette_coherence`
(full-frame dusk hue-lerp pushing pixel mass off the LimeZu bins) and `clustering` (uniform prop scatter +
channel-flat sea). Fixes: neutral-day base grade with multiply-only law alphas; purposeful prop clusters +
real clearings (§1 negative-space law); three-pass ground painting everywhere; open water capped ≲30% and
textured (waves/foam/ducks). Calibration files were never edited.

**Blind critic:** 7.5/10 after 2 rounds — "good bones, honest composition"; the dusk money shot is deferred
until the grade passes palette at law alphas (spec §13 render 1 stays the build-phase target).

**Ledger:** `WORLD-UNIFIED-V1/V2/V3` (todo, alpha-additive · WORLD) in
`docs/plans/operative-egg-ledger-2026-07-07.yml` + A13 parity rows in `operative-egg-plan-2026-07-07.md`,
committed alongside this doc.
