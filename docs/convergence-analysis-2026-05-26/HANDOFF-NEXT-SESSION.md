# Handoff to Next Session — Convergence-v2 Merge

**Created:** 2026-05-26
**Author:** Opus 4.7 (1M ctx) session that built the original convergence work
**For:** Whoever picks this up next (likely another Opus session)
**Status:** Ready to execute. Captain has approved the strategic pivot via this handoff.

---

## TL;DR

We're NOT merging the `claude/convergence` branch as-is. An independent agent audited it and found real bugs + CC-native gaps that I verified with file:line citations. The new plan:

1. Cut a **new branch `claude/convergence-v2`** from the parent's `codex/claude-native-org-foundation` (which has the modern Claude-native plumbing).
2. **Port** convergence's modular `framework/<subsystem>/` packages + 582 tests + scenario evals + role evals + self-improvement modules into v2.
3. **Fix** the path bugs convergence introduced.
4. **Keep** parent's CC-native plumbing (TaskCreated/Completed hooks, `--agent` launch, `name:` frontmatter, `${CLAUDE_PROJECT_DIR}` hook paths).
5. Apply the **CC-native gap report's Sprints A-D** to push from 51% → ~80% CC-native.

Total effort: 1-2 days for the merge (R1-R10), +2-3 days for Sprints A-D.

---

## Why this pivot — verified facts

Convergence branch (`/Users/nate/captains-cabinet/.claude/worktrees/convergence/`, on `claude/convergence`) has **confirmed bugs** I introduced or inherited and didn't catch:

| Bug | File | Issue | Severity |
|---|---|---|---|
| `$SCRIPT_DIR/..` off-by-one | `cabinet/scripts/bootstrap-project.sh:32` | Resolves to `cabinet/`, not repo root | HIGH — breaks product onboarding |
| Same off-by-one | `cabinet/scripts/verify-launchagents.sh:25` | Same issue | HIGH — broken Mac verification |
| `../..` off-by-one | `cabinet/scripts/hooks/session-task-inject.sh:6` | Resolves to `cabinet/`, not repo root | HIGH — mission task injection broken on Mac |
| `/opt/founders-cabinet/...` hardcoded | `.claude/settings.json` (all hook commands) | Won't work outside Docker | HIGH — entire hook chain dead on Mac unless symlinked |
| No `name:` in agent frontmatter | `.claude/agents/*.md` | Stale CC format | MED — agents not properly registered |
| No `--agent` launch | `cabinet/scripts/start-officer-mac.sh:143` | Doesn't probe new CC CLI flag | MED — officers don't get session-wide agent identity |
| No `TaskCreated`/`TaskCompleted` hooks | `.claude/settings.json` | Missing entire CC native task lifecycle bridge | HIGH — relies on regex-based `post-subagent.sh` instead |

**Parent codex** (`/Users/nate/captains-cabinet/`, on `codex/claude-native-org-foundation`, head `988de78`) has all of the above CC-native plumbing correctly wired, but lacks convergence's modular framework (zero `framework/<subsystem>/` dirs — it's one 2,057-line `cabinet/scripts/lib/org_runtime.py` with only 13 test files).

So neither branch is complete. The merge takes the best of both.

---

## Branch + worktree map

```
/Users/nate/captains-cabinet                        — parent repo, on codex/claude-native-org-foundation (head 988de78)
    ↑ THIS is where convergence-v2 should be cut from

/Users/nate/captains-cabinet/.claude/worktrees/convergence
    branch: claude/convergence (13 commits, +12k insertions, 582 tests)
    ↑ Mine convergence's framework/ + tests/ + scripts FROM here

/Users/nate/captains-cabinet/.claude/worktrees/funny-fermi-8daf32
    branch: claude/funny-fermi-8daf32 (≈ master)

/Users/nate/captains-cabinet/.claude/worktrees/rebuild-analysis
    detached HEAD at a08bcac (origin/claude/clever-tesla-CS3Su-rebuild)
    ↑ Can be deleted — only used for the original analysis dossier

/Users/nate/captains-cabinet/.claude/worktrees/nice-jackson-33075a
    sibling worktree, unrelated
```

