# CABINET WORLD — THE HATCHING
## In-world onboarding · genesis as a place you row into · 2026-07-09

**What this is.** The design of record for **WORLD-ONBOARDING-V1B**: onboarding a brand-new
Cabinet deployment happens **inside the world**, joyfully, instead of across Terminal +
dashboard + hand-edited files. Captain-ratified direction 2026-07-09: *onboarding should
happen as much as possible INSIDE the world; this is the sanctioned first write-surface.*

**Binding doctrine (not negotiable in this doc):**

- **World-writes are CAPTAIN-identity only, config-plane only**, routed through the
  EXISTING validated pipeline — the cabinet-init answers schema
  (`instance/config/cabinet-init.answers.yml`) consumed by
  `cabinet/scripts/generate-instance.py` (path-jailed to `instance/`, secret-shape refusal,
  marker-checked overwrites, end-of-run YAML validation) — **never org-runtime state**.
  The one addition this design makes to the write plane is the **append-only
  `cabinet/.env` secret drop** (backup-first, never echoed), specified in §6.
- **Every world-write is echoed to the decisions/needs ledger**
  (`append-interface.sh captain-decisions`, names-not-values).
- **The killswitch lever remains the ONLY in-world org-state actuator** (spec v2 §9.3,
  ruling 2026-07-09). The Hatching starts no officer, loads no launchd job, flips no
  posture. Org activation stays in the Captain's own LOCAL launcher process — a native
  Launch dialog (or the Terminal-fallback ENTER), never HTTP (§1 Act II, §5, §6.4).
- **External-by-nature steps** (BotFather token creation, TCC permission clicks,
  `launchctl` where the local launcher owns it, sudo/germline until **GOV-UNLOCK-UX**
  ships) are
  framed as in-world **errands** — narrative continuity **without lying about where the
  action happens** (§3).
- Everything visual obeys the world law stack: morphology/show-grammar as the only path to
  pixels (grammar-law PR, Captain merge), deterministic seeded rendering, honest zeros,
  reserved salience palette, aesthetic gate on every render, D6 glance budget, §15.5
  population law (the Captain rendered briefly at dock/mailbox is explicitly sanctioned —
  a real transient external).

**Read-first sources:** `.claude/skills/cabinet-init/SKILL.md` (interview phases + answers
schema) · `cabinet/scripts/generate-instance.py` (generated set, markers, idempotency,
`--adopt`) · `docs/plans/world-unified-spec-v2-2026-07-09.md` (THE ONE SPEC: egg §3.1,
growth ladders §15.1–15.4, UI layer §9, mailbox rulings, lever §9.3) ·
`docs/runbooks/mini-hatch-tonight-2026-07-07.md` (the real activation steps + rehearsal
stalls this flow must cover) · GENESIS ledger rows **ONBOARD-1/ONBOARD-2**
(`docs/plans/operative-egg-ledger-2026-07-07.yml`: genesis re-sequence
**connect → focus → onboard → org PROPOSES outcomes**; interview seed-outcomes superseded;
onboarding web-research brief → Library at genesis).

---

## 0. THE HATCHING WINDOW — one definition everything hangs on

**Hatching mode** is the bounded genesis window of a deployment:

```
OPEN   = genesis incomplete, decided SERVER-SIDE, scoped to THIS INSTALL
         (root + namespace — §10.1):
         instance/config/genesis.stamp ABSENT in this root
         AND org-reality check agrees FOR THIS CABINET (no seeded roster rows
         in this install, no live launchd job under this cabinet's label
         prefix, no ratified outcomes carrying THIS CABINET_ID)
CLOSED = genesis.stamp present OR org-reality says a cabinet already lives
         in THIS root
```

