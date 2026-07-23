# COG-4 · W1 · u3 — officer-plist instance-leakage cleanup — PARKED (dated marker)

- **Status:** PARKED (deliberate) — 2026-07-23. No code change landed; NO officer plist was
  deleted, moved, or regenerated. This unit produces ONLY this dated marker (the recorded-debt
  idiom, contract §9.1 "if its deploy-script blast radius proves non-trivial it PARKS with a
  dated marker rather than riding the exit gate"; LESSONS L1108 dated-marker idiom).
- **Unit:** the officer-plist leakage cleanup unit named in `cognitive-core-phase-4-contract-2026-07-23.md`
  §9.1 and §14.2 (W1). It is EXPLICITLY parkable per the contract; parking is in-contract, not a miss.
- **Ground pin:** all `:line` cites below were byte-verified this session at tree tip `de5d16c4`
  (== origin/master at marker time), per the LESSONS L1113 tip-assert discipline.
- **Provenance:** per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20 cognitive-masterplan grant.
- **Marker revision:** rev-1 (fix pass) — the builder's draft marker MISSED a live-runtime dependency
  and its "coherent path forward" step (i) as drafted would BRICK the Captain's receive path. This
  revision adds §4 (the missed dependency), corrects the path forward (§6), cites the prior art (§7),
  and records the root cause of the miss (§8). Candor: the original draft was wrong on step (i); the
  correction is below.

---

## 1. What the unit was to do (contract §9.1)

Remove the instance leakage of committed **concrete-slug officer plists** from the framework tree —
byte-verified present at tip:

- `cabinet/launchd/com.cabinet.officer.cos.plist`
- `cabinet/launchd/com.cabinet.officer.cos-inbound.plist`
- `cabinet/launchd/com.cabinet.officer.comms-officer.plist`  (comms-officer is not even in the
  5-officer seed roster — instance leakage against the 2026-07-14 roster-derivation doctrine)

(`cabinet/launchd/com.cabinet.officer.template.plist` is the legitimate TEMPLATE and STAYS.)

Contract §9.1 direction: "move to instance/deploy surface or delete; verify `deploy-mac.sh` renders
from the template + roster." The `test_cog4_fleet_truth.py` conservation guard (a SEPARATE W1 unit,
NOT this one) already pins the out-of-manifest set so nothing silently grows while this cleanup waits.

## 2. Why it parked

The deploy-script blast radius is non-trivial, and — decisively — one of the three plists
(`com.cabinet.officer.cos-inbound.plist`) is a **live-runtime dependency of the Captain's receive
path**, not dead instance clutter. Deleting or relocating it without FIRST re-pointing a suppression
check in `start-officer-mac.sh` bricks the Captain's ability to receive Telegram DMs (see §4). That is
an existential/irreversible-class live effect (Captain authority/receive path), so the unit parks
rather than ride the exit gate. A recorded handback/marker beats a workaround.

## 3. The full deploy/runtime coupling (byte-verified)

- `cabinet/scripts/generate-plists.py:426` — canonical render output dir = `cabinet/launchd/generated/`
  (a DIFFERENT path from `cabinet/launchd/`). `.gitignore:218` = `cabinet/launchd/generated/` — the
  generated dir is machine-specific and untracked.
- `generate-plists.py:459` — officers are SKIPPED by the generator: "officers (deploy-mac.sh template
  path owns these): ...". The generator renders NO inbound-poller plist at all — the cos-inbound plist
  is a hand-made, comment-rich artifact, not a template render.
- `cabinet/scripts/deploy-mac.sh:4-5,42-45` — renders roster officers from
  `com.cabinet.officer.template.plist` + `instance/config/roster.yml` into `~/Library/LaunchAgents/`
  (NOT into `cabinet/launchd/`); `GENERATED_DIR="$TEMPLATES_DIR/generated"`.

## 4. THE LIVE-RUNTIME DEPENDENCY THE DRAFT MARKER MISSED (the amendment core)

`cabinet/scripts/start-officer-mac.sh:357` (byte-verified this session):

```
    elif [ -f "$REPO_ROOT/cabinet/launchd/com.cabinet.officer.$OFFICER-inbound.plist" ]; then
      TELEGRAM_FLAG=""
      echo "start-officer-mac.sh: $OFFICER receive via inbound watchdog — not loading --channels ..." >&2
```

