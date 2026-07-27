# Mini Hatch — Tonight (2026-07-07) — THE Runbook

**What this is.** The exact, dress-rehearsed sequence for hatching Captain's
Cabinet on the Mac Mini tonight. Every step below was executed twice today in
a scratch clean-room rehearsal (synthetic captain "Ada Testburg", org flavor,
portfolio shape) against commit `b1e41a70`; the three stalls rehearsal 1 hit
were root-cause-fixed (`b1b97e97`, `cce6e601`, `b1e41a70`) and rehearsal 2
re-ran the full sequence on the fixed tree. What could not be exercised in a
rehearsal (live launchctl bootstrap, real tokens, TCC clicks) is called out
honestly in **Mini-manual steps** and **Residual stalls** below — those are
tonight's only unknowns.

**Success bar (Proof P3, `docs/plans/operative-egg-ledger-2026-07-07.yml`):**
≤ 1 concierge-day, with (a) the Chair live on `NullPersonalSource`
honest-empties (no captain data, no screenpipe, no source binding required to
boot), (b) the revocation drill fail-closed, (c) **zero hand-edits beyond the
documented steps in this runbook**. Any hand-edit not listed here is a P3
failure — stop and record it, don't improvise.

Generic sister doc: `cabinet/docs/mac-mini-setup.md` (the full Flavor-B
runbook this one instantiates). Deep detail: `cabinet/docs/mac-mini-deploy-runbook.md`.

---

## 0 — Prerequisites (before touching the repo)

| Requirement | Why | Check |
|---|---|---|
| macOS 14+ on Apple Silicon (rehearsed on macOS 26.6 / Darwin 25.6) | launchd user agents + Homebrew paths assume `/opt/homebrew` | `sw_vers` |
| Logged-in user session + auto-login + no sleep | the org lives in launchd **user** agents | `sudo pmset -a sleep 0 disksleep 0` |
| Homebrew + `git`, `node`, `gh`, `jq`, `tmux`, `redis`, `gettext` | `gettext` provides `envsubst` (plist rendering); redis is the trigger bus | `brew install node gh jq tmux redis gettext` |
| `python3.12` with `pytest` + `pyyaml` | the suite, the null-hatch gate, and generators are pinned to 3.12 semantics; `setup-mac.sh` installs/checks this exact version | Usually automatic; manual recovery: `brew install python@3.12 && python3.12 -m pip install pytest pyyaml` |
| Claude Code CLI | officers ARE Claude Code sessions | `npm i -g @anthropic-ai/claude-code && claude --version` |
| `gh auth login` | the fork is private; clone + CI checks need it | `gh auth status` |
| Tailscale — **optional** | remote SSH into the Mini afterwards; nothing in the hatch needs it | `brew install tailscale && sudo tailscale up` |
| Redis running with AOF | trigger durability across reboots | `brew services start redis && redis-cli ping` → PONG |

NOT prerequisites (deliberately): screenpipe, a personal vault, Monday/Notion
credentials, TCC grants, code-signing. The clean-room premise is enforced by
CI (`framework/tests/test_no_screenpipe_in_core.py`) and proven by the
null-hatch gate below.

## 1 — Clone from origin master

```bash
mkdir -p ~/work && cd ~/work
git clone https://github.com/nate-refslund/captains-cabinet.git captains-cabinet
cd captains-cabinet
git log -1 --oneline   # expect b1e41a70 or later — the rehearsal fixes MUST be present
```

Stay on the default branch (master). There is no `mac-native` branch; master
IS the ship branch (rehearsal-1 stall, fixed in docs at `b1e41a70`).

Then host bootstrap:

```bash
bash cabinet/scripts/setup-mac.sh          # idempotent; installs gaps, starts redis,
                                           # creates dirs, .env wizard, fast proofs
                                           # (null-hatch + P-b subset; full pytest
                                           # suite = --full-suite; sensors =
                                           # --with-sensors; dashboard = --with-dashboard)
bash cabinet/scripts/setup-mac.sh --check  # must exit 0
```

## 2 — The cabinet-init interview (INTERACTIVE)

