# Germline amendment — the employee phase-1 bundle (landed bytes, one window)

**Filed** 2026-09-08 · **Ledger row** CG-36 · **Status** captain-gated (NAMED
Captain sudo-unlock handback, non-grantable) · **AWAITING CAPTAIN** for the
ceremony only · **Apply token** reply **"apply employee phase 1"**

> **Nothing here writes a locked path on any machine.** It is the apply
> contract for two schg-locked files, delivered as unified diffs plus a
> runnable gate, so that one Captain unlock/relock window can carry the whole
> of phase 1's germline debt instead of two. Both files' new bytes are already
> committed on master in the unlocked lane; the window re-materialises them on
> the machine whose copies are locked, and only the Captain can open it.
>
> The germline path **SET** is byte-identical: `cabinet/scripts/germline-lock.sh`
> is untouched and no path enters or leaves the locked set. Only the CONTENT of
> two already-locked files is proposed to change.
>
> **Both halves are landed-then-ceremonied** (CLAUDE.md §8: a germline CONTENT
> fix is built in a clone, landed to master like any change, and one Captain
> window re-materialises the landed bytes). G1 landed as `00c3acd3`; G3 landed
> as `8bd3e0c2` under contract amendment A7.7 — see §3. The window therefore
> re-materialises both targets with `git checkout` and applies no diff inside
> a window that cannot be re-opened.

Sibling directory: `docs/proposals/germline-amendment-employee-phase1-2026-09/`
— `G1.diff`, `G3.diff`, `verify.sh`.
Sensors: `cabinet/scripts/tests/test_germline_bundle.py`.
Contract of record: phase-1 contracts §7 + amendments A7.1–A7.7.

## 1. What this bundle is for

Phase 1 gives the Cabinet one owned responsibility end to end: a ratified
outcome, an atomic claim in the real pull path, survival across a kill, receipts,
and an update that reaches the installed Cabinet. Two of the surfaces that path
runs through are constitutional and physically unwritable by this uid — that is
the design, not an obstacle. Both are named here once, with the bytes attached,
so the Captain spends one window rather than a window per defect.

Neither change is required for the phase-1 drill to go green
(`cabinet/scripts/drills/one-responsibility.sh`). Both are required for the
result to be *trustworthy on the box*: one stops a worker booting on a
constitution nobody can vouch for; the other stops the officer's only pull tick
from failing silently, and gives its claim a holder identity that survives a
restart.

## 2. The proposed bytes

| id | Locked file | Change | Evidence |
|---|---|---|---|
| G1 | `cabinet/scripts/start-officer-mac.sh` | fail closed (exit 78) when the runtime constitution + safety bundle fails to assemble, instead of logging and booting anyway | pre-change bytes at `cabinet/scripts/start-officer-mac.sh:169-174` of `00c3acd3^`; landed on master as commit `00c3acd3` |
| G3 | `cabinet/scripts/hooks/session-task-inject.sh` | pin `${CABINET_PYTHON:-python3.12}`; append stderr to `${CABINET_HOOK_LOG:-$HOME/Library/Logs/cabinet/hooks.err}` instead of `2>/dev/null`; export `CABINET_WORKER_ID="${OFFICER}@<session id>"` before the call | pre-change bytes at `cabinet/scripts/hooks/session-task-inject.sh:28-34` of `8bd3e0c2^`; landed on master as commit `8bd3e0c2` |

**The exact bytes, both ends.** A unified diff is a statement about a few lines,
so it applies just as cleanly to a file that differs everywhere else — and then
produces something nobody declared. Each row therefore pins the **pre-image
sha256** it was built against as well as the post-image it produces, and
`verify.sh` classifies the file in front of it by digest rather than by an
assumption about which tree it is looking at:

