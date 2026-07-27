# Checkpoint review — fix/bash-egress-fail-closed cp1

Verdict: PASS (after changes-required round 1)
Date: 2026-07-27
Base: master 73c516ba
Reviewer: fresh-context adversarial subagent, own clone, Opus 5
Author: orchestrator session, Opus 5

## What the change does

`framework/authority/classifier.py:_classify_bash` ended in a bare
`return "local_edit"`, so any Bash command it did not positively recognise was
declared a reversible local edit → risk_class `reversible` → `act_with_undo`
in guardian and `auto` in sovereign. The always-gated `external_comms` ceiling
was therefore walkable by shelling out.

The fix inverts the default. A Bash command earns `local_edit` only by passing
`_is_provably_local`; everything else resolves `AMBIGUOUS`, which has no
risk_class and proposes. No new action_type, no matrix change, no new module.

Deliberately NOT a blocklist of sender binaries. The argument is mechanical
rather than stylistic: the shared shell parser has measured gaps where the
command word resolves to something that is not the real binary. Under a
blocklist each gap is a bypass; under a positive-locality proof each gap is a
conservative answer, because the mis-resolved name is simply not a
provably-local binary.

## Round 1 — changes-required

The reviewer defeated the first version with a generic prefix: **20 of the 22
pinned egress commands classified `local_edit` again**, verified end-to-end to
`auto` under sovereign. Four causes, all in the SHARED parser
(`policy_engine.extract_invoked_binaries`), none in the allowlist:

| # | Shape | Why it escaped |
|---|---|---|
| 1 | `2>/tmp/echo sendmail -t` | a leading redirect whose target basename is an allowlisted name became the command word (`_strip_path("2>/tmp/echo") == "echo"`); the real program was never extracted |
| 2 | `ls && bash /tmp/exfil.sh` | shell-without-`-c` returned `[]`, and the concatenation let an allowlisted SIBLING absorb it |
| 3 | `ls\nsendmail -t` | `\n` was not a statement separator — every multi-line command analysed by line 1 only |
| 4 | `PATH=/tmp/evil ls`, `GIT_EXTERNAL_DIFF=/tmp/x git diff` | inline `VAR=VAL` was silently skipped, rebinding what an allowlisted name resolves to |

