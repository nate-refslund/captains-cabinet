# feat/salience-sweep — checkpoint 1

**Unit.** Rank what recurs across an operator's connected sources by NAME AND
COUNT only, then ask which candidate to open first. Depth is spent on the
answer, not on the ranking.

**Model.** Opus 5 (1M), single session, execution tier. The direction gate that
preceded this ran two blind arms; their positions and the adjudication are
below.

---

## 1. The adjudication — which arm was followed, and on what evidence

Two blind arms both returned **BUILD DIFFERENTLY**. They agreed on the
mechanism and split on whether the credentialed sweep ships. Both positions
are recorded; neither was averaged.

### Where they agreed — built as agreed

| Agreed point | Where it landed |
|---|---|
| Rank CLUSTERS of co-occurring tokens, not raw tokens | `salience._cluster` (row-set Jaccard ≥ 0.6) |
| Floors MEASURED from the estate, never a stopword list | `salience._apply_floors` |
| `score = connectors² × recency × (1 + min(n,20)/20)` — proposed identically and independently by both arms | `salience.rank` |
| No taxonomy of entity kinds anywhere | pinned mechanically by `test_the_module_contains_no_taxonomy_of_entity_kinds` |
| 3 candidates + escape hatch, per-candidate evidence = NAMES not scores | `salience.offer` |
| Mandatory not-reached statement | `salience.not_reached_line`, and `offer` refuses to build without coverage |
| Aliasing is the load-bearing failure; the operator's ANSWER repairs it | `salience._merge_aliases` |
| Wire to a consumer or do not build | `journey.salience_offer` → `answer_salience` → card |

### Where they diverged — and the side taken

**Divergence 1 — does the credentialed sweep ship inside `framework/`?**
Arm A: yes, gated by `ownership.open_ingest`. Arm B: no — `instance/config/egress.yml`
is `enforce: true, allow_hosts: []` and germline-locked (`germline-lock.sh:63`),
so on this deployment not one request is legal.

**Followed Arm B, on verified evidence.** I read the file: `enforce: true`,
`allow_hosts: []`, and it is line 63 of the germline set. Arm A's plan would
have shipped four API clients that 403 on every call here, and Arm B's second
reason is the stronger one — a client written against a live production estate
is where an accidental write comes from, and there is no adapter to inherit
(zero files in the tree match `monday`).

**But Arm B's conclusion ("do not build the ranker's input") was not followed.**
The repair is structural, not a deferral: the ranker consumes a plain
`(connector, name, updated)` row and does not care who produced it.
`rows_from_state` reads a rows block someone already lawfully produced plus the
probes this journey already ran; `sweep_ceiling` makes any future credentialed
producer consult the egress ceiling BEFORE its first request and report a
closed ceiling as a disclosed not-reached line rather than a wall of failures.
That is one code path for Arm A's credentialed sweep and Arm B's
export-seeded version, and it keeps the illegal-and-dangerous part out of the
framework.

**Divergence 2 — does the ranking surface the operator's own three answers?**
Arm A: ranks 1/2/4, clean. Arm B: 1 of 3 in the top 3, all three only by depth 8.
**Arm B was right, measured on the live estate** (§2). Arm A's claim does not
reproduce.

**Divergence 3 — identity tokens: demote or delete?** Arm A said demote-never-
delete because the employer's name and a real target are the same string. Arm B
said no floor separates them. **Followed Arm A, and it is now measured**: with
demotion the `stepnetwork` cluster survives at rank 6 carrying
`step-network-website` as evidence; a delete floor would have removed it and its
target with it.

**Divergence 4 — recency.** Arm A flagged it as its least-confident item; Arm B
measured two of four clocks dead. **Followed Arm B and made it a mechanism**:
`admissible_clocks` refuses a clock that does not discriminate, the affected
clusters score at a neutral band, and the refusal is disclosed. On the live
estate this fired correctly and unprompted on exactly one connector.

**Divergence 5 — new surface for the picker.** Arm A: reuse the seed field, no
new surface. Arm B: a new input kind, gated. Followed **A** on the framework
side — `answer_salience` carries `input: "choice"` alongside the existing
`input: "seed"` and the escape hatch reuses the seed field — so nothing outside
the framework changed in this unit.

---

## 2. What the ranking actually produced on a real estate

**READ-ONLY dress rehearsal.** 18 HTTP round-trips, ~27s, 0 writes, 0 Telegram,
0 Voyage. Every GET asserted `GET`; the Monday documents asserted to start with
`query` and to contain no `mutation` token before send. 665 names: 531 active
Monday boards / 56 GitHub repos / 20 Neon projects / 58 Vercel projects (the
personal Vercel scope resolves to the same team, so a naive sweep double-counts;
deduped by project id).

