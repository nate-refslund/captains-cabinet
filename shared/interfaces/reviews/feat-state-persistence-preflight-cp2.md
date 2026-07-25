# feat/state-persistence-preflight — checkpoint 2

Landing the fixes for the three defects an independent adversarial review found
against cp1. Each was reproduced end-to-end against a real runtime root before
being fixed, and re-measured after.

## What cp1 got wrong

cp1 added the durable paths to the persistence lists and added an adoption pass
to make listing a path actually carry it — but wired that adoption into the
`INSTANCE_PERSISTENT_FILES` loop **only**. The other two directory classes, and
the wildcard blocks, kept the original behaviour: seed an empty `shared/`
directory from the new slot's tracked skeleton, symlink the new release at it,
and leave the real data in the outgoing release. So cp1 relabelled nine paths as
covered without carrying them, which switched the alarm off rather than fixing
the loss.

Measured on a real runtime root with realistic accumulated state, cp1:

* lost **11 of 13** durable paths on a normal deploy, at **exit 0**, printing
  `OK — no durable path would be lost`;
* **destroyed 4 directories in place** on a same-sha redeploy — `provision`
  reuses a slot by sha, so `rm -rf "$slot/$rel"` ran against the LIVE release;
* lost `captain-decisions.md` and `captain-patterns.md` — the append-only
  Captain-law ledgers — while the policy counted them as `wildcard-linked`.

The root cause of all three is one wrong property: `check_slot` asked *"does the
NEW slot's path resolve into shared/?"* and treated absence as safe. Absence in
the new slot is the exact signature of the bug. Until the checker inspects the
**outgoing** release it cannot answer its own question.

## The fix

**`runtime-provision.sh` — adoption on every class, with a stated invariant.**
Two helpers, `_adopt_untracked` and `_seed_tracked`. Before any
`rm -rf "$slot/$rel"`, every untracked file beneath it has been copied into
`shared/` (or an identically-named file was already there); tracked files are
recoverable from git. That invariant makes the removal provably non-destructive,
which is why `_adopt_untracked` runs on the slot as well as on the outgoing
release — the slot is the thing being deleted, so it is the thing that must be
proven safe to delete. Copies never overwrite an existing `shared/` file, so the
pass is idempotent. Only untracked files are adopted, so a frozen snapshot can
never shadow a release's own tracked copy. Adoption runs BEFORE the skeleton seed
so real accumulated data beats a `.gitkeep`. All three discovery-only wildcard
blocks (`*.md`, `*-ceo.md`, `.oauth-backup-*.json`) now seed themselves from the
outgoing release first.

**`state-persistence-preflight.py` — the arm that asks the real question.**
`check_outgoing()` walks the live release for untracked (i.e. runtime-created)
content and fails on anything unreachable from the new slot. Wildcard units are
deliberately exempt from the whole-path `check_slot` and checked only per-file:
`instance/agents` and `shared/interfaces` are ordinary tracked directories
carried file by file, so the directory itself correctly stays real. `import yaml`
is guarded, because a missing dependency was surfacing as
`would DISCARD durable state`. `known_gap` expiry stays blocking in CI and
becomes loud-but-non-blocking at deploy time — `cabinet-deploy.sh` aborts on any
non-zero exit, so a blocking expiry made every `expires:` date a scheduled
hard-stop of the entire deploy path, over a deferral that says nothing about
whether *this* deploy loses state. Untracked-and-unignored residue is scanned and
reported, and the OK headline now states its scope instead of overclaiming.

**`cabinet-deploy.sh` — ordering.** The deploy is invoked as
`<runtime_root>/current/cabinet/scripts/cabinet-deploy.sh`, so `$PROVISION` is
the OUTGOING release's copy and cannot know about a persistence path the NEW
release added. The deploy now re-runs the linking pass from the new slot's own
`runtime-provision.sh` before the preflight — the same "read the new slot, not
the running one" discipline already applied to the health gate, `roster_officers`
and the preflight. Exit 2 (`CANNOT VERIFY`) is now reported distinctly from
exit 1 (state loss).

**Ordering decision:** `provision` stays before the preflight. The preflight
needs a provisioned slot to assert against, and — as the review said — a gate
downstream of the damage cannot protect against it even in principle. The
correct fix is therefore to make `provision` itself non-destructive, which the
adoption invariant does, rather than to reorder around a destructive step.

**Also:** `prune`'s `awk '{print $2}'` truncated any runtime root containing a
space and handed the truncated prefix to `rm -rf`; replaced with a leading-field
strip. No prune rewrite — the `stat -f` GNU fail-open is byte-identical to master
and out of scope.

## Evidence

13-path survival table, real runtime root, both scenarios (normal deploy and
same-sha redeploy): **13/13 survive, resolving into `shared/`, preflight exit 0**
— against 11/13 lost and 4 destroyed before.

12 new test arms. 11 fail against branch head `5b352c75` and pass after; the 12th
is an intentional always-pass control for the PyYAML arm. The weak pin
`test_real_repo_carries_the_paths_this_bug_was_about` now asserts the PARSED
lists — verified to fail when a path is dropped from the list while its comment
is left behind, which the old substring form allowed.

No existing test was edited, weakened or deleted.