Plus `git -c core.fsmonitor=/tmp/x status` (`-c` was in the SKIPPED value-flag
set — git's most direct arbitrary-exec vector) and nine git verbs the first
pass kept in violation of its own stated rule (`checkout`/`switch`/`restore`/
`worktree`/`stash` run post-checkout hooks and smudge filters, `add` runs the
clean filter, `grep -O` runs a named program, `config --edit` launches
`$EDITOR`, `help -w` a browser, `tag -s`/`verify-*` gpg).

**The most serious finding was not in the new code at all.** The same two
parser gaps defeat the LIVE-enforcing plane: `binary_block` and
`destructive_rm` are in `policy-shadow.py:_LEGACY_ENFORCING_TYPES` and do
block today, yet on master `2>/tmp/ls sudo rm -rf /tmp/x` and `ls\nrm -rf /`
were both ALLOWED. Pre-existing, and now closed.

## Round 2 — what landed

Parser (`framework/authority/policy_engine.py`):
- `\n` joined the statement separators.
- `_strip_redirections` drops redirect operators and their target words before
  the command word is chosen.
- `UNRESOLVED` sentinel where the parser knows it cannot see the program
  (shell running a script file), so a sibling cannot mask it.
- `ENV_ASSIGNMENT` sentinel for an inline `VAR=VAL` prefix, reported instead
  of skipped. Neither sentinel appears in any blocklist, so `binary_block`'s
  meaning is unchanged — only its coverage.

Classifier: `-c`/`--config-env`/`--exec-path` disqualify a git invocation
outright; nine hook/filter/pager/editor/browser/gpg verbs removed; `hostname`
and `df` removed (their comment claimed "no resolver traffic", which was
false); the membership rule now states the line it actually draws (own
capability in THIS invocation — arbitrary local file writing is the path/
germline plane's job, and treating it as egress here would contradict
`Edit`/`Write` classifying `local_edit` for the same write).

Verification after: 0/16 escapes, 7/7 previously-allowed live-plane forms now
BLOCKED, all pinned as arms.

## Round 1 findings accepted and fixed

- **A false claim in a Captain-facing register.** RES-018 asserted every
  evasion tried was blocked. It was wrong for the second round. Corrected with
  a `Note:` field recording the second round and the live-plane finding.
- **A vacuous sensor, in the session that lists sensor-vacuity as the dominant
  defect class.** `test_ceiling_risk_classes_is_derived_not_relisted` asserted
  set equality; master's hand-written frozenset has the identical six members,
  so it passed on both trees and could not see the property its own name
  claims. Rewritten as an AST check on the assignment's right-hand side —
  verified to FAIL against master's source.

## Round 1 findings judged and NOT actioned

- `cp`/`tee`/`ln`/`chmod`/`mv` can plant a launch agent or a git hook. Kept,
  with the membership rule sharpened to say why: this predicate is about reach
  from THIS command. Removing them while `Edit`/`Write` classify `local_edit`
  for the identical write would be incoherent, and arbitrary local write is
  governed by the path_block/germline policies and the sandbox write denies.
- Repo-config exec vectors (`core.pager`, `diff.external` via a committed
  `.git/config`) remain reachable for the kept read-only git verbs. Command-line
  injection is closed (`-c` disqualifies); config-in-a-hostile-checkout is
  named in RES-018 rather than papered over.

## Batteries (measured this session, serially, `__pycache__` purged)

| Gate | Master baseline | This branch |
|---|---|---|
| `pytest framework/ -q` | 1 failed / 6821 passed | 1 failed / **6954 passed** |
| `pytest cabinet/scripts/tests -q` | 4781 passed, 28 skipped | **4785 passed**, 28 skipped |
| task_adapters + world-aesthetic | — | 125 passed, 5 skipped |
| `check-layer-separation.sh` | — | OK, new=0 |
| `cog2-import-gate.py` | — | OK |
| `ledger-status-parity.sh` (A13) | — | GREEN, ids=353 md_rows=353 |
| `docs-track-code-sweep.sh` | — | GREEN, findings=0 |
| `run-golden-evals.sh` | — | **32/32 PASS** |
| `cognitive-architecture-census.py` | 69129 <= 69129 | 69315 <= 69315 (+186 allowance) |
| germline set hash | c8eb327c… (73 entries) | c8eb327c… **unchanged** |

The single framework failure is pre-existing on master:
`framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`
(`claude-sonnet-5` vs `claude-sonnet-4-6`).

## Non-vacuity

Every new arm was checked against a clean master clone. The 24 round-1 egress
arms, the parser-gap arms, the `/dev/tcp` arms, the git-verb arms, both grants
fence arms and the rewritten derivation sensor all FAIL on master. The
negative controls (`test_ordinary_local_work_still_classifies_local`,
`test_second_round_did_not_over_reject`, `test_benign_commands_still_pass`,
`test_every_ceiling_class_default_row_is_legal`) pass on both by design — they
exist to stop a rule that rejects everything from passing the positive arms.
`TestLiveOrganDescriptorsAreEnumBound` carries a `>= 6` floor and two mutation
arms, and was proven to RED against a mutated real manifest.

## Assertions changed — judged not weakenings

- `test_localhost_curl_mutations_stay_local_edit` → renamed
  `..._do_not_hit_the_network_ceiling`: keeps the original no-escalation
  property AND adds `== AMBIGUOUS`. Two assertions where there was one, and a
  strictly stricter runtime posture (was `auto` in sovereign).
- `npm test` moved out of the `local_edit` row into its own AMBIGUOUS arm.
  `npm test` runs whatever package.json says; `local_edit` was a comfortable
  falsehood.
- Fixture kinds `external_teams`/`vendor_payment`/`deploy_prod`/`pay_invoice`
  replaced with real enum members of the same risk class. These strings appear
  nowhere in production code; each replacement stays inside its class, so
  every property under test survives.

## Residual

RES-018 in `docs/plans/declared-residuals-register.md`. In short: this is a
CLASSIFICATION, not containment. The authority matrix is still shadow-consumed;
the Seatbelt profile is `(allow default)` with no `appleevent-send` deny, so an
`osascript` Mail/Messages send stays executable at full egress enforcement even
while it classifies propose-only here; and only Bash calls reaching this gate
are seen.

## Handback

`framework/authority/classifier.py`, `framework/authority/policy_engine.py`
and `framework/authority/grants.py` are germline (schg). Landed-then-ceremonied:
the germline SET is byte-identical (hash above), and one Captain unlock/relock
window is needed to re-materialize the landed bytes on the live machine.
