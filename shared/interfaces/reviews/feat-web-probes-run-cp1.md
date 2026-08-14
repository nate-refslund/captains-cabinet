# feat/web-probes-run — checkpoint 1 review

Branch: `feat/web-probes-run` off `origin/master` @ `d80b430a`.
Scope: a search shelf in the connector catalog (DATA), an executor that RUNS the
seed's outward probes in the research plane, and an earned "whose work is this"
question. Three Captain asks from one live session, 2026-08-14.

---

## What moved, and why each piece is where it is

| Surface | Change | Why here |
|---|---|---|
| `instance/config/connector-templates.yml.example` | `search` shelf; 5 verified providers + 1 open GET-only escape hatch; a documented `kind: search` template shape | DATA. Every vendor literal — endpoint, auth header, result paths, setup steps — is in the instance layer. `framework/` gained none, and the specifics ratchet is green with no new baseline row. |
| `framework/onboarding/research.py` | `assert_search_read_only`, `assert_declaration_read_only`, `_spec_kind`, lane-filtered `load_connector_specs`, `run_search_probes`, `_untrusted_text` / `_untrusted_url`, `_search_request` | This module already holds the only socket in onboarding and the read-only ceiling beside it. The search plane is the same law applied to a second call shape. |
| `framework/onboarding/journey.py` | `_discovery_block` (two-plane merge), `run_discovery` + `answer_organization` acts, `ORG_QUESTION` + `_organization_unclear`, `_discovery_seed`, `_estate_identities`, card sentences | The core still opens no socket: it proposes probes and delegates, exactly as `gather_connectors` already did for the sweep. |
| Dashboard `types.ts` / `bridge.ts` / `telegram.ts` / `journey-card.tsx` / `actions/connectors.ts` | the two new actions in all three mirrors, the results rendering, the org field, and the catalog loader's lane floor | The parity gate requires the core's vocabulary to reach every surface; the loader's floor was `inventory`-only, which would have silently dropped every search template. |

---

## The one architectural decision, stated for the reviewer

**Two ceilings, not one wider one.** The inventory lane admits a POST only when
the body is a GraphQL read document. That rule is sound for exactly one reason:
a GraphQL document declares its own verb, so `mutation` can be refused by name.
Search endpoints are overwhelmingly a JSON POST that declares nothing — two of
the five shipped providers are — so admitting them under the inventory rule
would have admitted every REST write with them.

So `assert_search_read_only` is a **separate function**, and `assert_read_only`
did not move a byte. The search rule is looser in exactly one dimension (a
bounded query envelope instead of a GraphQL document) and **stricter everywhere
else**: a broader write-verb refusal over both the address and the skeleton, the
injected credential header checked for method overrides, and exactly one
`{query}` hole counted across url + body.

**What it does not prove, and this is in the code at the function.** A flat JSON
body cannot be told apart from a create payload by inspection — `{"title": "…"}`
is a search parameter bag and an issue-creation payload in the same bytes
(verified below: it is admitted). What stands between that and a write is WHERE
the gate sits: a call reaches it only through a connector's `search:` slot, which
nothing but the probe executor reads, and the shipped shapes are verified. An
operator who hand-writes a mutating endpoint into that slot has told their own
cabinet to POST a search query at it.

The lane is decided by `_spec_kind` — the slot the author filled — never by the
`kind:` label, so a declaration cannot pick its own ceiling by writing a word.
Pinned by `test_the_lane_comes_from_the_shape_not_from_a_label`.

---

## The four class-11 questions

**1. Does each arm FAIL against pre-change code, in both directions?**

- `test_the_two_ceilings_did_not_merge` is the load-bearing one and fails in both
  directions by construction: it asserts `assert_read_only` REFUSES a search POST
  *and* that `assert_search_read_only` refuses an address `assert_read_only`
  accepts. Merging the two functions either way turns it red.
- `test_the_search_ceiling_refuses` is 17 parametrized arms, each asserting the
  specific violation string — a gate that started passing everything would fail
  17 times, not zero.
- The organisation arms assert both the appearance AND the disappearance of the
  question, once per each of the three things that can answer it. Before this
  branch the question did not exist, so every arm fails against the old code; a
  suppression condition that never fired would fail the three inverse arms.
- The rendering arms were run against the pre-change component during the build
  (the outward branch renders nothing without `probe.results`), and
  `journey-card.test.ts`'s hook script fails LOUDLY on any hook reorder — which
  it did, and which is why the new `useState` sits last.

**2. What does each check do at the DEGENERATE end?**

