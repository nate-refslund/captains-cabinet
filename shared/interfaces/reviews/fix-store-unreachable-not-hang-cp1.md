# Review — `fix/store-unreachable-not-hang` cp1

A store that is CONFIGURED and UNREACHABLE must render the same honest unknown as
one that is unconfigured. Before this change it hung.

## The defect, reproduced

ioredis 5.10.1 on node 26, one `GET` on a fresh client with the options
`lib/redis.ts` passed at the time (none):

| unreachable shape | default options |
|---|---|
| blackhole — SYN dropped (`192.0.2.1`, RFC 5737) | **never settled** (>65s pending) |
| refused — host up, redis down (ECONNREFUSED) | rejected @ **10 546ms** |
| mute accept — TCP accepted, no reply ever (proxy/LB in front of a dead backend, or a redis loading an RDB) | **never settled** (>65s pending) |
| HEALTHY control (real local store) | resolved @ 11ms |

Per-command bounds alone do not bound a PAGE. The five store fetchers a costs
render issues, against a mute socket: **12 009ms** with per-command bounds and no
breaker, **3 004ms** with one.

In the BUILT app against a mute store, before: `/queue` **timed out at 45s**.

## The numbers, and why they are these numbers

A dead store is told from a slow one by CONNECTION, not by latency.

- `connectTimeout: 2000` — connect is network round trips and nothing else: one
  RTT plain, three with TLS, so ~900ms worst-case intercontinental. Measured
  against the cabinet's own store: **1ms**, five cold connects in a row. Nothing
  on the public internet takes 2s to handshake.
- `commandTimeout: 3000` — one RTT plus server work. The only command this app
  issues that can be legitimately slow is `KEYS`, O(N) over the keyspace;
  measured on the cabinet's store `KEYS *` over 61 keys = **0ms**, `PING` ×200
  p50 **0.057ms** / p99 **0.122ms**. A pathological million-key store spends a
  few hundred ms of server CPU; 300ms RTT + that leaves ~5× headroom.
- `maxRetriesPerRequest: 1` — the ioredis default of 20 is exactly where the
  10 546ms came from.
- `enableOfflineQueue: true` — kept ON deliberately. With it off the first
  command of a cold process fails while the socket is still connecting, so a
  healthy store would render "unreachable" on every cold start. That is the
  inverse defect and it is one word away at all times; it has its own arm.
- `UNREACHABLE_COOLDOWN_MS: 5000` — one failure opens the breaker, not three:
  the first failure is already a 3s wait the Captain sat through. Recovery is
  automatic (the next call after cooldown is a real attempt).
- `HARD_DEADLINE_MS: 4000` — above `commandTimeout` on purpose, so ioredis's own
  timer normally wins and the race is a backstop rather than the only control.

## The vocabulary is the existing one, not a fourth dialect

`unreachable` joins `live | demo | unconfigured` in `lib/store-posture.ts`;
`unreachableReading()` builds the reading WITH its reason (no zero-argument
constant to reach for — the `unknownKillswitch` rule); the banner is the same
dashed-amber `StorePostureBanner`; `isNotLiveStore` already covered it.

A failed call THROWS rather than answering `null`, because
`readingFromKey(value, contacted)` treats a resolved `null` under `contacted:
true` as a MEASURED "the emergency stop is clear". Returning `null` from an
unreachable store would earn that claim about a fleet nobody reached — the defect
PR #330 closed, one level down. `killswitch-state.ts` already catches and says so.

`unreachableReading().fabricated` is **false**: nothing was invented, and reusing
the demo flag would send every consumer that branches on it down the demo path.

## Coverage — a wall on one client is not a wall

There are **nine** `new Redis(...)` sites in `src/`. Bounding only the shared one
left `/queue` at 45s (its own client) and the rail, the tasks publisher and three
subscribers unbounded. Two partial local dialects already existed
(`api/world/stream`, `api/world/engine`: `{lazyConnect, maxRetriesPerRequest: 1,
connectTimeout: 900}`) and BOTH still hung on mute-accept — neither carried a
`commandTimeout`, and that shape completes its connect. All nine now take one of
three named sets, and `store-clients.fence.test.ts` fails if any site does not.

`connectTimeout` moves 900 → 2000 for those two world routes, deliberately: 900
is marginal for a legitimately remote managed store, and they gain the bound that
actually closes their hang. Net strictly stronger.

## Arms — red then green, both directions

