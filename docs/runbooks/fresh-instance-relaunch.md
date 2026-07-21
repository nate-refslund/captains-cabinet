# Fresh-Instance Relaunch — Runbook

**Status: DESIGNED, NOT EXECUTED.** Nothing in this document has been run.
It is Captain-gated the same way as its sibling
`docs/runbooks/dev-runtime-split-cutover.md`: every step that touches the
live fleet, the live tree, or a secret is a "we do it together" step, run
from the Captain's own session, never unattended.

**Reversible.** The old instance is fully archived before the cutover.
Nothing here deletes or modifies the old checkout, its `instance/` data, or
any officer's history — see Step 9 Rollback.

## 0. What "relaunch" means here, in plain terms

This is not a bug fix or an update — it's a deliberate fresh start.
Instead of updating the current fleet in place, we build a **brand-new
instance** on the already-built dev/runtime-split infrastructure
(`docs/runbooks/dev-runtime-split-cutover.md`), and we're selective about
what carries forward:

- **Carried forward:** nothing is *seeded* into the fresh instance (Captain
  100%-SCRATCH ruling, 2026-07-18 — the fresh instance inherits nothing). The
  one thing that "carries" isn't copied at all: your external Obsidian vault
  (searchable memory — conversations, people, decisions) stays exactly where
  it is on disk, and the fresh instance RECONNECTS to it read-only through the
  tracked screenpipe adapter (Step 5), never a seeded copy.
- **Left behind, on purpose (everything else):** the officers' accumulated
  product knowledge ("working notes" per role), the frozen correction-example
  corpus, your secrets (API keys — re-entered fresh on the new box), every
  officer's earned trust level (starts back at zero — the whole point of this
  relaunch is to re-earn it), internal governance records (decision logs,
  rule ledgers), the current hired roster (you re-hire who you want, nobody is
  pre-loaded), and the simulated "world" state. All of it is preserved in the
  pre-cutover archive (Step 2) as the restore net, but NONE of it is seeded
  into the fresh instance — that is produced entirely by the fresh-hatch
  defaults (Step 4).

The old itemized carry-vs-drop inventory is
`docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md` — now **superseded
in part** by the 100%-SCRATCH ruling (see its dated header): every former
KEEP-of-live-content row is DROP-from-seed now, preserved only in the Step 2
archive. This runbook is the step-by-step for actually doing it.

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
- [ ] **The NEW repo exists and is pushed BEFORE Step 3's
      `runtime-provision.sh init`.** Set `$NEW_REPO_URL` (§5 Step 3) to the
      fresh repo you created and pushed for this deployment — never the old
      private repo. `init` clones/mirrors that remote and `provision` fetches
      the commit you chose from it, so the repo must exist and the commit must
      already be pushed there, or `init`/`provision` fail against an empty or
      nonexistent remote.

## 2. Step-by-step

Legend: **[ME]** = scripted, no live-fleet impact, safe to run any time.
**[CAPTAIN]** = needs the Captain's own hands, physical access, or a sudo
prompt. **[CAPTAIN + ME]** = we run it together, live-fleet impact.

### Step 1 — Quiesce the old fleet **[CAPTAIN + ME]**

Nothing should be writing to the old instance while we archive it. If the
kill switch is ON at this point (check fresh — see Step
7.1's note; the manifest's own §5 records it was ACTIVE on 2026-07-15 and
INACTIVE on a 2026-07-16 recheck, so don't assume either way), it already
blocks officers from taking further actions, but that alone doesn't
guarantee a mid-flight officer has finished writing to disk — so stop each
officer's LaunchAgent outright regardless of kill-switch state (the same
stop primitive `dev-runtime-split-cutover.md` Step 3 already uses, just
without a re-bootstrap at the old path yet):

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

### Step 2 — Archive **[ME]**, zero live-tree writes

```bash
LIVE=$HOME/captains-cabinet
RUNTIME=~/.cabinet/runtime
bash "$LIVE/cabinet/scripts/relaunch-seed.sh" \
  --old-root "$LIVE" \
  --runtime-root "$RUNTIME"
```

What this does (see the script's own header comment for the full,
authoritative list if this ever drifts) — it **ARCHIVES ONLY; it seeds
nothing**:

