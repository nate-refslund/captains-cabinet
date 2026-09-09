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
| State | `<root>/.updates/state.json` — phase, the legacy refusal mirror, `last_busy` |
| Refusal markers | `<root>/.updates/refusals/<sha>.json` — one verdict per bundle, the durable store a whole-document state replace cannot reach |
| Log | `<root>/.updates/update.log` |
| Receipts | `cabinet_update_applied` / `_refused` / `_rolled_back` in the ledger |
| Held records | `<root>/.updates/events.jsonl` — receipts this install's ledger would not take yet, replayed by the next apply |
| State lock | `<root>/.updates/.state.lock` — held for the read-modify-write of `state.json` only, so a busy refusal cannot write a stale copy back over the updater that beat it |

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

### Every refusal is durable, and every surface reads it

**Two classes, and they are not the same record (A5.17).** A **verdict** is
about the bundle's bytes — a locked constitutional path, a digest mismatch, an
unreadable bundle. A **timing note** is `busy`, or any record naming no bundle
at all: another updater held the lock, which says nothing about what is in the
inbox. A verdict binds its sha until a strictly newer apply or rollback names
that sha. A timing note is about no bundle: it never resolves, never occupies a
verdict store, never moves `phase` to `refused`, and never supersedes or is
superseded by anything.

**A verdict is written down three times, by one call, in this order:**

| | |
|---|---|
| `<root>/.updates/refusals/<sha>.json` | `{bundle, reason, paths, ts, door}` — the DURABLE store, one file per refused bundle |
| `cabinet_update_refused` | the ledger receipt, through the recorder that survives an older emitter |
| `<root>/.updates/state.json` | `phase: refused` plus the fields, and `last_refusal` as a legacy MIRROR of the newest verdict — unless `phase` is `applying` |

A timing note writes its receipt and `state.json.last_busy {bundle, ts, door}`,
and nothing else.

**Why a file per bundle rather than a field.** Every write to `state.json` is a
whole-document replace, by several writers, and during an update one of them
can be an OLDER updater copy that has never heard of the field — the install
carries the updater it was cut with, and an update is exactly the moment two
versions exist on one box. A single slot is lost the moment anything else
happens; a map is lost the moment an older copy writes. The marker survives
both. It is deleted by the apply or rollback that NAMES its sha (the verdict is
spent when the tree moves), never while its sha is still in the inbox, and the
store is bounded at 64 with the same exemption.

A failed marker or state write is NAMED, never swallowed and never raised:
`record-refusal` returns `state_error`, the updater logs `STATE WRITE FAILED`,
and `status --json` carries it — raising would lose the receipt the ledger
already took.

**Time is the record's own.** Every update event carries `recorded_at` in its
payload, stamped by the updater when the record was made, and every marker
carries `ts`. The ledger's insertion time is never used for ordering: a record
held for an older emitter is replayed by the NEXT apply, so under insertion
order a refusal from last week is newer than the update that overtook it.
Position in the ledger is not an input either — only times among records naming
the same sha are ever compared.

**`status --json` resolves ONE answer, about ONE bundle.**

```json
{ "phase": "refused",
  "last_refusal_source": "state",
  "last_refusal": { "bundle": "113b52c4…", "reason": "bundle 113b52c4… changes
    locked constitutional paths", "paths": ["cabinet/scripts/start-officer-mac.sh"],
    "ts": "2026-09-08T18:58:00Z", "door": "terminal" },
  "waiting_rollback": null,
  "last_busy": { "bundle": "", "ts": "2026-09-09T10:00:30Z", "door": "web" },
  "state_error": "" }
```

`last_refusal` is `current(W)` for the bundle W that is waiting: the newest
verdict about W — from its marker, from the ledger, or (only on an install with
no marker store at all) from the legacy `last_refusal` — that no strictly newer
apply or rollback about W has superseded, on either channel. Equal times keep
the refusal: a relock landing in the same second as the verdict has not proved
the bytes acceptable. When nothing is waiting, it is the newest verdict
anywhere that is newer than every applied and rolled-back record; else null.
`last_refusal_source` is `state`, `receipt`, or empty, and ties go to `state`.
The report never writes.

