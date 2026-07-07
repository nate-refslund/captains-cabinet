# Mac Mini Setup Runbook — Flavor-B hatch (clean-room)

End-to-end runbook for hatching Captain's Cabinet on a fresh Mac mini. This is
the **Flavor-B / personal-optional** path: the core install has **no
screenpipe, no personal vault, no external PM tool** — the same clean-room
premise CI itself enforces (`framework/tests/test_no_screenpipe_in_core.py`;
the null-hatch gate boots the tree with `~/.screenpipe` deliberately
unreadable). A personal sensing estate is an *optional add-on afterwards*
(Appendix A), never a prerequisite.

**Audience:** the Captain, hands-on for Phase 1 (physical Mac steps + TCC
clicks + tokens); everything in Phase 2 runs from a terminal / Claude Code
session on the Mini.

**Estimated time:** Phase 1 ~1-2 h; Phase 2 ~1 h to a booted Chair.

Sister docs: `cabinet/docs/mac-mini-deploy-runbook.md` (deep detail on
code-signing, LaunchAgents, soak, backups), `cabinet/docs/mac-mini-clone.md`
(second-Mini clone), `cabinet/docs/mac-tcc-code-signing-gate.md` (TCC
persistence).

---

## Phase 1 — Base Mac setup

### Checkpoint 1.1 — Unbox + initial macOS setup (~15 min, Captain hands-on)

1. Unbox the Mac mini, connect power + display + keyboard + Ethernet
2. Power on, complete initial macOS setup wizard:
   - User account: create a dedicated admin user (e.g. `cabinet`)
   - Set your timezone (the interview in Phase 2 records it for officers too)
   - Apple ID sign-in optional; Siri skip
3. Verify the Mac boots to desktop, then enable auto-login for the cabinet
   user (System Settings → Users & Groups) — the org lives in launchd *user*
   agents and needs a logged-in session

### Checkpoint 1.2 — FileVault decision (~5 min, Captain hands-on)

Your call. FileVault **off** means unattended reboots come back up without a
password at the console (simplest for a headless always-on box you physically
control). FileVault **on** is the right call if the Mini holds anything
sensitive and you can live with console unlock after power loss.

```bash
fdesetup status   # verify whichever state you chose
```

### Checkpoint 1.3 — Power management (`pmset`) (~2 min)

```bash
# Prevent sleep; cabinet officers + LaunchAgents must stay alive 24/7
sudo pmset -a sleep 0
sudo pmset -a disksleep 0
sudo pmset -a displaysleep 30   # display can sleep; system can't
pmset -g                        # verify
```

### Checkpoint 1.4 — Homebrew + CLI install (~20 min)

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Core dependencies — note: NO screenpipe here. The clean-room Mini runs no
# personal sensing stack; CI's null-hatch gate proves the org boots without it.
# gettext provides envsubst (deploy-mac.sh plist template substitution).
brew install node gh jq tmux tailscale postgresql@17 redis gettext

# postgresql@17 is keg-only; ensure PATH:
echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zprofile
source ~/.zprofile
pg_dump --version  # must show 17.x — if 16.x wins, fix PATH

# npm-installed tools
npm install -g @anthropic-ai/claude-code neonctl

# gh authentication (needed before the clone if your fork is private)
gh auth login   # follow prompts; pick HTTPS + browser OAuth
```

**Optional installs** (skip both on a first hatch; add later when the need is
real):
- `cua-driver` — only if you will grant an officer the `drives_computer`
  capability (computer-use). See Appendix B.
- `apcupsd` — only if the Mini sits on an APC UPS. See Appendix C.

### Checkpoint 1.5 — Redis service start with AOF persistence (~5 min)

```bash
echo "appendonly yes" | sudo tee -a /opt/homebrew/etc/redis.conf
brew services start redis

