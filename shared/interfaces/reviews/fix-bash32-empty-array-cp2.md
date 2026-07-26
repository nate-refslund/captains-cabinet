# Checkpoint review — fix/bash32-empty-array cp2 (FW-019)

**Scope:** the review-blocking defect only. The bash-3.2 shell fix itself
(`cabinet/scripts/lib/officer-env.sh`, `cabinet/scripts/bootstrap-roles.sh`)
is untouched by this checkpoint and was not challenged.

**Files:** `framework/tests/test_bash32_empty_array_ratchet.py`,
`cabinet/scripts/lib/tests/test_bash32_empty_array.py`. No production shell,
no thresholds, no allowlist entries added; nothing deleted or relaxed.

---

## The defect, reproduced before it was fixed

Both new test modules listed files with `git ls-files` under `check=True`.
A delivered egg has no `.git` — `null-hatch.sh` exports with
`git archive HEAD | tar -x` and falls back to a `--exclude='./.git'` tree
copy — so git exits 128 and the test hard-errors with `CalledProcessError`.

Measured on this host (`/bin/bash` 3.2.57, macOS 26.6, python3.12):

| command | origin/master `9673867f` | branch `d77cc091` |
|---|---|---|
| `bash cabinet/scripts/null-hatch.sh` | **exit 0** | **exit 1** |
| its stage 4/4 pytest | 1105 passed / 2 skipped | 1 failed, 1114 passed, 2 skipped |

Sole failure: `test_no_unguarded_empty_array_expansion_in_tracked_shell`,
`CalledProcessError ... 'ls-files' ... exit status 128`. That command is hatch
step proof-a, the `null-hatch` CI job, and the suite a stranger runs on the
unpacked egg.

Second module, same class, in a `git archive HEAD` export:
`1 failed, 5 passed`, failing arm
`test_officer_boot_command_assembles_under_bin_bash` — the arm that proves an
officer can boot.

## A second hole found while fixing the first

`git ls-files` does not only fail loudly. Unpack a gitless egg **inside another
checkout** and it *succeeds*, listing the outer repo's tracked files under this
directory — i.e. none, exit 0. Probed directly:

```
$ git -C <outer-repo>/egg ls-files            # egg is untracked in the outer repo
                                              # -> empty, exit 0
$ git -C <outer-repo>/egg rev-parse --show-toplevel
<outer-repo>
```

The ratchet would then scan **zero files and report a clean tree**. A silently
empty sensor is worse than a loud failure, so both listings now compare
`rev-parse --show-toplevel` against the root before trusting a git answer, and
the ratchet asserts three anchor files are in its corpus so a vacuous pass
cannot present itself as green.

## The remedy

