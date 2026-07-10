# AGI-wires 0709 — handback (feat/agi-wires-0709)

Independent validation lane, 2026-07-09. Source: the 07-08 52-agent report
(`~/agi-brainstorm-cabinet-analysis-2026-07-08.md`), every wire re-verified
against CURRENT code + operative-egg-ledger before implementation. All work
is report-only measurement, flag-gated-dark wiring, or internal-surface
repair — **zero germline files edited** (verified against the
germline-lock.sh set per commit). Promotion mechanics stay defer-captain
per D5/CG-10 throughout.

## What landed (17 commits)

| Wire | Commit | What |
|---|---|---|
| W2 | `af9ed8a1` | judge-calibration armed — daily cron row (D5 step 1a, ledger A2); stale future-B5 comment fixed |
| W3 + §4.3-5 | `28e2939b` | F1 label mine: monthly→weekly, D1 knobs (with_intent/emit_scored) ON, lane roster; SIE-9 sim runner |
| W6 + §4.3-4 | `cbe8f4e7` | instance/roles/active reader into boot-prompt assembly — flag-gated DEFAULT-OFF + parity audit script |
| W7 | `07c82f1f` | OrgSource.open_commitments = active outcomes → CG-2 gather seam; CABINET_GATHER_VIA_SOURCE=1 in the action-lane row after shadow-parity green |
| W9 | `bc9acd66` | prediction scorer — Brier/calibration series from action-card confidences vs UNDO-3/binder ground truth (ledger A10) |
| R6 | `c90ed66a` | label-starvation repair joins the standing pull (SOV-8; `_refuse_captain_paths` unchanged) |
| W10a | `e0d90e2b` | injection screen at intake enqueue — strips invisible chars, marks trigger shapes, never drops (default ON, `CABINET_INTAKE_SCREEN=0` kill switch) |
| W10b | `b935930a` | research-sweep (cro→cos) + backlog-refine (cpo→cos) retargeted, env-overridable, scheduled; roster-guard test for every cron |
| W10c | `a9e5ac95` | ORG-SENSES-2: cabinet:triggers:* verbatim append-only archive + trigger-archive embeds (read-only Redis; 441 entries pending first sweep) |
| W10d | `a2825ef9` | calendar perception tick — first `due_event_triggers` consumer + calendar→intake via the signed EventKit reader (15 min) |
| §4.2 growth | `f5809fb2` | labels_7d + time_to_graduation_days in the falsifier line; OVI learning_rate = per-day rate (components.yml range rescaled) |
| §4.2 cost | `dc8dd75b` | cost_7d in the falsifier line — window spend + cost_micro_per_label off the revived cost ledger |
| Rec 3.4 | `875cdb97` | run-golden-evals.sh --model parametrization + report-only per-model scalar series (lib/golden-scalar.sh) |
| Rec 3.3 | `ee895026` | charter-only shadow arm (sidecar; policy-shadow.py untouched) — engine-vs-charter divergence series |
| Rec pairs | `51e51a77` | preference-pair miner — action-lessons + captain-patterns → preference-pairs.jsonl |
| §4.2 beliefs | `1bec4358` | memory-contradictions propose-only supersession pass (near-duplicate + contradiction-cue; NEVER applies) |
| §4.2 skills | `197aaf72` | skill induction drafts become runnable (deterministic procedure distillation; promotion gate unchanged) |

## Deploy steps (Captain / main-checkout session — NOT done from this lane)

1. **Regenerate + reload plists** (`cabinet/scripts/generate-plists.py`, then
   Nate reloads — no launchctl from lanes). New/changed rows:
   `judge-calibration` (daily), `fidelity-f1` (now WEEKLY Mon 07:15, knobs
   in-row), `prediction-calibration` (daily 08:20), `research-sweep`
   (09:05/15:05), `backlog-refine` (08:35), `exhaust-archive` (04:40),
   `calendar-intake` (900s), `charter-shadow` (05:10), `preference-pairs`
   (05:20), `memory-contradictions` (Sun 05:30), and the `action-lane` row
   env gains `CABINET_GATHER_VIA_SOURCE=1` (W7 — flip lands at plist regen;
   revert = delete one env key).
2. **W6 role-registry flag**: reader ships DEFAULT-OFF. Before any flip run
   `bash cabinet/scripts/audit-role-parity.sh` (added with W6) and reconcile
   the 4 role YMLs vs `.claude/agents/*.md` (P0 officer-config-contamination
   lesson). The flip itself + REPORT_ONLY=0 arming stay **Captain's** per the
   07-07 memory-audit ruling ("arm after soak"); restart the 6h soak clock
   once the reader is live so the soak observes reality.
3. **First exhaust-archive sweep** will archive ~441 backlogged trigger
   entries and queue embeds (500/sweep flood guard means the backlog drains
   over ~1 run + memory-worker ticks) — expected, not a fault.
4. **Watch first ticks**: prediction-calibration (expect thin
   `n_ground_truthed` until label volume grows — by design), calendar-intake
   (needs the EventKit helper binary built + TCC grant on the target box;
   fail-closed = reports errors, enqueues nothing), charter-shadow (needs
   org_events history; empty store = honest n=0 line).
5. **Ledger bookkeeping** (docs-track-code, Captain-plane file): mark A2
   (judge-calibration scheduling) done; note ORG-SENSES-2 organ shipped
   (gate: spot-check one aged trigger id from org memory after its Redis
   window expires); A10 scorer shipped.

## Explicitly NOT done (defer-captain, by design)

- Any consumption of the golden-eval scalar / calibration series /
  charter-shadow divergence as an autonomy GATE (D5/CG-10 promotion
  mechanics).
- policy_engine deletion (Rec 3.3 only produces the pricing evidence).
- Auto-apply of supersession proposals (precision must be measured first).
- REPORT_ONLY=0 self-improvement arming; W6 flag flip (Captain's).
- Germline edits of any kind; `sudo germline-lock.sh` state untouched.
