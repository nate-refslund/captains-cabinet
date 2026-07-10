# Germline Window 3 — Captain Runbook (ONE ceremony: H0 pull + CANDOR + W4 + W8)

**Lands:** `feat/germline-window-3` → the live checkout (`~/captains-cabinet` on the live box), together with the H0 gateway pull. Window 2 executed 2026-07-07 (its branch is fully contained in master); this file is now the WINDOW-3 contract, same pattern.
**Authored:** 2026-07-10 by the orchestrator (Fable 5). **Re-pin every sha at window time — base branches keep advancing.**
**Captain wall-clock cost:** ~10 minutes, two sudo commands (steps 1 and 4 — the ONLY Captain-sudo steps). Everything else is orchestrator work with no sudo and no passwordless-sudo path (the boundary's whole design — see `cabinet/scripts/germline-lock.sh` header).
**Apply contract:** `docs/proposals/germline-amendment-candor-2026-07-10.md` — reply **`"apply candor law"`** in the Captain DM before opening the window.

## What this window lands

1. **H0 — arm the Attention Gateway on the live checkout** (the standing NEEDS-CAPTAIN row): the live checkout is held pre-gateway; the unlock → `git pull --ff-only` / merge of current `origin/master` brings the merged gateway (P1–P5) and everything since onto the running deployment. Until this pull, gateway code is code, not behavior.
2. **CANDOR LAW (germline VALUE, Captain ruling 2026-07-10):** `framework/constitution-base.md` §Values — mandatory evidence-cited dissent BEFORE any compliance path; dissent-then-obey (Captain vetoes bind absolutely); agreement-as-target banned org-wide (generalizing D12: silence is never agreement/consent); optimization target = mission/products, authority root = captain; "serve the mission, answer to the captain, flatter no one"; candor genome / tone expression (D15c). Plus the Chair candor clause (`presets/portfolio/agents/cos.md`), the lane-CEO template clause (`presets/portfolio/agents/_lane-ceo.md.template`), and the eval body `memory/golden-evals/eval-024-candor.md` (its runnable half — `cabinet/evals/candor/` harness + fixtures + runner section EVAL-024-CANDOR — is already live, non-germline).
3. **W4 rider — lessons-splice** (agi-wires dead-wire #4): `framework/acting/action_lane.py` gains the `%%LESSONS%%` slot + `render_lessons()` + `lessons=` param; `framework/acting/run_action_lane.py` loads the SIE-1 ledger best-effort — Captain corrections become standing proposer instructions instead of evaporating.
4. **W8 rider — head→tail** (dead-wire #8): `cabinet/scripts/hooks/session-start.sh` captain-patterns/intents boot injection `head -100` → `tail -40` — the freshest encoded preferences finally load at boot (append-only ledgers put the newest law at the tail).

## 0. Preconditions — orchestrator verifies BEFORE requesting the window (no sudo)

```bash
cd ~/captains-cabinet
git fetch origin feat/germline-window-3 master feat/fidelity-harness-design
git -C .claude/worktrees/germline-window-3 status --short          # must be clean
# predict merge conflicts of window-3 onto CURRENT master (0 expected at stage time):
git merge-tree "$(git merge-base origin/master origin/feat/germline-window-3)" \
  origin/master origin/feat/germline-window-3 | grep -c "<<<<<<<" || true
# staged-branch suites (pinned green at stage time; re-run at window time):
( cd .claude/worktrees/germline-window-3 && \
  python3.12 -m pytest framework/acting/tests framework/tests/test_amendment_doc_lint.py -q && \
  bash -n cabinet/scripts/hooks/session-start.sh )
# fleet quiet + kill switch state:
redis-cli GET cabinet:killswitch
```

## 1. Captain — OPEN the window (sudo, ~15s)

```bash
sudo bash cabinet/scripts/germline-lock.sh unlock
# expect: "UNLOCKED all germline targets. RE-LOCK when done: sudo bash cabinet/scripts/germline-lock.sh lock"
```

## 2. Orchestrator — H0 pull + merge + full gates ON THE MAIN CHECKOUT (no sudo)

```bash
cd ~/captains-cabinet
git pull --ff-only origin feat/fidelity-harness-design   # own branch current first
git merge --no-ff origin/master                          # H0: gateway + everything since
git merge --no-ff origin/feat/germline-window-3          # candor + W4 + W8
# gates — ALL green BEFORE relock:
python3.12 -m pytest framework/ -q
python3.12 -m pytest cabinet/scripts/tests -q
bash cabinet/scripts/check-layer-separation.sh
bash cabinet/scripts/run-golden-evals.sh                 # EVAL-024-CANDOR must be green
```

Conflict fallback: resolve on the main checkout (window-2 rule: keep master's semantics, take the branch's staged hunks); if a file resists, cherry-pick the window-3 commits one at a time instead of the merge.

## 3. Orchestrator — canaries (no sudo, ~2 min)

```bash
# W8: fresh boot context carries the TAIL sections
echo '{}' | OFFICER_NAME=cos bash cabinet/scripts/hooks/session-start.sh | grep -c "last 40 lines"
# W4: composed proposer prompt renders the lessons block or the no-lessons
# note — NEVER the literal %%LESSONS%% token (dry-run, propose-only):
python3.12 -m framework.acting.run_action_lane --dry-run 2>&1 | grep -F "%%LESSONS%%" && echo W4-RED || echo W4-OK
# CANDOR: harness self-test 16/16 (review tighten 2026-07-10: negation/retraction guard + 3 bypass fixtures)
python3.12 cabinet/evals/candor/harness.py --self-test | tail -1
```

## 4. Captain — CLOSE the window (sudo, ~30s) — MUST be same day (D3)

```bash
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh verify
# expect: "VERIFY OK — write to schg-locked ... was refused (Operation not permitted)"
```

## 5. Orchestrator — publish, ledger, officer-note (no sudo; boundary already closed)

```bash
git push origin HEAD
# Captain decision-ledger apply record: paste the §4 block of
# docs/proposals/germline-amendment-candor-2026-07-10.md via the sanctioned interface:
bash cabinet/scripts/append-interface.sh captain-decisions   # entry on stdin
# ledger/plan-doc parity rows for W4/W8 (agi-wires handback bookkeeping), same commit.
```

## R. ROLLBACK

- **R1 (pre-relock):** `git reset --hard <pre-merge sha>` on the main checkout, then relock — the window simply didn't happen.
- **R2 (post-relock mini-window):** unlock → `git revert -m 1 <window-3 merge sha>` → gates → relock. The amendment doc's **One-revert rollback** names every germline file; no half-state exists (the runner section tolerates the eval body's absence; W4 reverts atomically with both acting files).
- **R3 (scalpel):** single-file revert inside an unlock window for exactly one regressed path — last resort; prefer R2.

---
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>


## W-WARROOM — war-room census joins the germline plane

Staged DARK on this branch (command-center Stage 1, 2026-07-10). Rides the
SAME unlock→pull→lock ceremony as H0 + candor + W4 + W8 — no extra Captain
steps beyond the one window.
**Apply contract:** `docs/proposals/germline-amendment-war-room-census-2026-07-10.md`
(names the four Ring-0 entries for the amendment-doc lint; one-revert
rollback = `git revert 875416fd`).

What it changes (all four germline lists in lockstep + one lane file):
1. `framework/policies/immutable-core.yml` — four war-room paths enter
   Ring-0: `framework/attention/{situations,queue,hygiene,queue_card}.py`
   (they decide what the Captain SEES — admission law, census, closure —
   so an officer edit would re-weight its own visibility).
2. `cabinet/scripts/germline-lock.sh` FILES — same four (lock skips them
   until the master merge lands the files; arms automatically after).
3. `cabinet/scripts/hooks/pre-tool-use.sh` §5 arm + §5b GERM_PATH_RE —
   same four.
4. `framework/policies/base-safety.yml` germline-readonly — same four.
5. `framework/acting/run_action_lane.py` — the card-expiry sweep journals
   a `demote` feed row per expiry (H5: expiry is routing, never a verdict;
   the situations view already re-types bare expiries — this makes the
   demotion first-class for P6 attention cells). Best-effort, no behavior
   change to the sweep itself.

Verify inside the window (after pull, before lock):
    python3.12 -m pytest framework/tests/test_germline_lockstep_consistency.py -q
    python3.12 -m pytest framework/attention/tests/ -q
