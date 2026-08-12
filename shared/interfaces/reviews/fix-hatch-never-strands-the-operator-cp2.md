# Checkpoint review — fix/hatch-never-strands-the-operator (cp2, post-merge)

Scope: the merge of `origin/master` (`39388dd3`, PR #345 "you choose your Cabinet
password on first run") into this branch, plus the adaptation it forced. The cp1
artifact covers the branch's own change set and is unaffected.

## Why the merge needed more than a conflict resolution

PR #345 removed the generated dashboard password: a fresh cabinet has none, and
the operator chooses one on the dashboard's first-open screen. It did **not**
update `hatch.sh`'s browser handover, which still ran
`dashboard-password.sh --copy` and, on the refusal that is now the NORMAL
first-run case, printed:

    [app-feel] password not copied — get it with: bash cabinet/scripts/dashboard-password.sh --copy

That sends a fresh operator back to the command that just refused, and this
branch's own copy then told them to "paste in the password we just copied" — a
password that does not exist. Shipping that would reproduce, in the same tail,
the class of failure this whole branch exists to remove.

## What changed post-merge

- `app_feel` tracks whether the copy actually succeeded (`pw_copied`). On
  success: "Sign in with the password we just copied for you — paste it in."
  On refusal: "nothing was copied to your clipboard — the line above says why. A
  brand-new Cabinet asks you to choose a password on its first screen," and the
  closing line becomes "if it asks you to choose a password, pick one you'll
  remember".
- hatch never guesses the reason. `dashboard-password.sh` prints the precise one
  (no password yet / no clipboard / bad permissions) and hatch points at that
  line, so the two can never contradict each other.
- `test_forced_password_failure_stays_green_with_honest_line` became
  `test_password_refusal_reads_as_the_first_run_case_and_stays_green` (asserts the
  first-run instruction, the deferral, the ABSENCE of the re-run advice, and the
  absence of "paste it in"), plus a new inverse arm
  `test_password_copied_tells_them_to_paste_it`.
- README conflict resolved by keeping master's first-run-password paragraph and
  re-adding this branch's never-strand paragraph after it.
- Runbook: master's password bullet extended with the refusal contract; the
  operator-copy table gained the row.

## Risk

Behaviour of the password script itself is untouched; only which sentence hatch
prints around it. Both arms are tested. The merge brought in `hatch.sh` edits
from master (the password bullet in the tail comment) which merged cleanly with
this branch's rewrite of the same function — verified by running the full
`test_hatch_app_feel.py` + `test_hatch_movein_nonfatal.py` +
`test_hatch_dry_run.py` + `test_hatch_cleanroom_containment.py` set green after
the merge, and the full `cabinet/scripts/tests` suite after that.