(Per-install scoping is load-bearing on a multi-cabinet Mac, §10: another cabinet
living elsewhere on the machine neither BLOCKS a fresh hatch in a new root, nor can
a fresh root ever REOPEN an existing cabinet's closed window.)

While OPEN, and only while OPEN, the dashboard serves the hatching UI and the
`/api/hatch/*` captain-write endpoints (§6). When CLOSED, every hatching route returns
**410 GONE permanently** and the world is exactly the ratified living world: read-only +
the lever. `?hatching` in the URL is a cosmetic deep-link hint, **never trusted** — mode is
server-decided on every request. Deleting the stamp on a live cabinet does NOT reopen
hatching (the org-reality check is a second independent gate).

Two scoped law amendments apply INSIDE the window and die with it (both ride the
grammar-law PR; see §8 self-review for why they are lawful):

- **H-1 (hatching tempo).** Interview-consequence quick works run their full
  CLEARING→RAISING→FINISHING→REVEAL pipeline **compressed to 10–20 s** (the witness record
  is the Captain's answer itself; sites are pure `f(T0, now_tick)` as always — only `D` is
  shorter). Post-genesis, lawful tempos (15/90 min, 24 h) apply forever.
- **H-2 (hatching buttons).** The ui-pack button law ("ONLY close / page / killswitch
  PULL-ABORT") gains a hatching-scoped set inside hatching dialogs: `Next / Back / Sign /
  Send / Validate`. These button kinds are unreachable outside the window by construction
  (their dialogs only exist on hatching routes).

---

## 1. ARRIVAL — Hatch Cabinet.app and the rowboat

**Captain amendment 2026-07-09 (binding; supersedes the earlier one-command contract):
NO Terminal at all on the stranger path.** The bootstrap is a double-clickable macOS
launcher. The Terminal path (`git clone … && ./hatch.sh`) remains as a **documented
fallback for technical captains only** — same engine, second face.

### 1.1 What must precede the world (honest floor — a double-click, not a command)

Cannot be automated away, enumerated exactly:

| # | Precondition | Why it cannot be inside the launcher |
|---|---|---|
| 1 | A Mac: macOS 14+ on Apple Silicon, logged-in user session, network | the org lives in launchd **user** agents (mini-hatch §0) |
| 2 | The download: a zip containing **Hatch Cabinet.app**. The repo tree rides INSIDE the app as a **bundled payload**, so this path needs NO git auth, no gh login, no clone | someone must hand the captain the zip (link / AirDrop); distribution happens off-machine. (The Terminal fallback still needs repo access — `gh auth login` — honestly noted there, not hidden) |
| 3 | Gatekeeper passage, v1b: **right-click → Open → Open**, once. The app is unsigned in v1b; the download page documents the two clicks with a picture. A signed + notarized build removes this step and is a **commercialization-lane item** (requires an Apple Developer certificate; deferred with that lane, per standing ruling) | macOS policy on unsigned apps; only Apple's cert process removes the ceremony |
| 4 | At most ONE admin-password prompt — the native macOS auth dialog (`osascript … with administrator privileges`), and only if Homebrew is absent | Homebrew's installer requires it. Nothing else in the hatch asks for admin — germline locking is deliberately NOT part of the hatch (§3 E7) |

**The Terminal surface of the stranger path: zero commands, zero ENTER, zero typing**
(the watchword is typed in the browser, §1.2 Act I step 6).

### 1.2 Hatch Cabinet.app — a native wrapper around ONE engine

The .app (Platypus-style shell script applet or a minimal SwiftUI wrapper; v1b may be an
osascript-driven applet — smallest thing that works) bundles the repo payload and drives
**`hatch.sh`, the engine** (new script, repo root; v1b build artifact). One engine, two
faces: `hatch.sh --ui native` when the app drives it (progress + prompts as native
dialogs), plain stdin/stdout on the Terminal fallback. **No logic forks** — the app
renders progress; the engine does the work; every step is identical underneath.

**Act I — make the sea (double-click → browser; silent bootstrap, minimal native
progress dialog):**

1. **DETECTION FIRST (Captain amendment 2 — §10.1)**: the app scans for existing
   cabinets on this Mac — the machine registry `~/.cabinet/registry.json` plus a
   launchd label scan (`launchctl print gui/$(id -u)` for `com.cabinet.*`) to catch
   pre-registry installs. If ANY exist, the app opens THEIR world (one cabinet ⇒
   straight to its dashboard; several ⇒ a native chooser listing the islands by
   name) and offers **"Hatch a new cabinet…"** as an explicit choice on the same
   dialog — never the default, never hidden. An unregistered existing cabinet is
   offered registration first (read-only inspection of its `instance/config` + one
   registry row; the cabinet itself untouched). Re-hatching an existing install is
   impossible from the app AND from its server (§0 gates — two independent layers).
2. On "Hatch a new cabinet" (or a genuinely empty Mac): unpack the bundled payload to
   the registry-allocated root `~/CaptainsCabinet/<slug>/captains-cabinet` (the slug
   arrives at the signpost, §1.3/§10.2 — until then a staging dir; first cabinet on a
   clean Mac may default `main`). Terminal fallback: the existing clone IS the
   install, registered as-is.
3. **Self-record**: the engine re-execs under
   `script -q ~/hatch-logs/hatch-$(date +%Y%m%d-%H%M%S).typescript` — the flight-recorder
   rule (mini-hatch runbook) is structural, not remembered; the typescript is
   ORG-SENSES-1's seed ingest.
4. Dependency checks/installs behind the native progress dialog: Homebrew if missing
   (the one admin prompt), then `brew install git node gh jq tmux redis gettext
   python@3.12`, `python3.12 -m pip install pytest pyyaml`,
   `npm i -g @anthropic-ai/claude-code`, `brew services start redis` (AOF) — exactly the
   mini-hatch §0 floor, idempotent — then `bash cabinet/scripts/setup-mac.sh &&
   setup-mac.sh --check` (exit 0 required — the existing host gate, not a new one).
   **Failure UX**: on any failed step the dialog names the step and its one-line cause
   and offers **Retry / Copy details** — it never dumps the captain into Terminal; the
   typescript holds the full record for whoever helps.
5. Dashboard up: `npm ci` + build in `cabinet/dashboard`, then start **bound to
   `127.0.0.1`** on the configured port (default 3000). Localhost bind is a security
   invariant (§6), asserted at startup, not a default someone can drift.
6. Mint `DASHBOARD_PASSWORD` into `cabinet/.env` (chmod 600) if absent and show it ONCE
   in a native dialog with a Copy button — **"the harbor watchword"** (v1b: the Captain
   pastes it once at `/login` in the browser; v2 upgrade: a one-time login URL minted by
   the launcher and exchanged server-side for the session cookie — zero typing).
7. Open the browser at `http://127.0.0.1:<port>/world?hatching`. Act I is done; nothing
   org-shaped has started.

**Act II — the wheel (a NATIVE dialog; same security property as the old stdin gate):**
the launcher stays resident (v1b: a small progress/status window is enough):

> *The world is in your browser. When it hands you the Launch Warrant, the wheel will
> knock here.*

It watches the **filesystem** (never HTTP) for `instance/config/.genesis-ready` (written
server-side at charter countersign + required errands green, §2.6/§3) and only then
presents the native **Launch dialog** — *"Raise the officers?"* **Cancel / RAISE**. The
click is an OS-level UI event inside the Captain's own local launcher process: web
content cannot click it, the dashboard server cannot trigger it, and it does not exist
until genesis-ready does. (Terminal fallback: the same gate is a blocking stdin ENTER.)
On RAISE the engine runs exactly the mini-hatch runbook, mechanized (§5): proof gates
P-a/P-b/P-c, the P-d revocation drill choreographed with the lever,
`bootstrap-roles.sh --roster`, `load-preset.sh`, `deploy-mac.sh --officer cos`,
`generate-plists.py` + `plutil -lint` + `launchctl bootstrap` of the measurement plane,
`cabinet-doctor.sh` as the final acceptance gate — each step appending a line to
`shared/interfaces/hatch-status.jsonl` (append-only, names-not-values) that the world
tails read-only for choreography (§5). On doctor GREEN it writes
`instance/config/genesis.stamp` and the window closes.

**Failure honesty:** any red gate stops Act II with the exact failing command and the
runbook's own words (P-a red = "the tree leaks personal state — file it upstream, do not
patch here"), shown in the native dialog with **Copy details** — never a Terminal dump.
The world renders the stall as a storm-lamp on the jetty with the same text
(WHAT/NOW/PROOF card, PROOF = the typescript path + failing command). No silent retries.

### 1.3 The rowboat arrival (first render in hatching mode)

Deterministic, seeded, ~20 s, skippable with a tap. Dusk sea. A rowboat enters from the
south edge and crosses at the fixed 0.5 s/tile lane physics to the jetty of the **egg
islet** (spec v2 §3.1 / `egg-tile-plan.md`: R=24 forested islet, 20×14 cleared heart, one
cottage, bare flagpole, mailbox flag-down, dirt path, rowboat jetty, dark lantern-cairn).
A lantern-lit figure — **the Captain; §15.5 sanctions a transient real external at
dock/mailbox, and no one is more real here** — steps onto the jetty head, where a bare
signpost waits. **The first exchange happens right there, on landing (Captain amendment
2, §10.2): "What will you call this island?"** The island's name IS the cabinet's name:
a wright carves it into the signpost on the spot, the machine registry allocates this
cabinet's namespaces from it, and the rowboat's transom takes the slug. Then the figure
walks the path to the cottage door; the camera follows; the door opens; the roof fades
(the v1b cutaway, single-active); inside: a writing desk, a candle, the first parchment
dialog frame (32×32 pack frames, Harvestholm theme, typewriter text, DOM mono for every
datum — spec v2 §9.2 / §15.6). The interview begins where the org will live.

Codex on the arriving figure: *"You. The only human this world will ever render."* The
sprite retires when the interview opens; the Captain is never a resident avatar.

---

## 2. THE INTERVIEW AT THE DESK

### 2.1 Sequencing — the genesis re-sequence honored

GENESIS ruling (ONBOARD-1, Captain 2026-07-07): **connect → focus → onboard → org PROPOSES
outcomes.** The desk interview maps onto it with the org's *shape* as phase 0:

```
SHAPE   (§2.2–2.4: who/what/how — profile, lanes, org shape, posture axes)
CONNECT (§2.5 + §3: integrations declared at the desk; keys fetched as errands,
         validated live at the telegraph pole)
SIGN    (§2.6: the Charter — answers.yml committed, generate-instance.py runs)
FOCUS   (§4: the first letter at the mailbox = ONBOARD-1 input)
RAISE   (§5: the wheel knocks — the launcher's native RAISE click; officers
         arrive on real state)
ONBOARD (post-hatch, org-side: the org explores its estate; ONBOARD-2 web-research
         company/market/product brief → Library)
PROPOSE (the org PROPOSES outcomes → return letters → Captain ratifies on the
         existing surfaces; §4.3)
```

**What the re-sequence REMOVES from the interview:** the entire SKILL.md **phase 5 (seed
outcomes)** — no outcome interviewing, no `outcomes.yml.draft` staging at init. An egg has
no outcomes; it has a **focus**. The org earns its outcome proposals by exploring first
(gather-then-decide, made organizational). The interview asks **zero** "what should the
org achieve" questions; the first letter (§4) carries intent instead.

### 2.2 The mapping law

Every cabinet-init question becomes a desk exchange with a **visible consequence** in the
clearing — a real render of the real config value it wrote (WHAT/NOW/PROOF card cites the
generated file), era-appropriate per the growth ladders (§15.1–15.2: egg era vocabulary —
carved wood, rope, stakes, barrels, a single wire; never streetlights next to a tent).
Consequences run as H-1 compressed quick works: a "wright" sprite (decorative-honest
staging, codex says exactly that) walks out and does the work while the Captain watches.
All new props enter via manifest rows + asset gate + the grammar-law PR like everything
else. **None of these props mint capability**: they render *declared config*, each card
honest that nothing is active yet ("declared, not yet alive — contexts ship
`active: false`").

### 2.3 The full question map (every SKILL.md phase-1..4 + 6 field)

| # | cabinet-init question (answers.yml key) | Desk exchange | VISIBLE consequence (egg-era form) | PROOF on the card |
|---|---|---|---|---|
| 1 | Captain name (`captain.name`) | "What name do your officers know you by?" | **The door lintel**: a wright carves *"‹Name›'s cabinet"* above the Great House door (the signpost belongs to the ISLAND's name — §1.3/§10.2) | `platform.yml captain_name` (via `framework.env.captain_name()`) |
| 2 | Timezone (`captain.timezone`) | "Where does your sun rise?" — picker seeded from the browser's IANA zone, confirmed not assumed | **The sun finds your sky**: the day/night sky clock snaps to the Captain's local hour, visibly wheeling to position | `platform.yml captain_timezone`; sky-clock binding (v1a) |
| 3 | Telegram chat id (`captain.telegram_chat_id`) | NOT asked as a number. Deferred to errand E1's return leg: after the bot token validates, the world says "send your new bot any word" and captures the chat id from that first message (§3 E1) | **The mailbox gets its address plate** (small brass strip on the post) | `platform.yml captain_telegram_chat_id` (an address, never a secret) |
| 4 | Cabinet id + mode (`cabinet.id`, `cabinet.mode`) | Already answered AT THE SIGNPOST on landing (§1.3): island name → display name; slug (generator `SLUG_RE`, reserved-ids + registry-uniqueness checked) → `cabinet.id`. The desk only CONFIRMS it. Mode: auto-`multi` when the registry already holds another cabinet (§10.2) | **The signpost** carries the island name; **the rowboat's transom** takes the slug | `answers.yml cabinet.id`; registry row (§10.1); multi mode queues the `CABINET_MODE`/`CABINET_ID` .env appends (§6.2) |
| 5 | Officer model (`cabinet.officer_model`) | One confirm, default shown | Card-only (no prop — a model string is not a place) | `roster.yml model:` stamp |
| 6 | Lanes: name + slug (`lanes[].name/slug`) | "Name the waters you work." One exchange per lane | **A claim is staked at sea**: a barrel-buoy drops at the lane's archipelago fan bearing (spec v2 §2.2 — anchors are morphology law, fixed at birth) + a shore stake with the slug; mist stays over the slot. Codex: *"staked, not earned — no outcome has ever landed here"* | `contexts/<slug>.yml` (`active: false`), `archipelago-positions.json` slot |
| 7 | Lanes: repos (`lanes[].repos`) | "Which holds carry its cargo?" | **The cargo manifest**: a paper nailed to the jetty head listing repo names per lane | `projects/<slug>.yml product.repo` |
| 8 | Lanes: task system + boards (`lanes[].task_system/boards`) | "Where is its work tallied?" | Lines added to the same jetty manifest (board ids as NAMES/ids, plugin routes noted) | `projects/<slug>.yml` tasks block / deliberate-absence comment |
| 9 | Lanes: infra NAMES (`lanes[].neon_project/vercel_project`, linear keys) | "Name — never keys — its stores and piers." Input refuses secret shapes live (§6.4) | Manifest lines (NAMES only) | `projects/<slug>.yml` neon/vercel NAME fields |
| 10 | Org shape (`cabinet.org_shape`) | "One Chair with lane consultants (portfolio), the classic five (functional), or your own charter (custom)?" — recommendation logic verbatim from SKILL.md | **House-plots staked**: rope-and-stake outlines in the clearing — portfolio: ONE plot by the Great House (the Chair's) + a consultant's bench per lane; functional: five plots; custom: a surveyor's table with a blank charter | `roster.yml` / `platform.yml` officers block (marker-managed) |
| 11 | Autonomy level (`autonomy.*`, posture preset copy) | The SKILL.md §4 statement rendered as the **Charter Hall preamble** ("every deployment starts guardian; hard ceilings never resolve unconditional auto"), then ONE question per axis | **The flag bundle**: the chosen posture's colors appear as a furled bundle at the bare flagpole's base — it does NOT hoist (the pennant hoists on the first census keyframe, per the egg manifest binding; honest). Sovereign choice: the bundle is shown **locked in a strongbox** + errand note E7 (the ritual is a post-init Captain act, printed verbatim — never a hatch side-effect) | `posture.yml` INERT scaffold (generator renders it; resolve_posture demands the schg lock) |
| 12 | Flavor (`autonomy.flavor`) | "Does this box sense a person's estate, or only the org's own?" | **The memory chest**: org → a small book chest appears by the desk (OrgSource binding = recall works day one); personal → the chest renders open and empty, codex *"bind your own adapter — until then, honest zero recall"* | `sources.yml` emitted/omitted per the generator's emission rule |
| 13 | Deployment target (`autonomy.deployment_target`) | "Shared daily Mac, dedicated Mini, or a container?" | Card-only + a small brass plate by the cottage door (mac_mini gets a stone door-step — a dedicated foundation; joy, `decorative: true` beyond the card) | posture scaffold `deployment_target` |
| 14 | Telegram bot username + token env NAME (`integrations.telegram`) | "Your Chair needs a telegraph address." Bot USERNAME + env-var NAME only; the TOKEN is errand E1 | **The telegraph pole rises** (single wooden post + one wire at egg era, per §7's estate — the wire hangs SLACK and grey: declared, unkeyed) | `projects/*.yml telegram:` block (`TOKEN-TBD` kept) |
| 15 | Optional warroom group | One optional exchange | Second hook on the pole, slack until E1b | env NAME row |
| 16 | MCP env NAMES (`integrations.mcp_env_names`) | "Which other instruments will officers hold?" (names walked from the lanes' needs) | **Insulator pegs** added to the pole, one per declared env NAME, each grey with a paper tag naming the unresolved `${VAR}` — exactly the §7 DEAD-wire dialect, honestly applied to not-yet-keyed | `answers.yml integrations.mcp_env_names[]`; tags clear as errands validate |

Answers persist **progressively** server-side into
`instance/config/cabinet-init.answers.yml` after each phase (schema-validated per phase;
the file is the same single input the skill writes — resumable: close the browser, return,
the desk reopens at the first unanswered phase, exactly the skill's own idempotency
posture).

### 2.4 Era-appropriateness rule for hatching props

All §2.3 props are **egg-era forms** and each sits on its element's ratified growth ladder
(§15.1) so nothing is thrown away: signpost → the crossroads waymark → the noticeboard
cluster; single telegraph post → the §7 pole line; barrel-buoy → r0 dock when the lane's
first outcome ratifies; house-plot stakes → the great-work CLEARING site when the role is
actually seeded (§5). The grammar PR writes these as ladder rungs in `growth-ladders.yml`,
not as one-off props.

### 2.5 CONNECT at the desk

Integration DECLARATIONS (names, usernames, env NAMES) happen at the desk (§2.3 rows
14–16). Everything requiring a secret VALUE or an external account is an errand note (§3)
— the desk hands them over as physical envelopes. The interview does not block on errands
except where hard-required (§3 table): the Captain can sign the Charter with the telegraph
still slack, and the world says so honestly (Chair boots Telegram-dark; the runbook
verified boot warns-and-continues without secrets).

### 2.6 SIGN — the Charter and the natural commit point

When phases SHAPE+CONNECT are answered, the desk lays out **the Charter**: the assembled
answers rendered human-readable on one parchment (exactly what the skill's "confirm the
assembled answers back" step does — same content, nicer table). Secrets are absent by
construction (the answers file never holds them). Buttons: `Back` (edit any phase) and
`Sign` (H-2).

**The candor covenant (CANDOR LAW, Captain ruling 2026-07-10).** The Charter parchment
carries one standing covenant line above the signature, and the genesis interview SETS
THE EXPECTATION before the Captain signs — verbatim:

> *"Your cabinet will disagree with you, loudly, with evidence — its vetoes are yours,
> its silence is never agreement."*

This is not copy; it is the constitution's candor-over-comfort value surfacing at the
one moment every Captain reads a contract: officers owe evidence-cited dissent BEFORE
any compliance path, then obey the ruling (dissent-then-obey — Captain vetoes bind
absolutely); agreement-as-target is banned org-wide; tone is configurable per persona,
truthfulness is not (D15c: style is expression, values are genome). A new Captain who
wants an agreeable cabinet learns HERE that this one optimizes for the mission and
answers to them — it flatters no one. (Constitution amendment + role-def clauses staged
on `feat/germline-window-3`; golden eval EVAL-024-CANDOR pins the behavior.)

**Sign** (reauth-gated, §6.3) runs the EXISTING pipeline, unmodified:

1. Server writes the final `instance/config/cabinet-init.answers.yml`.
2. `python3.12 cabinet/scripts/generate-instance.py --dry-run` — the plan is rendered as a
   **wright's worksheet** card (every "would write" path listed).
3. Real run. Each generated file = one visible beat at H-1 tempo (contexts → the buoy
   plates get slugs burned in; projects → manifest inked; roster/platform → house-plot
   name-boards; posture scaffold → the strongbox seal; sources.yml → the chest latches;
   active-project.txt → the first lane's buoy gets a pennant ribbon).
4. `GenerationError` renders honestly on the parchment — *"the wright refuses:
   ‹stderr verbatim›"* — with the fix path. Secret-shape refusal, path-escape refusal,
   marker refusal all surface as themselves; nothing is retried silently.
5. **Adoption path**: if the clone ships a previous deployment's `instance/` (the
   MacBook's committed instance — the standard case per the mini-hatch runbook), the
   marker refusal is EXPECTED and the world offers **"settle the previous homestead's
   effects"**: re-run with `--adopt`, rendered as a wright carrying labeled crates into an
   **archive chest** by the shore (`instance/_pre-adopt-<stamp>/`, nothing deleted, path
   listed on the card). The refusal→adopt flow is the rehearsed one, world-skinned.
6. Ledger echo (§6.5) + `instance/config/.genesis-ready` written once the generator exits
   0 AND the hard-required errands are green.

The generator's printed next-steps become the **errand rack** (§3) — the world's version
of "relay the generator's printed list, expanded."

---

## 3. ERRANDS — the honest fetch-quests

Each external-by-nature step is an **errand note**: an envelope on the desk's errand rack.
Opening one shows: **WHERE you're going** (the real app/surface, named plainly), **WHY**
(one honest sentence), **WHAT to bring back** (paste field / a click confirmation /
"answer the wheel when it knocks"), and **VALIDATE** (a live server-side check with a visible
consequence). No errand pretends to happen in-world; the note says *"this walk leaves the
world — the world will know when you're back."*

| ID | Errand | WHERE (honest) | Bring back | VALIDATE (live) | Visible consequence | Required for hatch? |
|---|---|---|---|---|---|---|
| E1 | **The Chair's telegraph key** (bot token) | Telegram → @BotFather → `/newbot` (steps printed verbatim; never reuse a token another poller holds) | Paste the token into the note's **write-only** field | Server calls `getMe` with it (fixed host api.telegram.org — the only egress). Success ⇒ append-only `.env` write under the declared env NAME (§6.2). Response carries the bot USERNAME only, never the token | **The wire snaps taut** with a single traveling spark and a brief hum, then goes STILL (§7's inverted-humming law: change is the signal; healthy is quiet). Pole card NOW shows the bot username | **Yes** (Telegram is the single human surface; may be deferred — Chair boots dark and the note stays on the rack, amber) |
| E1b | Your chat id (return leg of E1) | Your own Telegram: send the new bot any word | Nothing to paste | Hatching-only single `getUpdates` poll reads the chat id (no competing poller exists pre-deploy; polling stops at RAISE, structurally before the Chair's poller starts) | **A letter slides into the mailbox** with your chat id on the address plate; Captain confirms it into the answers | Yes, with E1 |
| E2 | **The librarian's lens** (`VOYAGE_API_KEY`, optional) | voyageai.com dashboard | Paste (write-only) | Embed one probe string server-side; on success, append-only .env write | The memory chest gains a small brass lens; codex: *"without it the library still answers — keyword-only"* (EMBED-SEAM keyless fail-soft, verified 2026-07-07) | No (fail-soft is proven) |
| E3 | **The window latches** (macOS TCC, optional) | System Settings → Privacy & Security, via `bash cabinet/scripts/grant-mac-permissions.sh` in the Terminal (interactive — the OS requires human clicks; grants are responsible-process-scoped) | Click-through, then "done" | v1b: self-reported + doctor's next verdict; v2: probe-backed (calendar `calinfo` probe class) | Cottage window shutters open | No (base hatch skips TCC per the runbook) |
| E4 | **The lane-CEO scope lines** (germline files) | The Terminal (or an editor): paste the generator-PRINTED lines into `cabinet/mcp-scope.yml` (`agents:`) + `cabinet/officer-capabilities.conf`. On a FRESH clone these are not schg-locked — plain edits work (runbook 4.2). The world may NOT write them: they are germline, outside `instance/`, outside the sanctioned pipeline | "done" | Server RE-READS both files and diffs for the exact expected rows; green only on match | Each staked house-plot gets its **capability rope-knots** (one knot per capability row) | **Yes for portfolio lanes** (Chair-only hatch can proceed; lane CEO seeding waits). Auto-voids when the **lane-CEO scope seam** ships (runbook germline-handback #1: a managed block generate-instance can stage for Captain apply) |
| E5 | **The Launching** (Launch Warrant) | The wheel = the Hatch Cabinet launcher's native **Launch dialog** (it knocks when the Warrant is ready; Terminal fallback: the ENTER where `./hatch.sh` waits). WHY: raising officers is org-state actuation; the world does not hold that power (doctrine §0) — your hand at the wheel, in a local OS dialog no web page can click, does | Click **RAISE** (fallback: ENTER) | Act II runs §5's chain; `hatch-status.jsonl` feeds the choreography | §5 entire | **Yes** — it IS the hatch |
| E6 | **The dead-man's bell** (Healthchecks.io) | healthchecks.io account: create checks per `services.yml` expected-floors, ASSIGN ALERT CHANNELS (the 2026-07-02 drill: API-created checks ship with empty channel lists — an alarm wired to nobody), keys into `cabinet/.env` | Paste ping/API keys (write-only) | Ping round-trip | A small bell bracket on the jetty post (grey until the weekly drill first rings it) | No (post-hatch, recommended) |
| E7 | **The vault door** (germline lock / sovereign ritual) | The Terminal, with sudo: `sudo bash cabinet/scripts/germline-lock.sh lock` (and for sovereign: the full posture ritual printed VERBATIM from SKILL.md §4 — unlock → copy preset → edit basis/ruled_at → commit → lock). WHY the world cannot do this: unlock is fail-DANGER; per **GOV-UNLOCK-UX** (ledger row) any future non-Terminal path must terminate in an OS-level auth ceremony (TouchID/Authorization Services), NEVER a web click — until that ships, this is honestly a Terminal act | "done" | v1b: `germline-lock.sh status` read; v2: doctor probe | The strongbox at the flagpole visibly LOCKS (sovereign target renders its pennant only after a locked, deployment-matched ruling — read from `resolve_posture`, never claimed early) | No for the base hatch (fresh clones start unlocked; lock is a post-hatch Captain act) |

Errand rack states are dual-coded (grey = not started, amber = open, green = validated)
and every note's card carries PROOF (the config path / doctor line / probe output —
names-not-values). Deferred-allowed errands stay on the rack **after** genesis as plain
world cards (the rack itself survives as the noticeboard's ancestor; hatching-only WRITE
paths die per §0 — post-genesis, E2/E3/E6/E7 validation reruns ride read-only probes and
their VALUES go in via the existing Terminal paths, with the world only rendering state).

---

## 4. THE FIRST LETTER — focus, not seed outcomes

### 4.1 Writing it

After SIGN, the desk dialog closes and the Captain's marker walks the path to the
**mailbox** (the crossroads-to-be). The mailbox opens a letter frame (same pack dialogs):

> *"Tell your org what matters. Not tasks — bearing. What should it explore first, what
> is precious, what is urgent, what should it never touch?"*

Free text, plus an optional per-lane emphasis line (pre-filled from the lane exchanges).
This is **ONBOARD-1's input**: the onboarding **focus** that replaced interview
seed-outcomes. Stored as `instance/config/onboarding-focus.md` (generated-by-marked,
config-plane, part of the sanctioned write class §6), echoed to the ledger, and consumed
by the Chair's genesis brief at first boot.

The mailbox flag goes UP — its real binding (`pending_captain_items` ≥ 1 in spirit:
there is now one letter in the world's postal system, and it is the Captain's own).

### 4.2 What happens next, visibly (the org side)

Post-RAISE (§5), the org runs the genesis re-sequence's back half — all real, all
rendered from real events:

1. **ONBOARD (explore):** the Chair reads the focus letter + the estate
   (`gather-then-decide`); activity verbs render the Chair at the desk/library
   ("reading the charter", "walking the holds"). **ONBOARD-2** fires: the onboarding
   web-research organ produces the company/market/product brief **into the Library** —
   choreographed (v2) as a courier boat delivering the first book-crate to the cottage
   (Library ladder rung 1: the first shelf fills — real `memory_rows_total`/Library
   records moving, never invented).
2. **PROPOSE:** the org compiles proposed outcomes (draft rows, `status: draft`,
   `captain_ratified: false`) and **return letters arrive**: the mailbox flag rises on the
   real pending count; each letter = one proposal card (WHAT: the proposed outcome ·
   NOW: draft, awaiting ratification · PROOF: the draft row).
3. **RATIFY — on the existing surfaces, not in the world.** The living world is read-only
   + lever (D2). Opening a return letter shows the proposal and **deep-links** to the
   existing ratification surface (the dashboard decision-queue / the Chair's Telegram
   proposal card — the mailbox's ratified deep-link dialect). In-world ratification would
   be a NEW write class (WORLD-WRITE-CLASS-2) and is explicitly NOT designed here — open
   call §9.1.

### 4.3 Honesty line

The letter is the last hatching write. Everything after it that looks like "the world
responding" is the org actually working — if the org is slow, the mailbox is honestly
quiet. No scripted replies, no fake first proposal.

---

## 5. THE HATCH — officers arrive on real state

Trigger: E5 — the Captain clicks **RAISE** in the launcher's native Launch dialog
(Terminal fallback: ENTER). Act II drives; the world only *renders* what
`hatch-status.jsonl` + the live keys/launchd state say. Beats, in the real dependency
order of the runbook:

1. **Seaworthiness trials** (P-a null-hatch, P-b clean-room ratchets, P-c dry renders):
   typescript-first output; the world shows three lanterns lighting on the jetty rail as
   each gate goes green (status-feed driven; a red gate = storm-lamp + verbatim failure,
   §1.2).
2. **The Oath** (P-d revocation drill, choreographed with the ruled ONE actuator): the
   world walks the camera to the **killswitch lever** and asks the Captain to PULL —
   two-tap + confirm + cookie, the real lever, the real key (`cabinet:killswitch`).
   *"Prove you can stop it before you start it."* Red wash falls over the world.
3. **Roster seeded** (`bootstrap-roles.sh --roster`): each staked house-plot gets its
   name-board (roles exist as rows — honest: boards, not buildings; cottages are earned
   later by the growth grammar when sessions actually live).
4. **The Chair sails in** (`deploy-mac.sh --officer cos` → launchd job): a boat enters on
   the real job-start event and — because the killswitch is ACTIVE — **holds at anchor**
   in the roadstead (the ratified at-anchor mechanic, honest wait made visible). Act II
   meanwhile proves the fail-closed bar: the booted Chair's first tool call is REFUSED by
   the pre-tool-use hook while ACTIVE (recorded in the typescript + status feed; the
   drill requirement, satisfied for real).
5. **Release**: the Captain releases the lever (same ceremony via `deactivate`). The wash
   lifts; the boat rows in; the Chair sprite steps ashore, walks the path, and the Great
   House window lights — the light is the real presence key, nothing else.
6. **Measurement plane**: plists render + lint + bootstrap; each loaded job = a lantern
   hung along the jetty rail (v1b: simple lanterns; v2: the bestiary/infra dialects take
   over when those layers ship).
7. **Doctor**: `cabinet-doctor.sh` runs; GREEN lands in the typescript + status feed AND
   the world hangs the harbor's **green riding-light** at the jetty head. Expected-DEAD rows for
   deliberately-unloaded services follow the runbook's rule (flip `disabled: true` or
   bootstrap them — a documented edit, not a P3 violation).
8. **Genesis stamp** → hatching CLOSES (§0). Title beat: the pennant will hoist on the
   **first census keyframe** (the egg's ratified first beat — usually within the day;
   the world does not fake it early). The Chair's first Telegram round-trip happens on
   the Captain's phone; the world shows the Chair "at the desk, writing" from its real
   activity verb, and nothing more (DM content never renders — privacy law).

From this moment the world is the living world: read-only + lever, lawful tempos,
hatching routes 410. The hatching props remain as the youngest rungs of their ladders.

---

## 6. SECURITY REVIEW — the captain-write endpoint

### 6.1 Surface inventory (complete)

Routes (all under the existing authenticated dashboard app; middleware cookie required;
`/display` kiosk route serves NOTHING hatching-related):

| Route | Method | Writes | Gates |
|---|---|---|---|
| `/api/hatch/status` | GET | none | session cookie + hatching-OPEN |
| `/api/hatch/answers` | POST | `instance/config/cabinet-init.answers.yml` (per-phase), then shells `generate-instance.py` at SIGN (dry-run, then real; `--adopt` only on explicit adopt confirm) | cookie + OPEN + same-origin + rate limit + per-phase schema validation + generator's own jail/refusals; SIGN additionally requires a fresh reauth OTU |
| `/api/hatch/secret` | POST | `cabinet/.env` append-only (backup first) | cookie + OPEN + same-origin + rate limit (5/min) + reauth OTU + env-NAME allowlist (only names declared in the interview) + refuse-if-name-exists |
| `/api/hatch/focus` | POST | `instance/config/onboarding-focus.md` | cookie + OPEN + same-origin + rate limit + length cap + plain-text only |
| `/api/hatch/errand` | POST | none (validation only; E1b's answers write rides `/answers`) | cookie + OPEN + same-origin + rate limit |

That is the ENTIRE write plane. No route starts, stops, signals, or schedules anything;
no route touches `outcomes.yml`, Redis org keys, launchd, tmux, or any file outside the
two named paths + the focus file. `POST /api/world/killswitch` (P-KS) is a separate,
already-ruled surface and is unchanged.

### 6.2 Write mechanics

- **answers.yml**: written atomically (tmp + rename, same pattern as the generator);
  every phase POST is schema-checked against the cabinet-init schema fragment for that
  phase AND run through the generator's `SECRET_PATTERNS` scan server-side — a pasted
  token in a name field is refused with the generator's own message. The generator run
  itself is `execFile` with a CONSTANT argv (`python3.12`, script path, flags) — captain
  input never touches a shell string, never becomes an argument.
- **cabinet/.env**: before any append, copy to `cabinet/.env.bak-<UTCstamp>` (chmod 600);
  append exactly one `NAME=value` line; never rewrite, never delete, never reorder;
  if NAME already exists → refuse with an errand note pointing at the Terminal
  (`setup-env.sh`) — the world never overwrites a secret. Values are held in memory only
  for the write + the single validation probe; never logged (the status feed and ledger
  echo carry NAMES only), never in any response body, never in the answers file.
- **Ledger echo**: every successful write appends a provenance-stamped entry via
  `bash cabinet/scripts/append-interface.sh captain-decisions` (stdin), e.g.
  `world-write: answers phase=lanes fields=[...] · by captain cookie+OTU · hatch window` —
  names-not-values, the append-only captain-law path (direct Write/Edit is hook-blocked,
  which is exactly right: the hatch server uses the same sanctioned interface officers do).

### 6.3 AuthN/AuthZ stack (defense in depth, all EXISTING mechanisms)

1. **Localhost bind**: the dashboard listens on `127.0.0.1` only during hatching
   (the launcher starts it so; the server asserts at boot and refuses hatch routes if
   bound wider). No LAN/tailnet exposure of the write window.
2. **Session cookie**: the existing `cabinet_session` HMAC cookie (middleware.ts) —
   possession = logged-in captain (DASHBOARD_PASSWORD was minted by the launcher into a
   0600 file in the captain's own install minutes earlier).
3. **Re-auth OTU for SIGN + secrets**: the existing Spec-034 two-step
   (`/api/auth/reauth-challenge` → Redis 5-min challenge → `/api/auth/reauth-verify`
   {password} → one-time-use token, consumed by the write). Binds each high-consequence
   write to a live password entry; replay-proof by construction.
4. **Same-origin enforcement on every POST**: `Origin`/`Host` allowlist
   `{127.0.0.1, localhost}:<port>` + `Sec-Fetch-Site: same-origin` required (also kills
   DNS-rebinding: a rebound hostname fails the Host check). Cookie `SameSite` as an
   additional belt. No GET mutates anything.
5. **Rate limits**: token-bucket per route (writes 30/min global, secrets 5/min) — a
   compromised page cannot brute the window.
6. **Hatching-OPEN gate** (§0): server-side, dual (stamp + org-reality), checked per
   request. CLOSED ⇒ 410 for every `/api/hatch/*` and the hatching UI chunk is not even
   served.

### 6.4 Threat cases (worked)

| Threat | Why it fails here |
|---|---|
| **XSS in the dashboard → key theft** | World CI ratchets already mandate strict CSP + text-only rendering (`textContent`, no inline/eval). Beyond that: secrets are **write-only** — no route ever returns a secret, logs one, or stores one outside `cabinet/.env` (0600); the DOM never holds a token after the POST resolves; responses carry derived proofs only (bot USERNAME). An attacker with full page JS could at most call the same rate-limited, schema-validated, OTU-gated endpoints — and the OTU requires a fresh password entry the attacker doesn't have. Residual: a keylogging XSS during the paste itself — mitigated by CSP making script injection the hard step, and by the window's brevity; accepted and named. |
| **CSRF from a hostile site** | SameSite cookie + Origin/Host allowlist + Sec-Fetch-Site + OTU on the dangerous routes. A cross-site form POST fails three independent checks before schema validation even runs. |
| **Replayed hatching mode on a LIVE cabinet** (the killer case: resurrect the write plane after genesis) | §0's dual gate: the stamp AND the org-reality check (seeded roster / live Chair job / ratified outcomes for this CABINET_ID). Deleting `genesis.stamp` on a live box does not reopen anything — reality says a cabinet lives here, routes stay 410. The stamp itself is echoed to the ledger at creation, so a missing stamp is also an auditable anomaly. Re-hatching legitimately = the documented rollback (runbook: bootout agents, delete the clone) — a NEW hatch on a clean tree, not a reopened window. |
| **DNS rebinding to 127.0.0.1** | Host-header allowlist (a rebound origin presents the attacker's hostname); same-origin fetch metadata; localhost bind means the target is only reachable from the machine anyway. |
| **Command injection via answers/errand fields** | No captain input is ever interpolated into a shell string: answers go via the YAML file into a constant-argv `execFile`; errand notes print STATIC command templates (no substitution of captain text into printable commands); the slug/name/env-NAME regexes (generator's own) reject shell metacharacters as a class. |
| **Path traversal** | The endpoint writes exactly three paths, all CONSTANT; everything under `instance/` goes through the generator's realpath jail + kebab-slug validation (its refusal, not a reimplementation). |
| **Secrets smuggled into config** | The generator's `SECRET_PATTERNS` abort, run BOTH at phase-POST time (fast feedback at the desk) and inside the generator itself (authoritative). The .env lane is the only value path and it never round-trips. |
| **SSRF via validation probes** | The only egress is `api.telegram.org` (getMe/getUpdates, fixed host, no captain-controlled URL component) and the optional Voyage probe (fixed host). No fetch-arbitrary-URL exists on any hatch route. |
| **The web surface starting the org** (privilege creep) | Structurally impossible: activation commands live in the engine's Act II, gated behind an **OS-level UI event in the Captain's own local launcher process** — the native Launch dialog's RAISE click (Terminal fallback: stdin ENTER). The launcher watches the filesystem for `.genesis-ready`, never listens on HTTP; the server can only write that file (a permission for the wheel to KNOCK), web content cannot click a native dialog, and the dialog does not exist until genesis-ready does. The world's only org-state actuator remains the lever, which shells the proven `kill-switch.sh` and nothing else. |
| **getUpdates poller conflict / token hijack window** | The hatching chat-id capture polls only while hatching is OPEN and stops structurally before `deploy-mac.sh` runs (Act II ordering) — no second poller ever competes with the Chair's; the token was written to .env once and is read from there, never re-transmitted to the client. |

### 6.5 WORLD-WRITE-CLASS-1 — ruling text (for captain-decisions, verbatim)

> **WORLD-WRITE-CLASS-1 (The Hatching write class) — ruled 2026-07-09.**
> The Cabinet World may carry writes ONLY of this class: **captain-identity**
> (dashboard session + fresh re-auth OTU for signing and secrets), **config-plane only**
> — (a) `instance/config/cabinet-init.answers.yml` + `instance/config/onboarding-focus.md`
> routed through the EXISTING validated pipeline (`cabinet/scripts/generate-instance.py`:
> instance/ path jail, secret-shape refusal, marker discipline), and (b) **append-only**
> `cabinet/.env` secret drops (backup-first, 0600, never echoed, names declared in the
> interview only) — **never org-runtime state** (no officer start/stop, no launchd, no
> Redis org keys, no outcomes ratification, no posture attestation, no germline files).
> Every write is echoed to the captain-decisions ledger via the append interface,
> names-not-values. The class exists ONLY inside the hatching window (`genesis.stamp`
> absent AND org-reality agrees no cabinet lives here); at genesis completion the routes
> die permanently (410). The killswitch lever remains the ONE in-world org-state actuator
> in every era. Germline unlock/lock stays a Captain Terminal act until GOV-UNLOCK-UX
> ships its OS-auth ceremony. Any widening of this class (e.g. in-world ratification of
> proposed outcomes = WORLD-WRITE-CLASS-2) is a separate Captain ruling, never an
> implementation drift.

---

## 7. STAGING, REUSE, ACCEPTANCE

### 7.1 v1b ships (rides the WORLD-V1B wave; this row = WORLD-ONBOARDING-V1B)

- **Dialog framework**: 32×32 pack frames + typewriter + input-row variant (pulled forward
  from the v3 library-query dialog family — same component, earlier customer) + H-2
  hatching button set.
- **The interview at the desk**: full §2.3 mapping, progressive answers.yml, Charter +
  SIGN → generator (dry-run preview, real run, `--adopt` flow), consequence props via ONE
  grammar-law PR (signpost, buoy+stake, jetty manifest, house-plots, flag bundle +
  strongbox, memory chest, telegraph post + pegs, address plate, errand rack, arrival
  rowboat pass) with codex on every entry + H-1 tempo clause.
- **The first letter** (`/api/hatch/focus` → onboarding-focus.md → Chair genesis brief).
- **Errand rack v1**: all seven notes rendered; live validation for E1/E1b (getMe +
  getUpdates capture), E2 (probe embed), E4 (file re-read diff), E5 (.genesis-ready +
  status feed); E3/E6/E7 self-reported + doctor-verdict readback.
- **Hatch Cabinet.app + `hatch.sh`**: the native launcher (bundled repo payload,
  Gatekeeper right-click→Open documentation, idempotent re-launch, native
  progress/failure dialogs, the Launch dialog) wrapping the engine's Act I + Act II
  (proof gates, drill, activation chain, status feed, genesis stamp) — mechanizing the
  mini-hatch runbook it must keep byte-honest with. Terminal fallback face documented
  for technical captains.
- **Security plane**: §6 complete (routes, gates, 410 lifecycle, ledger echo) + the
  security test suite (§7.4).
- **Arrival + hatch choreography, minimal**: rowboat-in, signpost naming, walk, cutaway
  desk; Chair boat on real job start + at-anchor drill + window light; lanterns per
  status-feed line.
- **Multi-cabinet v1b half (§10.6)**: detection + native chooser + explicit
  "Hatch a new cabinet…", registry create/append + legacy registration offer, island
  naming at the signpost (name→slug→cabinet.id), per-install genesis gates, namespace
  bundle allocated + recorded.

### 7.2 v2 (polish + probes; nothing in v1b lies while waiting)

Full errand validators (TCC probe class, doctor-probe-backed E6/E7, germline-status
probe); one-time login URL (kills the watchword typing); richer hatch choreography
(per-service arrivals riding the infra/bestiary dialects when those layers land);
ONBOARD-2 book-crate delivery scene; stranger-hatch usability pass with a real
non-technical captain; hatching-tempo tuning against real interview pacing; launcher
polish (menu-bar residency, payload update story); **full multi-run + the shared
archipelago** (§10.3/§10.5: MULTI-CABINET-READINESS executed, two-cabinet side-by-side
drill, multi-source renderer + island-rises choreography riding WORLD-E0B-MINI — the
Mini-island flagship demo). **Commercialization-lane (deferred with that lane, not
v2):** signed + notarized Hatch Cabinet.app (Apple Developer cert) — removes the
Gatekeeper right-click→Open step.

### 7.3 Reuse map (what this rides on — build nothing twice)

| Component | Source of truth (already designed/shipped) |
|---|---|
| Egg islet render, growth ladders, quick-work sites, at-anchor mechanic | WORLD-V1A (spec v2 §3, §2.4; `egg-tile-plan.md`) |
| Roof-cutaway desk scene, inspect cards WHAT/NOW/PROOF, coverage/validator ratchet | WORLD-V1B interiors + shipped `inspect-card.tsx` |
| Pixel dialog frames, typography, portrait rail | WORLD-NEXT-UIPACK (§9, §15.6 — pack ON-DISK) |
| Killswitch lever + P-KS route pattern (cookie-gated POST shelling a proven script + chronicle witness) | spec v2 §9.3 — the hatch endpoints copy its shape, not new machinery |
| Interview content, idempotency, adoption, activation list | cabinet-init SKILL.md + generate-instance.py, UNMODIFIED semantics (one additive schema key family if needed for the focus letter is NOT taken — focus lives in its own file) |
| Host bootstrap, proofs, drill, doctor | setup-mac.sh, null-hatch.sh, clean-room pytest ratchets, kill-switch.sh, cabinet-doctor.sh, generate-plists.py — hatch.sh ORCHESTRATES, never reimplements |
| Auth | middleware cookie + Spec-034 reauth OTU routes |
| Ledger echo | append-interface.sh captain-decisions |
| SSE/status | tasks-stream SSE pattern; hatch-status.jsonl tail |

### 7.4 Acceptance criteria (WORLD-ONBOARDING-V1B gate)

1. **The stranger hatch (the bar that matters — starts from the double-click):** a
   non-technical captain, fresh macOS user account, completes: download zip →
   right-click→Open **Hatch Cabinet.app** (the documented Gatekeeper step) → watchword
   pasted in the browser → desk interview → phone errand (BotFather) → ONE native
   **RAISE** click when the wheel knocks → sees the Chair arrive → Telegram round-trip —
   **ZERO Terminal**, at most one native admin prompt (Homebrew), ≤90 min wall-clock
   including downloads, zero hand-edits beyond documented steps (P3 discipline
   inherited), the whole run self-recorded to `~/hatch-logs/`. Double-clicking the app
   again afterwards opens the living world and can never re-hatch.
2. **Doctrine:** post-genesis, `/api/hatch/*` all return 410 — including with
   `genesis.stamp` manually deleted on a live org (org-reality case); the ONLY successful
   in-world mutation on a living world remains the lever; every hatch write has a ledger
   echo line (names-not-values, spot-checked).
3. **Security suite (vitest + one live drill):** origin-reject, Host-allowlist reject,
   rate-limit trip, OTU-required on SIGN/secret, secret-echo scan = zero hits over all
   responses + logs + status feed + ledger for a full hatch, .env backup exists +
   append-only property (pre/post diff = exactly one line), refuse-on-existing-name.
4. **Pipeline fidelity:** the hatch's generated `instance/` is byte-identical to running
   the cabinet-init skill + generator by hand on the same answers (the world added a UI,
   not a fork); re-running the interview is idempotent per the generator's own contract;
   the `--adopt` path archives (never deletes) and is rendered honestly.
5. **World law:** six-command world bar (vitest suites, framework pytest, gate self-tests,
   binding-validator, asset gate, mechanical aesthetic gate) green on the hatching
   fixtures — arrival-dusk frame, desk-dialog frame, charter parchment, errand rack,
   Chair-at-anchor red-wash frame; determinism replay (same answers + ticks ⇒
   byte-identical frames); every hatching prop has codex or `decorative: true`; honest
   zeros intact (the cairn stays DARK through the entire hatch — onboarding mints no
   graduation, no light).
6. **Multi-cabinet v1b (§10):** with one cabinet registered, a second app launch opens
   its world (no re-bootstrap, no re-hatch) and shows "Hatch a new cabinet…"; choosing
   it lands a NEW island whose signpost naming refuses registry-colliding and reserved
   slugs with the exact reason; the registry row carries the full namespace bundle and
   zero secrets; cabinet A's genesis state provably does not gate cabinet B's routes
   (per-install 410 tests).
7. **A13 parity:** ledger rows WORLD-ONBOARDING-V1B + MULTI-CABINET-READINESS ↔
   plan-doc rows, gate exit 0.

---

## 8. ADVERSARIAL SELF-REVIEW (run before commit; kept in the doc — the holes are load-bearing)

**Doctrine holes hunted:**

- *"World render is read-only except the lever" vs a write-surface in the world* —
  resolved by scope, not exception-creep: the hatching window is defined server-side and
  terminal (§0), the write class is enumerated and config-plane only (§6.5), and the
  living world's D2 is untouched. The Captain's 2026-07-09 onboarding direction is the
  ruling basis; WORLD-WRITE-CLASS-1 is its precise form.
- *Buttons law / read-only mailbox* — H-2 scopes buttons to hatching dialogs; the mailbox
  WRITE (focus letter) exists only inside the window; the living mailbox stays view +
  deep-link exactly per the 2026-07-09 ruling. Post-genesis ratification letters
  deep-link out; no in-world ratify (open call §9.1).
- *Population law* — the arriving Captain figure is §15.5-sanctioned (transient real
  external at dock/mailbox); wrights are the already-ruled decorative-honest site crews;
  no fictional villagers appear at any hatching beat.
- *Rate-routing / capability-minting* — interview props render DECLARED CONFIG, never
  earned capability: buoys say "staked, not earned", plots are stakes not cottages, the
  flag does not hoist early, the cairn stays dark. Nothing in the hatch advances any
  ladder rung that binds to org evidence.
- *D4 (structure never pops) vs H-1 tempo* — sites still run all four phases with a crew;
  only D is compressed, the witness record is real (the answer), and the clause is
  window-scoped and written into the grammar PR. Checked against the alternative (lawful
  15-min sites would make the interview a wait-simulator — worse joy, same honesty).
- *Era conformance* — all props are egg-era rungs of ratified ladders (§2.4), so the
  hatch cannot render a town the org hasn't earned.
- *ONBOARD-1 sequence fidelity* — connect precedes focus (telegraph before mailbox);
  focus precedes org onboarding; outcomes are PROPOSED by the org, never interviewed —
  the removed phase-5 is explicit (§2.1).

**Security holes hunted:** the §6.4 table is the record; the four that shaped the design:
(1) replayed-hatching needed the org-reality second gate, stamp alone was forgeable by
deletion; (2) the wheel gate (native Launch dialog / fallback stdin — an OS UI event in
the Captain's local launcher process) is what keeps org activation out of the web trust
domain entirely — without it, "the server runs bootstrap when ready" would have made the
world an org-state actuator through a side door; (3) secret echo was eliminated
structurally (write-only lane + derived-proof responses), not by "being careful";
(4) multi-cabinet forced the genesis gates to be PER-INSTALL (§0/§10.1) — a machine-wide
gate would have let cabinet A's existence block cabinet B's hatch, or worse, let a fresh
staging root masquerade as a reopened window on A.

**Chicken-and-egg audit:**

- *World before instance/?* Yes — the egg renders from zero state (v1a's egg is the
  zero-event world by definition; absent chronicle/census ⇒ egg t0). Acceptance §7.4.5
  pins it.
- *Dashboard before deps?* The launcher's Act I owns the whole chain; the browser opens
  LAST.
- *Gatekeeper before anything?* The unsigned .app cannot open by plain double-click on
  first run — the download page documents right-click→Open with a picture (v1b), and
  the signed build (commercialization lane) deletes the step. Named, not hidden.
- *Second double-click?* Idempotent by design (§1.2 Act I step 1): existing install ⇒
  open the world in whatever mode genesis says; re-bootstrap never runs twice; re-hatch
  is impossible from the app AND from the server (§0 dual gate — two independent layers).
- *Chat id before bot?* Captured on E1's return leg via hatching-only getUpdates — the
  skill's "leave it for a re-run" gap, closed live without guessing.
- *Drill before Chair?* The lever + kill-switch.sh need only Redis (Act I started it);
  the drill's refusal-proof needs the Chair booting AFTER activation — Act II orders it
  exactly as the runbook does (activate → boot → observe refusal → release).
- *Charter before errands?* Sign requires only SHAPE answers; E1/E4 can complete after
  SIGN but before E5 (.genesis-ready = generator-0 AND hard-required errands green);
  deferring E1 entirely leaves the Chair Telegram-dark and the world says so (runbook
  warns-and-continues behavior, rendered honestly).
- *Generator refusal on shipped instance/?* The --adopt flow is a first-class scene
  (§2.6.5), not an error path — it was rehearsal-1's worst stall, so it gets the gentlest
  UX.
- *Mid-interview crash/close?* answers.yml is the resume point (§2.3 tail); hatch.sh Act
  II survives independently (it only watches for .genesis-ready); a killed dashboard
  restarts idempotently from Act I's launcher.

**Named residual risks:** paste-time keylogging XSS (§6.4 row 1, accepted + named);
hatching-tempo is presentation-layer law bent inside a ruled window — if the Captain
dislikes ANY tempo distinction, the fallback is lawful quick-work minima with a progress
dialog (pre-agreed, one constant); E4 remains a copy-paste errand until the scope seam
ships (tracked, auto-voiding); the watchword typing step survives until the v2 one-time
login URL; the unsigned-app Gatekeeper ceremony (right-click→Open) is real stranger
friction until the commercialization-lane signing lands — mitigated only by
documentation with a picture; the bundled payload is a SNAPSHOT (updates ride the
normal git path post-hatch — the launcher never auto-updates the tree).

---

## 9. OPEN CAPTAIN CALLS

1. **WORLD-WRITE-CLASS-2 (in-world ratification of org-proposed outcomes)** — return
   letters currently deep-link to the existing surfaces (§4.2.3). Ratifying at the
   mailbox would need its own ruling + design (it is org-runtime state by this doc's own
   doctrine). Default: NOT designed; the deep-link stands.
2. **Distribution + update story for the bundled payload** (§1.1 row 2) — who builds the
   zip, where it downloads from, and how a hatched install takes framework updates
   (post-hatch git pull is the default; the launcher never auto-updates). The Terminal
   fallback still needs repo access (`gh auth login`) until a public-repo/token-URL
   story is ruled.
3. **Watchword vs one-time login URL in v1b** — v1b ships the watchword (smaller surface);
   pull the OTU login forward if the stranger-hatch dry run stumbles on it.
4. **E1 required-vs-deferrable** — this doc marks the bot token deferrable (Chair boots
   dark, honest amber note). If the Captain prefers "no hatch without a voice", flip E1
   to hard-required — one constant in the .genesis-ready predicate.

---

## 10. MULTI-CABINET (Captain amendment 2, 2026-07-09 — BINDING; where this contradicts §0–9, THIS section wins)

One Mac, N cabinets, one archipelago. Every judgment below is grounded in what the code
does today (read-only evidence pass 2026-07-09), and everything that today HARDCODES a
single-cabinet assumption is flagged into the **MULTI-CABINET-READINESS** ledger row
rather than hand-waved.

### 10.1 Detection + the machine registry (v1b)

- **Registry:** `~/.cabinet/registry.json` — the ONE machine-level file the launcher
  owns (`~/.cabinet/` already exists as the machine state home: autoreply/logs/state).
  Schema `cabinet.registry/v1`:

  ```json
  { "schema": "cabinet.registry/v1",
    "cabinets": [ { "name": "Harvestholm", "slug": "harvestholm",
        "cabinet_id": "harvestholm", "root": "/Users/x/CaptainsCabinet/harvestholm/captains-cabinet",
        "dashboard_port": 3000, "redis_url": "redis://127.0.0.1:6379/0",
        "launchd_prefix": "com.cabinet.", "claude_config_dir": "~/.cabinet/harvestholm/claude-config",
        "telegram_bot_username": "…", "created_at": "…", "genesis": "closed" } ],
    "peers": {} }
  ```

  Rules: launcher-only writes (flock + atomic); **no secrets ever** (bot USERNAME yes,
  token never); **not a trust surface** — every consumer realpath-validates `root`
  before serving/opening anything, and the world renderer treats registered chronicle
  paths as read-only exhaust (§10.5). The registry records; it never actuates.
- **Detection** (launcher Act I step 1, §1.2): registry ∪ launchd label scan
  (`com.cabinet.*`) ∪ known legacy roots. Existing cabinets ⇒ open THEIR world (native
  chooser when several — islands listed by name); **"Hatch a new cabinet…"** is an
  explicit same-dialog choice, never the default. Pre-registry cabinets (this MacBook,
  the Mini) get offered a registration row on first sight — read-only inspection, one
  registry append, nothing in the cabinet touched.
- **Genesis gates are PER-INSTALL** (§0 amended): each cabinet's stamp + org-reality
  check scope to its own root/label-prefix/CABINET_ID. Cabinet A's existence neither
  blocks nor reopens anything about cabinet B.

### 10.2 Naming — the island IS the cabinet (v1b)

The signpost exchange on landing (§1.3) is the naming act: **island name = cabinet
display name**; slug = kebab-case of it (generator `SLUG_RE` + `RESERVED_SLUGS` +
registry uniqueness — refusals surface as the wright shaking his head with the exact
reason). From the name the registry allocates the cabinet's whole namespace bundle:
root dir, dashboard port, Redis db index, launchd label prefix, CLAUDE_CONFIG_DIR —
recorded in the registry row at carving time, consumed by the generator/engine
(`cabinet.id` = slug; `CABINET_MODE=multi` + `CABINET_ID` .env appends automatic when
the registry already holds another cabinet). The FIRST cabinet on a clean Mac may stay
single-mode with today's bare namespaces (db 0, `com.cabinet.` labels) — recorded
as-is in its registry row; converting it to multi-mode later is a documented Captain
step (readiness row), never a silent rewrite.

### 10.3 Multi-run namespacing (v2 — honest judgments, not wishes)

Per-cabinet, all registry-allocated:

| Surface | Design | Honest basis |
|---|---|---|
| Repo clone dir | `~/CaptainsCabinet/<slug>/captains-cabinet` | plain; shared/interfaces + ledgers are per-clone already |
| Dashboard port | registry-allocated (3000 + next-free), bound 127.0.0.1 | today's port is config; per-install .env carries it |
| **Redis isolation** | **DB index, not key-prefix**: per-cabinet `REDIS_URL=redis://127.0.0.1:6379/<n>` (registry-allocated; db 0 = the first/mother cabinet) | Evidence: **164 files** carry bare `cabinet:*` key literals; spec v2 D5 cites `cabinet:cost:tokens:daily:<date>` BY NAME as law; doctor/dashboards grep these constants. A key-prefix refactor would touch all of it and invite missed-prefix cross-talk forever. A db index isolates EVERY key with zero literal churn (SCAN/KEYS are per-db). Named limits, rendered honestly: SELECT-db is a namespace, NOT an auth boundary (any local process can SELECT any db); FLUSHALL crosses dbs; Redis Cluster forbids db>0 (irrelevant: single host). Precondition = every call site honors `REDIS_URL` — 19 files do today; the ~92 hardcoded `6379`/bare `redis-cli` sites are the readiness row's audit list |
| launchd labels | `com.cabinet.<slug>.<service>` for new cabinets; mother keeps bare labels until its documented migration | `generate-plists.py` + officer template render labels today; supervisor/doctor greps parametrize on the prefix (readiness row) |
| CLAUDE_CONFIG_DIR | `~/.cabinet/<slug>/claude-config` per cabinet | the AUD-1 pattern — pilot already live in `start-officer-mac.sh` (comms-officer); kills officer-config cross-contamination between cabinets |
| Telegram | one bot per cabinet organism (per-cabinet `TELEGRAM_COS_TOKEN` in that cabinet's own `cabinet/.env`) | the standing one-token-one-poller rule; E1 errand runs per hatch |
| Germline lock | per-clone `schg` via each cabinet's own `germline-lock.sh` | schg is per-file per-checkout; locking cabinet A says nothing about B — correct, and each island's strongbox renders its OWN lock state |
| tmux / `/tmp/cabinet-runtime` / `~/Library/Caches/cabinet` | `<slug>`-namespaced | the KNOWN deferred residual from the mini-hatch runbook (cce6e601 follow-up note) — becomes a readiness-row item instead of a footnote; the cross-checkout takeover guard (exit 65) already protects against the worst accident and generalizes to N |

Everything in this table that is not true TODAY is a line item in
**MULTI-CABINET-READINESS** (ledger row, todo): the audit gate is mechanical —
`REDIS_URL` honored at every Redis touch; zero bare-label greps outside the mother's
documented exception; two cabinets hatched side-by-side on one Mac pass BOTH doctor
runs green with zero key/label/port collisions (the live two-cabinet drill is the row's
acceptance).

### 10.4 Inter-cabinet comms (v3 — config surface only, per the ratified colony contract)

- **Typed envelope schema ONLY** (`cabinet.envelope/v1`: closed verb set, schema-validated
  at the receiver; free-form command text is not a verb). **Trust never crosses**: no
  shared cookies/tokens/sessions; an envelope is DATA and enters the receiver through its
  own gates like any untrusted input. **Ledgers never shared**: captain-decisions /
  patterns / intents / needs stay per-cabinet, forever.
- **Spawning/federating = propose-only, highest-consequence** (standing egg ruling): a
  cabinet may PROPOSE hatching a sibling or opening a peer lane; only its Captain
  executes (the hatch is a Captain double-click by construction — §1).
- **Config surface** (designed now, DARK until v3): the registry `peers:` block —
  default `{}` (OFF). A peer row names {from_slug, to_slug_or_host, envelope_schema,
  transport: file-drop dir (one-way, receiver-validated), enabled: false}. No transport
  code ships before v3; the cabinet MCP's consent-gated `instance/config/peers.yml`
  remains the in-cabinet half when it re-wires (its grant was descoped 2026-07-07 as
  dead policy weight — that ruling stands).

### 10.5 SHARED WORLD — one archipelago, N islands (v2; flagship demo)

- **Organs stay per-cabinet** (WORLD-E0B-MINI's ratified shape: each cabinet runs its
  OWN census + chronicle; never cross-mounted organs). What §10 adds — superseding the
  "one world per instance" READING for rendering only — is that **ONE world renderer
  may consume N chronicle sources**: the registry hands the renderer each cabinet's
  chronicle/keyframe paths; every source renders as its own ISLAND in the one
  archipelago canvas.
- **Cabinet-island anchors**: allocated at registration, deterministic
  (`fnv1a(slug)` bearing on a cabinet-ring OUTSIDE the lane-isle fan, min pairwise
  separation, fixed forever — layout_fold). Lane isles stay children of their own
  cabinet's island in its own sector. `archipelago-positions.json` grows a
  `cabinet_islands` block (schema bump, grammar-PR reviewed).
- **Read-only by construction**: chronicles are exhaust (E0b: PII-scrubbed at ingest,
  verb-normalized, replay-identical). The renderer of cabinet A NEVER touches cabinet
  B's Redis, org_events, or config — files only, schema-validated line by line, unknown
  shapes ⇒ grey. Remote islands render keyframe truth with an honest "as of ‹last
  keyframe›" staleness chip; LIVE presence/verbs render only for the local cabinet.
  Cross-MACHINE islands (the Mini) need their chronicle exhaust carried over by a
  one-way copy (rsync/tailnet pull by the renderer host) — transport choice is an open
  item; the doctrine holds because copying exhaust adds no write path.
- **Hatching a second cabinet in a shared world**: the new island RISES offshore —
  visible from the first island — and the SAME rowboat onboarding plays out on it
  (its own egg, its own signpost, its own hatch; H-1/H-2 scoped to ITS window only).
- **Flagship demo (note for the gallery): the Mini hatch becomes, literally, "a new
  island rises next to the MacBook island."** The mini-hatch runbook executes on the
  Mini; its chronicle exhaust registers as a source; the MacBook's renderer shows the
  new island rising while the Mini's own dashboard runs the desk interview. This is
  the section's acceptance image.

### 10.6 Staging + open items

| Stage | Ships |
|---|---|
| **v1b** | Detection + chooser + "Hatch a new cabinet…" explicit choice; registry create/append + legacy-cabinet registration offer; island NAMING at the signpost (name→slug→cabinet.id, registry-uniqueness); per-install genesis gates (§0); namespace bundle ALLOCATED + recorded (even though only one cabinet runs) |
| **v2** | Full multi-run: MULTI-CABINET-READINESS executed (REDIS_URL db-index everywhere, label prefixes, tmux//tmp/caches namespacing, CLAUDE_CONFIG_DIR per cabinet, port allocation live); two-cabinet side-by-side drill green; shared-world multi-source renderer + cabinet-island anchors + island-rises choreography (rides WORLD-E0B-MINI) |
| **v3** | Peers config surface goes live (typed envelopes, receiver-gated, default OFF; propose-only federation) |

Open items (Captain calls when they ripen): cross-machine chronicle transport (Mini →
renderer host); which dashboard is "the" archipelago renderer vs every dashboard
rendering all registered sources (default: every dashboard renders all, read-only —
no designated master); mother-cabinet migration timing (bare→prefixed namespaces).

## 11. GATEKEEPER STALENESS ADDENDUM (2026-07-10, Wave-D appshell — supersedes the right-click→Open clauses in §2/§7/§8)

This design's stranger Gatekeeper passage (§2 preconditions row 3 "right-click →
Open → Open, once", §7.1 "Gatekeeper right-click→Open documentation", §7.2's
commercialization-lane framing, and the §8 FAQ line) predates the Wave-D appshell
v0.5 empirical matrix and is STALE as written:

- **The right-click→Open bypass for quarantined unsigned apps was REMOVED in
  macOS 15 Sequoia and stays gone in Tahoe.** The real passage on a quarantined
  unsigned/ad-hoc app is Settings ▸ Privacy & Security ▸ **Open Anyway** → second
  warning → admin auth. Tahoe 26.2 reports: some unsigned apps are declared
  "damaged" and auto-trashed with NO Open Anyway offered — that lane can dead-end
  entirely. Matrix + transport table of record:
  `docs/runbooks/hatch-appshell-v05-2026-07-10.md` ("Hand-transport + Gatekeeper
  (2026 reality)"); the AirDrop/browser row on a 26.2 box still carries its
  honest-empty manual-test slot there.
- **Quarantine-free transports are unaffected**: scp / curl / local share / USB
  set no quarantine xattr, and the ad-hoc-signed app runs on double-click on
  Apple Silicon (the v0.5 recommended hand-transport lane).
- **Consequence for the V1B stranger bar**: a downloaded-zip distribution cannot
  honestly document "two clicks with a picture" — the download lane needs either
  the Open-Anyway ceremony documented (more clicks, admin auth, may dead-end on
  26.2+) or the Developer ID + notarization item pulled FORWARD from the
  commercialization lane for any download-transport distribution. Hand-transport
  (scp/USB) keeps the original low-ceremony promise. This is a V1B design input,
  not a ruling — the lane choice stays with the V1B build + Captain.

Per append-only doctrine the original clauses stand un-edited above; where they
conflict with this addendum, the addendum wins.

---
*Sources: `.claude/skills/cabinet-init/SKILL.md` · `cabinet/scripts/generate-instance.py`
· `docs/plans/world-unified-spec-v2-2026-07-09.md` (+ §15 addenda; world-next track docs)
· `docs/runbooks/mini-hatch-tonight-2026-07-07.md` · `docs/plans/operative-egg-ledger-2026-07-07.yml`
GENESIS rows ONBOARD-1/2, GOV-UNLOCK-UX, WORLD-V1A/V1B, WORLD-E0B/WORLD-E0B-MINI ·
`cabinet/dashboard/src/middleware.ts` + `api/auth/reauth-*` (Spec 034) · Corridor plan
analysis 2026-07-09 (security context confirmed: constant-argv shell bridge, dual-layer
auth, constant-path writes) · multi-cabinet evidence pass 2026-07-09 (164 bare
`cabinet:*` key files, 19 REDIS_URL sites, `~/.cabinet/` machine home,
CLAUDE_CONFIG_DIR pilot in start-officer-mac.sh, cce6e601 namespacing residual).*
