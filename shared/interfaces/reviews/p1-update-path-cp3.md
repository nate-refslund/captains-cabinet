# p1-update-path — checkpoint 3: the round-2 review, answered

Branch `feat/p1-update-path`. Reviewer verdict: **reject**, at
`59cc7be68d5532ed58828e8aa7ee9111b62dbd6d`, on one blocking defect, two
must-fixes and five notes. All eight are addressed below; every one carries the
sensor that would have caught it, shown red before the change and green after.

---

## 1. BLOCKING — the health gate rolled back every framework-only update

**What was true.** `/api/health`'s `source_commit` was inlined by `next build`
(`next.config.ts` `env`). The updater rebuilds the dashboard only when the plan
touches `cabinet/dashboard/**`, and `start-dashboard.sh` rebuilds only when
`.next` is absent. So a bundle that changed no dashboard file restarted the
same build, the build answered with the OLD commit, and the gate's
`stamp == to_sha` leg went red — automatic rollback, tree reverted, one
`cabinet_update_rolled_back` receipt. Phase-1 units 1–4 are framework-only, so
that is the majority bundle shape: the unit's whole purpose failed for it.

**The adjudication.** The contract is internally inconsistent here — §5 says
"rebuild iff `cabinet/dashboard/**` changed" and A5.5 says "stamp == to_sha".
Two ways out:

| | cost |
|---|---|
| rebuild on every apply where `to_sha != from_sha` | a 1–2 minute `next build` on every framework-only update, and an update that fails outright on a box with no node toolchain — for a build whose inputs did not change |
| separate the two facts the one field was carrying | one more field on an endpoint that already exists |

Taken: the second, which is the reviewer's own alternative ("make the swap
itself write the stamp artifact the route reads, keeping `started_at` as the
anti-stale-process leg"), in the form that needs no artifact. A5.5's *named*
property — "an identity-only probe passes an old process that survived a failed
restart" — is preserved in full; §5's rebuild condition is preserved unchanged.

**What the endpoint now answers, and why each field exists:**

| Field | Question | Source | Gated |
|---|---|---|---|
| `source_commit` | which Cabinet is this? | the process's environment, read at REQUEST time; `start-dashboard.sh` resolves it from `egg-manifest.json`, which apply rewrites before it restarts | always |
| `build_commit` | which build is serving? | inlined by `next build` | only when this apply rebuilt |
| `started_at` | did it actually restart? | `process.uptime()`, so it is the process's start and not the moment the route module happened to load | always |

An old process that survived a failed restart cannot answer with the new
`source_commit`: its environment was fixed when it started and nothing can
reach into a running process to change it. That is the leg A5.5 asked for.

**Two further corrections inside the same leg**, both found while writing it:

* `started_at` was a module-scope `new Date()`. A route module in a Next
  production server is loaded on the FIRST REQUEST that reaches it — possibly
  after the update that was supposed to restart the process. Now derived from
  `process.uptime()`.
* the start-time comparison was a STRING comparison. The dashboard answers with
  milliseconds and the updater's clock reading does not, so `...T12:00:00.123Z`
  sorts before `...T12:00:00Z` and a restart in the same second as the apply
  began read as a process that predates it — a good update rolled back on a
  lexicographic accident. Both sides are now parsed to seconds.

**Proof, on the real artifact** (not only the fixture):

```
built  CABINET_BUILD_SOURCE_COMMIT=deadbeef…  npm run build
served CABINET_SOURCE_COMMIT=cafebabe…        npx next start
GET /api/health -> {"source_commit":"cafebabe…","build_commit":"deadbeef…", …}
```

and the gate's own check, extracted from `cabinet-update.sh` and run against
that live endpoint:

```
rebuilt=0  rc=0                                        <- the framework-only apply is GREEN
rebuilt=1  rc=1  the answering build is deadbeefdead, expected cafebabecafe
wrong sha  rc=1  the cabinet answering is cafebabecafe, expected bbbbbbbbbbbb
predates   rc=1  the answering process predates this update
```

---

## 2. MUST-FIX — no sensor exercised the dashboard leg

Every arm passed `--skip-restart`, which makes the leg log THIN and return;
`test_health_gate_defaults_are_the_contract_legs` is a grep of the script. The
one gate leg with an automatic rollback behind it had no executing arm in
either direction, which is exactly how the defect above shipped.

Seven arms now run it end to end against a served endpoint through the
`CABINET_UPDATE_HEALTH_URL` seam:

