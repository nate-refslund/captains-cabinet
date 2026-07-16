# Fresh-Instance Relaunch — Runbook

**Status: DESIGNED, NOT EXECUTED.** Nothing in this document has been run.
It is Captain-gated the same way as its sibling
`docs/runbooks/dev-runtime-split-cutover.md`: every step that touches the
live fleet, the live tree, or a secret is a "we do it together" step, run
from the Captain's own session, never unattended.

**Reversible.** The old instance is fully archived before anything is
seeded or moved. Nothing here deletes the old checkout, its `instance/`
data, or any officer's history — see §7 Rollback.

## 0. What "relaunch" means here, in plain terms

This is not a bug fix or an update — it's a deliberate fresh start.
Instead of updating the current fleet in place, we build a **brand-new
instance** on the already-built dev/runtime-split infrastructure
(`docs/runbooks/dev-runtime-split-cutover.md`), and we're selective about
what carries forward:

- **Carried forward:** the vault (your searchable memory — conversations,
  people, decisions), the officers' accumulated product knowledge
  ("working notes" per role), the frozen set of real correction examples
  used to test the system, and your secrets (API keys, etc.) — except the
  Telegram bot token, which gets a fresh one.
- **Left behind, on purpose:** every officer's earned trust level (starts
  back at zero — the whole point of this relaunch is to re-earn it),
  internal governance records (decision logs, rule ledgers), the current
  hired roster (you re-hire who you want, nobody is pre-loaded), and the
  simulated "world" state (starts fresh).

The full itemized list of what's carried vs. left behind, and why, is
`docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md`. This runbook
is the step-by-step for actually doing it.

**Relationship to the dev/runtime-split cutover runbook:** that document
is the one-time plumbing change (give the fleet its own clean checkout,
separate from your dev tree). This document assumes that plumbing exists
and layers the fresh-instance decision on top of it — it points at that
runbook's steps by name instead of repeating them, and calls out
everywhere the two differ.

## 1. Preconditions checklist

- [ ] `docs/runbooks/dev-runtime-split-cutover.md`'s own preconditions are
      met (current fleet green, no other deploy/restart in progress).
- [ ] `cabinet/scripts/runtime-provision.sh` and `cabinet/scripts/
      cabinet-deploy.sh` exist on the commit you're about to provision —
      merged from `feat/dev-runtime-split` (already true on this branch).
- [ ] `cabinet/scripts/relaunch-seed.sh` exists on that same commit (this
      build adds it).
- [ ] You have decided WHICH commit becomes the fresh instance's starting
      point (defaults to `origin/master`'s tip if you don't name one).
- [ ] You've read the manifest doc once (§0 above) so the "why" behind
      each step below isn't a surprise.

## 2. Step-by-step

Legend: **[ME]** = scripted, no live-fleet impact, safe to run any time.
**[CAPTAIN]** = needs the Captain's own hands, physical access, or a sudo
prompt. **[CAPTAIN + ME]** = we run it together, live-fleet impact.

### Step 1 — Quiesce the old fleet **[CAPTAIN + ME]**

Nothing should be writing to the old instance while we archive and seed
from it. The kill switch already blocks officers from taking further
actions (verified ACTIVE independently — see §6), but that alone doesn't
guarantee a mid-flight officer has finished writing to disk. Stop each
officer's LaunchAgent outright (the same stop primitive
`dev-runtime-split-cutover.md` Step 3 already uses, just without a
re-bootstrap at the old path yet):

```bash
launchctl list | grep com.cabinet.officer   # see what's actually loaded
for p in ~/Library/LaunchAgents/com.cabinet.officer.*.plist; do
  [ -e "$p" ] || continue
  launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
done
launchctl list | grep com.cabinet.officer && echo "still running — investigate" || echo "fleet quiesced"
```

This is a pause, not a teardown: the plists, the tmux sessions' history,
and all instance data are untouched — Step 7's rollback restarts the same
way `dev-runtime-split-cutover.md` Step 5 does.

### Step 2 — Archive + seed **[ME]**, zero live-tree writes

```bash
LIVE=/Users/nate/captains-cabinet
RUNTIME=~/.cabinet/runtime
bash "$LIVE/cabinet/scripts/relaunch-seed.sh" \
  --old-root "$LIVE" \
  --runtime-root "$RUNTIME"
```

What this does (see the script's own header comment for the full,
authoritative list if this ever drifts):

