# Review artifact — fix/bash32-empty-array cp1 (2026-07-26)

Batch: macOS `/bin/bash` 3.2 empty-array expansion — 2 shell repairs
(`officer-env.sh`, `bootstrap-roles.sh`) + 2 new test modules (6 runtime
sensors on macOS, 11 ratchet arms on any platform). ~720 lines → FW-019
artifact.

## Incident

macOS ships `/bin/bash` **3.2.57** (`GNU bash, version 3.2.57(1)-release
(arm64-apple-darwin25)`, measured on the Captain's Mac). Under `set -u`,
bash 3.2 aborts on expanding an **empty** array; bash >= 4.4 permits it:

```
$ /bin/bash -c 'set -u; a=(); echo "${a[@]}"'
/bin/bash: a[@]: unbound variable
```

`cabinet/scripts/lib/officer-env.sh:30-32` (introduced 2026-07-15 in
`f0d13bfd`, the only commit ever to touch that file) built
`local -a _observe_arg=()` and expanded it unguarded. The array is empty on
the **default** (not observe-only) path, so the default path was the broken
one and no env override routed around it. `start-officer-mac.sh` runs
`set -euo pipefail`, so the non-zero return killed the launcher.

Blast radius, measured not assumed:

- `cabinet/launchd/com.cabinet.officer.template.plist` hardcodes `/bin/bash`
  → **no officer could boot on macOS on this master**. Reproduced
  end-to-end: `start-officer-mac.sh cos --dry-run` exits **2** before the fix,
  **0** after, under otherwise identical conditions.
- `bash` on `PATH` is also `/bin/bash` 3.2 on a stock Mac (no Homebrew bash on
  the Captain's machine), so every `bash foo.sh` invocation in the tree runs
  3.2 — the exposure is not limited to launchd.
- `hatch.sh` step `proof-c1` is literally
  `bash cabinet/scripts/start-officer-mac.sh cos --dry-run`, so the hatch
  died there too.

The emitted error blamed the dotenv ("refusing to source it as shell code"),
which is a red herring — the parser alone returns rc 0. The misleading text is
a consequence of `$(...)` failing for a reason unrelated to the parser.

## Why nothing caught it — two sensor failures, not one

1. All seven CI jobs are `ubuntu-latest` (bash 5.x). CI structurally cannot
   execute its way into this class.
2. **The more interesting one:** `cabinet/scripts/lib/tests/test_officer_env.py`
   *does* call `officer_env_load_file` under `/bin/bash` (3 harnesses) — but
   every harness runs `set -e` **only, never `set -u`**, while the real callers
   run `set -euo pipefail`. Measured on the Captain's Mac against the broken
   master: **18/18 of those tests pass while no officer can boot.** A harness
   that does not reproduce the caller's shell options is not a sensor for
   anything those options decide. Fixing only the CI-platform gap would have
   left this hole open.

## Fix

Both sites use the alternate-value form `${arr[@]+"${arr[@]}"}`, which expands
to **zero** arguments when empty and to the element(s) when populated.

`"${arr[@]:-}"` — the form already used elsewhere in this tree
(`cabinet-bootstrap.sh`, `sentry.sh`, `vercel.sh`) — was **explicitly
rejected** here: it expands to **one empty-string argument**, and the officer
parser's argparse rejects that as `unrecognized arguments:` with exit 2. Same
outage, new disguise. Verified both forms' argc directly.

- `cabinet/scripts/lib/officer-env.sh:32` — the live break.
- `cabinet/scripts/bootstrap-roles.sh:302` — same shape on the hatch's
  roster-seeding step (which runs *before* `proof-c1`), under
  `set -euo pipefail`. `caps` is validated non-empty by the roster reader, so
  the empty case is currently **unreachable**; fixed as class hygiene and
  labelled as latent rather than presented as a second outage.

Security properties preserved (checked deliberately, since `--observe-only` is
a credential-*scoping* control, not cosmetics): the flag still reaches the
parser when set, and observe-only still subtracts remote MCP credentials
(`NOTION_API_KEY` unset in the observe arm, present in the default arm). A
"fix" that dropped the flag in both branches would have silently *widened* the
projected credential set while every other test stayed green — that is now its
own test arm.

## Sweep

All 298 tracked shell files scanned (`.sh`/`.bash` plus bash-shebang files),
for empty-array init **and** the `read -ra` / append-only variants that leave
an array unset. 13 further `(file, array)` sites carry the shape but are safe
today, each for a reason a text scanner cannot see — a parallel `$FAIL`
counter, or a `[ -n "$str" ]` on the string that later feeds `read -ra`. All 13
are enumerated with their specific invariant in the ratchet's allowlist. The
`feed-purge-testrows.sh` / `ledger-purge-testrows.sh` guards already carry an
in-code comment describing *this exact gotcha*, so the class was known in this
repo before it shipped in the officer boot path.

## Guards

`cabinet/scripts/lib/tests/test_bash32_empty_array.py` — 6 runtime sensors.
Runs the real code path under `/bin/bash` (absolute path — never `bash` from
`PATH`, which is how a bash-5 host gives a false green) with the real
`set -euo pipefail`. Skips on bash >= 4.4 with a reason naming the interpreter
and version. **CI (ubuntu) skips all 6**; the framework suite runs pytest with
`-rs`, so the skip and its reason print rather than vanish. This is stated
plainly rather than papered over: the defect is macOS-only, so macOS-only
coverage is correct, and the ratchet below covers CI.

`framework/tests/test_bash32_empty_array_ratchet.py` — 11 arms, no shell
executed, **runs on ubuntu CI**. Whole-tree text ratchet over tracked shell,
plus engine self-tests. The allowlist is shrink-only: a stale entry fails the
test, so it cannot grow into a blanket waiver.

Non-vacuity proven four ways rather than by absence-failure:

| Direction | Result |
|---|---|
| New guards vs **pre-change master** | 3 runtime arms + 2 ratchet arms FAIL; the 3 companion arms pass (documented as such) |
| Plant a new unguarded site in an unrelated script | ratchet names `health-check.sh:153 array 'MUTANT_ARR'` |
| Plant a stale allowlist row | shrink-only arm fails naming the row |
| Revert **only** the officer-env fix on the fixed tree | 4 arms fail across both modules |

The ratchet's own self-tests earned their keep: the first scanner draft was
order-insensitive and reported the exact pre-fix `officer-env.sh` shape as
**clean**, because the conditional `[ ... ] && _observe_arg=(--observe-only)`
on the next line read as proof the array was populated. Rewritten as an ordered
positional walk in which a conditional populate proves nothing.

## Verification

Serial, against a re-measured baseline on pristine master, cache purged and
`PYTHONDONTWRITEBYTECODE=1` on every run. Deltas are additive only: no
existing test or threshold was weakened, relaxed or deleted.
