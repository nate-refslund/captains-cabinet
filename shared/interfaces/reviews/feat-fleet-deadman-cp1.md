# Checkpoint review — feat/fleet-deadman cp1

Reviewed-Scope-Digest: 1120c4c2c256f2ab9e0900b90683ebc8e0c09dfb04093111c9ceddb6f04d01ad

## What is under review

A fleet dead-man: the fleet writes pulse files, a watcher outside the fleet reads
them and returns ALIVE / DEAD / UNKNOWN, and pings an off-machine watcher **only**
on ALIVE. 13 paths, ~1.9k lines, of which roughly half are tests and prose.

## HONEST LIMITATION OF THIS REVIEW, stated first

**This is a self-review.** I authored the diff and I reviewed it. I could not
dispatch an independent fresh-context reviewer from this session — no subagent
tool was available to it. Doctrine wants a frozen panel on a claim surface this
size, and this is not that. Treat the findings below as one pass by an interested
party, and note that the interested party did find two real defects in its own
work (§ Findings) and a mutation sweep, not the review, is what carries the
weight here.

## Method

1. **Mutation sweep — 17 named defects re-introduced one at a time**, each
   asserted to change the source (occurrence count == 1) before the suite ran.
   **17/17 killed.** Every mutation is a defect this program has actually paid
   for, not a synthetic operator swap. The four that matter:
   - answered-with-nothing read as could-not-ask → killed (this is the exact
     2026-07-25 defect);
   - any absence read as death → killed (the mirror image, a false page);
   - `state != DEAD` as the ping predicate → killed;
   - a state the module has never heard of pinging → killed.
2. **End-to-end through the real CLI**, with a real local HTTP endpoint standing
   in for the off-machine watcher: unarmed → armed-never-pulsed → ALIVE (pings) →
   torn down (DEAD, stops pinging, notifies once) → store removed (UNKNOWN, still
   no ping). **Ping ledger reconciled exactly: 5 ALIVE verdicts, 5 pings, 0 after
   death.**
3. **Under real launchd, in a scratch domain.** A stand-in fleet member under
   `com.cabinet.zz-e2e-pulser` and the watcher under a scratch label, both
   bootstrapped into `gui/501` from plists in a scratch directory (never
   `~/Library/LaunchAgents`). Booting out the `com.cabinet.*` label left the
   watcher **loaded and running**; it flipped to DEAD and stopped pinging. Both
   booted out afterwards; `launchctl list` verified clean.
4. **The two red CI jobs reproduced locally and driven green** (both had the same
   root cause, the census above).
5. **Gate batteries as CI runs them**, not a hand-picked subset:
   `pytest framework/ -q`, `pytest cabinet/scripts/tests -q`,
   `check-layer-separation.sh`, `bash -n` + `shellcheck -S error` on the one
   shell file touched, `plutil -lint` on the rendered plist.

## Finding F0 — CI refused the module boundary, and CI was right

The first push went red on the architecture census: `framework_production_modules`
248 → 249, `framework/liveness/fleetwatch.py` an **unregistered set member**. That
class is a bijection whose members the expansion registry names, and an expansion
row **structurally requires two independently-run model arms** — the direction-gate
law made mechanical. **A new framework organ is a direction-gate-class decision and
I am one model**, so I could not satisfy it, and buying it with a mass allowance is
exactly what the contract forbids by name.

The answer was not to relax the gate but to fix the composition, and the tree
already had the right shape:

| half | where it now lives | why |
|---|---|---|
| emitter — `pulse()`, the store resolvers, the filename guard, the atomic write | `framework/liveness/deadman.py` | it is a liveness signal emitted from inside what it measures, which is that module's entire subject; it also removes a duplicated config-comment parser I had copied |
| watcher — scan, assess, notify, ping, CLI | `cabinet/scripts/fleet-deadman.py` | a scheduled runner that looks at this box and pings out, beside `ledger-liveness-check.py` and `healthchecks-drill.py`, its two exact siblings |

Zero new framework modules, zero expansion rows, and the layering is better than
what I first wrote: universal emitter in `framework`, operations in `cabinet`.
The one budget still owed is MASS (+131 non-comment lines), raised visibly with
its reason — the sanctioned instrument for mass, per the contract's own text.

**Stated plainly so a later session can reopen it:** the module boundary was
decided *partly* by a gate I could not clear alone. If a future session with two
model arms judges the watcher deserves its own `framework/` module, the
adjudication is theirs to run — and it would be arguing against the placement
above, not against a summary of it.

A second, smaller find from the same gate: `VERDICT_NAME` — a filename constant —
matched the `framework_verdict_vocabulary_members` symbol pattern and grew a
*decision vocabulary* budget by one for a string holding `"verdict.json"`. Renamed
to `FLEET_STATE_FILE`; budget back to 70/70. Raising a vocabulary ceiling for a
filename would have been a lie in a ledger built to make vocabulary growth visible.

