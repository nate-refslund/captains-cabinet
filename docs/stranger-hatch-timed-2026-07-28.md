# The stranger hatch, TIMED — and the first briefing scored

Date: 2026-07-28 · Measured against `49ed144e` (origin/master at the time of
the run) · Machine: Apple Silicon Mac, already carrying every dependency
`setup-mac.sh` would install.

The direction gate ruled that the stranger-hatch bar had to be decoupled from
the World-art dependency and **actually timed**. It never had been. This is
that measurement: numbers, not impressions. Everything below was produced by
running the real chain end to end — export, hatch, first briefing — and reading
the artifacts it wrote.

---

## 0. The verdict in three lines

| | |
|---|---|
| Master `49ed144e`, unmodified | **The stranger hatch does not complete.** Red at step `proof-a` after 21s. No briefing is ever rendered. |
| With the two fixes on this branch | **Green.** Export → first briefing in **2m 22s** wall clock, on a Mac that already has the dependencies. |
| The first briefing, scored on the shipped 0–3 scale | **1 — "read it, no value."** Defended in §3. |

The red was invisible to every gate in the repo because CI only ever runs
against the origin checkout's own `instance/`, and the origin's `instance/` is
not the one a stranger boots. Details in §5.

---

## 1. The timing table

Command actually run (from the export directory, which is not a git tree):

```
bash cabinet/scripts/egg-export.sh --out <scratch>/egg
cd <scratch>/egg
bash cabinet/scripts/hatch.sh --defaults --clean-room --altitude contributor \
     --flight-log <scratch>/flight/flight.log
```

Wall clock measured around each stage; per-step seconds are the hatch's own
flight recorder (`cabinet/scripts/hatch-lib/flight-recorder.sh`).

| # | Stage | Step id | Seconds | Human needed? |
|---|---|---|---|---|
| — | **Export the egg from HEAD** | `egg-export.sh` | **1.8** | no |
| 1 | Seed `cabinet/.env` non-interactively | `setup-env` | 0 | no |
| 2 | Host preflight (clean-room: check only) | `setup-mac` | 0 | **see §1a** |
| 3 | Generate the instance | `gen` | 0 | no |
| 4 | Select the active preset | `preset` | 0 | no |
| 5 | Seed the durable roster | `roles` | 0 | no |
| 6 | Assemble the runtime | `load-preset` | 0 | no |
| 7 | Roster authorization | `roster-authz` | 0 | no |
| 8 | **P-a null-hatch gate** | `proof-a` | **100** | no |
| 9 | P-b clean-room ratchets | `proof-b` | 5 | no |
| 10 | P-c dry render: officer boot | `proof-c1` | 0 | no |
| 11 | P-c dry render: plist plan | `proof-c2` | 0 | no |
| 12 | P-d kill-switch drill | `proof-d` | skipped | — |
| 13 | **FIRST RECEIPT — the genesis briefing** | `first-receipt` | **34** | **yes — Claude Code must be installed and authenticated** |
| 14 | Demo receipt | `demo-receipt` | 0 | no |
| | **TTFR** (proofs-done → first receipt) | | **34s** | |
| | **Hatch total** | | **140s** | |
| | **Export + hatch total** | | **142s (2m 22s)** | |

Two steps are 96% of the clock: the null-hatch proof gate (100s — it stages a
sandbox copy of the tree and runs the full framework suite inside it) and the
first receipt (34s — a `claude` CLI call for the genesis research brief).
Everything else rounds to zero.

### 1a. What this number does NOT include, stated plainly

**The host bootstrap was not timed, because it could not be.** `--clean-room`
runs `setup-mac.sh --check` (verify deps present, install nothing); a real
stranger runs `setup-mac.sh --fast`, which will `brew install` any of tmux, jq,
python@3.12, redis, node, bun, gettext and gh that are missing. On a bare Mac
that is minutes to tens of minutes of network and compile time, entirely
outside this measurement. **The honest headline is therefore: 2m 22s from an
already-provisioned Mac, and UNMEASURED from a bare one.**

