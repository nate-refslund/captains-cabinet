# Mac Mini Clone — 1-then-3 Fleet Setup

Captain's fleet plan: validate 1 Mac mini, then clone the setup to 3 (per Captain msg 2603 Q3 ratification). This guide walks the per-Mac setup for Macs 2 and 3 after Mac 1 (canonical image) is validated through the full Spec 057-065 Mac migration arc.

**Mac 1 (canonical):** Follow `docs/mac-mini-setup.md` end-to-end (Phase 1-8).

**Macs 2-3 (clone):** Inherits many account-scoped resources from Mac 1; only per-machine setup needed.

## Skip-list — inherited from Mac 1 (DO NOT redo on Macs 2-3)

These resources are account-scoped or already-provisioned and **do not** need to be redone for each Mac:

| Resource | Why skip |
|----------|----------|
| Apple Developer Program enrollment | One per developer account, NOT per machine. Mac 1's enrollment covers Macs 2 + 3. Code-signing identity transfers via Keychain export. |
| Developer ID Application certificate | Issued once per developer account; export from Mac 1's Keychain, import on Macs 2 + 3. |
| BotFather bot creation | Bots are tokens, not per-machine. Single CoS bot already created on Mac 1; reuse the same token. |
| ElevenLabs voice IDs | Voices are account-scoped; reuse Mac 1's voice config. |
| Neon Postgres project | Single project shared across the fleet; same connection string. |
| Notion workspace + sub-processor DPA | Account-scoped. |
| Tailscale account | Single account; Macs 2-3 join the same tailnet via auth-key. |
| Vercel project | Account-scoped; deployment infrastructure shared. |

## Per-machine setup — required for Macs 2-3

These steps are MACHINE-level and must be done fresh on every Mac:

1. **Unbox + initial macOS setup** (per `docs/mac-mini-setup.md` Phase 1 Checkpoint 1.1)
2. **FileVault disable** (per Captain msg 2603 Q1 — STEP-internal deployment)
3. **Homebrew + CLIs install** (per Phase 1 Checkpoint 1.4: node + postgresql@17 + redis + gh + tailscale + cua-driver-pinned + screenpipe + apcupsd)
4. **`pmset -a sleep 0`** (prevent sleep — per Phase 1 Checkpoint 1.3)
5. **macOS permissions grant** (Accessibility + Screen Recording + Full Disk Access for the Cabinet officer-runner binary — per Phase 1 Checkpoint 1.8)
6. **Tailscale join via auth-key** (joins the existing Mac 1 tailnet — per Phase 1 Checkpoint 1.9)
7. **LaunchAgent install** via `deploy-mac.sh` (envsubst-renders templates + bootstraps services — per Phase 2)
8. **apcupsd config** (UPS-specific per-machine; Phase 1 Checkpoint 1.10)
9. **Code-signing identity import from Keychain export** (per Phase 1 Checkpoint 1.11 in Spec 058 v1.2 — without this, TCC permissions don't persist across launches)
10. **Cabinet repo clone** from GitHub (`gh repo clone nate-step/captains-cabinet ~/work/captains-cabinet`) — pulls in framework + presets + instance + scripts (mac-native branch picks up Phase 0 host-state tarball on first officer start)

## Effort estimate per Mac (2 or 3)

**Realistic: 2-3 hours focused per Mac**, mostly hands-on macOS install steps. Much faster than Mac 1 (which had spec-arc-folding + integration discovery overhead).

## Validation gate per cloned Mac

Same gate as Mac 1 Phase 7 soak: 48h under real workload with all 5 officers active. Pass = clone is canonical-equivalent.

## Fleet positioning

After 3 Macs validated:
- **Mac 1** = primary product Cabinet (canonical image source)
- **Mac 2** = second product Cabinet (commercial Phase 1)
- **Mac 3** = Reserve / staging (failover for either, or experimental preset deployments)

Per Captain Mac Migration Directive (msg 2599) — exact role per Mac decided at Phase 8 sign-off.

## Per Spec 065 v1.1 Checkpoint 8.2 + CTO v1.1 #6 skip-list expansion.