---

## Mac state at end of last session

These were left on the user's Mac. Don't reinstall; verify they exist:

- **Homebrew installs**: `tmux 3.6b`, `redis 8.8.0`, `gettext 1.0` (envsubst), `gh CLI`, `tailscale-cask` (failed install — needs sudo)
- **Redis**: running as `brew services` background service (PONG verified)
- **LaunchAgents deployed in `~/Library/LaunchAgents/`**:
  - `com.cabinet.heartbeat-watchdog.plist` — registered with launchctl, idle PID `-` (timer daemon, fires every 5min)
  - `com.cabinet.cost-summary.plist` — same
- **Stub plist** at `/tmp/cabinet-stub-supervisor-test.plist` — created but never registered. Safe to delete.
- **NOT installed**: Apple Developer cert (`security find-identity` shows 0 valid identities), Tailscale (sudo required), TCC consents.

If user wants a clean slate before next session:
```bash
launchctl bootout gui/$(id -u)/com.cabinet.heartbeat-watchdog 2>/dev/null
launchctl bootout gui/$(id -u)/com.cabinet.cost-summary 2>/dev/null
rm ~/Library/LaunchAgents/com.cabinet.{heartbeat-watchdog,cost-summary}.plist
rm /tmp/cabinet-stub-supervisor-test.plist
# Optional: brew services stop redis
```

---

## Documents the next session MUST read first (in this order)

1. **This file** — `docs/convergence-analysis-2026-05-26/HANDOFF-NEXT-SESSION.md` (you're reading it)
2. **The gap report** — `docs/convergence-analysis-2026-05-26/cc-native-gap-report.md` (lays out the 16 specific CC-native gaps + Sprints A-D)
3. **The original convergence plan** — `docs/convergence-analysis-2026-05-26/05-convergence-plan.md` (sets context for what convergence was trying to do)
4. **Phase 9 log** — `docs/convergence-analysis-2026-05-26/phase-9-log.md` (final state of convergence; what tests pass)
5. **Parent's CLAUDE.md** — `/Users/nate/captains-cabinet/CLAUDE.md` (the parent codex branch's working philosophy)

---

## The merge plan: R1–R10

### R1 — Cut branch + baseline (30 min)

```bash
cd /Users/nate/captains-cabinet
git checkout codex/claude-native-org-foundation
git pull --ff-only origin codex/claude-native-org-foundation 2>/dev/null || true   # if pushed; OK if not
git checkout -b claude/convergence-v2
git worktree add /Users/nate/captains-cabinet/.claude/worktrees/convergence-v2 claude/convergence-v2
cd /Users/nate/captains-cabinet/.claude/worktrees/convergence-v2

# Verify parent's tests pass as baseline
python3 -m pytest cabinet/scripts/lib/ -q 2>&1 | tail -5
# Document: <N> tests baseline pass count
```

Copy this handoff doc + the analysis dossier to the new branch:
```bash
mkdir -p docs/convergence-analysis-2026-05-26
cp -r /Users/nate/captains-cabinet/.claude/worktrees/convergence/docs/convergence-analysis-2026-05-26/* docs/convergence-analysis-2026-05-26/
git add docs/
git commit -m "docs: copy convergence analysis dossier to v2 branch as merge reference"
```

### R2 — Port framework modules wholesale (1-2 hours)