| Degenerate input | Behaviour, and the arm |
|---|---|
| No probes at all | `executed == [] and deferred == []`, no socket. `test_no_probes_is_not_a_search` |
| No search tool declared | every probe deferred `no_search_tool_connected`, and the fetch seam records ZERO calls |
| Egress closed | deferred before a socket exists; fetch seam records zero calls |
| Credential absent | `search_credential_absent`, and the env var NAME does not appear in the result |
| Empty body `{}` | refused (`post_body_not_a_query_envelope`) — an empty envelope is not a query |
| Zero `{query}` holes | refused. Without this the probe would search the template's own placeholder and report results as if they answered the operator |
| Empty result list | `search_returned_nothing_at:<declared path>` — never "the web has nothing", because a mistyped `results_path` is the same bytes |
| Result with neither title nor address | dropped, run continues |
| Blank org answer / empty estate list | still counted as UNANSWERED, so the question is still asked (`test_the_organization_question_is_earned_…`) |
| Seed with no terms | organisation question asked (fail-to-ask, the cheap direction) |

**3. What does the test environment guarantee that production does not?**

The end-to-end arms stub exactly one thing — `research._http_fetch` — so the
action, the lock, the commit, the two-plane merge and the rendered card are all
real. What a seam cannot prove is that a socket is really opened and that a 30x
is really not followed, so `test_the_fetch_layer_really_reads_and_really_refuses_a_redirect`
runs a REAL local server and asserts both. It is plain HTTP there on purpose,
stated at the arm: the https rule lives in the ceiling ABOVE the fetch (and is
pinned separately), so serving that fixture over TLS would be testing Python's
trust store rather than any code in this repo.

Additionally verified LIVE, outside the suite, against two real providers with
keys from a scratch instance's own `cabinet/.env` — see the acceptance case
below. That is the only thing that could prove the SHIPPED SHAPES are right
rather than my reading of the docs, and it caught a real defect (see below).

**4. Is the sensor wired to the LIVE artifact?**

`test_connector_catalog.py` resolves and parses the shipped
`instance/config/connector-templates.yml.example` from the repo root — not a
fixture — and builds every template through the real
`build_connector_from_template`, holding each to its own lane's real ceiling.
`test_the_catalog_ships_a_way_to_search_the_web` is a floor on that same file.
The parity test imports the LIVE `ACTIONS` set and `ONBOARDING_ACTIONS` array and
parses the LIVE core dispatch; both new actions passed it without an exemption.

---

## Adversarial pass — executed, not reasoned about

Run against this tree; every line below is a program's output, not a claim.

```
PASS write-verb search template REFUSED at declaration
PASS flat create-shaped POST is ADMITTED (known + documented limit)
PASS wire carries ONLY the shown query as a parameter
PASS credential is a header, never in the url or the result
PASS newline/line-sep scrubbed
PASS javascript: url dropped
PASS markup neutralised
PASS whole result is json/utf-8 safe
```

**Can a hostile search result inject or execute anywhere?** No, and the reason is
structural rather than filtered: nothing downstream interprets a result. The
consuming pipeline is deterministic — no model reads it, no branch turns on it,
nothing executes it. What it CAN do is be displayed, so every field is scrubbed
and capped at the one place results enter (`_untrusted_text` / `_untrusted_url`):
control characters and U+2028/U+2029 (a newline in a title would forge a second
rendered line), angle brackets (measured: a live provider returns snippets with
markup by default — that was found by the live call, not by reasoning), lone
surrogates (legal in decoded JSON, illegal in UTF-8, would crash the CLI that
prints this state as JSON and take the action down with the result), lengths, and
an address that is not http/https reduced to empty. The card BODY carries only
the operator's own query, so third-party text never enters the string that
travels to a messenger; Telegram sends `plain: true` with no parse mode; the
dashboard renders text nodes and only emits an `<a>` when the address survived.

**Can the probe leak more of the seed than the shown query?** No. The query is
bounded, whitespace-collapsed and capped, then percent-encoded with an empty safe
set into a URL or JSON-encoded into a body — so no character in a sentence can add
a parameter, close the query string or walk the path. Verified above: the wire URL
carried exactly one parameter and its value was byte-identical to the query shown
on the card. The credential rides a header and appears in no URL and no result.

**Are write-verb search templates refused?** Yes, at declaration
(`assert_declaration_read_only` runs inside `build_connector_from_template` AND
inside `write_connector_declaration`, so a caller that skips the builder is still
refused), and again at execution before the first socket. Verified above.

**The known, documented limit:** a flat POST body that IS a create payload but
names no write verb is admitted by the search ceiling. It is stated at the
function, in this artifact, and in the design of record; the containment is the
slot, not the shape. The open `search_rest` template is therefore GET-only and no
field may write `search.method`, so nothing an operator fills in through the UI
can produce an unverified POST — pinned by `test_the_catalog_ships_a_way_to_search_the_web`.

