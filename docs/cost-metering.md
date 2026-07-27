# Cost metering

How the cabinet knows what it spent. One module — `framework/cost/meter.py` —
prices every path that costs money, and `cabinet/scripts/hooks/session-stop.sh`
calls it once per officer turn through `framework/cost/record_turn.py`.

Referenced from `framework/cost/__init__.py`. Read this before changing a rate,
a key name or a failure path: most of what follows is a bug that was shipped,
measured, and is now pinned by a test.

---

## 1. What this is for — and what it deliberately is not

The meter is a **WATCH, not a gate.** The Captain removed every spend cap on
2026-07-26, so nothing in `framework/cost` can refuse, delay or slow a call.
Its whole job is to make spend *visible*: to `cabinet/scripts/cost-report.sh`,
`cabinet/cron/cost-summary.sh`, the dashboard, and the three spend rows of the
outcome watchdog (`framework/docs/outcome-watchdog.md`).

That inverts the usual error preference. A gate that over-charges refuses work
that should have run — expensive. A watch that under-reports simply goes blind,
and reports a reassuring number while it does it. So **every estimation choice
in this module fails toward OVER-reporting**, and the two places where it still
cannot (§7) are written down rather than papered over.

Second consequence: a metering failure must never cost an officer a turn.
`record_turn` always exits 0, prints one `cost-meter: …` line, and writes
nothing to stdout that a Stop hook's `{"decision":…}` JSON protocol could
misread.

## 2. The 16.0x under-report — what was actually wrong

The meter this replaced was inline `jq` + bash arithmetic inside the Stop hook.
Measured against **279 real transcripts (~1 GB)** it under-reported by **16.0x**.
Three independent faults, every one of them failing toward under-reporting, and
the layer decomposition was measured separately:

| Layer | Fault | Factor |
|---|---|---|
| Turn scope | `tail -100 \| jq … \| tail -1` billed only the LAST assistant entry per Stop. A response contains one API call per tool round-trip, so a 30-tool-call turn was billed as one call. | **4.4x** |
| Cache price | Cache tokens charged at `0.25x` / `0.02x` of the input rate instead of the published `1.25x` / `0.1x`. Exactly 5x low. The `*fable*` arm three lines above was correct — which is how the opus/sonnet arms survived review. | **3.8x** |
| Cache TTL | No concept of the 1-hour cache TTL (`2.0x` input) — both flavours billed as the 5-minute one. **99.7%** of measured cache writes carry the 1h flavour. (The smaller sample quoted in `framework/cost/tests/test_meter.py` rounds this to 100%.) | **1.1x** |

Plus a fourth, unquantified: an unrecognized model fell through to the
**cheapest** row (Sonnet), so every model the table failed to name was billed at
a fifth of Opus.

`4.4 × 3.8 × 1.1 ≈ 16`.

## 3. Rates, and why cache prices are not literals

Everything is **microdollars**. `$1/MTok` is exactly 1 microdollar per token, so
a rate written in `$/MTok` doubles as microdollars-per-token and the arithmetic
stays integer at the boundary.

| Model key | input $/MTok | output $/MTok |
|---|---|---|
| `fable` | 10 | 50 |
| `opus` | 15 | 75 |
| `sonnet` | 3 | 15 |
| `haiku` | 1 | 5 |

The key is a **substring of the model id** and the first match wins, so more
specific families go first. `RATES` is the single place a rate is written down
in this repo; the shell hooks that used to carry their own copies now call
`price()`. A new model is a new row here and **no branch anywhere else**.

Cache prices are **derived from the input rate by multiplier**, never typed in
as separate literals:

```
MULT_CACHE_WRITE_5M = 1.25    # 5-minute TTL cache write
MULT_CACHE_WRITE_1H = 2.00    # 1-hour TTL cache write
MULT_CACHE_READ     = 0.10    # cache hit
```

