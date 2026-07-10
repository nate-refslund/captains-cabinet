<!-- DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated. -->

**DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated.**

# Show HN draft — Captain's Cabinet

Prepared private-side for the Perfect Cabinet launch kit (Wave C). Every
number below is the honest number as of 2026-07-10; the pre-publication
checklist at the bottom must be green before this leaves the box.

---

## Title options (HN style: ≤80 chars, no hype words)

1. `Show HN: Captain's Cabinet – an AI org on your Mac; every act leaves a receipt`
2. `Show HN: Run an AI company, not an assistant – what/why/cost/undo receipts`
3. `Show HN: Captain's Cabinet – governed delegation for Claude Code agents`
4. `Show HN: AI officers under launchd, with an authority matrix and a kill switch`
5. `Show HN: Captain's Cabinet – agents that must earn autonomy on evidence`

Recommendation: option 1 (name + platform + the one differentiator) or
option 5 (the mechanism as the hook). Avoid 2 as a title if the body already
opens with the tagline — redundant.

---

## Body draft

Captain's Cabinet is a framework for running a small autonomous AI
organization on a Mac. Officers — persistent Claude Code sessions under
launchd and tmux — own domains (a product, a pipeline, ops) and work
continuously; you are the Captain and steer the whole org from Telegram:
briefings, one-card decisions, a kill switch. It is not another assistant.
The tagline is the design goal: don't hire an AI assistant — run an AI
company, where every action leaves a receipt: what, why, cost, undo.

The category story in one line: agents have already proved **execution**
(OpenClaw) and **accumulation** (Hermes); the axis nobody has claimed is
**governed delegation**. What's genuinely different here: every
consequential action starts as a proposal, and when the org does act, you
get a receipt — the exact content it produced (what), the reason (why), the
measured spend or an honest "cost: unattributed" (never an invented number),
and an undo handle with a real 48-hour window backed by a write-ahead
journal and a deterministic inverse — no inverse registered means it never
acted unattended in the first place. Above that sits an authority matrix
with six hard-ceiling classes that no amount of proven confidence ever
lifts — external comms, production deploys, spend, secrets, network writes,
credential grants — enforced in code and asserted in CI. A fleet-wide kill
switch fails closed — enforced in code: if its state store is unreachable,
the gate halts rather than proceeds. Anyone can throw it; Captain-only
resume is today enforced by process, not yet by code. Even the org's own
boot is propose-only: the genesis step writes proposal cards a mission
compiler never reads, so nothing self-activates.

Honest limitations, because Show HN deserves them: it is macOS-first (Apple
silicon; the org lives in launchd user agents), it requires Claude Code with
a Max subscription plus a Telegram bot token, and it is pre-1.0. The
move-in bar we hold ourselves to is a full org hatch in under 90 minutes —
that bar is ratified but has NOT yet been timed end-to-end on a bare Mac;
the measured numbers today are a clean-room hatch of ~8 seconds with
dependencies already present, and 1–2 seconds from proofs-green to the
first briefing. So the honest claim is "first receipt in minutes once
hatched" — this is not a five-minute install, and week one is deliberately
approval-heavy: everything consequential is proposed to you until action
classes graduate on evidence.

Feedback we actually want:

1. Attack the governance — can you construct an action that reaches a
   hard-ceiling effect without a Captain gate?
2. Is the receipt grammar (what/why/cost/undo) missing a field you'd need
   to trust a delegated act?
3. Undo semantics — where would a deterministic inverse lie to you?
4. Is the propose-first week-one approval load tolerable, and what would
   you want auto-graduated first?
5. If you'd run this anywhere other than a Mac, what's the smallest port
   you'd accept?

`<REPO-URL — inserted at publication; repo is private until CG-7 clears>`

---

## First-comment draft (technical depth, posted by the author)

Some architecture notes for the technically curious:

