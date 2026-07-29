# feat/look-capabilities — cp1

Reviewed-Scope-Digest: 00d423c01319a31b51212d3728239fd5bb5deec7f74998e99358acd51942c42c

## What this is

Three capabilities recovered into the landed credentialed read lane
(`framework/onboarding/research.py`) from a parallel sweep engine that was
built against the same live estate, proven, and then deliberately dropped
because two producers for one state key is worse than either. That judgment
stands and is not reversed here: nothing new produces `salience_rows`, no
second state key exists, no parallel code path was added. The port is inside
the one producer.

Ported on merit — each closes a claim the landed lane was measurably making
and could not support — not because the other engine happened to have it.

## The three, and the evidence each rests on

### 1. A clock in another encoding is not an absent clock

`date_encoding: iso | epoch_ms | epoch_s`, declared per connector beside the
path it describes, never sniffed. An unknown value is refused BY NAME before a
socket exists rather than read as ISO.

Proven live this session, read-only, against the operator's real estate —
three runs, 21 requests, every one a GET or a mutation-free GraphQL document
asserted before the socket, zero writes:

| | pre-change | post-change |
|---|---|---|
| `hosting` freshest | `'1785241649467'` | `2026-07-28T12:27:29Z` |
| `hosting` clock verdict | `admitted=False, clock_absent_on_most_rows, stamped=0/58` | `admitted=True, stamped=58/58, 39 distinct days` |
| sweep period | `dated 175/233` | `dated 233/233` |

So one of four connectors — one that stamps every single row — was reported to
the operator as having no clock, and a raw integer was presented as its
freshest timestamp. That is a sensor describing itself rather than the estate.

The third live run proves the self-teaching path: with the encoding NOT
declared, the disclosure the operator reads now says

> `hosting: the declared date path (updatedAt) resolved on 58 of 58 items but
> none of it is a date I can read — if that system stamps in epoch time,
> declare date_encoding: epoch_ms (or epoch_s) beside the path`

`instance/config/connectors.yml` carries the one-line declaration so the fix is
live on the estate that has one, and the diagnosis carries it for everyone else.

### 2. One item does not have one actor

`actor_field` accepts a string OR a list of paths, and a path may resolve to a
person-shaped object or a list of them. The row key is `actors: [str]` — the
singular `actor` is replaced, not shadowed; there is one vocabulary, not two.

`_scalar` returns None for any container, so before this a declared path
resolving to a LIST of people was dropped whole: the connector reported zero
distinct actors while carrying the operator's own handle in every row, every
attribution came back `unresolved`, and `presence_question` could never fire —
the sweep then presented the window as representative of their work without
anything having checked. Armed by
`test_the_operator_is_recognised_when_they_are_not_the_first_actor`, which
fails against pre-change code.

Not live-proven, and not claimed to be: the estate that exists declares no
list-shaped actor path. The defect is a property of the code, and that is what
the arm pins.

### 3. A declaration that missed is not an empty estate

`_items_of` returns its reason; a name path that resolved on nothing says so;
items dropped for having no name are counted into the disclosure; and a date or
actor path that never resolved is named. Pre-change, a mistyped `items_path`
and a system with nothing in it returned the identical reason
(`inventory_returned_no_items`) — on the operator's first pass at their own
config, which is exactly when it is most likely to be wrong. The module's own
header already required this one level up ("collapsing them is how 'nothing is
connected' gets confused with 'I never looked'"); the level below it was
collapsing three facts into one.

## What was deliberately NOT ported, and why

* **Per-row `counts: {label: field}`** — no consumer. Salience ranks
  `(connector, name, updated)`; the connector-level counts already exist.
  Machinery outrunning value.
* **Multiple date labels per row** — the operator already names the clock with
  `updated_field`, and every downstream reader takes one. A second clock would
  be a wider row with nothing reading it.
* **`${ENV}` substitution anywhere in url/headers/body** — a REGRESSION in
  control, not a capability. The landed lane has exactly ONE site where a
  credential enters the wire, which is what let `assert_read_only` check every
  header this module can emit (the override channel closed on 2026-07-29).
  Multiple injection sites reopen that audit surface and admit a credential
  into a URL, where it lands in error text.
* **`identity_from: credential` refusal** — there is no such key in this
  lane's vocabulary. A refusal for a config key nothing can spell is a sensor
  pointed at a dead twin, and this program has found that ten ways.
* **A literal `estate_identity` list** — a second way to say what the declared
  `identity` call already says. Demotion identities are pooled across
  connectors, so one connector reporting the estate's name is enough.
* **A `read_only_proofs` block** — positive proof-kind recording. The ceiling
  already refuses violations by name; recording "http_get" adds a field with no
  consumer.
* **`[]` list-flattening in the dotted-path grammar** — `_people` handles the
  actor-list case without touching the path grammar. Widening the grammar is a
  wider blast radius than the remaining gap justifies; recorded here rather
  than smuggled in.

## Verification

* `framework/onboarding/tests` — 533 passed, 1 skipped.
* Whole framework suite as CI runs it (`pytest framework/ -q`) — 7624 passed,
  25 skipped, 1 failed: `test_retro_shim.py::test_reexports_constants`, the
  known local-only red (a model-id constant), unrelated and untouched.
* **Every new arm fails against pre-change code, cache purged**: 19 of the 19
  new arms plus the 4 vocabulary arms fail when `research.py` is reverted to
  HEAD and the tests are kept. Two parametrized degenerate cases (`None`, `""`,
  `[]`, `{...}`) pass both ways, correctly — those inputs were already handled;
  the ones carrying the delta (`"not-a-number"`, `True`, `0`, `-1`) fail.
* Inverse arm present: `test_a_path_that_did_resolve_says_nothing` — a clean
  read must print no diagnosis, or the new sensor is noise the operator learns
  to skip.
* Census: +94 framework production non-comment lines, `maximum` RAISED VISIBLY
  60543 → 60637 with a per-item reason, never an allowance (nothing here has a
  deletion gate that could ever fire). Zero new production modules. Re-pins at
  zero headroom — and the first number written here was 60635, measured before
  the two attack-driven guards below existed; re-running the census over the
  COMMITTED tree is what caught it.
* `check-layer-separation.sh` — OK, no new violations. Nothing in `framework/`
  names a tool, vendor, host, industry, role or entity kind; the vendor-shaped
  facts live in `instance/config/connectors.yml`.
* COG-4 scope digest re-bound in this same commit.

## Attacks run against the fix itself, and what they changed

Ten hostile probes against the new extraction. Two found real defects and were
fixed before this commit, both at the degenerate end:

* **epoch `0` converted to 1970-01-01** — a date, which ranks and sorts like a
  real reading, where systems write 0 for "never set". Non-positive epoch
  values are now absent. Armed.
* **`date_encoding: ISO` was refused** — a config keyword refused on invisible
  case. Normalised like every other verb this lane reads. Armed.

Held under attack: a nested-only actor object gives up nothing (contents-free
survives the one level the walk descends, and the body string is absent from
the whole serialized sweep); the per-item actor cap is global across multiple
declared paths; the 200-char field cap holds on a 5000-char name; an HTTP 500
produces no spurious path diagnosis; scalar (non-object) items still read.

Reviewed by the authoring agent against the staged diff, adversarially, per the
2026-07-07 full-autonomy grant.