This is the structural half of the 5x fix. As literals, a cache price could
drift from its input rate silently and per-model — which is precisely what
happened: opus and sonnet were wrong while fable was right, in the same table,
and the table looked plausible. As multipliers, **the bug is not expressible**:
there is one number per cache kind for every model, and all three are asserted
by name in `framework/cost/tests/test_meter.py`. Adding a model cannot
reintroduce it.

### Unknown models bill at the most expensive known rate

`resolve_rate()` returns the **per-dimension maximum** of the whole table with
the key `"unknown"` — not a default row, and not the max of `input + output`.

Per-dimension because a future row with a high input rate and a low output rate
would otherwise leave unknown models resolving to some other family and
under-billing input. Most expensive because the direction of error is the whole
point: an unknown model is usually a model that shipped after this table was
last edited, and a new frontier model is more likely to be dearer than cheaper.
Over-billing it shows up as a number someone can question; under-billing it
shows up as nothing at all.

## 4. Reading a transcript: dedupe, then watermark

`parse_transcript(path, from_line)` prices every API response appended after
`from_line` and returns the new mark. Two mechanisms, each fixing one half of
the turn-scope problem.

**Dedupe by `message.id`.** Claude Code writes one assistant entry per **content
block**, and every copy repeats the same *message-level* usage. A measured
821-entry transcript held **352 distinct message ids**; summing entries naively
over-counted `cache_read` by 2.3x. Billing is per API response, so a repeated id
inside one slice is counted once and tallied in `duplicates_skipped`.

**Per-session watermark.** The Stop hook fires once per officer *response*, but
a response spans many API calls, so the meter must sum the whole slice — and
summing the whole *file* every Stop would re-bill everything already counted.
So `record_turn` persists the line count in `cabinet:cost:wm:<session_id>` and
passes it back as `from_line` on the next Stop. Properties that matter:

* The mark is **advanced only after the ledger write is positively confirmed**.
  A failed write leaves it where it was, and the slice is re-billed next Stop.
  That can double-count on a retry — the OVER direction, which is the safe one
  for a watch.
* It is keyed **per session**. A session id that does not survive
  `safe_principal()` (the Stop payload defaults it to the literal `unknown`)
  falls back to the officer slug, because letting `unknown` through would
  collapse every such session onto one counter, where a long transcript's high
  mark silently suppresses billing for a short one.
* TTL is 8 days, matching the ledgers. An expired mark re-bills the transcript
  from line 0 — an over-count, but a needless one.
* **Truncation recovery.** If the file is now SHORTER than the mark it is not
  that file any more (rotated, replaced, rebuilt), so the mark resets to 0 and
  is repaired even when the slice has nothing billable. Without this the meter
  goes permanently dark for that session: `from_line` can never be reached
  again, silently and forever.

Two entry kinds are deliberately not billed: `<synthetic>` model entries (the
CLI produces those locally — no API call happened, and pricing them would invent
spend), and any entry whose usage numbers will not parse, which is counted in
`malformed_skipped` and skipped. One malformed value must never raise out of the
loop: before that guard, a single poison line stopped the mark from advancing
and every later Stop re-read the same line — a silent, permanent blackout for
that officer.

Legacy transcripts carry no TTL split on `cache_creation_input_tokens`. Those
are charged at the **5-minute** rate — the lower of the two. See §7.

## 5. Two ledgers, on purpose

**Officer ledger** — `cabinet:cost:tokens:daily:<UTC date>`, one hash per day,
8-day TTL. Fields are `<officer>_<dim>`, or `<officer>_<project>_<dim>` when the
turn carries a project, over the dimensions `input`, `output`, `cache_write`,
`cache_read`, `cost_micro`.