redis-cli ping                    # PONG
redis-cli CONFIG GET appendonly   # "yes"
```

(`setup-mac.sh` in Phase 2 re-checks + can do this for you — doing it here
just front-loads the reboot-survival test: `redis-cli SET t 1`, reboot,
`redis-cli GET t`.)

### Checkpoint 1.6 — Remote access: SSH + Tailscale (~10 min, Captain hands-on)

```bash
sudo systemsetup -setremotelogin on
sudo tailscale up --authkey=<your-auth-key>   # or interactive: sudo tailscale up
tailscale status
# From another machine: ssh <user>@<mini-tailscale-name>
```

### Checkpoint 1.7 — macOS permissions + TCC persistence (~15 min, Captain hands-on)

Phase 2's `grant-mac-permissions.sh` walks the TCC grants interactively (the
OS requires human clicks — this cannot be automated). Two things to know now:

- Grants are **responsible-process-scoped**: a grant given to Terminal does
  not cover a LaunchAgent-spawned process. Follow the prompts from the script,
  not ad-hoc clicking.
- Grants persist across reboots **only for code-signed binaries**. If you see
  repeated permission prompts after reboots, work through
  `cabinet/docs/mac-tcc-code-signing-gate.md` (Developer ID signing +
  notarization). This is required before any Appendix-B computer-use work,
  not for the base hatch.

### Checkpoint 1.8 — Clone the repo (~5 min)

```bash
mkdir -p ~/work && cd ~/work
git clone <your-fork-url> captains-cabinet   # your fork of captains-cabinet
cd captains-cabinet
# Stay on the fork's default branch — that IS the ship branch. There is no
# separate "mac-native" branch to check out.
```

**PASS Phase 1** when: repo cloned, `redis-cli ping` answers, `claude
--version` works, Tailscale/SSH reachable.

---

## Phase 2 — The hatch (interview → generate → verify → deploy)

Run everything below from the repo root on the Mini. The hatch path is:
**cabinet-init interview → generate-instance.py → activation steps →
null-hatch gate → dry render → deploy**. Config is *generated*, not
hand-edited — never edit `instance/config/product.yml` / the managed
`officers:` block in `platform.yml` directly (their headers say the same);
change the answers file and re-run the generator instead.

### 2.0 — Host bootstrap

```bash
bash cabinet/scripts/setup-mac.sh          # interactive orchestrator; idempotent
bash cabinet/scripts/setup-mac.sh --check  # verify: exit 0
```

Installs missing deps, starts Redis, creates directories, runs the API-key
wizard into `cabinet/.env` (chmod 600; headless alternative:
`SKIP_ENV_WIZARD=1 bash cabinet/scripts/setup-mac.sh`), loads the preset, and
runs the framework test suite.

### 2.1 — The onboarding interview (`/cabinet-init`)

```bash
claude
> /cabinet-init
```

The skill interviews you (captain profile, lanes, org shape, autonomy
posture, seed outcomes, integrations), writes
`instance/config/cabinet-init.answers.yml`, and runs the generator:

```bash
python3 cabinet/scripts/generate-instance.py            # --dry-run to preview
```

**If your clone ships a previous deployment's `instance/`** (committed
platform.yml with another captain's officers block, a hand-authored
sources.yml, live contexts/projects), the generator will *refuse* rather than
clobber. That refusal is the cue for the adoption path:

```bash
python3 cabinet/scripts/generate-instance.py --adopt
```

`--adopt` archives every conflicting file to
`instance/_pre-adopt-<stamp>/` (nothing is deleted) and generates *your*
instance fresh. An existing `posture.yml` ruling is never touched.

The generator writes: per-lane contexts + projects,
`instance/agents/<lane>-ceo.md`, the managed captain keys + `officers:` block
in `platform.yml`, `instance/config/roster.yml`,
`instance/config/active-project.txt` (first lane slug — `bootstrap-roles.sh`
needs it), the inert posture scaffold, and (org flavor) the
`sources.yml` OrgSource recall binding. Nothing activates by itself.

### 2.2 — Activation steps (the generator prints these; in order)

```bash
# 1. Preset
echo portfolio > instance/config/active-preset    # or work/custom per your shape