```bash
CONV=/Users/nate/captains-cabinet/.claude/worktrees/convergence
V2=/Users/nate/captains-cabinet/.claude/worktrees/convergence-v2

# Wholesale copy — these directories don't exist in parent at all
cp -r $CONV/framework/events $V2/framework/
cp -r $CONV/framework/roles $V2/framework/
cp -r $CONV/framework/missions $V2/framework/
cp -r $CONV/framework/ovi $V2/framework/
cp -r $CONV/framework/measurement $V2/framework/
cp -r $CONV/framework/policies $V2/framework/
cp -r $CONV/framework/outbox $V2/framework/
cp -r $CONV/framework/learning $V2/framework/
cp -r $CONV/framework/products $V2/framework/
cp -r $CONV/framework/schemas $V2/framework/ 2>/dev/null || true

# Library code that convergence added
cp $CONV/cabinet/scripts/lib/policy_engine.py $V2/cabinet/scripts/lib/
cp $CONV/cabinet/scripts/lib/work_graph.py $V2/cabinet/scripts/lib/
cp -r $CONV/cabinet/scripts/lib/tests/* $V2/cabinet/scripts/lib/tests/ 2>/dev/null || mkdir -p $V2/cabinet/scripts/lib/tests && cp -r $CONV/cabinet/scripts/lib/tests $V2/cabinet/scripts/lib/

cd $V2
PATH="/Users/nate/Library/Python/3.9/bin:$PATH" python3 -m pytest framework/ cabinet/scripts/lib/tests/ -q
# Expect most to pass; fix any that fail due to parent's slightly different env

git add framework/ cabinet/scripts/lib/policy_engine.py cabinet/scripts/lib/work_graph.py cabinet/scripts/lib/tests/
git commit -m "feat(merge): port convergence framework modules — events, roles, missions, ovi, measurement, policies, outbox, learning, products"
```

### R3 — Reconcile mission compiler (1-2 hours)

Parent has richer task fields in `cabinet/scripts/lib/org_runtime.py` around line 777 (Mission Compiler v2): `owner`, `acceptance_criteria`, `evidence`, `verifier`, `risk`, `rollback`, `budget`, `dependencies`, `captain_attention`. Convergence's `framework/missions/compiler.py` uses simpler fields (`description`, `assigned_role`, `verification_criteria`).

**Action:** read both files; copy the richer field set into `framework/missions/compiler.py`'s WorkNode dataclass; update mission compilation logic to populate the new fields when present in `outcomes.yml`. Keep the modular structure. Update tests in `framework/missions/tests/test_compiler.py` to verify new fields.

```bash
# After edits
cd $V2
git add framework/missions/ cabinet/scripts/lib/org_runtime.py
git commit -m "feat(merge): fold parent's Mission Compiler v2 richer fields into framework/missions/"
```

### R4 — Fix the convergence path bugs (30 min)

Three files need surgical fixes. Each uses `$SCRIPT_DIR/..` (or `../..` from a hooks subdir) that resolves one level too high.

**`cabinet/scripts/bootstrap-project.sh:32`** — change:
```bash
# WRONG (in convergence):
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# CORRECT:
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
```

**`cabinet/scripts/verify-launchagents.sh:25`** — same fix.

**`cabinet/scripts/hooks/session-task-inject.sh:6`** — change `../..` → `../../..`:
```bash
# Note: hook scripts are at cabinet/scripts/hooks/, one level deeper
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
```

After fixing, audit ALL `cd .../..` patterns in `cabinet/scripts/` and `cabinet/cron/` to ensure each resolves to the repo root:
```bash
grep -rn "cd .*\\.\\.\\b" $V2/cabinet/ | head -20
# Verify each one
```

### R5 — Port operational scripts (30 min)

```bash
cp $CONV/cabinet/scripts/work-graph-complete.sh $V2/cabinet/scripts/
cp $CONV/cabinet/scripts/bootstrap-project.sh $V2/cabinet/scripts/      # already fixed in R4
cp $CONV/cabinet/scripts/backup.sh $V2/cabinet/scripts/
cp $CONV/cabinet/scripts/verify-launchagents.sh $V2/cabinet/scripts/    # already fixed in R4
cp $CONV/cabinet/scripts/bootstrap-captain-triplet.sh $V2/cabinet/scripts/

cp -r $CONV/cabinet/scripts/task_adapters $V2/cabinet/scripts/
cp $CONV/cabinet/scripts/task_sync_runner.py $V2/cabinet/scripts/

cp $CONV/cabinet/cron/mission-supervisor.sh $V2/cabinet/cron/
cp $CONV/cabinet/cron/outbox-relay.sh $V2/cabinet/cron/
cp $CONV/cabinet/cron/role-evals-weekly.sh $V2/cabinet/cron/
cp $CONV/cabinet/cron/task-sync.sh $V2/cabinet/cron/

# Verify syntax
for f in $V2/cabinet/scripts/*.sh $V2/cabinet/cron/*.sh; do bash -n "$f" || echo "FAIL: $f"; done

git add cabinet/scripts cabinet/cron
git commit -m "feat(merge): port convergence operational scripts (mission supervisor, outbox relay, work-graph-complete, bootstrap, backup, task adapters)"
```

