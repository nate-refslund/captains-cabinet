# Germline Amendment — CANDOR LAW (candor-over-comfort) + window-3 riders W4/W8

**Status: AWAITING CAPTAIN. Apply token: reply `"apply candor law"` in the Captain DM, then run the window-3 ceremony in `WINDOW-RUNBOOK.md` (one unlock window covers H0 pull + this amendment + the W4/W8 riders).**

Staged DARK on branch `feat/germline-window-3` (worktree from `origin/master`; pattern: germline-window-2). Nothing below is live until the Captain's unlock → merge → relock ritual. Prior rulings are REFERENCED here, never re-pasted (do NOT re-paste already-logged rulings into this doc): SOVEREIGN POSTURE (2026-07-05), ACT-AND-DRAFT (2026-07-04), EARN-DEMOTION (2026-07-03/04), D12 silence-breaker (sovereign spec 2026-07-04 — told-and-silent is never consent), D15c persona-vs-genome (egg analysis 2026-07-06).

---

## 1. The ruling being encoded (Captain, 2026-07-10)

**CANDOR LAW — candor-over-comfort, a germline VALUE:**

- **Mandatory dissent on contradicting evidence**, evidence-cited, stated BEFORE any compliance path. Agreement-without-evidence is the named failure mode; softening/flattery/praise-first framing never substitute for the dissent.
- **Dissent-then-obey** — once dissent is on the record the Captain's ruling binds absolutely; vetoes bind; no re-litigating.
- **Agreement-as-target banned org-wide**, generalizing D12: neither Captain silence nor Captain approval-rate is ever an optimization target or reward signal; silence is never agreement.
- **Optimization target = mission/products; authority root = captain.** "Serve the mission, answer to the captain, flatter no one."
- **Candor is genome; tone is expression (per D15c)** — per-persona tone/register is configurable; truthfulness and the dissent duty are not.

Already live NON-GERMLINE (landed on `feat/fidelity-harness-design`, 2026-07-10): the deterministic eval harness + fixtures at `cabinet/evals/candor/`, the `run-golden-evals.sh` section **EVAL-024-CANDOR**, the telegram-communication drafting-law note, the Hatching Charter candor covenant ("your cabinet will disagree with you, loudly, with evidence — its vetoes are yours, its silence is never agreement"), and the cabinet-meta orchestrator doctrine.

## 2. Germline edit set (every file staged on the branch)

| File | Change |
|---|---|
| `framework/constitution-base.md` | new §Values — CANDOR LAW (the four clauses above + enforcement pointer) |
| `presets/portfolio/agents/cos.md` | Chair candor clause (single human surface; guards lane-CEO payloads for evidence) |
| `presets/portfolio/agents/_lane-ceo.md.template` | lane-CEO candor clause (dissent-first attention payloads; no approval-optimizing loops) |
| `memory/golden-evals/eval-024-candor.md` | NEW eval body in its germline home (dir schg-locked live; runnable half already live at `cabinet/evals/candor/`) |
| `framework/acting/action_lane.py` | **W4 rider** — `%%LESSONS%%` slot + `render_lessons()` (marker-stripped, capped, never-obey preamble) + `lessons=` param on `propose_actions` |
| `framework/acting/run_action_lane.py` | **W4 rider** — best-effort `load_lessons()` at the call site (missing ledger = `[]`; errors degrade, never gate the lane) |
| `cabinet/scripts/hooks/session-start.sh` | **W8 rider** — captain-patterns/intents boot injection `head -100` → `tail -40` (append-only ledgers: freshest law lives at the tail; matches the proven captain-decisions pattern) |

Non-germline files riding the same branch: `framework/acting/tests/test_lessons_splice.py` (12 tests), `framework/tests/test_amendment_doc_lint.py` (this package's lint entry), `docs/proposals/` (this doc), `WINDOW-RUNBOOK.md` (the ceremony).

W4/W8 provenance: agi-wires report 2026-07-08 dead-wires #4 and #8; deliberately NOT done in the agi-wires lane because both files are germline — implemented fresh here so the next window is ONE ceremony: **H0 pull + candor + W4 + W8**.

## 3. Non-entries (explicitly not in this amendment)

- No authority-matrix / posture / grants change — candor is a VALUES amendment; verdict resolution is untouched.
- No new Ring-0 / immutable-core entries **in this candor package** — every path edited by THIS amendment is already inside the locked set (or, for preset/constitution sources, already hook-protected constitution sources). The one-ceremony branch DOES carry a separate rider that adds 4 immutable-core entries: the war-room census germline join (`framework/attention/{situations,queue,hygiene,queue_card}.py`, commit `875416fd`) — its own contract is `docs/proposals/germline-amendment-war-room-census-2026-07-10.md`, not this doc.
- No `shared/interfaces/action-lessons.yml` seed commit — the ledger is runtime-appended (germline-lock SKIP class); `load_lessons()` treats an absent file as `[]` by contract, so committing a header-only file would only invite merge conflicts with live captures.
- External comms stay per-item Captain-approved in every posture (reference: ACT-AND-DRAFT — unchanged, untouched).

## 4. Apply record (paste-ready — the Captain's decision-ledger entry)

```markdown
## CANDOR LAW APPLIED (2026-07-XX)
**What:** Applied the candor germline amendment: constitution §Values CANDOR LAW (mandatory evidence-cited dissent before any compliance path; dissent-then-obey — vetoes bind; agreement-as-target banned org-wide; serve the mission, answer to the captain, flatter no one; candor genome / tone expression), Chair + lane-CEO candor clauses, eval-024 body into memory/golden-evals/, plus riders W4 (lessons-splice into the proposer) and W8 (session-start head→tail).
**Why:** Sycophancy is a capability defect: an org that optimizes for my agreement stops surfacing the evidence I pay it to surface. Candor-over-comfort makes dissent a duty and my veto the binding end of it.
**Captain:** Nate
**Token:** "apply candor law" · ceremony per WINDOW-RUNBOOK.md (sudo germline-lock.sh unlock → git pull --ff-only + merge feat/germline-window-3 → gates → chflags schg relock via sudo bash cabinet/scripts/germline-lock.sh lock)
```

## 5. Verification (run inside the window, before relock)

- `python3.12 -m pytest framework/acting/tests framework/tests/test_amendment_doc_lint.py -q` — green (lessons splice 12/12 + this package's lint).
- `bash -n cabinet/scripts/hooks/session-start.sh` — clean.
- `bash cabinet/scripts/run-golden-evals.sh` — EVAL-024-CANDOR green (16/16 fixture responses — review tighten 2026-07-10 added a negation/retraction guard + 3 sycophancy-vocabulary bypass fixtures on the live branch), suite exit 0.
- Canary: one fresh officer session boot — Captain Patterns/Intents sections show "last 40 lines" (tail), and one `run_action_lane --dry-run` prints either the lessons block or the no-lessons note (never `%%LESSONS%%` verbatim).

**One-revert rollback:** a single `git revert` of the window-3 merge commit inside an unlock window restores every germline file — `framework/constitution-base.md`, `presets/portfolio/agents/cos.md`, `presets/portfolio/agents/_lane-ceo.md.template`, `memory/golden-evals/eval-024-candor.md` (removed again), `framework/acting/action_lane.py`, `framework/acting/run_action_lane.py`, `cabinet/scripts/hooks/session-start.sh` — then relock. The non-germline EVAL-024-CANDOR runner section tolerates the eval body's absence (it never reads the .md) and the W4 splice reverts atomically with both acting files, so no half-state exists. eval-024 removal alone does not disarm candor enforcement (harness + fixtures are non-germline and stay live).

---
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
