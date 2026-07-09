# CABINET WORLD — UNIFIED SPEC v2 · THE ONE SPEC
## Harvestholm & Lantern Quay → the Archipelago · egg → endless growth · 2026-07-09

**What this is.** The single spec of record for the next level(s) of the Cabinet World. It
synthesizes the ratified unified island (`world-unified/unified-spec.md`, approved 7.5,
`docs/plans/world-unified-direction-2026-07-08.md`) with the eight 2026-07-09 track
deliverables in `world-next/`: `archipelago.md`, `growth-grammar.md` + `egg-tile-plan.md`,
`interiors.md`, `bestiary.md`, `infra-viz.md`, `economy.md`, `ui-pack.md`. Where tracks
conflicted, §10 resolves them explicitly. Everything in every source doc that is not
contradicted here CARRIES; where this spec contradicts a source doc, THIS spec wins.

**Every binding below was live-verified read-only on 2026-07-08/09** by its track (receipts
in the track docs, §0 tables there). No invented feeds, no assumed numbers.

---

## 0. RULING LEDGER + SUPERSESSIONS

**Binding Captain rulings, newest first:**

| Date | Ruling | Effect in this spec |
|---|---|---|
| **2026-07-09** | **Killswitch lever = the ONE in-world actuator** (two-tap + confirm). Everything else read-only, **including the mailbox**. | §9.3 lever spec; doctrine line D2 amended with the single carve-out; no other interaction mutates anything, ever |
| **2026-07-09** | **Economy = STRICT cost-viz.** Real token spend from the revived cost ledger (`cabinet:cost:tokens:daily:<date>`, writer `cabinet/scripts/hooks/session-stop.sh`) — never invented numbers. | §8; all $ surfaces cite the exact Redis key; missing data renders grey "unmeasured", never $0-as-fact, never back-filled |
| **2026-07-09** | **Growth = VISIBLE WORK.** Sprites clear trees / build when real events fire. | §3.4 two-speed construction pipeline; ceremonies 8/9; infra recovery walks; all movement event-anchored |
| 2026-07-08 (addendum) | Four-library taxonomy (home library / product-isle libraries / harbor shipping-record / Charter Hall). Mailbox strictly read-only. | §5.2 (Charter Hall furnished; harbor record lives in the Harbormaster's hut card); mailbox view-only carried |
| 2026-07-08 | ONE island, TWO districts ratified (7.5); Harvestholm = self-work, Lantern Quay = mission/product work. | §2 carries the geography verbatim; archipelago extends it without moving a tile |

**Standing doctrine (not re-litigated):** one continuous world; LOD zoom + pan only
(zoom-OUT to archipelago = LOD, ratified — never a scene swap); roof-cutaway in place for
interiors; morphology/show-grammar law (`cabinet/world/{morphology,show-grammar}.yml`) =
the only path to pixels, no auto-merge; deterministic seeded everything
(`fnv1a(stableId[+salt])` + logical tick; `world_at(T) = f(state_at(T))`); aesthetic
harness (`cabinet/scripts/world-aesthetic/world-aesthetic-gate.py`) gates every render —
fix composition, never thresholds; every bound element carries codex + WHAT/NOW/PROOF
inspect card; decorative elements answer honestly "carries no data"; rate-routing (>1
event/day sources drive TEXTURE only — volume cannot mint capability); honest zeros render
prominent; reserved salience palette (green verified / amber blocked / **red
killswitch-only** / grey unmeasured / purple captain-gated), dual-coded always.

**Supersessions (v1 → v2):**

1. **Unified-spec §8 "Day-0" is superseded by the EGG** (§3.1 here, tile plan
   `egg-tile-plan.md`). The old day-0 hamlet (full Great House, well, noticeboard, stone
   quay at birth) becomes growth stages — the egg is a clearing, a cottage, a pole, a
   mailbox, a path, a rowboat jetty, and a dark lantern-cairn.
2. **The always-standing lighthouse is superseded by the staged lighthouse** (cairn → base
   → tower by `cells_accumulating` tier → LIT at first graduation). The honest-zero anomaly
   exists from birth at egg scale (the dark cairn) — the codex line "No light has ever been
   earned" carries at every stage.
3. **Doctrine line "≤2 render levels: the island plus ONE interior (the Great House
   wardroom)"** is amended — pending the Captain's grammar-law PR merge (§14 call #1) — to:
   *"the island plus AT MOST ONE interior open at a time — the interior of whichever bound
   building the camera is close over."* Same spirit (bounded complexity, no scene swaps,
   one dollhouse at a time), universal scope.
4. **"No new actuators, ever" gains its single ruled exception:** the killswitch lever
   (§9.3). The sentence now reads: *the world render is read-only; the ONE in-world
   actuator is the killswitch lever, two-tap + confirm, cookie-gated; everything else —
   mailbox included — navigates, inspects, or deep-links only.*
5. Grammar-v2 `scenes:` enum (`wardroom|street|island`) retirement carries from v1 —
   completed by the universal cutaway (§5.1), which is the same mechanic applied N times.
6. The growth-track "hearth woodpile" cost seam is **cut** in favor of the economy track's
   surfaces (§10 R3) — one truth, one place.

---

## 1. LOCKED DOCTRINE v2 (delta lines only — everything else carries from v1 §0)

- **D1 (unchanged).** One continuous world; camera = pan + integer-NN LOD zoom. Ladder
  extended DOWNWARD: ×3 close / ×2 mid / ×1 island / **×1/2 coast / ×1/4 archipelago**
  (grammar precedent: show-grammar.yml already quantizes `"0.5" → island`).
- **D2 (amended per ruling).** World render is read-only **except the killswitch lever** —
  the ONE actuator, two-tap + confirm + captain cookie (§9.3). Mailbox, noticeboard,
  library, cargo, poles, beds, animals: navigate / inspect / deep-link only.
- **D3 (amended pending merge).** At most ONE interior open at a time, any bound building,
  revealed by roof-fade in place (§5.1). The world keeps ticking around it.
- **D4 (new, from VISIBLE WORK).** Structure never pops in: every quick work runs its
  minutes-scale site, every great work runs its 24 h scaffold **with a crew** — both pure
  functions of `(T0, now_tick)` (§3.4). Sprites move only when real events fire.
- **D5 (new, from STRICT COST).** Every $ figure on any surface derives from
  `cabinet:cost:tokens:daily:<YYYY-MM-DD>` / `cabinet:cost:tokens:<officer>` (writer:
  `session-stop.sh`, live-verified). Estimates are labeled estimates; absences are grey;
  history begins the day durable keyframes land (P-ECO2) and is never back-filled.
- **D6 (new).** Glance-budget law extends to every zoom level: max 5 signals per level
  (island budget carries; archipelago budget in §2.4). Anomaly lamps (killswitch pin,
  infirmary red-cross) PREEMPT the lowest-priority slot when lit rather than adding a 6th.
- **D7 (new).** One truth, one place — enforced across tracks: a census field/ledger key
  binds ONE glance surface; any second rendering of the same truth is a *dual-view* that
  must codex-link its sibling (registry in §10 R8).

---

## 2. GEOGRAPHY v2 — the island unchanged, the sea grown honest

### 2.1 Main island (carried verbatim)
The ratified 60×48-tile core — Harvestholm inland-north on the rise, Lantern Quay on the
south coast, the ~40-tile road with the crossroads (mailbox + noticeboard + post-kiosk) at
its midpoint — carries tile-for-tile from unified-spec v1 §1–2. District rosters (v1 §2.1/
2.2/2.3) carry with the deltas listed in §4. Nothing moves (layout_fold law).

### 2.2 Archipelago canvas + anchors (from `archipelago.md`, ADOPT-STAGED)
- Canvas grows to **240×192 tiles** (3840×3072 px @16 px ×1); the ratified island composes
  in unchanged at offset **(90, 8)**. Sea owns everything south of the quay line (y≈52).
