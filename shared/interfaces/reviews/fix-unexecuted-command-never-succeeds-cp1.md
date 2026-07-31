# Checkpoint review — fix/unexecuted-command-never-succeeds cp1

Reviewed-Scope-Digest: 52a314ec6e114d2fb16b4c23691200c69c7dd2f57963c23795436bedea5f1eef

Reviewer: fresh-context adversarial subagent (Opus 5) in its own clone, with the staged
diff applied and every claim re-measured. It did not accept a single "the suite is green"
without re-running it. Verdict on the first pass: **changes-required**. Both BLOCKING
findings are fixed below; all ten NON-BLOCKING findings are also fixed rather than
deferred, because every one of them was a claim-or-sensor defect of the class this change
exists to kill.

## What changed

`lib/docker.ts` returned `{ stdout: 'mock: command executed', stderr: '' }` for any
command it declined to run whenever the store was not live. 19 write actions turned that
into `{ success: true }`; two rendered it as data. `dockerExec` now REJECTS with
`CommandNotExecutedError`. `store-posture.ts` gains `isUnconfiguredInProduction` — the
production exclusion `demo` always had and `unconfigured` never did. `actions/killswitch.ts`
gains the posture gate its read-back could not substitute for (with no store the client is
an in-process object that echoes the write back, so the read-back passed over a fleet
never contacted). `createOfficer` gains the guard its four siblings already had. Three
read libs lose now-dead sentinel-literal checks.

## Reproductions (before the change, against the BUILT app, NODE_ENV=production, no REDIS_URL)

- `/officers/create` → "Officer Created · the officer is booting and will announce on the
  warroom shortly". `create-officer.sh` never invoked.
- `/integrations` → add-secret modal closed on success; `cabinet/.env` byte-identical.
- header pill → `unknown` → `engaged`, offering "▶ Resume". Nothing was halted.

All three rendered underneath the app's own "NO STORE CONFIGURED — nothing here is a
measurement" banner. Photographs and the full write-up are in the meta workspace at
`designs/write-lie-root-2026-07-31/`.

## BLOCKING findings — both fixed

1. **The new sweep could write into the live `cabinet/.env`.** `lib/unexecuted-command.test.ts`
   overrode `CABINET_ROOT` but not `CABINET_ENV_PATH`, which `actions/env.ts` reads at
   module scope and `start-dashboard.sh` exports — and the inverse block runs a real
   `echo >> $ENV_PATH`. Reviewer proved it: `CABINET_ENV_PATH=victim.env npx vitest run`
   appended `SWEEP_INVERSE_KEY` and `EXISTING_KEY=second-copy` to that file. On a
   configured box that file holds the Anthropic key, every Telegram bot token, the GitHub
   PAT. Fixed by owning the variable in `saved`, setting it inside `sandboxPaths()`, and
   asserting the path is inside the temp tree before anything writes. Re-verified both
   ways: with the guard, 15/15 pass and the victim file is byte-identical; with the guard
   removed, 2 arms go red and the victim file gains both keys.
2. **Two docstrings still asserted the sentinel exists.** `docker.ts:23` ("its sentinel
   makes every caller take its empty branch") and `:187` ("whose sentinel yields an empty
   roster") — verbatim the false-claim class this very patch's header cites, left live in
   the same file. Both rewritten to say the call rejects and the caller's existing catch
   yields the empty value.

## NON-BLOCKING findings — all fixed

1. `killswitch.test.ts` comment claimed an unmocked named export imports as `undefined`.
   Vitest 4 throws. Restated with the measured behaviour.
2. The new `availability.test.ts` arm cannot fail against pre-change code (dockerExec is
   mocked there and the catch already returned `err.message`). Kept, and **labelled** as
   not a sensor for this change — an arm that cannot fail must not be counted as coverage.
3. `docker.test.ts`'s `/nothing was run/` matched BOTH refusal sentences. Added an arm
   that pins demo-vs-misconfiguration.
4. `no-store-honesty.test.ts` had a vacuous assertion after `toEqual([])`. Replaced with
   one that can fire (the REASON must not carry the dead string).
5. The `exit 7` inverse arm passed whether the command ran and failed or was refused.
   Now asserts the message shape, both directions.
6. The "strictly worse than refusing" justification was false of the app: six other
   modules shell out with no posture gate at all (`lib/crontab.ts`, `lib/attention/verdict.ts`,
   `lib/evidence/read.ts`, `lib/library.ts`, `lib/onboarding/bridge.ts`, the `/posture`
   page). Claim narrowed to this transport and the other six named as still open.
7. "the catch that all 19 already had" mis-stated the shape (`ok: false` in gaps.ts, a
   bare `{ error }` in createOfficer). Corrected.
8. "even an action that forgets this guard cannot report success" holds only for actions
   that shell out. Narrowed.
9. `capability-gaps.ts` docstring still said "mock output". Corrected.
10. `demo-dashboard.sh`'s header did not mention that the demo kit's buttons now refuse.
    Documented — docs track code in the same commit.

## Fences, each proven red against the defect it names

Mutation battery re-run after every fix; baseline green between each.

| Mutation | Red arms |
|---|---|
| the sentinel return restored | 18 |
| killswitch loses its posture gate | 3 |
| `createOfficer` loses its guard | 1 |
| the production exclusion goes inert | 5 |
| `NOT_LIVE` narrowed to demo only (the exact P0 asymmetry) | 9 |
| the sentinel constant re-exported | 1 |

The reviewer independently ran fourteen more, including both directions of
`isUnconfiguredInProduction`, `REDIS_URL !== undefined` (the empty-string end), hoisting
the `createOfficer` gate above validation, always-refuse mutations that catch a
fix which simply breaks everything, and re-inserting the sentinel string into the refusal
message. Every fence went red on its own defect and the inverse arms stayed green.

Inverse arms (required — a change that made everything fail would satisfy every refusal
arm): a live posture runs the command and returns its real stdout; a genuinely failing
command still fails and says so as a RUN command; `addEnvVar` writes the key and reports
success, proven by reading the file; `addEnvVar` still refuses a duplicate.

## Independent verification on this tree

`tsc --noEmit` clean · dashboard vitest **3201 passed, 1 skipped** · golden evals **32/32**
· layer separation OK, no new violations · the three dashboard python suites green · the
built app crawled with no store: 200 on every page, zero 500s (`/tasks` 500s identically
before and after this change — `NEON_CONNECTION_STRING` unset, unrelated).

## Not closed, named rather than folded in

`api/cabinets/[id]/archive` (audit row asserts `peers_yml_atomic: true` for two
`console.info` stubs) · `provisioning/worker.transitionState` (`rowCount` never read) ·
the `sed -i` class · the six ungated shell transports above. Each needs its own
reproduction; fixing them blind would convert silent holes into green ones.
