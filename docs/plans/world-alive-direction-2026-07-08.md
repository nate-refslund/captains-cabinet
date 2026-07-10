# World-Alive — Creative Direction (2026-07-08)

**Role of this doc:** art direction for the `feat/world-grammar-v2` wave. The 07-06 chassis + 07-07 growth design are LAW; this doc is the loving touch inside that law. Captain ratified "go all in" in-session 2026-07-08 — the ship phase cites that when the PR opens. Everything below was verified against disk/live state today (grammar v1 MERGED, renderer live under loaded grammar, 4 officers present: `comms-officer`, `cos`, `polads-ceo`, `stephie-ceo`).

**The one-sentence direction:** the Wardroom becomes a place you'd want to work in, the camera pulls back to a street and then an island that are honestly *young*, and every new pixel still enters through `cabinet/world/{morphology,show-grammar}.yml`.

**Scope ruling (fewer, finished, polished):** ship today = (A) Wardroom behavior + cozy pass at Z2, (B) Street scene at Z1, (C) Island scene at Z0, (D) growth read-model wired into all three, (E) grammar/morphology v2 in ONE PR. NOT today: interiors-per-building (§10.3), Post Office envelope system (§10.4), minimap, `?mode=tv`, expression-seed mint (§5), per-officer house tiers (per-officer census scope is still dark — render houses uniform, honestly).

---

## 0. Hard constraints (checklist the ship phase re-reads before every commit)