1. **Archives the entire old `instance/` tree + `cabinet/.env`** (the real,
   un-redacted secrets — this archive is the rollback safety net, so it
   deliberately keeps the real token) to a timestamped file under your
   home directory, plus a best-effort archive of
   `~/Library/Application Support/cabinet/` (the larger Mac-level state).
   **This archive contains real secrets — treat the file itself like a
   password, don't paste its contents anywhere.**
2. **Writes the curated fresh seed** into `$RUNTIME/shared/` — only the
   "carried forward" list from §0, with the Telegram token's value
   replaced by a placeholder (chat id untouched). Nothing on the "left
   behind" list is ever read by this step.
3. Refuses to run at all (before touching anything) if you mistakenly
   point it at the live tree itself, or at itself nested inside its own
   read source — this is a hard, non-overridable safety check, not a flag
   you can turn off.

Run it with `--dry-run` first if you want to see the exact plan without
writing anything. Re-running the real command is safe — it converges to
the same result rather than piling up duplicates (a fresh archive file is
the one exception: each run names a new one, on purpose).

**Known gap, not fixed by this build:** the frozen regression-test corpus
(`instance/fidelity/regression_corpus/`) gets captured into the seed for
safekeeping, but `runtime-provision.sh` doesn't yet automatically carry
that particular folder into a release. Either commit any new test cases to
the branch before doing Step 3, or copy them into the release by hand
afterward — flagged here rather than silently assumed to work.

### Step 3 — Provision the release **[ME]**, zero live-tree writes

Same as `dev-runtime-split-cutover.md` Step 1 — that runbook's own
instructions apply verbatim here (init the runtime root if this is the
first time, provision the commit you chose, validate with the `--dry-run`
proofs it already documents). One difference: skip that runbook's Step 2
(it copies the OLD instance data wholesale) — Step 2 above already put the
curated fresh seed in place, and `provision`'s own symlink step (called
again here, idempotently) picks it up:

```bash
RUNTIME=~/.cabinet/runtime
LIVE=/Users/nate/captains-cabinet
bash "$LIVE/cabinet/scripts/runtime-provision.sh" provision "$RUNTIME" origin/master   # or your chosen commit
RELEASE=$(bash "$LIVE/cabinet/scripts/runtime-provision.sh" provision "$RUNTIME" origin/master | sed -n 's/^PROVISIONED_SLOT=//p')
```

### Step 4 — Hatch the fresh instance shape **[ME]**

Run the same one-command hatch every brand-new Cabinet uses, against the
release you just provisioned — this is what actually turns the bare code
checkout into a real instance (generates a default roster, activates the
Chair, runs the proof gates, prints the first briefing):

```bash
cd "$RELEASE"
bash cabinet/scripts/hatch.sh --defaults
```

Notes:
- **Don't add `--with-launchd`.** Step 6 below handles pointing launchd at
  the new tree, using the exact same three-mechanism approach
  `dev-runtime-split-cutover.md` Step 3 already documents — running
  hatch's own launchd move-in here would set up a competing path.
- **Don't add `--clean-room`.** That mode is for throwaway rehearsals and
  actively refuses to run against a real checkout like this one. Plain
  `--defaults` is correct and expected to just work — `hatch.sh` already
  knows how to handle a checkout that ships its own tracked default config
  (it archives the tracked copy aside and generates fresh, same as any
  first-time hatch of this repo).
- This step reads `instance/config/roster.yml` through the symlink Step 2
  set up — since that file was on the "left behind" list, it doesn't exist
  yet, so hatch generates a genuinely fresh, empty roster: no product CEOs
  pre-hired. You re-hire whoever you want afterward, the normal way
  (`cabinet/scripts/create-officer.sh`).

### Step 5 — Connect the vault (screenpipe adapter), opt-in **[ME]**

The code for this is already part of the checkout (it's tracked in git,
same as any other file) — this step is a verification, not a new file to
write. Confirm `instance/config/sources.yml` in the release still carries:

```yaml
adapter: flavor_a.screenpipe_source:ScreenpipeSource
dispatch: flavor_a.screenpipe_dispatch:ScreenpipeDispatch
```

If it's missing (e.g., a future commit reset it to the framework's
default-off state), the exact two lines to restore are documented at
`instance/flavor-a/README.md`. With those two lines present, the fresh
instance reads your existing vault (`~/Obsidian/screenpipe-brain` — an
external folder this relaunch never touches or copies) the moment it
boots; no path needs to be typed in, since the adapter's default already
points there. If you also want live screen/audio capture read through
(not just the vault notes), confirm `SCREENPIPE_API_AUTH_KEY` is present
by name in the seeded `cabinet/.env` — if it's absent, that one capability
degrades quietly rather than failing anything else.

