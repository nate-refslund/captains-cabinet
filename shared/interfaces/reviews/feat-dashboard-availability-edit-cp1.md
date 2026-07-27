# Checkpoint review — feat/dashboard-availability-edit (cp1)

**Unit:** Wave-2 D — the Captain's availability dial becomes adjustable from the
dashboard, not only from Telegram.
**Direction:** Captain direction 2026-07-26 (recorded in
`/Users/nate/cabinet-meta/designs/captain-perspective-retro-2026-07-26.md` §5,
"Executed 2026-07-26/27": *"dashboard shows it display-only (write path =
follow-up server action, backlog)"*), under the captain-controls ruling that his
controls must work without a terminal.
**Base:** `82766859d283d5b279e727f001d557e7cf02cfbf`.
**Reviewer:** the landing agent, on Opus 5 (`claude-opus-5[1m]`).

---

## 1. What changed

| file | change |
|---|---|
| `cabinet/dashboard/src/lib/availability.ts` | NEW. The mode-table mirror + the strict value grammar. Pure, no fs, importable from both a server action and a client component. |
| `cabinet/dashboard/src/actions/config.ts` | NEW action `updateCaptainAvailability`. Auth-first, allowlist, exec of the store's own recorder, receipt-gated success. |
| `cabinet/dashboard/src/components/consumer/availability-field.tsx` | NEW. The editable row: current value, where it came from, the whole mode table, an exact-minutes escape hatch. |
| `cabinet/dashboard/src/components/consumer/settings-consumer.tsx` | the read-only block becomes the field; docstring re-stated. |
| `cabinet/dashboard/src/app/(authenticated)/settings/page.tsx` | the row is now on the Advanced surface too (see §3.2). |
| `cabinet/dashboard/src/lib/config.ts` | docstring re-stated; **plus a real defect fix** (§3.1). |
| `docs/runbooks/captain-availability.md` | the "display-only today" paragraph replaced by the write path and its three properties. |
| 3 vitest files + 1 pytest file | the sensors (§4). |

Not touched: the germline onboarding bridge, `src/app/api/onboarding/**`,
`framework/onboarding/availability.py`, `framework/env.py`,
`cabinet/scripts/lib/captain_availability.py`. No germline path is in the diff.

## 2. The load-bearing design calls

**The write goes through the recorder, never a `sed`.** Every sibling action in
`config.ts` writes with `sed -i` against `instance/config/product.yml`. That
shape is wrong here twice over: `instance/config/platform.yml` is a
marker-managed generator output with exactly one writer, and the value the
resolver actually serves is the append-only adjustment store, not the platform
key. So the action runs
`python3.12 <root>/cabinet/scripts/lib/captain_availability.py set <value>
--source dashboard` — the same module the phone verb uses, which already owns
the grammar, the range check, the refuse-don't-round rule, the provenance
comment and the append-only guarantee. A dashboard change and a phone change are
now the same append to the same file; neither can win by being newer somewhere
else. Re-implementing the write in TypeScript would have made a second writer of
the one number the whole org budgets against.

**The row records `source: dashboard`; the resolver still reports `adjusted`.**
Those are different fields answering different questions — provenance versus
precedence level — and both are asserted.

**Only a canonical token reaches the shell.** `parseAvailabilityValue` admits a
mode verb from the table or digits 0..1440, and returns `cli`: the token
re-derived from the table or from the parsed integer. The action interpolates
`cli`, never the caller's string, so a shell metacharacter cannot survive
parsing even in principle. The phone's richer forms (`2h`, `1.5h`, `20 min`) are
deliberately NOT accepted here: every form the dashboard admits is a form the TS
parser would have to keep in step with the python one, and the picker offers the
modes anyway.

**Success is claimed only against the writer's receipt.** `dockerExec`'s mock
branch returns `mock: command executed` having written nothing, and a save the
dashboard reported as done while nothing reached disk is exactly why
`dockerWriteFile`/`dockerReadFile` were deleted (`lib/docker.ts`). The action
requires the writer's `recorded N min/day (mode) -> path` line before it reports
success or revalidates.