### R6 — Port skills + docs (30 min)

```bash
mkdir -p $V2/.claude/skills
cp -r $CONV/.claude/skills/cabinet-work-graph-complete $V2/.claude/skills/
cp -r $CONV/.claude/skills/cabinet-org-status $V2/.claude/skills/
cp -r $CONV/.claude/skills/cabinet-route-tasks $V2/.claude/skills/

cp $CONV/docs/cabinet-slash-commands.md $V2/docs/
cp $CONV/docs/mac-mini-deploy-runbook.md $V2/docs/

# Captain triplet + Phase 3 wiring patches — only the new logic, NOT the entire convergence hook
# (parent has its own captain-rule-encoder.sh that needs the two-count rule + cross-officer broadcast layered in)
# See docs/convergence-analysis-2026-05-26/phase-3-log.md for the diff to apply

git add .claude/skills docs/cabinet-slash-commands.md docs/mac-mini-deploy-runbook.md
git commit -m "feat(merge): port convergence skills + slash-commands doc + Mac deploy runbook"
```

### R7 — Port Phase 3 (Captain triplet 4th/5th loop wiring) (30 min)

Don't copy convergence's `captain-rule-encoder.sh` wholesale — parent has its own. Instead, layer in just the two new mechanisms:

1. **Two-count rule** — Redis INCR keyed on `cabinet:patterns:seen:$RULE_ID`, 30-day TTL, broadcast on count ≥ 2
2. **Cross-officer broadcast** — iterate `instance/roles/active/*.yml`, call `notify-officer.sh` for each non-self officer

Reference convergence's diff:
```bash
diff $V2/cabinet/scripts/hooks/captain-rule-encoder.sh $CONV/cabinet/scripts/hooks/captain-rule-encoder.sh
# Apply the new sections (REDIS_HOST_LOCAL setup, RULE_COUNT block, broadcast block)
```

Also copy `bootstrap-captain-triplet.sh` (R5 already did) and verify the hooks reference the parent's path scheme.

```bash
git add cabinet/scripts/hooks/captain-rule-encoder.sh
git commit -m "feat(merge): layer two-count rule + cross-officer broadcast into parent's captain-rule-encoder.sh"
```

### R8 — Verify Mac-native plumbing intact (15 min)

Parent already has the right wiring; just verify it's still intact after the merge:

```bash
cd $V2
# TaskCreated/Completed hooks present?
grep -E '"TaskCreated"|"TaskCompleted"' .claude/settings.json
# Hooks use $CLAUDE_PROJECT_DIR or bash command (not /opt path)?
grep '"command":' .claude/settings.json
# Agents have name: frontmatter?
for f in .claude/agents/*.md; do head -3 "$f"; done
# start-officer-mac.sh probes --agent?
grep -n -- "--agent" cabinet/scripts/start-officer-mac.sh
```

If anything got accidentally clobbered by the R-phase copies, restore from parent. Settings.json + agent frontmatter + start-officer-mac.sh should be UNTOUCHED from parent in this merge.

### R9 — Apply gap report Sprints A-D (~2-3 days)

See `docs/convergence-analysis-2026-05-26/cc-native-gap-report.md` for the full plan. Quick summary:

- **Sprint A** (half-day): wire PreCompact + PostCompact hooks, standardize `hookSpecificOutput` wrapping, set `permissions.defaultMode: "auto"`, enable CC native voice, wire `SessionStart` hook
- **Sprint B** (half-day to day): lift top 10 foundation skills from `memory/skills/` to `.claude/skills/<name>/SKILL.md`, add `skills:` frontmatter to each agent
- **Sprint C** (half-day): author 6 `.claude/commands/cabinet-*.md`, write statusLine script, convert one bash hook to `type: prompt`
- **Sprint D** (half-day): plugin marketplace packaging (`marketplace.json` + plugin manifest)