The **existence of the REPO-TRACKED** `cabinet/launchd/com.cabinet.officer.<officer>-inbound.plist`
file is what SUPPRESSES `--channels` on that officer's session. The guarding comment at
`start-officer-mac.sh:349-353` states the invariant plainly: "if an inbound-watchdog LaunchAgent
exists for this officer, that poller OWNS getUpdates — do NOT also load `--channels`, or two pollers
on one bot token fight (Telegram 409 Conflict → nothing consumes; observed 2026-06-23)."

The cos-inbound plist's OWN header line 8 is the visible pointer that the draft sweep walked past:

```
     token; start-officer-mac.sh drops --channels when this plist exists).
```

**Consequence of the draft path forward as written** — the draft's COHERENT-PATH-FORWARD step (i)
("delete the checked-in file and install the generated copy") is unsafe on two independent grounds:

1. **Path mismatch.** The `elif` at `:357` tests `$REPO_ROOT/cabinet/launchd/...`. The generated copy
   renders to `cabinet/launchd/generated/...` (§3) — a different path the check never reads. So even
   if a generated copy existed, deleting the checked-in file makes the `:357` test FALSE.
2. **No generated inbound exists.** `generate-plists.py` skips officers and renders no inbound plist
   (§3), so "install the generated copy" produces nothing at the path `:357` reads.

Either way, on the next cos (re)start the `elif` at `:357` is FALSE → control falls to the `else`
branch → `TELEGRAM_FLAG="--channels ..."` loads. The installed inbound LaunchAgent
(`~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist`) is STILL running and STILL owns
`getUpdates`. Two pollers now hit `getUpdates` on the one Chair bot token → **Telegram 409 Conflict →
the Captain's receive path is bricked** — the exact worst case this park exists to avoid.

## 5. Why the check and the install path disagree (the trap)

deploy-mac.sh installs the poller to `~/Library/LaunchAgents/` (the running LaunchAgent), but the
`:357` suppression test reads the REPO-TRACKED `cabinet/launchd/` source copy. The two are different
locations. A cleanup that only reasons about "is this file dead in the repo?" cannot see that the
repo copy is load-bearing as a RUNTIME SIGNAL for `--channels` suppression, independent of the
installed LaunchAgent that actually polls.

## 6. Corrected COHERENT PATH FORWARD (for the future integrated pass)

Ordering is load-bearing. The re-point is a PRECONDITION, not an afterthought.

- **(0) PRECONDITION — re-point the suppression check first.** In `start-officer-mac.sh:357`, change
  the inbound-existence test from the repo-tracked `$REPO_ROOT/cabinet/launchd/com.cabinet.officer.$OFFICER-inbound.plist`
  to the INSTALLED LaunchAgent `"$HOME/Library/LaunchAgents/com.cabinet.officer.$OFFICER-inbound.plist"`
  (the true poller-ownership signal). Land + verify this FIRST, with the cos session observed to still
  drop `--channels` while the LaunchAgent is installed. Only after this does the repo-tracked copy stop
  being a runtime signal. (This is the `~/Library/LaunchAgents` re-point the 2026-07-07 SKIP note
  prescribed — §7.)
- **(i, corrected) Then remove the leakage.** Delete/relocate the concrete-slug officer plists
  (`cos`, `cos-inbound`, `comms-officer`) to the instance/deploy surface. Do NOT rely on
  `generate-plists.py` to reproduce the inbound plist — it does not (§3). If the cos-inbound artifact
  is to remain repo-provided, keep it under the instance/deploy surface with its install path
  (`cp ... ~/Library/LaunchAgents/`) intact.
- **(ii) Verify the render path.** Confirm `deploy-mac.sh` renders the officers from
  `com.cabinet.officer.template.plist` + `instance/config/roster.yml` and that a fresh deploy still
  installs the cos-inbound poller to `~/Library/LaunchAgents/`, so the re-pointed `:357` check stays
  satisfied and the cos session stays `--channels`-dark.
- **(iii) comms-officer.** It is not in the 5-officer seed roster — remove it or move it to the
  instance surface per the 2026-07-14 roster-derivation doctrine.
- **(iv) Re-attempt gating.** Also confirm the two other 2026-07-07 re-attempt needs (§7) are clear:
  `generate-plists.py` covering the verdict-supply group, and the AUD-1 fleet rollout complete
  (concrete officer plists no longer being live-edited for CLAUDE_CONFIG_DIR env keys).