Mutation matrix, run after every edit (`node_modules/.vite` purged each time):

| # | defect re-introduced | arm | result |
|---|---|---|---|
| M1 | `new Redis(url, LIVE_CLIENT_OPTIONS)` → `new Redis(url)` (the original) | e2e "client the app actually constructs" | RED |
| M1b | drop `commandTimeout` from the set | e2e BARE-ioredis + unit option-set | RED, RED |
| M1c | `maxRetriesPerRequest` back to 20 | unit + e2e bounds | RED, RED |
| M2 | breaker `isOpen` always false | unit call-count + e2e render shape | RED, RED |
| M3 | hard deadline passes through | unit `withDeadline` | RED |
| M3 | (same) | e2e mute | **GREEN — honest finding: ioredis's own `commandTimeout` suffices there; the race is belt-and-suspenders, and the unit arm is what proves it works** |
| M4 | guarded call returns `null` instead of throwing | e2e killswitch | RED |
| M5 | **INVERSE** — every call unreachable, always | e2e INVERSE + unit INVERSE | RED, RED |
| M6 | blank-reason regression (`\|\|` → `??`) | unit "always has a reason" | RED |
| M7 | `enableOfflineQueue: false` (breaks healthy cold start) | unit + e2e INVERSE healthy | RED, RED |
| M8 | unbind each of 5 sites in turn | coverage fence | RED ×5 |

Control, unmutated: unit 20/20, e2e 11/11, fence 3/3. Whole suite **3 101
passed** (was 3 067), `tsc --noEmit` clean, `next build` clean.

**Two false greens in my own fences, caught by mutation, not by review:**

1. The first version of the M1 arm PASSED with the options reverted — because
   `guardCommands`' own deadline caught the hang either way. The arm named "the
   options" was measuring the wrapper. Fixed by reading the constructed client's
   own option bag (`liveClientBounds()`) and by a BARE-ioredis arm that uses no
   wrapper at all.
2. The first version of the page-bound e2e arm asserted a "31 sequential call"
   shape that never ran — `getCostHistory` bails at its FIRST call when the
   roster read fails, so it passed with the breaker neutered. Replaced with the
   five real fetchers of a costs render, whose measured with/without margin
   (3 004 vs 12 009ms) is stated in the test.

## The built app, driven

`next build` + `next start` (NODE_ENV=production, minted session cookie), against
an in-process mute store:

| path | before | after | banner |
|---|---|---|---|
| /display | (hang) | 200 @ 3 050ms | `unreachable` / STORE UNREACHABLE |
| / | (hang) | 200 @ 24ms | `unreachable` |
| /costs | (hang) | 200 @ 12ms | `unreachable` |
| /health | (hang) | 200 @ 11ms | `unreachable` |
| /crons | (hang) | 200 @ 11ms | `unreachable` |
| /officers | (hang) | 200 @ 9ms | `unreachable` |
| /queue | **TIMEOUT @ 45s** | 200 @ 6 014ms | `unreachable` |

Visible text on `/costs` under an unreachable store contains **no dollar amount**
at all, and the banner reads *"the store this dashboard is configured to read
(REDIS_URL) did not answer — the store rejected `ping` (Command timed out)."*

**INVERSE, same harness against a store that ANSWERS:** every page 200 in 9-56ms
with **no banner on any of them** (zero pixels for a live store).

`/tasks` 500s in this harness on BOTH the unreachable and the healthy run —
`NEON_CONNECTION_STRING env var is not set`. A Postgres dependency of
`getBoardStats`, unrelated to this change and pre-existing. Its redis path was
still fixed (`lib/tasks.ts` roster read now falls back rather than throwing).

## Residuals, stated rather than folded in

- **Subscriber clients get no `commandTimeout`.** They hold long-lived sockets
  and receive pushed messages; bounding a per-command reply on them is probably
  right, but this change cannot prove the healthy subscriber path (its fake store
  answers commands, not pub/sub), and an unproven change to a long-lived
  connection is how a silent break ships. They gain the connect and retry bounds.
- **The blackhole shape is measured but not in CI.** A sandboxed runner may
  answer ENETUNREACH instantly instead of dropping the SYN, which would pass the
  arm for the wrong reason. Both CI arms are loopback-local and deterministic.
- **`/queue` costs two timeouts (6s), not one**, because `queue.ts` holds its own
  client with its own breaker. A process-wide breaker across independent clients
  would be over-engineering for a bounded 6s.
