# Dev/Runtime Split — Cutover Runbook

**Status: DESIGNED, NOT EXECUTED.** This document describes a one-time
migration. Nothing in it has been run. It is Captain-gated — every step that
touches the live fleet is a "we do it together" step, done from the
Captain's own session against the live host, never run unattended.

**Reversible.** Every step has a same-shaped undo. Nothing here deletes the
dev checkout, the live `instance/` data, or any officer's history.

## 0. What this changes, in one paragraph

Today, every officer's LaunchAgent runs `claude` out of
`/Users/nate/captains-cabinet` — the same checkout you develop in, which
routinely sits mid-edit on a feature branch with hundreds of uncommitted
files. A save-in-progress is live in a running officer. This runbook moves
the **fleet** onto its own clean, pinned checkout (a "fleet runtime tree")
separate from your dev tree, so `git checkout`, `git stash`, or a bad
mid-edit save in `~/captains-cabinet` can never affect a running officer
again. After cutover, `~/captains-cabinet` is for development only; the
fleet is updated deliberately, by pinning a known-good commit and deploying
it — the same discipline the Cabinet already uses to hatch a fresh
deployment (`hatch.sh`), just applied to updates instead of only first-boot.

## 1. Terminology — two different things are both called "runtime"

This repo already has an environment variable named `CABINET_RUNTIME_DIR`
(see `cabinet/scripts/load-preset.sh`, default `/tmp/cabinet-runtime`). That
is the directory where the **rendered constitution + safety-boundaries
files** get assembled for officers to read at boot — a small, regenerated-
every-load scratch area. It is **not** what this runbook is about, and this
cutover does not move it, rename it, or otherwise touch it.

This runbook is about a **different, new thing**: a full pinned checkout of
the repository (code + local instance data) that `launchd` points its
officer LaunchAgents at, instead of pointing at your dev tree. To keep the
two apart on the page, this doc always spells the new one out as **"the
fleet runtime tree"** and never abbreviates it to bare "runtime" where
`CABINET_RUNTIME_DIR` could also be meant.

## 2. Design this runbook assumes — read this before running anything

This doc was written in the same build wave as (and possibly before)
`cabinet/scripts/runtime-provision.sh` (provisions the fleet runtime tree)
and `cabinet/scripts/cabinet-deploy.sh` (the ongoing update command, fetch →
checkout → health-check → graceful restart → rollback-if-unhealthy). **If
those scripts exist on your checkout, use them — their own `--help`/header
comment is authoritative over this document if the two ever disagree**
(Docs-Must-Track-Code). If they do not exist yet, every step below gives the
manual equivalent using only scripts already proven in this repo, so the
cutover is not blocked on Lane A/B landing first.

Layout (Capistrano-style: code and data are physically separate so a code
update never touches data, and a rollback never touches data either):

```
~/.cabinet/runtime/                          <- the fleet runtime tree (root)
  shared/
    instance/                                <- THE persistent instance data (roster.yml,
                                                 roles, memory, agents, loop-prompts, ...) —
                                                 copied in ONCE (Step 2), then re-used by
                                                 every future release via symlink. Never
                                                 versioned per-release; never deleted by a deploy.
    cabinet.env                              <- persistent copy of the secrets file
  releases/
    20260715-143000-df7abb1d/                <- one clean checkout per deploy (name:
                                                 <UTC stamp>-<short sha>), immutable once
                                                 validated
      instance -> ../../shared/instance       <- symlink (not a copy — one edit, every release sees it)
      cabinet/.env -> ../../../shared/cabinet.env
      cabinet/ framework/ ...                <- the rest of the checked-out repo tree
  current -> releases/20260715-143000-df7abb1d   <- STABLE symlink; this is the path
                                                     launchd's plists are rendered against
```

