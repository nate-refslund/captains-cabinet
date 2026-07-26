# feat/state-persistence-preflight — checkpoint 3 (landing)

Landing checkpoint: the merge of current `origin/master` into the approved
branch, plus the two fixes the branch's own CI and the merge made necessary.
`state-persistence-preflight.py`, `cabinet-deploy.sh` and `restore-drill.sh`
are byte-identical to the reviewed tree; `runtime-provision.sh` changes in one
place only (the prune mtime probe, below), and the approved ADOPTION INVARIANT
and its helpers are untouched.

**Both changes here are things CI proved, not opinions.** The branch had never
been through a green CI run — PR #201's only run (`30183105928`) was red on two
jobs, and both reds are fixed here.

## Review status carried in

* cp1 (`968eb5cf`..`5b352c75`) was **blocked** by an independent adversarial
  review — three defects, all reproduced.
* cp2 (`52f4f820`) fixed them; `b3bcf812` closed a hole cp2's own self-review
  found in its `ADOPTION INVARIANT` (a failed `cp` was swallowed, then the
  caller `rm -rf`'d the only copy).
* The **same reviewer that blocked it** re-reviewed `b3bcf812` on its own
  rebuilt harness and returned **`VERDICT: approve`** — 13/13 durable paths
  `SURVIVES -> shared/` with `LOST_COUNT=0` in all three scenarios (first
  deploy after landing, same-sha redeploy, and shared/ pre-populated then
  redeploy), against 9-11 lost and 4 destroyed in place before.
* One bounded residual was **filed and deliberately not applied**, so that the
  bytes reviewed are the bytes that land: the invariant permits destroying
  *newer* bytes if a mid-run FATAL aborts a provision, the cabinet keeps
  appending to an already-adopted file, and the operator re-runs — because
  `[ -e "$shared_abs/$sub" ] && continue` makes `shared/` win unconditionally.
  Loss is bounded to that interval, is preceded by a loud FATAL, and is
  strictly better than master. The minimal fix (a `cmp -s` fail-closed abort)
  is filed for a follow-up.

## The merge

`origin/master` `566632df` merged in with **no textual conflict**. The two file
sets are disjoint — verified by `comm -12` over both name-only diffs against
the merge-base, empty output.

**One semantic interaction, which is the gate doing its job.** Master's
PR #200 (the E-stop fail-closed work) added `instance/config/estop` to
`.gitignore`. This branch's preflight *derives* its durable set from
`.gitignore`, so the merged tree had exactly one unaccounted durable
candidate — drift detected within hours of the path being created, which is
the whole point of deriving instead of hand-maintaining a fourth list:

```
state-persistence-preflight: DEPLOY WOULD LOSE STATE
  instance/config/estop   (.gitignore:305)
      on NO persistence list and NO policy entry
```

## The design call: `disposable`, and carrying it would be a BUG

Not a judgement call about convenience — carrying this path would brick the
fleet. Measured, not read:

| marker path is | `_ks_marker_verdict` |
|---|---|
| absent | `CLEAR` |
| a **symlink** | `INDETERMINATE` — "stop marker present but not a regular file" |

`killswitch-read.sh` treats existence in ANY form as not-CLEAR, and
INDETERMINATE halts exactly like ACTIVE. So a persistence symlink at
`instance/config/estop` would arm the emergency stop **permanently** on every
release. Worse, it would be unclearable through the normal verb:
`kill-switch.sh deactivate` runs `rm -f "$ESTOP_MARKER"` (`:117`), which
removes the *link* and leaves the `shared/` copy — verified — so the next
provision recreates the halt.

Nothing durable is lost by not carrying it. The authoritative channel is the
Redis key `cabinet:killswitch`; the verdict is the OR of the two channels; and
`activate` does not write this marker at all today (declared residual RES-016).

The residual is written into the policy row rather than hidden: once RES-016
arms the marker, a deploy drops the filesystem channel for the incoming
release, so inside that window the pre-armed `DEL` loop the second channel
exists to defeat wins again. The fix for that is a re-arm step at provision
time driven by the Redis verdict — **never** a symlink into `shared/`.

Verified this path is genuinely not carried by any class: `instance/config` is
in none of `INSTANCE_PERSISTENT_DIRS` / `SEEDED_DIRS` (it is carried file by
file), so no adoption pass and no wildcard block reaches the marker.

That residual is registered, not just narrated: **RES-017** in
`docs/plans/declared-residuals-register.md`, with the provision-time re-arm as
its retirement condition. The house guard
(`test_declared_residuals_register.py::test_every_discovered_marker_is_registered`)
caught the unregistered declaration and is the reason the row exists — the
alternative, rewording the policy text to dodge the marker sweep, is the same
"switch the alarm off" move that blocked cp1.

## CI red #2: prune exits 1 on Linux — the platform-lie class

`test_prune_handles_a_runtime_root_containing_a_space` passes on macOS and
failed in CI. `-f` is BSD `stat`'s FORMAT flag and GNU `stat`'s FILE SYSTEM
flag, so a BSD-first probe does not fail over on Linux the way an unknown flag
would: it takes the GNU branch carrying directives that mean nothing there, GNU
refuses, and under `set -euo pipefail` that status propagates out of the
pipeline and kills the command. `prune` exited 1 having pruned nothing.

The comment the branch shipped claimed this failed open with `sorted` empty.
The measured behaviour is a non-zero exit — corrected in place, because a
wrong reassurance in a comment is worse than none.

Fixed GNU-first with a BSD fallback, and a candidate whose mtime cannot be read
at all is DROPPED rather than defaulted into the ordering: prune keeping too
much costs disk, prune deleting the wrong release is unrecoverable. macOS
behaviour is unchanged (BSD `stat -c` exits 1 on the illegal option, so the
`-f` branch answers exactly as before — verified locally).

New arm `test_prune_orders_by_mtime_on_a_gnu_stat_platform` puts a
coreutils-shaped `stat` first on PATH, so the Linux-only failure now reproduces
on any host. **Non-vacuity proven**: against the BSD-first line it fails with
`returncode=1` — byte-for-byte the CI symptom — and passes against the fix.

## Gates

Committed-tree gates, recorded before and after the merge:

| gate | master `566632df` | merged tree |
|---|---|---|
| `verify-cognitive-phase0` | 1 | 1 |
| `verify-cognitive-phase1` | 1 | 1 |
| `verify-cognitive-phase2` | 1 | 1 |
| `verify-cognitive-phase3` | 1 | 1 |
| **`verify-cognitive-phase4`** | **0** | **0** |

phase0..3 are the pre-existing block on master and are unmoved — phase0, 2 and
3 byte-identical, phase1 differing only in its HEAD-derived digest line.
**phase4 stays green**, differing only in test timings, same pass counts.

Preflight: 93 derived candidates, 58 carried, 4 wildcard-linked, 29 disposable,
**0 unaccounted, exit 0**. `test_state_persistence_preflight.py` 41/41 (40 + the
new GNU-stat arm). `test_declared_residuals_register.py` 9/9. No existing test
was edited, weakened, skipped or deleted anywhere in this checkpoint.