| Arm | Asserts |
|---|---|
| `test_a_bundle_that_changes_no_dashboard_file_still_passes_the_gate` | the blocking defect, as an arm: applied, not rolled back |
| `test_a_dashboard_that_never_restarted_reds_the_gate` | the old process is caught |
| `test_a_process_that_predates_the_apply_reds_the_gate` | the start-time leg alone |
| `test_something_else_on_the_port_is_never_this_cabinet` | the identity marker |
| `test_a_rebuilt_dashboard_must_serve_the_build_it_was_given` | a rebuild that produced the old bytes is red |
| `test_a_dashboard_bundle_that_builds_and_serves_its_own_bytes_is_green` | its green twin, plus A5.6's `.next` snapshot and its restore on rollback |
| `test_the_gate_says_which_legs_it_ran` | a THIN leg says so in the log |

**Why the stub is honest.** A fixture install has no Next.js, so these arms run
a ~30-line HTTP stub — but the stub does not hardcode the body.
`health_field_sources()` reads the field → environment-variable mapping OUT OF
THE LIVE ROUTE FILE and the stub answers from that, so a route that goes back
to answering its identity from the baked build variable makes these arms red
with nobody editing them. The restart is modelled by a fixture
`lib/dashboard.sh` that re-reads `egg-manifest.json` exactly as
`start-dashboard.sh` does, and the stub freezes its values at ITS start — which
is what a running server is.

A second, cheaper sensor pins the same property without a server:
`test_the_health_identity_field_is_not_baked_into_the_build` reads
`next.config.ts`'s inlined set and the route's env reads and asserts the
identity field is not in the inlined set while the build stamp is.

---

## 3. MUST-FIX — A5.14: the staged tree outlived a failed apply

`rm -rf $STAGE/$sha` ran only on the green and no-change paths. A rolled-back
apply left the whole unpacked export in `.updates/stage/<sha>/` for ever, and
refusals (digest mismatch, unreadable plan, a locked path — all of which unpack
first) left one too. With the blocking defect in place, rollback was the normal
outcome, so this compounded.

Now: `drop_stage <sha>` on the rollback path, on every refusal, and on the green
and no-change paths, and `prune_stage` bounds whatever else is lying around
under the same `CABINET_UPDATE_KEEP` policy as the snapshots. Three arms:
`test_the_stage_tree_does_not_outlive_a_rolled_back_apply`,
`test_a_refused_bundle_leaves_no_unpacked_tree_behind`,
`test_the_stage_is_bounded_by_the_keep_policy`.

---

## 4. NOTE — a locked path could be downgraded to a skip

`build_plan` filtered preserved paths before computing `locked_hits`, and two
locked FILES are also in the generated preserve set
(`instance/config/egress.yml`, `instance/config/act-first-surfaces.yml`). A
bundle shipping a changed copy of either was reported as `skipped_preserved`
while the rest of it applied. Nothing was written either way — the fail-closed
property held — but the whole-bundle constitutional refusal §5 requires was
lost.

The plan now computes the RAW changed and deleted sets, takes `locked_hits`
over those, and only then applies the preserve filter. Locked beats preserved,
in that order, stated in the code.
`test_a_locked_path_that_is_also_preserved_is_still_a_refusal`.

One deliberate consequence: `skipped_preserved` now reports preserved paths
whose content actually DIFFERS, rather than every preserved path the bundle
happens to carry. A5.2 says "shipped changes to preserved paths are REPORTED",
and a report that fires for an identical file is noise.

---

## 5. NOTE — `built_at` never reached the card

It travelled from the manifest into `lib/updates.ts` and into the
`cabinet_update_applied` payload, and the card rendered `owner` and `mtime`
only. A5.11 wants all three: the inbox is same-uid writable, so "where did this
come from, and is it newer than what I am running" must be answerable before
tapping Apply. Rendered now, with `update-card.test.tsx` — three arms, including
the degenerate one (a manifest with no `built_at` says so rather than showing a
blank).

---

## 6. NOTE — `runtime-provision.sh lists` had no production consumer

`parse_provision_lists` re-parsed the `INSTANCE_PERSISTENT_*` assignments out of
the script text, so one declaration had two readers and the subcommand's only
caller was a test — the drift shape the amendment set out to remove. The
updater now RUNS `bash runtime-provision.sh lists` and parses its records; the
text parse is the documented fallback for an install whose script will not run
here, and an unreadable declaration still raises rather than reading as an
empty preserve set.
`test_the_preserve_set_reads_the_lists_subcommand_not_the_script_text`
(a fixture script whose printed lists and whose assignments disagree on
purpose) and `test_an_unrunnable_provision_script_falls_back_to_its_declaration`.

