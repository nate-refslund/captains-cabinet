# Germline session-start boot-pack — captain-law digest injection + write plane (staged, not landed)

**Date:** 2026-07-15 (write-plane + promotion-gate rev 2026-07-16, same
lane) · **Author:** memwave3 lane-BC consolidation/boot-pack agent (scratch
clone off `405abed3`) · **Ledger row:** not yet assigned — a CG row is
required before the unlock window (integrator files it; suggested wording
travels with the lane hand-back) · **Targets (ONE patch, ONE ceremony):**
`cabinet/scripts/hooks/session-start.sh`,
`cabinet/scripts/hooks/pre-tool-use.sh` (both schg-locked via the
`germline-lock.sh` hooks-dir entry) and
`cabinet/scripts/lib/officer-sandbox.sh` (schg-locked, its own entry) ·
**Patch artifact:**
`docs/proposals/germline-session-start-digest-2026-07-15.patch` — a plain
FILE directly under `docs/proposals/` BY CONTRACT: the egg exporter's
`t_proposals_archive` `rm -f`'s each entry under `set -e`, so a
subdirectory here aborts the export (both package files carry
`expect-absent` manifest rows and archive out of the egg like every other
non-amendment proposal) · **Provenance:** no locked file was ever edited
anywhere — the patch was built against pristine copies in a disjoint
scratch tree and is verified by
`cabinet/scripts/tests/test_session_start_digest_patch.py` on every CI run
without touching the locks.

## Why

`session-start.sh` injects the captain triplet via `tail -40` per ledger.
The ledgers are append-only and growing (decisions ~175KB and +~11%/3d at
flag time): everything older than the last 40 lines is boot-invisible, so
early law silently stops binding new sessions. Lane BC adds a distillation
organ, `cabinet/scripts/memory-distill.py`, whose flow is
review-then-promote:

1. default run → `shared/interfaces/captain-law-digest.proposal.md` (the
   REVIEW surface; never boot-injected; PROPOSAL banner in-file);
2. Captain reviews (standing handback);
3. `--apply` → refuses unless the on-disk proposal byte-matches a fresh
   render of the live ledgers, then writes the PROMOTED boot surface
   `shared/interfaces/captain-law-digest.md` (no PROPOSAL banner) and
   queues per-topic `captain_law_summary` rows (`trust=reflection`, never
   `captain`);
4. `--check` → read-only staleness tell (recorded ledger sha256s vs live);
   `cabinet-doctor` maps stale to WARN/AMBER daily and the cross-officer
   retro's Part 5 acts on it (regenerate proposal → Captain review — no
   automatic regeneration; scheduling stays a Captain decision).

This patch makes boot USE the promoted digest — and, in the SAME ceremony,
makes the promoted digest as write-protected as the law it summarizes.

## The staged change (three hunks, one artifact)

The `.patch` artifact is canonical; excerpts below name each hunk's intent.

1. **`session-start.sh` — inject the digest IN FULL, FIRST.** If
   `shared/interfaces/captain-law-digest.md` exists it is injected as the
   first section (`Captain Law Digest (distilled index — full ledgers
   remain authoritative)`), ahead of the tail-40 sections, which stay
   unchanged. Backslashes are doubled (`body="${body//\\/\\\\}"`,
   bash-3.2-safe) before the body joins `$context`.

2. **`pre-tool-use.sh` — the digest + its distiller join the captain-law
   write plane.** §5 Write/Edit arm gains
   `*"shared/interfaces/captain-law-digest.md"` and
   `*"cabinet/scripts/memory-distill.py"`; §5c's
   `CAPLAW_PATH_RE` becomes
   `shared/interfaces/captain-(patterns|intents|decisions|law-digest)\.md|memory/skills/|cabinet/scripts/append-interface\.sh|cabinet/scripts/memory-distill\.py`.
   Every write-shaped Bash vector §5c already screens (redirect, append,
   tee, sed -i, cp/mv/install/ln, truncate, dd, interpreter-with-flag,
   rm/shred) now also blocks on the digest and on the distiller script
   (doorway protection, exactly the append-interface.sh pattern).

3. **`officer-sandbox.sh` — kernel plane.** `captain-law-digest.md` joins
   the seatbelt ledger loop: `deny file-write*` + `deny file-write-unlink`
   on its vnode, closing redirects/interpreters/split-variables/symlinks
   below the hook for sandboxed officers.

## Threat model & safety analysis

**1. Envelope safety (JSON).** The final emission path is UNCHANGED:
`printf '%s' "$full_context" | jq -Rs '{hookSpecificOutput: …}'` —
`jq -Rs` string-encodes arbitrary bytes, so no digest content can escape
the JSON envelope. The one pre-existing hazard on the section path is
`printf '%b'`, which expands backslash sequences in section bodies; the
patch doubles every backslash in the digest body BEFORE it joins
`$context`, so `%b` collapses the pairs back to the original bytes —
byte-exact round-trip, pinned by test (and a mutant with the doubling line
removed FAILS the round-trip: the escape is load-bearing). The three
tail-40 sections keep today's behavior, untouched.