1. **Archives the ENTIRE old-root tree** — the code, `.git`, the whole
   `instance/` tree (org-brain/searchable memory + every lane's working
   notes), `shared/interfaces/` (governance ledgers, world chronicle,
   product-specs), and the real, un-redacted `cabinet/.env` (this archive is
   the rollback safety net, so it deliberately keeps the real secrets) — to a
   timestamped file under your home directory, excluding only regenerable
   `__pycache__`/`*.pyc` noise. Plus a best-effort second member for
   `~/Library/Application Support/cabinet/` (the larger Mac-level state).
   **This archive contains real secrets — treat the file itself like a
   password, don't paste its contents anywhere.**
2. Refuses to run at all (before touching anything) if you mistakenly point
   the archive path or runtime root at the live tree itself, or nested inside
   its own read source — a hard, non-overridable safety check, not a flag you
   can turn off. (A relative `--archive-path` is absolutized first, so it
   can't sneak past that check by resolving into the old root.)

It writes **NOTHING into `$RUNTIME`** — the fresh instance inherits nothing;
its data is created entirely by the fresh hatch in Step 4. `--runtime-root` is
passed only so this step and Step 3 name the same target.

Run it with `--dry-run` first if you want to see the exact plan without
writing anything. Each run names a fresh archive file by default, so a re-run
never overwrites a previous safety snapshot.

### Step 3 — Provision the release **[ME]**, zero live-tree writes

Same as `dev-runtime-split-cutover.md` Step 1 — that runbook's own
instructions apply verbatim here (init the runtime root if this is the
first time, provision the commit you chose, validate with the `--dry-run`
proofs it already documents). One difference: skip that runbook's Step 2
(it copies the OLD instance data wholesale) — under the 100%-SCRATCH ruling
we deliberately seed nothing, so there is nothing in `$RUNTIME/shared/` for
`provision`'s own symlink step to pick up; the fresh instance's data is
created by the hatch in Step 4, and `provision` here just lays down the
pinned code checkout:

```bash
RUNTIME=~/.cabinet/runtime
LIVE=$HOME/captains-cabinet
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
- This step reads `instance/config/roster.yml` in the release's own tree —
  since nothing seeded it (the whole "left behind" list is DROP-from-seed), it
  doesn't exist yet, so hatch generates a genuinely fresh, empty roster: no
  product CEOs pre-hired. You re-hire whoever you want afterward, the normal
  way (`cabinet/scripts/create-officer.sh`).

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
by name in the fresh box's `cabinet/.env` (the one you populate on the new
box in Step 7 — nothing is seeded here) — if it's absent, that one
capability degrades quietly rather than failing anything else.

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

1. **Clear the kill switch, if it's on.** Check its LIVE state fresh —
   don't trust this doc or any prior session's note, since this is exactly
   the kind of boundary state that changes across sessions (it was
   observed ACTIVE on 2026-07-15 while this build was staged, and INACTIVE
   on a fresh 2026-07-16 recheck — Captain-side activity unrelated to this
   relaunch, not something either build session touched):
   ```bash
   bash cabinet/scripts/kill-switch.sh status
   ```
   Whatever its state, it stays exactly as-is straight through Steps 1–6
   above — an agent never touches it either direction, in either build
   session or on relaunch day. Once you're satisfied the new instance is
   healthy, if it's ON:
   ```bash
   bash cabinet/scripts/kill-switch.sh deactivate
   ```
2. **Set the Telegram bot token + re-enter secrets.** Nothing is seeded, so
   the fresh box's `cabinet/.env` (at `$RUNTIME/shared/cabinet.env`) starts
   empty — populate it on the new box. For the Chair, talk to @BotFather, get
   a fresh token, and add it. The chat id is unchanged — look it up in the
   Step 2 archive's `cabinet/.env` if you need it, but treat that archived
   file like a password.
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
at `$HOME/captains-cabinet` (the old dev tree, never modified by any
step above), using the same three mechanisms in reverse. Then, if you also
want the OLD deployment back exactly as it was (not just the code path): the
Step 2 archive holds **two** components under two distinct member prefixes —
the ENTIRE old-root tree under its own basename (e.g. `captains-cabinet/...`,
including `instance/`, `shared/interfaces/`, `.git`, and the real
`cabinet/.env`), and `Application Support/cabinet` from the Mac-level state.
Restore each to its own real location with its own `tar -xzf`, never both
with a single `-C`, or the Application Support half lands nested inside the
repo checkout instead of `~/Library/Application Support/`:

```bash
LIVE=$HOME/captains-cabinet
tar -xzf <archive-path> -C "$(dirname "$LIVE")" "$(basename "$LIVE")"
tar -xzf <archive-path> -C "$HOME/Library" "Application Support/cabinet"
```

(the first line restores the whole old-root tree in place — its member
prefix is the old-root's basename, so extracting from the PARENT dir lands it
back exactly where it was; the second line is a no-op if
`--skip-appsupport-archive` was passed at Step 2, or `~/Library/Application
Support/cabinet` simply didn't exist on this host at archive time — the
archive won't have that member, and `tar -xzf` skips restoring what isn't
there). Nothing above ever deleted or modified the original, so in the common
case rollback is just "repoint launchd" — the archive is the
belt-and-suspenders extra, not something you should need.

## 3. After relaunch — what's different

| | Old instance | Fresh instance |
|---|---|---|
| Roster | Whatever was hired before | Empty — you re-hire deliberately |
| Trust level per officer | Earned over time | Back to zero, re-earns from real behavior |
| Vault / searchable memory | Connected | Connected read-only via the adapter (same external vault — reconnected, never seeded) |
| Officer product knowledge | Present | Empty — fresh (old notes are in the archive only, not seeded) |
| Internal governance records (decision logs, rule ledgers) | Accumulated | Empty — genuinely fresh |
| Simulated "world" state | Accumulated | Fresh — old one is archived, not deleted |
| Telegram bot | Old token | New token (Captain-set on the fresh box), same chat |
| Secrets otherwise | — | Re-entered on the fresh box (not carried; the archive keeps the old ones for rollback) |

## 4. Troubleshooting

See `dev-runtime-split-cutover.md` §7 first — every symptom listed there
(roster not found, officer boots to a bare prompt, germline reported
unlocked, a manifest daemon still on the old path) applies here unchanged,
since Steps 3/6 above reuse those exact mechanisms. Two relaunch-specific
additions:

| Symptom | Likely cause | Fix |
|---|---|---|
| A product CEO is already hired right after Step 4 | A stray `roster.yml` is present in `$RUNTIME/shared/` from an earlier migration/seed (this archive-only relaunch never puts one there) | Confirm `instance/config/roster.yml` isn't present anywhere in `$RUNTIME/shared/`; if it is, remove it and re-provision so the fresh hatch's empty roster wins |
| The Chair can't answer questions from the vault | Step 5's two `sources.yml` lines are missing, or `OBSIDIAN_VAULT_PATH` was overridden somewhere to a path that isn't the real vault | Re-check `instance/config/sources.yml` in `$RELEASE`; confirm no stray `OBSIDIAN_VAULT_PATH` env var is set anywhere in the officer's environment |

## 5. Command reference — condensed, paste-ready, NOT YET RUN

```bash
# Step 1 — quiesce
for p in ~/Library/LaunchAgents/com.cabinet.officer.*.plist; do
  [ -e "$p" ] || continue
  launchctl bootout "gui/$(id -u)" "$p" 2>/dev/null || true
done

# Step 2 — archive only (zero live-tree writes; seeds nothing)
LIVE=$HOME/captains-cabinet
RUNTIME=~/.cabinet/runtime
bash "$LIVE/cabinet/scripts/relaunch-seed.sh" --old-root "$LIVE" --runtime-root "$RUNTIME"

# Step 3 — provision
# NEW_REPO_URL: the fresh repo you created + pushed for this relaunch (§1
# preconditions) — NOT the old private repo. Must exist and hold the commit
# you provision below BEFORE `init` runs.
NEW_REPO_URL=https://github.com/<your-org>/<your-cabinet-repo>.git
bash "$LIVE/cabinet/scripts/runtime-provision.sh" init "$RUNTIME" \
  --remote "$NEW_REPO_URL"
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
# set a fresh Telegram token via @BotFather + re-enter secrets into the (empty) $RUNTIME/shared/cabinet.env  [CAPTAIN]
( cd "$RELEASE" && sudo bash cabinet/scripts/germline-lock.sh lock && bash cabinet/scripts/germline-lock.sh status )
bash "$RUNTIME/current/cabinet/scripts/cabinet-doctor.sh"

# Step 8 — verify: follow docs/runbooks/dev-runtime-split-cutover.md Step 4 verbatim

# Step 9 — rollback, only if Step 8 is red: follow docs/runbooks/dev-runtime-split-cutover.md
# Step 5 verbatim; restore the OLD deployment from the Step 2 archive only if truly needed
# (two components, two distinct member prefixes — restore each separately, never one -C for both):
#   tar -xzf <archive-path> -C "$(dirname $HOME/captains-cabinet)" "$(basename $HOME/captains-cabinet)"
#   tar -xzf <archive-path> -C "$HOME/Library" "Application Support/cabinet"
```
