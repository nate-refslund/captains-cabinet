# Expansion: `framework/onboarding/salience.py` — rank, then ask

**Class:** `framework_production_modules` (bijection) · **Gate date:** 2026-07-28
**Arms run, blind and independent:** Fable 5 and Opus 5, own clones, neither
reading the other's output.
**Provenance:** per 2026-07-07 full-autonomy grant + 2026-07-21
ownership-on-GO; Captain ruling of 2026-07-28 (helicopter-first onboarding).

---

## 1. What the Captain asked for

> *"obviously the cabinet should start from top/helicopter-perspective and
> downwards: find out what's MOST relevant first (e.g. 1-3
> projects/products/clients/targets/tasks/etc.) and continuously have a dialog
> with the captain about what's relevant... but remember it could be anything,
> for a sales person it could be clients, for a librarian something entirely
> else, so how can we create the onboarding agnostic to anything but let the
> cabinet explore, gather, then ask for direction?"*

## 2. Why this is not the refuted ingest engine

A decisive experiment refuted READING EVERYTHING to produce findings: on an
employee-slice fixture, of four findings one needed more than one FILE and
**zero** needed more than one SYSTEM (`framework/onboarding/research.py`, module
header). That experiment asked *"does reading everything produce findings?"*

The Captain is asking *"what is MOST relevant?"* — **ranking, not ingest**. And
the cross-system signal he names is not a fact joined across systems; it is an
entity whose NAME RECURS across systems. Recurrence needs names and counts and
never contents. Depth — the expensive, revocable, employer-estate-touching part
— is then spent only on a target the operator ratified by answering, which is
what makes it affordable.

## 3. The two arms, and the adjudication

Both arms returned **BUILD DIFFERENTLY** and converged, independently, on the
mechanism: cluster co-occurring tokens; derive every floor from the estate;
score `connectors² × recency × (1 + min(n,20)/20)`; three candidates plus a
mandatory escape hatch; state what was not reached; no taxonomy of entity kinds.
Both also independently identified the alias split and the identity/product
collision as the load-bearing failures.

They diverged on four points. Each was decided on evidence, not averaged:

| # | Divergence | Decision | Evidence |
|---|---|---|---|
| 1 | Ship a credentialed sweep inside `framework/`? | **No** (arm B) | `instance/config/egress.yml` is `enforce: true, allow_hosts: []` and germline-locked; no request would be legal here, and no read adapter exists to inherit. Rows arrive from whoever lawfully produced them; `sweep_ceiling()` makes a future producer consult the ceiling first. |
| 2 | Does the ranking surface the operator's own three answers cleanly? | **No** (arm B) | Measured live: ranks 3, 4-5 and 8 of 47; top three held one of three. Arm A's claimed 1/2/4 does not reproduce. |
| 3 | Identity tokens: demote or delete? | **Demote** (arm A) | The employer's name and a real target are the same string. Measured: with demotion the cluster survives at rank 6 carrying its evidence; a delete floor removes the target with the noise. |
| 4 | Recency | **Refuse it per connector** (arm B, made mechanical) | Measured: one of four connectors resolved three distinct days across twenty rows. `admissible_clocks()` refuses such a clock, scores its clusters at a neutral band, and discloses the refusal. |

## 4. The merge that was refuted

`framework/onboarding/research.py::probe_connectors` is the nearest existing
organ and the obvious fold target: it is the connector registry, it already
answers "what is connected", and this module ranks across exactly those
connectors. It is refused as a home for three reasons that are properties of
that function rather than preferences.

* **Different question, different arity.** `probe_connectors` answers a
  per-source BOOLEAN — did this source answer, and if not, why. `rank` answers a
  cross-source ORDERING over entity names. Folding an ordering into a probe
  registry would give the registry a second output whose shape has nothing to do
  with its first.
* **Different inputs.** Every probe in `research.py` is a bounded LOCAL FILE
  READ by explicit design ("no network, no credentials, no subprocess") because
  a probe that needed a credential would be the first brick of the refuted
  engine. `rank` consumes rows a credentialed sweep, an operator export or those
  same probes may have produced; putting a row-consuming ranker inside the
  module whose whole discipline is that it reads only local files would erase
  the distinction the header exists to hold.
* **Different failure mode.** `probe_connectors` is fail-closed per source. The
  ranker's failure mode is a CONFIDENT WRONG — an ordering asserted over an
  estate it only partly reached — and its defences (the escape hatch, the
  not-reached line, `offer()` refusing a coverage-less ranking) are meaningless
  inside a function whose contract is a boolean.

Second candidate considered and refused: `framework/onboarding/estate.py`
(`proposed_lanes`) derives lanes from a ratified First Window's DIRECTORY
markers — one source, structural evidence, write-capability gated on ownership.
It never sees a second system, which is the only place recurrence exists.

## 5. Consumer, named before the producer landed

`framework/onboarding/journey.py` — `salience_offer()` builds the ask,
`entry_plan()` attaches it to the standing `salience` residual question in
connected mode, the welcome card renders the candidates and the not-reached
sentence, and the `answer_salience` action records the ratified target. Proven
by EXECUTION against a real 665-name estate, not by a reference grep: the offer
rendered on a real `journey.snapshot()` card, the action committed, and the
alias learned from the escape hatch changed the next ranking.

## 6. What it costs and what it is worth

688 lines, one module, no new dependency, no network, no credential, no content
read. It replaces a question that connected mode DELETED on a premise this gate
falsified — that a cabinet which has swept its sources already knows what
matters. Measured, it does not; it knows what is there, which is a different
thing, and the difference is exactly the dialog the Captain asked for.

## 7. Superseded in part, 2026-07-29 — re-executed on the same estate

Two things §3 records as decided were REPORTED as working and, re-run against
the same live 665-name sweep, were not. Both are corrected on
`fix/salience-ranking`; the positions above are kept verbatim because a later
session must argue with what was actually claimed, not with a tidied version.

| Claim above | What re-execution measured | What replaced it |
|---|---|---|
| Divergence 3, "identity: demote, not delete" — closed | Three identity-shaped candidates were still REMOVED with reason `connector_furniture`. The identity exemption added afterwards only fires for strings the connectors report about *themselves*, and the organisation owning 52 of 56 repositories was never one of them. | Both floors are DISCOUNTS. The occurrences one connector's filing explains stop counting as evidence; the token keeps the rest and stays findable. The owner stamped on each row now joins the estate's identity strings. |
| §5, "the alias learned from the escape hatch changed the next ranking" | True, and beside the point: cold, the entity stood as FIVE candidates (ranks 6, 11, 21, 33, 34), and an operator's typed answer only ever unions the two names they happened to type. Three fragments survived the "closed loop". | `rank(join=…)` hands the candidates' names UNMODIFIED to judgment and takes back groups it validates against what it actually ranked. No string function joins them and none may — a stem table is a hand-maintained list wearing an algorithm. |

§3's divergence 2 ("does the ranking surface the operator's own three answers
cleanly? **No**") stands, and is now MEASURABLE rather than anecdotal:
`salience.check` grades a ranking against answers the operator supplies, and its
live consumer is `answer_salience`, where every real answer grades the ordering
that operator was actually shown. The score is unchanged except that its volume
term counts the occurrences the discount left standing, and the connector span
is counted over those too.