### Step 6 — Repoint launchd **[CAPTAIN + ME]** — the actual cutover moment

This is identical to `dev-runtime-split-cutover.md` Step 3 — same three
mechanisms (officer plists via `deploy-mac.sh`, the manifest-driven
daemons via `generate-plists.py`, the Chair's static Telegram-receive
plist via the documented `sed` substitution), same catch-all `grep` sweep
afterward to prove nothing was missed. Follow that runbook's Step 3
exactly, pointed at `$RELEASE`/`$RUNTIME/current` as it already describes.
This is the moment officers actually (re)start, on the new path, with the
fresh roster from Step 4.

### Step 7 — Captain-only steps

These are steps nobody but the Captain does — some are literally
impossible for an agent to do (a physical BotFather conversation), others
are deliberately reserved so a mistake can't cascade unattended.

1. **Clear the kill switch.** It's currently ON (verified independently,
   not something this relaunch turned on) and stays on straight through
   Steps 1–6 above — an agent never touches it either direction. Once
   you're satisfied the new instance is healthy:
   ```bash
   bash cabinet/scripts/kill-switch.sh deactivate
   ```
2. **Rotate the Telegram bot token.** Talk to @BotFather, get a new token
   for the Chair, and paste it into the seeded `cabinet/.env` in place of
   the `__ROTATE_ME__` placeholder Step 2 left there. The chat id doesn't
   change.
3. **Re-lock the protected config files** on the fresh checkout (this Mac
   calls this "germline" locking — it's a filesystem-level protection so
   nobody, agent or human, can casually edit certain safety-relevant
   files by accident):
   ```bash
   cd "$RELEASE"
   sudo bash cabinet/scripts/germline-lock.sh lock
   bash cabinet/scripts/germline-lock.sh status   # confirm it reports fully locked, no sudo needed to check
   ```
4. **Confirm the instance is fully healthy** — the same all-clear check
   every deploy in this repo uses:
   ```bash
   bash "$RUNTIME/current/cabinet/scripts/cabinet-doctor.sh"
   ```
   A clean pass here is the real "done" signal for this whole relaunch.

### Step 8 — Verify

Same checklist as `dev-runtime-split-cutover.md` Step 4: the launchd path
sweep shows nothing pointing at the old tree, `verify-launchagents.sh`
and `cabinet-doctor.sh` both pass, the Chair's tmux session is live, and a
real Telegram DM to the Chair gets a reply (**[CAPTAIN]** — sending that
confirmation DM is always a human action, never automated). Additionally
for this relaunch specifically, confirm:

- `list-officers`-style check (or simply `cabinet/scripts/create-officer.sh
  --list` / your usual roster view) shows an **empty** roster, not the old
  product CEOs — if a product CEO shows up already hired, Step 4 read a
  stale roster somewhere and needs re-checking before you rely on this
  being a true fresh start.
- The vault connection is live: ask the Chair something only the vault
  would know (a real fact from a past conversation) and confirm it
  answers correctly.

### Step 9 — Rollback **[CAPTAIN + ME]** — same shape, reverse direction

Identical to `dev-runtime-split-cutover.md` Step 5: repoint launchd back
at `/Users/nate/captains-cabinet` (the old dev tree, never modified by any
step above), using the same three mechanisms in reverse. Then, if you also
want the OLD instance data back exactly as it was (not just the code
path): the Step 2 archive holds **two** components under two distinct
prefixes (`instance` + `cabinet/.env` from the repo; `Application
Support/cabinet` from the Mac-level state) — restore each to its own real
location with its own `tar -xzf`, never both with a single `-C`, or the
Application Support half lands nested inside the repo checkout instead of
`~/Library/Application Support/`:

```bash
tar -xzf <archive-path> -C /Users/nate/captains-cabinet instance cabinet/.env
tar -xzf <archive-path> -C "$HOME/Library" "Application Support/cabinet"
```

