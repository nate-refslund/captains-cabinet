# Expansion adjudication — per-source ownership class

**Member:** `framework/authority/ownership.py`
**Class:** `framework_production_modules`
**Gate date:** 2026-07-26 (altitude direction gate, two blind arms: Fable 5 and
Opus 5, independent clones, neither reviewing the other; diff surfaced and
adjudicated in writing before any work started)
**Provenance:** per 2026-07-07 full-autonomy grant + 2026-07-21 ownership-on-GO

## What the gate decided

The gate examined whether the cabinet's connect-by-default posture is safe at
**employee altitude** — a developer inside a large company, where most of the
estate on their laptop belongs to their employer rather than to them. Both arms
reached the same structural finding from opposite entry points, and the resulting
order carries it as item 4:

> Ownership class per source + refuse-on-unclassified + **structural read-only
> for non-owned sources** + sensitivity classes + ingest-side ceiling and the
> surviving per-source record.

The gate also named one ACTIVE hazard already in the tree, in the adapter
contract's own words — *"canonical wins. If an officer changes a task and an
operator changes the same task in the external UI, the next sync overwrites the
external change"* — and ruled that read-only must be **structural** for any
non-owned source, not a configuration flag.

The gate additionally recorded what the framework **cannot** enforce: the truth
of the operator's attestation. It can force the question per source, refuse an
unclassified source, record the answer in the tamper-evident plane, and default
non-owned sources to no-egress. That is stated in the module, in the Charter
payload, and in `docs/source-ownership-and-authority.md`, rather than implied.

This is not hypothetical for this program: the repository itself was flipped
private on 2026-07-14 on an employer-IP ruling, and the egg export manifest
carries that ruling as a scrub rule.

## Why this is a NEW module and not a merge

**Merge candidate examined:** `framework/authority/grants.py::CEILING_RISK_CLASSES`.

That plane answers *"which class of ACT may the cabinet take, and has the
authority root signed a grant for it?"* Its subject is the action; its
membership is the six hard-ceiling risk classes; and a grant is valid only when
signed by the authority root under an schg lock.

The ownership plane answers a different question — *"whose DATA is this source,
and under what right does the operator connect it?"* — and it binds at moments
`grants.py` never sees: before a read (the ingest ceiling), inside a Charter
hash the Captain approves, and at adapter construction in `cabinet/scripts/`.
Grants say nothing about a source, and the two sets do not overlap: no risk
class names an estate, and no ownership class names an act.

Folding one into the other was rejected because it would put a source-classifier
inside the enforcement plane every officer's action already routes through,
widening that plane's blast radius for a question it does not ask. The two
remaining candidates were `framework/authority/classifier.py` (classifies
ACTIONS from tool calls — same mismatch, plus it is imported on the hot path of
every hook) and `framework/onboarding/journey.py` (would make
`cabinet/scripts/task_adapters/base.py` import the onboarding journey to learn
whether it may write to a tracker — a worse coupling than a new module).

## Consumers, named before the producer

- `framework/onboarding/journey.py` — the ingest ceiling on `propose_window`,
  ownership inside the Charter hash, per-class sensitivity refusals in the scan,
  the surviving access record, and the egress verdict on the dividend card.
- `cabinet/scripts/task_adapters/base.py` — `get_adapter` refuses an
  unclassified tracker and returns `ObserveOnlyTaskAdapter` for any non-owned
  one.
- `cabinet/scripts/task_sync_runner.py` — carries the observe-only posture into
  sync telemetry so an observing cycle is distinguishable from an idle one.
- `cabinet/dashboard/src/lib/onboarding/telegram.ts` and
  `cabinet/dashboard/src/components/onboarding/journey-card.tsx` — the surfaces
  that ask the question and render the egress verdict.

## Cost

+1 `framework_production_modules`, +585 `framework_production_noncomment_lines`,
+1 `durable_store_units` (the access record, which must survive the read it
describes). Each paid at the exact measured total, with the module registered
here rather than bought as line mass.