**Three layers, assembled at session start.** `framework/` is the universal
base — constitution, safety boundaries, policies, schemas, and the
evidence/authority/gate machinery; identical for every deployment.
`presets/<active>/` shapes it to a use case (officer archetypes,
terminology) — preset addenda are append-only: assembly writes the full
framework base first, then appends the addendum (a containment test
asserts the assembled constitution comes from the base), so an addendum
can add restrictions but cannot remove base rules. `instance/` is your
deployment only: config, directions, roles, working notes. Nothing
personal is baked into the framework, and there's a proof of that (below).

**The evidence engine.** One append-only consequence ledger records every
proposal, every Captain verdict (captured mechanically, in-process with the
action — never by an LLM's self-report), and every machine-probed outcome,
joined by correlation IDs. Graduation math reads the ledger per action
class — never per agent — and the authority matrix maps risk class ×
earned confidence to propose / act-with-undo / act-and-tell. Demotion is
automatic on wrong verdicts, detected fabrication, model upgrades, or
evidence starvation — a dead-man watchdog pages and revokes autonomy when
verdicts stop flowing. Autonomy is a computed, demotable property of one
ledger, never a vibe.

**No loop may edit its own judge.** The enforcer and judge plane — policy
engine, authority matrix code, undo journal writer, kill switch, the gate —
is locked macOS system-immutable (`schg`), which only root can clear and
officers have no passwordless sudo. A germline change is a deliberate,
sudo-gated Captain act, not a clever prompt.

**Self-improvement through a gate.** The org drafts its own skills and
playbook changes, but every change is admitted by an eval gate the org
cannot edit. Improvements compound because the gate holds, not because the
proposer is trusted.

**The null-hatch proof.** CI boots the framework from a sandbox copy of the
committed tree with NO captain data, NO personal-sensing stack, no instance
source binding — and the personal-data dir present but unreadable, so any
latent read fails loudly instead of passing by accident. The framework must
come up with honest empties everywhere. That's the proof the egg carries no
baked-in captain.

**Verification posture.** The framework suite is ~4,069 tests, plus
script/fixture suites and CI proof gates (null-hatch, clean-room ratchets,
dry renders). A daily falsifier line appends acts, reversal rate, and
graduated cells — numbers chosen so that if the system is NOT working, the
data will say so. Vetoes are recorded verbatim and matched by exact fields
(never an LLM's paraphrase); silence never clears one.

**Demo honesty.** The seeded day-one demo receipt is labeled `demo: true`,
is never written to the live undo journal, and a fresh org's `/receipts`
page is honestly empty until the org has actually acted. Demo artifacts
always say they are demo; honest empties beat invented data.

License: BSL 1.1 (free to self-host, fork, modify, and use — production
included; the Additional Use Grant reserves only hosted/embedded offerings
to third parties that compete with the licensor's paid managed service;
each version converts to Apache 2.0 after four years).

---

## Pre-publication checklist (CG-7 — every box is Captain-gated)

- [ ] Captain approves publishing at all (external comms = hard ceiling).
- [ ] Employer-IP clearance in writing (see
      `docs/launch/business-model-proposal.md`, CG-7 section).
- [ ] Repo actually public at a final URL; `<REPO-URL>` placeholder replaced.
- [ ] Bare-Mac end-to-end hatch timed; either the ≤90-min bar is met and can
      be cited as measured, or the body's "not yet timed" phrasing stays.
- [ ] Kill-switch claims reconciled repo-wide before posting:
      `framework/safety-boundaries-base.md` says only the Captain
      activates/deactivates; the guide says anyone-halts with Captain-only
      resume via a typed resume token (implemented nowhere); and both
      `cabinet/scripts/kill-switch.sh deactivate` and the dashboard toggle
      are unauthenticated deletes — align docs and code, or keep this
      draft's softened claim ("resume enforced by process, not yet by
      code") in the published body.
- [ ] Any screenshots attached went through the hero-demo A6 review gate
      (Testburg-only, nav out of frame, banned-pattern re-read).
- [ ] Title picked from the options above; no edits that add hype words.
