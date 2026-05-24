# Spec 065 — Mac Migration Phase 8 Plan (Documentation + Release)

- **Version:** v1.1 (CTO 6 MUST-fold)
- **Date:** 2026-05-23 (v1.0 07:50 UTC → v1.1 07:55 UTC)
- **Author:** CoS (autonomous per Captain msg 2605, 2607, 2612)
- **Status:** READY for CTO re-confirm + Captain execution

**v1.1 changelog — CTO 6 MUST-fold findings (msg 2026-05-23 07:10 UTC):**
- **(1) README dual-edit eliminated 8.1:** v1.0 said "edit root AND Mac-deployed copy." Wrong — Mac copy is a `git pull` consequence, not a separate edit target. Single source of truth: `/opt/founders-cabinet/README.md` on master. Mac picks it up via pull.
- **(2) Phase 0 vs Phase 8 snapshot purpose 8.5:** Spec 057 Phase 0 snapshot = pre-cutover rollback target. Phase 8 snapshot = Hetzner-suspension state. Different purposes; both kept. 8.5 clarifies.
- **(3) pg17 client explicit 8.5:** `pg_dump` invocation must use the pg17 client from Homebrew (Phase 1 1.4) for Neon Postgres 17 compatibility (Phase 0 had pg_dump 16 vs Neon 17 incident).
- **(4) BotFather rollback 8.5:** revoke is one-way — to restore Hetzner officers we must regenerate new tokens + update Hetzner `.env`. Procedure made explicit.
- **(5) Tag uniqueness check 8.4:** `git tag -l v1-mac-native` MUST be empty before `git tag -a v1-mac-native ...` to avoid overwriting an existing tag.
- **(6) Clone skip-list 8.2:** `docs/mac-mini-clone.md` clarifies that Apple Developer Program enrollment is one-time per developer account — Macs 2-3 inherit (no re-enrollment). Same for BotFather bots, ElevenLabs voice IDs, etc.

**Cross-spec META (caught during Phase 8 drafting):** `shared/interfaces/captain-patterns.md` + `captain-intents.md` + `captain-decisions.md` are gitignored runtime state on the Hetzner deployment. On Mac cutover they regenerate blank from `cabinet-bootstrap.sh`. Phase 0 (Spec 057) host-state tarball + Phase 8 export-state.sh manifest MUST include these 3 files. Folded forward to Spec 057 v1.1 (separate spec amendment).

- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 8 ("Documentation + release — 0.5 day")
- **Predecessors:** Spec 057-064 (Phases 0-7)
- **Successor:** None (terminal phase of Mac migration arc)

---

## 1. Phase 8 goal (from directive)

Documentation reflects native-Mac as the canonical deployment. `v1-mac-native` release tag landed. Hetzner cabinet suspended (frozen for rollback). The 1-cabinet-then-clone-to-3 fleet plan is documented + ready to execute (Captain msg 2603 ratified 1-then-clone-to-3).

## 2. Inputs from Phase 7

- All 5 officers running stably as LaunchAgents
- 48h soak validated under real Sensed workload
- Observability live (heartbeat-watchdog + cost-summary + log rotation)
- Phase 7 baseline doc committed

## 3. Captain ratifications carried forward

- **A11 Library + /tasks canonical** — README + setup guides emphasize this
- **Mac Migration Directive §Risk Mitigation:** Hetzner stays alive in frozen state for fast rollback (NOT decommissioned)
- **Captain reader-friendly tone (msg 2583):** README + setup guides plain language

## 4. Checkpoint structure

Phase 8 decomposes into **7 checkpoints**. Directive estimates 0.5 day; realistic 3-4 hours focused.

### Checkpoint 8.1 — Update root `README.md` for native-Mac deployment

