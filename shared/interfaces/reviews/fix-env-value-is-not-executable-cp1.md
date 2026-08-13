# Self-review — fix/env-value-is-not-executable cp1

Reviewed-Scope-Digest: 037aff660d04b697b05b70137183799e4e5a97e84cce8e7d19839bc5aa6461d0

Security-sensitive change. This review attacks its own fix; it is not a summary.

## The property being asserted

**A value written into `cabinet/.env` by any of the cabinet's writers is INERT
when a script `source`s the file — for ANY input.** `cabinet/.env` is bash-
`source`d by 30+ scripts, several under `set -a` (`cabinet-spawn.sh:170`,
`create-project.sh`, `memory-reconcile.sh`, `resume-officer.sh`, the cron
wrappers…). Before this change the only validation on a value was a newline
refusal, so `FOO=$(touch /tmp/x)` — settable through the dashboard's add-a-secret
form (`integrations-forms.tsx` → `addEnvVar`) — executed at assignment the next
time any of those scripts sourced the file. Reproduced on bash 3.2 (the
deployment): the payload's `touch` ran; the marker appeared.

## Approach chosen, and why (not the alternative)

**Safe emission by SINGLE-QUOTING, applied only when the value is not provably
literal.** A value made entirely of the shell-inert set
`[A-Za-z0-9_.:/=+@%,-]` (plus empty) is emitted BARE; anything else is wrapped
in single quotes with `'` escaped as `'\''`. bash treats the whole of a single-
quoted string literally — no `$()`, `${}`, backtick, `~`, glob or word-split
survives — so the quoted form cannot expand.

- **Why quote-when-needed, not always-quote.** The security property is identical
  either way (anything not provably inert is quoted). Quoting *only* the unsafe
  minority keeps every plain value (API keys, tokens, ids, connection strings
  without query args) **byte-identical to today**, so the ~15 hand-parsers that
  read plain keys by `cut -d= -f2-` are untouched, and existing byte-exact tests
  (`unexecuted-command.test.ts` `SWEEP_INVERSE_KEY=landed`, `config-write.e2e`
  `EXISTING_KEY=rotated`, the wizard's `WEBHOOK==64 chars` / `DASHBOARD_PASSWORD=`
  empty) stay green without edits. Always-quoting would have relabelled every one
  of those and forced ~20 consumer edits — larger blast radius for zero extra
  safety.
- **Why not an allowlist that rejects `$`/backtick (option b).** An operator's
  third-party key is not ours to constrain; a Neon string legitimately carries
  `&`/`?`. Rejecting on charset breaks real credentials. Quoting accepts any byte
  and neutralises it.

## Attack panel — can anything still expand on source?

Written via the real writer, then `set -a; source; set +a` on real bash. All
verified (vitest `env-source-safety.test.ts` 35 cases; pytest
`test_env_value_not_executable.py` 24 cases, run on `/bin/bash` 3.2):

| Attack | Result |
|---|---|
| `$(touch M)` / `` `touch M` `` / `pre$(…)post` | quoted → literal; M never created |
| `${HOME}`, `${IFS}` | quoted → literal `${HOME}` |
| `x; touch M`, `x && touch M`, `x \| touch M`, `x > M`, `(touch M)` | quoted → literal; no exec |
| unquoted space `a touch M` (splits the assignment word) | quoted → literal; no exec |
| `~root/x` (tilde expansion) | `~` excluded from bare set → quoted → literal |
| a value that is itself `"$(touch M)"` (double-quoted subst) | single-quoted → the inner `"` and `$()` are literal; no exec |
| `'`-laden `O'Brien`, `a'b'c` | `'`→`'\''`; sources back to the exact string |
| newline `a\nSUPERUSER=yes` | still REFUSED (throws); cannot inject a second line |
| unicode `café-☕-Ünïcode` | not in bare set → quoted → literal round-trip |
| backslash `a\b\c` | quoted → literal (single quotes preserve `\`) |

Degenerate ends: **empty** → bare `KEY=` (sources to empty; the first-run
`DASHBOARD_PASSWORD=` shape is preserved). **all-safe** → bare (no churn).

The bare set was derived from bash's assignment-RHS expansion rules (RHS
undergoes tilde/parameter/arithmetic/command-substitution + quote removal, **not**
word-splitting or globbing). Every excluded byte is either an expansion trigger
(`$` backtick `~`), a word terminator (space `;` `&` `|` `<` `>` `(` `)` newline),
a quote, or simply not-proven-safe (kept out on purpose — quoting it is free).

## Do the readers still read it?

`source` needs nothing — bash unquotes natively, and 30+ sourcing consumers are
fixed for free. The hand-parsers (that read a value's TEXT) were swept:

- **In-process (TS):** `parseEnvDocument` and `docker.ts getEnvVars` now pass
  values through `envValueUnliteral` (exact inverse of the writer; decodes
  `'\''`). `officers.ts envAndRun` dropped its fragile `export $(grep|xargs)`
  second-parse — xargs' quote rules are not bash's and would have mangled a
  quoted value — for `set -a; source; set +a`, the idiom every other boot script
  uses.
- **Shell writers' own reads:** the 3 `current_value` helpers now `_env_unquote`.
- **`load-preset.sh`** already stripped a `"`-quoted Neon string; extended to `'`.
- **Plain-only readers accounted for, not changed:** the `cut -d= -f2-` readers
  of tokens/ids/slugs (`run-frontdoor-briefing.sh`, `chair-preflight.sh`,
  `model-fallback-pager.sh`, `telegram-validate-token.sh`, `sentry.sh`,
  `setup-mac.sh` NEON *presence*-check, …) read keys whose values are always in
  the bare set → the writer never quotes them → they see exactly today's bytes.
- **Already-tolerant readers:** `cabinet-doctor.sh`, `lib/memory.sh` and the two
  Python falsifiers strip outer `'`/`"` already, so a quoted value (Neon) reads
  correctly.

## Known residual (stated, not hidden)

A value that is BOTH shell-unsafe (so it is single-quoted) AND contains a literal
`'` (so the wrapper carries `'\''`), when read by a hand-parser that strips only
*outer* quotes (the two Python falsifiers, `cabinet-doctor.sh`, `lib/memory.sh`),
decodes with the `'\''` artifacts left in. This is (a) not a security hole — the
value is inert on source, this is a read-fidelity edge; (b) confined to keys those
parsers read (EMBED_*/VOYAGE/NEON/secret-refs), none of which legitimately
contains an apostrophe; a wrong secret is an auth failure, never an execution.
The in-process parsers and the 3 `current_value` helpers decode `'\''` fully.

## Gates

`bash -n` + shellcheck clean on all shell edits (one pre-existing SC2097 at
`load-preset.sh:640`, untouched). Full dashboard vitest green; `pytest
cabinet/scripts/tests` green; `check-layer-separation.sh` OK (new=0); null-hatch
sources its generated `.env` cleanly. Sensor proven: neutering the quoter turns
16 vitest arms RED with "sourcing .env executed the payload".
