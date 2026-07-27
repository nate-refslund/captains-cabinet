# Onboarding ordering inversion — read the operator's world, stop interviewing it

**Type:** design of record + adjudication summary. **Date:** 2026-07-26.
**Gate:** direction gate, two models run independently and blind (Fable 5 arm A,
Opus 5 arm B), diff surfaced and adjudicated in writing before work started.
**Supersedes:** nothing. It corrects the ORDER of the existing onboarding path;
no schema was redesigned.

---

## 1. The ruling this implements

The north star — *the cabinet becomes the company and runs the company* — is an
AIM, not an entry bar. The cabinet must be valuable to someone who will never
reach the apex: a developer inside a large company, who does not get to run it.
The product is **capability expansion at whatever altitude the operator
occupies**, and the mechanism is **connect → explore (read-only) → structure
into memory → then converse.**

*"What is your company?"* is a question this system should ask far less often
than it did, and never as a precondition for existing.

## 2. What the tree actually did, measured

Both arms hit a hard stop independently, at two different places:

| Where | What it did |
|---|---|
| `cabinet/scripts/generate-instance.py` | RAISED *"answers must declare at least one lane under lanes:"* — and a lane **is** a product (`framework/docs/work-model.md`). |
| `cabinet/scripts/first-briefing.sh` → `framework/onboarding/genesis.py` | Composed outcome cards **only** from the answers file. Never from anything read. |
| `cabinet/scripts/hatch.sh` (`--defaults`) | Fabricated a placeholder lane `First Lane`, which the cards were then derived from. |

So a developer inside a large company owns no lane, and the only paths were
inventing one or taking the placeholder. The first real briefing scored 1 of 3
and the Captain's verdict on its cards was *"the cards were irrelevant"* —
which is the **predicted output** of a briefing that never read the operator's
world, not a rendering defect. Fixing composition is the point; a better
renderer is not.

Both arms also found, independently, that Onboarding v2's **First Window**
(`framework/onboarding/journey.py`) already does the read-under-charter part
well — bounded scan, hash-bound charter, secret redaction, purge receipts,
validated on three NON-founder personas — and that **its output fed nothing.**

## 3. The adjudicated fix — an ORDERING INVERSION, not new substrate

1. **`lanes` become DERIVABLE.** `lanes: []` is accepted when a derived-estate
   artifact exists for this deployment. An EMPTY estate still passes: *"I
   looked and found nothing"* is a legitimate lane-less state. What stays
   refused is `lanes: []` with no artifact at all — nobody ever looked.
2. **Discovery proposes lanes for ratification.** `formation.py`'s
   `DISCOVERY_DONE` stops being an IOU stub and structures the ratified First
   Window into `instance/onboarding/formation/derived-estate.yml`, deriving
   `instance/config/lanes-proposed.yml` beside it. Ratification is the Captain
   copying a row into the answers file and re-running the generator — nothing
   self-activates, and no generator, compiler or officer reads the proposal
   filename.