| id | pre-image sha256 (the bytes the diff expects) | post-image sha256 (what it produces) |
|---|---|---|
| G1 | `856db3fcd8952fbe21db051fd6597c1aaad81b9e2147c262f78378d3c398b1bd` | `bd5dcd464e9b81b694c5a24d2f66d3db0a61473cbff9804b0606b1656d481345` |
| G3 | `8e37461fcb807a269cb6e59a6b7825e99cd592651fce6e6a947bd03fbafc553c` | `5f2e177b80d0e49949d9bde24b8ee7964aeea21b6281d6699913320e31934297` |

### G1 — `cabinet/scripts/start-officer-mac.sh` (LANDED, awaiting the window)

The launcher assembled the officer's runtime constitution and safety boundaries
through `load-preset.sh` and, on a non-zero exit, logged
`runtime constitution may be incomplete` and **continued** — the comment said
"let officer try to boot anyway". That started a worker whose own rules were of
unknown provenance, while every sibling assembly failure in the same script
already refuses: egress reconciliation, security-path resolution, the sandbox
library, the Captain-law broker and the one-shot launcher all `exit 78`, and the
MCP generator fails closed to an empty server set. The constitution — the one
input that defines what the officer may do at all — was the single fail-open.

The landed bytes refuse with `exit 78` and print the recovery path. Retention of
"the last verified bundle" was considered and rejected: `$CABINET_RUNTIME_DIR`
holds the two files with no manifest, no revision stamp and no completion
marker, so both can be present and current while assembly failed *after* them,
or present and stale when it failed *before* them. Presence is not completeness.

`G1.diff` therefore takes the file **from the pre-change bytes named above to
the bytes already on master**. On a clone of master the target is byte-identical
to the post-image — `verify.sh` reports `already-at-target`, which is a pass,
not a skip. What the schg-locked tree holds is **not measurable from this
repository**, so this document does not say: `verify.sh` digests the file that
is actually there and answers, and the ceremony asks it **before the unlock**
(§5 step 0). G1 is also the safer of the two shapes regardless of the answer,
because step 3 re-materialises the landed bytes with `git checkout` rather than
patching — the result is the declared post-image on any tree.

### G3 — `cabinet/scripts/hooks/session-task-inject.sh` (LANDED, awaiting the window)

This hook is the officer's only pull tick. Three defects, all in the same four
lines:

1. **`python3` is unpinned.** On the box that resolves to the system 3.9 while
   the framework targets 3.12, so the *interpreter* — not the code — decides
   whether the pull path imports at all. The landed bytes pin
   `${CABINET_PYTHON:-python3.12}`, the same seam
   `cabinet/scripts/work-graph-complete.sh` and `ledger-status-parity.sh` use.
2. **`2>/dev/null` swallows the traceback.** A broken import and an empty queue
   produce byte-identical output: nothing. A claim sensor that cannot fail
   loudly is not a sensor. The landed bytes append stderr to
   `${CABINET_HOOK_LOG:-$HOME/Library/Logs/cabinet/hooks.err}`, creating the
   directory first and degrading to `/dev/stderr` if it cannot be created —
   never back to `/dev/null`.
3. **The claim has no stable holder.** `framework/missions/claims.py`
   `derive_holder` prefers `CABINET_WORKER_ID` and otherwise falls back to
   `<role>@session:<pid>`, so one role's two live sessions are told apart by a
   pid a restart reuses. The landed bytes export
   `CABINET_WORKER_ID="${OFFICER}@<session id>"` from the hook payload before
   the call, so a holder is stable for as long as the session that holds the
   work. A missing field or an absent `jq` yields `nosession`, never an empty
   holder.

Two smallest-thing choices the contract left open, recorded rather than assumed:
`$HOME` is defaulted (`${HOME:-/tmp}`) because the script runs under `set -u`
and an unset `HOME` must not abort the tick; and the log directory is created
before first use, because appending to a path whose directory does not exist
fails the redirection and would silently disable the injector — the exact class
of failure this change exists to end.

