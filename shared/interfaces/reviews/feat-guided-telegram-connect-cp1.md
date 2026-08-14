# feat/guided-telegram-connect — checkpoint 1 review

Adversarial pass over the guided Telegram connect (dashboard). ~2.8k added
lines, of which ~1.1k are tests and ~1.2k are screenshots.

## What changed

| Surface | What it now does |
|---|---|
| `cabinet/dashboard/src/lib/telegram/contract.ts` | the vocabulary the client may hold: the test message, the chat shape, the two env var NAMEs, the plain sentence a failure becomes. No `fetch`, no `process.env`. |
| `cabinet/dashboard/src/lib/telegram/connect.ts` | the ONLY new Telegram transport: `getMe`, a no-offset `getUpdates`, one `sendMessage`; `readCapture` decides which chat to bind to. |
| `cabinet/dashboard/src/actions/telegram-connect.ts` | four auth-gated server actions: status, verify-then-store the token, listen once, send-then-record. |
| `cabinet/dashboard/src/components/telegram/connect-flow.tsx` | four props-only step components plus the stateful container. |
| `cabinet/dashboard/src/components/telegram/power-up-card.tsx` | the post-onboarding offer; renders nothing when connected or dismissed. |
| `cabinet/dashboard/src/lib/config-write.ts` | `ensureEnvFile` lifted out of `actions/env.ts` (one copy, two callers); `setYamlScalar` gained a `quoted` option. |
| errand notes, `setup-env.sh`, `setup-mac.sh`, `hatch-v0` runbook, capture-script header | all now point at the flow instead of a terminal dance. |
| `framework/tests/test_single_telegram_door.py` | docstring residual names the third TypeScript caller. |

## The four questions

**Does the arm FAIL against pre-change code?** The module is new, so "pre-change"
is meaningless — the arms were mutation-checked instead. Three mutations were
planted and each turned its arm red, then reverted: adding `offset: '0'` to
`getPendingUpdates` (reds the no-offset arm), binding `readCapture` to the LAST
sender (reds the first-sender arm), dropping `scrub` from the rejected path
(reds the no-token-in-a-result arm). The clobber-safety test carries its own
inverted arm rather than a mutation: `test_is_clobbered_when_only_platform_was_written`
removes the answers write from the same fixture and asserts the loss, so the
positive arm cannot pass vacuously against a generator that ignores answers.

**What happens at the degenerate end?** Every one is an arm, and none reports
success: an empty getUpdates window (no candidate, never a fabricated one), an
absent `cabinet/.env` (created 0600 — this found a REAL defect, the first
credential write of a fresh hatch would have thrown), an absent answers file
(a note, and the runtime half still lands), a `getUpdates` result that is not an
array, malformed/`null` updates, a platform file with no such key (appended),
a send that fails (nothing is written at all), an unreadable non-JSON 200.

**What does the test environment guarantee that production does not?** Only the
host. `TELEGRAM_API_BASE` points at a real HTTP socket that records what
actually left the process; the writers, the parsers, the capture reader and the
file layout are the shipped code against real files in a temp tree. No real bot
is ever created — a BotFather account action in the Captain's name is not
something a test may do, and the live halves are proven once by the Captain's
own connect.

**Is the sensor wired to the live artifact?** The writes are asserted by READING
THE FILES BACK, not by trusting a returned flag. The no-offset property is
asserted on the query the fixture server received, not on the code that built
it. The step components are rendered through `react-dom/server` rather than
grepped.

## The three attacks the brief named

**Can the token leak?**
- *Return values*: every action's result is `JSON.stringify`'d and asserted
  token-free on five paths, including two where Telegram quotes the
  token-bearing URL straight back in its `description`.
- *Logs*: `console.log/error/warn/info/debug` are spied across the whole flow
  and asserted never to have received it.
- *Page source*: the container is a client component whose SSR pass runs with
  `token: ''`, so server-rendered HTML never carries one; `getTelegramStatus`
  returns presence booleans and never a masked copy or a last-four — a value the
  page renders is a value in the page source.
- *The file*: stored through the same safe writer every other credential uses,
  and asserted to contain no shell metacharacter, so `source cabinet/.env`
  cannot execute it.
- Residual, stated: the token is in the browser's own input element between
  paste and submit, and in the POST body of the action. Both are unavoidable for
  a paste field; neither survives the request — the client's copy is cleared the
  moment the server has it.

**Can a hostile getUpdates message inject into the UI?** A display name is
untrusted text from a stranger. `sanitizeLabel` strips C0/C1 controls, the bidi
overrides and the zero-width range (two accounts that render identically is the
attack that matters here, not script execution) and caps at 48 characters.
React escapes what it interpolates and nothing uses `dangerouslySetInnerHTML`;
a rendered `<img src=x onerror=…>` username is asserted to arrive as
`&lt;img src=x`.

**Can the capture grab the WRONG chat?** `CAPTAIN_TELEGRAM_ID` is the
default-deny identity gate on inbound DMs and the sole recipient of every
outbound briefing, and a fresh bot's username is guessable. Three things
together: bind to the FIRST private sender rather than the latest; report every
other distinct sender on screen ("More than one person has messaged this bot. I
will use the first one, @ada"); and write NOTHING until the operator confirms
the name they are shown. Groups are never candidates and bots are skipped.
Residual, stated: a stranger who messages the bot in the seconds between its
creation and the operator's own "hi" would be first. The screen says so and the
way out — block, fresh bot, start again — is on the same card.

## Two things found and fixed during the pass

1. **The first credential write of a cabinet's life would have thrown.** The
   safe `.env` writer edits an existing file; a fresh hatch has none. `env.ts`
   had a private `ensureEnvFile` for exactly this; it is now shared rather than
   copied. Caught by the arm, not by review.
2. **A 429 read as "your token did not work."** Telegram returns rate limiting
   in the same `ok: false` envelope as a bad token, so the operator would have
   been sent back to BotFather for a problem that fixes itself in a minute. It
   is now its own reason with its own sentence.

Also corrected before landing: the chat id was being written as a bare YAML
scalar and loading back as an INT, while `generate-instance.py` writes it
quoted. Now byte-identical to the generator's own output, so a regenerate is a
no-op rather than a re-quote.

## Gates

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npx vitest run` (full dashboard suite) | 3511 passed, 1 skipped |
| `python3.12 -m pytest cabinet/scripts/tests -q` | 5290 passed, 34 skipped, 1 failed — `test_evidence_seam_bypass_replay.py::…[evidence-access.sh]`, reproduced identically on a pristine clone of origin/master d80b430a, so pre-existing and environment-local |
| `python3.12 -m pytest framework/tests -q` | 1252 passed, 1 skipped |
| `cabinet/scripts/null-hatch.sh` | PASS (run against HEAD, not the working tree) |
| `check-layer-separation.sh` | new=0 |
| live browser drive | eight screens captured against a production build, real login, fixture Telegram; all three writes verified on disk afterwards |

## What is honestly not covered

- No real Telegram account is exercised anywhere. `getMe` accepting a genuine
  token and a message landing on a genuine phone are proven by the Captain's own
  connect, once.
- The one-door ratchet still does not scan TypeScript. This adds a third caller
  to the three the ratchet's docstring already names as unseen; the flow's
  transport is deliberately one file so a later widening has one decision to
  make.
- Inbound replies do not work on a fresh instance and the flow says so on the
  final screen rather than implying a two-way channel.