Git-tracked listing where git can authoritatively answer for the root;
filesystem walk otherwise. One shared `_is_shell_file` predicate so the two
modes cannot drift apart. `_WALK_PRUNE` drops VCS/vendor/cache/build dir names
on the walk path only — a stranger's egg is a working directory, and `npm
install` under any of the three tracked `package.json` trees would otherwise
push thousands of vendored shell scripts into the scan and turn a green gate
red on third-party source.

Verified 2026-07-26 that **no tracked file lives under any pruned name**
(`git ls-files | awk -F/ ...` → empty), so the prune costs zero coverage today,
and `test_the_two_listings_agree_file_for_file` goes red the day that changes.

## Evidence

* **Counts match across modes:** git mode 298 files, walk mode 298 files, set
  difference empty in both directions — the reviewer's own measurement,
  reproduced.
* **Teeth preserved in walk mode**, in a real gitless `git archive` export:
  * reverting the actual `officer-env.sh` repair (occurrence count asserted
    `1 -> 0`, not reported) → red, naming
    `cabinet/scripts/lib/officer-env.sh:41 array '_observe_arg'`;
  * a brand-new bad `cabinet/scripts/newly-added-gate.sh` → red, naming
    `newly-added-gate.sh:5 array 'new_args'`.
  Both are pinned as standing arms, not one-off manual runs.
* **`bash cabinet/scripts/null-hatch.sh` exit 0** on the committed tree.

## New arms, and what each is worth

| arm | asserts | fails on `d77cc091` because |
|---|---|---|
| `test_the_ratchet_runs_green_in_a_gitless_export` | the shipped ratchet runs from disk inside a `.git`-less dir, exit 0 | the sub-run raises `CalledProcessError` — byte-identical test text both directions |
| `test_the_ratchet_keeps_its_teeth_in_a_gitless_export` | a planted regression is caught **and named** | sub-run goes red for the wrong reason; the "names the probe" assertion fails |
| `test_the_two_listings_agree_file_for_file` | walk == git, file for file | the walk mode does not exist |
| `test_the_sandbox_copies_the_same_tree_without_git` | the boot sandbox stages from a gitless tree | `_sandbox_repo` cannot read a gitless root |
| `test_officer_boot_command_assembles_from_a_gitless_export` | proof-c1 on the artifact a stranger receives | same |

`test_the_two_listings_agree_file_for_file` SKIPS honestly in a gitless tree:
`null-hatch.sh` runs this module inside its egg, where there is no git side to
compare against. Asserting one exists made that arm itself turn null-hatch red
— caught by running the gate against the COMMITTED tree, and fixed before push.

`test_the_sandbox_copies_the_same_tree_without_git` is deliberately **not**
gated on `_requires_legacy_bash`. This defect is interpreter-independent, so it
is the one arm in that module awake on CI (ubuntu, bash 5) where the rest
honestly skip — which matters, because the git-only listing shipped precisely
because no ubuntu job could see it.

The existing `test_officer_boot_command_assembles_under_bin_bash` keeps every
assertion it had; the body was split into `_dry_run_boot` +
`_assert_officer_booted` so the gitless arm reuses it rather than forking a
second copy that could drift.

## Hardening the mode switch itself

Which listing mode runs must depend on the filesystem, not on the caller. An
ambient `GIT_DIR` defeats the probe even inside a real checkout — measured:

```
$ GIT_DIR=/nonexistent/x.git git -C <a real checkout> rev-parse --show-toplevel
fatal: not a git repository: '/nonexistent/x.git'
$ env -u GIT_DIR git -C <same> rev-parse --show-toplevel
<the checkout>
```

So all four git probes now run with `GIT_DIR`/`GIT_WORK_TREE`/`GIT_COMMON_DIR`
/`GIT_INDEX_FILE`/`GIT_OBJECT_DIRECTORY`/`GIT_ALTERNATE_OBJECT_DIRECTORIES`
/`GIT_NAMESPACE`/`GIT_CEILING_DIRECTORIES`/`GIT_DISCOVERY_ACROSS_FILESYSTEM`
scrubbed from the CHILD env only. Verified: with `GIT_DIR` leaked into pytest,
`test_the_two_listings_agree_file_for_file` still passes.

And the parity arm no longer skips quietly on a bad premise: it skips only when
`ROOT/.git` is genuinely absent (a delivered egg). If a `.git` is present and
git still will not name it as the toplevel, the arm goes **red** rather than
retiring itself.

### One unexplained observation, recorded rather than buried

The first branch-wide sweep reported `framework/` as
`1 failed, 6517 passed, 26 skipped`; six subsequent runs — including one
through the identical sweep harness — all report `1 failed, 6518 passed, 25
skipped`, with a skip list byte-identical to master's. One test skipped once
and has not skipped since; it was not identified. 23 of the 25 standing skips
are `redis-cli cannot reach a Redis server`, i.e. a live-service surface. No
tracked python anywhere in the repo writes a `GIT_*` env var, so an in-repo
leak is ruled out. Recorded as open; the hardening above means this module's
arms cannot be the silent contributor.

## Honest bounds

* The walk fires only when git cannot answer. On a **dirty checkout with no
  git binary** it would also scan untracked shell. That is a loud, fixable red
  on real shell in the tree, not a silent pass — accepted.
* `_WALK_PRUNE` matches bare directory *names* at any depth. Confirmed today
  that no tracked shell sits under one; the parity arm is the standing sensor.
* Module count: `cabinet/scripts/lib/tests/test_bash32_empty_array.py` is now
  **8** sensors, not the 6 recorded in cp1.
