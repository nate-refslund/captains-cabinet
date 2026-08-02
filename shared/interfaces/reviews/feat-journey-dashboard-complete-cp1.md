# FW-019 self-review — feat/journey-dashboard-complete (cp1)

Reviewed against the working diff, 2026-08-02. Branch off `ad8f0d3f`.

## What changed, and why each piece exists

| Unit | Change | The defect it closes |
|---|---|---|
| U3 | `src/lib/onboarding/parity.test.ts` (new) | Nothing compared the Python action vocabulary with the three TS mirrors, so an action could exist in the core, be printed on the card, and be refused by the bridge. |
| U1 | `types.ts`, `bridge.ts`, `journey-card.tsx`, `telegram.ts` | `answer_salience` was a LIVE dead-end button: `choose()` bare-sent it and the bridge refused `action_invalid` before the core saw it. `record_operator_identity` fell through the same path onto a core refusal. |
| U2 | `bridge.ts` (`refusalDetail`), `route.ts`, `journey-card.tsx` | `salience_window_off_target` arrived as a sentence with no control able to state either relation the core accepts. |
| U4 | `journey-card.tsx` | The Dashboard rendered citations without disclosing that some had been withheld. Telegram has said so since the verdict existed. |
| — | `docs/plans/declared-residuals-register.md` | RES-023 updated (surface half closed, anchor still live so it stays open); RES-027 added for the inert detail lane. The register gate caught the new declaration and refused the commit until it had a row — working as designed. |
| — | (withdrawn) | A calendar time-bomb in `_split_estate_rows` was found and fixed here, then landed independently on master as `fc0efa9d` while this branch was in CI. Master's version is strictly better; mine was dropped at the merge. See "concurrent writer". |

## Dissent from the brief, on record

The brief said the API route drops `detail`, so the UI can never build the
fix-up. **The first clause is true and the second is not, and the drop starts
one layer deeper than mapped.** Measured by driving the real core:
`framework/onboarding/journey.py::_cli` (line ~4628) prints
`{"ok": false, "code": ..., "error": ...}` and never forwards
`JourneyError.detail`. The bridge and the route were downstream of a value that
does not exist. journey.py is out of scope by instruction (germline + COG-4), so
the mechanism as briefed is unreachable without it.

What was built instead, and why it is not a half-fix: everything the fix-up
needs is already on the surface — the answered target is `state.salience.target`,
the folder is what the operator just submitted, and the relation vocabulary is
`WINDOW_RELATIONS`, now mirrored in `types.ts` and pinned key-for-key against
the Python dict by the parity gate. So the card renders the two statements from
what it holds, and *prefers* an allowlisted `detail` when one is present. The
receiving half (bridge allowlist + route pass-through) is real, tested, and
inert until the CLI emits — which is a germline+contract unit of its own. Both
arms are tested; neither is claimed to be live when it is not. The residual is
stated in `bridge.ts`, in the CLI-contract test, and in the PR body.

## Class-11: the four questions, per new sensor

**1. Does the arm FAIL against pre-change code?** Verified by simulation, not
assertion. The parity gate was landed first and run on the pristine tree:

```
FAIL  the dashboard bridge admission set equals the core dispatch set
FAIL  the TypeScript action vocabulary equals the core dispatch set
FAIL  every offered action has a Telegram branch or a named exemption
      → ['answer_salience', 'gather_connectors']
```

The card arms were then verified by reverting the three behaviours in place and
re-running: `the option button POINTS AT the picker`, `the identity option
POINTS AT its picker`, `drops a relation this surface cannot state` and `says
how much is held back` all went red, and only those. The file was restored from
a byte copy.

**2. What happens at the degenerate end?** `refusalDetail` is tested against
`undefined`, `null`, an array, a bare string, wrong-typed fields, whitespace-only
strings and an empty list — every one yields `{}`, and the route omits the key
entirely rather than sending `detail: {}` (an absent detail must not read as a
present-but-blank one). The egress line is tested at `withheld > 0`,
`withheld === 0`, and no verdict at all. The salience picker is tested with no
pick, escape-hatch-without-name, escape-hatch-with-name and a ranked pick. The
parity parsers throw on zero parsed entries rather than comparing empty sets —
a set-equality gate whose both sides are empty is the classic green hole.

**3. What does the test environment guarantee that production does not?** The
bridge arms stub `node:child_process` rather than spawning Python — deliberate,
since a real spawn would write into the running checkout's onboarding state. The
protocol that stub implements is not assumed: `test_journey_cli_surface.py`
drives the REAL core through the REAL argv/stdin path and pins the same shapes,
so the two halves meet at a tested contract. Conversely that Python file's
`sys.executable` is the interpreter pytest runs under, not a hardcoded
`python3.12`, so it cannot pass here and fail on a runner with a different name.

**4. Is the sensor wired to the LIVE artifact?** `ACTIONS` is now exported from
`bridge.ts` and imported by the gate — the admission set itself, not a re-parse
of its source. `ONBOARDING_ACTIONS` is a runtime array in `types.ts`, and the
documented union is pinned to it at compile time by `ActionsAgree` (a `never`
assignment fails `tsc --noEmit`, which CI runs as its own job). Only the Python
side and Telegram's command table are parsed, because neither can be imported
here — and both parsers refuse input they cannot read rather than skipping it.

## Attacks run against my own fix

