# Comms-Charter edit path — the .example twin + the one-sentence amend verb

Closes audit finding A/META (2026-07-17): the comms charter — including what
may wake the Captain — bound from `framework/attention/charter-default.yml`
with no tracked `.example` twin and no amend verb, despite the header's
one-sentence-amendment promise (§4.7).

## The three ways to change the charter

1. **Edit the file** — copy `instance/config/comms-charter.yml.example`
   (tracked, commented, ships with the framework-default values) to
   `instance/config/comms-charter.yml` and edit. A present-and-valid override
   replaces the default wholesale; validation is fail-closed against
   `framework/schemas/comms-charter.schema.json` (invalid ⇒ loud stderr line,
   framework default rules). Both the override and its ledgers are
   deployment-local (gitignored).
2. **One sentence on the Captain channel** — the binder verb (this runbook).
3. **Programmatic** — `framework.attention.charter.amend(changes, why,
   provenance)`: the provenance-laddered writer everything ultimately rides
   (schema-validated before write, atomic replace, amendment ledger row in
   `comms-charter-amendments.jsonl`). First shipped caller: the cabinet-init
   quiet-hours question (`framework/onboarding/quiet_hours.py`).

## The verb (propose-only, per the autonomy law)

Typed on the Captain channel; grammar is whole-message anchored — free text
never widens authority. Wired: `officer-inbound-poller` →
`binder_wire.handle_captain_update` (Captain-verified slot) →
`reply_binder.route_charter_amend` → `framework/frontdoor/charter_amend.py`.

```
charter: <one sentence>          # file the amendment card (writes NO charter bytes)
charter grant CHM-<8hex>         # apply the pending amendment
charter drop CHM-<8hex>[: why]   # discard it
```

Supported sentences (deterministic; anything else refuses with this menu —
the Chair LLM may still call `charter.amend()` natively for richer asks):

| Sentence | Dial |
|---|---|
| `quiet hours 22:00 to 06:30` | `quiet_hours.start/end` |
| `verbose` / `terse` | `verbosity` |
| `ack confirm-line` / `ack silent-fyi` | `ack_style` |
| `decisions cap 5` / `show at most 5 decisions` | `attention_queue.decisions_render_cap` |
| `wake me for <class>` | add to `quiet_hours.floor_classes` |
| `stop waking me for <class>` / `don't wake me for <class>` | remove from the floor |
| `route <class> <route>` / `mute <class>` | `classes[<class>].route` |

`request` parses the sentence, derives the machine yaml changes against the
live base, validates the ENTIRE merged result against the schema (fail-closed:
invalid ⇒ refusal card with the schema error, nothing written — not even a
pending row), classifies the disturbance, and files a card with the rendered
yaml diff into `instance/config/comms-charter-proposals.jsonl` (gitignored
sidecar; ids are `CHM-` + sha256(intent)[:8], so re-filing the same ask is
idempotent). Class slugs must name an existing charter class — free text never
mints a yaml value.

## §4.10.4 asymmetry (preserved — grant provenance)

Classification is CONSERVATIVE: only a provably-quieter move is `quieten`
(floor shrink, route demotion, longer quiet window, `terse`, `silent-fyi`,
lower cap); everything else — including neutral/ambiguous, e.g. an
equal-length shifted window — is `louder`.

* **quieten** → auto-applies on grant under `{trust: chair}` provenance (the
  reversible act-first rung; chair may only ever keep-or-shrink the floor —
  `charter.amend` enforces that independently).
* **louder** → applies ONLY with the Captain's citable receipt: **the grant
  reply IS the provenance.** The poller passes the grant DM's own Telegram
  message id as `receipt_message_id`; it lands on the amendment-ledger row as
  `{trust: captain, receipt_message_id: <grant reply id>}`. No receipt id
  available ⇒ the grant refuses, nothing written. The card says which class
  the amendment is before the Captain grants.

Both classifications are RE-computed at grant time against the then-current
base (the charter may have moved since the card); an amendment that already
rules is an honest no-op (`applied-noop`, no version bump).

## Files

| Path | Role |
|---|---|
| `framework/attention/charter-default.yml` | conservative framework default |
| `framework/schemas/comms-charter.schema.json` | the schema (fail-closed) |
| `instance/config/comms-charter.yml.example` | tracked commented twin (this lane) |
| `instance/config/comms-charter.yml` | deployment override (gitignored, runtime) |
| `instance/config/comms-charter-amendments.jsonl` | provenance ledger (gitignored) |
| `instance/config/comms-charter-proposals.jsonl` | pending amend cards (gitignored) |
| `framework/frontdoor/charter_amend.py` | parse/classify/file/grant/drop |
| `framework/frontdoor/reply_binder.py` | verb grammars + `route_charter_amend` |

Tests: `framework/frontdoor/tests/test_reply_binder_charter.py` (round-trip,
refusals write nothing, quieten-vs-louder pins, grant provenance, collision
corpus) and `framework/attention/tests/test_charter.py` (the `.example`
validates, is value-identical to the shipped default, and loads as the
override).
