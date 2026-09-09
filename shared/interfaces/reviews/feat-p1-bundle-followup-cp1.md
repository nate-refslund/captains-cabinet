# FW-019 review artifact — `feat/p1-bundle-followup` checkpoint 1

Unit U7b (phase-1 wave-2 tail). Contract of record: phase-1 contracts §7 +
amendments A7.1–A7.7; the deliverable is A7.6 (the landing-acknowledgement
predicate), A7.7 (G3's bytes landed in the unlocked lane) and the round-2
reviewer's note n4 (a docstring that claimed an arm drove a channel it never
touched). Everything below was run in a fresh clone of
`https://github.com/nate-refslund/captains-cabinet.git` at `113b52c4`, on
`python3.12`, with `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` purged.

## What changed, and why each piece is here

| file | why |
|---|---|
| `cabinet/scripts/hooks/session-task-inject.sh` | A7.7. `G3.diff` applied verbatim, not re-authored: `git apply --check` rc 0, resulting sha256 `5f2e177b…` = the declared post-image, `bash -n` clean. The hooks directory's schg lock is a fact of the LIVE checkout, not of git (precedent `5338cb42`). |
| `…/germline-amendment-employee-phase1-2026-09/verify.sh` | G3's `BUNDLE_ROWS` state `proposed` → `landed`; digests unchanged and re-verified (pre-image = the file at `8bd3e0c2^`, post-image = the file at `8bd3e0c2`, the G1 shape). |
| `…/germline-amendment-employee-phase1-2026-09.md` | the apply contract now describes what is true: both halves landed, step 3 is a `git checkout` for both rows, §4 documents the A7.6 channel, §7 keeps the box's bytes UNMEASURED, §8 records two new residuals. |
| `cabinet/scripts/tests/test_germline_bundle.py` | the A7.6 predicate + five new arms; the post-image arm rebuilt on a pre-image fixture; the backstop rewritten and its master-red fixed. |
| `cabinet/scripts/drills/one-responsibility.sh` | two consequences of the landed bytes, found by running the drill: P2h's re-tick and the hook's new log directory. See "What landing found" below. |
| `framework/tests/test_interpreter_pin.py` | its locked-hook exclusion arm was self-retiring (`"if it was pinned by a ceremony, this exclusion is obsolete"`) and retired. Inverted, not deleted. |
| `framework/missions/gaps.py`, `framework/missions/session_bridge.py`, `framework/missions/tests/test_session_bridge.py` | three comments that described the hook's `2>/dev/null` as current. Comment-only: framework production non-comment line count delta **0** on both production files (measured). |
| `framework/tests/test_amendment_doc_lint.py` | `A7.6`/`A7.7` anchors; `proposed, not landed` and `g3 is not landed` forbidden so the withdrawn phrasing cannot drift back. |
| `docs/plans/operative-egg-ledger-2026-07-07.yml`, `…-plan-2026-07-07.md` | CG-36's title, `gate_cmd`, note and plan twin. A13 parity rc 0 after; `CG-36` count 1 in each. |

## A7.6 — what the predicate is now

`_landing_acknowledged(offenders, ack)` vouches only when **both** halves hold:
`CABINET_GERMLINE_LANDING` names a CG row present exactly once in the ledger,
AND every offending path is one the package **declares** it is landing — a
`landed` row of its own `BUNDLE_ROWS` table, or an explicit landing list in its
document — and that path currently holds the digest the package declares for
it. An empty offender list is never vouched for (`all([])` is True, and that is
the degenerate end this file keeps finding elsewhere).

The channel is deliberately NOT wired into CI. A landing branch is an
exceptional reviewed act; the operator running it exports the variable for that
run. After the merge the branch diff is empty and the guard is a no-op again.

## What landing the bytes found — the part that could not be found before

A7.7's argument was that a diff which can only be applied inside the window can
only be *checked* inside the window. Landing it produced two failures in this
session that the Captain would otherwise have met at ceremony step 4:

1. **The phase-1 drill's P2h stage failed** (`exit 20 — the holder's own tick
   did not renew its claim`), reproducibly, on the first run after the landing.
   Cause: the landed hook derives the holder from the payload's `session_id`
   and **exports** `CABINET_WORKER_ID` over whatever it inherited, while the
   drill's re-tick hardcoded one session id and set `CABINET_WORKER_ID` to the
   winner of a race it does not control. Fixed by reading the winning session
   id back out of the holder the race produced. Pre-window bytes are unaffected
   (they export nothing and the explicit variable still wins).
2. **The hermeticity stage then failed** — the hook creates
   `${CABINET_HOOK_LOG:-$HOME/Library/Logs/cabinet/hooks.err}`, four new paths
   under the drill's scratch `HOME`. Fixed by pinning `CABINET_HOOK_LOG` into
   the run's own scratch, which drives the override seam the bundle added
   rather than suppressing the channel it exists to open.

Full drill after both fixes: `rc 0`, including the update leg; `--skip-update`
run four times, P2h green every time.

## A pre-existing red on master, repaired here

`test_the_guard_is_not_exempted_on_this_branch` asserted `changed` non-empty.
On master `HEAD` **is** the base, so the diff is empty and the arm has been RED
on the trunk since U7 merged — measured on a pristine clone of `113b52c4`
before any change of mine. A backstop that cannot be green on the tree it
protects is the shape that gets deleted. The empty case is now asserted to be
empty for the right reason (`base == HEAD`) instead of failing.

## Claim surface

Every docstring in the changed test files was re-read against its body. The one
that was false — n4's "with the acknowledgement channel driven at the same
time" — is now true: the arm drives `_landing_acknowledged` with a CG id that
has no ledger row and with an undeclared locked path added to the set, and
requires both to refuse.

Sensors, batteries, exit codes and the failing-set identity proof are in the PR
body and are not duplicated here.