- **Isle anchors = morphology law, fixed at birth**, a bearing fan off the quay center
  (120, 52) at ring radius 126 tiles, slots ≥30° apart: polads SE (200,150) · stephie SW
  (40,150) · stepnetwork S (120,168) **reef-buoy only** (retired; ruling stands) · slots
  4/5 reserved under mist + grey buoys (canvas extends ±48 tiles mechanically at
  assignment; anchors never move). Future lanes take the next fan slot.
- **Spacing math holds pairwise:** `R_isle = 8 + 3·tier(lane_org_events)` → tier-7 max
  R=29; minimum pairwise separation 65 > 58 — no two tier-7 isles ever touch, no isle
  reaches the main island (min lane ≈ 98 tiles). Distance is FIXED and never encodes
  maturity; maturity = size + light.
- `system-self` = the main island (codex states it). `sensed` lane gets no isle (open call
  §14 #6). Compositor contract: `archipelago-positions.json` (schema
  `archipelago-positions/v1`, in this dir).

### 2.3 Isle growth rings (unbounded, each ring earns itself)
| Ring | Band | Builds | Binding | Status |
|---|---|---|---|---|
| r0 dock | 0–4 | jetty + dock light + mooring | lane has ≥1 ratified outcome (`outcomes.yml`) | **EXISTS** |
| r1 warehouses | 4–10 | one warehouse per ACHIEVED outcome; ceremony-landed crates | `outcomes.yml` achieved per lane (polads 1, stephie 1) | **EXISTS** |
| r2 town | 10–20 | cottages/workshops by lane work tier; lit windows = lane-classified presence; chimney = lane chronicle flow | per-lane census block (**P3**) + `attrs.lane` (**P2**) | [v2] |
| r3 district | 20–29 | one lot per work-graph node, lot state = node state, footpaths = node edges (task viz, Obsidian-graph feel) | work-graph events read (**P5**) — events, never 0-row projections | [v2] |

Rings appear outward only; 2-keyframe hysteresis + scaffold; an un-earned ring may render
surveyor stakes with codex "staked, not earned: per-lane census not wired". Isles become
explorable (pan across water — still one world) when r2 lands.

### 2.4 Sea lanes, ships, fog, LOD (adopted)
- **Two-signal shipping (polads live TODAY):** cargo ship departs on the real milestone
  (achieved flip / verified work item); crosses at fixed 0.5 s/tile over the real 126-tile
  lane (**the Captain's 60–90 s emerges from distance ÷ speed, not a timer**); **rides at
  anchor** in the isle roadstead until probe-vercel `deploy_ready` (READY + prod alias
  stable ≥60 min — the honest wait made visible); docks + unloads (~20 s linger) on the
  verdict; **turns back with cargo** on rollback supersede (witnessed failure). Unprobed
  lanes (stephie) sail and dock on keyframe-confirm with codex "unverified by probe —
  probes.yml has no stephie row". Plumbing: **P-A** (chronicle lifts probe verdicts into
  closed verbs `deploy.verified`/`deploy.rolled_back` + `attrs.lane`); **P-B** (stephie
  probes.yml row = Captain merge, §14 #7). Ships NEVER render cost (economy lives at §8's
  surfaces).
- **Horizon fog = grey-unmeasured made geographic** (not decor): mist pockets over
  reserved slots; thin haze ribbon on unprobed sea lanes (wiring P-B clears it); isle
  interior mist beyond the last earned ring. Always dual-coded with a grey buoy. Distinct
  from the unratified [v3] sensor-fog proposal (P8, §14 #4) — spatial vs temporal, never
  confused. Gate: mist = dithered native tiles in horizon band + pockets, never full-frame
  wash; open water ≲30% per frame via wave tiles/foam/wakes/ships.
- **LOD ×1/2 + ×1/4:** props cull, buildings collapse to seeded footprint blocks from
  `world.map.json`, officers cull, **ships stay** (4-px silhouettes), light aggregates per
  district. **Archipelago glance budget (max 5):** ① killswitch red wash (override) ② the
  dark lighthouse ③ per-isle light mass ④ ships under way / at anchor ⑤ mist share.
  Stranger's read at ×1/4: *"one warm island that thinks, a fleet on the water, bright
  colonies growing where the ships go — and mist where the org hasn't looked yet."*

---

## 3. GROWTH GRAMMAR — egg → archipelago, all work visible

### 3.1 The egg (supersedes v1 day-0; tile plan in `egg-tile-plan.md`)
A fresh deployment renders an R=24 forested islet with a **20×14 cleared heart**: one
cottage (the Great House at t0 — same building identity, it GROWS, never replaced), one
bare flagpole, one mailbox (flag down), a dirt path south to a **rowboat jetty** (Lantern
Quay at t0), and a **dark lantern-cairn** on the shore rock (lighthouse t0 — ambition
visible from birth at egg scale). No cottages, no crew, no noticeboard, no well: an egg
has no streets. All positions are the unified island's anchors at t0 (layout_fold —
nothing ever moves). First five beats a Captain watches: pennant raised on first keyframe →
first cottage (first role, trees felled ON SCREEN) → first berth chalk (first outcome) →
first tool pip (first skill) → rowboat replaced by the sailing packet (first achieved).