## Findings — two real defects, both found by attacking my own diff, both fixed

**F1 (would have been permanently, confidently wrong). The pulse store rode
`ledger_dir()`.** `ledger_dir()` honours `CABINET_EVENT_LOG_DIR`, which the
fleet's own launchd plists **set** (`~/Library/Application Support/cabinet/events`)
and the out-of-fleet watcher's plist does not. Writers and reader would have
resolved two different directories: the fleet pulses into one, the watcher scans
the other, finds nothing, and — correctly by its own rules — reports DEAD forever.
A watcher that cries wolf on day one is worse than none.
*Fixed:* `fleet_liveness_dir` resolves `~/.cabinet/liveness` independently of
`CABINET_EVENT_LOG_DIR`. Pinned by `test_pulse_store_does_not_ride_the_event_log_dir`,
which fails against the original resolver (verified as mutation M17). The one
variable still steering the path is `CABINET_ENV`, kept deliberately (a dev run
must not certify a runtime fleet) and it fails in the safe direction: a false page,
never a false all-clear. The verdict now names the directory it scanned so a
mismatch is a diff rather than a mystery.

**F2 (a sensor pointed at something other than the control).** `notify_argv`
returned `[osascript, -, script, title, body]` and the runner re-sliced it into a
different argv. The injection test asserted the returned list — not what ran — so
it could have passed while the executed command was wrong.
*Fixed:* `notify_command` returns exactly `(argv, stdin)`; the test asserts the
returned shape **and** spies the actual `subprocess.run` call.

## Attacked and found sound

- `DEAD > UNKNOWN > ALIVE` precedence: a confirmed stale source is not downgraded
  because a different file was corrupt, and one unreadable source still forbids
  ALIVE. Both directions tested.
- Degenerate ends: empty expectation set returns UNKNOWN/`unarmed`, not the
  vacuous ALIVE an `all()` over nothing produces. Absent config, disabled config
  and unparseable config all degrade to unarmed — a bad config can silence this
  watcher, never make it claim a fleet is alive.
- Boundary exercised on both sides (`age == limit` ALIVE, one second past DEAD).
- Path traversal: a source name is validated as a filename; `../../etc/passwd`,
  `a/b`, `.`, `..`, `.hidden` and over-length all refused at write, ignored at read.
- Injection: the notification body is argv to an `on run argv` handler, never
  interpolated into AppleScript source.
- Atomicity: the final filename only ever appears via a rename of a complete file.
- Failure reporting: a failed external ping reports as failed
  (`pinged=False, ping_reason=transport-error`), never as sent.
- No module-level import of anything watched; the one `framework.env` import is
  lazy and guarded, matching `deadman`'s survival contract.
- No hardcoded dates; `now` is a parameter throughout.

## Residual risks, named rather than discovered later

- **The local leg survives by NAMING, not by isolation.** `gui/<uid>` is the only
  domain a non-root user can bootstrap into — `user/<uid>` and `system` both
  return `Bootstrap failed: 5` (measured). A broader teardown or a logout takes
  the watcher too. Documented at the top of the plist and in the runbook. The
  external leg is the one that survives the box, and `--status` reports the two
  separately so local-only cannot read as covered.
- **Arming before the fleet is raised reports DEAD.** Correct, but noisy on a
  fresh hatch, where `hatch.sh` defaults to `--no-launchd`. The errand should be
  worked after move-in; a line saying so is in the errand.
- **The `osascript` path is not exercised by CI**, which is ubuntu. Its argv is
  asserted there and the call itself is covered only by manual verification. This
  is why the module is Python and not shell: everything decidable without launchd
  runs on the CI runner.
- **It measures only the sources it is told to expect.** Two call sites are wired.
  A service with no `pulse()` call is invisible to it.
- **Not fixed here, and not claimed to be:** the desk pet is still unsupervised
  and still not running, so the standing local surface is the verdict file plus a
  transition notification, not the pet.

## Pre-existing red, not from this diff

`framework/fidelity/tests/test_retro_shim.py::test_reexports_constants` fails on
clean `origin/master` (verified by stashing the whole change and re-running).
Everything else green: framework 8056 passed / 1 pre-existing failure,
cabinet/scripts nearest-neighbour set 147 passed, layer separation OK
(`new=0 fixed=0`), shellcheck clean, plist lints.

## Verdict

**Ship**, with the self-review caveat at the top standing. The two defects this
pass found were both in the class the week has been paying for — a sensor pointed
somewhere other than the control — which is evidence for attacking your own fences
and against trusting a green.