- Repo `~/captains-cabinet`, work branches off `feat/fidelity-harness-design` → `feat/world-grammar-v2`. GERMLINE is schg-locked — touch nothing in it.
- **Pixels only via grammar law**: every new scene/prop/behavior lands as a `show-grammar.yml` / `morphology.yml` v2 entry FIRST; renderer consumes parsed law. No grammar change auto-merges — the PR is the door.
- **Determinism ratchets:** no `Math.random` / `Date.now` / unseeded RNG anywhere in `lib/world/` or `components/world/` (CI greps). All variation = `fnv1a(stableId [+ ':' + salt])` + the logical tick. Wall-clock time enters ONLY as data on the SSE snapshot (server route may read the clock; the render path may not).
- CSP for `/world` stays **byte-identical** (eval-free; keep the `pixi.js/unsafe-eval` AOT import; `preferWorkers` stays off).
- **Loud-failure contract extends to every new asset class**: every sheet any scene may draw goes through `requiredSheets()` → `resolveWorldSprites().missing` → `onIssues` → DOM badge (ratchets #8/#9 pattern). Placeholder rendering stays visibly-placeholder, never fake art, never invisible.
- Reserved salience palette untouched: green=verified, amber=blocked/drift, red=killswitch/frozen ONLY, grey=unmeasured, purple=captain-gated. All cozy warmth lives outside those hues (tans, browns, lavender walls, warm amber *lamplight* is fine — it is not signal-amber on a status surface; dual-coding rule keeps it unambiguous).
- Honest zeros render prominent. Rate-routing: >1 event/day sources may only drive TEXTURES (wear, lit windows, pins, smoke), never structure.
- No world-space text — every glyph is DOM. `sel` stays an opaque server handle; no slugs/pids in URLs beyond what exists.
- Dirty-guard: `instance/fidelity/regression_corpus/*` is another session's work — never `git add` it; always `git add <exact paths>`. `.git/index.lock` → retry 5× with sleep 2. Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Gates: `npx vitest run` + `npx tsc --noEmit` + `npx next build` green in `cabinet/dashboard`; `python3.12 -m pytest` green at repo root for touched python; `python3.12 cabinet/scripts/world-asset-gate.py` green after ANY manifest change; `python3.12 cabinet/scripts/world-binding-validator.py` green after ANY morphology change.
- LimeZu binaries stay gitignored (commercial license). Manifest rows + grammar YAML + code are what gets committed.

---

## 1. BEHAVIOR VOCABULARY — the officers act like people

The director stays a pure reducer (`step(state, input)`). All new behavior = new *targets and dwell schedules* computed from `(slug, tick)` via `fnv1a`; walking between them uses the existing journey machinery (`TICKS_PER_TILE = 3`, retarget-from-current-position). Everything y-sorts through the existing `propLayer.zIndex = footY` scheme. Phase-stagger every loop with `fnv1a(slug, salt)` offsets so four officers NEVER move in sync — sync reads as fake; stagger reads as alive.

Logical clock: 1 tick = 250ms. Define `MICRO = 16` ticks (~4s) as the micro-loop quantum.

### 1.1 `working` (and `editing`/`testing`/`investigating`/`researching` — the five desk verbs)

At their own desk, `work` anim (down-facing idle strip + the existing 2px work-bob). Add **micro-loops** on a seeded schedule — pick per window `w = floor((tick + fnv1a(slug,'micro')) / (8*MICRO))`, `r = fnv1a(slug + ':' + w) % 16`:
- r 0–9: type on (no change — typing is the default and should dominate).
- r 10–11: **stretch** — hold static up-frame (row 0, U at x=16) for 6 ticks, then back. Reads as leaning back.
- r 12: **sip** — walk 2 tiles to the officer's desk-side coffee spot (see §2 flair), pause 8 ticks facing down, walk back. Only if the kettle nook exists in layout; otherwise skip (fail to nothing, never to invention).
- r 13: **glance** — face left or right (`fnv1a(slug+':'+w+':g') % 2`) for 4 ticks toward the nearest neighbor's desk.
- r 14–15: type on.
`deploying`/`shipping`/`replying` keep the postbox; `reviewing`/`coordinating` keep the board. No micro-loops at civic stations — civic verbs are higher-salience and should read clean.

### 1.2 `idle` — the seeded wander (replaces daytime "asleep at 2pm")

Today TTL-expired presence → bunk/asleep always, which reads dishonest at 14:00 (session alive, just no tool call for 5 min). v2 splits by the snapshot clock (`snapshot.clock.hour`, server-supplied):
- **Day (08–20 local):** TTL-expired → `idle_program` wander. Waypoint set (all new stations, §2): `kettle` nook → `bookshelf` → `window:1..2` gaze → own desk chair. Schedule: dwell `24 + fnv1a(slug+':'+leg)%16` ticks per stop; next stop = `fnv1a(slug + ':wander:' + legIndex) % 4`. Officers WALK between stops (journey machinery does this for free). Window gaze = up-facing idle strip; bookshelf = up-facing; kettle = down-facing.
- **Night (20–08):** TTL-expired → bunk, `asleep` (existing dim + static frame). Bunk row gets the §2 rest-alcove upgrade.
- **Chat pairing:** when two TTL-expired officers' wander schedules put them on the same waypoint class within 2 tiles (deterministic — schedules are seeded, so co-presence is computable), both face each other (left/right by relative x) and a DOM **ellipsis chip** `…` renders above the midpoint (label layer, text-as-text — this is a label, not grammar pixels). Dwell extends to 40 ticks. No content is invented; the chip means exactly "two quiet officers, same spot".

Honesty note for the legend: idle-wander’s codex says outright "verb TTL expired — the officer's session is alive but no tool call in 5 min; wandering is the *absence* of a verb, not an activity claim."

### 1.3 `meeting` — coordination becomes visible

No invented meeting signal. Real trigger: **≥2 officers simultaneously in `coordinating`** (the verb the post-tool-use hook stamps on trigger/handoff work). Grammar v2 gives `coordinating` a `group` block: solo → work board (unchanged); 2+ → all coordinating officers walk to the new `table` station (the Conference Hall oval table, §2) and take seeded seats around it (`fnv1a(slug,'seat') % 6` of 6 fixed seat offsets), up-/down-facing idle strips, one shared DOM chip listing the verb. Dissolves the moment the condition does. This is the single best "org is alive" moment we can ship honestly today.

### 1.4 `asleep`

Night TTL-expired only (§1.2). At the rest alcove: officer on the bunk seat, alpha 0.45 (exists), plus a DOM `z` chip that blinks on `(tick + phase) % 24 < 12`. No canvas glyphs.

### 1.5 `killswitch` — freeze + red wash

When `snapshot.killswitch`: the client STOPS advancing the director (hold last scenes — frozen mid-stride is the point), canvas gets a full-scene red wash `0xcc2222` at alpha 0.14 via the existing `fxG` layer + the lever lamp stays red. Dual-coded: the unsuppressible DOM banner already exists. Officers frozen, world red, banner text — three channels, one truth. (Red is the reserved hue used exactly per law.)

### 1.6 Transition table (all walked, all seeded)

| from \ to | desk-verb | civic-verb | idle-wander | table (group) | bunk (night) |
|---|---|---|---|---|---|
| any | walk to own desk | walk to station | walk to waypoint 0 | walk to seeded seat | walk to bunk |

Never teleport (grammar is loaded now — the snap-when-pending branch stays for the pending edge case only). `TICKS_PER_TILE` stays 3; wander walks feel right at that speed.

---

## 2. COZY INTERIOR SPEC — the Wardroom you want to live in

All sprite indices below were **verified visually today** against contact sheets of the 339 `office/singles/Modern_Office_Singles_N` (each a 32×48 canvas, bottom-anchored) and the manifest'd interior sheets. Where a cut comes from a big sheet (Conference Hall, Classroom/Library, Room_Builder), the builder re-verifies exact px cuts with the same grid-overlay method documented in the `sprites.ts` header (2026-07-08 precedent) and records them as constants.

Room stays 40×24. Layout additions (new fixed stations in `layout.ts` — ids are grammar-visible):

| station id | tile pos | what it is | sheets/cuts |
|---|---|---|---|
| `table` | (10, 12) | conference oval table + 6 seat offsets | `interiors/13_Conference_Hall_16x16` — big rounded beige table (upper-left region, ~80×48px); verify cut |
| `kettle` | (5, 5) | break nook: vending machine + counter + coffee | singles **175** (vending, warm red items) + **190/191** (low wooden counter) + Conference Hall sideboard-with-coffee-cup cut |
| `bookshelf` | (26, 4) | the org's journal wall (binds tier2 notes, §5) | `interiors/5_Classroom_and_library_16x16` library shelf cuts (verify); interim fallback: tan cabinets **179/180** |
| `window:1` | (12, 2) | wall window, sky swaps by clock | `office/Room_Builder_Office_16x16` window piece on the wall band (verify cut) |
| `window:2` | (28, 2) | second window | same |
| `noticeboard` | (17, 3) | cork board, pins = today's chronicle volume | singles **194** (tall cork panel; **195** variant) |
| `clockwall` | (23, 2) | wall anchor for the DOM clock chip | no sprite — DOM only (numbers are text, text is DOM: law) |

Set dressing (flat + prop layers, all decorative → inspect card says `decorative: true`, zero information, Stardew-density is phenotype and legal):

- **Floor warmth:** keep the grey office floor as the work zone, lay a big warm rug field under the desk band: singles **86** (tan) as the main 3-desk-wide runner at y 7–9, **92** (light centre rug) stays at `floor`, **87** (red) stays dojo. Doormat **93** stays at the door.
- **Plants everywhere sensible:** tall monstera **98** flanking the door (3,11) and the board (22,3); small plant **99** on the kettle counter; snake plant **100** in the NE corner (38,4). One plant per 8 tiles max — cozy, not jungle.
- **Desk lamps:** one articulated lamp per desk from **141–146**, variant = `fnv1a(slug,'lamp') % 6`, placed on the desk's left edge. At night (§2 lighting) each lamp gets a warm additive glow.
- **Wall life:** posters **96, 114, 115** spaced along the top wall; colorful prints **163/164** near the dojo; portraits (Conference Hall green/blue-framed pair) beside the door.
- **Seating that isn't work:** two orange chairs **107 + 111** angled at the kettle nook low table; beanbags (Conference Hall olive/tan/grey trio, verify cut) in the dojo corner — the dojo becomes a reading corner when nobody trains (it is still the dojo; beanbags are decor).
- **Rest alcove (bunk upgrade):** keep chair **197** per officer but back it with the tan cabinet **181** and a small rug **95** strip — reads as a nap corner, not a punishment bench. (Real beds from `interiors/4_Bedroom_16x16` are a later interiors-scene item; don't put beds in the Wardroom.)
- **Postbox dressing:** printer desk **325** (exists) + paper stacks **153/154** beside it + outbound crate **320** — the dispatch corner looks like it ships things.
- **Board dressing:** analytics board **172** (exists) + flip-chart **171** beside it + presentation screen (Conference Hall white canvas cut) on the wall behind.

**Noticeboard pins (bound texture, not decor):** pin count = `min(12, ceil(events_today / 250))` tiny 2×2 colored squares at seeded offsets on the cork — binds a >1/day source, so TEXTURE ONLY per rate-routing law; morphology entry `wardroom_noticeboard_pins` (§5). Right-click the board → codex cites `events_today` from the census keyframe.

**Per-officer desk personalization (seeded, zero-info):** 2 flair items per desk, `fnv1a(slug,'flair') % C(pool)`: pool = {plant **99**, plant **100**, paper stack **153**, tablet **136**, second monitor **131**, backpack **331/333/335** leaning on desk leg, mug (Conference sideboard cup cut)}. Same slug renders identically forever, no two desks match. Officer sprites already vary via the 20 Premade Characters (`fnv1a(slug) % 20`).

**Lighting & day/night (§12 law: night = warm lamp pools + moon-tint, never murky):**
- Snapshot gains `clock: { hour, minute }` (server-computed in `stream/route.ts` from the Captain-timezone; render path never reads a clock).
- Buckets: dawn 06–08, day 08–18, dusk 18–21, night 21–06. Bucket drives: (a) window sky cut swap (light blue / bright / amber / dark-blue-with-stars — 4 window cuts, verify on Room_Builder), (b) a full-room ambient tint layer: dawn `0xffe8d0`@0.06, day none, dusk `0xffc890`@0.10, night `0x2a3560`@0.22, (c) at dusk/night every desk lamp + the kettle nook renders a warm radial pool (additive circle, `0xffb050`@0.15, r=28px). Officers inside a pool at night = the coziest frame this product will ever render; that's the screenshot.
- The DOM clock chip at `clockwall` shows `HH:MM` from snapshot clock (logical time made visible; also proves the world isn't a static picture).

---

## 3. GEOGRAPHY — Z2 Wardroom · Z1 Street · Z0 Island

The existing quantized camera `{0.5, 1, 2}` becomes a **scene selector** (design §10.2 semantics, adapted: our shipped "room at all scales" was already off-spec — this fixes it into three honest levels):

| z (URL `?z=`) | scene | one activity predicate (S1-F1) |
|---|---|---|
| `2` | **Wardroom interior** — everything above, unchanged coordinates | full sprites + verbs + labels |
| `1` | **Street/campus** — the HQ building on its street | officers = 1× sprites ONLY if walking the street would lie; they are inside — so: lit HQ windows + per-officer **badge motes** at the facade (moving = verb present, still = TTL-expired; same Redis predicate as Z2) |
| `0.5` | **Island** — the whole org as land | 4×4px motes at the HQ building, same predicate; ≤12 glyph classes, zero world-space text, no numbers except the overflow count chip |

**Camera transitions:** wheel/± steps swap scenes with a 120ms fade-through-black (snap-tween per §10.2; no parallax tricks — a cut reads cleaner in pixel art). Each scene keeps its own `x/y` clamp box; on scene entry the camera centers on the scene's anchor (Wardroom: room center; Street: HQ door; Island: town center). Primary click at Z0/Z1 keeps its law meaning: navigate — click the HQ at Z0 → Z1; click the HQ door at Z1 → Z2 (matches the door-is-a-scene-swap doctrine). `?z&x&y&sel&at` URL contract unchanged. Secondary click inspects at every level (Legend Law cite path), including the new outdoor props.

### 3.1 Z1 — the Street (LimeZu Modern Exteriors 16px)

**Asset reality check (verified today):** the full 16px Modern Exteriors pack is NOT installed — it exists ONLY as `~/.Trash/modernexteriors-win.zip` (222MB, contains `Modern_Exteriors_16x16/` with the ME_Theme_Sorter singles; the 48px MV sheets at `staged-future/mv-exteriors/` remain BANNED from the manifest). **First act of the ship phase: rescue the zip out of Trash** (`mkdir -p ~/world-packs && mv ~/.Trash/modernexteriors-win.zip ~/world-packs/`) — Trash can be emptied any moment and the license was paid for. Extract ONLY the 16px subtree to `~/world-packs/modernexteriors-win/`.

Promote a curated ~24-file street kit into `cabinet/dashboard/public/world-assets/exteriors/street/` + manifest rows + `world-asset-gate.py` (names verified in the zip listing; exact picks confirmed visually at build):
- Ground: `2_City_Terrains_Singles_16x16/ME_Singles_City_Terrains_16x16_Asphalt_1_Variation_{1,4,7,12}.png` + sidewalk/curb tiles from `1_Terrains_and_Fences_Singles_16x16`.
- HQ building: modular floor pieces from `5_Floor_Modular_Building_Singles_16x16` + office facade/balcony/roof pieces from `16_Office_Singles_16x16` (`…_Balcony_1_Building_{1..4}`, `…_Air_Duct_{1..3}_Roof_Prop`) — **the HQ stacks one modular floor per `commits` tier** (§4), which is exactly what this modular set was made for.
- Neighbors: 2 condo fronts from `4_Generic_Building_Singles_16x16` (`…_Condo_1_*`) — set dressing, decorative, codex says so.
- Street life: from `3_City_Props_Singles_16x16` — streetlight ×2 variants, bench, hydrant, trash can, street tree ×2; parked vehicles from `10_Vehicles_Singles_16x16` (2 cars, side-facing `_Left_1`/`_Right_1` frames), seeded color/slot via `fnv1a('street:car:'+k)`.
- The existing manifest'd mailboxes (`exteriors/22_Post_Office_16x16_Big_Blue_Mailbox`, `…City_Props_16x16_Mailbox_1`) finally go on stage: the blue mailbox stands by the HQ door — it is the STREET face of the postbox station (same dispatch semantics, decorative at Z1).

**Composition:** horizontal street band; sidewalk fore, asphalt mid, buildings rear (HQ centered, condos flanking); trees between streetlights every 6 tiles. Night bucket: streetlight pools (same warm additive), lit HQ windows = `min(floors*4, ceil(ev_session_started_today/50))`-ish TEXTURE binding — no: keep it simpler and lawful — lit windows = one per officer with a live verb (same predicate as motes), the rest dim at night. Liveliness stays presence-driven, not volume-driven.

### 3.2 Z0 — the Island (Serene Village + Modern Farm, staged-future PROMOTION)

Promote (move + manifest rows + gate): `staged-future/village/Serene_Village_16x16.png` → `village/Serene_Village_16x16.png`; from `staged-future/farm/`: `3_Props_and_Buildings_16x16.png`, `1_Terrains_16x16.png`, and 4 crop strips `Crops_Growth_16x16/{Wheat,Corn,Pumpkin,Strawberry}_Growth_Stages_16x16.png` → `farm/…`. (All 16px, gate-conformant; the rest of farm stays staged.)

Verified content of the Village sheet: grass/dirt/stone-path terrains, water edges + bridge, **wooden docks/piers**, a tilled-field patch, hedges, rocks, flower beds, signposts, fences, tree rows in two greens, and cottages in **three roof palettes (red/green/blue) × ~5 shapes with chimneys**. Farm props sheet: barn, two farmhouses, **metal silo**, market stalls with 4 awning colors, stone wells, kilns/furnaces, workbenches, hay, scarecrow, coop.

**Island composition (the law's fixed polar anchors, R from the fold formula — today R = 24 + 6·floor(log10(155,785)) = 54 tiles):**
- Center: the **HQ** (village large cottage sprite + a signboard; click → Z1). Around it a stone-path plaza.
- **Residential W:** one cottage per `role_defined` officer (4 today), birth-order slots on the west path; roof palette seeded `fnv1a(slug,'roof') % 3`, uniform size (per-officer tiers are dark — uniform is the honest render; codex says so).
- **Fields SE:** one tilled sector per ratified outcome (`outcomes_total` = 10 small plots fanned SE); each plot renders a crop strip stage (§4). Crop species per plot = `fnv1a('outcome:'+k) % 4` of the four promoted strips.
- **Harbor S:** village docks + a moored boat (`10_Vehicles …_Boat_1_Down_1` from the street kit) + **the beacon tower: the farm silo with an UNLIT lamp overlay — THE dark lighthouse stand-in** (`cells_graduated = 0`). Codex declares the silo an interim sprite (bespoke lighthouse art remains the authored-art budget line per §12) and that the beam lighting on first graduation will be the biggest visual event in the world's life. Prominent placement, slightly oversized: honest zero rendered LOUD.
- **Works E:** barn + kiln cluster (masonry — commits). **Signals SW:** the two manifest'd mailboxes as tiny postal kiosks. **Training NW:** dojo banner + scarecrow (golden_evals delta ≤ 0 → genome dummies only: exactly one scarecrow, weathered). **Memory NE:** market stall + well (library-to-be; codex: "Library building lands in E2 — stall marks the anchor"). **Law N:** fenced plot + signpost (Keep-to-be). Every anchor marked even when its building is future — absence of the building must never read as absence of the surface.
- Nature fill: tree rows thicken with org age (§4), flower beds only inside R·0.6, rocks at the shoreline. Water ring beyond R.
- Night bucket: cottage windows glow warm; the dark beacon stays DARK (never give it a night light — the zero is the point).

---

## 4. GROWTH STAGES — young org, first sprouts (never "empty")

Pure client fn in new `lib/world/growth.ts`: `tier(S, base) = clamp(floor(log2(S/base + 1)), 0, 7)` — same formula as morphology law; unit-tested against these live values (keyframe 2026-07-08) so the fixtures pin today's world:

| surface | S today | base | tier | visual at that tier |
|---|---|---|---|---|
| memory_rows_total | 1,170 | 80 | **3** | bookshelf ⅜ full (Wardroom); market-stall anchor NE (island) |
| evolved_skills | 9 | 1 | **3** | workbench at Works cluster shows 9 hung-tool pips (≤ tier·4, texture) |
| consequence_ledger_lines | 569 | 70 | **3** | ledger book prop thickness step 3 (postbox corner) |
| commits_total | 1,011 | 120 | **3** | **HQ street building = ground + 3 modular floors** |
| captain_rules | 38 | 5 | **3** | law-plot fence upgrades to stone posts |
| work_completed | 6,708 | 850 | **3** | field plots at crop stage 3 of 7 (see below) |
| subagents_lifetime | 1,260 | 140 | **3** | plaza path: dirt→gravel→cobble→**flagstone center** |
| tier2_note_files | 37 | 4 | **3** | journal stacks on the Wardroom bookshelf |
| packs_dirs | 5 | 1 | **2** | 5 crates on the harbor dock |
| golden_evals_delta | −4 | 2 | **0** | one weathered scarecrow, no grown dummies (honest ≤0) |
| cells_graduated | 0 | 1 | **0** | **dark beacon** — prominent, unlit, forever until the first graduation |
| org_events_total | 155,784 | — | R=**54** | island land radius; shoreline sits exactly there |

- **Crop stages:** each Crops_Growth strip is 112px = **7 stages × 16px**. Field plot stage = `min(6, work_completed tier)` today (aggregate; per-sector splits land with the E2 emitters — codex says which). Today that renders stage-3 growth: visible green rows, nothing ripe. **Reading: "first sprouts", precisely as briefed — 10 plots, all growing, none harvested, and the beacon dark.** A young org that is clearly ALIVE, not an empty map.
- **Hysteresis (law):** a tier change must hold 2 consecutive daily keyframes; until then render the OLD tier + a construction scaffold overlay (village fence pieces + a DOM "under construction" chip on inspect). `growth.ts` takes the last two keyframes and returns `{tier, pendingTier|null}`; the API serves both (only 2 keyframes exist yet — day one of hysteresis is itself honest).
- **Street liveliness with age:** props unlock by org-age band (from first keyframe date): <7d = bare street; 7–30d = benches + trees (today); >30d = second streetlight row + planters. Seeded positions, never moving once placed (positions fix at birth: fold law).
- **Stage narrative hooks (defer the fireworks):** celebration cutscenes (first paving, kind_unfrozen ice-shatter, rule-promotion bell) are E2 vocabulary expansion per the chassis — do NOT ship ad-hoc versions today. The growth pass just makes the *state* readable; ceremonies come through their own grammar PRs.
- **Data path:** `/api/world/grammar` response gains `keyframes: [prev, latest]` (server reads `shared/interfaces/world-chronicle.jsonl` tail — same fenced file the validator uses; no DB creds, no Redis in the render path). Missing/short file → `keyframes: []` → all growth surfaces render day-0 + ONE amber "census unavailable" badge via the issues chain (grey/unmeasured discipline).

---

## 5. GRAMMAR DELTA — everything above, as law (one PR)

`feat/world-grammar-v2` carries exactly these additions. Parser work in `grammar.ts` stays fail-closed: unknown keys ignored-with-problem, closed enums, codex required everywhere (coverage gauge already live).

### 5.1 `show-grammar.yml` → version 2

New top-level blocks (schema additions in `parseShowGrammar`):

```yaml
version: 2

# vocab.anims unchanged: [work, walk, idle] — asleep stays a director-honesty
# state, micro-loops are cosmetic variation inside anim=work (phenotype).

idle_program:            # daytime TTL-expired wander (verb-absence made visible)
  waypoints: [kettle, bookshelf, window:1, window:2]
  dwell_ticks: 24
  night_station: bunk    # 20:00–08:00 captain-local → asleep at the rest alcove
  chat_chip: true        # DOM ellipsis when two idle officers share a waypoint
  codex:
    represents: "Officer session alive but no tool call in 5 min (activity TTL expired). Wander/chat/nap are the ABSENCE of a verb — day renders wander, night renders sleep; nothing here claims work."
    mechanism_path: "cabinet/scripts/hooks/post-tool-use.sh"
    day0: "empty room after hours"

group_scenes:
  coordinating:
    min_officers: 2
    station: table
    codex:
      represents: "Two-plus officers holding the coordinating verb simultaneously — rendered as a table meeting instead of separate board visits. Dissolves when the condition does."
      mechanism_path: "cabinet/scripts/hooks/post-tool-use.sh"
      day0: "empty table"

night:                   # §12 law: warm pools + moon tint, never murky
  buckets: { dawn: [6, 8], day: [8, 18], dusk: [18, 21], night: [21, 6] }
  lamp_pools: true
  window_sky: true
  codex:
    represents: "Captain-local wall clock, server-stamped onto the SSE snapshot (the render path never reads a clock). Drives ambience only — never state, never morphology."
    mechanism_path: "cabinet/dashboard/src/app/api/world/stream/route.ts"
    day0: "same room, honest lighting"

killswitch_scene:
  freeze: true
  wash: red              # reserved hue, dual-coded with the DOM banner
  codex:
    represents: "cabinet:killswitch active — director halts (officers freeze mid-stride), scene washes red, banner breaks through. Reset stays a Captain act outside the world."
    mechanism_path: "cabinet/scripts/kill-switch.sh"
    day0: "never seen, hopefully"

scenes:                  # quantized camera z → scene (design §10.2 adapted)
  "2": wardroom
  "1": street
  "0.5": island
```

New stations referenced (`table`, `kettle`, `bookshelf`, `window:1`, `window:2`, `noticeboard`) land in `layout.ts` as fixed civic stations; each gets an inspect codex in the client (decorative ones say decorative).

### 5.2 `morphology.yml` → version 2 (new entries; validator must stay green)

All bind the census keyframe via the same `jq -r -s 'last | .FIELD' shared/interfaces/world-chronicle.jsonl` pattern (T0, replay: ledger) unless noted. Each with the mandatory codex; `day0` lines below are the actual codex day0 strings:

| id | represents | binding field | base | day0 |
|---|---|---|---|---|
| `street_hq_floors` | HQ street building height — one modular floor per commits tier | `commits_total` | 120 | "ground floor only" |
| `island_land_radius` | island landmass — R = 24 + 6·floor(log10(events+1)) | `org_events_total` | — (formula in codex) | "24-tile islet" |
| `island_officer_houses` | one cottage per defined role, birth-order slots, west path | `ev_role_defined` | 1 | "no houses — an egg has no streets" |
| `island_fields` | one tilled plot per ratified outcome; crop stage = work_completed tier (aggregate until E2 sector emitters) | `outcomes_total` + `ev_work_item_completed` | 850 | "unplowed ground" |
| `island_harbor_beacon` | THE dark beacon (interim silo sprite; bespoke lighthouse art tracked in the authored-art budget) — beam lights on first graduated cell | `cells_graduated` | 1 | "dark beacon, loud about it" |
| `island_harbor_crates` | dock crates per extension pack | `packs_dirs` | 1 | "5 inherited crates" |
| `island_services_mill_row` | Works-ridge mill/kiln row: total service rows, disabled rows render stopped | `services_rows_total` / `services_rows_disabled` | 8 | "9 spinning, rest ghost-framed" |
| `wardroom_bookshelf_fill` | Wardroom bookshelf fill — tier-2 journal mass | `tier2_note_files` | 4 | "empty shelf" |
| `wardroom_noticeboard_pins` | cork-board pin TEXTURE — today's org-event volume (rate-routed: >1/day source, texture only, never structure) | `events_today` | — | "bare cork" |
| `street_liveliness` | street prop unlock band by org age (bench/trees/planters) — TEXTURE class | first-keyframe date | — | "bare pavement" |

(Existing v1 entries untouched. `hats_earned` stays dark; `org_posture` keep-flag rendering waits for the Keep building — unchanged.)

### 5.3 Code touch list (renderer, all under the law above)

- `lib/world/grammar.ts`: parse the five new blocks (closed enums, problems[] on anything malformed, codex coverage counts them).
- `lib/world/layout.ts`: new stations; export per-scene layout modules `street-layout.ts`, `island-layout.ts` (pure, integer tiles, seeded placement, positions never move).
- `lib/world/growth.ts` (new): tier fn + hysteresis pair + unit tests pinning the table in §4.
- `lib/world/director.ts`: idle_program wander scheduling, group_scenes resolution, night bucket input, killswitch freeze input. Still one pure `step()`; new inputs arrive via `DirectorInput` (`clockHour`, `killswitch`).
- `lib/world/sprites.ts`: new cut constants (verified px), `STATION_SPRITES` additions, per-scene `requiredSheets(scene)` union feeding the SAME missing→badge chain.
- `components/world/world-canvas.tsx`: tint/lamp/window layers, scene-swap rendering, red wash; `world-client.tsx`: scene selector on z, clock chip, ellipsis/z chips (DOM), HUD title per scene.
- `app/api/world/stream/route.ts`: `clock` on snapshot; `app/api/world/grammar/route.ts`: `keyframes` tail.
- Manifest: street kit + village/farm promotion rows; `python3.12 cabinet/scripts/world-asset-gate.py` MUST pass; binaries stay gitignored.

### 5.4 Ship order (commits on `feat/world-grammar-v2`)

1. `world: rescue+promote street/island asset kit (manifest+gate)` — zip rescue, extraction, promotion, gate green. *(Assets themselves untracked; manifest.json is the commit.)*
2. `world: grammar v2 — idle program, group scenes, night, killswitch scene, scenes map + morphology v2 growth entries` — YAML + parser + validator green. **The PR review centers here.**
3. `world: growth read-model (growth.ts) + keyframe/clock plumbing` — tests pin §4 table.
4. `world: wardroom cozy pass + behavior vocabulary` — layout/sprites/director/canvas.
5. `world: street + island scenes with scene-swap camera`.
6. `world: ratchet + badge extensions, vitest/tsc/build green` — determinism greps still clean, new sheets in the loud chain.

Then: PR `feat/world-grammar-v2` → base `feat/fidelity-harness-design`, body citing the Captain's in-session "go all in" ratification (2026-07-08) and this doc; Captain merge = the law act that turns the pixels on. Trailer on every commit: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

**Definition of done (today):** four officers visibly living — typing, stretching, wandering to the kettle, meeting at the table when coordination overlaps, sleeping at night under lamp pools; one wheel-scroll out reveals a 3-floor HQ on a lit street; one more reveals a 54-tile island with 4 cottages, 10 sprouting plots, 5 dock crates, and one loud dark beacon. All of it citable by right-click, all of it law.