---

## The Captain's acceptance case, live

His words: *"i mentioned i am tech lead at STEP Network, then it should be able to
search for step network and what kind of business that is."*

Executed against the real providers through the shipped template shapes and the
real executor (scratch instance, its own `cabinet/.env`, no key committed):

```
brave_search: 5 result(s), truncated=False
   • STEP Network - Danmarks største medienetværk | https://www.stepnetwork.dk/ | Vi forbinder brands med millioner af danskere …
   • STEP Network | LinkedIn | https://dk.linkedin.com/company/stepnetwork | STEP Network er Danmarks største medienetværk …
exa_search: 5 result(s), truncated=False
   • step network | https://stepnetwork.dk/ | STEP Network is a Advertising Services company …
   • STEP Network - CVR-nr 25506227 - Odense | https://www.proff.dk/firma/step-network/… | … Se Regnskaber, Roller og mere
```

**The live calls and the live screens earned their keep — four defects, none of
them predictable from documentation or reasoning:**

1. Snippets arrived wrapped in `<strong>` markup. Fixed twice: `text_decorations=0`
   on the shipped shape, and angle brackets added to the scrub so no future
   surface can be handed markup whatever a provider sends.
2. The seed "I am tech lead at STEP Network" produced one query — "tech lead
   STEP Network" — and Brave returned pages about being a tech lead. The role
   words are common, the name is not, and the engine ranked the common half, so
   the operator's actual question went unanswered. The names now go out as a
   query of their own, first.
3. Composing the dream onto the role made "Give me back my mornings" donate its
   opening capital: the query became "STEP Network Give". `_seed_names` now
   skips each SENTENCE's opener, and `_discovery_seed` joins with a boundary.
4. Reading the rendered card: snippets showed `I&#x27;ve` and `&quot;` — providers
   HTML-escape them. Decoded before the scrub (so an entity-encoded tag still
   loses its brackets), pinned by an order arm that fails if the two swap.

Three of the four are invisible to a test suite written from the design; all
four are pinned by arms now.

The same case is pinned in the suite without a network by
`test_answering_the_seed_goes_and_looks_it_up`, which also asserts the operator's
old sentence — *"did not run — no egress in the onboarding core"* — is gone.

---

## Gates

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework/onboarding/tests -q` | 948 passed, 1 skipped |
| `python3.12 -m pytest framework/ -q` | 8115 passed, 30 skipped, **1 pre-existing failure** |
| dashboard `npx tsc --noEmit` | clean |
| dashboard `npx vitest run` | 3441 passed, 1 skipped (167 files) |
| `check-layer-separation.sh` | OK — new=0 |
| specifics ratchet (`test_no_launcher_hardcode.py`) | 74 passed, no new baseline entry |
| `cognitive-architecture-census.py --check` | PASS after a visible `framework_production_noncomment_lines` raise (63096 → 63700, +604), reasoned in the contract |
| `docs-track-code-sweep.sh` | GREEN (65 files, 0 findings) |
| guarded-token grep | no guarded literal added |

**The pre-existing failure, named rather than buried.**
`framework/fidelity/tests/test_retro_shim.py::test_reexports_constants` asserts
`retro.LLM_MODEL == "claude-sonnet-4-6"`. It fails on a CLEAN checkout of
`origin/master` on this machine (verified by stashing every change and re-running)
because the shim resolves the operator's LOCAL retrodiction pipe, whose value is
`claude-sonnet-5`. `origin/master`'s own CI run is green, so this is an
environment-resolved constant, not a regression and not in this branch's scope.

---

## Residual, stated rather than implied

1. **Genesis does not read the organisation answer yet.** It is recorded on state
   under one documented key and has a live consumer today (it joins the discovery
   seed, so the next look-up searches it), but `genesis.recall_probes` reads the
   cabinet-init answers file and nothing copies the journey's answer there. Adding
   a `organization=` parameter nobody passes would be machinery ahead of its
   consumer, which this program has a named bias against; the honest state is
   this sentence.
2. **Three residual questions still have no field.** `rights`, `limits` and
   `purpose` are printed with no way to answer them. Pre-existing, out of scope,
   and deliberately NOT papered over — `test_renders_NO_field_for_a_question_the_core_gave_no_action`
   exists so a later edit cannot hide the gap behind a field that sends nothing.
3. **One search tool runs a look-up**, the first declared. Deterministic and
   recorded per probe; a cabinet with three declared does not fan out.
4. **The seed half of the organisation heuristic over-detects English title case**
   and cannot fire in a script without letter case. Stated at the function; it
   errs toward asking, which is the cheap direction for an optional question.