Why the plists point at `current` (the stable symlink) and not at a
versioned `releases/<id>` path directly: a future `cabinet-deploy.sh` run
only needs to build a new `releases/<id>`, validate it, then swap what
`current` points to and gracefully restart — it never has to re-render or
re-bootstrap the LaunchAgents themselves, because their on-disk plist never
changes. That is the "atomic symlink swap" the deploy script is built
around. This cutover runbook renders the plists exactly **once**, against
`current`.

Root path: this doc uses `~/.cabinet/runtime` throughout (dot-prefixed,
alongside `~/.claude`, so it reads as tooling-owned, not a folder to `cd`
into and hand-edit). If `runtime-provision.sh` defaults to a different root
or exposes an override flag/env var, follow the script; only the path
string changes, nothing else in this procedure does.

**Three different plist mechanisms exist in this repo — know all three
before Step 3, or the cutover will look done while part of the fleet is
still quietly running the old path.**

1. **Officer** plists (`com.cabinet.officer.<slug>.plist`) are envsubst-
   rendered from `cabinet/launchd/com.cabinet.officer.template.plist` by
   `deploy-mac.sh`, fleet derived from `instance/config/roster.yml`. Most of
   Step 3 is about this one.
2. **Manifest-driven daemons/watchdogs/crons** (`dashboard`,
   `limit-reset-watchdog`, `backup`, the `probe-*` family, and more) are
   rendered from `cabinet/services.yml` by `cabinet/scripts/generate-
   plists.py` into `cabinet/launchd/generated/` — a directory that is
   **gitignored and machine-specific** (its own docstring says so). Nothing
   checked into git is the install source for these.