Three further gaps between what was run and what a stranger runs:

* The documented Quickstart is `git clone … && bash cabinet/scripts/hatch.sh
  --defaults` — **without** `--clean-room`. That path installs packages, writes
  the live `/tmp/cabinet-runtime`, and rewrites the checkout's tracked
  `instance/config/platform.yml` in place. It was not run here (this machine
  hosts a live deployment). The chain is identical apart from step 2 and the
  runtime-dir routing.
* `--clean-room` **refuses a plain `git clone`** (tracked `platform.yml` over 50
  lines) unless `HATCH_ALLOW_TRACKED_INSTANCE=1`. So the verifiable path and the
  documented path are not the same path. Anyone re-running this measurement must
  hatch from an EXPORT, as here.
* The 34s first receipt assumes a working, authenticated `claude` CLI. Without
  one, genesis takes the honest-IOU branch and the briefing loses its research
  brief entirely — a quality cliff, not a timing one.

---

## 2. The human errands — ten of them, six named

Every point where the stranger must stop and go do something is a place they
can drop out. The hatch prints six errand notes. It does not print four more
that the path actually requires.

### Printed by the hatch (`cabinet/scripts/hatch-lib/errands.sh`)

| # | Errand | Where it happens | Blocking? |
|---|---|---|---|
| 1 | Germline scope lines for a lane CEO | your editor, two files | no — explicitly marked not blocking, and the roster hires only what those files already authorize |
| 2 | **Chair bot token from @BotFather** | a Telegram conversation | no, but the Chair boots dark without it — i.e. the org has no way to reach you |
| 3 | TCC grants | System Settings clicks | no — only for calendar/computer-use |
| 4 | **Move-in (raise the fleet)** | 6 commands in the terminal | yes, if you want a live org — the hatch stops short of launchd by default |
| 5 | Healthchecks.io dead-man registration | an external account | no |
| 6 | Germline lock | `sudo` in the terminal | no |

### NOT printed anywhere, but required

| # | Errand | Where | Why it is a drop-off risk |
|---|---|---|---|
| 7 | **Install + authenticate Claude Code (Max plan)** | claude.com, then a login | The README lists it as a prerequisite; nothing in the hatch checks it, and its absence silently degrades the first receipt to an IOU. |
| 8 | **Install Homebrew, then let `setup-mac --fast` install 8 packages** | the terminal, network-bound | The single longest stage on a bare Mac, and it is invisible in every timing claim including this one. |
| 9 | **Fix three placeholders in the generated answers file** | `instance/config/cabinet-init.answers.yml` | `--defaults` writes `timezone: UTC`, `telegram_chat_id: "0000"` and a lane literally named `First Lane`, each flagged `# placeholder`. Nothing prompts for them afterwards; the first briefing is built on them. |
| 10 | **Start the dashboard to reach the First Window** | `bash cabinet/scripts/start-dashboard.sh`, then a browser | The one surface that reads the operator's OWN estate is not on the hatch path at all (§5). The hatch prints a dashboard URL but not the reason to go there. |

**Count: 10 errands, of which 4 are unnamed.** The unnamed four are the ones
that decide whether the first briefing is worth reading.

---

## 3. The first briefing, rendered and scored

The real artifact: `instance/memory/first-briefing-2026-07-28.md`, produced by
the run in §1. It contains three proposed outcome cards, two FYI lines, and one
contribute/fund ask. Verbatim excerpt of the load-bearing content:

> **Proposed outcome: First verifiable improvement shipped in the First Lane lane**
> WHAT: One reviewed, Captain-approved improvement in First Lane traced end-to-end…
> WHY: You staked First Lane as a lane at genesis.