**Both surfaces consume only that.** No surface reads a receipt or a state
field to speak a refusal. In this order, identically on the home card and the
briefing line:

1. `phase: applying` → the applying sentence, no refusal.
2. W waiting with a current verdict naming locked paths → *Update refused — N
   constitutional files differ; needs the Captain (W)*, the files named on the
   card, **Apply withdrawn** — those bytes change by a ceremony and no number
   of taps will do it.
3. W waiting with any other current verdict → *Update refused — <reason> (W)*,
   **Apply kept**: a retry re-tests.
4. W waiting, no current verdict, and the newest record about W is a rollback
   FROM W → *Update rolled back — <reason>; still waiting (W)*, Apply kept.
5. W waiting otherwise → *Update ready*, regardless of any other bundle's
   records.
6. Nothing waiting → the resolved verdict if any, else the existing applied /
   rolled-back / quiet ladder.

`busy` is never a headline anywhere; `cabinet-update.sh status` and `last_busy`
carry it.

**What each round of review paid for.** A refusal that spoke for as long as the
phase said `refused` spoke over every bundle published afterwards — including
the one cut right after the Captain's ceremony — and withdrew Apply with it,
which is the only no-terminal way to take an update (round 1). Rule 1's
`applying` guard was written on the card only, so through every designed retry
the card said "Taking an update" and the briefing said "Update refused" (round
2). A refusal that spoke for as long as it was ON RECORD outlived the apply
that overtook it, and both surfaces then said *Update refused — busy* over a
Cabinet running exactly those bytes, for ever (round 3). The rules were applied
to ONE of two channels, so a locked-path refusal that had reached only the
ledger gave the briefing *REFUSED* while the card rendered Apply (round 4).
And the resolution itself took the newest refusal receipt GLOBALLY: a `busy`
note written by a rollback that lost the lock — a record about no bundle at all
— blanked the constitutional verdict on the bundle in the inbox, and both
surfaces said *ready to take — tap Apply* over it (round 5). Round 4 was
card-wrong and briefing-right; round 5 was both wrong, in agreement, which is
worse.

None of that is a claim, and it is no longer proved by the states somebody
thought of. Two checked-in fixtures under `framework/frontdoor/tests/` are
driven through all THREE readers — the briefing (`test_card_update_notice.py`),
the resolver the card is fed by (`test_cabinet_update.py`) and the card itself
(`lib/updates.test.ts`):

* `update_surface_parity.json` — the argued cases, with the exact wording each
  surface must produce and the resolution each must reach.
* `update_surface_oracle.json` — the WHOLE product of the six axes these
  readers branch on: phase (5) × what is waiting (3) × what the state channel
  says about B (5) × the ledger's SEQUENCE about B (7) × the newest ledger
  record not about B (5) × ledger fault (2) = **5250 rows**, each carrying the
  exact sentence for both surfaces, whether the refusal speaks, whether Apply
  is live, and which channel answered. Four inputs are held outside the product
  as INVARIANCE arms over sampled rows — a marker about another bundle,
  `last_busy` in any value, `event_fallback` either way, and the ledger's
  record order — because each is claimed independent, and a claim of
  independence is worth what it is tested at.

A sentence or a flag changed in either file reds all three suites. The ledger
became an axis when round 4 found the defect living exactly where the table did
not look — all 240 rows ran on an empty ledger — and became an axis of
SEQUENCES when round 5 found the same thing one level down: 1440 rows, every
one of them with at most ONE receipt about the refused bundle, so "the newest
refusal about B" and "the newest refusal anywhere" were indistinguishable and
the shape `refuse_busy` writes on every lock contention was not representable
at any point in the product. A completeness claim that holds an input's DEPTH
constant is a green hole, not a covered one.

### When this install's ledger does not know the event yet