**G3 is still the row that can come back needing a rebuild, and here is exactly
why.** Its diff was built against master's bytes as they stood before the
landing. Master last changed this file on 2026-07-31 (`5338cb42`), **outside
G3's own hunk** — a GNU-first `stat` fallback ten lines above it. A locked copy
that predates that commit therefore still takes G3.diff cleanly and produces
`c89c578fc10de08e89668416b45fc51b9ac7b366a1efa10f2992e697f2b30348`, which is not
the post-image declared above. Measured 2026-09-08; it is the reason the
pre-image is pinned at all. Landing the bytes removes the *apply* from the
window — step 3 is now a `git checkout` for both rows, which yields the declared
post-image on any tree — but it does not make the box's bytes knowable from
here. If step 0 reports DRIFT for this row the answer is unchanged: **rebuild
the bundle against the bytes it actually holds and re-file this row** — never
force-apply, and never spend the window finding out.

## 3. What is deliberately NOT here

- **G3 rode as a diff only, and no longer does.** The unit that built this
  bundle was bound by a hard invariant — *nothing under a locked path is
  modified* — and `cabinet/scripts/hooks` is a locked DIRECTORY, so it could
  not land the bytes itself. That invariant was correct for that unit and is
  lifted for this one file by contract amendment **A7.7**: the directory's
  schg lock is a fact of the LIVE checkout, not a rule about git (precedent
  `5338cb42`, a hooks-directory file landed on master on 2026-07-31). The
  bytes landed as `8bd3e0c2` in the unlocked lane, as a separate reviewable
  act, exactly as G1 did as `00c3acd3`. Nothing on any box was written by that
  commit; `verify.sh` reports the state of whatever tree it is pointed at.
- **G2 — `cabinet/scripts/hooks/on-subagent-start.sh` — is dropped** (contract
  amendment A7.1). Its only emitter today sends a `task_ref`-shaped
  `work_item_started` the compiler overlay can never apply
  (`framework/missions/compiler.py:283-289`), and the event type that would
  replace it is deliberately **not registered in phase 1** (A0.5): nothing
  emits it, and registering an event with no emitter is substrate with no
  consumer. It stays a residual (§8).
- **G4 — an officer-sandbox deny under `.updates/`** — is a residual (A7.4),
  not part of this window. The update path's own refusals are its boundary
  today; a sandbox rule is defence in depth that can be added at the next
  window without re-opening this one.
- **No `sudo`, no unlock, no workaround.** An unavailable window is a recorded
  handback, which is already raised in the program's handbacks file
  (2026-09-06, A7.2). This document is the apply contract for that handback.

## 4. The apparatus, and what it actually proves

`docs/proposals/germline-amendment-employee-phase1-2026-09/verify.sh` is the
bundle's own gate and is runnable both in a clone and on the box that owns the
locked bytes (an installed Cabinet has no git repository, so every check is done
against files, never against revisions). For each row of its embedded table it:

1. digests the CURRENT bytes of the target and compares them with the row's two
   declared digests. Equal to the **pre-image sha256** ⇒ apply into a scratch
   tree. Equal to the post-image ⇒ `already-at-target`, a pass. **Neither** ⇒
   exit 10, naming all three digests: the bundle does not describe these bytes,
   so it is rebuilt against them and is **never force-applied**. No `git apply`
   is attempted in that case, deliberately — a diff applies to bytes it was
   never built from and yields something nobody declared, which is the most
   misleading answer available;
2. pins the resulting post-image `sha256` against the digest declared in the
   table, which catches a bundle whose diff was edited after its digest was
   computed;
3. runs `bash -n` over the post-image;
4. digests every path of the parsed locked set before and after the run and
   fails (exit 12) if a single byte moved — the bundle must cost nothing to
   inspect;
5. re-runs `cabinet/scripts/run-golden-evals.sh`, the ceremony's behavioural
   gate. `--checks-only` skips only that stage, and says so, because it needs a
   Redis endpoint the automated sensors do not provide.