These take the branch from 51% → ~80% CC-native.

### R10 — Final validation + merge prep (30 min)

```bash
cd $V2
PATH="/Users/nate/Library/Python/3.9/bin:$PATH" python3 -m pytest framework/ cabinet/scripts/lib/tests/ cabinet/scripts/task_adapters/tests/ -q
# Expect ~600+ tests pass

# Scenario evals
python3 -c "import sys; sys.path.insert(0,'.'); from framework.measurement.scenario_runner import _discover_scenarios, _SCENARIOS, run_scenario; _discover_scenarios(); [print(run_scenario(n).passed, n) for n in _SCENARIOS]"

# Role evals
python3 -c "import sys; sys.path.insert(0,'.'); from framework.measurement.role_eval_runner import run_all; r=run_all(); print(f'{sum(1 for x in r if x.passed)}/{len(r)} pass')"

# OVI
python3 framework/ovi/compute.py --from-events --window-days 7

# Mac setup gate
bash cabinet/scripts/setup-mac.sh --check

# Plist render lint
for tmpl in cabinet/launchd/*.template.plist; do tmpf=$(mktemp); CABINET_SOURCE_REPO="$V2" HOME="$HOME" USER="$USER" envsubst < "$tmpl" > "$tmpf"; plutil -lint "$tmpf"; rm -f "$tmpf"; done

# When all green:
git log --oneline claude/convergence-v2 -20
git push -u origin claude/convergence-v2   # CAPTAIN APPROVES this push
```

---

## Open decisions awaiting Captain

(These came up in the prior session; pick the answer before starting R3 / R7.)

1. **Mission compiler reconciliation (R3)** — fold parent's richer task fields into convergence's modular compiler? **My recommendation: yes**. Decision: ___
2. **`org_runtime.py` (2,057 lines)** — keep alongside, gradually decompose into matching `framework/<subsystem>/` modules, or treat as eval-target reference? **My recommendation: gradually decompose during Sprint A-D**. Decision: ___
3. **`claude/convergence-v2` branch name** — OK? Or different. **My recommendation: keep**. Decision: ___
4. **Push timing** — push v2 to origin after R8, or hold until Sprint A-D done? **My recommendation: push after R8 (so Captain can review the merge before more changes pile on)**. Decision: ___

---

## Quick reference: what's where

| Convergence asset | Location | Action |
|---|---|---|
| 9 `framework/<subsystem>/` packages | `framework/events/`, `roles/`, `missions/`, `ovi/`, `measurement/`, `policies/`, `outbox/`, `learning/`, `products/` | Wholesale copy (R2) |
| 582 pytest | `framework/*/tests/`, `cabinet/scripts/lib/tests/`, `cabinet/scripts/task_adapters/tests/` | Wholesale copy (R2) |
| Operational scripts | `cabinet/scripts/{work-graph-complete,bootstrap-project,backup,verify-launchagents,bootstrap-captain-triplet}.sh` | Copy with bug fixes (R4+R5) |
| Cron drivers | `cabinet/cron/{mission-supervisor,outbox-relay,role-evals-weekly,task-sync}.sh` | Wholesale copy (R5) |
| Cabinet skills | `.claude/skills/cabinet-{work-graph-complete,org-status,route-tasks}/SKILL.md` | Copy (R6) |
| Phase 3 captain-rule-encoder patches | Two-count Redis + cross-officer broadcast | Layer into parent (R7) |
| Docs/dossier | `docs/convergence-analysis-2026-05-26/*` + `cabinet-slash-commands.md` + `mac-mini-deploy-runbook.md` | Copy (R1 + R6) |