**The mirror is paid for with a parity test.** `captain_availability.py`
deliberately refuses to keep a second copy of the mode bands ("a second copy of
the bands would drift"). The dashboard cannot import python, so it mirrors — and
an arm reads `framework/env.py`, extracts the canonical tuple, and compares both
directions. Without that arm the mirror IS the drift the lib warns about.

## 3. Two things found while building

### 3.1 Pre-existing defect: the dashboard dropped every timestamp

`getCaptainAvailability()` read the row stamp as
`typeof r.at === 'string' ? r.at : null`. js-yaml types an UNQUOTED
`2026-07-27T08:00:00Z` as a **Date**, not a string — the same YAML-retyping
class `framework/env.py::_availability_stamp` was already fixed for on the
python side — so `setAt` was silently `null` for every row the recorder has ever
written. The Settings row could show a value but never when it was set.

Found by the read-reflects-write arm failing on a fixture written in the
recorder's real format. Fixed with `normalizeStamp()` (string arm + Date arm,
rendered as `…Z` to match the writer's format), pinned by three arms, and
mutation-checked (M9). In scope because the row this unit makes editable is
required to show its own provenance.

### 3.2 The row was consumer-only, and consumer mode is a flag

`AdvancedSettings` never received the availability value; a deployment with
`consumer_mode_enabled: false` renders Advanced directly. Had the editable row
stayed consumer-only, that deployment would have had no dashboard control at
all — which is the phone-only hole this unit exists to close, reintroduced one
flag deeper. The field is now on both surfaces, from one shared component and
one server action.

## 4. Evidence

### 4.1 New sensors, red against pre-change state

Run in a `git worktree` at the base commit with only the new test files copied
in (`__pycache__` purged between checks):

| sensor | pre-change | why |
|---|---|---|
| `cabinet/scripts/lib/tests/test_captain_availability_dashboard.py` | **14/14 FAIL** | every arm renders the command template extracted from the live `actions/config.ts`; pre-change there is none |
| `cabinet/dashboard/src/actions/availability.test.ts` | **34/34 FAIL** | the export does not exist |
| `cabinet/dashboard/src/lib/availability.test.ts` | **file FAILS** (module absent) | brand-new module — see the caveat below |
| `cabinet/dashboard/src/lib/config.availability.test.ts` | **3/13 FAIL** | the three stamp/adjusted-row arms; the other ten pin pre-existing reader behaviour the new write path now depends on, and honestly cannot be red |

Caveat stated rather than papered over: for a brand-new module "it fails before
the file exists" proves nothing about what the arms claim. That is why §4.2
exists — a parity/allowlist arm can only be falsified by a mutation.

### 4.2 Guard-mutation sweep — 9 mutations, 9 red

| # | mutation | arm that caught it |
|---|---|---|
| M1 | mirror band drifts (`part_time` 30 → 31) | parity |
| M2 | mirror gains a mode the canonical table lacks | parity |
| M3 | canonical table made unreadable (extraction returns nothing) | parity non-empty guard |
| M4 | allowlist widened to accept fractions/negatives | action refusals + grammar refusals |
| M5 | receipt guard widened to match anything | python receipt arm + action mock-exec arms |
| M6 | auth guard no longer the first statement | python auth-first arm |
| M7 | write path swapped back to a `sed` | python store-writer arm + action no-sed arm |
| M8 | raw caller string interpolated instead of the canonical token | action canonical-token arm |
| M9 | stamp normaliser reverted to the naive string check | stamp arms |

Two of these came back GREEN on the first pass and were treated as findings, not
noise:

- **M3** was too weak — renaming the constant left the extraction working, so it
  proved nothing. Replaced with a mutation that genuinely makes extraction
  return an empty set. It now reds.
- **M4** exposed a real gap: the action test's refusal list contained no value
  that the widened regex would newly admit, so it passed while the grammar test
  failed. `0.0` and `-0` were added to the action list; it now reds on the same
  mutation.

Each substitution asserts it actually changed the file — a no-op replace that
"passes" would be the reported-is-not-measured failure.

### 4.3 Batteries run this session (post-change)

| battery | result |
|---|---|
| `npx tsc --noEmit` (dashboard) | exit 0 |
| `npm test` (full vitest) | 123 files passed, 1 skipped; **2307 passed** |
| `python3.12 -m pytest tests/ -q` in `cabinet/scripts/lib` | **438 passed** |
| `python3.12 -m pytest cabinet/scripts/tests -q` | **4781 passed**, 28 skipped |
| `bash cabinet/scripts/check-layer-separation.sh` | OK — new=0 |
| `bash cabinet/scripts/docs-track-code-sweep.sh` | GREEN (files=64 findings=0) |
| `python3.12 cabinet/scripts/state-persistence-preflight.py --repo .` | OK — 0 unaccounted |

## 5. Scope discipline

- **No new durable store, no new instance file.** The unit writes to a store
  that already exists, is already gitignored, already carried by
  `runtime-provision.sh`'s persistence list, already deleted by the egg export,
  already has an `.example` twin, and is already fenced in the repo-root
  `conftest.py`. So: no manifest row, no persistence entry, no new fence — and
  the preflight confirms nothing became unaccounted.
- **Timezone and the monthly budget stay read-only.** Both are `platform.yml`
  fields whose only writer is the generator; a settings action for them needs
  the marker-managed-file question answered first. Noted in the component
  docstring, the page comment and the runbook, and deliberately not built.
- **Nothing here renders a Captain-declared input as a performance number.** The
  value is his statement about his own day, displayed only in his own settings
  row as a budget.
