# Review — fix/killswitch-unknown-not-off (cp1)

Branch: `fix/killswitch-unknown-not-off` · base `0ca37a72` (PR #328, the census fix)
Reviewed: the whole diff, by the author, against the claim surface below.

## The defect

`cabinet:killswitch` is the org's emergency stop. The dashboard rendered it from a
plain boolean whose **every failure path produced `false`**:

| producer | old expression | what it meant |
|---|---|---|
| `api/world/stream/route.ts:143` | `killswitch: false` | no store contacted at all |
| `api/world/stream/route.ts:190` | `presence?.killswitch ?? false` | absent / unparseable presence |
| `api/world/engine/route.ts:207` | `let killswitch = false` (survived the catch) | store unreachable |
| `api/world/engine/route.ts:219` | `Boolean(await get(...))` | any non-empty string ⇒ ARMED |
| `layout.tsx:10`, `page.tsx:106` | `value === 'active'`, no try/catch | anything else ⇒ not engaged |

`false` draws the lever UP, the pill "Stop All", the sky calm. So **"I cannot read the
emergency stop" and "the emergency stop is verified off" were the same pixels**, and the
two routes disagreed with each other on the *same* input (an unrecognised reply was
`true`/storm in one and `false`/running in the other).

Reproduced, photographed, fixed, re-photographed:
`~/cabinet-meta/designs/killswitch-unknown-{BEFORE,AFTER,AFTER-home}-2026-07-31.png`.

## The law it broke, and the plane that already had it right

`cabinet/scripts/hooks/killswitch-read.sh` — the ONE reader, schg-locked — returns
**CLEAR / ACTIVE / INDETERMINATE** and states the contract in words: *"INDETERMINATE
MUST BEHAVE EXACTLY LIKE ACTIVE for anything that acts, and be REPORTED DISTINCTLY to
the Captain — he has to be able to tell 'stopped' from 'I cannot tell', and must never
be shown 'inactive' for either."* Every enforcement surface obeys it
(`pre-tool-use.sh`, `action_exec.py`, `channel.py`, the watchdog, the doctor, the
Telegram card), and `cabinet/companion/main.swift` already carries `Bool?` for exactly
this reason. **The dashboard was the only consumer that flattened it.**

Upstream, `world-chronicle.py:562` did `killswitch_active = verdict != "CLEAR"` — fail-closed
for behaviour but lossy for reporting, folding INDETERMINATE into the same `true` as an
armed stop. The tri-state died there, so no dashboard fix could have recovered it.

## The fix

- **`lib/world/killswitch.ts`** (new, pure, ZERO imports — the census fix's
  `glance.ts` lesson: a `node:fs` import graph reaching a `'use client'` component
  breaks the Turbopack bundle while `tsc` and vitest stay green). Holds the reading,
  the three-way `killswitchGlance`, and the words/glyphs/attr a surface may print.
  Same dialect as `lib/attention/queue.ts`: `null` not a value, an `unknownReason` in
  plain words, one decision function, and a `killswitchWord` that **cannot return "UP"**
  for an unknown.
- **`world-chronicle.py`** now writes `killswitch_verdict` verbatim beside the legacy
  bool (additive; the Swift companion's parse is untouched).
- **Both routes** produce `boolean | null` + a reason. `readingFromKey` is one closed
  enum for both, so the two routes can no longer disagree.
- **The lever takes a `KillswitchGlance`, not a boolean** — a tagged union has no `??`
  that turns unknown into clear. Its intent comes from `intentFor`, which returns
  **null** for unknown; the dialog then offers ENGAGE / RELEASE explicitly rather than
  deriving a direction from the guess. Capability preserved, guess removed.
- **The sky**: `weatherTarget` gets an unknown→fog branch ABOVE the doctor checks — a
  green doctor used to paint SUN ("the measured good day") over an unread stop. And
  `initialWeather()` now opens on fog, not on `sun` with why "no eval yet — default
  sun"; `weatherStep` adopts the first eval immediately so honesty costs no delay.
- **The write**: `toggleKillSwitch` now **reads its write back** before reporting
  success — it returned `{success:true}` from having *issued* the command, the exact
  defect `kill-switch.sh` was written against. `KillSwitchHeader` stopped flipping its
  label optimistically and reports what the action actually returned.
- **Mock mode**: `lib/redis.ts` exports `isMockRedis`; with `REDIS_URL` unset the
  killswitch readers say so instead of reading a fabricated `''` as "not engaged".
- **Deleted** `components/kill-switch.tsx` — unreferenced dead twin that encoded the
  same lie ("Inactive -- Officers operating normally"). Also deleted
  `lever.fallbackCommand`, which derived the CLI verb from a state that may not exist.

## Guards — what I added, and what I proved

18 mutations, each reverting one producer/decision to its pre-change shape, suite
re-run per mutation: **17 RED, 1 semantically equivalent** (`if (s.killswitch === true)`
→ `if (s.killswitch)` — null is falsy either way, and the load-bearing `=== null` branch
below it IS caught). No arm passes for the wrong reason.

Two new fences in `test_killswitch_fail_closed.py` extend that file's own coverage
sweep, which scanned `cabinet/scripts` + `framework` and **therefore never saw the four
dashboard readers**: one requires every dashboard read of the key to flow into
`readingFromKey`, one forbids `?? false` / `killswitch: false` on any surface. Both
proven to fire and proven not to false-alarm on prose.

**A fence of mine was itself defeated during that proof**: `git grep -E` is POSIX ERE,
where `\s` matches a literal backslash-then-s, so the pattern reported GREEN against a
deliberately re-introduced `killswitch ?? false`. Character classes now. This is the
class-11 shape (the sensor tested something other than the control) reproduced inside
the fix, and it was the mutation run — not review, not the suite — that caught it.

## Honest limits

- vitest runs `environment: 'node'` with no DOM renderer, so the React surfaces cannot
  be mounted here. Their decisions were MOVED into `lib/world/killswitch.ts` and are
  driven directly; the pixels are covered by the browser captures. What is untested in
  CI is JSX layout, not the engaged/clear/unknown decision.
- The world shell's own `EventSource` did not connect under Playwright + `next dev` in
  this environment (identical before and after; a manually-created `EventSource` on the
  same page received the frame correctly). The rendered captures therefore show the
  PRE-CONNECT unknown — which is the exact case the old code drew as "LEVER UP" — while
  the store-specific reasons are evidenced on the wire and in the route tests.
- `actions/killswitch.ts`'s read-back is weaker than `kill-switch.sh`'s: one client,
  one endpoint, no nonce sandwich, no filesystem second channel. It closes the gap that
  matters (the write is verified to have landed) and does not claim more.
- Mock mode still fabricates every OTHER reading with no disclosure. Only the safety
  switch is fixed here; the general problem is reported, not fixed.