---

## 7. NOTE — the runbook stated the rebuild unconditionally

`docs/runbooks/cabinet-update.md` said apply always rebuilds. That sentence is
the one that hid the blocking defect. It now states the rebuild CONDITION and
the build-stamp leg's condition together, in one place, with the reason they
must move together.

---

## 8. NOTE — the in-function busy branches looked like dead code

`cmd_apply`'s and `cmd_rollback`'s own `take_lock || refuse_busy` are
unreachable behind the dispatch's lock — the reviewer found it by mutating one
and watching its sensor stay green. They are NOT dead: the dispatch skips
locking when `CABINET_UPDATE_REEXEC=1`, which is how the re-exec'd copy arrives
and what a caller that sets the variable by hand gets. Deleting them would
leave that entry point unlocked. Kept, with the reason in line, and given an
arm: `test_a_re_execed_updater_takes_the_lock_for_itself` — red when the branch
is mutated away (`0 == 4`, and the update applied under a held lock).

---

## Red-before-green, per sensor

| Sensor | Red on | Failure text |
|---|---|---|
| `test_the_health_identity_field_is_not_baked_into_the_build` | 59cc7be6 | `answers source_commit from CABINET_BUILD_SOURCE_COMMIT, which next.config.ts bakes in at BUILD time` |
| `test_the_health_start_time_is_the_process_start_not_a_module_load` | 59cc7be6 | `started_at must be derived from process.uptime()` |
| `test_a_bundle_that_changes_no_dashboard_file_still_passes_the_gate` | 59cc7be6 | rc 1, `the health gate was red — rolling back automatically` |
| `test_a_process_that_predates_the_apply_reds_the_gate` | 59cc7be6 | red for the identity reason instead of the time reason |
| `test_a_rebuilt_dashboard_must_serve_the_build_it_was_given` + green twin | 59cc7be6 | `the build failed` (no seam), then `the answering build is …` |
| `test_the_gate_says_which_legs_it_ran` | 59cc7be6 | no `build stamp leg THIN` line exists |
| `test_a_dashboard_that_never_restarted_reds_the_gate` | mutation: the leg answers on `service` alone | `assert 0 == 1` — the update applied over a dashboard that never restarted |
| `test_something_else_on_the_port_is_never_this_cabinet` | mutation: `if False:` on the marker check | `assert 0 == 1` |
| `test_the_stage_tree_does_not_outlive_a_rolled_back_apply` | 59cc7be6 | `['bbbb…']` still in `.updates/stage` |
| `test_a_refused_bundle_leaves_no_unpacked_tree_behind` | 59cc7be6 | `['bbbb…']` |
| `test_the_stage_is_bounded_by_the_keep_policy` | 59cc7be6 | six trees survived |
| `test_a_locked_path_that_is_also_preserved_is_still_a_refusal` | 59cc7be6 | rc 0 — the bundle applied and the locked change was reported as a skip |
| ” | mutation: `is_locked(...) and not is_preserved(...)` | rc 0 again |
| `test_the_preserve_set_reads_the_lists_subcommand_not_the_script_text` | 59cc7be6 | `the updater read the script's TEXT, not its lists subcommand` |
| `test_an_unrunnable_provision_script_falls_back_to_its_declaration` | mutation: the fallback dropped | `an unrunnable script read as an empty list` |
| `test_a_re_execed_updater_takes_the_lock_for_itself` | mutation: the in-function branch removed | `assert 0 == 4` |
| `update-card.test.tsx` | 59cc7be6 | `expected … to contain '2026-09-07T11:22:33Z'` |
| `pwa.test.ts` (key set + request-time identity) | 59cc7be6 | `expected [ 'ok', 'service', …(3) ] to deeply equal [ 'build_commit', … ]` |

## What this change does NOT prove

* The fixture arms model a dashboard; the REAL composition is proved by the
  probe above (real `next build`, real `next start`, the gate's own check code
  against that live endpoint) rather than by a test in the suite. A full
  end-to-end apply against a real Next build on a real install is still the
  drill's job (P7), not this suite's.
* `--skip-rebuild` on a bundle that DID change dashboard files still applies
  with a stale build serving. It logs THIN and the build-stamp leg is not
  armed, because nothing was rebuilt. That is the flag's stated meaning; it is
  not a green the gate earned.