**Latest-turn snapshot** — `cabinet:cost:tokens:<officer>`, 24h TTL, carrying
`last_input`, `last_output`, `last_cache_write`, `last_cache_read`,
`last_cost_micro`, `last_model`, `last_context_tokens`, `last_context_pct`,
`last_updated`. This is a **per-turn** snapshot, never cumulative: the health
dashboard, `cabinet/scripts/list-officers.sh`, `cabinet/scripts/org-health-audit.sh`
and the fw-a14 stop-guard eval read `last_context_pct` from it, and a running
sum would report a context window many times over 100%. The model string is
scrubbed of anything outside `[A-Za-z0-9._:@-]` first — a whitespace or newline
in a model name would desync every line-pair `HGETALL` parser downstream,
including this module's own.

**Lane ledger** — `cabinet:cost:lanes:daily:<UTC date>`, a **separate key**, same
8-day TTL. Fields are `<lane>_calls`, `<lane>_units` (omitted when zero) and
`<lane>_cost_micro`, plus the per-principal twins `<lane>__<principal>_calls`
and — only when the lane is priced — `<lane>__<principal>_cost_micro`.

Lanes are not folded into the officer hash, and this is a deliberate structural
choice rather than tidiness. Anything reading the token hash sums `*_cost_micro`
across it; a fork still running a per-officer cap (`framework/defaults/spending-limits.yml`
ships one) would silently find that "this officer's spend" had changed meaning
to include a shared embeddings bill. Lanes are counted and reported; they are
never charged against an officer.

A principal is an officer slug or `svc:<service>`. Anything else becomes
`unattributed`: that string turns into a Redis **field name** and reaches a
`redis-cli` argv, and it arrives from an environment variable. Spend we cannot
attribute is still spend and is still counted — just not against the wrong
officer. The one exception is `record_session_turn`, which refuses an
unattributed principal outright rather than corrupting per-officer accounting.

## 6. Counted vs merely call-counted

`LANES` marks each lane `priced` or not:

| Lane | Priced | What it is |
|---|---|---|
| `advisor` | yes | the advisor crew → the Anthropic API |
| `api_direct` | yes | raw API calls from crons and hook callers |
| `subscription` | yes | `claude -p` headless — rides the Max pool, not a card |
| `embeddings` | no | vendor `/v1/embeddings` |
| `rerank` | no | vendor `/v1/rerank` — **lane defined but NOT yet wired, see below** |
| `tts` / `stt` | no | vendor speech |
| `websearch` | no | metered search MCPs |

An **unpriced lane never materializes a cost field at all.** It records calls
and vendor units, and every surface renders it as counts. A lane showing
`1,240 calls (unpriced)` is true. A lane showing `$0.00` is a lie, and this
meter exists because of a lie like that: a zero reads as "this lane is free",
which is exactly the reading that let the old under-report survive.

### Known gap: `rerank` is defined but not wired

The Voyage `/v1/rerank` call in `cabinet/scripts/lib/memory.sh` sits inside the
`RANKING-BLOCK` region pinned by
`cabinet/scripts/tests/fixtures/memory-ranking.fingerprint`. Every byte of that
region is guarded, and the only legitimate way to change it is
`retrieval-eval-nightly.sh --stamp`, which re-stamps ONLY from a run where both
retrieval-quality arms hold their floors. That stamper is store-local — it needs
`NEON_CONNECTION_STRING` and a Voyage key — so it cannot run from a clean-room
clone or from CI.

The lane is therefore declared in `LANES` but has no call site. Hand-editing the
fingerprint hex would have made this green by converting a working guard into a
disabled sensor wearing a green badge; an honestly uncounted lane is the better
of the two. `embeddings` IS counted (`memory_get_embedding`, outside the block)
and carries the far larger call volume.

**Follow-up:** wire `rerank` in the same commit as a legitimate re-stamp, on a
box that has the store and the key.

The corollary for anyone adding a lane: do not invent a rate to make the
dashboard tidy. Add it as unpriced, or add a real row to `RATES`.

## 7. Known residuals — where the meter is still wrong

Written down because a watch whose blind spots are undocumented is worse than
one everybody distrusts.