(the second line is a no-op if `--skip-appsupport-archive` was passed at
Step 2, or `~/Library/Application Support/cabinet` simply didn't exist on
this host at archive time — the archive won't have that member, and
`tar -xzf` skips restoring what isn't there). Nothing above ever deleted or
modified the original, so in the common case rollback is just "repoint
launchd" — the archive is the belt-and-suspenders extra, not something you
should need.

## 3. After relaunch — what's different

| | Old instance | Fresh instance |
|---|---|---|
| Roster | Whatever was hired before | Empty — you re-hire deliberately |
| Trust level per officer | Earned over time | Back to zero, re-earns from real behavior |
| Vault / searchable memory | Connected | Connected (same vault, same history) |
| Officer product knowledge | Present | Carried forward (the "working notes" per role) |
| Internal governance records (decision logs, rule ledgers) | Accumulated | Empty — genuinely fresh |
| Simulated "world" state | Accumulated | Fresh — old one is archived, not deleted |
| Telegram bot | Old token | New token (Captain-rotated), same chat |
| Secrets otherwise | — | Carried forward unchanged |

## 4. Troubleshooting

See `dev-runtime-split-cutover.md` §7 first — every symptom listed there
(roster not found, officer boots to a bare prompt, germline reported
unlocked, a manifest daemon still on the old path) applies here unchanged,
since Steps 3/6 above reuse those exact mechanisms. Two relaunch-specific
additions:

| Symptom | Likely cause | Fix |
|---|---|---|
| A product CEO is already hired right after Step 4 | Something copied the old `roster.yml` forward instead of leaving it absent | Re-check Step 2 actually ran against this release's `$RUNTIME` (not an old one), and that `instance/config/roster.yml` isn't present anywhere in `$RUNTIME/shared/` before re-provisioning |
| The Chair can't answer questions from the vault | Step 5's two `sources.yml` lines are missing, or `OBSIDIAN_VAULT_PATH` was overridden somewhere to a path that isn't the real vault | Re-check `instance/config/sources.yml` in `$RELEASE`; confirm no stray `OBSIDIAN_VAULT_PATH` env var is set anywhere in the officer's environment |

## 5. Command reference — condensed, paste-ready, NOT YET RUN

```bash
# Step 1 — quiesce
for p in ~/Library/LaunchAgents/com.cabinet.officer.*.plist; do
  [ -e "$p" ] || continue
  launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
done

# Step 2 — archive + seed (zero live-tree writes)
LIVE=/Users/nate/captains-cabinet
RUNTIME=~/.cabinet/runtime
bash "$LIVE/cabinet/scripts/relaunch-seed.sh" --old-root "$LIVE" --runtime-root "$RUNTIME"

# Step 3 — provision
bash "$LIVE/cabinet/scripts/runtime-provision.sh" init "$RUNTIME" \
  --remote https://github.com/nate-refslund/captains-cabinet.git
bash "$LIVE/cabinet/scripts/runtime-provision.sh" provision "$RUNTIME" origin/master
RELEASE=$(bash "$LIVE/cabinet/scripts/runtime-provision.sh" provision "$RUNTIME" origin/master | sed -n 's/^PROVISIONED_SLOT=//p')

# Step 4 — hatch (no --with-launchd, no --clean-room)
( cd "$RELEASE" && bash cabinet/scripts/hatch.sh --defaults )

# Step 5 — confirm the vault adapter is wired (read-only check)
grep -q "adapter: flavor_a.screenpipe_source:ScreenpipeSource" "$RELEASE/instance/config/sources.yml" \
  && echo "adapter wired" || echo "MISSING — restore per instance/flavor-a/README.md"

# Step 6 — repoint launchd: follow docs/runbooks/dev-runtime-split-cutover.md Step 3 verbatim,
# pointed at $RELEASE / $RUNTIME/current

# Step 7 — Captain-only
bash cabinet/scripts/kill-switch.sh deactivate                 # [CAPTAIN]
# rotate the Telegram token via @BotFather, paste into $RUNTIME/shared/cabinet.env  [CAPTAIN]
( cd "$RELEASE" && sudo bash cabinet/scripts/germline-lock.sh lock && bash cabinet/scripts/germline-lock.sh status )
bash "$RUNTIME/current/cabinet/scripts/cabinet-doctor.sh"

# Step 8 — verify: follow docs/runbooks/dev-runtime-split-cutover.md Step 4 verbatim

# Step 9 — rollback, only if Step 8 is red: follow docs/runbooks/dev-runtime-split-cutover.md
# Step 5 verbatim; restore old instance data from the Step 2 archive only if truly needed
# (two components, two distinct prefixes — restore each separately, never one -C for both):
#   tar -xzf <archive-path> -C /Users/nate/captains-cabinet instance cabinet/.env
#   tar -xzf <archive-path> -C "$HOME/Library" "Application Support/cabinet"
```