| Parent codex asset | Location | Action |
|---|---|---|
| TaskCreated/Completed hooks | `.claude/settings.json` | KEEP — don't overwrite from convergence |
| `claude-task-bridge.py` | `cabinet/scripts/claude-task-bridge.py` | KEEP |
| Agent frontmatter (`name:` + `skills:`) | `.claude/agents/*.md` | KEEP |
| `--agent` launch probe | `cabinet/scripts/start-officer-mac.sh` | KEEP |
| `${CLAUDE_PROJECT_DIR}` / bash command hooks | `.claude/settings.json` | KEEP |
| `activate-project.sh`, `mac-preflight.sh`, `mac-tcc-gate.sh` | `cabinet/scripts/` | KEEP |
| `org_runtime.py` Mission Compiler v2 fields | `cabinet/scripts/lib/org_runtime.py:777` | EXTRACT into framework/missions/ (R3) |

---

## Captain-physical items still pending

These 8 items remain Captain-only and are NOT advanceable by any software agent. They block the eventual MacMini-readiness final cutover, NOT the v2 merge itself:

1. Apple Developer ID enrollment ($99/yr) + Keychain cert import
2. Codesign + notarize claude binary on the actual MacMini
3. TCC permissions granted (System Settings GUI)
4. Tailscale install (requires sudo) + sign-in
5. UPS hardware shutdown test
6. 72-hour soak on the actual MacMini
7. Force-crash supervisor restart test (Captain decides when to burn Anthropic tokens)
8. Power-cycle test on the MacMini

These are runbook execution items per `docs/mac-mini-deploy-runbook.md`. Convergence-v2 merge is independent of them.

---

## First commands for the next session

```bash
# 1. Read this doc first
cat /Users/nate/captains-cabinet/.claude/worktrees/convergence/docs/convergence-analysis-2026-05-26/HANDOFF-NEXT-SESSION.md

# 2. Read the gap report
cat /Users/nate/captains-cabinet/.claude/worktrees/convergence/docs/convergence-analysis-2026-05-26/cc-native-gap-report.md

# 3. Skim parent CLAUDE.md to understand its working philosophy
head -200 /Users/nate/captains-cabinet/CLAUDE.md

# 4. Confirm the Captain's answers to the four Open Decisions

# 5. Execute R1
cd /Users/nate/captains-cabinet
git checkout codex/claude-native-org-foundation
git checkout -b claude/convergence-v2
git worktree add /Users/nate/captains-cabinet/.claude/worktrees/convergence-v2 claude/convergence-v2

# 6. Continue with R2 → R10 per the plan
```

---

## What the next session should NOT do

- Don't try to satisfy the prior `/goal` condition (the MacMini-readiness checklist with 8 Captain-only items). The prior Captain ran `/goal clear` for a reason.
- Don't merge convergence-v1 to master. Convergence-v1 stays as a research/reference branch.
- Don't auto-push v2 to origin without Captain approval after R8.
- Don't reinstall the LaunchAgents that are already deployed; verify state first.
- Don't try to test items 2-8 from the Captain-physical list (Apple cert, TCC, Tailscale, UPS, 72h, crash-test, power-cycle). They're explicitly in the deploy runbook, not the v2 merge plan.

---

## Open question: convergence branch fate

After v2 lands and tests pass, what happens to `claude/convergence`?

Options:
- **A.** Delete the branch (it's superseded by v2)
- **B.** Keep it as `claude/convergence-archive` for reference
- **C.** Keep it on origin as a historical artifact (don't push if not yet pushed)

**My recommendation: B** — local archive only, don't push to origin. The dossier is preserved in v2.

---

## Contact / who to ask

- Captain: Nate (you)
- The independent agent's review that triggered this pivot — preserved in this conversation's transcript; key claims verified inline in this doc
- The 4 phase logs (0, 1, 2, 3, 5, 6, 7, 8, 9) in `docs/convergence-analysis-2026-05-26/phase-*-log.md` document the original convergence's reasoning per phase — useful reference when porting modules

---

## Done

When R1-R10 complete + Sprints A-D landed + Captain ratifies → the v2 branch becomes the new operational base. Cabinet is then ready for the runbook-driven MacMini deployment (the 8 Captain-physical items).

Good luck. The hard architectural decisions are made; this is mostly mechanical porting + the gap-closing sprints. Don't overthink it.
