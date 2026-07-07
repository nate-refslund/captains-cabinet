---
name: brain-audit
description: Audit and repair Nate's memory estate (Obsidian vault + embeddings index + graph + memories store) when brain quality regresses. Use when the memory-curator-health service pages cos (Redis trigger "BRAIN-QUALITY REGRESSION"/staleness), when the frozen-core-14 probe gate fails after any wave, when the Memory Curator has self-frozen, or on a Captain ask to check brain quality. Runs the audit fleet -> fix waves -> adversarial verify -> probe gate loop, and owns the curator freeze/unfreeze runbook.
---

# Skill: Brain Audit (memory-estate quality loop)

**Status:** installed (brain-quality Wave F hand-off 2026-07-06; staging header stripped 2026-07-07 so the frontmatter parses — audit #7)
**Owner:** cos (escalation target of `com.cabinet.memory-curator-health`)

## When to use

- A Redis trigger arrives: `BRAIN-QUALITY REGRESSION — ...` or `sensor output
  missing/stale` (sent by `cabinet/scripts/check-brain-health.py`, daily 06:45).
- The frozen-core-14 probe gate fails after any estate-mutating wave.
- The Memory Curator has **self-frozen** (freeze flag present — see runbook) and the
  cause must be diagnosed before unfreezing.
- The Captain asks for a brain-quality check or the daily digest reports a regression.

## Ground truth & paths (read these, never re-derive from memory)

| Artifact | Path |
|---|---|
| Sensor output (2x/day, 06:00/18:00) | `~/.screenpipe/state/brain_health.json` |
| Frozen-core-14 probe suite | `~/.screenpipe/state/brain-probes/probes/` + `run_probes.py` + `probe_gate.py` |
| Graded expectations (oracle) | `~/.screenpipe/state/brain-probes/expectations.json` |
| Durable baseline | `~/.screenpipe/state/brain-probes/baseline-20260705.json` (p@1 0.929 / p@3 0.929) |
| Pinned invariants | `eval-021-brain-retrieval-quality.md` (golden eval; staged copy in `brain-probes/staging/`) |
| Suppressed person stems | `~/.screenpipe/state/person-merge-plan-20260705/suppressed-slugs.json` |
| Vault | `~/Obsidian/screenpipe-brain/` |
| Embeddings index + search | `~/.screenpipe/pipes/embeddings/` (`search.py`, `lib.py`, `index.py`) |
| Curator pipe | `~/.screenpipe/pipes/memory-curator/` (`sync.py` + `brakes.py` + `fix_classes.py` + `digest_send.py`) |
| Curator ledger / digest / backups | `~/.screenpipe/state/curator-ledger.jsonl` · `state/curator-digest.md` · `state/curator-backups/<run_id>/` |
| Wave ops ledgers (orchestrator fix waves) | `~/.screenpipe/state/ops-ledger-*.jsonl` |
| Synthetic drill fixtures | `~/Obsidian/screenpipe-brain/3-People/_synthetic-drill/` (never delete; `type: synthetic-drill`) |

**Invariants that may never regress (eval-021):** frozen-core-14 p@1 ≥ 0.90, p@3 ≥ 0.93;
zero hits under excluded/parked prefixes (`3-People/_noise/`, `8-Archive/`,
`7-Resources/My-Prompts/`, `*/_archived-dups*`, `0-Self/`); per-hit text ≤ 2,000 chars,
max 2 chunks/file; `as_of` fencing fail-closed (unstamped = excluded, never mtime);
suppressed stems never re-appear as live 3-People root notes.

## Methodology — audit fleet → fix waves → adversarial verify → probe gate

This is the loop that took the estate from p@1 0.5 to 0.929 across waves 1–4b. Run it
in this order; never skip the gate.

### 1. Audit fleet (read-only, parallel)

Fan out parallel READ-ONLY finder agents, one per estate surface, each returning
file:line-grounded findings (no fixes yet): retrieval (re-run `run_probes.py`, diff
per-probe grades against `expectations.json` + baseline — per-probe, not just
aggregate), integrity (dangling links / orphans / dup clusters / content_ts % /
suppression re-mints — the sensor's `integrity` block is the checklist), index hygiene
(excluded-prefix leaks, giant chunks, db size/churn vs baseline), capture watchdog
(inbound silence, writer green-but-silent, prompt backpressure — the sensor's
`watchdog.flags`), and provenance (ops ledgers for the most recent mutating runs —
curator or wave — that precede the regression). Findings without a reproducible
file:line or query→hit trace are hypotheses, not findings.

### 2. Fix waves (mutating — braked)

- One lane per defect class, **disjoint by file**; no two vault-mutating lanes run
  concurrently (the vault has no worktree isolation) — land → gate → land.
- **Standing doctrine, every mutation:** timestamped backup first; append to an ops
  ledger (`~/.screenpipe/state/ops-ledger-<lane>-<date>.jsonl`) with **explicit action
  vocab** (`park` ≠ `park-copy` ≠ `archive` ≠ `alias_add` ≠ `restamp` — say exactly
  what happened, old→new paths); **park, never delete**; **explicit paths only — never
  bulk-select by existence checks or ledger-action inference**.
- Root-cause the writer before backfilling its output.
- **Incident history (why the brakes exist — the design precedents):** (i) a re-park
  pass once mass-moved **240 LIVE canonical notes** by misreading ledger action vocab;
  (ii) vault-mirror parking was silently reverted by a 30-min regenerating writer —
  durable dedup must act on the SOURCE (e.g. archive the Monday item), not the mirror;
  (iii) a cross-board Monday archive destroyed 3 legit dual-tracking items (no API
  unarchive exists — Nate had to restore by hand). Any fix that smells like these
  three: stop, propose instead.
- Identity/cross-person merges are **propose-only, forever** — never autonomous.

### 3. Adversarial verify

A fresh-context reviewer (not the fixing agent) re-derives each fix from the diff +
ledger: correct target? action vocab honest? backup present? blast radius as claimed?
Reviewer findings are fixed before gating. (This pass is what caught the 3 cross-board
Monday violations in Wave D-adjacent dedup.)

### 4. Probe gate (frozen-core-14)

Run `python3 ~/.screenpipe/state/brain-probes/run_probes.py` (or `probe_gate.py`)
against the live index and compare per-probe grades to `expectations.json` +
`baseline-20260705.json`. **Gate doctrine:** gate-fail ⇒ freeze the next wave →
restore the failing wave's pre-backup → diagnose → re-run the gate before proceeding.
The frozen-core-14 is the cross-wave comparable denominator; new probes report
separately and enter the gating set only via curated promotion (a curator fix-class).
Oracle edits (co-canonical adds, re-points to kept survivors) must be adjudicated +
independently reviewed and noted inline in `expectations.json` — never edited to force
a pass.

## Curator freeze / unfreeze runbook

The Memory Curator (screenpipe pipe `memory-curator`) **self-freezes** when its
pre/post probe subset regresses after one of its mutating runs (auto-revert + freeze =
its self-veto brake).

- **Freeze flag (core's contract, brakes.py):** `~/.screenpipe/state/curator-freeze` —
  presence = frozen; JSON record `{why, ts, run_id}` (an unreadable freeze file STILL
  freezes — conservative). While present the curator refuses all mutating runs
  (sensing/digest continue). The wave↔curator mutex is separate:
  `~/.screenpipe/state/wave-in-progress.lock` — an orchestrator fix wave holds it and
  the curator skips mutating runs while it exists (set it before your own fix waves).
- **To freeze manually** (before your own fix waves, or on suspicion):
  `echo '{"why":"<reason>","ts":"'$(date -u +%FT%TZ)'","run_id":"manual-cos"}' > ~/.screenpipe/state/curator-freeze`
  Hard-stop variant: unload the curator's launchd job if one is loaded (house
  convention: screenpipe plists load in-session); the freeze flag alone already
  refuses every mutation, so it is the primary brake.
- **Diagnose while frozen:** read the curator's latest ops-ledger rows (explicit
  old→new per mutation), its auto-revert record, and the pre/post probe subset scores;
  restore from the timestamped backups if the auto-revert was partial.
- **To unfreeze — ALL of:** (1) root cause written down (ledger or tier2 note);
  (2) offending mutations reverted or ratified; (3) frozen-core-14 gate GREEN again;
  (4) then delete `~/.screenpipe/state/curator-freeze` (and reload the plist if you
  unloaded one). Unfreeze is deliberately a human file-delete after review — never
  unfreeze on a red gate; that is exactly the drift the brake exists to stop.
- **Live-fire drill fixtures:** the synthetic entity in `3-People/_synthetic-drill/`
  (dangling `Zz-Drill-Target` link + NULL content_ts, quarantine tag
  `type: synthetic-drill`) is the only sanctioned target for curator drills — never
  drill on a real person/product; consumers read the live index during drills.

## Reporting

One digest line per audit through the brain-curator digest channel (informational,
kind=brain-curator, kill switch `CURATOR_TG=0`), plus `log_reasoning` + the ops ledger
for every mutation. Regressions you could not close: page the Captain in the daily
digest with the decide-by date — never per-item ask-spam (interaction contract,
outcome-system-self-003 node brain-003-d).