# 2. Germline edits (Captain applies): lane CEOs into cabinet/mcp-scope.yml
#    agents: list + capability rows in cabinet/officer-capabilities.conf

# 3. Chair bot token (BotFather) into cabinet/.env:
#    TELEGRAM_COS_TOKEN=...           # canonical name; config keeps TOKEN-TBD
#    Multi-cabinet only: CABINET_MODE=multi + CABINET_ID=<id> in cabinet/.env

# 4. Seed the roster (reads instance/config/active-project.txt for the slug)
bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml

# 5. TCC grants (interactive — Captain clicks)
bash cabinet/scripts/grant-mac-permissions.sh

# 6. Assemble the runtime
bash cabinet/scripts/load-preset.sh
```

### 2.3 — The null-hatch gate (clean-room proof)

Before any officer boots, prove the hatch is clean — the same gate CI runs:

```bash
bash cabinet/scripts/null-hatch.sh    # exit 0 = the egg boots with NO captain
                                      # data, NO screenpipe, NO source binding
```

It runs against a sandbox copy of the committed tree with an *unreadable*
`~/.screenpipe`, so any latent personal-stack read fails loudly. Do not
proceed on a red gate.

### 2.4 — Dry render (no side effects), then deploy

```bash
# Officer command assembly, no tmux/redis/boot:
bash cabinet/scripts/start-officer-mac.sh cos --dry-run

# Plist render preview, no launchctl:
bash cabinet/scripts/deploy-mac.sh --officer cos --dry-run