**Long-context premium tiers are not modelled — under-reports.** Requests above
the 200K context threshold are billed at a premium rate; batch and priority
service tiers carry their own discounts and surcharges. Neither is in `RATES`,
because both need the request's actual service tier and context bucket, and the
transcript does not carry the tier reliably. **A 1M-context turn can therefore
still be under-reported.** This is the one residual pointing in the unsafe
direction, and it is deliberate: the alternative is a guessed multiplier, which
would be a number nobody could audit. If the transcript ever starts carrying a
dependable `service_tier`, this is the first thing to fix.

**Legacy cache writes without a TTL split — under-reports.** An older transcript
reports only `cache_creation_input_tokens` with no `ephemeral_1h`/`ephemeral_5m`
breakdown. Those are charged at the 5m rate (`1.25x`) rather than the 1h rate
(`2.0x`). Given 99.7% of measured writes are the 1h flavour this is usually low
— but the alternative is fabricating 1h spend that may not have happened, and
inventing cost is the worse failure for a ledger. It self-corrects as
transcripts age out.

**Cross-Stop message-id repeats can re-bill — over-reports.** Dedupe is scoped
to one parse. A message id repeated *across* a watermark boundary is billed
twice. Measured: **1 occurrence at a gap greater than 9 lines across 3,124
repeat events**. The direction is over-count, the safe direction for a watch, so
it is left alone rather than paid for with a persistent cross-slice id set.

**A failed ledger write re-bills the whole slice — over-reports.** By design; see
§4. Same for an expired watermark.

**The `subscription` lane's dollars are notional.** `claude -p` rides the Max
pool, so its `cost_micro` is list-price-equivalent, not a card charge. Do not
add it to a figure that claims to be money actually billed.

## 8. Failure semantics — why exit codes are not trusted

`redis-cli` prints error replies on **stdout** and still exits 0. Worse, and
measured on redis 8.x: reading commands from **stdin** it exits **0 with EMPTY
stdout** when the server is unreachable, printing "Could not connect" once per
command to stderr.

An exit-code-only check therefore reads a total connection failure — or a
`WRONGTYPE` ledger, a `NOAUTH` after someone sets `requirepass`, a `LOADING`
during an AOF replay — as a **successful write**. The mark advances, the spend is
gone, and the log line is green.

So `_redis_atomic()` uses **positive confirmation**: MULTI must answer `OK`,
there must be exactly one `QUEUED` per command, stderr must be clean, and no
reply line may carry an error prefix. All four layers, and the failure they
each catch, are pinned against a real ephemeral Redis in
`framework/cost/tests/test_meter_redis.py`.

The same MULTI/EXEC gives atomicity: a partial write (3 of 5 `HINCRBY`s landing)
used to report failure, so the whole slice re-billed next Stop and
double-counted the three that had succeeded. One subprocess also caps latency —
a per-command `redis-cli` meant ten 5-second timeouts on a Redis that accepts
connections but never answers, i.e. ~50s inside a Stop hook.

**`hgetall()` returns a tri-state and callers must keep it apart:** a dict when
the key was read, `{}` when the ledger genuinely exists-and-is-empty, and `None`
when Redis could not be reached at all. `{}` with officers who worked today is
an alarm (`meter-silent`); `None` is not an observation and must skip. Collapse
them either way and you get a dead meter that stays green, or a false alarm on
every Redis blip.

## 9. Tests

| File | Covers |
|---|---|
| `framework/cost/tests/test_meter.py` | pricing, the rate table, transcript parsing, principal sanitation — pure unit, no Redis |
| `framework/cost/tests/test_meter_redis.py` | every Redis path, against an ephemeral private `redis-server`: watermark round-trip, poisoned ledger, unreachable Redis, rotated transcript, the Stop-hook exit-0/clean-stdout contract, the `hgetall` tri-state, and the lane ledger |

The second file exists because the first passes identically with `REDIS_PORT`
pointed at nothing. Every arm in it stands up its own server on a free port and
refuses 6379; the arms skip with a reason if `redis-server` is unavailable
rather than silently passing.