> Recall: live — OrgSource answered 0 hit(s) across 0 of 1 subject(s) (First Lane).
> — recall is bound and reachable but held NOTHING on the subjects you declared.

### Score: **1** — "read it, no value"

Scale of record (`cabinet/scripts/lib/briefing_score.py`): 0 wouldn't read it ·
1 read it, no value · 2 told me something I didn't know · **3 changed what I did
next**.

**Why not 2.** Nothing in it is about the operator's world. Every sentence is
either the cabinet describing its own mechanics (propose-only, where the draft
row lives, how to ratify) or an echo of the zero information the operator
supplied. The one operator-specific token in all three cards is the string
`First Lane` — a placeholder the generator invented. A briefing cannot tell you
something you didn't know when its entire input is a file it wrote itself thirty
seconds earlier.

**Why not 0.** It is genuinely well made and genuinely honest. It says out loud
that recall returned nothing and that this is an empty answer rather than a
stale one; the genesis research brief refuses to invent a market for a lane it
knows is a placeholder ("that is a slot label, not a product… any specific
answer I gave would be fabrication dressed as analysis"). That honesty is worth
something. It is not worth a 2 on this scale, because the scale asks about the
reader's world, not about the writer's character.

**Why not 3.** Rung 3 is "changed what I did next". It does prompt an action —
ratify a card, rename the lane — but that is the cabinet asking to be
configured. If configuring the tool counted as the tool changing what you did,
every installer on earth would score 3.

**An honest 1 is the finding.** The instrument works: it separates "the cabinet
produced a well-formed artifact" from "the cabinet was useful", and on the
documented Quickstart path those two answers differ.

**What would move it.** The score is capped by the input, not by the renderer.
`--defaults` is a zero-question lane: the operator is never asked anything, so
the briefing has nothing of theirs to work with. The two things that would
plausibly move this to a 2 or 3 are both off the measured path: (a) the
interview lane instead of `--defaults`, and (b) the First Window sweep of a
folder the operator points at — the only mechanism in the product that reads the
operator's own material. See §5.

---

## 4. Altitude: an operator with no company, and possibly no repo

Run at the altitude the Captain named — `--altitude contributor`, no company, no
repo, no tracker.

**The path does not demand a lane, a repo or a company.** `--defaults` writes a
consent-safe answers set with zero questions asked, invents one placeholder
lane, records `lanes[0].repos: []` and `task_system: none`, and completes green.
The preset resolved to `personal`. Nothing in the chain refuses to proceed.

**That is the right refusal posture and the wrong outcome.** Because nothing is
demanded, nothing is known, and the briefing in §3 is what "nothing is known"
produces. The failure is not that the hatch asks for too much — it is that it
asks for nothing and then produces a briefing shaped as though it had asked.
Every card is phrased in the second person about commitments the operator never
made ("You staked First Lane as a lane at genesis" — they did not; the generator
did).

---

## 5. The known coverage lie, checked

Claim under test: the sweep caps at 200 files / 2 MB and walked alphabetically,
so repo and tracker got zero coverage on a realistic slice; a truncation
disclaimer landed this week; does it fire on the stranger path, and does it name
what it did not look at?

**Finding A — the relevance-ordering fix is real and landed.**
`framework/onboarding/journey.py` now ranks eligible paths into buckets
(manifests, entry docs, prose, config, other) before spending the budget, and
records `ordering: "relevance"`. Verified by execution, not by reading.

**Finding B — the disclaimer fires, and it was a fraction, not a naming.**
Driving the real journey over a 723-file operator-scale estate (four top-level
areas: `notes/`, `repo/`, `tracker/`, `zz-archive/`):

```
coverage : eligible 723, examined 200, complete=false, ordering=relevance
opened   : repo 122, notes 78
ZERO     : tracker, zz-archive
card     : "…I read 200 of 723 supported files, most-informative first;
            the rest were left unopened by the First Window limits."
```

Every word of that card is true, and the operator still cannot tell that
`tracker/` — the one area holding an urgent row — was never opened at all. A
bucket-3 CSV export loses to four hundred bucket-2 standup notes. The count
sensor added on 2026-07-27 cannot catch this: it reads identically whether one
area or four went unread. **Fixed on this branch** — `coverage` now carries
`unopened_areas` and both rendering sites name them:

```
…the rest were left unopened by the First Window limits.
Nothing at all was opened in: tracker, zz-archive.
```

**Finding C — and none of it is on the stranger path.** The First Window sweep
is reachable only from the dashboard's `/onboarding` route and the Telegram
provisioning webhook. The v0 hatch starts neither: it defaults to `--no-launchd`
and prints "dashboard not started". The stranger's first briefing comes from a
completely different surface (`framework/onboarding/genesis.py` +
`framework/frontdoor/run_briefing.py`). **So the disclaimer cannot fire on the
hatch path, because the sweep it belongs to is not on the hatch path** — and the
one mechanism that would read the operator's own material, and is therefore the
only plausible route from a 1 to a 3, requires errand #10 that nothing tells them
to run.

---

## 6. What was fixed here, and what is reported rather than fixed

### Fixed

1. **The stranger hatch was dead on master.** `instance/config/watchdog.yml` is
   read unconditionally by a Phase-4 lens proof that runs inside `null-hatch.sh`
   — which stages the EXPORT tree, where that path is materialized from
   `instance/config/watchdog.yml.example` by the `watchdog-default` transform.
   The 2026-07-26 arm-the-cabinet ceremony armed `evidence-store-invariants` in
   the live file and not in the shipped twin, so the origin checkout stayed green
   and every hatch from the export died. Armed the twin (safe on a day-one box
   for the ruling's own stated reason: the checker returns `skipped=True` when
   the store is not observable) and added the lockstep arm that was missing —
   the existing proof was a claim about two files with only one pinned.
2. **The truncation caveat now names the areas it never opened**, at both
   rendering sites, capped at five when rendered and recorded in full.

### Reported, not fixed

| Finding | Why not fixed here |
|---|---|
| The documented Quickstart path (`git clone` + `--defaults`, no clean-room) is not the verifiable path, and `--clean-room` refuses a plain clone | A doc-and-flags decision about what the public entry point should be, not a bug with an obvious right answer |
| Four of the ten human errands are unnamed, including the two that decide briefing quality (Claude Code auth, the placeholders) | Fixing it means deciding what the hatch should ask for, which is the same product question as below |
| The first briefing scores 1 because `--defaults` asks nothing, then writes in the second person about commitments the operator never made | This is the product decision the score exists to surface. Making the briefing better means either asking the operator something or reading something of theirs — both are direction calls |
| The First Window — the only surface that reads the operator's own estate — is not reachable from the hatch at all | Wiring it in is a change to what the hatch IS, not a defect fix |
| The relevance ranking puts tracker/CSV exports below bulk prose, which is how `tracker/` starved in the first place | The disclosure now names the starvation; changing the ranking to prefer trackers is a judgment call that needs its own measurement |

---

## 7. Reproducing this

```bash
git clone https://github.com/nate-refslund/captains-cabinet.git /tmp/sh-repo
cd /tmp/sh-repo && git checkout fix/stranger-hatch-timed
bash cabinet/scripts/egg-export.sh --out /tmp/sh-egg
cd /tmp/sh-egg
bash cabinet/scripts/hatch.sh --defaults --clean-room --altitude contributor \
     --flight-log /tmp/sh-flight/flight.log
cat instance/memory/first-briefing-*.md      # score it yourself, 0-3
```

The flight log carries per-step timings and the `HATCH_START` /
`HATCH_PROOFS_DONE` / `FIRST_RECEIPT_DONE` stamps. To reproduce the red on
master, check out `49ed144e` instead and stop reading at `step-proof-a.log`.