The locked set is read through the repository's own audited parser
(`cabinet/scripts/lib/update_bundle.py::parse_locked_set`), which refuses a
partial parse. A boundary this script cannot read is a refusal (exit 64), never
an empty set.

`cabinet/scripts/tests/test_germline_bundle.py` is the standing sensor:
`verify.sh` green in `--checks-only` mode; the bundle table and the doc naming
the same files; every `landed` row already at its declared post-image in the
tree; no path of the locked set appearing in a branch's own diff unless that
branch is a sanctioned landing; the ledger row present exactly once with its
plan-doc twin and A13 parity green. Its `test_phase1_touches_no_locked_path`
arm **fails** when its base revision is unreachable (A7.3) rather than passing
on a shallow checkout — a guard that cannot see the diff it guards is a
disabled sensor, not a pass.

**The landing-acknowledgement channel (A7.6).** A branch that lands germline
bytes in the unlocked lane necessarily puts a locked path in its own diff, so
the guard needs one exemption or the sanctioned pattern becomes unlandable and
`--admin` bypass is forbidden. The exemption requires BOTH halves and neither
is prose: `CABINET_GERMLINE_LANDING=<CG row>` in the environment of the run,
AND every locked path in the diff being a target this package **declares** it
is landing — a row of `verify.sh`'s own `BUNDLE_ROWS` table whose state is
`landed`, or, for a package that ships no bundle table, an explicit landing
list in its document (a line beginning `landing` and a colon, then one `- path`
bullet per line). The declared target must also currently hold the declared
post-image, so the exemption cannot cover one byte more than the Captain is
being asked to accept. A path that merely APPEARS in this document — the
dropped G2 residual `cabinet/scripts/hooks/on-subagent-start.sh`, or
`cabinet/scripts/germline-lock.sh`, which is named in §6 and is the file that
*defines* the set — is not declared and cannot ride the exemption. The
unconditional backstop `test_the_guard_is_not_exempted_on_this_branch` stays,
and asserts the same property from the tree alone, without reading the
environment at all.

## 5. Ceremony (Captain sudo, relock SAME day)

Reply **"apply employee phase 1"**. The window, in order:

0. **Before any sudo, and this is the step that matters:**
   `bash docs/proposals/germline-amendment-employee-phase1-2026-09/verify.sh --checks-only`
   against the tree that owns the locked bytes. It writes nothing and needs no
   privilege. Every row must report `applies` or `already-at-target`. A row that
   reports DRIFT means the bundle was built against different bytes — **rebuild
   it against the ones printed and re-file this row; do not open the window**. A
   Captain unlock cannot be delegated and is not the place to discover a
   rebuild, which is precisely where the first draft of this package would have
   discovered it (§2, G3).
1. `bash cabinet/scripts/germline-lock.sh status` and `ls -lO` on both targets —
   lock state is re-verified fresh immediately before the edit, never assumed
   from an earlier session.
2. `sudo bash cabinet/scripts/germline-lock.sh unlock`.
3. Both rows are re-materialised the same way — the landed bytes checked out,
   never a hand edit and never a patch applied inside the window:
   `git checkout 00c3acd3 -- cabinet/scripts/start-officer-mac.sh` ·
   `git checkout 8bd3e0c2 -- cabinet/scripts/hooks/session-task-inject.sh`.
   `git checkout` yields the declared post-image on any tree, which is why
   this is the safe shape and why A7.7 landed G3's bytes first.
4. Gates, all green in the same session:
   `bash docs/proposals/germline-amendment-employee-phase1-2026-09/verify.sh`
   (full form, golden evals included) ·
   `bash cabinet/scripts/run-hook-regression.sh` ·
   `python3.12 -m pytest framework/tests/test_germline_lockstep_consistency.py -q`
   (the lockstep meta-test — the SET must still be byte-identical) ·
   `bash cabinet/scripts/drills/one-responsibility.sh` with the locked-hook leg
   asserted (its P2h stage runs the real hook bytes; exits 20/21 name the stage
   if the pull path cannot be measured through them).
