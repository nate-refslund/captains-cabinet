# feat/onboarding-connector-read — checkpoint 1

**Unit.** Credentialed READ-ONLY gathering at onboarding: read every connector
the operator declared, contents-free (names, dates, actors, counts), and put the
onboarding journey into the connected entry mode on the strength of a read that
actually happened. Plus the egress default the Captain ruled, so the read can
leave the machine at all.

**Model.** Opus 5 (1M), single session, execution tier. Direction was already
adjudicated — Captain rulings 2026-07-26 (ordering inversion: connect, then
gather) and 2026-07-29 (gather from connectors read-only; network allow-all by
default). This checkpoint implements a ruling; it does not re-open one.

---

## 1. The premise that was overturned, and why the overturn is sound

`framework/onboarding/research.py` carried: *"NO NETWORK, NO CREDENTIALS, NO
SUBPROCESS … That is not a limitation to be lifted later"*, justified by the
ingest experiment — "of four findings, one needed more than one file and ZERO
needed more than one system".

That justification is a non-sequitur, and it is checkable rather than a matter
of taste:

1. The experiment refuted **ingest-everything-into-a-vault**. Its fixture's
   second system was **a CSV already on disk**, so the network hop was
   presupposed as done by a human. **No-credential was never an experimental
   arm.** A refutation of ingest is not a refutation of LOOKING.
2. The tree already contradicted the sentence one module over:
   `framework/onboarding/estate.py` — *"Widening the estate to new source KINDS
   is a later unit; the schema below already has the shape for them."*
3. `instance/config/egress.yml` carried an expired 72-hour dogfood posture
   (`enforce: true`, `allow_hosts: []`) that 403s **every** outbound request
   and contradicted both `framework/defaults/egress.yml` and its own `.example`
   twin — the bytes the egg ships to a stranger.

The prose is superseded in place with the reasoning above rather than deleted,
so the next reader cannot re-derive the old law from the old argument.

## 2. What landed

| Piece | Where |
|---|---|
| The ceiling — refuses anything that could write, before a socket exists | `research.assert_read_only` |
| The socket — one call, **no redirects**, capped read | `research._http_fetch` |
| The lane — paging, call budget, item cap, contents-free extraction, named refusals | `research.sweep_connectors` / `_sweep_one` |
| Operator declaration (absent ⇒ zero connectors, an honest empty) | `research.load_connector_specs`, `instance/config/connectors.yml{,.example}` |
| Registry: a completed READ grants the mode; a declaration grants nothing | `research._probe_sweep`, `probe_connectors(sweep=…)` |
| The action, on the record, once, when asked | `journey.act` → `gather_connectors` |
| The offer, only where connectors are declared | `journey.entry_plan(gather=…)`, `_with_registry` |
| Surface reachability (payload-free by design) | dashboard `bridge.ts` ACTIONS, `types.ts` union |
| Egress default the ruling requires | `instance/config/egress.yml` |

## 3. The ceiling, stated exactly

* **Verbs.** `GET`, or `POST` whose body is a GraphQL read document. Nothing
  else is reachable — there is no branch in the module that emits another verb.
* **GraphQL.** Body key set must be ⊆ `{query, variables, operationName}` and
  must carry `query`; the serialized document is token-scanned for
  `mutation`/`subscription` with word boundaries (so a board *named*
  "mutations-team" stays readable and a keyword cannot hide in an identifier).
* **Smuggling.** `X-HTTP-Method-Override` and its spellings are refused.
* **Transport.** https only; **redirects are not followed**, so a credential
  cannot be handed to a host the operator never declared.
* **Blast radius.** Call budget, per-call timeout, 4 MiB response cap, item cap.
* **Contents.** Only the declared `name`/`updated`/`actor` paths are read out,
  each coerced to a short scalar; a container value is dropped rather than
  flattened. The response body is never persisted or returned.

**Nothing on the write or send side was touched.** Egress is a reachability
ceiling, not a permission to act: `framework.env.allow_sends()`, the comms
charter and recipient gates, the front-door killswitch and vetoes, and the
authority matrix are all byte-unchanged.

## 4. Verification — what was run, not what was intended

* **Both directions.** All 41 arms in
  `framework/onboarding/tests/test_connector_read_lane.py` pass on this branch
  and **all 41 fail** against `origin/master` (70bf330e) in a clean worktree,
  caches purged.
* **The ceiling arms assert on an EMPTY request log**, not merely on the raised
  exception — an arm checking only the exception would pass against a lane that
  made the call and then complained.
* **The redirect refusal is proven over a real socket** against a local server
  that 302s: the second request never arrives.
* **The contents-free arms search the whole serialized document** for a string
  that was in the response and must not be in the result (and for the
  credential), rather than asserting the wanted fields are present.
* **Degenerate ends, each with a DIFFERENT named reason:** zero declared, empty
  inventory, absent credential, closed ceiling, HTTP 401/500, non-JSON body,
  transport error, oversized response.
* **Suites.** `framework/` — 7543 passed, 1 failed
  (`test_retro_shim.py::test_reexports_constants`, the known local-only red,
  green in CI). Onboarding alone: 472 passed, 1 skipped.
* **Gates.** `check-layer-separation.sh` OK (0 new);
  `cognitive-architecture-census.py --check` PASS at zero headroom;
  `docs-track-code-sweep.sh` GREEN; `ledger-status-parity.sh` GREEN. The COG-4
  Reviewed-Scope-Digest is re-bound in this same commit (the contract and the
  egg manifest are both scope members).
* **Executed against the Captain's real estate, read-only, through the public
  `journey.act` API:** 4 connectors, **665 names, 14 HTTPS requests, ~9
  seconds**; entry mode `seeded` → `connected`; `opening_move` `sweep_and_assert`;
  the ranker consumed the rows and produced a real offer. **No write of any kind
  was emitted** — every request the lane made was a GET or a mutation-free
  GraphQL query, asserted mechanically before the socket.

## 5. Residuals, declared rather than implied

1. **`instance/config/connectors.yml` is not germline.** It says where a
   credential may be sent, so it deserves the same custody as
   `instance/config/egress.yml`. The germline SET cannot be extended from here;
   this needs a Captain-gated ledger row. Mitigated meanwhile by https-only,
   no-redirect, and the fact that the credential only ever reaches the declared
   origin.
2. **Ranking quality is not this unit.** The lane produces rows; how they rank
   is `framework/onboarding/salience.py` and its open proposal.
3. **One page size per connector.** Cursor-paged APIs get their first page
   only, and say so in `not_reached` when the page came back full.
4. **`framework/channels` is untouched** — no send path was opened, read or
   otherwise.