- **Pre-conditions:** Phase 7 complete.
- **Actions (v1.1 CTO #1 — single-edit):**
  1. Edit `/opt/founders-cabinet/README.md` ONLY (master branch source of truth). Mac copy at `~/work/captains-cabinet/README.md` picks up the change via `git pull` on next sync — NOT a separate edit target.
     - Update "Quick start" section to describe Mac mini deployment as canonical
     - Add "Hetzner Docker deployment (legacy/dev SaaS)" subsection beneath
     - Reference Spec 058 setup process (Phase 1 unbox+install) as the new bootstrap path
     - Reference Spec 050 v1.2 Tier 1 (refslund.ai backend Docker) vs Tier 2 (Customer Mac native) two-tier architecture
  2. After commit + push to `mac-native` (and merge to master), run `git pull` on Mac to sync — verifies single-source-of-truth flow.
- **Golden eval:**
  - README's "Quick start" section first paragraph mentions Mac mini + launchd
  - Hetzner Docker referenced only as "legacy" or "dev/SaaS"
  - Tier 1 + Tier 2 distinction explicit
- **Rollback:** `git revert`.
- **Effort:** 30 min.

### Checkpoint 8.2 — Update `docs/` setup guides

- **Pre-conditions:** 8.1 PASS.
- **Actions:**
  1. Write `docs/mac-mini-setup.md` consolidating Phase 1 (Spec 058) + Phase 2 (Spec 059) checkpoints into a step-by-step guide for a fresh Mac mini
  2. Write `docs/mac-mini-clone.md` — the 1-then-clone-to-3 fleet plan per Captain msg 2603:
     - Snapshot the validated 1-cabinet image (via Time Machine + Restic per Spec 058 + 057)
     - On new Mac mini: restore from snapshot OR re-run mac-mini-setup.md
     - Decision: re-run setup.md is preferred (idempotent + verified) over snapshot-restore (couples macOS user state to deployment state)
     - **(v1.1 CTO #6) Skip-list for Macs 2-3 (one-time setup steps inherited from Mac 1):**
       - Apple Developer Program enrollment — one per developer account, NOT per machine
       - BotFather bot creation — bots are tokens, not per-machine. CoS bot already created on Mac 1; reuse.
       - ElevenLabs voice IDs — voices are account-scoped, not per-machine. Reuse.
       - Neon Postgres project — single project shared across the fleet
       - Tailscale account — single account, Macs 2-3 join the same tailnet via auth-key
     - **Per-machine setup steps for Macs 2-3:** unbox + FileVault disable + Homebrew + pmset + permissions grant + Tailscale join (via auth-key) + LaunchAgent install + apcupsd (UPS-specific).
  3. Update `docs/migration-phaseN-baseline.md` index file (or create `docs/README.md` index pointing to all phase baselines)
- **Golden eval:**
  - `docs/mac-mini-setup.md` exists with all Phase 1 + Phase 2 substeps
  - `docs/mac-mini-clone.md` exists with the 1-then-3 fleet plan
  - Phase baseline docs (057-064) all indexed
- **Rollback:** `rm` new docs; `git revert` for index changes.
- **Effort:** 1-1.5 hours.

### Checkpoint 8.3 — Update `framework/README.md` + `presets/README.md`

- **Pre-conditions:** 8.2 PASS.
- **Actions:**
  1. Edit `framework/README.md`:
     - Add subsection on constitution-base clauses added in Mac migration: Lead-only Telegram (Spec 060), Lead-only computer-use (Spec 061)
     - Note these are framework-level (not preset-level) per cross-spec META ratification
  2. Edit `presets/README.md`:
     - Add note that current `work` preset does NOT override the Lead-only clauses (i.e., they apply uniformly)
- **Golden eval:**
  - `grep -c 'Lead-only Telegram\|Lead-only computer-use' framework/README.md` returns ≥2
- **Rollback:** `git revert`.
- **Effort:** 30 min.

### Checkpoint 8.4 — Tag `v1-mac-native` release

- **Pre-conditions:** 8.1-8.3 PASS.
- **Actions (v1.1 CTO #5 — uniqueness check first):**
  1. **Uniqueness check before tag creation** — refuse to clobber an existing tag:
     ```bash
     if git tag -l v1-mac-native | grep -q .; then
       echo "ABORT: tag v1-mac-native already exists. Bump to v1.1-mac-native or delete the stale tag first."
       exit 1
     fi
     ```
  2. From `mac-native` branch:
     ```bash
     git tag -a v1-mac-native -m "Mac mini native deployment — canonical for this Captain.
     
     Phase 0-8 complete:
     - Phase 0 (Spec 057): pre-migration baseline
     - Phase 1 (Spec 058 v1.1.1): Mac unbox + install
     - Phase 2 (Spec 059 v1.1): native launchd cabinet
     - Phase 3 (Spec 060 v1.1): Lead-only Telegram topology collapse
     - Phase 4 (Spec 061 v1.1): cua-driver + Lead-only computer use
     - Phase 5 (Spec 062 v1.1): Screenpipe integration
     - Phase 6 (Spec 063 v1.1): Cabinet worktrees + adapter contract
     - Phase 7 (Spec 064): full officer rollout + observability + 48h soak
     - Phase 8 (Spec 065): documentation + release
     
     Hetzner cabinet suspended; canonical deployment is Mac mini native."
     git push origin v1-mac-native
     ```
  2. (Optional) Promote `mac-native` branch to default branch on GitHub if Captain ratifies. Default is to keep `master` as the canonical branch (Captain's Hetzner cabinet still runs from `master`) and have `mac-native` track Mac releases. Hold this decision for Captain.
- **Golden eval:**
  - `git tag -l v1-mac-native` returns 1
  - `git ls-remote --tags origin v1-mac-native` returns the tag
- **Rollback:** `git tag -d v1-mac-native` + `git push --delete origin v1-mac-native` (only Captain-authorized).
- **Effort:** 10 min.

### Checkpoint 8.5 — Suspend Hetzner cabinet (frozen rollback state)

- **Pre-conditions:** 8.4 PASS; v1-mac-native release tag landed; soak validates Mac is canonical.
- **Actions (Captain hands-on or CoS-coordinated):**
  1. On Hetzner host, stop all officer containers (don't destroy): `docker stop $(docker ps -q --filter "name=cabinet-")` — keeps state intact
  2. **(v1.1 CTO #2 — snapshot purpose distinction)** This Phase 8 snapshot captures the *Hetzner-suspension* state — *what Hetzner looks like at the moment we stopped*. Distinct from Spec 057 Phase 0 snapshot which captured the *pre-cutover* state. Both kept; they answer different rollback questions ("undo the cutover" vs "restore the last-known-good Hetzner").
  3. Snapshot Hetzner Postgres + Redis state (v1.1 CTO #3 — explicit pg17 client):
     ```bash
     # MUST use pg17 client (Homebrew Phase 1 install) — Neon is Postgres 17
     /opt/homebrew/opt/postgresql@17/bin/pg_dump "$NEON_CONNECTION_STRING" > hetzner-suspend-postgres.sql
     redis-cli -h <hetzner-redis> BGSAVE  # then scp the .rdb snapshot off-Hetzner
     ```
  4. Tag Hetzner state in git: `git tag -a v0-hetzner-suspended -m "Hetzner cabinet suspended <date>; rollback target."` on whatever Hetzner commit was last live
  5. Document rollback procedure in `docs/hetzner-rollback.md` (v1.1 CTO #4 — BotFather is one-way):
     - Restore Postgres + Redis from snapshots (Spec 057 paths)
     - `docker start` all containers
     - **BotFather note:** revoking a token is one-way. To restore Hetzner officers we must:
       1. `/mybots` → for each of 4 officer bots → **"API Token" → "Generate new token"** (creates fresh token; old one stays revoked)
       2. Update Hetzner `cabinet/.env` with the 4 new tokens (CTO_TOKEN, CPO_TOKEN, CRO_TOKEN, COO_TOKEN)
       3. Restart Hetzner officers so they pick up new tokens
     - Estimated rollback time: 30-60 min total (BotFather + .env + restart adds ~15 min vs naive `docker start` alone)
- **Golden eval:**
  - Hetzner containers stopped (verified via `docker ps` from Hetzner host or via Captain)
  - `v0-hetzner-suspended` tag landed
  - `docs/hetzner-rollback.md` exists + has all steps
- **Rollback:** `docker start` reverses the suspension; no irreversible action taken.
- **Effort:** 30-45 min (Captain hands-on for Hetzner-side docker stop unless CoS still has Hetzner access).

### Checkpoint 8.6 — Migration arc retrospective (Captain digest)

- **Pre-conditions:** 8.5 PASS.
- **Actions:**
  1. Write `docs/mac-migration-retro.md`:
     - **What went well:** specific Phase-by-Phase callouts (e.g., Phase 6 safety guard saved dev-tasks territory; Phase 3 dispatch test validated Telegram collapse)
     - **What didn't:** any incidents from Phase 7 soak; fold-claim-vs-execute drift (Spec 050 + Spec 060 v1.1) → task #172 framework skill
     - **What we'd do differently:** any process improvements for future big-bang migrations
     - **Capability deltas Mac vs Hetzner:** cua-driver (new), Screenpipe (new), native launchd (new), restic + Time Machine (new vs Docker volumes), etc.
  2. CoS DMs Captain reader-friendly summary version (msg 2583 tone): "We're on Mac now. Here's what's different / what to expect / what to watch."
- **Golden eval:**
  - `docs/mac-migration-retro.md` exists with all sections
  - Captain receives reader-friendly DM summary
- **Rollback:** N/A — retrospective is informational.
- **Effort:** 1 hour.

### Checkpoint 8.7 — Phase 8 baseline doc + commit

- **Pre-conditions:** 8.1-8.6 PASS.
- **Actions:**
  1. Write `docs/migration-phase8-baseline.md`:
     - README + docs/ change diff summary
     - `v1-mac-native` tag SHA
     - Hetzner suspension confirmation + `v0-hetzner-suspended` tag
     - Migration retro doc pointer
  2. Commit + push.
- **Golden eval:** baseline doc on `mac-native` branch; Mac migration arc fully closed.
- **Effort:** 20 min.

## 5. Effort estimate (whole Phase 8)

**Realistic: 3-4 hours focused.** Directive's 0.5 day matches.

## 6. Stop-the-line gates

1. **8.4 release tag overwrites existing tag** (unlikely; mitigated by inspecting `git tag -l` first).
2. **8.5 Hetzner suspension irreversible** (would be a problem if rollback needed; we explicitly use `docker stop` not `docker rm` to keep state recoverable).

## 7. Phase 8 → terminal

When Phase 8 completes:
- Mac mini native is the canonical Cabinet deployment for this Captain
- Hetzner is frozen but recoverable (Time-bounded — Captain decides retire-Hetzner cutoff at later date)
- 1-then-clone-to-3 fleet plan documented and ready (Captain executes when budget/timing allows)
- Mac migration arc complete; next arcs: Personal Cabinet on Mac (deferred per msg 2603), refslund.ai commercial Cabinet build (Spec 050 v1.2 Tier 1 backend already on Hetzner — out of scope for this migration arc)

## 8. Sign-off

DRAFT ready for CTO tech review. Captain ratifies 8.4 (release tag) + 8.5 (Hetzner suspension trigger). All other checkpoints CoS-executable.
