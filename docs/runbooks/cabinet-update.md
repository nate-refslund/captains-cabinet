# Runbook — taking an update on an installed Cabinet

An installed Cabinet is an unpacked export: no version control, no remote, no
way to learn on its own that better bytes exist. `cabinet/scripts/cabinet-update.sh`
is the leg that closes that — the one that makes an improvement the org made
about itself actually reach the machine the operator runs.

**The operator never needs this file.** The whole path is one card on the
dashboard home page: *Update ready — N files changed*, Apply, and afterwards
*Updated to `<sha>`* with Roll back. This runbook is for whoever fills the
inbox, and for reading a refusal.

## The shape

| | |
|---|---|
| Bundle | `<root>/.updates/inbox/<sha>.tar.gz` + `<sha>.manifest.json` |
| Identity | `egg-manifest.json` → `source_commit`. There is no second version file |
| Snapshots | `<root>/.updates/snapshots/<stamp>-<from-sha>/`, newest 3 kept |
| State | `<root>/.updates/state.json` — what the card reads |
| Log | `<root>/.updates/update.log` |
| Receipts | `cabinet_update_applied` / `_refused` / `_rolled_back` in the ledger |

## Publishing a bundle (the producer side)

Run from a **checkout**, after the improvement has landed on the main branch —
never on the install itself:

```bash
bash cabinet/scripts/cabinet-update.sh publish \
     --from /path/to/checkout --to /path/to/installed/cabinet
```

That runs `egg-export.sh --bundle` into the install's inbox: the same cut a
fresh install would receive, packaged, with per-file `sha256`, the source
commit, a changelog of the commits since the install's own, and — as
information only — the constitutional set as the checkout declares it.

## Taking it

```bash
bash cabinet/scripts/cabinet-update.sh status            # what is installed, what waits
bash cabinet/scripts/cabinet-update.sh apply --bundle <sha>
bash cabinet/scripts/cabinet-update.sh rollback          # newest snapshot
```

`--from terminal|web|chat` records the door. The terminal door is
**attribution, not authentication** — it is the same account every worker runs
as — so it never records the Captain as the actor; only an authenticated web or
chat door does.

What `apply` does, in order: verify every file against the manifest → refuse
outright if any differing path is in the constitutional set → snapshot the
pre-images → write (each file to a temporary name and rename) → **rebuild the
dashboard, but only if the bundle changed a file under
`cabinet/dashboard/`** — in a staging tree, with the built output swapped in
last → restart the dashboard → run the health gate → prune old snapshots and
staged trees. A red gate rolls the whole thing back automatically and records
why; the staged tree is dropped on the way out of every exit, green or not.

### The health gate, and why the rebuild condition is part of it

The gate has three legs — the dashboard, the receipt ledger, and the
persistence preflight — and the dashboard leg asks three separate questions of
`/api/health`:

| Field | Question | Where the value comes from |
|---|---|---|
| `source_commit` | which Cabinet is this? | the environment the process was started with (`start-dashboard.sh` reads `egg-manifest.json`, which the apply rewrites *before* it restarts) |
| `build_commit` | which build is serving? | inlined when the dashboard was built |
| `started_at` | did it actually restart? | the process's own uptime |

`source_commit` and `started_at` are checked on every apply. **`build_commit`
is checked only when this apply rebuilt** — and that is the half that has to
match the rebuild condition above. A bundle that changes no dashboard file
restarts the same build, so its build stamp is still the previous commit and
always will be; demanding the new one there rolled every framework-only update
back automatically, with the improvement undone and a
`cabinet_update_rolled_back` receipt to show for it (found in review,
2026-09-07 — the majority bundle shape).

Read the two together: **the rebuild is conditional, so the build-stamp leg is
conditional.** If a later change makes the rebuild unconditional, the leg
becomes unconditional with it; if the leg is ever armed for an apply that did
not rebuild, every framework-only update rolls back again.

## The refusals, and what each one means

| Exit | Meaning |
|---|---|
| 0 | applied, or already at that commit (a no-op writes nothing) |
| 1 | the update ran and did not survive its gate; the previous bytes are back |
| 2 | usage |
| 3 | refused before the first write — nothing was touched |
| 4 | another update is running |

Exit 4 is a refusal like any other and leaves a `cabinet_update_refused`
receipt with `reason: busy` — from `rollback` as well as from `apply`. **One
updater at a time, and the lock is the first thing either command takes**,
ahead of every write it makes, including the copy of itself it runs from
(`.updates/run/`). Copying over a script another process is executing makes
that process continue out of the new file's bytes, so the lock comes first and
the copy lands by rename rather than in place.

Exit 3 covers: a per-file digest mismatch; an absent, empty or unreadable
bundle; **any** differing path inside the constitutional set; and a preserve
declaration neither side carries. Every one of them is whole-bundle — partial
application is never a legal state.

**A constitutional-set refusal is not a bug.** Those bytes are changed by a
deliberate ceremony — unlock, apply, lock again in the same sitting — not by an
unattended update. The refusal prints the paths, the current boundary state,
and that sentence.

## What it never touches

- **Your own data.** The preserve set is declared, not typed: it is the union
  of the shipped `cabinet/config/egg-preserve-set.txt` (generated at export
  time from the export manifest's own rules plus the ledgers the export ships
  empty), the bundle's copy of it, and the persistence lists
  `runtime-provision.sh lists` prints. A bundle that ships a preserved path is
  not applied and not silently dropped: it is reported as `skipped_preserved`,
  on the card and in the receipt.
- **Anything it did not ship you.** Deletions are previous-manifest minus
  new-manifest, so a first apply — and every install that has never taken an
  update — deletes nothing at all.
- **Service definitions, secrets, and the menu-bar companion.**

## Reading a health-gate rollback

The gate is three legs, and it is deliberately not an identity probe: the
dashboard must answer carrying **the new build's commit** and a start time
later than the apply began (an old process that survived a failed restart
answers happily otherwise), the receipt ledger must still read, and the
state-persistence preflight must pass. `cabinet-doctor` is **reported, not
gated** — a single-worker install is legitimately dead on fleet services it was
never meant to run, and gating on it would roll back every good update.

If the gate goes red the previous bytes, and the previous dashboard build, are
restored before anything else, and `cabinet_update_rolled_back` carries the
reason.

## Interrupted mid-apply

`state.json` stays at `applying` with its snapshot on disk, and the tree is
neither version. The next `apply` or `rollback` restores that snapshot **first**
and says so. Nothing else runs until it has.

## Where the Captain hears about it

Two surfaces, both derived and neither hand-maintained: the home card
(`Update ready — N files changed`, then `Updated to <sha>`, with Roll back) and
one line on the daily briefing. The briefing line reads the inbox and the state
file directly — a briefing must never be able to hang on a subprocess — and
reads the three `cabinet_update_*` receipts back off the ledger for the one
state the files cannot carry: a REFUSAL writes no state at all, so without that
read a bundle refused for touching the constitutional set would sit in the
inbox for ever behind a sentence saying "ready to take".

## First bootstrap

An install that predates this leg has no updater in it, so it cannot take the
bundle that would give it one. That first hop is a one-off act by whoever
publishes: copy the bundle's `cabinet-update.sh` and `lib/update_bundle.py`
into `<root>/.updates/run/` and run `apply` from there. Every later update is
the card.