Net: the checked-in copy may be deleted ONLY after the runtime signal it feeds has been re-pointed.
Order (0) → (i). Reversing that order is the brick.

## 7. Prior art the future pass MUST cite

`docs/plans/operative-egg-ledger-2026-07-07.yml:568` — row R067's 2026-07-07 row-sweep SKIP note
documents this SAME dependency and prescribes the SAME remedy: "start-officer-mac.sh:261
behavior-branches on repo-tracked `com.cabinet.officer.<role>-inbound.plist` existing — deleting
cos-inbound.plist flips live cos to `--channels` = double-poller Telegram 409 ... Re-attempt needs:
inbound-check re-pointed to `~/Library/LaunchAgents`, generate-plists.py covering the verdict-supply
group, and AUD-1 rollout complete."

Line drift, reconciled: R067 cites the branch at `start-officer-mac.sh:261`; at tip `de5d16c4` the
same `elif` is at `:357` (the file grew between 2026-07-07 and now). Same code, same trap, moved line.

## 8. Root cause of the miss + the sweep-method fix

The draft marker's reference sweep was a **literal-basename grep** — it searched for the fixed
strings `com.cabinet.officer.cos-inbound.plist` / `com.cabinet.officer.comms-officer.plist`. That
sweep STRUCTURALLY cannot see the reference at `:357`, because the filename there is
variable-interpolated: `com.cabinet.officer.$OFFICER-inbound.plist`. The dependency was
nonetheless visible two other ways the sweep should have caught: (a) the cos-inbound plist's own
header line 8 ("start-officer-mac.sh drops --channels when this plist exists"), and (b) the R067
prior-art note (§7).

**Fix for future officer-plist / launchd sweeps:** grep for the VARIABLE-interpolated pattern
(`\$OFFICER-inbound`, `-inbound\.plist`, `officer\.\$`), not just literal basenames; AND read the
target file's own header comments for a "this plist is load-bearing / consumed by X" pointer before
declaring it deletable; AND grep the operative ledger for a prior SKIP note on the same path.

## 9. Durable-record text for the integrator (COG-4 ledger row note / phase record)

The integrator lands this park in the COG-4 durable record. Fold in verbatim (this closes the
"durable record the integrator lands" half of the fix — it is furnished here rather than raced into
the in-flight COG-4 ledger row, which the integrator owns at landing):

> W1/u3 officer-plist instance-leakage cleanup PARKED 2026-07-23 (deploy blast-radius non-trivial +
> live receive-path dependency; recorded debt, contract §9.1). BLOCKER: `start-officer-mac.sh:357`
> suppresses `--channels` on an officer session iff the REPO-TRACKED
> `cabinet/launchd/com.cabinet.officer.<officer>-inbound.plist` exists; deleting the checked-in
> cos-inbound plist flips the next cos restart to `--channels` → double `getUpdates` poller on the
> Chair bot token → Telegram 409 → Captain receive bricked. Re-attempt PRECONDITION: re-point the
> `:357` inbound-check to `~/Library/LaunchAgents/` (the installed poller) BEFORE deleting the
> repo-tracked copy; then relocate `cos`/`cos-inbound`/`comms-officer` to the instance/deploy surface
> and verify `deploy-mac.sh` renders officers from template + roster. Prior art:
> `operative-egg-ledger-2026-07-07.yml:568` (R067, same dependency, cited `:261` pre-drift). Marker:
> `docs/plans/cog4-w1-u3-officer-plist-cleanup-PARKED-2026-07-23.md`.

## 10. Fix-verification of THIS marker

- No live-runtime / germline / launchd file touched — this unit's entire diff is the addition of this
  marker doc (`git diff --stat` shows exactly one added file).
- Every `:line` cite byte-verified at tip `de5d16c4`: `start-officer-mac.sh:357`,
  cos-inbound plist header line 8, `generate-plists.py:426`/`:459`, `deploy-mac.sh:4-5,42-45`,
  `.gitignore:218`, `operative-egg-ledger-2026-07-07.yml:568`.
- The corrected path forward orders the `~/Library/LaunchAgents` re-point BEFORE the delete (§6),
  closing the 409-brick hole the draft step (i) opened.