The emitter that knows `cabinet_update_applied` **arrives with the update that
event announces**, so the first apply on any install cut before this leg
existed cannot record it — measured on the box as `ValueError: Unknown event
type: cabinet_update_refused`. The updater therefore records through its own
recorder: the installed emitter first, and on any refusal from it an identical
record is appended to `<root>/.updates/events.jsonl` with
`state.json.event_fallback` set and a line on the log saying so. Nothing is
dropped and nothing crashes.

**Held is not the same as broken.** Two very different things put a record in
that file, and only one of them heals itself:

| `status` says | what happened | what to do |
|---|---|---|
| `held: a record is waiting … for a newer ledger` | the emitter is one version behind and does not know the event type yet | nothing — the next apply files it |
| `held: ledger fault: <why>` (`ledger_error` in `status --json`) | the ledger **failed** — a full disk, a permission, a file that will not open | look at the ledger; no update fixes this one |

The next successful apply replays those records into the ledger **after the new
tree is in place**, once each — idempotent on the record's own id, which the
replayed ledger row carries as `deferred_record_id` — and renames the sidecar
to `events.ingested-<ts>-<pid>-<n>.jsonl` rather than deleting it. Replaying
before the health gate is deliberate: a rollback undoes the bytes, and must not
also undo the record that they were there.

The batch is renamed to `events.draining-<ts>-<pid>.jsonl` **before** it is
read, so a record held by another updater while the replay runs lands in a
fresh `events.jsonl` and is picked up next time instead of being retired
unreplayed. A drain that could not finish keeps that name and the next ingest
folds it back in.

**"Once each" means once per completed replay.** The record's id goes into the
marker *after* its row reaches the ledger, so a crash between the two replays
that one row on the next pass and the ledger carries it twice — deliberate, and
the other order is worse: marking first turns the same crash into a record that
never reaches the ledger at all. A duplicate is visible and deduplicable by
`deferred_record_id`; a hole is neither, and no record being lost is the one
guarantee this path makes.

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
falls back to the three `cabinet_update_*` receipts on the ledger for anything
the state file does not carry.

Both channels answer a refusal, and they have to: the state file is written by
the updater itself, and the ledger is exactly what an install too old to know
the event kind refuses to write. On 2026-09-08 both were silent on the same
refusal, and the sentence waiting for the Captain was "an update is ready to
take — tap Apply", over a bundle that had already been turned down.

## Reading a held record

`status` says `held: a record is waiting in .updates/events.jsonl for a newer
ledger`, and `status --json` says `event_fallback: true`. The file is one JSON
object per line — `{id, event_type, actor, payload, ts}` — and needs nothing
done to it: the next apply files it. When `status` says `held: ledger fault:
<why>` instead (`ledger_error` in `status --json`), the record is held for the
other reason and waiting will not clear it — that is the ledger itself failing,
and the `why` names the exception the emitter raised.

A fault is named on every surface: `status`, `status --json`, the briefing line
(which spends its one line on it above everything but a refusal, because it is
the sentence nobody goes back to look for) and the home card, which shows it as
a sub-line beside whatever its headline says. The card renders at all only when
it has a headline, so a fault with an idle phase, nothing waiting and no
refusal on record now BECOMES the headline — *Update records are not reaching
the ledger* — rather than reaching no web surface at all.

`events.ingested-<ts>-<pid>-<n>.jsonl` beside it is what has already been
filed, kept so the bootstrap hop is readable afterwards; `events.draining-*` is
a batch a replay is working on or could not finish, which the next ingest
drains; and `events.ingested` (no suffix) is the list of record ids already in
the ledger — the thing that makes a second pass over the same records a no-op
rather than a duplicate. None of them is content: nothing ships them and
nothing reads them but the updater.

## First bootstrap

An install that predates this leg has no updater in it, so it cannot take the
bundle that would give it one. That first hop is a one-off act by whoever
publishes: copy the bundle's `cabinet-update.sh` and `lib/update_bundle.py`
into `<root>/.updates/run/` and run `apply` from there. Every later update is
the card.