- **Prototype chain.** `detail.relations` reaches the card from a refusal.
  `isWindowRelation` uses `hasOwnProperty`, and the test feeds it
  `['elsewhere', 'probably', 'constructor', '__proto__']` — only `elsewhere`
  survives. A relation the surface cannot state is dropped rather than rendered
  as a button that could only earn `salience_relation_invalid`.
- **Exemption as a place to file work.** `TELEGRAM_EXEMPT` is guarded three
  ways: the reason must exceed 60 characters, must not match a placeholder
  pattern (`tbd|todo|later|not wired|coming soon|n/a`), and must name an action
  the core actually offers and Telegram does NOT already handle. Without those,
  the "or a named exemption" clause is a rubber stamp.
- **Closing one dead end by opening another.** Wiring `answer_salience` into
  Telegram means an operator can answer there — and then propose an off-target
  folder there, and get a refusal that channel could not answer. So the folder
  and documents commands take a trailing `| same_thing` / `| elsewhere`, and the
  refusal reply carries that syntax the way an ownership refusal already carried
  its own. An unrecognised trailing segment is NOT dropped: it stays in the
  string, the ownership tail stops parsing, and the core refuses for a reason
  the operator can act on — pinned, because a parser that silently drops what it
  cannot read would send a proposal nobody wrote.
- **Interception becoming a quieter dead end.** Routing `choose()` to a control
  that is not on the card would be a button that silently does nothing. Both
  interceptions are conditional on the control existing; otherwise the bare send
  still goes so the operator gets the core's own sentence. Pinned by
  `still sends bare when the control does not exist`.
- **Egress leak.** The disclosure renders counts only. The fixture carries a
  `withheld_reason` sentinel and the test asserts it never appears in the HTML —
  the surface renders the verdict and can never reconstruct what it withheld.
- **Widened boundary.** `refusalDetail` is a field-by-field allowlist, never a
  spread; strings are cut at 300 chars, lists at 8 members, non-string members
  dropped. Tested with a 5,000-char target and a 40-member list.

## Concurrent writer — a fix of mine that is correctly NOT in this PR

`_split_estate_rows` in `framework/onboarding/tests/test_journey.py` stamped its
rows `2026-07-01..17`. The ranker scores recency, so on unchanged code the
fixture aged out of its own premise and
`test_answering_merges_a_split_candidate_and_the_shortlist_changes` failed its
`"no split to fix"` assertion — a required job going red on a commit nobody
touched. I root-caused it, measured the stable band, anchored the fixture to
`now`, and committed it here because a green PR was otherwise impossible.

**Another session landed the same fix first**, as `fc0efa9d`, while this branch
was in CI. Theirs is strictly better and I took it whole at the merge: it names
the mechanism exactly (`salience._RECENCY_BANDS` at 7/30/180 days, so the
literals were authored inside the 30-day band and the oldest rows crossed out of
it), it anchors ALL THREE dated fixtures rather than only the one that fired
("fixing only the red one is how a silent hole becomes a green one"), it makes
the row AGES constant by construction rather than re-tuning an offset, and it
names a measured residual — three more tests in `test_who_and_when.py` on the
same fuse about a month out.

`git checkout --theirs` on that file; `git diff origin/master` over it is empty,
so nothing of mine survives in it. This is the class-8 case working as intended:
the other writer's fix made mine *wrong to keep*, not merely redundant, because
two anchoring schemes in one file would be worse than either.

`framework/fidelity/tests/test_retro_shim.py` also fails locally
(`claude-sonnet-5` vs a pinned `claude-sonnet-4-6`). **Deliberately NOT touched**:
that constant is re-exported from an out-of-repo personal pipe,
`framework/fidelity/tests/conftest.py` skips the suite where the pipe is absent,
and master's CI is green on it. Changing the pin would be adapting the repo to
this laptop.

## Batteries

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npx vitest run` (full dashboard) | 3282 passed, 1 skipped (was 3225 — 57 new) |
| `pytest framework/onboarding/tests -q` | 842 passed, 1 skipped (re-run post-merge on master's anchoring) |
| `pytest framework/ -q` | 8013 passed, 25 skipped; 1 environment-local failure documented above |
| `pytest cabinet/scripts/tests -q` | 5226 passed, 34 skipped |
| `check-layer-separation.sh` | OK — new=0 |
| `cognitive-architecture-census.py` | PASS — no budget moved (test files are excluded from the counts) |
| guarded-token grep on the diff | one hit, a captain-identity string in a new fixture; replaced |

## Known limits of this change

- The `detail` path is inert until `journey._cli` forwards `JourneyError.detail`.
  The card does not depend on it.
- Telegram gained `answer_salience` and `gather_connectors`;
  `record_operator_identity` remains exempt with its reason (the offer cannot fit
  a 64-byte `callback_data` and the core requires a picker over estate-spelled
  identifiers).
- `gather_connectors` gets a tap only past the `welcome` stage — that stage
  returns no buttons at all by an existing deliberate rule, left untouched. The
  `/onboard gather` command works everywhere.
- The parity gate compares vocabularies, not payload shapes. An action whose
  required FIELDS change on the Python side is still invisible to it.
- RES-023 cannot be retired here: its anchor paragraph lives in `journey.py`, and
  a row may not be retired while its declaration is in the tree. Its Open field
  now records that only the paragraph remains.