```bash
claude
> /cabinet-init
```

This is a conversation, not a form — the skill interviews you and writes
`instance/config/cabinet-init.answers.yml`. What the answers mean (the
rehearsal's synthetic answers file is the shape reference):

- `captain.name / timezone / telegram_chat_id` — how officers address you,
  what clock every Captain-facing time renders in, where the Chair DMs land.
- `cabinet.id` — THIS deployment's key (e.g. `<yourname>-mini`). Outcomes and
  posture files are pinned to it; an inherited file with another id is inert.
- `cabinet.org_shape` — `portfolio` (one persistent Chair + on-demand lane
  CEOs; what the rehearsal used and what the Mini should use) vs `work`
  (five functional officers, single product).
- `lanes[]` — one entry per product: slug, repos, task system, Neon/Vercel
  project names. Drives generated contexts/projects/lane-CEO agents.
- `autonomy.posture: propose_first` + `flavor: org` +
  `target_posture: guardian` — the safe hatch posture. `flavor: org` makes
  the generator bind `sources.yml` to `OrgSource` (the cabinet's OWN memory)
  and NO personal estate; sovereign is a later Captain-only attested ritual
  (§2.6 of mac-mini-setup.md), never part of the hatch.
- `integrations.telegram.bot_token_env` — the env var NAME
  (`TELEGRAM_COS_TOKEN`); the interview never takes the token value.

## 3 — Generate the instance

```bash
python3.12 cabinet/scripts/generate-instance.py --dry-run   # preview
python3.12 cabinet/scripts/generate-instance.py
# zero-question fast lane (what hatch.sh --defaults runs):
python3.12 cabinet/scripts/generate-instance.py --defaults --adopt
```

**This clone ships MY committed `instance/`** (the MacBook deployment's
platform.yml officers block, sources.yml, contexts). The generator will
REFUSE to clobber it — that refusal is correct behavior, and the cue for:

```bash
python3.12 cabinet/scripts/generate-instance.py --adopt
```

`--adopt` (built from rehearsal-1's worst stall, `b1b97e97`) archives every
conflicting file to `instance/_pre-adopt-<stamp>/` (nothing deleted) and
generates the new captain's instance fresh. It also writes
`instance/config/active-project.txt` (first lane slug) — without it
`bootstrap-roles.sh` exits 1 (rehearsal-1 stall #2, same commit).

## 4 — Activation steps (generator prints these; do them in order)

```bash
# 4.1 Preset
echo portfolio > instance/config/active-preset

# 4.2 GERMLINE EDITS (Captain's hands, documented = allowed):
#     add the lane-CEO entries the generator PRINTS into
#       cabinet/mcp-scope.yml            (agents: block)
#       cabinet/officer-capabilities.conf (capability rows)
#     On a FRESH clone these files are not schg-locked yet — plain edits work.
#     (Rehearsal 2 applied exactly these two edits for testburg-store-ceo.)

# 4.3 Bot token (see Mini-manual steps below) into cabinet/.env:
#     TELEGRAM_COS_TOKEN=<value>    # chmod 600; never committed

# 4.4 Seed the roster (reads active-project.txt)
bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml

# 4.5 Assemble the runtime
bash cabinet/scripts/load-preset.sh
#     (also materializes instance/config/posture.yml + trust-ladder.yml from
#     their .example twins when absent — guardian/floor defaults; existing
#     files or symlinks are never overwritten)
```

TCC grants (`grant-mac-permissions.sh`) are **NOT in tonight's path** — see
Mini-manual steps.

## 5 — PROOF sequence (run before any officer boots; all must be green)

```bash
# P-a  Null-hatch gate — the egg boots with NO captain data, NO screenpipe,
#      NO source binding; sandbox copy of the COMMITTED tree, HOME redirected,
#      ~/.screenpipe present-but-unreadable so latent personal reads fail LOUD.
bash cabinet/scripts/null-hatch.sh                      # exit 0 required

# P-b  Clean-room ratchets (subset of the suite; fast)
python3.12 -m pytest framework/tests/test_clean_room.py \
  framework/tests/test_no_screenpipe_in_core.py \
  framework/tests/test_no_launcher_hardcode.py -q       # all pass required

# P-c  Dry renders — command assembly + plist render, ZERO side effects.
#      Both reject unknown flags (exit 64); start-officer-mac.sh refuses to
#      touch a tmux session owned by another checkout (exit 65) — rehearsal-1's
#      sharpest finding (it killed the live Chair from a scratch clone), fixed
#      + regression-tested in cce6e601 (test-mac-dry-run.sh 14/14).
bash cabinet/scripts/start-officer-mac.sh cos --dry-run
bash cabinet/scripts/deploy-mac.sh --officer cos --dry-run

# P-d  REVOCATION DRILL (fail-closed proof) — with redis up but BEFORE trusting
#      the org: activate the kill switch, prove a booted officer halts on its
#      next tool call (pre-tool-use hook), then deactivate.
REDIS_URL=redis://localhost:6379 bash cabinet/scripts/kill-switch.sh activate
REDIS_URL=redis://localhost:6379 bash cabinet/scripts/kill-switch.sh status   # ACTIVE
# ... boot the Chair (step 6), observe it refuse tool calls while ACTIVE ...
REDIS_URL=redis://localhost:6379 bash cabinet/scripts/kill-switch.sh deactivate
```

Do not proceed past a red gate. P-a red = the tree leaks personal state into
framework core: file it upstream, do not patch on the Mini.

## 6 — Deploy the Chair + measurement plane

```bash
# Chair only — lane CEOs are on-demand consultants, no persistent agent:
bash cabinet/scripts/deploy-mac.sh --officer cos

# Measurement-plane plists (verdict supply: verifier, probe-github,
# probe-vercel, probe-sentry, fidelity-f1, regression-corpus,
# graduation-transitions) — rendered from cabinet/services.yml:
python3.12 cabinet/scripts/generate-plists.py
for p in cabinet/launchd/generated/*.plist; do plutil -lint "$p"; done   # all OK
# bootout-first = idempotent on re-runs (no-op on a fresh box):
for p in cabinet/launchd/generated/*.plist; do launchctl bootout gui/$(id -u) "$p" 2>/dev/null || true; launchctl bootstrap gui/$(id -u) "$p"; done
launchctl print gui/$(id -u) | grep com.cabinet | head    # loaded + last-exit 0
```

Verify: `bash cabinet/scripts/health-check.sh`, `tmux attach -t officer-cos`
(detach `C-b d`), Telegram round-trip with the Chair. Then ratify seed
outcomes in `instance/config/outcomes.yml` (`status: active` +
`captain_ratified: true`, keyed to YOUR `cabinet.id`).

## 7 — First receipt (Perfect Cabinet PC-A, 2026-07-09)

After the proofs (and independent of the launchd move-in above), land the
LOCAL first receipt — the org's genesis output on disk, no Telegram needed:

```bash
bash cabinet/scripts/first-briefing.sh --local
# prints: FIRST BRIEFING RECEIPT: instance/memory/first-briefing-<date>.md
#         (N proposed outcome cards, propose-only)
```

`hatch.sh` runs this as its `first-receipt` step automatically and measures
**TTFR** (proofs-done → first-receipt) in its flight log — see
`docs/runbooks/hatch-v0-2026-07-09.md`. On a live deployment, echo the
genesis proposal into the runtime ledger afterwards:
`cabinet/scripts/append-interface.sh captain-decisions` with the entry on
stdin (hook-guarded, append-only — a hatch-time step, never a build-session
write).

## Mini-manual steps (human-only, with WHY)

1. **Chair bot token — BotFather → `cabinet/.env`.** Telegram bot creation is
   a human conversation with @BotFather (`/newbot`, name it, copy the token).
   Put it in `cabinet/.env` as `TELEGRAM_COS_TOKEN=...` (chmod 600). WHY
   manual: tokens never ship in the repo (config keeps `TOKEN-TBD`; rehearsal
   proved the boot path warns-and-continues without secrets rather than
   crashing). Without it the Chair boots but is Telegram-dark.
   While `cabinet/.env` is open, also paste `VOYAGE_API_KEY=...` alongside
   `TELEGRAM_COS_TOKEN`. Optional — the org memory brain fail-softs to
   keyword-only (lexical) search without it (keyless degrade verified
   2026-07-07) — but recommended tonight for onboarding backfill quality:
   embeddings make the backfilled org memories semantically searchable,
   not just keyword-matchable.
2. **TCC grants — ONLY if calendar/computer-use is wanted. NOT needed for the
   base hatch.** macOS requires human clicks (`grant-mac-permissions.sh`
   walks them), grants are responsible-process-scoped, and they persist
   across reboots only for code-signed binaries
   (`cabinet/docs/mac-tcc-code-signing-gate.md`). Skip tonight; add later
   when a capability actually needs it.
3. **`launchctl bootstrap` of the measurement-plane plists** (step 6). WHY
   manual tonight: the rehearsal was constitutionally forbidden from loading
   scratch plists into the live gui domain, so only `plutil -lint` and the
   render path are rehearsal-proven — the first real `launchctl bootstrap`
   happens on the Mini. If an agent fails: `launchctl print gui/$(id -u)/<label>`
   for last-exit; PATH gaps are the historical failure class.
4. **Healthchecks.io dead-man registration.** Create the checks (per
   `cabinet/services.yml` expected-floors; at minimum verifier, drill-failed
   and **`ledger-liveness`** — the drill's target since the 2026-07-26
   re-point off the Captain's personal screenpipe sensor), assign ALERT
   CHANNELS (the 2026-07-02 drill found API-created checks ship with EMPTY
   channel lists — an alarm wired to nobody), put the ping/API keys in
   `cabinet/.env` (names-not-values everywhere else). The weekly
   `healthchecks-drill.py` then exercises the alarm end-to-end. Skipping this
   step is allowed: with no keys in `cabinet/.env` the drill logs one
   `DRILL_SKIP` line and exits 0 rather than paging every Sunday.

## Rollback (nothing severs)

The hatch is fully contained in: the clone directory, `gui/$(id -u)` launchd
agents, a tmux session, and local Redis keys. To roll back completely:
`launchctl bootout gui/$(id -u)/com.cabinet.<label>` for each loaded agent
(or just power the Mini off), `tmux kill-server`, `rm -rf ~/work/captains-cabinet`.
No external state was created except the Telegram bot (delete via BotFather)
and Healthchecks checks (delete in UI) — neither can act on anything by
itself. Nothing on the MacBook deployment is touched by any step here
(cross-checkout takeover guard, `cce6e601`, enforces this even on operator
error).

## Residual stalls — honest list from rehearsal 2

Rehearsal 1's three stalls (missing `active-project.txt`, no adoption path
over a shipped `instance/`, and the dry-run arg fall-through that killed the
live Chair from a scratch clone) are FIXED and regression-tested. What
rehearsal 2 still could not make hands-free — **5 mini-manual residuals**,
all documented above, none blocking:

1. Germline activation edits (step 4.2): the generator PRINTS the
   mcp-scope.yml / officer-capabilities.conf lane-CEO entries but cannot
   write them (germline discipline). ~2 min of copy-paste per lane.
2. Bot token via BotFather (Mini-manual 1) — inherently human.
3. TCC grants (Mini-manual 2) — inherently human; skipped for base hatch.
4. First live `launchctl bootstrap` (Mini-manual 3) — unrehearsable off-Mini
   by constraint; plist syntax + render path proven, load step is not.
5. Healthchecks registration + channel assignment (Mini-manual 4) — needs
   the account owner.

Known non-stall residual: full `CABINET_ID` namespacing of tmux session
names / `/tmp/cabinet-runtime` / `~/Library/Caches/cabinet` is deferred
(follow-up noted in `cce6e601`); irrelevant on a one-checkout Mini, matters
only for multi-checkout boxes (the takeover guard covers the observed hazard).

## Germline handback list (next unlock window, live MacBook repo)

Tonight's Mini clone starts unlocked (schg does not survive `git clone`), so
none of these block the hatch. On the LIVE repo, queue for the next Captain
unlock window (`sudo cabinet/scripts/germline-lock.sh unlock` → edit →
`lock`):

1. **Lane-CEO scope seam**: a managed block (or generator-staged patch file)
   so `generate-instance.py` can stage `cabinet/mcp-scope.yml` +
   `cabinet/officer-capabilities.conf` entries for Captain apply instead of
   copy-paste (residual stall 1).
2. **CG-2** (carried): `framework/acting/run_action_lane.py` signal-gather
   rewire onto PersonalSource — deferred while the parallel session owned
   the file.
3. **R137 retroactive ratification** (carried from the 2026-07-07 seal):
   deleted files inside locked `memory/golden-evals/` lack a companion
   amendment doc — ratify or revert.
4. **eval-021-brain-retrieval-quality.md** — Captain-staged germline entry,
   still uncommitted-by-design; commit it inside an unlock window.
5. If tonight's Mini is ever posture-upgraded: `instance/config/posture.yml`
   ritual + `germline-lock.sh lock` on the Mini itself (mac-mini-setup.md §2.6).

## Flight recorder (added 2026-07-07 — wrap the hatch, gate the exit)

Two additions that cost nothing and make tonight auditable end-to-end:

### 1. Record the whole hatch in a `script(1)` transcript

**Before step 1** (immediately after opening the terminal on the Mini), start
a typescript that captures every command and every byte of output for the
entire hatch — including the stalls, which are exactly what P3's
"zero hand-edits beyond documented steps" bar needs evidence for:

```bash
mkdir -p ~/hatch-logs
script -q ~/hatch-logs/mini-hatch-$(date +%Y%m%d-%H%M%S).typescript
# ... the ENTIRE runbook (steps 1-6 + proofs) runs inside this shell ...
```

Rules:
- **Everything** runs inside the `script` shell. If you must open a second
  terminal (e.g. `tmux attach` verification), start a second transcript
  there — never an unrecorded shell.
- On any stall: keep typing inside the transcript (the diagnosis IS the
  record), and note the wall-clock time inline with `date` before and after.
- End with `exit` (closes the typescript cleanly), then copy
  `~/hatch-logs/` off the Mini alongside the timed hatch log P3 asks for.
  The transcript is also raw material for the ORG-SENSES-1 transcript-digest
  organ (operative-egg-ledger row) — do not delete it after the hatch.

### 2. `cabinet-doctor` is the FINAL acceptance gate

After step 6 (Chair + measurement plane live, Telegram round-trip done),
the hatch is not "done" until the deterministic config-liveness prober says
so:

```bash
bash cabinet/scripts/cabinet-doctor.sh        # exit 0 required
```

It probes every `cabinet/services.yml` row ↔ loaded launchd job ↔ fresh log,
every settings hook entry → existing script, MCP layers env-resolve
(names only, never values), skill frontmatter (zero leading bytes),
mcp-scope grants registered, statusline exit 0, Redis PING, and a killswitch
DRY status check. Also load its daily row: `generate-plists.py` renders
`com.cabinet.cabinet-doctor.plist` with the rest of the measurement plane in
step 6 — bootstrap it there like the others.

Reading the verdict on a fresh Mini:
- `CABINET_DOCTOR GREEN` → hatch accepted; append the GREEN line + the
  transcript path to the timed hatch log.
- `DEAD service <row> — launchd job not loaded` for rows you deliberately
  did NOT bootstrap tonight (this runbook loads the Chair + measurement
  plane only) → expected on the Mini; record which rows, and either
  bootstrap them or flip them `disabled: true` in `services.yml` on the
  Mini clone so the manifest tells the truth (that edit is documented here,
  so it is not a P3 hand-edit violation).
- Any OTHER `DEAD` line → a real stall. Do not hand-patch around it —
  record it (transcript already has it) and fix root-cause or file it
  upstream, per the P3 bar.
- `WARN`/`WAIVED` lines do not block acceptance (waivers cite their pending
  germline amendments).
