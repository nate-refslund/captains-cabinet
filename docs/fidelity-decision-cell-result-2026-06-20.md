# Decision cell — first measurement (clone vs generic) — 2026-06-20

First intent-fidelity measurement on real Head-of-Tech DECISIONS (the F3-intent
cell). The reply cell measures voice; this measures judgment calls — the thing
"replace Nate" actually requires. 12 of 16 corpus notes survived
extraction+leak-scan. Both arms judged by the SAME judge on the SAME dilemmas;
only the system prompt differs (clone identity vs generic assistant).

## Result
| Arm | intent-aligned | aligned+partial | intent-divergent | mean composite |
|---|---|---|---|---|
| **Clone (Nate identity)** | **58%** (7/12) | **100%** | **0** | **0.833** |
| Generic assistant | 33% (4/12) | 75% | 3 | 0.542 |

**Clone-identity lift: +25pp intent-aligned, 0 vs 3 values-divergent, +0.29
composite.** Decision-match (clone): 6 match / 4 partial / 2 divergent.

## What it means
On real judgment calls the clone is meaningfully MORE Nate-aligned than a
competent generic assistant — and it never made a values-divergent call (the
generic made 3). This is the opposite of the reply cell (60% divergent, voice
axis): on the axis that maps to *doing Nate's job*, the clone identity (voice +
nate_model patterns) does genuine work.

**Proof case — `approve-with-db-backup`:** generic = divergent/intent-divergent
(it REFUSES the risky DB op a cautious assistant would block); clone =
match/intent-aligned (it APPROVES like Nate, knowing his "max AI autonomy with a
manual safety net" stance). The clone captures Nate's specific risk posture
where the generic gets it wrong. Same pattern on `cohere-embeddings` and
`next-bug-vat` (clone credits intent where generic diverges).

## The honest caveats
- **n=12, single day (2026-05-28/29), single judge.** Directional, not precise.
- **Answer-aware judge** (it sees Nate's actual decision+why and grades against
  it). Absolute numbers are in a LENIENT regime — but the regime is identical
  for both arms, so the **+25pp contrast is robust** to judge leniency; the
  absolute 58% is not a hard fidelity figure.
- **Selection bias:** these are decisions clear enough to have been logged with
  a WHY — likely the cleaner judgment calls.

## What's next (the real bottleneck is now DATA)
The pipeline works and shows real signal. The limit is the substrate: 12
one-day cases. To turn this directional read into a robust decision baseline,
grow the decision ground truth:
- mine Monday activity-log transitions, commitment closures, the agent
  reasoning log into more {dilemma, decision, why} cases;
- and/or capture it live via shadow-drafting (the clone proposes real calls
  behind Nate's approval gate; every approve/edit/skip is a new logged decision).
The cell ingests new cases the moment they exist (cache-keyed by note).

## Provenance
`framework/fidelity/decision_cell.py` (committed f54c08e). Clone arm:
`/tmp/decision_cell_eval.py`. Generic baseline arm: `/tmp/decision_cell_baseline.py`.
Extraction cached at ~/.screenpipe/state/cabinet_decision_cases.json.