**2. Write plane — the injection-persistence channel (the reason this rev
exists).** Boot-injecting an officer-writable file as "Captain Law Digest"
would reopen the 2026-07-07 audit-CRITICAL self-persuasion channel that
the captain-law plane closed for the three ledgers: any officer (or
prompt-injected text steering one) could write arbitrary instructions into
the digest and have them injected FIRST into every subsequent session,
bypassing `append-interface.sh`'s provenance gate. Therefore the SAME
patch that starts injecting the digest adds it to all three write guards
(§5 Write/Edit arm, §5c bash screen, kernel seatbelt deny) — the digest is
never injectable without being guarded, and a half-applied ceremony fails
the test suite's all-or-none state check. Sanctioned-writer carve-out:
bare distiller invocations (`python3.12 cabinet/scripts/memory-distill.py
[--apply|--check]`) carry no write-shaped token targeting a plane path and
pass §5c (pinned ALLOW); the promoted file is written by the distiller
from an unsandboxed Captain/CoS context. The `.proposal.md` review sibling
is DELIBERATELY outside the plane (pinned ALLOW): tampering it cannot
reach boot because `--apply` refuses on any divergence from a fresh
render — see 3.

**3. Content authenticity chain.** What boots is derived, gated, and
guarded end-to-end: (a) the source ledgers are append-only with
provenance-stamped officer appends (`### officer-note … [trust:officer]`),
and the distiller EXCLUDES officer-notes from distillation; (b) the render
is deterministic and LLM-free (no prompt-injection summarization channel;
byte-identical re-runs); (c) `--apply` promotes only when the reviewed
proposal byte-matches a fresh render (review-rot and hand-tampering both
abort, exit 3, nothing written or queued); (d) post-ceremony the promoted
vnode is write-guarded (hook + kernel) and the distiller script itself is
doorway-protected. Memory rows land as `captain_law_summary` /
`trust=reflection` — a summary never masquerades as law.

**4. Staleness (detection-without-closure guard).** The ledgers keep
growing after promotion; entries newer than the promoted snapshot but
older than tail-40 would be boot-invisible again — masked by an
authoritative-looking digest section. Closure: `--check` (recorded
per-ledger sha256s vs live), probed daily by `cabinet-doctor` (WARN/AMBER,
never DEAD — regeneration is Captain-gated) and acted on by the
cross-officer retro's Part 5 step 13 (regenerate the proposal for Captain
review). Deleting the digest (kill switch) reads as "not in use", not
stale — no nagging.

**5. Accepted residuals (named).** Same §5b/§5c class as the ledgers:
variable indirection, `git checkout -- <path>` content restores, and
script-file interpreters (`python3 evil.py`) remain screen residuals for
NON-sandboxed contexts — for sandboxed officers the kernel deny closes
them on the digest vnode. The distiller runs unsandboxed by design (it is
the sanctioned writer); its own tampering surface is closed at the hook
plane (Write/Edit + §5c doorway arms). Pre-ceremony the digest file is
inert: today's hook never reads it.

## Test coverage (the ceremony's acceptance evidence)

`cabinet/scripts/tests/test_session_start_digest_patch.py` — STATE-AWARE
(pre-ceremony: applies the artifact to pristine copies + runs the
pre-state negative controls; post-ceremony: probes the live files' copies,
apply-test skips; MIXED state fails loudly): clean apply + `bash -n` on
all three files; digest section ordered BEFORE the tails; hostile-digest
JSON round-trip byte-exact; doubling-line mutant control; absent digest →
output byte-identical to the unpatched hook; write-plane probes — BLOCK
Write/Edit/redirect/append/tee/rm on the digest (cro AND cos) and doorway
tampering on the distiller, ALLOW reads/distiller invocations/proposal
writes/unrelated interface writes; three-ledger regression pin; pristine
hook ALLOWS the digest write (pre-state control proving the guard is this
patch's work); kernel deny-line pins for the sandbox.
`cabinet/scripts/tests/test_memory_distill.py` pins the organ side:
proposal-only default (no promotion, no enqueue), --apply refusal on
missing/tampered/stale proposal, promotion banner, trust=reflection rows,
--check 0/3/4 cycle incl. read-only-ness, gitignore class for both
surfaces.

## Ceremony (Captain-gated unlock window — never self-serve)

1. Prereqs: this addendum + the CG row filed; `memory-distill.py` landed;
   the Captain has reviewed a generated `captain-law-digest.proposal.md`
   at least once and run `--apply` (the boot file must exist as REVIEWED
   content before it ever boots — though the patch is safe either way:
   absent digest = today's behavior, byte-identical).
2. Captain sudo unlock window (`cabinet/scripts/germline-lock.sh unlock`,
   or the file-scoped chflags equivalent for the hooks dir +
   `officer-sandbox.sh`).
3. Apply from repo root: `patch -p1 <
   docs/proposals/germline-session-start-digest-2026-07-15.patch`
   (equivalently `git apply` the same file). No other germline file
   changes.
4. Verify: `bash -n` on all three files; `python3.12 -m pytest
   cabinet/scripts/tests/test_session_start_digest_patch.py -q` (flips to
   live-copy mode automatically post-apply — the write-gate probes now
   exercise the live hook's copies); `bash
   cabinet/scripts/run-hook-regression.sh` (existing harnesses are
   unaffected — additions only widen the plane); commit with the CG row
   flip in the same batch.
5. Relock the SAME day (`germline-lock.sh lock` + `status`/`verify`).

## Rollback

`git revert` of the unlock-window commit, or `patch -p1 -R` with the same
artifact inside a new window (all three files revert together — never
partially). Runtime kill switch WITHOUT any unlock is Captain-side by
design: delete/rename `shared/interfaces/captain-law-digest.md` from an
unsandboxed Captain/CoS context — the boot section vanishes and the hook
output is byte-identical to today's. Officer sessions are deliberately
unable to operate the kill switch (rm on the digest is write-shaped and
blocked): an officer must not be able to erase boot law any more than
forge it.
