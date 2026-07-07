# Germline Window 2 — Captain Runbook

**Lands:** `feat/germline-window-2` → `feat/fidelity-harness-design` (main checkout `/Users/nate/captains-cabinet`)
**Authored:** 2026-07-07 by the orchestrator (Fable 5), pinned against branch tip `ade5cd47` × base `e340098b` (merge-base `b9b42d95`; every gate + the merge-tree prediction re-verified 2026-07-07 after base advanced from `9dd8e827`). **Re-pin every sha in §0.1 at window time — both branches are advancing.**
**Captain wall-clock cost:** ~10 minutes, two sudo commands. **Steps 1 and 4 are the ONLY Captain-sudo steps.** Everything else is orchestrator work with no sudo and no passwordless-sudo path (that is the boundary's whole design — see `cabinet/scripts/germline-lock.sh` header).

## What this window lands

Eight CG commits staged in the worktree (`git rev-list --reverse b9b42d95..feat/germline-window-2`), plus this runbook itself as the docs-only tip commit (rides the same merge; picked up automatically by every rev-list below):

| sha | what |
|---|---|
| `3aa93ef8` | CG-14 — `policy_engine.py` pull-down into `framework/authority/` (import-closed germ layer, R099 rename + 250-test corpus) |
| `e0e67ac4` | CG-2/R004a — `run_action_lane.py` gather rewire onto the PersonalSource seam, **dark** behind `CABINET_GATHER_VIA_SOURCE` (default OFF = byte-identical gather) |
| `5cfe9453` | CG-15/R104 — retire `constitution/` (superseded by load-preset assembly base; `ROLE_REGISTRY` → `instance/config/role-registry.md`) |
| `381e29ae` | CG-13 — cosmetic batch (CAPTAIN-RULING scrubs, R151 settings audit, R126 `act-first-surfaces.yml.example` twin) |
| `8d3a76f4` | ledger — germline-window-2 rows → in-flight |
| `1f0e9342` | CG-14 follow-up — measurement seeds off the retired `cabinet/scripts/lib` engine path |
| `354ec3d1` | CG-2 follow-up — D13 inbound-provenance floor back inside the locked lane |
| `ade5cd47` | test repair — `gen-officer-mcp-config` allowedMcpServers object-shape drift |

Germline discipline is already satisfied **on the branch**: four amendment docs committed under `docs/proposals/` (`germline-amendment-{policy-engine-pulldown,gather-rewire,constitution-retirement,cosmetic-batch}-2026-07-07.md`), and `framework/tests/test_amendment_doc_lint.py` + `framework/tests/test_germline_lockstep_consistency.py` (237 tests together) pass at tip. The lockstep suite proves the four germline lists moved together off `framework/policies/immutable-core.yml`: `germline-lock.sh` FILES/DIRS/SKIP arrays, `cabinet/scripts/hooks/pre-tool-use.sh` §5 case arm, §5b `GERM_PATH_RE`, and `framework/policies/base-safety.yml` germline-readonly patterns.

## Window budget

| T | step | actor | sudo |
|---|---|---|---|
| T–1d…T–30m | §0 preconditions | orchestrator | no |
| T+0:00 | §1 unlock | **Captain** | **yes** |
| T+0:30 | §2 merge | orchestrator | no |
| T+1:30 | §2 gates (full suite + 4 named) | orchestrator | no |
| T+6:30 | §3 canary tick (dry-run) | orchestrator | no |
| T+8:30 | §4 relock + verify | **Captain** | **yes** |
| T+9:00→ | §5 push / ledger / officer-note | orchestrator | no |

§5 needs no unlock and no sudo — it may spill past T+10 freely. The Captain is done after §4.

---

## 0. Preconditions — orchestrator verifies BEFORE requesting the window (no sudo)

**0.1 Re-pin shas, clean-enough trees.**

```bash
cd /Users/nate/captains-cabinet
git rev-parse --abbrev-ref HEAD        # feat/fidelity-harness-design
PRE=$(git rev-parse HEAD)              # rollback anchor — RECORD IT (2026-07-07 re-pin: e340098b)
git status --porcelain                 # empty, or only known-benign untracked files*
git -C /private/tmp/claude-501/-Users-nate/e55f9b5f-b7cf-469f-af48-89a202a8cc4a/scratchpad/germline-window-wt status --porcelain   # empty
git rev-list --count HEAD..origin/master   # 0 — HEAD is never BEHIND origin/master (at re-pin: origin/master 9dd8e827 == HEAD~2, §5.1 catches it up; local master is STALE at 809c089f — ignore it)
```

\* At the 2026-07-07 re-pin, the main checkout carries **two tracked modifications** (`framework/fidelity/oauth_llm.py` + its test — parallel-session work in flight) and two untracked files (`cabinet/scripts/cabinet-doctor.sh`, `memory/golden-evals/eval-021-brain-retrieval-quality.md`). The untracked pair is verified non-colliding — the branch tracks a *different* eval file (`eval-021-source-boundary.md`) and neither path appears in the merge write-set (Appendix A) — but the tracked modifications MUST be committed (or stashed) to zero before the window opens: any *tracked* modification, or any untracked file that appears in Appendix A, blocks the window.

**0.2 Branch gates green in the worktree** (all verified green at `ade5cd47`, 2026-07-07):

```bash
cd /private/tmp/claude-501/-Users-nate/e55f9b5f-b7cf-469f-af48-89a202a8cc4a/scratchpad/germline-window-wt
python3.12 -m pytest framework/ -q                                  # expect: 3741 passed, 18 skipped (~73s), 0 failures (count grows as the branch advances)
bash cabinet/scripts/run-hook-regression.sh                         # expect: "Harnesses: 15 / 15 passed" "STATUS: ALL GREEN"
bash cabinet/scripts/check-layer-separation.sh                      # expect: "[layer-sep] OK — no new layer-separation violations."
python3.12 -m pytest framework/tests/test_amendment_doc_lint.py \
    framework/tests/test_germline_lockstep_consistency.py -q        # expect: 237 passed
```

**0.3 Merge-conflict pre-resolution (KNOWN ISSUE as authored).** `git merge-tree --write-tree feat/fidelity-harness-design feat/germline-window-2` predicts **CONFLICT in `cabinet/scripts/tests/test_gen_officer_mcp_config.py`** — base commit `9dd8e827` (drops the unenforced `allowedMcpServers` mirror) and branch tip `ade5cd47` both rewrote those tests. (Re-verified 2026-07-07 against base `e340098b`: still exactly this ONE conflict, no new ones.) Resolve OUTSIDE the window, in the worktree, so the Captain window opens conflict-free:

```bash
cd /private/tmp/claude-501/-Users-nate/e55f9b5f-b7cf-469f-af48-89a202a8cc4a/scratchpad/germline-window-wt
git merge feat/fidelity-harness-design       # pull the base INTO the branch; resolve the one conflict
# resolution rule: keep 9dd8e827's semantics (mirror stays dropped) + the branch's object-shape repairs
python3.12 -m pytest cabinet/scripts/tests/test_gen_officer_mcp_config.py -q   # 17+ passed
git add -A && git commit                     # normal commit on feat/germline-window-2 (never push)
# re-run all of §0.2, then confirm the prediction is now clean:
git merge-tree --write-tree feat/fidelity-harness-design feat/germline-window-2   # tree sha only, no CONFLICT lines
```

The window does not open while `merge-tree` still prints a CONFLICT line.

**0.4 Fleet idle or paused.**

```bash
# kill switch state (the fleet pause mechanism — Redis key cabinet:killswitch):
REDIS_URL=redis://localhost:6379 bash cabinet/scripts/kill-switch.sh status
# officers/agents quiet? nonzero second column = red exit:
launchctl list | grep com.cabinet | awk '$2 != 0'
tmux ls 2>/dev/null | grep officer          # sessions may exist; confirm no active run mid-burst
```

Either confirm idle, or pause deliberately for the window: `REDIS_URL=redis://localhost:6379 bash cabinet/scripts/kill-switch.sh activate` (+ drop a one-line paused-note per §5.3) and `deactivate` after §4. The scheduled action lane (`com.cabinet.action-lane.plist`, StartInterval 1800) is additionally protected by `run_action_lane.py`'s singleton lock — a collision with §3 degrades to a graceful "done: another action-lane run holds the lock", not corruption.

**0.5 No red watchdog, boundary state recorded.**

```bash
launchctl list | grep -E 'com.cabinet.(outcome-watchdog|heartbeat|fidelity|graduation)' | awk '$2 != 0'   # expect empty
cd /Users/nate/captains-cabinet
bash cabinet/scripts/germline-lock.sh status    # expect: "--- 41 locked, 0 unlocked (of 40 files + 5 dirs) ---" + "BOUNDARY ARMED"
bash cabinet/scripts/germline-lock.sh verify    # expect: "VERIFY OK — write to schg-locked framework/authority/classifier.py was refused"
```

If status shows the boundary already open (a prior window never closed), §1 becomes a no-op confirmation — but §4's same-day relock becomes *more* urgent, not less (D3).

**0.6 Ask the Captain for the window.** Hand over this runbook, the §0 evidence, and the pinned shas. Do not proceed past this line without the Captain's go.

---

## 1. Captain — OPEN the window (sudo, ~15s)

```bash
cd /Users/nate/captains-cabinet
sudo bash cabinet/scripts/germline-lock.sh unlock
# expect: "UNLOCKED all germline targets. RE-LOCK when done: sudo bash cabinet/scripts/germline-lock.sh lock"
```

Why unlock before merging: the merge writes schg-locked inodes (Appendix A lists them — `run_action_lane.py`, the hooks dir, `framework/policies/*`, `germline-lock.sh` itself, the `policy_engine.py` move, a locked-dir eval deletion). `schg` blocks git checkout/rename on those paths, so *all* git operations on germline happen inside the unlock (script header, "OPERATIONAL PATTERN"). This unlock runs the PRE-merge enumeration; §4's relock runs the POST-merge one — that asymmetry is correct and intended.

## 2. Orchestrator — merge + full gates ON THE MAIN CHECKOUT (no sudo)

**2a. Merge (primary path — use this one):**

```bash
cd /Users/nate/captains-cabinet
git merge --no-ff feat/germline-window-2 \
  -m "merge: germline window 2 — CG-2 gather-rewire (dark), CG-13 cosmetic batch, CG-14 policy_engine pull-down, CG-15 constitution retirement (+R004a/R104/R126)"
MERGE=$(git rev-parse HEAD)   # RECORD IT — this is the single rollback handle
```

`--no-ff` is mandatory: it gives rollback §R2 a one-commit revert handle.

*If a conflict appears in-window despite §0.3* (only plausible file: `test_gen_officer_mcp_config.py`): resolve inline with the §0.3 resolution rule, `git add <file> && git commit` to complete the merge. Any *other* conflict means the main tree moved after §0.1 — prefer `git merge --abort`, close the window via §4, and restage in the worktree.

**2b. Cherry-pick fallback** — ONLY if the Captain rules the merge shape unusable (main tree diverged in a way §0.3 can't pre-clean):

```bash
git merge --abort 2>/dev/null
git cherry-pick $(git rev-list --reverse b9b42d95..feat/germline-window-2)
# as pinned: 3aa93ef8 e0e67ac4 5cfe9453 381e29ae 8d3a76f4 1f0e9342 354ec3d1 ade5cd47
```

Cost of the fallback: rollback becomes N reverts in reverse order instead of one `revert -m 1` (§R2). Prefer aborting back to the worktree over cherry-picking.

**2c. Gates on the main checkout** (python3.12; all five, in order; ~6 min total):

```bash
cd /Users/nate/captains-cabinet
python3.12 -m pytest framework/ -q                                  # full suite — expect ≈3741+ passed (18 skipped ok), 0 failures
bash cabinet/scripts/run-hook-regression.sh                         # 15/15, ALL GREEN
bash cabinet/scripts/check-layer-separation.sh                      # [layer-sep] OK
python3.12 -m pytest framework/tests/test_amendment_doc_lint.py -q  # amendment lint (the 4 window docs are the license for every germline edit)
python3.12 -m pytest framework/tests/test_germline_lockstep_consistency.py -q   # lockstep: 4 lists moved together
python3.12 -m pytest cabinet/scripts/tests/test_gen_officer_mcp_config.py -q    # the §0.3 conflict file specifically
```

The pytest runs are safe beside a live fleet: the repo-root `conftest.py` fence redirects `CABINET_EVENT_LOG_DIR`/`CABINET_UNDO_DIR` away from the live audit ledger (see `pytest.ini` header). **Any red → §R1 immediately. Do not relock a red tree — and do not leave the window open to debug at leisure either: reset, relock, restage in the worktree.**

## 3. Orchestrator — one canary tick, propose-only, flag one-shot (no sudo, ~1–2 min)

```bash
cd /Users/nate/captains-cabinet
CABINET_GATHER_VIA_SOURCE=1 python3.12 framework/acting/run_action_lane.py --dry-run
```

`--dry-run` contract (script header + `main()`): gather + propose + print the would-be cards; **no Telegram, no ledger, no Redis writes** (card-expiry sweep is skipped too). It *does* make LLM calls. The env var is read once, `== "1"`, routing gather through the new `framework/sources/vault_signals.py` seam (`_source_parts`).

**PASS** = exit 0 with either `done: no fresh signals in window` or `DRY RUN — N card(s) would present:` and no traceback. Sanity-eyeball any printed cards.
**Collision** = `done: another action-lane run holds the lock` → a scheduled tick is mid-run; wait ~2 min, rerun.
**FAIL** = traceback / nonzero exit → §R1.

**The flag stays OFF after the canary.** It is a one-shot env var on this command only. Do **not** add `CABINET_GATHER_VIA_SOURCE` to `cabinet/launchd/com.cabinet.action-lane.plist` `EnvironmentVariables` (today: REDIS_HOST/REDIS_PORT only — keep it that way). Flipping it on for the scheduled lane is a separate, later Captain decision after a soak on this merged-but-dark state.

## 4. Captain — CLOSE the window (sudo, ~30s) — **MUST be same day (D3)**

```bash
cd /Users/nate/captains-cabinet
sudo bash cabinet/scripts/germline-lock.sh lock
# expect: "LOCKED <n> germline targets (schg). Runtime-written fail-safe files left writable: shared/interfaces/captain-vetoes.yml ..."
bash cabinet/scripts/germline-lock.sh verify     # no sudo — the non-root write-probe IS the proof (running it under sudo proves less)
# expect: "VERIFY OK — write to schg-locked framework/authority/classifier.py was refused (Operation not permitted)"
bash cabinet/scripts/germline-lock.sh status     # expect: "BOUNDARY ARMED"
```

D3 (operative egg plan 2026-07-07): *relock same day — never hold the boundary open while redesigning it.* The relock runs the **merged** `germline-lock.sh`, so it arms the NEW enumeration — `policy_engine.py` now locks at `framework/authority/policy_engine.py`; `skip (absent)` lines for retired paths are expected and fine. If §0.4 used the kill switch, `deactivate` it now.

## 5. Orchestrator — publish, ledger, officer-note (no sudo; boundary already closed)

**5.1 Push (standing authorization — Captain pre-ruled, no fresh ask):**

```bash
cd /Users/nate/captains-cabinet
git push origin feat/germline-window-2                    # the window record
git push origin feat/fidelity-harness-design              # the integration branch with the merge
git push origin feat/fidelity-harness-design:master       # origin/master rides lockstep; local master (809c089f, frozen 2026-06-12) is deliberately untouched
```

**5.2 Ledger** — `docs/plans/operative-egg-ledger-2026-07-07.yml`, commit directly on `feat/fidelity-harness-design` (docs/plans is not germline; no unlock needed), then re-run `git push origin feat/fidelity-harness-design && git push origin feat/fidelity-harness-design:master`:

| row | change |
|---|---|
| `CG-2`, `CG-13`, `CG-14`, `CG-15` | `status: "in-flight"` → `"done"`; note += `merged @ $MERGE; canary dry-run <result>; relocked+VERIFY OK <ts>`; `last_update` → date. CG-2's "canary tick still pending post-merge" clause is closed by §3's result. |
| `R004`, `R104`, `R126` | same flip (R004's (a) run_action_lane half lands; its (b) run_draft_lane half still rides W1A-T1 — keep that clause). |
| `R003` | **note-only, stays `todo`** — it is the B4 `framework/acting` compression row, *not* staged on this branch; append `unblocked: CG-2 source seam merged @ $MERGE`. (The window order named R003 — recorded here as note-only; if a status flip was intended, that is a Captain call, not this runbook's.) |

**5.3 Officer-note** — `captain-decisions.md` is a captain-law ledger: direct Write/Edit **and write-shaped Bash (`cat >>`)** to it are hook-blocked (`pre-tool-use.sh` §5/§5c). The ONLY sanctioned path is `cabinet/scripts/append-interface.sh` (entry on stdin; it provenance-stamps its own `### officer-note — appended by <officer> @ <UTC> [trust:officer]` heading, so the entry text must contain **no `#`/`##` heading lines** — they are rejected as Captain-law masquerade; set `OFFICER=orchestrator` for a clean stamp). The file itself is an untracked runtime surface — never commit it:

```bash
cd /Users/nate/captains-cabinet
OFFICER=orchestrator bash cabinet/scripts/append-interface.sh captain-decisions <<EOF
$(date -u +%Y-%m-%dT%H:%MZ) — germline window 2 closed (orchestrator).
Merged feat/germline-window-2 @ $MERGE into feat/fidelity-harness-design (CG-2 dark gather-rewire, CG-13, CG-14, CG-15; R004a/R104/R126).
Gates: framework full suite + hook-regression 15/15 + layer-sep + amendment lint + lockstep 237 — green on main checkout.
Canary: one CABINET_GATHER_VIA_SOURCE=1 --dry-run tick — <result>. Flag remains OFF pending soak.
Boundary: relocked + VERIFY OK same day (D3). Pushed feat/germline-window-2, feat/fidelity-harness-design, master.
EOF
```

---

## R. ROLLBACK

**R0 — invariant:** the window closes same day (§4 relock + verify) on *every* path below, success or failure. A red tree gets reset, not babysat behind an open boundary.

**R1 — failure IN the window, before relock** (gate red in §2c, canary FAIL in §3, wrong merge):

```bash
cd /Users/nate/captains-cabinet
git merge --abort 2>/dev/null          # if still mid-conflict
git reset --hard "$PRE"                # if the merge committed — tree is still unlocked, so schg paths reset cleanly
git status --porcelain                 # back to §0.1 state
python3.12 -m pytest framework/ -q     # confirm the restored tree is green
```

Then the **Captain still runs §4** (lock + verify — same day, no exceptions), and the orchestrator: no pushes; ledger rows stay `in-flight` with a note (`window 2 aborted <ts>: <one-line reason>`); officer-note records the abort. The branch and worktree are untouched — repair there, re-run §0, request window 3.

**R2 — failure discovered AFTER relock/push** (soak turns something up):

Second Captain mini-window, same shape, ~5 min:

```bash
# Captain (sudo #1):
cd /Users/nate/captains-cabinet && sudo bash cabinet/scripts/germline-lock.sh unlock

# Orchestrator (no sudo):
git revert -m 1 "$MERGE"               # -m 1: parent 1 is $PRE, the pre-window integration tip — one commit undoes the whole window
python3.12 -m pytest framework/ -q && bash cabinet/scripts/run-hook-regression.sh && bash cabinet/scripts/check-layer-separation.sh \
  && python3.12 -m pytest framework/tests/test_amendment_doc_lint.py framework/tests/test_germline_lockstep_consistency.py -q

# Captain (sudo #2):
sudo bash cabinet/scripts/germline-lock.sh lock && bash cabinet/scripts/germline-lock.sh verify
# NOTE: this relock runs the REVERTED (pre-window) enumeration — policy_engine.py re-locks at its old cabinet/scripts/lib path. Expected.

# Orchestrator (no sudo):
git push origin feat/fidelity-harness-design && git push origin feat/fidelity-harness-design:master
```

Ledger: flip the seven §5.2 rows `done` → back to `in-flight`, note += `reverted @ <revert-sha>: <reason>`; strike R003's unblocked note. Officer-note the revert. The canary flag needs no undo — it was never persisted anywhere (plist untouched, one-shot env only). If §2b's cherry-pick fallback was used instead of the merge, there is no `-m 1` handle: revert each pick in reverse order (`git revert <runbook-tip> ade5cd47 354ec3d1 1f0e9342 8d3a76f4 381e29ae 5cfe9453 e0e67ac4 3aa93ef8` — newest-first per `git rev-list b9b42d95..feat/germline-window-2`, which includes the docs-only runbook tip commit) — this is exactly why 2a is the primary path.

**R3 — single-file scalpel** (one bad germline file, everything else sound): `sudo bash cabinet/scripts/germline-lock.sh unlock <path>` → fix via a normal committed change + amendment-doc touch-up on the integration branch → `sudo bash cabinet/scripts/germline-lock.sh lock` + verify. Same-day rule applies.

---

## Appendix A — germline paths this merge writes (why §1 must precede §2)

From `git diff --name-status b9b42d95..feat/germline-window-2`, intersected with the lock enumeration:

- **FILES (schg singles):** `cabinet/scripts/germline-lock.sh`, `cabinet/scripts/policy-shadow.py`, `framework/acting/action_lane.py`, `framework/acting/run_action_lane.py`, `framework/authority/matrix.py`, `framework/learning/gate.py`, `framework/learning/trust_ladder.py`, and the R099 move-in `framework/authority/policy_engine.py` (old `cabinet/scripts/lib/policy_engine.py` deleted).
- **DIRS (schg -R):** `cabinet/scripts/hooks/` (`pre-tool-use.sh`, `post-tool-use.sh`, `post-file-write-memory.sh`), `framework/policies/` (`authority-matrix.yml`, `axes-allowlist.yml`, `base-safety.yml`, `immutable-core.yml`), `memory/golden-evals/` (`eval-019` modified, `eval-002-constitution-readonly.md` **deleted** — unlink inside a locked dir).
- **Untouched by design:** `instance/config/act-first-surfaces.yml` (live ruled file byte-identical; only the `.example` twin is added — R126), `.claude/settings.json` (no settings edits ride this window), the SKIP set (`captain-vetoes.yml`, `action-lessons.yml`, `needs-ledger.jsonl` — runtime fail-safes, never locked).

## Appendix B — state as authored (2026-07-07, for diffing at window time)

- Main checkout: `feat/fidelity-harness-design` @ `e340098b` (origin/master at `9dd8e827` == HEAD~2 — §5.1 catches it up); boundary **ARMED** (41 locked / 0 unlocked of 40 files + 5 dirs — re-verified at re-pin); two in-flight tracked modifications + two untracked files (§0.1 footnote) — tracked mods must reach zero pre-window.
- Worktree branch tip `ade5cd47`: full framework suite **3741 passed, 18 skipped** (~73s wall), hook-regression **15/15 ALL GREEN**, layer-sep **OK**, amendment lint + lockstep **237 passed** (11 + 226), conflict-file tests **17 passed**. (All re-run 2026-07-07 at re-pin.)
- `git merge-tree` prediction: **one CONFLICT** (`cabinet/scripts/tests/test_gen_officer_mcp_config.py`) — re-verified against base `e340098b`; §0.3 clears it pre-window.
- Ledger rows CG-2/CG-13/CG-14/CG-15/R004/R104/R126: `in-flight`, notes ending "awaiting review+merge+relock". R003: `todo` (B4).

## Appendix C — happy-path crib (copy-paste order)

```text
§0  orchestrator  preconditions + §0.3 conflict pre-resolution + Captain go
§1  CAPTAIN sudo  sudo bash cabinet/scripts/germline-lock.sh unlock
§2  orchestrator  git merge --no-ff feat/germline-window-2 -m "merge: germline window 2 — ..."
                  MERGE=$(git rev-parse HEAD)
                  python3.12 -m pytest framework/ -q
                  bash cabinet/scripts/run-hook-regression.sh
                  bash cabinet/scripts/check-layer-separation.sh
                  python3.12 -m pytest framework/tests/test_amendment_doc_lint.py -q
                  python3.12 -m pytest framework/tests/test_germline_lockstep_consistency.py -q
§3  orchestrator  CABINET_GATHER_VIA_SOURCE=1 python3.12 framework/acting/run_action_lane.py --dry-run   # flag stays OFF after
§4  CAPTAIN sudo  sudo bash cabinet/scripts/germline-lock.sh lock
                  bash cabinet/scripts/germline-lock.sh verify        # VERIFY OK, same day — D3
§5  orchestrator  git push origin feat/germline-window-2
                  git push origin feat/fidelity-harness-design
                  git push origin feat/fidelity-harness-design:master
                  ledger rows CG-2/13/14/15 + R004/R104/R126 → done (R003 note-only) → commit + re-push
                  officer-note → append-interface.sh captain-decisions (stdin heredoc; never cat >> — hook-blocked)
```

*Sudo recap: §1 and §4 only. If any other step appears to need sudo, stop — something is wrong with the plan, not with the permissions.*