The clock sensor fired on its own: Neon resolved 3 distinct days across 20 rows
→ `clock_does_not_discriminate` → refused, disclosed, and Neon contributed no
recency. Monday (211 distinct days), GitHub (47) and Vercel (39) were admitted.

**Cold ranking, 47 clusters from 1,178 tokens, 32 floored:**

| # | cluster | score | conns | rows |
|---|---|---|---|---|
| 1 | website | 24.80 | 4 | 11 |
| 2 | mediasummit | 10.80 | 3 | 4 |
| 3 | networkwebsite | 10.80 | 3 | 4 |
| 4 | polads | 10.80 | 3 | 4 |
| 5 | politiskeannoncer | 10.80 | 3 | 4 |
| 6 | stepnetwork *(demoted — identity)* | 10.56 | 4 | 13 |
| 7 | devtasks | 10.35 | 3 | 3 |
| 8 | stephie | 7.83 | 3 | 9 |

Floored, all by measurement: `subitems` (177 rows, 33% of one connector →
furniture), `tasks`, `publisher`, `medie`, `team`, `2025`, `intern`, `archive`,
`test`, `audience` (single-system structure).

**Honest verdict: a good shortlist, a bad oracle.** The operator's three named
answers are at ranks 3, 4-and-5, and 8 — all inside the top 8 of 47, and the
top 3 contains one of them. Two real, unnamed candidates (`mediasummit`,
`devtasks`) rank alongside them, which is the mechanism doing its job. Two
defects are structural, not tuning:

* **The generic descriptor outranks the specific one.** `website` is #1 and it
  merges four unrelated sites; the specific `networkwebsite` is #3 with a
  strict subset of its rows. No floor derived from this estate separates them.
* **The alias split.** PolAds spans four connectors and is scored as two
  three-connector candidates, because the tracker says `PolAds` and the code,
  database and hosting say `politiske-annoncer`. Names cannot join them; the
  row sets do not overlap and they are two separate repositories.

That measured result is the whole argument for the escape hatch and the
not-reached line being mandatory rather than decorative — and it is why the
`salience` question is now ASKED in connected mode instead of deleted.

**The loop closes.** One answer through the escape hatch —
*"PolAds, which the repos call politiske-annoncer"* — merges the split and it
becomes a 4-connector candidate at **rank 2, score 22.40**, above every noise
candidate. Nothing recorded what KIND of thing it is.

---

## 3. Defects found by running it (not by reading it)

1. **The alias merge absorbed an innocent cluster.** Matching a typed sentence
   against every token in every cluster let the word *"call"* pull
   `AdMetrics---Network-call-tracking` into the merge; the junk cluster ranked
   2nd. Fixed: only cluster LABELS merge — an operator can join things the
   ranking already named, and a word matching nothing is a target, not a merge.
   Pinned by `test_an_alias_only_merges_what_the_ranking_already_named`.
2. **The furniture floor deleted small connectors entirely.** A share computed
   over two rows is not a measurement. Fixed with `_FURNITURE_MIN_ROWS = 8`;
   re-verified that the live 665-row ranking is byte-identical after the fix
   (47 clusters, 32 floored, same top 8).

---

## 4. Verification

| Gate | Result |
|---|---|
| `framework/onboarding/tests/test_salience.py` | 21 passed |
| `framework/` full suite | 7436 passed, 1 failed = `test_retro_shim.py::test_reexports_constants` (known local-only red, unrelated) |
| New arms against pre-change code | salience suite fails to import; **all 8** journey arms FAIL — both directions verified, `__pycache__` purged |
| `check-layer-separation.sh` | `new=0` — OK |
| `ledger-status-parity.sh` | GREEN (ids=353 md_rows=353) |
| clean-room ratchets | 24 passed |
| Live estate execution | offer rendered on a real `journey.snapshot` card; `answer_salience` committed; re-ranked with the learned alias |

**One existing test was inverted, not weakened.**
`test_connected_mode_does_not_ask_what_the_data_answers` asserted salience is
DROPPED in connected mode. Its premise — a cabinet that has swept already knows
what matters — was tested against 665 real names and is false. The arm now
asserts the stronger property (all four questions present, seed question still
suppressed) and its docstring carries the measurement.

## 5. External-write status

**NONE.** Every request this session was a GET or a GraphQL document
mechanically asserted mutation-free before send. No Telegram call of any kind.
No Voyage call. No write to any external system.