# Deploy the Chair only (lane CEOs are on-demand consultants — no persistent
# LaunchAgent; they are started per trigger via start-officer-mac.sh):
bash cabinet/scripts/deploy-mac.sh --officer cos
```

Both scripts reject unknown flags (exit 64) — a mistyped flag never falls
through to the real boot path. `start-officer-mac.sh` also refuses to take
over a tmux session owned by a *different* checkout (exit 65;
`CABINET_FORCE_TAKEOVER=1` overrides deliberately) — rehearsals and scratch
clones cannot kill the live Chair.

### 2.5 — Ratify outcomes + verify

- Ratify seed outcomes in `instance/config/outcomes.yml` (`status: active` +
  `captain_ratified: true`, with your `CABINET_ID` as the deployment key —
  the compiler refuses files pinned to another deployment, so an inherited
  `outcomes.yml` is inert until replaced).
- Verify: `bash cabinet/scripts/health-check.sh`, `tmux attach -t officer-cos`
  (detach: `C-b d`), and a Telegram round-trip with the Chair.

### 2.6 — Posture ruling (optional, Captain-only)

A Mini that should run the sovereign posture needs the Captain ratification
described in `cabinet/docs/mac-mini-deploy-runbook.md` §4 step 5: edit +
commit `instance/config/posture.yml` (+ empty `standing-grants.yml`), then
`sudo bash cabinet/scripts/germline-lock.sh lock`. Skipping this leaves the
deployment guardian (today's rules) — nothing else changes.

*Axes (amendment 2026-07-05):* start from the shipped preset —
`cp instance/config/posture-presets/org-macmini.yml instance/config/posture.yml`
(axes `flavor: org` · `deployment_target: mac_mini` · schg attestation), set
`deployment:` to this Mini's `CABINET_ID`, and add a `never_grant:` list if
any ceiling class should be structurally non-grantable on this deployment.
Downgrade is always instant and needs no unlock: `CABINET_POSTURE=guardian`
env, or the Captain binder verb `posture guardian` (writes the narrow-only
`instance/config/posture-narrow` cap). Upgrades happen ONLY via this lock
ritual — no env var, dashboard, or chat verb can widen.

---

## Stop-the-line gates

If any checkpoint fails, halt + investigate before continuing. Common failure
modes:

- 1.4 `pg_dump 16.x` wins → fix `~/.zprofile` PATH order
- 1.4 `envsubst: command not found` → `brew install gettext` (keg-only; may
  need `echo 'export PATH="/opt/homebrew/opt/gettext/bin:$PATH"' >> ~/.zprofile`)
- 1.5 Redis doesn't survive reboot → verify `appendonly yes` actually landed
  in redis.conf
- 1.7 permission prompt re-fires after reboot → code-signing gap
  (`cabinet/docs/mac-tcc-code-signing-gate.md`)
- 2.1 generator refuses over existing files → that's the guard working; use
  `--adopt` (fresh captain adopting a shipped instance/) or `--force`
  (deliberate single-file overwrite)
- 2.2 `bootstrap-roles.sh` exits 1 "no product slug" →
  `instance/config/active-project.txt` missing (generated since 2026-07-07;
  on older generations: `echo <lane-slug> > instance/config/active-project.txt`)
- 2.3 null-hatch red → do NOT deploy; the tree leaks launcher/personal state
  into framework core — fix or file the failure upstream

---

## Appendix A — OPTIONAL Flavor-A add-on: personal sensing estate

Only for a **personal-flavor** deployment (the Captain's own clone-org on
their daily machine, or a Mini deliberately bound to the Captain's estate).
Never required; the core org runs entirely without it.

1. Install the personal stack: `brew install screenpipe`,
   `brew services start screenpipe`, complete its setup wizard (configure
   exclusions: password managers, banking, personal email; set retention).
2. Bind the source seam: copy `instance/config/sources.yml.example` to
   `instance/config/sources.yml` and set `adapter:` to the Flavor-A adapter
   under `instance/flavor-a/` (see the example file's contract — the module
   must live in the instance tree; framework core never names it).
   If the generator emitted an OrgSource `sources.yml` (org flavor), replace
   it; if you ran the interview with `autonomy.flavor: personal`, none was
   emitted and the file is yours to author.
3. Packs: personal-preset capability packs live under `packs/`
   (`preset-personal-pack`, etc.) — install per `packs/README.md`.
4. Rules: the binding addendum `instance/flavor-a/rules/brain-bridge-*.md`
   governs officer use of the estate alongside `.claude/rules/brain-bridge.md`.

The clean-room ratchets stay green either way: personal code lives in
`instance/flavor-a/`, reached only through `framework.sources` — a screenpipe
import inside `framework/` is CI-red regardless of flavor.

## Appendix B — OPTIONAL: cua-driver (computer-use)

Only when an officer will carry the `drives_computer` capability.

```bash
PINNED_TAG=$(gh release list --repo trycua/cua --limit 1 --json tagName --jq '.[0].tagName')
mkdir -p cabinet/config && echo "$PINNED_TAG" > cabinet/config/cua-driver-version.txt
gh release download "$PINNED_TAG" --repo trycua/cua --pattern '*macOS*' --dir ~/Downloads/
sudo mv ~/Downloads/cua-driver /opt/homebrew/bin/cua-driver && sudo chmod +x /opt/homebrew/bin/cua-driver
cua-driver --version
```

TCC: cua-driver needs Accessibility + Screen Recording + Full Disk Access,
and code-signing (Checkpoint 1.7 / the TCC gate doc) for the grants to
persist. The MCP overlay ships at `cabinet/mcp-overlays/cua-driver.mcp.json`
(per-officer override: `instance/agents/<officer>/mcp.json`) —
`start-officer-mac.sh` merges it automatically for `drives_computer`
officers.

## Appendix C — OPTIONAL: UPS (apcupsd)

Only if the Mini sits on an APC UPS.

```bash
brew install apcupsd
sudo $EDITOR /opt/homebrew/etc/apcupsd/apcupsd.conf   # UPSCABLE + UPSTYPE per model
brew services start apcupsd
# Test: pull the wall plug briefly; apcupsd should detect + log
```