3. **`com.cabinet.officer.cos-inbound.plist`** (the Chair's Telegram-receive
   poller) is a genuine exception to both of the above: a static,
   hand-authored, hand-installed file whose target path is **hardcoded
   directly in the checked-in XML** (see its own header comment: "Install +
   load: cp ...; launchctl load -w ..."). Repointing it means editing that
   path, not re-running a generator.

**A fourth thing to know about, but never use:** roughly two dozen
non-`.template` files sitting directly under `cabinet/launchd/*.plist`
(`com.cabinet.dashboard.plist`, `com.cabinet.backup.plist`,
`com.cabinet.probe-github.plist`, and similar) are stale, previously-
committed *output* of mechanism 2, from whenever `generate-plists.py` was
last run and its result accidentally got `git add`ed. They still carry the
**old** live path baked in and are not kept in sync with anything — the
real, current output of mechanism 2 only ever lives in the gitignored
`generated/` directory. Do not `cp` one of these by mistake; Step 3
regenerates fresh instead.

## 3. Preconditions checklist

Before starting, confirm:

- [ ] `bash cabinet/scripts/cabinet-doctor.sh` is **GREEN** on the live tree
      right now (baseline health — see Step 0; don't cut over a fleet that's
      already unhealthy, you won't be able to tell which problem is new).
- [ ] `bash cabinet/scripts/verify-launchagents.sh` exits 0 on the live tree.
- [ ] You know which commit is "known-good" to pin (defaults to
      `origin/master`'s current tip if you don't have a specific sha in
      mind — name one explicitly if you want anything else).
- [ ] `instance/config/roster.yml` on the live tree is the roster you want
      the fleet running (this migration carries it forward as-is, it does
      not let you redesign the roster mid-cutover).
- [ ] No other wave is mid-deploy or mid-restart-drill on the live fleet
      right now (check for a live `deploy-mac.sh`/`restart-all-officers-
      oneshot.sh` run in progress before starting).

## 4. Step-by-step

Legend: **[ME]** = scripted, no live-fleet impact, safe to run any time.
**[CAPTAIN]** = needs the Captain's own session, physical access, or a sudo
prompt. **[CAPTAIN + ME]** = we run it together, live fleet impact — this is
the "we do it together" gate the standing grant reserves for cutover day.

### Step 0 — Safety snapshot **[ME]**, ~5 min, zero live impact

Capture a baseline before touching anything, so "did the cutover cause this"
is always answerable.

```bash
LIVE=/Users/nate/captains-cabinet
SNAP=~/cabinet-cutover-snapshot-$(date -u +%Y%m%d-%H%M%S)
mkdir -p "$SNAP"

bash "$LIVE/cabinet/scripts/cabinet-doctor.sh"        > "$SNAP/doctor-before.log" 2>&1
bash "$LIVE/cabinet/scripts/verify-launchagents.sh"   > "$SNAP/verify-before.log" 2>&1

# what REPO_ROOT is currently baked into the live plists (names only — the grep
# pattern below matches the WorkingDirectory/ProgramArguments path, never a secret)
grep -l "$LIVE" ~/Library/LaunchAgents/com.cabinet.*.plist > "$SNAP/plists-pointing-at-live.txt"

# the rollback anchor: an exact copy of the instance data + secrets AS THEY STAND
# right now, independent of anything Step 2 does next
tar -czf "$SNAP/instance-and-env-backup.tar.gz" \
  -C "$LIVE" instance cabinet/.env
echo "snapshot: $SNAP"
```

Keep `$SNAP` until the cutover has soaked (see §5) — it is the fastest path
back to "exactly how things were" if anything downstream needs re-deriving.

### Step 1 — Provision the fleet runtime tree **[ME]**, zero live impact

If `cabinet/scripts/runtime-provision.sh` exists:

```bash
bash "$LIVE/cabinet/scripts/runtime-provision.sh" --target ~/.cabinet/runtime \
  --commit origin/master   # or an explicit sha
```

Manual equivalent (uses only `git` + scripts already in this repo):

```bash
RUNTIME=~/.cabinet/runtime
mkdir -p "$RUNTIME/shared/instance" "$RUNTIME/releases"

# one persistent bare mirror — created once, fetched on every future deploy
[ -d "$RUNTIME/shared/repo.git" ] || \
  git clone --mirror https://github.com/nate-refslund/captains-cabinet.git "$RUNTIME/shared/repo.git"
git -C "$RUNTIME/shared/repo.git" fetch --all --prune

TARGET_SHA=$(git -C "$RUNTIME/shared/repo.git" rev-parse origin/master)   # or your named sha
RELEASE="$RUNTIME/releases/$(date -u +%Y%m%d-%H%M%S)-${TARGET_SHA:0:8}"

# Clone FROM THE LOCAL MIRROR (not GitHub again) — same filesystem, so git
# hardlinks objects automatically: instant, no network round-trip beyond the
# one `fetch` above. Deliberately KEEPS .git per release (unlike hatch.sh's
# own git-archive clean-room export): several scripts in this repo
# (generate-plists.py, germline-lock.sh) fall back to `git rev-parse
# --show-toplevel` when no CABINET_ROOT is set — a real fleet target should
# never depend on every future invocation remembering the override.
git clone "$RUNTIME/shared/repo.git" "$RELEASE"
git -C "$RELEASE" checkout --detach "$TARGET_SHA"
echo "provisioned: $RELEASE"
```

**Do not point `current` at it yet** — validate first, with zero launchd
involvement, using the dry-run flags these scripts already ship
(the same proofs `hatch.sh` runs as its own P-c gate):

```bash
cd "$RELEASE"
CABINET_SOURCE_REPO="$RELEASE" bash cabinet/scripts/start-officer-mac.sh cos --dry-run
CABINET_SOURCE_REPO="$RELEASE" bash cabinet/scripts/deploy-mac.sh --officer cos --dry-run
```

Both must print their assembled command/plan and exit 0 with no errors.
This proves the release directory is structurally sound *before* any
instance data or launchd is involved.

### Step 2 — Copy the live instance data in **[CAPTAIN + ME]**, one-time

This is a **copy**, never a move — the live tree's `instance/` and
`cabinet/.env` are left exactly as they are, in place, untouched.

```bash
LIVE=/Users/nate/captains-cabinet
RUNTIME=~/.cabinet/runtime

# secrets: API keys, bot tokens, connection strings (names only — see
# cabinet/.env.example for the field list; values are never printed by this
# runbook or by anything it invokes)
install -m 600 "$LIVE/cabinet/.env" "$RUNTIME/shared/cabinet.env"

# the whole instance/ tree: roster.yml, active roles, memory, per-officer
# agent files, loop-prompts, the judged config layer — everything a running
# deployment has accumulated that isn't in git
rsync -a "$LIVE/instance/" "$RUNTIME/shared/instance/"

# Mac-level per-officer state (Telegram getUpdates poll offsets, isolated
# Claude config homes) — optional, but carrying it forward means officers
# don't have to re-settle Telegram polling or redo AUD-1 config-home setup
# on the new path
rsync -a "$HOME/Library/Application Support/cabinet/" "$RUNTIME/shared/app-support/" 2>/dev/null || true
```

Then wire the copy into the release from Step 1 (symlinks — one shared
copy, every release sees it; this is what makes a future code-only deploy
never touch data):

```bash
# $RELEASE still set from Step 1 in the same shell — if you're starting a
# fresh shell instead, re-derive it as the newest release directory:
RELEASE=$(ls -td ~/.cabinet/runtime/releases/*/ | head -1); RELEASE=${RELEASE%/}

ln -s "$RUNTIME/shared/instance"    "$RELEASE/instance"
ln -s "$RUNTIME/shared/cabinet.env" "$RELEASE/cabinet/.env"
```

**Germline callout — do this before the tree goes live.** A subset of what
you just copied is boundary-locked on the live tree via macOS `schg`
(`instance/config/act-first-surfaces.yml`, `instance/config/posture.yml`,
`instance/config/standing-grants.yml`, `instance/config/policies/`,
`instance/config/posture-presets/` — see `cabinet/scripts/germline-lock.sh`).
`schg` is a filesystem flag on the live tree's own inodes; copying the
*content* across (above) does **not** carry the flag with it — the new
tree's copies land unlocked. Arm the same boundary on the fleet runtime
tree before it takes live traffic:

```bash
# CAPTAIN types this one (schg needs root; the standing rule is "attempt
# sudo -n, else a named handback" — this is the named handback):
cd "$RELEASE"   # re-derive per the comment above if this is a fresh shell
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh status    # confirm LOCKED, no sudo needed to check
```

> **Known gap for the ongoing-update path (flag this to whoever builds
> `cabinet-deploy.sh`, do not let it get silently lost):** because
> `instance/` is a symlink into `shared/`, locking it once locks the shared
> data for every release permanently. But the **code**-side germline files
> (`framework/authority/*.py`, `.claude/settings.json`,
> `cabinet/scripts/kill-switch.sh`, etc.) live *inside* each release
> directory, not in `shared/` — a plain `git archive`/checkout materializes
> new inodes every time, so **every future `cabinet-deploy.sh` release needs
> its own fresh `sudo germline-lock.sh lock` run**, or a deploy can silently
> go live with the enforcer boundary open on the new release while the old
> one (and everyone's mental model) still says "locked." This is exactly the
> failure class the doctor's germline watchdog (`cabinet-doctor.sh` §10)
> exists to catch — make sure `cabinet-doctor.sh` runs (and is *watched*,
> not just green-and-forgotten) after every future deploy, not only after
> this one-time cutover.

### Step 3 — Repoint launchd **[CAPTAIN + ME]** — the actual cutover moment

Three mechanisms, three treatments (see §2 above) — do all four parts below
before Step 4. None of this hand-edits plist XML by feel; every rewrite goes
through a script this repo already ships.

**3a. Officer plists.** `deploy-mac.sh` already resolves the path it bakes
into each officer's `WorkingDirectory`/`ProgramArguments` from
`CABINET_SOURCE_REPO` (falling back to `CABINET_ROOT`); pointing that at the
fleet runtime tree's stable `current` symlink and re-running it rewrites
every officer's plist in place, then bootout+bootstraps it:

```bash
ln -sfn "$RELEASE" ~/.cabinet/runtime/current   # $RELEASE from Steps 1-2 (re-derive if a fresh shell)

cd ~/.cabinet/runtime/current
CABINET_SOURCE_REPO=~/.cabinet/runtime/current CABINET_ROOT=~/.cabinet/runtime/current \
  bash cabinet/scripts/deploy-mac.sh --officer all
```

`--officer all` derives the fleet from the roster you copied in at Step 2
(`instance/config/roster.yml`) — it never guesses or falls back to a preset
default.

**3b. Manifest-driven daemons/watchdogs/crons** (`dashboard`,
`limit-reset-watchdog`, `backup`, the `probe-*` family, and more). Not
rendered by `deploy-mac.sh` — regenerate from the runtime tree and install
the fresh output (never the stale, checked-in `cabinet/launchd/*.plist`
files that share a name — see §2's fourth item):

```bash
cd ~/.cabinet/runtime/current
CABINET_ROOT=~/.cabinet/runtime/current python3.12 cabinet/scripts/generate-plists.py
for p in cabinet/launchd/generated/*.plist; do
  [ -e "$p" ] || continue
  plutil -lint "$p"
  launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$p"
done
```

`generate-plists.py` reads only `CABINET_ROOT` (not `CABINET_SOURCE_REPO`)
and otherwise falls back to `git rev-parse --show-toplevel` from its own
script location — pass `CABINET_ROOT` explicitly every time you invoke it
from the runtime tree.

**3c. The static `cos-inbound` poller.** The Chair's Telegram receive path
owns `getUpdates` for the bot token and is neither template- nor
manifest-driven; its checked-in plist has the live path baked directly into
its XML. Repoint with a path substitution, installing the runtime tree's
copy (not the live tree's):

```bash
NEW=~/.cabinet/runtime/current
sed "s|/Users/nate/captains-cabinet|$NEW|g" \
  "$NEW/cabinet/launchd/com.cabinet.officer.cos-inbound.plist" \
  > ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist
```

**3d. Catch-all — prove nothing was missed.** After 3a-3c, grep every
*installed* plist for the old path; anything that still matches is a gap
3a-3c didn't reach and needs the same treatment before Step 4:

```bash
grep -l "/Users/nate/captains-cabinet" ~/Library/LaunchAgents/com.cabinet.*.plist
# expect NO OUTPUT — any line printed here names an unrepointed plist
```

This is the one moment officers actually restart — the previous tmux
sessions are killed and relaunched from the new path (same
`--continue`-free, fresh-boot restart every officer already goes through on
a normal `reload-officer-mac.sh` reload; conversation history for the
*current* turn is not preserved across this specific restart, same as any
other officer relaunch).

### Step 4 — Verify **[CAPTAIN + ME]**

```bash
bash ~/.cabinet/runtime/current/cabinet/scripts/verify-launchagents.sh   # exit 0 required
bash ~/.cabinet/runtime/current/cabinet/scripts/cabinet-doctor.sh        # exit 0 (GREEN) required
```

Also confirm by hand:

- Step 3d's sweep (`grep -l "/Users/nate/captains-cabinet" ~/Library/
  LaunchAgents/com.cabinet.*.plist`) prints nothing, re-confirmed — this is
  the single check that catches all three mechanisms (3a/3b/3c) at once.
- `launchctl print gui/$(id -u)/com.cabinet.officer.cos` shows the new path
  in its working directory / program arguments (not `/Users/nate/captains-
  cabinet`).
- `tmux capture-pane -t officer-cos -p | tail -5` shows a live, booted
  session (not a bare shell prompt, not "Not logged in").
- `~/Library/Logs/cabinet/officer-cos.out.log` has fresh (last few seconds)
  lines.
- **[CAPTAIN]** send a real Telegram DM to the Chair and confirm a reply —
  external-comms confirmation is structurally a Captain action, not
  something this runbook automates.

If any of these are off: do **not** improvise a fix under time pressure —
go to Step 5.

### Step 5 — Rollback **[CAPTAIN + ME]** — same shape, reverse direction

The live dev tree was never modified, so rollback is exactly "point launchd
back at it" — the same three mechanisms as Step 3, run once each, pointed
back at the dev tree:

```bash
cd /Users/nate/captains-cabinet

# 3a reversed
CABINET_SOURCE_REPO=/Users/nate/captains-cabinet CABINET_ROOT=/Users/nate/captains-cabinet \
  bash cabinet/scripts/deploy-mac.sh --officer all

# 3b reversed
CABINET_ROOT=/Users/nate/captains-cabinet python3.12 cabinet/scripts/generate-plists.py
for p in cabinet/launchd/generated/*.plist; do
  [ -e "$p" ] || continue
  launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$p"
done

# 3c reversed — a plain copy suffices here: the live tree's own checked-in
# cos-inbound plist already carries the correct (original) path, no sed needed
cp cabinet/launchd/com.cabinet.officer.cos-inbound.plist ~/Library/LaunchAgents/
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist

bash cabinet/scripts/verify-launchagents.sh
bash cabinet/scripts/cabinet-doctor.sh   # must return to GREEN
```

If `cabinet-doctor.sh` does not return to the exact baseline captured in
Step 0's `$SNAP/doctor-before.log`, that is a new, separate problem to
root-cause before touching anything else — not evidence the rollback itself
failed (the rollback only repoints launchd; it cannot fix a fleet that was
already unhealthy before this runbook started).

## 5. After cutover — the new steady state

| | Before | After |
|---|---|---|
| launchd points at | `/Users/nate/captains-cabinet` (dev tree, on a feature branch, possibly 100s of dirty files) | `~/.cabinet/runtime/current` → a pinned, validated release |
| Dev tree's job | development **and** production | development only |
| Fleet updates via | `git checkout`/save in the dev tree (implicit, unreviewed) | `cabinet/scripts/cabinet-deploy.sh` (explicit: fetch → checkout a named commit → `cabinet-doctor.sh` health gate → graceful restart → automatic rollback if unhealthy) |
| Instance data (`instance/`, `cabinet/.env`) lives at | inside the dev tree | `~/.cabinet/runtime/shared/` — persists across every future deploy untouched |
| A bad mid-edit save in the dev tree | could be live in a running officer | has zero effect on the fleet until deliberately deployed |

Going forward, "ship an update to the live fleet" means: land the change on
`master` (same review discipline as always) → run
`cabinet/scripts/cabinet-deploy.sh` with the commit you want live → it does
Steps 1/3/4 of this runbook for you, automatically, every time — never a
manual `deploy-mac.sh --officer all` again except for this one-time cutover
and true disaster recovery.

## 6. Non-goals — explicitly unaffected by this cutover

- **Redis.** Same server, same host/port, same keys (heartbeats, trigger
  streams, cost counters, the kill switch). A code-path move does not touch
  it — officers on the new path talk to the exact same Redis instance
  officers on the old path did.
- **Neon / Postgres.** External to both trees. The only thing that has to
  carry over is the connection string, and that travels inside
  `cabinet/.env` (Step 2) like every other secret — no data migration.
- **MCP servers / Telegram bot tokens / any other secret.** Same secrets,
  same values — Step 2 copies `cabinet/.env` byte-for-byte; nothing is
  rotated or regenerated by this cutover.
- **The roster, org shape, or any officer's role definition.** Carried
  forward as-is (Step 2). This runbook is a plumbing change, not an org
  change — if you also want to redesign the roster, do that as a separate,
  later act against the runtime tree via the normal deploy path, not folded
  into cutover night.
- **`~/Library/Caches/cabinet/` and `~/Library/Logs/cabinet/`.** Not copied
  by Step 2, and that's deliberate: the per-officer merged-MCP-config /
  settings caches are regenerated fresh by `start-officer-mac.sh` on every
  boot (including the boot this cutover triggers), and the logs are additive
  — a fresh `officer-<slug>.out.log` on the new path is expected and healthy,
  not a sign anything was missed.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `deploy-mac.sh --officer all` refuses with "roster.yml not found" | Step 2's rsync didn't land, or ran against the wrong destination | Re-check `~/.cabinet/runtime/current/instance/config/roster.yml` resolves (through the symlink) to a real file |
| Officer boots then immediately shows a bare shell prompt | `cabinet/.env` symlink didn't resolve, or a required var was never named in it | `cat ~/.cabinet/runtime/current/cabinet/.env` should show *lines*, not "No such file"; check `~/Library/Logs/cabinet/officer-<slug>.err.log` |
| `cabinet-doctor.sh` reports `germline <path> — exists but NOT schg-locked` | Step 2's lock ceremony was skipped or ran against the wrong directory | Re-run `sudo bash cabinet/scripts/germline-lock.sh lock` from *inside* the release actually referenced by `current` |
| `verify-launchagents.sh` shows an officer missing | `deploy-mac.sh --officer all` didn't reach it (roster mismatch, or the run failed partway) | Re-run `deploy-mac.sh --officer <name>` for the missing one specifically |
| `generate-plists.py` errors with something like "not a git repository" | It fell back to `git rev-parse --show-toplevel` because `CABINET_ROOT` wasn't set (it does not read `CABINET_SOURCE_REPO`) | Re-run with `CABINET_ROOT=~/.cabinet/runtime/current` set explicitly (Step 3b) |
| A manifest daemon (`dashboard`, `backup`, a `probe-*`) still shows the old path after Step 3 | Its install came from the stale, checked-in `cabinet/launchd/<name>.plist` instead of a fresh `generate-plists.py` render | Re-do 3b; install only from `cabinet/launchd/generated/`, never the bare `cabinet/launchd/<name>.plist` files |
| Telegram DM gets no reply | Poller state didn't carry over cleanly, or the bot token env var name doesn't match | Confirm `TELEGRAM_COS_TOKEN` (or the relevant officer's var) is present by *name* in the copied `cabinet.env`; check for a second, orphaned `getUpdates` poller (409 Conflict) per the existing gotcha in `start-officer-mac.sh` |
| Everything above passes but you're not confident | — | Give it a real 24-72h soak before archiving `$SNAP` from Step 0 (mirrors the existing 72h-soak discipline in `cabinet/docs/mac-mini-deploy-runbook.md` §11) |

## 8. Command reference — condensed, paste-ready, NOT YET RUN

Everything below is the same commands as above, back to back, for the
session that actually executes cutover day. Replace `<RELEASE>` with the
directory Step 1 produced.

```bash
# Step 0 — snapshot
LIVE=/Users/nate/captains-cabinet
SNAP=~/cabinet-cutover-snapshot-$(date -u +%Y%m%d-%H%M%S); mkdir -p "$SNAP"
bash "$LIVE/cabinet/scripts/cabinet-doctor.sh" > "$SNAP/doctor-before.log" 2>&1
bash "$LIVE/cabinet/scripts/verify-launchagents.sh" > "$SNAP/verify-before.log" 2>&1
tar -czf "$SNAP/instance-and-env-backup.tar.gz" -C "$LIVE" instance cabinet/.env

# Step 1 — provision + validate (zero live impact)
RUNTIME=~/.cabinet/runtime
mkdir -p "$RUNTIME/shared/instance" "$RUNTIME/releases"
[ -d "$RUNTIME/shared/repo.git" ] || git clone --mirror https://github.com/nate-refslund/captains-cabinet.git "$RUNTIME/shared/repo.git"
git -C "$RUNTIME/shared/repo.git" fetch --all --prune
TARGET_SHA=$(git -C "$RUNTIME/shared/repo.git" rev-parse origin/master)
RELEASE="$RUNTIME/releases/$(date -u +%Y%m%d-%H%M%S)-${TARGET_SHA:0:8}"
git clone "$RUNTIME/shared/repo.git" "$RELEASE"
git -C "$RELEASE" checkout --detach "$TARGET_SHA"
CABINET_SOURCE_REPO="$RELEASE" CABINET_ROOT="$RELEASE" bash "$RELEASE/cabinet/scripts/start-officer-mac.sh" cos --dry-run
CABINET_SOURCE_REPO="$RELEASE" CABINET_ROOT="$RELEASE" bash "$RELEASE/cabinet/scripts/deploy-mac.sh" --officer cos --dry-run

# Step 2 — copy instance data + secrets, wire symlinks, lock germline [CAPTAIN sudo]
install -m 600 "$LIVE/cabinet/.env" "$RUNTIME/shared/cabinet.env"
rsync -a "$LIVE/instance/" "$RUNTIME/shared/instance/"
rsync -a "$HOME/Library/Application Support/cabinet/" "$RUNTIME/shared/app-support/" 2>/dev/null || true
ln -s "$RUNTIME/shared/instance" "$RELEASE/instance"
ln -s "$RUNTIME/shared/cabinet.env" "$RELEASE/cabinet/.env"
( cd "$RELEASE" && sudo bash cabinet/scripts/germline-lock.sh lock && bash cabinet/scripts/germline-lock.sh status )

# Step 3 — the cutover moment (3a officers / 3b manifest daemons / 3c cos-inbound / 3d sweep)
ln -sfn "$RELEASE" "$RUNTIME/current"
( cd "$RUNTIME/current" && CABINET_SOURCE_REPO="$RUNTIME/current" CABINET_ROOT="$RUNTIME/current" \
    bash cabinet/scripts/deploy-mac.sh --officer all )
( cd "$RUNTIME/current" && CABINET_ROOT="$RUNTIME/current" python3.12 cabinet/scripts/generate-plists.py )
for p in "$RUNTIME/current/cabinet/launchd/generated/"*.plist; do
  [ -e "$p" ] || continue
  plutil -lint "$p"
  launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$p"
done
sed "s|/Users/nate/captains-cabinet|$RUNTIME/current|g" \
  "$RUNTIME/current/cabinet/launchd/com.cabinet.officer.cos-inbound.plist" \
  > ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist
grep -l "/Users/nate/captains-cabinet" ~/Library/LaunchAgents/com.cabinet.*.plist   # expect NO OUTPUT

# Step 4 — verify
bash "$RUNTIME/current/cabinet/scripts/verify-launchagents.sh"
bash "$RUNTIME/current/cabinet/scripts/cabinet-doctor.sh"

# Step 5 — rollback, only if Step 4 is red
( cd /Users/nate/captains-cabinet && \
  CABINET_SOURCE_REPO=/Users/nate/captains-cabinet CABINET_ROOT=/Users/nate/captains-cabinet \
    bash cabinet/scripts/deploy-mac.sh --officer all )
( cd /Users/nate/captains-cabinet && CABINET_ROOT=/Users/nate/captains-cabinet python3.12 cabinet/scripts/generate-plists.py )
for p in /Users/nate/captains-cabinet/cabinet/launchd/generated/*.plist; do
  [ -e "$p" ] || continue
  launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$p"
done
cp /Users/nate/captains-cabinet/cabinet/launchd/com.cabinet.officer.cos-inbound.plist ~/Library/LaunchAgents/
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist
bash /Users/nate/captains-cabinet/cabinet/scripts/verify-launchagents.sh
bash /Users/nate/captains-cabinet/cabinet/scripts/cabinet-doctor.sh
```