### 3.2 Three-class event routing (Captain's "every real event grows the world", made lawful)
| Class | Rate | Grows | Mechanism |
|---|---|---|---|
| **TEXTURE** | >1/day | wear, bloom, smoke, footprints, pins, crop stages — never meaning-bearing objects | pure f(today's counters) per tick; resets daily |
| **QUICK WORKS** | ~1/day–1/week | props on existing structures: berth chalk, tool pip, shelf band, lantern post, veto stone, field plot | construction site, 15 min (small) / 90 min (large) |
| **GREAT WORKS** | <1/week | buildings + land: cottages, workshop, library wings, barn tiers, lighthouse stages, quay sections, isle rings | 2-keyframe hysteresis + 24 h scaffold, WITH crew |

A tool-call bends grass; a ratified outcome chalks a berth in an afternoon; a hired officer
raises a cottage over a witnessed day. Full ladder (element × stages × driver × class,
every driver live-verified with today's value) = `growth-grammar.md` §3, adopted whole.
Highlights: Great House grows by `ev_session_started` tier; workshop shed at 4th evolved
skill; well at first completed loop; lantern posts ERECTED per graduation-transition
(13 → posts standing) but LIT only per full graduation (`cells_graduated` 0 → **all
dark** — the road of dark posts is the honest pre-graduation picture); rowboat → packet
boat at first achieved outcome (already earned, 2).

### 3.3 The visible-work pipeline (pure function — replay-identical)
```
T0(site)  = ts of the WITNESS record (chronicle ts for verb-witnessed quick works;
            first-seen snapshot tick persisted to world-sites.jsonl for config flips;
            FIRST keyframe showing the new tier for great works)
progress  = clamp((now_tick − T0) / D, 0, 1)
phases    = CLEARING (<0.25, crew fells trees/clears lot) → RAISING (<0.75, scaffold +
            hammer crew) → FINISHING (<1.0) → REVEAL (quiet frame; site retired)
crew      = 1 + tier(footprint,4) seeded "wright" sprites — DECORATIVE-HONEST: staging of
            a real transition, never officer claims; codex says exactly that
site sign = WHAT (element + target stage) / NOW (phase, %) / PROOF (witness record:
            census field old→new, outcomes.yml diff, or chronicle iid)
```
Great works whose 2nd keyframe does NOT confirm are **STRUCK**: crew departs, scaffold
comes down, lot reverts — an honest false start, codex cites both keyframes. High-rate
events can never start buildings (T0-from-keyframe enforces rate-routing).

### 3.4 Land expansion + the unbounded map
- **Village:** forest retreats only where a great-work site needs its lot, during its
  CLEARING phase — trees fall on screen; clearing = union of earned footprints + margins.
- **Harbor:** land reclamation — quay sections extend per pier tier (posts → infill →
  capping over water); berth demand beyond capacity renders a waiting chalk outline.
- **Products:** isle rings raise per §2.3, built by rowboat crews around the shore.
- **Map:** sparse 16×16-tile chunks over a procedural `base(cx,cy)` field parametrized by
  the growth counters (R, clearing polygon, quay sections, isle rings) — land growth needs
  zero chunk rewrites; only authored content stores diffs (append-only site ledger,
  rebuildable). Endless with O(built) storage; LOD samples the same world coarser.
- **Eras** (the arc): EGG → HOMESTEAD → HAMLET → **VILLAGE + WORKING QUAY (≈ today: R=54,
  t3 village, 6 berths at stage-3, lighthouse tower part-built and DARK)** → PORT TOWN
  (P2/P3 + first graduation = the light) → ARCHIPELAGO.

---

## 4. DISTRICT ROSTER DELTAS (v1 rosters carry; new/changed elements only)

| Element | District | Binding (verified) | Class / stage |
|---|---|---|---|
| **Switchboard hut** | between crossroads + Great House | doctor heartbeat `cabinet:doctor:heartbeat` (GREEN/DEAD:n, staleness-gated) | §7 · v2 |
| **Telegraph poles + wires** (12 repo servers) | along the road spine | doctor per-MCP lines + `.mcp.json.mac-native`/`extra-mcps.json` + `mcp-scope.yml` | §7 · v2 |
| **Infirmary + convalescent yard** | Harvestholm north edge | census infra block (P-INF): crash-loops, dead services, probe failures | §7 · v2 |
| **Water tank** | village edge above the barn | `cabinet:memory:embed_queue` XLEN (fills AND drains; amber float on clog) | §6 · v2 |
| **Counting table → Counting-house** | village, plaza edge | anchor now; building staged on chronicle cost keyframes (P-ECO2) | §8 · v1b anchor, v3 building |
| **Customs House board** | Lantern Quay | org aggregate today+yesterday from the daily cost hash | §8 · v1b |
| **Treasury pin** | crossroads noticeboard | latest daily 23:00 cost digest (real, exists) | §8 · v1b |
| **Killswitch lever + far-zoom pin** | Great House exterior wall, left of door | `GET cabinet:killswitch` every tick; renders true state incl. out-of-band flips | §9.3 · v1b |
| **Lighthouse (staged)** | breakwater point | cairn → base → tower (`cells_accumulating` 16) → LIT (`cells_graduated` 0 = dark) | §3.2 · v1a |
| **Lantern posts** | the road | erected per `ev_graduation_transition` (13), lit per graduation (0) | v1a |
| **Chickens (flock + chick)** | workshop/coop yard | `ev_subagent_completed` tier + live `tool.call[Agent]`/`crew.completed` | §6 · v2 |
| **Groundskeeper + lawn state** | meadow, by composter | apoptosis sweep census ints (P-LAWN); leaning-on-fence = REPORT_ONLY truth | §6 · v3 |
| **Bees + beehive** | crossroads → buildings | chronicle `comms.notified` (Day-1 from mailbox; point-to-point at P-BEE) | §6 · v2/v3 |
| **Cat** (companion #2) | wardroom kettle counter / window sill | none — honest "carries no data" | §6 · v2 |

Glance-budget priority at island zoom (D6): killswitch wash > mailbox flag > infirmary
red-cross lamp (only when a critical bed is occupied — preempts slot 5) > bodies/windows/
smoke > cargo gradient > dark lighthouse > sky clock.

---

## 5. INTERIORS + UNIVERSAL INSPECT (from `interiors.md`, ADOPT-STAGED)

### 5.1 Universal roof-cutaway (single-active)
At ≥×3, the ONE building whose bbox covers ≥40% of the viewport's central third (held 2
ticks; deterministic tie-break by birth order) fades its roof layer 1→0.08 over 300 ms IN
PLACE; wall caps stay; interior props + officers render y-sorted inside; night tint + lamp
pools apply inside too. Pan away → roof returns. Officers are *revealed mid-verb*, never
teleported — the director stages interior stations whether or not a roof hides them. The
world ticks on around the open room. Requires doctrine amendment D3 (§14 call #1).
Ambient-audio continuity recorded as law-intent (zero audio exists today; if it ever
ships, it is a world-level seeded loop, never per-interior).

### 5.2 Truth-rooms (furniture IS the data; all bindings live-verified)
- **Memory Library:** 7 shelf units filled to `memory_rows_total` tier (1,170 → t3; empty
  shelves are the honest zero); journal desk stacks = keyframe delta bucket (Δ+551 real);
  archive boxes = `tier3_files` 33. [v3] card gains GET-only search (P6).
- **Skill Workshop:** pegboard = `evolved_skills` 9 pips; fixed 18-slot foundation rack
  (repo constant — the pegboard-vs-rack contrast is the story); 5 pack crates (dual-view
  with warehouse, §10 R8); shavings + open door on `skill.promoted` days.
- **Charter Hall (the Manor):** framed rulings = `captain_rules` tier (38 → frame count;
  empty hooks beyond = wall built for more law than exists); **empty veto plinth**
  (`captain_vetoes_total` 0 — "no Captain veto has ever been recorded"); posture pennant
  echo; officers with `policy.shadowed`/`trust.*` verbs visibly walk here to consult
  (event-real). Ruling TITLES live only in the authed card (P-INT1) — never world-space.
- **Officer cottages ×4:** v1 uniform desk + honesty codex; v1.5 per-officer paper piles
  from `tier2_by_role` (P-INT2; on-disk today: cos 11 / polads 9 / comms 5 / stephie 3).
  Night cutaway shows the sleeping officer (presence TTL law pays off).
- **v1.5 rooms:** Harbormaster's hut (open ledger = 6 active outcomes; the harbor
  shipping-record library of the four-library taxonomy lives HERE as card depth);
  Warehouse (crate rows = 2 achieved + 5 packs provenance-face); Observatory (star-chart
  pins = `cells_accumulating` 16; **blank graduation ledger book** while 0); **Lighthouse
  lamp room** — an unlit lamp, a dusty chair, `cells_graduated = 0` on the card. Nothing
  else. Barn/pens: no interior (animals live outside).

### 5.3 Universal clickability + coverage gauge
Every renderable entity id carries a grammar entry with `codex` or `decorative: true`;
click resolves via the compositor hit-map (`world.map.json` + `labels.json` — already the
gate contract) → the SHIPPED WHAT/NOW/PROOF card (`inspect-card.tsx`, decorative →
WHAT-only fallback verified). Catch-all: unmapped pixels answer "ground / water — carries
no data" (zero dead clicks). Legend chip: `codexCoverage` redefined = entries with
codex-or-decorative ÷ entity kinds emitted in map.json; **binding-validator adds the
check: an emitted entity kind with no grammar entry = validation error** (coverage only
ratchets up). Free text (ruling titles, card prose) lives in the authed response only.

---

## 6. BESTIARY — adopted subset (from `bestiary.md`; verdicts carried)

| Creature | Verdict | Binding | Stage |
|---|---|---|---|
| **Water tank** | ADAPT | level = `cabinet:memory:embed_queue` XLEN (1,076 — fills AND drains; the manifest's own health floor is "XLEN not monotonically growing"); amber float on multi-day rise. Brain SIZE stays with the Library (no double-bind) | v2 (P-TANK: one int on snapshot) |
| **Chickens** | ADOPT | flock = `ev_subagent_completed` tier (1,260 → 3 hens); chick hatches per live `tool.call[Agent]`, fades on `crew.completed` or TTL — codex states TTL semantics ("the chick is the event, not a running-count claim") | v2 |
| **Cows / mixed herd** | ADOPT-STAGED | 38 services − 2 disabled graze (ghost pens already law); per-animal health (grazing / lying = stale / amber vet flag = dead) from the **census infra block** (P-INF, §10 R2 — NOT a second doctor feed); species seeded per manifest row (mixed herd, pure phenotype) | counts v1a (ratified) · health v2 |
| **Cat + dog** | ADOPT | DECORATIVE, honest card ("Carries no data — pets gratefully accepted"); "petting" = client-only seeded reaction riding the inspect click — zero state, zero writes. Exactly one of each, forever (scarcity keeps the bound/decorative boundary legible) | dog v1a (law) · cat v2 |
| **Lawn-mowing** | ADAPT | lawn shagginess = days since last sweep WITH actions>0; mow animation only on an action-bearing sweep (live or replay); **groundskeeper leans on the fence while cards-only** — the honest REPORT_ONLY-apoptosis joke | v3 (P-LAWN: 3 census ints) |
| **Bees** | ADOPT-STAGED | one bee per live `comms.notified`, mailbox → recipient building, cap 4 (overflow = hum shimmer); point-to-point origins at P-BEE (sender-name allowlist). Bees mean exactly "a message moved" — never content or importance | v2 (Day-1) · v3 (P-BEE) |

Rules carried: only flock/herd/tank-structure are structure (census + hysteresis); chicks/
bees/stripes/tank-level are event- or overlay-texture; vet flag is AMBER (red stays
killswitch-only); every creature promotion enters via manifest rows + asset gate + grammar
PR; creature adjacency to a building never implies binding (cards carry the truth).

---

## 7. INFRA LAYER — telegraph + infirmary (from `infra-viz.md`, ADOPT)

### 7.1 MCP telegraph (trunk + LOD drops)
Switchboard hut (bound to the doctor heartbeat — **stale >26 h ⇒ ALL wires grey
"unmeasured"**: never render yesterday's OK as today's) anchors 12 repo-layer server wires
along the road; at ≥×2, drop-wires fan to buildings whose officers hold the grant
(`mcp-scope.yml`). Five wire states, dual-coded, matching the estate exactly (not the
Captain's three — collapsing would lie): OK = taut dark still · DEAD = snapped + 2-frame
spark + paper tag naming the unresolved `${VAR}` (names only, never values) · UNVERIFIABLE
(claude.ai profile connectors) = wire into coastal fog at 50% · WAIVED = purple insulator
cap · unregistered grant = slack grey wire pooling at the pole base. **Humming inverted
deliberately:** healthy wires are still; only the broken one animates (change-is-signal).
Wires = a show-grammar procedural pass (no catenary sprite exists in LimeZu — same legal
class as blob shadows/lamp pools). Pole card: WHAT (server, layer, command summary) / NOW
(doctor line verbatim, grant holders) / PROOF (log path + heartbeat key + config path);
"last use" renders **"no usage telemetry — carries no data"** until a hook-side counter
exists (never inferred).

### 7.2 Infirmary (field-infirmary, exterior cots — doctrine-clean)
LimeZu Hotel&Hospital building (on disk) + walled convalescent yard at the village north
edge; cots are exterior props (no second cutaway needed). **Admissions are real degraded
things only:** officer crash-loop (launchd no-PID + nonzero exit 2 ticks, or liveness key
expired while a session should live) = critical, red-cross lamp; dead service = major
(enacted by the herd animal walking to the yard — §10 R2); probe failure = major; Sentry
incident = v2.5 (parse contract first); red CI = v2+ (no feed on disk — honest absence);
non-localizable doctor DEADs = minor generic bed. Killswitch is NEVER a patient (it is the
world-wide red wash); WAIVED never admits (purple = deliberately waiting). **Empty
infirmary renders prominently empty** — made beds, lamp off: "no degraded systems" is a
glance value. **Wrench overlay** (≤8 px) badges localizable findings on their element via
`morphology.yml infirmary.finding_map`; unmapped findings fall through to a generic bed —
no finding is ever silently dropped. **Recovery = the sprite walks home** on the real
DEAD→OK diff (`ev_infra_recovered` chronicle verb); if unwatched, the keyframe diff still
empties the bed (the walk is only played live — no replay lie).

Day-one truth render (doubles as the acceptance fixture): neon + vercel poles sparking
with NEON_API_KEY / VERCEL_API_KEY tags, monday + claude-in-chrome wires in fog, one
purple cap, all other wires taut-dark — matching the live doctor log exactly (§14 #9).

---

## 8. ECONOMY — STRICT COST-VIZ (from `economy.md`; ruling-conformant)

**The ledger (live-verified):** `cabinet:cost:tokens:daily:<date>` per-officer HINCRBY
fields (real: 07-08 totals $28–43/officer) + `cabinet:cost:tokens:<officer>` last-turn
snapshots. Writer: `session-stop.sh` (revived 2026-07-07; hooks dir germline-locked).
**Hard limits rendered around, never hidden:** 48 h TTL (only today + yesterday are real —
"this week" is unrenderable until P-ECO2); estimates at pinned rates (cards say so);
officer-dimension only (no per-mission attribution exists — per-shipment figures would be
fiction); per-turn-at-Stop undercount noted; Captain's own sessions don't draw from the
ledger (codex: "officers' wages only").

**Surfaces (each = the ONE home of its truth, §10 R3):**
| Surface | Truth | Source |
|---|---|---|
| Desk ledger-papers (per officer, cutaway) | that officer's today/yesterday/last-turn spend; stack tier = today's spend (TEXTURE, $15 steps) | daily hash fields + snapshot key |
| Customs House board (quay) | org aggregate today + yesterday; codex verbatim: "Shipping costs are not attributable per shipment — the treasury ledger is kept per officer" | dual-shape sum (dashboard `redis.ts` logic reused) |
| Treasury pin (noticeboard) | latest DAILY 23:00 cost digest (weekly staged behind P-ECO4) | cost-summary cron output |
| Counting table → **Counting-house** | the village's cost-growth beat: anchor now; building earns itself post-P-ECO2 under growth law (§10 R1) | chronicle cost keyframes |
| Portrait-rail cost strip (§9.1) | per-officer today `$X.XX` + 8-px bar normalized to day's max; missing field = grey `—` | daily hash |

Framing: **"wages drawn from the Captain's treasury"** — real spend as wages; rent/salary
fiction REJECTED and omitted everywhere including codex. Zero-data day renders "no wages
drawn yet today" (grey), never $0.00-as-fact. Decorative coinage: `decorative: true`.

**Staged builds:** P-ECO1 (v1b): `/api/world/economy` + the three reader surfaces — pure
readers, no germline. P-ECO2 (v3): census/chronicle keyframe gains `cost_total_micro` +
`cost_by_officer_micro` snapshotted from the daily hash (writer = census cron, NOT the
hook) — durable history begins that day; subsumes the ui-pack rollup-cron proposal (§10
R5). P-ECO3 (v3, **Captain unlock** §14 #3): per-task HINCRBY in session-stop while
`cabinet:active-task:<officer>` is set → real per-shipment manifests. P-ECO4 (v3): OVI
weekly digest gains a cost line → the weekly town notice becomes real.

---

## 9. UI-PACK LAYER (from `ui-pack.md`; killswitch-lever exception ruled)

### 9.1 Portrait bar (hybrid DOM rail — chrome, not world)
Left rail, 4 roster slots, toggleable, collapses to 16-px status dots in ambient mode.
Portrait = pack Portrait-Generator face seeded `fnv1a(officer_id)` (same face forever;
params = manifest + codex rows); talk animation only while the activity verb is <5 min
fresh; interim pre-purchase = head-crop from owned walk sheets (visible placeholder
doctrine). Verb line from `cabinet:officer:activity:<id>` — stale >30 min dims to `idle
since HH:MM`; chronicle `actor:"unknown"` NEVER attributes to a slot. Status ring =
reserved palette dual-coded; **red never** (killswitch-only). Cost strip per §8. Rail
stays out of the world framebuffer (the gate judges the world, not the chrome).

### 9.2 Pixel dialog frames + typography
CSS 9-slice pack frames around DOM card content (pixel shell, legible interior): warm
parchment theme for Harvestholm surfaces, cool slate for Lantern Quay; WHAT/NOW/PROOF
contract untouched. Buttons exist ONLY for: close, page ⟨/⟩, killswitch PULL/ABORT.
Library query dialog [v3] = input row + typewriter results + owned thinking-dots GIF as
loading state; GET-only. Interim own-pixel 16-grid 9-slice (`ui/frame_interim`) unblocks
everything pre-purchase. **Typography two-tier law:** pixel font (monogram CC0, pending
æøå check; fallback m5x7) for short labels ≤24 chars at integer scale only; **DOM mono for
all data-bearing text and EVERY numeral** (cost figures must be unmistakable — strict-cost
ruling); in-canvas world text: none (world IS the chart). Contrast ≥4.5:1 incl. night
tint; one night-tint card render joins the gate goldens.

### 9.3 THE KILLSWITCH LEVER — the ONE actuator (ruling 2026-07-09)
- **Placement (conflict resolved §10 R4):** Great House exterior wall, left of the door,
  lamplit — seat of authority, findable ≤2 s, NOT inside any interior. At far zoom a 6-px
  lever pin renders at the Great House position.
- **Break-through-fog rendering:** lever + pin render ABOVE night tint, weather, red wash,
  occlusion — the one element exempt from lighting passes. State polled (`GET
  cabinet:killswitch`) every tick: the lever renders REAL state, including flips made from
  the shell out-of-band.
- **Two-tap + confirm + cookie:** Tap 1 arms (amber glow, 10 s auto-expire) and opens the
  heavy confirm dialog (the third, unadorned frame — only place it appears): consequence
  copy *"All officer operations halt on their **next tool invocation** — not instantly"*,
  live state as PROOF (`redis GET cabinet:killswitch → (nil)`), PULL (enabled only with
  the captain session cookie; without it the lever is view-only — visitors see truth,
  can't act) / ABORT. Tap 2 PULL → `POST /api/world/killswitch` → shells the existing
  `cabinet/scripts/kill-switch.sh activate` (no new write machinery; the lever is UI sugar
  over the proven script). Release = same ceremony via `deactivate`.
- **Witnessed cause:** the API route emits the chronicle event (`killswitch.pull`, actor
  captain, src world-ui) after a successful shell call; out-of-band shell pulls are
  witnessed by the chronicle daemon observing the key change (no germline touch on the
  script). Lever card shows the last pull's who/when as PROOF.
- **Honest degradation:** if the API call fails, the dialog prints the exact fallback
  command — never a silent failure.
- **Exclusivity:** this is the sole in-world write; its red PULL button is the only red
  interactive element anywhere. Mailbox/noticeboard/library/cargo/poles/beds stay
  read-only (fresh ruling; the v1 addendum's mailbox-view-only carries).

---

## 10. CROSS-TRACK CONFLICT RESOLUTIONS (binding)

| # | Conflict | Resolution |
|---|---|---|
| **R1** | **Growth thresholds vs economy building.** Economy's counting-house tier was drafted off *daily* spend ($50/day t1) — but daily spend is a rate metric, and rate metrics may not mint structure (rate-routing law); a rate-driven building would also flap tiers on quiet days. | Counting-house SHELL tier binds to **cumulative treasury outflow since P-ECO2 landed** (sum of real cost keyframes — monotonic, like `commits_total`; base pinned in the grammar PR, sized so t1 lands within the first week at current ~$150/day volumes; codex: "treasury records begin <date>", never back-filled). **Daily** spend drives TEXTURE only: lit windows, desk stacks, board numbers. Appearance obeys the standard 2-keyframe hysteresis + 24 h crewed scaffold — a real growth beat, lawful. |
| **R2** | **Two competing service-health feeds + two sick-places.** Bestiary proposed cabinet-doctor writing `services-health.json`; infra-viz proposed a census-side `infra` block parsing the doctor log. Bestiary also had a "sick pen beside the barn" while infra-viz built the infirmary yard. | **ONE feed: the census `infra` block (P-INF)** — world-census.py is already the fenced local reader; cabinet-doctor stays untouched (bestiary's sidecar subsumed). **ONE sick-place: the infirmary convalescent yard** — a DEAD service's bed row is occupied by that service's HERD ANIMAL walking from its pen to the yard (bestiary's vet-flag story and infra's admission table become the same witnessed scene); recovery = the animal walks back. Cow health states (grazing/lying/vet-amber) read the same block. |
| **R3** | **Three renderings of the same cost truth.** Growth-grammar's hearth woodpile, economy's customs board, and the counting-house all showed org-level spend. | **Woodpile CUT** (the growth track itself called it a seam). Truth homes: per-officer = desk ledgers (+ rail strip, same number, chrome); org aggregate = Customs House board (harbor) with the treasury pin carrying the 23:00 digest (different truth — final vs live — codex distinguishes); the counting-house becomes the village's *cumulative* home post-P-ECO2 (R1). All cards cross-link siblings (D7). |
| **R4** | **Killswitch lever placement.** ui-pack picked the Great House wall; interiors.md said in passing "it lives at the crossroads". | **Great House exterior wall** (ui-pack's reasoned 3-way pick): authority placement, exterior wall satisfies interiors' real constraint (no interior contains an actuator), and the crossroads is already the mailbox/noticeboard civic cluster — a second high-salience surface there would break the glance budget. Far-zoom pin keeps it findable everywhere. |
| **R5** | **Two durable-cost-history mechanisms.** ui-pack asset #7 proposed a rollup cron harvesting daily hashes; economy proposed chronicle keyframe fields. | **P-ECO2 (chronicle cost keyframes) is the one mechanism** — no new cron, rides the existing census keyframe machinery, durable in the same forever-file the rest of the world trusts. ui-pack #7 is subsumed. |
| **R6** | **Bestiary cows vs services count churn** (Captain's own flag). | Carried as resolved by the bestiary: the fleet IS the herd — manifest row add/remove = animal appears/vanishes, damped by 2-keyframe hysteresis, and every animal's card names its `services.yml` row so churn is attributable in two clicks. "Lying down" dual-codes with a grey zzz-chip so cute never hides a silent-cron warning. |
| **R7** | **Egg vs ratified day-0** (and the always-standing lighthouse). | Egg supersedes (§0 supersessions 1–2); the honest-zero anomaly survives at every scale via the dark cairn → dark tower ladder. Unified §8's "next deltas" list carries with the staged-lighthouse reading. |
| **R8** | **Dual-view registry (D7).** Same truth deliberately visible in two dialects: 5 pack crates (workshop capability-face / warehouse provenance-face); system-self outcomes (quay berth = shipping view / village field plot = husbandry view); per-officer cost (desk ledger / rail strip). | Allowed ONLY with reciprocal codex cross-links ("same 5 packs, seen from the trade side"). Field-plot CROP stages stay aggregate TEXTURE until P2 lands, then mirror the berth stage exactly (never a second number). Registry lives in the grammar PR; binding-validator can't catch semantic double-claims — human review owns this list (also §13 risk #6). |
| **R9** | **Infirmary red-cross lamp vs the 5-item glance budget.** | D6: anomaly lamps preempt the lowest-priority slot when lit (priority order in §4) — the budget stays 5. |
| **R10** | **Bees vs telegraph wires** (two building-to-building line systems). | Distinct by physics and class: wires = static infrastructure STATE (still when healthy); bees = transient event TEXTURE (exist only in flight, cap 4). No shared palette signals; codex on both names the other. |

---

## 11. CONSOLIDATED FEEDS & PLUMBING LEDGER (everything new, one table)

**Runs today with ZERO new plumbing:** SSE presence/verbs/killswitch-state/clock;
chronicle tail + `attrs.lane/outcome` allowlist; census keyframes (all §3 drivers, values
verified 07-08); `outcomes.yml`; grammar status; egg/growth ladder; commute; ceremonies
1/2/5; day/night + seeded weather; v1 isles r0+r1; chicken flock; dog.

| ID | Item | Size | Stage | Notes |
|---|---|---|---|---|
| P1 | `pending_captain_items` int on SSE snapshot | ~½ d | v1a | the only new feed the mailbox needs; source-of-record = §14 #5 |
| P-SITES | `world-sites.jsonl` append-only site ledger (renderer-side) | tiny | v1a | T0 persistence for config-flip quick works; rebuildable |
| P-KS | `POST /api/world/killswitch` → existing `kill-switch.sh` + witness emit | ~½ d | v1b | the ONE actuator; cookie-gated |
| P-ECO1 | `/api/world/economy` reader + 3 surfaces | ~½ d | v1b | pure Redis readers |
| P-INT1 | `captain_rulings_recent` titles in authed snapshot | ~¼ d | v1b | mailbox-card free-text precedent |
| P-INT2 | census `tier2_by_role: {slug: n}` | ~¼ d | v1b | closed roster slugs |
| P2 | emitters stamp `outcome:`/`lane:` into org_events | small, germline window | v2 | allowlist already lifts them |
| P3 | per-lane census block (fenced `git rev-list` per `projects/*.yml`, `ev_*` GROUP BY lane) | ~1 d + validator | v2 | isle r2 + real light-mass health |
| P4 | chronicle salience config | tiny | v2 | v1 uses the fixed 4-kind set |
| P5 | work-graph node-state read (events, never projections) | ~1–2 d | v2 | isle r3 task viz |
| P-A | chronicle lifts probe verdicts → `deploy.verified`/`deploy.rolled_back` | ~½ d | v2 | polads two-signal shipping |
| P-B | stephie row in `probes.yml` | config, Captain merge | v2 | §14 #7 |
| P-INF | census `infra` block (doctor log parse + heartbeat gate + launchctl + liveness keys) + `ev_infra_state_changed/recovered` | ~1 d | v2 | ONE feed for wires, beds, cow health (R2) |
| P-TANK | `embed_queue` XLEN int on snapshot | tiny | v2 | water tank level |
| P6 | GET-only library/product search into cards | ~1 d | v3 | already-ratified path |
| P-ECO2 | chronicle keyframe cost fields (census cron writer) | ~½ d | v3 | durable history begins; counting-house unlock (R1) |
| P-ECO3 | per-task cost HINCRBY in session-stop | small, **germline unlock** | v3 | §14 #3; per-shipment manifests |
| P-ECO4 | OVI weekly digest cost line | small | v3 | weekly town notice |
| P-LAWN | 3 apoptosis census ints | ~10 lines | v3 | lawn state |
| P-BEE | trigger `sender` name in chronicle allowlist | ~5 lines + tests | v3 | point-to-point bees |
| P7 | apoptosis per-kill events | rides that project | v3 | when REPORT_ONLY arms |
| P8 | sensor-fog binding | tiny | v3, **needs ratification** | §14 #4 |

Asset lines: farm animal promotions + cat + water tower + groundskeeper (owned, manifest
rows + gates); bee micro-sprite (the one authored-art line, via gate); pixel font monogram
CC0 (æøå check); interim 9-slice frame (own pixels); **Modern User Interface pack =
$3.90 purchase handback** (§14 #2) — nothing blocks on it.

---

## 12. STAGED BUILD PLAN (per-stage acceptance = harness pass + named gate_cmds)

Common contract for EVERY stage: all new pixels via one grammar-law PR
(morphology/show-grammar v-next, codex on every entry, Captain merge = the door); every
render ships `world.map.json` + `labels.json` + a green `--mechanical` log BEFORE Captain
review; `--full` judge run on final candidates; thresholds never edited.

### v1a — ISLAND + COMMUTE + MAILBOX + EGG-GROWTH CORE
**Scope:** unified continuous island on EXISTS feeds (both district rosters; scene-swap
retirement); commute classifier + 20–30 s walks + thought bubbles; crossroads mailbox
(P1, read-only view); ceremonies 1/2/5/7; day/night + seeded weather; **egg + growth
ladder + three-class routing + visible-work pipeline (P-SITES) + chunked map base**;
staged lighthouse + dark lantern posts; dog. Killswitch renders state (red wash) —
actuation lands v1b, so v1a ships with ZERO actuators (safe default).
**Fixtures:** egg day-0 · day-3 (cottage site mid-RAISING at T0+30 h) · day-30 · today
(real 07-08 keyframe — must reproduce the live island) · dusk money shot.
**Acceptance — all green:**
```
cd cabinet/dashboard && npm test                                   # vitest world suites (growth/grammar/director/…)
python3.12 -m pytest framework/tests -q                            # framework suite stays green
python3.12 -m pytest cabinet/scripts/world-aesthetic/tests -q      # gate self-tests
python3.12 cabinet/scripts/world-binding-validator.py              # every entity kind has codex|decorative
python3.12 cabinet/scripts/world-asset-gate.py                     # manifest/asset gate
python3.12 cabinet/scripts/world-aesthetic/world-aesthetic-gate.py --mechanical \
  --map <fixture>.map.json --render <fixture>.png --labels <fixture>.labels.json
                                                                   # × each fixture above, day AND dusk
```
Plus: determinism replay check (same state + tick ⇒ byte-identical frame, two runs) and
the commute classifier simulated over a recorded chronicle window (no ping-pong: switch
rule 0.6 share / 2 evals / 180 s dwell holds).

### v1b — INTERIORS + INSPECT + UI BAR (+ the lever)
**Scope:** universal single-active cutaway (needs doctrine amendment merged, §14 #1); 4
flagship truth-rooms + cottage v1; universal clickability + catch-all + coverage gauge +
validator ratchet; portrait rail (interim head-crops) + pixel dialog frames (interim
9-slice) + typography law; **killswitch lever** (P-KS — the ONE actuator); economy readers
(P-ECO1: desk ledgers, customs board, treasury pin, counting-table anchor); P-INT1/2.
**Fixtures:** cutaway-open frame (roof-hole + dense room + live world — new gate
territory); night-tint card golden; lever armed-state frame.
**Acceptance:** the six commands above (gate run on the cutaway-open + night-card
fixtures), plus: lever end-to-end on a dev instance — arm → PULL → `cabinet:killswitch`
active → red wash + thrown pose → release; view-only without cookie verified; API-fail
path prints the fallback command; chronicle witness event present. Coverage chip ≥
baseline and validator errors on any uncodexed entity kind.

### v2 — ISLANDS FAR + DISTRICTS + TASK VIZ + INFRA LAYER
**Scope:** archipelago canvas + anchors + LOD ×1/2 + ×1/4 + fog/buoys + reef-buoy;
two-signal shipping on polads (P-A) with at-anchor + turned-back ceremonies (8/9 + ring
raisings); keyframe-confirm shipping on stephie (honest codex; P-B when Captain calls);
isle r2 towns (P2 + P3) + r3 work-graph task lots (P5); salience config (P4); **infra
layer** (P-INF: switchboard hut, poles/wires, infirmary + yard, wrench overlays, recovery
walks); bestiary v2 subset (chickens, water tank P-TANK, cat, cow health via P-INF, Day-1
bees).
**Fixtures:** archipelago ×1 AND ×1/4, day AND dusk (open-water ≲30% rule at LOD); the
infra day-one truth render (neon+vercel sparking / monday+chrome fog / one purple cap —
must match the live doctor log); ship-at-anchor night frame.
**Acceptance:** the six commands (gate on all four archipelago frames + infra frame);
ship-phase determinism test (position = pure f(two real timestamps + tick)); infra parse
test against the live 344-line doctor log (unknown line shapes ⇒ grey, never green);
pairwise anchor spacing asserted in vitest (no tier-7 collision).

### v3 — LIBRARY QUERIES + ECONOMY FULL + BESTIARY FULL
**Scope:** GET-only library search in Library card + isle annexes (P6) with pack/interim
dialog UI; economy full (P-ECO2 durable keyframes → counting-house per R1; P-ECO3 per-task
manifests if Captain unlocks; P-ECO4 weekly notice); bestiary full (P-LAWN lawn state,
P-BEE point-to-point bees, portrait-generator faces post-purchase); P7/P8 as they ratify.
**Fixtures:** library-query card (loading + results states); counting-house t1 keyframe
fixture (2-keyframe hysteresis proven on synthetic keyframes); lawn shaggy-vs-mown pair.
**Acceptance:** the six commands; library round-trip is GET-only (no mutating verbs in the
network trace); counting-house tier tests pinned against synthetic cost keyframes
(monotonic cumulative, no backfill before the P-ECO2 landing date); every new $ surface's
card cites its exact Redis key/keyframe field (spot-check harness in vitest).

---

## 13. HONEST-RISK REGISTER

1. **Gate risk on new compositions.** Egg (forest-heavy: canopy dominant-share), cutaway-
   open frames (dense room + roof hole), archipelago LOD (mostly water) are all NEW gate
   territory. Budgeted mitigations are in each section (≥45% clearing+water in egg frames,
   3-pass everything, water ≲30%, prop clusters) — but expect composition iterations.
   Law: fix composition, never thresholds.
2. **Doctor-log parse fragility (P-INF).** The infra feed parses a text log (stable format
   today, 344 lines, but a doctor wording change silently breaks states). Mitigation:
   parse is contract-tested against the live log in CI; unknown line shapes degrade to
   grey "unmeasured" (fail-closed to honesty, never to green); heartbeat staleness gate
   catches a dead doctor entirely.
3. **Cost-ledger truth limits are permanent until staged items land.** 48 h TTL means no
   history before P-ECO2's landing day, ever (no backfill — by design); per-shipment cost
   stays honestly unattributable unless the Captain unlocks P-ECO3; the hook prices
   last-entry-per-Stop (small undercount, codexed). The world renders these limits rather
   than papering over them — expect Captain-visible "grey" until the plumbing earns color.
4. **Classifier ping-pong / commute noise.** Hysteresis parameters (0.6 / 2 evals / 180 s)
   are designed, not field-proven. v1a acceptance replays a recorded chronicle window
   before walks go live; parameters are grammar-PR constants if retuning is needed.
5. **world-sites.jsonl is renderer-side state.** For config-flip quick works, T0 =
   first-seen (not the true flip instant); if the ledger is lost, sites re-witness at next
   snapshot with a new T0. Replay of those sites is faithful to *observation*, not to the
   flip — codex on site signs says so. Chronicle- and keyframe-witnessed works are immune.
6. **Semantic double-claims are human-reviewed, not machine-caught.** The binding-
   validator proves coverage, not uniqueness — the D7/R8 dual-view registry is enforced
   only by grammar-PR review. Risk: a future track silently double-binds a field (the
   water-tank-vs-library case caught this wave). Registry review is a standing PR
   checklist line.
7. **Egg ↔ island ↔ archipelago coordinate reconciliation.** The egg tile plan, the 60×48
   core, and the (90,8) archipelago offset were authored by three tracks; layout_fold says
   nothing moves, but no single canonical anchor table exists yet. v1a's first task emits
   one (extending `archipelago-positions.json`) and the day-0→today fixture pair proves
   anchors coincide. Until then treat all absolute tile coords as draft.
8. **Performance at archipelago scale is unproven.** 240×192 canvas + chunked base +
   LOD aggregation is designed O(built), but the dashboard has never rendered ×1/4 frames.
   v2 acceptance adds a frame-time smoke (no budget number pinned yet — measure first).
9. **Killswitch lever copy vs reality drift.** Halt semantics are "next tool invocation,
   not instantly" — if kill-switch.sh semantics ever change, the dialog copy must change
   in the same PR (Docs-track-the-code rule applies to consequence copy).
10. **Pack purchase is deferred-cosmetic, not blocking — but two surfaces stay visibly
    interim** (head-crop portraits, hand-drawn frame) until $3.90 is spent. Deliberate
    (placeholder doctrine), flagged so nobody mistakes interim art for the end state.
11. **Chick/bee TTL semantics can visually lag reality** (a fast subagent's chick lingers
    ~60 ticks). Codex states TTL outright; accepted as the price of rate-legal liveness.
12. **Field-plot/berth dual-view could still read as double-counting** to a fresh viewer
    even with cross-linked codex (R8). If Captain gallery feedback confirms, the fallback
    is pre-agreed: field plots become existence-only (no stage mirroring).

---

## 14. OPEN CAPTAIN CALLS

1. **Doctrine amendment (blocks v1b interiors):** merge the D3 line — "at most ONE
   interior open at a time, any bound building" (replaces "ONE interior = the wardroom").
   One line in the grammar-law PR; same spirit, universal scope.
2. **$3.90 purchase (non-blocking):** LimeZu *Modern User Interface* pack — confirmed
   ABSENT from `~/Downloads` (re-verified 2026-07-09; only the small
   `4_User_Interface_Elements` subset inside moderninteriors-win is owned). On 35% sale
   (reg $6) at limezu.itch.io/modernuserinterface. Buys: window frames, 42 buttons, the
   animated Portrait Generator. Everything ships with interim art without it.
3. **P-ECO3 germline unlock (v3):** per-task cost HINCRBY in `session-stop.sh` (hooks dir
   is germline-locked) → real per-shipment cost manifests at the harbor. Proposal only
   until the unlock window.
4. **P8 sensor-fog ratification (carried from v1):** promote weather's single honest
   binding (fog onshore when the chronicle is stale >2 d) — or keep weather purely
   decorative forever.
5. **P1 source of record (carried, blocks v1a mailbox):** which store E0b counts for
   `pending_captain_items` — dashboard decision-queue or the Chair's binder queue (one
   truth, one place; pick ONE).
6. **`sensed` lane geography:** default = no isle, codex on the mist; alternative = a
   drift-net buoy field in v2 bound to stream items sensed. Default stands until ruled.
7. **P-B timing:** adding the stephie row to `probes.yml` changes what the world can
   honestly claim — Captain merges it like grammar, when stephie's cards carry
   deploy-shaped chains.
8. **Retired-lane render (carried):** reef-buoy at the stepnetwork anchor acceptable, or
   remove retired lanes from the map entirely?
9. **Two real findings worth fixing, not rendering:** NEON_API_KEY and VERCEL_API_KEY are
   genuinely unresolved in `cabinet/.env` (today's sparking poles). Fixing them gives the
   world its first honest recovery-walk — and greener infrastructure either way.

---
*Sources: `world-unified/unified-spec.md` (v1, ratified 7.5) · `world-next/{archipelago,
growth-grammar,egg-tile-plan,interiors,bestiary,infra-viz,economy,ui-pack}.md` ·
`archipelago-positions.json` · live-estate verifications 2026-07-08/09 (read-only).
Gate scripts verified on disk: `world-aesthetic-gate.py`, `world-asset-gate.py`,
`world-binding-validator.py`; test suites: `cabinet/dashboard` vitest, `framework/tests`,
`cabinet/scripts/world-aesthetic/tests`.*

---

## 15. CAPTAIN ADDENDA INTEGRATION (2026-07-09, post-synthesis — BINDING; where this section contradicts §0–14, THIS section wins)

Three binding Captain addenda landed after §0–14 were synthesized
(`world-next/captain-addendum-{growth-npcs,2-balance,3-uipack}.md`). Integrated here verbatim-in-effect:

### 15.1 Universal growth-ladder principle (addendum 1.1)
**No bound element spawns at final size — every one has a natural, VISIBLE growth ladder.**
Canonical instantiation (water tank = memory/context reservoir): empty bucket → bucket with
water → several buckets → barrel → water tank → tank cluster/tower. The same ladder thinking
applies to ALL bound elements: flagpole (bare pole → pennant → flag → crested flag) · library
(shelf → bookcase → room → wing) · workshop (toolbox → bench → hut → hall) · berths (mooring
post → jetty → berth → double berth) · counting-house (papers on desk → strongbox → building)
· lighthouse (unlit frame → built-unlit → LIT at first graduation) · roads (trampled grass →
dirt → gravel → cobble by real foot-traffic) · hospital (first-aid chest → tent → infirmary).
Ladders bind to the RATIFIED tier mechanics (log2 tiers, cadence-justified bases, hysteresis).
**The §3/§4 element tables are hereby read with this ladder column implied**; the grammar-law
PR (v1a) writes every ladder out explicitly in `growth-ladders.yml` (15.3). The triptych egg
render shows the t0 bucket (not a tank) accordingly.

### 15.2 Two-axis growth model: ERA × RUNG (addendum 2.1 — balance made structural)
- **ERA (global aesthetic vocabulary):** ONE org-maturity index — a weighted basket of real
  metrics (org age, total events, outcomes achieved, graduations, active lanes) — gates WHICH
  vocabulary everything uses: campfire/tent/torch/dirt era → lantern/cottage/gravel era →
  streetlight/townhouse/cobble era → beyond-the-bay era (reclaimed land, second pier, hillside
  terraces). Everything shares one era ⇒ the world always reads coherent (torches before
  streetlights; tent before house; never medieval-village-next-to-modern-harbor). Era advance
  = the true "grown far beyond the bay" moment, real by construction. Hysteresis applies to
  era transitions too (no era flapping).
- **RUNG (per-element magnitude):** within the current era, each element's size/count tracks
  its OWN real metric on the ratified log2+hysteresis tiers. Tent→house = era; house→bigger-
  house = rung. §3.4's era arc (EGG → … → ARCHIPELAGO) is the ERA axis; §3.2's class table
  and every §3/§4 driver stay the RUNG axis.

### 15.3 Captain-tunable growth as DATA: `cabinet/world/growth-ladders.yml` (addendum 2.3)
All ladders, era baskets, weights, thresholds live in **`cabinet/world/growth-ladders.yml`**
— same law-family as morphology/show-grammar (versioned, schema-validated, NO auto-merge for
schema changes; VALUE edits are Captain-editable directly), hot-reloaded by the renderer,
world-data class (never germlined). Schema sketch:
```yaml
schema: cabinet.world.growth-ladders/v1
era:
  basket:            # weighted real metrics -> one maturity index (weights sum 1.0)
    org_age_days: {weight: 0.15}
    org_events_total: {weight: 0.25, curve: log10}
    outcomes_achieved: {weight: 0.25}
    cells_graduated: {weight: 0.20}
    active_lanes: {weight: 0.15}
  thresholds: {camp: 0.0, hamlet: 0.25, town: 0.55, beyond_bay: 0.8}   # + 2-keyframe hysteresis
ladders:
  water_tank:
    metric: memory_embed_queue_xlen        # MUST cite a real census/snapshot field (validator-enforced)
    rungs: [bucket_empty, bucket_full, buckets_3, barrel, tank, tank_tower]
    base: 64                               # log2 tier base — cadence-justified, grammar-PR constant
```
Validator refuses malformed/untruthful configs (every rung metric must cite a real field).
Ships with a preview tool — `world-preview --maturity <index|date>` (or `/world?preview=` dev
param) — so the Captain tunes values → sees stills → commits, no orchestrator in the loop.

### 15.4 Calibration BEFORE build (addendum 2.2 — REQUIRED gate before v1a growth ships)
A calibration harness REPLAYS the org's real history (137k+ org_events, census keyframes,
chronicle, outcomes ledger) through candidate era-basket weights + rung curves and renders a
week-by-week timelapse strip of how the world WOULD have grown. Judged on: story readability
(visible progress most weeks, no dead months, no everything-jumps-at-once days), era
transitions landing at genuinely meaningful moments, egg not outgrown too fast, current-day
render matching felt maturity. Ledger row **WORLD-GROWTH-CALIBRATION** carries this as a
REQUIRED deliverable gating v1a's growth core.

### 15.5 Population law: real actors only; fauna for joy (addendum 1.2 — orchestrator call, reversible)
- **FAUNA freely allowed** as joy-honest ambience (fly-by birds, butterflies, the pettable
  cat/dog, fish jumping at the quay) — each answers inspect honestly: "carries no data —
  exists for joy". Seeded/deterministic like everything.
- **HUMAN-SHAPED SPRITES = REAL ACTORS ONLY.** Officers = named residents. **Subagents render
  as small transient APPRENTICE figures** near their spawning officer's workplace for the
  duration of their real run (they ARE real actors) — adopted per the addendum's
  recommendation; **this supersedes the bestiary's chick-per-subagent event mapping** (§6
  chicken row): the chicken flock demotes to coop-yard FAUNA (honest "carries no data" card),
  the `ev_subagent_completed` tier + live `tool.call[Agent]`/`crew.completed` bindings move to
  the apprentice figures. Reversible if Captain gallery feedback prefers the chicks.
- Transient real externals (inbound webhook/packet-boat courier, the Captain if ever rendered)
  may appear briefly at dock/mailbox — because they are real. **NO fictional villagers/
  shopkeepers/extras, ever** — a stranger in town implies an agent that doesn't exist. The
  town's soul = fauna + weather + light + the REAL population working; never crowd-fill.
- §3.3's construction-crew "wright" sprites remain as ruled there: decorative-honest STAGING
  of a real witnessed transition, codex says exactly that (the addendum's legibility law is
  about implied *residents*; site crews are scenery of a real event, not implied agents).

### 15.6 UI pack ON-DISK — purchase handback VOID (addendum 3; supersedes §11 asset line, §14 call #2, risk #10)
`~/Downloads/modernuserinterface-win/` landed 2026-07-09 07:05 — Modern UI in THREE scales
(16x16 / 32x32 / 48x48: Modern_UI_Style sheets, buttons, gamepad glyphs, Animated variants,
Portrait_Generator piece sets) + `~/Downloads/Portrait Generator 1.5.0 Linux Build/Portrait
Pieces/` raw part PNGs (the Linux app itself CANNOT run on macOS and MUST NOT be executed —
irrelevant: the raw pieces compose directly with PIL, same pattern as the character sprites).
Consequences: (a) **§14 open call #2 is RESOLVED** — asset status ON-DISK; install rides the
world-asset-install pattern (copy → manifest rows → `world-asset-gate.py` GREEN; binaries
gitignored per license); (b) **officer portraits for the rail are buildable NOW** —
deterministic per-officer composition from Portrait Pieces seeded `fnv1a(slug)`, rendered once
at build, manifest'd as derived assets with provenance (§9.1's interim head-crop stage may be
skipped if the composed portraits land first); (c) canonical scales: **32x32 for in-world
dialogs**, 16x16 for in-map micro-labels, never mix scales inside one dialog; (d) killswitch
confirm dialog + inspect-card frames + library query box all use these frames (in-world feel,
not DOM-modern). §9.2's interim 9-slice remains the fallback only if install lags the build.

---
*§15 sources: `world-next/captain-addendum-growth-npcs.md` · `captain-addendum-2-balance.md` ·
`captain-addendum-3-uipack.md` · `~/Downloads` re-verified 2026-07-09 07:26.*

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