3. **The estate is a first-class input beside the answers file.** Genesis
   composes subject cards from estate entities WITH CITATIONS (declared lanes
   still win — they are the Captain's own statement), and `run_briefing
   --local-render` carries them plus a provenance card naming sources,
   ownership class and every refusal count.
4. **The interview is demoted to the residual questions.** When there is
   neither a lane nor an entity, ONE residual card asks the three questions
   that are un-derivable by construction — *which of these sources are yours to
   grant? · of what you saw, what matters this week? · what must this never
   touch?* — plus the human-shaped seed question (*what do you do / how can I
   best serve you*) for an operator who has connected nothing. A cabinet with
   no sources must still never be a dead end.
5. **Altitude reaches two live surfaces or it is decoration.**
   `mission.altitude` ∈ {contributor, project, team, function, company}:
   * **preset SELECTION** — `resolve_preset()` is now the ONE resolution
     (`cabinet.preset` > `mission.altitude` > `org_shape`) and `hatch.sh` calls
     it via `--print-preset` instead of re-deriving a mapping that had already
     drifted past `cabinet.preset`. `contributor`/`project` resolve to
     `presets/personal`, the one kit with no C-suite;
   * **proposed-CARD derivation** — the proof line changes shape.
   ABSENT is a first-class answer meaning UNKNOWN, and it reproduces the
   pre-altitude behaviour byte-for-byte.

### Why the proof line changes, and what the promise is

The growth engine is graduated autonomy over evidence, and its ceiling classes
(`framework/authority/grants.py`) are `external_comms, deploy_prod, spend,
secrets, network_write, credentials_grant`. At contributor/project/team
altitude **every one of those belongs to the employer, not the operator** — a
grant is valid only when signed by the authority root, and a developer inside a
large company is not the authority root over their employer's production. No
autonomy setting manufactures authority the operator does not hold.

So a card whose proof is *a shipped, deployed change* is unreachable there **by
org chart, not by cabinet quality**. At those rungs the proof becomes
proposal-shaped: a written proposal citing evidence assembled across what the
operator already reads, delivered to whoever owns the decision, plus the
decision it changed.

> **Authority is granted downward and capped by org chart. Context is assembled
> sideways and capped only by access.** The promise at low altitude is expanded
> REACH and PROPOSAL QUALITY — never expanded permission. Stated that way to a
> stranger, or the first developer who reads "grow into running the company"
> and hits the ceiling correctly concludes the framework lied to them.

## 4. Safety properties, and the ones deliberately NOT claimed

* **No new read.** `framework/onboarding/estate.py` opens no folder, no socket
  and no connector, and calls no LLM. Every fact is re-derived from artifacts
  the journey wrote after the Captain ratified a hash-bound charter. Pinned by
  a test that deletes the granted folder and asserts an identical document.
* **No file bodies.** Paths, hashes and counts only — the journey persists no
  raw contents and neither does this.
* **Provenance survives the read**, per source: root, ownership class, charter
  hash, manifest hash, entry count, and EVERY refusal with its reason. Silent
  skips destroy auditability, so the count is rendered even when it is zero.
* **Ownership is ASKED, never inferred — and asked once, by somebody else.**
  The sibling source-ownership landing put the ingest ceiling in
  `framework/authority/ownership.py` and bound the declared class and its
  authority basis INTO the charter hash the Captain approves. This unit
  reconciled onto it rather than keeping a second vocabulary: the estate reads
  the class off the charter, rides `access_record` for the per-source record
  shape, and asks `writes_permitted` — the same function the task adapters
  route through — whether a derived lane may be proposed write-capable.
  Anything that is not the operator's own proposes `task_system: none` and no
  repos, so ratifying it cannot point a write-capable adapter at an estate they
  do not own. That is the write-back danger (`cabinet/scripts/task_adapters/
  base.py` — *"canonical wins … the next sync overwrites the external
  change"*) closed at this surface too. `unclassified` survives only as the
  marker for a journey persisted before that ceiling existed, and is treated as
  non-owned.
* **Undo takes its effects with it.** `undo_run` supersede-archives the derived
  estate and the lanes proposal along with the run, when they carry that run's
  id. An undo that leaves its effect in place is not an undo.
* **NOT claimed:** the framework cannot verify the truth of an ownership
  attestation. The class is recorded, the question is forced, and the record
  carries `attestation_limit` saying so in its own words; that is the
  enforceable boundary and it is stated rather than implied.
* **NOT built:** any ingest engine, and any new connector. The gate ruled that
  the sweep and its consumer land as ONE unit, and that the employee-slice
  experiment settles whether cross-system ingest beats single-system reads
  before an ingest engine is built. `INGEST_DONE` and everything after it stay
  honest IOU stubs on purpose.

## 5. The gap that was open here, and the sibling landing that closed it

While this unit was in flight, `contributor`/`project` resolved to
`developer` — the closest FIT, not a solution, because every shipped preset
stood up a C-suite for a company the operator may not run and
`presets/personal/` was a placeholder whose README forbade activating it. The
generator said so in its printed next steps rather than letting a stranger
discover it.

The sibling **personal-preset landing** (resulting-order item 8,
`docs/plans/personal-preset-live-2026-07-27.md`) activated that preset: no
C-suite, Navigator / Librarian / Reviewer, "someone who owns a project, not a
company; a developer inside a large organisation". So the mapping was
CORRECTED to `personal` — with the gap closed, "closest fit" had become the
wrong fit, since `developer` is a flat copy of `work` and ships the C-suite
this altitude does not have. `hatch.sh` also gained that landing's existence
guard on the resolved slug, kept on the single-resolution path.

## 6. Surfaces

| Path | Role |
|---|---|
| `framework/onboarding/estate.py` | the derived-estate contract: derive, write, load, usability gate, proposed lanes |
| `framework/onboarding/formation.py` | `DISCOVERY_DONE` derives it; undo supersedes it |
| `framework/onboarding/genesis.py` | consumes it for cards + provenance; altitude shapes the proof |
| `cabinet/scripts/generate-instance.py` | `lanes: []` gate · `mission.altitude` validation · `resolve_preset` · `--print-preset` · `--defaults --altitude` |
| `cabinet/scripts/hatch.sh` | `--altitude` · preset selection asks the generator |
| `instance/onboarding/formation/derived-estate.yml` | the artifact (gitignored runtime state) |
| `instance/config/lanes-proposed.yml` | the ratification surface (propose-only) |
