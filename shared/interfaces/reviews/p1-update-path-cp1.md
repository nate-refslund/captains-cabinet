# Review checkpoint 1 — feat/p1-update-path (phase-1 unit U5, the update path)

Contract of record: `phase1-contracts-v2-2026-09-07.md` §5 plus amendments
A5.1–A5.13, A0.5, A0.7. Arms A (Fable 5.1) §5 and B (Opus 5) §5 are normative
where the adjudication cites them.

## What this checkpoint contains

The producer (`egg-export.sh --bundle`, `cabinet-update.sh publish`), the
consumer (`cabinet-update.sh status|apply|rollback` over
`lib/update_bundle.py`), the web door (`lib/updates.ts`, `actions/updates.ts`,
`components/updates/update-card.tsx`, the home card), the briefing line, the
three ledger receipts, and the sensor suite.

## The four decisions that carry the most weight, and the reason for each

1. **Deletions are manifest-to-manifest, never bundle-versus-installed**
   (A5.1). A bundle contains no `instance/` path at all — the export manifest
   deletes 29 of them — so diffing what the bundle has against what the install
   has would mark the operator's entire instance tree for deletion. A first
   apply therefore deletes nothing, which is the only honest answer available
   with no previous manifest to compare against.
2. **The locked set is parsed from the INSTALLED boundary script** (A5.4), with
   `DIRS` matching by prefix because the lock is applied recursively. A bundle
   that named its own boundary could widen it. Unparseable or absent ⇒ refuse:
   an empty locked set read as "nothing is locked" is the fail-open this whole
   path exists to avoid.
3. **The preserve set is declared data with ONE authoring source** (A5.2). The
   export manifest deletes ITSELF from the egg, so the set is derived at cut
   time into `cabinet/config/egg-preserve-set.txt` and read at run time. A
   bundle that ships a preserved path is reported as `skipped_preserved`, never
   silently dropped: an operator whose live veto ledger was not overwritten
   deserves to be told so.
4. **The health gate is not an identity probe** (A5.5). It requires the
   answering process to carry the new build's commit AND to have started after
   the apply began, because "something answered as the dashboard" passes for an
   old process that survived a failed restart. `cabinet-doctor` is reported,
   never gated — a single-worker install is legitimately dead on fleet services
   and a doctor gate would roll back every good update.

## Where this checkpoint chose, because the contract was silent

- **Snapshot of the previous `.next`** lives beside the snapshot rather than
  inside it: it is a local build artifact the export manifest deletes, not
  shipped content, so it has no place in a tree of shipped pre-images.
- **The gate's receipts leg** is the emitter replay, not a `receipts --json`
  CLI: that CLI is phase-1 unit 1's deliverable and does not exist yet. The
  command is overridable by a named seam, and a sensor pins what the default
  is so the seam cannot quietly become the behaviour.
- **The briefing line reads the updater's files, not its CLI** — a briefing
  pass that can hang on a subprocess is a briefing that can fail to arrive.
- **Both home-page render branches** carry the card; a consumer-mode operator
  is exactly the one who will never open a terminal.

## Defects found and fixed in the salvaged work

- `${VAR:-default}` with a brace inside the default: bash ends the expansion at
  the first unescaped `}`, so the gate's receipts command leaked `, sys.stdout)"}`
  as literal text — and did so **even when the variable was set**. Every apply
  rolled itself back with an unreadable syntax error. Rewritten as explicit ifs.
- The kill seam killed only the helper, so the shell rolled back and the tree
  never reached the interrupted state the resume path exists for. It now models
  the updater DYING, which is the event that leaves nobody to roll anything back.

## Verification

Red-before/green-after for every sensor, the full local battery, and the
pre-existing failing-set identity proof are on the pull request. Locked-set
check over `git diff --name-only origin/master...HEAD` plus the working tree:
zero hits.

## Checkpoint 2 — the evidence pass (2026-09-07)

One real defect surfaced when the battery ran whole, and it was not in the
update path: `framework/triggers/tests/test_schema_registry.py::test_m4_central_enum_untouched`
pinned `len(VALID_EVENT_TYPES) == 91` beside the assertion that actually
carries M4 — that a schema resolve leaves the enum byte-identical. Registering
the three update receipts moved the enum to 94 through the expansion registry,
a route the schema registry cannot reach, and the size literal could not tell
that apart from the failure M4 exists to catch. The literal is gone; the
identity assertion is the whole test and was proved still armed by injecting a
rebind of `emitter.VALID_EVENT_TYPES` into `schema_registry.resolve`. The
count ceiling keeps its own sensor — the census.

That fix had a second-order cost worth recording: the first rewrite of the
production docstring added ONE non-comment line, which put
`framework_production_noncomment_lines` at 79446 against a 79445 maximum and
turned 31 tests plus 14 errors red across every census-dependent suite. The
docstring was reworded to the same line count. A one-line docstring is a
budget event here.

Every invariant of §5 was additionally proved red by MUTATION, not only by
module-absence:

| Invariant | Mutation | Sensor's red |
|---|---|---|
| A5.2 preserve set | `build_plan` no longer skips preserved paths | the veto row came back `vetoes: []` |
| A5.1 deletion set | deletions computed bundle-vs-installed | first apply deleted 17 paths |
| A5.5/A5.6 gate | rollback-on-red replaced by a log line | apply exited 0 on a red gate |
| A5.7 lock | `flock` call removed | the second updater exited 0 instead of busy |
| A5.9 web guard | `verifySession` swapped for `requireDashboardAuth` | no-auth posture returned `{ok: true}` |

Two inverted arms ship inside the suite itself rather than as one-off
mutations, because they guard controls whose absence is otherwise invisible:
`test_a_locked_check_stripped_from_the_script_lets_the_bundle_through` and
`test_without_the_re_exec_the_group_kill_takes_the_updater_with_it`.