5. `sudo bash cabinet/scripts/germline-lock.sh lock`, then `status` and
   `verify` — **same session, same day**.

`sudo -n` is attempted first. On failure this is the recorded handback and
nothing here is worked around.

## 6. Rollback

**One-revert rollback:** per file, and each one is itself a Captain-windowed
germline edit once applied. `cabinet/scripts/start-officer-mac.sh` — revert to
the pre-amendment bytes named in §2 (the launcher then logs and boots on an
unverified constitution again, which is the pre-ruling behaviour, not a broken
state); on the git side, revert the single landing commit `00c3acd3`.
`cabinet/scripts/hooks/session-task-inject.sh` — reverse-apply `G3.diff`
(`git apply --reverse`), restoring the unpinned `python3` and `2>/dev/null`; the
hook then reports "no task" for a broken import exactly as it did before the
window. On the git side, revert the single landing commit `8bd3e0c2`. The
**germline path SET** needs no restoration — `cabinet/scripts/germline-lock.sh`
is never touched by this package, so no path enters or leaves the locked set,
and the lockstep meta-test pins that both before and after. Ledger row **CG-36**
returns to `captain-gated` with a dated note; nothing else in the tree depends
on either change, and no schema or interface unwinds with them.

## 7. Honest status

**On master: G1 and G3 both in effect. On the deployment: neither in effect
until the window.** Those are two different trees and the distinction is the
whole point of landed-then-ceremonied. Until the window runs, the box's
launcher still boots on an unverified constitution and its pull tick still
swallows stderr — landing bytes on master changes nothing on a machine whose
copy of the file is schg-locked. No sensor anywhere claims otherwise, and the
phase-1 ledger status stays `in-flight` until the drill passes on the installed
Cabinet (A0.8) — nobody writes `done` on a fixture pass.

**What is NOT known here, stated as unknown.** Nothing in this repository can
read the schg-locked tree, so the bytes each target currently holds there are
**unmeasured**. The first draft of this package asserted them instead, and the
assertion was wrong for G3 in the one case that matters (§2). Landing G3
removed the apply from the window; it did not make the box readable. The bytes
are answered by digest at §5 step 0 and nowhere else, and G3's row is still the
one that may come back needing a rebuild.

## 8. Residuals recorded here

- **G2** `cabinet/scripts/hooks/on-subagent-start.sh`: the `task_ref`-only
  `work_item_started` emit, and the same interpreter/stderr defects. Waits on an
  event type with a real emitter (A0.5).
- **G4** officer-sandbox deny under `.updates/` (A7.4).
- The `CABINET_HOOK_LOG` file has no rotation. It is append-only stderr from one
  hook; if it ever matters, rotation belongs to the log plane, not to a locked
  hook. The phase-1 drill pins it into its own scratch
  (`cabinet/scripts/drills/one-responsibility.sh`) rather than letting the
  default create four paths under the drill's scratch `HOME`, which its
  hermeticity stage correctly reported as a write outside the root.
- **After the window, `BOX_PY` in the drill has to be re-argued.**
  `cabinet/scripts/drills/one-responsibility.sh` runs stage P2h under the box's
  own bare `python3` because that is what the LOCKED copy of the hook still
  execs, and `framework/tests/test_interpreter_pin.py` sanctions that one line
  for exactly that reason. Once this window re-materialises the landed bytes on
  a box, the locked copy pins `${CABINET_PYTHON:-python3.12}` and the line no
  longer mirrors it. The stage still measures something real — whether the pull
  path imports under the box's 3.9 — but the sentence justifying it changes,
  and the sanctioned row must be re-argued rather than quietly kept.
