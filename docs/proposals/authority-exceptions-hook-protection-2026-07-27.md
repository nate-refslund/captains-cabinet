# Proposal — put the Captain's exception list behind the hook (Ring-0 addition)

**Status:** PROPOSED, awaiting the Captain. Not a staged amendment package — it
adds a path to the Ring-0 set, and `framework/policies/immutable-core.yml` says
in its own header: *"this file is itself Ring-0 (dir-cover). Officers/loops
propose changes to the Captain; only the Captain applies them in a germline-lock
unlock window."* This document is that proposal.

**Raised by:** the adversarial review of `feat/authority-matrix-enforcing`
(2026-07-27), as a blocker against the exception surface's original claims.

---

## The gap, measured

`instance/config/authority-exceptions.yml` is the Captain's deny-only "not that"
list (`docs/authority-matrix-enforcement-dryrun-2026-07-27.md` §5). It is
consulted before every typed policy, so a row he adds refuses the call.

It is also **erasable by an ordinary officer tool call**. The path is on neither
of `pre-tool-use.sh`'s protected lists, so all of these are permitted today:

| probe | result |
|---|---|
| `Write` over the file | exit 0 |
| `Bash: echo 'denylist: []' > <file>` | exit 0 |
| `Bash: rm -f <file>` | exit 0 |
| *contrast:* `Write` to `instance/config/act-first-surfaces.yml` | exit 2 `germline_readonly` |

Worse, the refusal an officer receives names the row that blocked it
(`captain_exception:<id>`), which is good for a cooperative officer and hands an
uncooperative one the exact string to delete.

Four of those erasures are **silent** — plain `rm`, truncate to zero, an empty
`denylist: []`, or dropping the `denylist:` key all read as the ruled empty
posture, which is correct behaviour for an absent list and indistinguishable
from a deliberate Captain edit. Only a wrong-SHAPE file (symlink, directory,
corrupt YAML) fails closed.

So today the surface is a **preference channel**: it holds against drift,
mistake, and an officer that is not trying to defeat it. It is not a boundary.
The shipped `.example` and the report both say so, but the Captain asked for
*"guardrails through hooks"*, and this is the hook half.

## The fix, and why it is small

Exactly the treatment `shared/interfaces/captain-vetoes.yml` already gets:
**hook-protected, deliberately NOT schg-locked**. `germline-lock.sh`'s `SKIP=`
array documents the rationale for that class, and it fits this file precisely —
forging it can only DoS (deny more) or drop a denial (advisory loss); it can
never GRANT authority, because there is no allow direction in the format. schg
would be wrong here for the same reason it is wrong there: the Captain must stay
able to edit it without root.

`framework/policies/immutable-core.yml` is the single source, and
`framework/tests/test_germline_lockstep_consistency.py` enforces both
directions — every list atom must map back to an immutable-core entry, and
`hook_protected` entries must NOT appear in the lock lists. So the change is one
enumerated entry plus the two hook lists it requires:

```yaml
# framework/policies/immutable-core.yml, under `hook_protected:`
  - path: instance/config/authority-exceptions.yml
```

then wire:

1. `cabinet/scripts/hooks/pre-tool-use.sh` §5 germline case arm — refuse
   Edit/Write.
2. `cabinet/scripts/hooks/pre-tool-use.sh` §5b `GERM_PATH_RE` — refuse the Bash
   write bypasses (redirect / tee / `sed -i` / `cp` / `mv` / `truncate` / `dd` /
   `python -c`).
3. `framework/policies/base-safety.yml` germline-readonly patterns, if the
   meta-test's class table requires it for `hook_protected` (it requires the
   pair for `files`; confirm against the entry the Captain applies).

`germline-lock.sh` is **not** edited: the path is not schg-locked, and
`test_unlocked_classes_not_in_lock_lists` asserts it must not be.

## Why it was not done in the originating PR

Adding a path to `immutable-core.yml` changes the Ring-0 **set**, not germline
content. Doctrine separates the two: a germline *content* fix is
landed-then-ceremonied by any wave, but the *set* stays byte-identical without a
Captain ruling. The reviewer judged this "free and precedented"; the precedent is
right and the cost estimate is not — it is one entry, two or three list edits, a
lockstep meta-test re-run, both germline hook harnesses re-run, and a Captain
apply window.

## Ceremony cost, honestly

**Zero marginal windows.** It rides the unlock/relock the same deployment already
needs for two other reasons:

1. `cabinet/scripts/policy-shadow.py` must be re-materialised so the exception
   surface exists on the box at all (that file is currently byte-identical to
   master, so it is a pure re-materialise).
2. `cabinet/scripts/hooks/pre-tool-use.sh` on the box **matches no commit in
   history** and is missing `1cbeb14d` *"the emergency stop failed OPEN"* — see
   `docs/authority-matrix-enforcement-dryrun-2026-07-27.md` §6.3. That file has
   to be adjudicated and re-materialised regardless, and this proposal edits the
   same file.

## Acceptance — what to prove before relocking

* `framework/tests/test_germline_lockstep_consistency.py` green, including the
  reverse direction and `test_unlocked_classes_not_in_lock_lists`.
* `cabinet/tests/hook-regression/germline-readonly.sh` and
  `germline-bash-write.sh` green, each with a NEW probe pair for this path:
  Edit/Write BLOCK, and the Bash write bypasses BLOCK.
* `cabinet/tests/hook-regression/captain-exceptions.sh` still PASS=19 FAIL=0 —
  the harness drives a throwaway `CABINET_ROOT`, so hook protection must not
  break the Captain's ability to place a file there.
* A both-directions arm: the Captain (outside the hook) can still write the
  file; an officer tool call cannot.

## What changes in the story once applied

`docs/authority-matrix-enforcement-dryrun-2026-07-27.md` §5.2 and the header of
`instance/config/authority-exceptions.yml.example` both currently state the
preference-channel limitation. Both must be rewritten in the same commit that
applies this, and the claim upgraded to what is then true: an officer tool call
cannot erase the Captain's exclusions, while the Captain still edits the file
with no root and no deploy.
