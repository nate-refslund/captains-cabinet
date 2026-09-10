# Checkpoint review — `feat/p1-staged-rebuild-real` cp3 (FW-019)

Reviewed-Scope-Digest: 31639c8b1d4cf3ffa30a0d41dd62e7bdd546266201cd39194c8a85b0a0f9c32c

**Scope:** the updater's exit codes are its own on Linux too. Three files:
`cabinet/scripts/cabinet-update.sh` (the re-exec, one branch removed),
`cabinet/scripts/tests/test_cabinet_update.py` (two new arms, one re-aimed),
`docs/runbooks/cabinet-update.md`.

## The defect being closed

Found by CI on this PR's own branch and, on inspection, already red on `master`:
the acceptance drill's `responsibility-drill` job has been failing at P7 with

```
FAIL [P7] exit 50 — an apply whose dashboard never restarted exited 0;
1 is the exit of an apply that rolled itself back
```

The gate-red leg hands the apply a restart that does nothing, the health gate
must go red, and the apply must exit 1. On the runner it exited **0**, with no
output at all.

`reexec_detached` re-execs the updater into `.updates/run/` under a new session
before its first write, so that killing the caller cannot kill the update. It
did that two ways:

```bash
if command -v setsid >/dev/null 2>&1; then
  exec setsid bash "$RUN_DIR/cabinet-update.sh" "$@"
fi
exec "$PY" -c 'os.setsid(); os.execvp(...)' ...
```

`setsid(1)` **forks** when its caller is already a process group leader, and the
parent exits **0 immediately** without waiting. So on every Linux box this
script answered 0 for a refusal (3), a rollback (1) and a busy lock (4) alike.
macOS has no `setsid(1)`, took the interpreter branch — one process, exit status
preserved — and told the truth. **Every arm in the updater's own suite is green
on macOS and always was.** That is the whole shape of the bug: a platform
divergence in a script that ships to boxes this org does not own, invisible to
the only platform anyone developed it on.

## The fix

Delete the branch. The interpreter this script already requires makes the same
call and does not fork: `os.setsid()` then `os.execvp` keeps ONE process, so the
exit status is the updater's own and the open file description holding the lock
rides through the `exec` exactly as before. One path, both platforms.

## Sensors

| Arm | RED on `ae687861` | GREEN |
|---|---|---|
| `test_the_re_exec_hands_back_the_updaters_own_exit_code` | "a bundle that is not in the inbox came back as 0. Exit 3 is this path's word for 'refused'…" | rc 0 |
| `test_the_re_exec_does_not_hand_its_exit_code_to_a_program_that_may_fork` | "the updater execs setsid(1), which forks when its caller is a process group leader…" | rc 0 |

The behavioural arm is **portable on purpose**: it plants a forking `setsid` FIRST
on PATH, so a box without `setsid(1)` measures exactly what a box with one does.
Without that, the arm would be a skip on the only machine that runs it by hand —
and a skipped arm is a disabled sensor, which is how this got here.

## One existing arm re-aimed, and it re-aimed itself

`test_without_the_re_exec_the_group_kill_takes_the_updater_with_it` mutates the
updater to strip the new session and requires the property to disappear. It
neutered two sites; one is gone, so it failed with **"the re-exec moved; this
inverted arm must be re-aimed"** rather than silently mutating nothing and
scoring the real updater as a red. It now aims at the code line
`try:\n    os.setsid()\nexcept OSError:` — the first cut aimed at the bare name
`os.setsid()` and hit the **comment above the call**, mutating prose; the guard
added in the same edit (`mutated_text != text and marker not in mutated_text`)
caught it immediately instead of leaving a confusing red.

## Residual

The exit-code arm proves the status survives a forking `setsid` on PATH. What it
cannot prove from macOS is the runner's own process-group shape; the actual proof
is the `responsibility-drill` job on this PR, which is red on `master` for this
reason and must be green here.
