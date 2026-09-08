# Expansion adjudication — the tap: an outcome-lifecycle package and a work-receipts read model

**Date** 2026-09-07 · **Class** `framework_production_modules` (+3) ·
**Members** `framework/outcomes/__init__.py`, `framework/outcomes/ratify.py`,
`framework/missions/receipts.py`

Two arms were authored blind on identical briefs — **arm A: Fable 5.1**, **arm B:
Opus 5 (1M)** — and adjudicated in writing before any code was written. This
document is the repository-side record of that gate for the three production
modules the landing adds. It exists because the expansion registry in
`cabinet/config/cognitive-architecture-contract.yml` refuses an anonymous
net-new member of a bijection class: the question a budget bump cannot answer is
not "how many?" but "which, and was the merge into an existing organ actually
refused?"

## What the modules are for

A Cabinet could propose an outcome and had no way of being given one. The
proposed-card file's own header told the operator to open a YAML file and move a
row by hand — a control nobody can reach from a phone, which makes it not a
control. The tap replaces that sentence with one writer and three doors
(terminal, web, chat), and a read model that lets a person see what happened
afterwards.

## Member 1 — `framework/outcomes/ratify.py`

The one writer of both outcome files: it validates a proposal row's projection
against `framework/schemas/outcome.schema.json`, copies the row into the live
mission file with `status: active`, marks the proposal `ratified` rather than
deleting it, and emits `captain_outcome_ratified` carrying the door and the
principal. Every door calls it; none of them composes YAML.

**Merge refuted:** `framework/onboarding/genesis.py::merge_proposals` — arm A's
proposal put the writer beside genesis, which owns the proposals file, its
digest and its atomic writer. Refused on three properties of that organ rather
than on preference.

- **Different direction of authority.** `merge_proposals` DERIVES drafts: it is
  the propose-only end of the pipe and its whole contract is that nothing it
  writes can activate itself. Ratification is the opposite act — a decision that
  turns a draft into something the org may compile. Putting the act that grants
  authority inside the organ whose stated invariant is that it grants none would
  make that invariant unreadable.
- **Different lifetime and different producers.** Genesis runs once, at hatch.
  Proposals will come from more than genesis — a discovery pass, a supervisor's
  gap, an operator's own words — and every one of them ratifies through the same
  door. A ratify function reachable only through the onboarding package would
  have to be imported by organs that have no business importing onboarding.
- **Different blast radius.** `merge_proposals` writes one file that the compiler
  never reads by design (`instance/config/outcomes-proposed.yml`). The tap writes
  the file the compiler DOES read. Folding the second into the module whose
  safety story is "the compiler ignores my output" would delete that story.

Second candidate refused: `framework/onboarding/journey.py` — schg-locked
constitutional path, and its own header states that its state lives below
`instance/onboarding/v2`, "a surface the mission compiler never reads".

**Consumer:** `cabinet/scripts/lib/org_runtime.py` — its `outcomes ratify`
verb, the superseded twin that wrote SQLite and never the file the compiler
reads, now delegates to this module through the terminal door. The other
consumers are `cabinet/dashboard/src/actions/outcomes.ts` (the web door's Ratify
button), `cabinet/scripts/outcome-ratify.sh` and
`framework/frontdoor/binder_wire.py`; the registry names the one that resolves
inside the census's own mutant tree, which copies `framework/**` and
`cabinet/scripts/**.py` and no dashboard sources at all.

## Member 2 — `framework/outcomes/__init__.py`

The package itself, import-inert: a docstring and nothing else. It exists because
the ruling above put ratification in its own home rather than inside onboarding,
and a package needs a marker. It is listed as its own member because the census
counts modules, not packages, and an unlisted file is an unregistered member
whatever its size.

**Merge refuted:** `framework/onboarding/genesis.py::merge_proposals` — the same
refusal as member 1; this file exists only because that merge was refused.

**Consumer:** `framework/frontdoor/binder_wire.py` — the chat door does
`from framework.outcomes import ratify`, which imports this package by name.

## Member 3 — `framework/missions/receipts.py`

A read model over the event ledger, and nothing else: it replays the declared
work vocabulary — ratified, started, renewed, released, completed, failed,
verified, gap, and the three update kinds — and shapes each row into something a
person can scan. It emits nothing and writes nothing.

**Merge refuted:** `framework/events/emitter.py::replay` — the obvious fold: the
ledger reader already exists, and a caller could pass event types to it directly.
Refused on three counts.

- **`replay` returns raw ledger rows**, whose payload shape differs per event
  type. Every surface that wanted receipts would have to re-derive the same
  per-type field mapping, which is the duplication this module removes.
- **The vocabulary is a decision, not a filter argument.** Which event types
  appear on a receipts surface is a declaration about what the org considers part
  of a responsibility's life; passing it as a parameter at each call site means
  two surfaces can silently disagree about what a receipt is.
- **`emitter` is a writer.** It owns emission, the per-file lock, and the valid
  type registry. A read model that renders for people has no business living
  inside the module every writer imports; the dashboard would then import the
  emitter to read.

**Consumer:** the `dashboard` service declared in `cabinet/services.yml` —
`cabinet/dashboard/src/lib/work-receipts.ts` shells to this module's `--json`
CLI and renders it as the second section on `/receipts`. The registry names the
service rather than the file for the same reason as member 1: the census's
mutant tree carries `cabinet/services.yml` and no dashboard sources.

## Line mass

`framework_production_noncomment_lines` rises with the two real modules and the
door wiring in `binder_wire.py`, `genesis.py`, `advisor.py` and
`run_briefing.py`. Raised visibly rather than bought with a temporary allowance:
the tap is a permanent organ — it is the only way a proposal becomes a
responsibility — so an allowance would promise a deletion gate that will never
fire.

## Provenance

Per the 2026-07-07 full-autonomy grant + the 2026-07-21 ownership-on-GO grant.
Two blind arms (Fable 5.1, Opus 5 1M) on identical briefs, adjudicated in writing
before implementation; the ruling on this class was arm B's home
(`framework/outcomes/`) over arm A's (`framework/onboarding/`), for the reasons
recorded above. Direction of record: the 2026-08-26 Captain ruling that the
target operator decides direction and delegates everything below it — a decision
they cannot record from a phone is a decision the org cannot honour.
