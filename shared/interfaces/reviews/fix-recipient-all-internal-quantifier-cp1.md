# fix/recipient-all-internal-quantifier — cp1

Hostile pass on the **routing** channel of the outbound classifier — the channel
the `matrix-class-mapping-pin` landing (`2e2322d9`) explicitly left open:

> *"the pin protects the matrix layer, not the classifier's routing. If
> `_classify_mcp` were changed so an outside-recipient `queue_draft` returned
> `draft_only` instead of `external_email`, the matrix would never see an
> egress kind and this invariant never fires."*

Adversary model: **one line of classifier code, or one crafted input.** Goal:
make something that really reaches a person outside the org resolve to a
non-ceiling `action_type`, so the `external_comms` ceiling never engages.

Base: `2e2322d9` (clean clone of origin/master). Every result below was
**executed**, not read. `__pycache__` purged and `PYTHONDONTWRITEBYTECODE=1`
before every run. No sender was ever invoked: the audit never leaves
`classify_action` / `_eval_authority_matrix` / `policy-shadow.py`, and the one
hook execution was run with `CABINET_EVENT_LOG_DIR` + `CABINET_UNDO_DIR`
redirected to a scratch dir so no live ledger, undo journal or redis key was
written.

---

## 1. The paths by which an action acquires its `action_type`

Enumerated, then each **proved by execution** rather than by grep.

| # | path | `action_type` is | note |
|---|---|---|---|
| P1 | `framework/authority/classifier.py:231` `classify_action` | **DERIVED** | the only deriving function |
| P2 | `framework/authority/policy_engine.py:1538` (`_eval_authority_matrix`) | DERIVED | THE gate; result not overridable downstream (`:1540/:1568/:1622/:1678`) |
| P3 | `cabinet/scripts/policy-shadow.py:293` | DERIVED | shadow record; `main()` always returns 0 |
| P4 | `framework/authority/deploy_classifier.py:185` | DERIVED + supplied `target`/`environment` (`:174-179`) | supplied fields only widen to prod — narrowing |
| P5 | `framework/acting/action_lane.py:682-688` `ACTION_TYPE_MAP` | **SUPPLIED** (proposal step `kind`) | the acting lane never calls `classify_action`; enum-guarded at `:721`, semantic parity only by CI (`test_action_type_map_parity.py`) |
| P6 | `framework/frontdoor/action_undo.py:202,1273` | SUPPLIED | stamped into the undo journal, echoed onto the acted consequence row |
| P7 | `framework/fidelity/consequence.py:393,443` `emit_consequence(action_type=)` | SUPPLIED | **validated** against `ACTION_TYPES` (`:166-175`) |
| P8 | `framework/attention/queue.py:157` `step["action_type"] or step["kind"]` | SUPPLIED | **no enum check**; unknown ⇒ `"gate"` (fail-safe) |
| P9 | `framework/organs/descriptor.py:226` (organ manifest) | SUPPLIED | **no membership check** — `:145-160` checks "non-empty string" only |
| P10 | `framework/authority/needs.py:94,309` `file_need(action_type=)` | SUPPLIED | free text, unvalidated; `:290-295` renders it into a paste-ready grant row |
| P11 | `instance/config/standing-grants.yml` → `grants.py:259,465` | SUPPLIED | `action_types` checked as "list of str" only (`risk_class` **is** enum-pinned at `:255`) |
| P12 | `instance/config/trust-ladder.yml` → `trust_ladder.py:214` | SUPPLIED | unvalidated |
| P13 | `framework/frontdoor/binder_wire.py:285,670-677` | SUPPLIED, from **Captain Telegram text** | narrows only |
| P14 | `framework/frontdoor/binder_wire.py:829` / `actfirst_canary.py:1301` | SUPPLIED | **widens** (lifts a breaker); guarded by a ≤24h green canary receipt |

`draft_only`, `investigation_run` and `officer_dispatch` are in `ACTION_TYPES`
and carry live matrix rows, but **no branch of `classify_action` can return
them** — they are supplied-only values, and `draft_only` /
`read_only_dispatch` resolve to `notify_after` (= ALLOW) at every confidence
state. That is the shape the original warning predicted; it is reachable only
through P5/P9, not through routing.

---

## 2. The attack table

`T = mcp__brain__queue_draft`. **HELD** = landed on the `external_comms`
ceiling (or otherwise refused). **HOLE** = an outside recipient resolved off
the ceiling. 61 probes.

### A — recipient string (no code change; crafted input only)

| attack | result | verdict |
|---|---|---|
| plain external `outsider@gmail.com` | `external_email` | HELD |
| comma list, external last | `external_email` | HELD |
| **comma list, internal LAST** `outsider@gmail.com, nate@<org>` | `internal_email` | **HOLE** |
| **space separated, internal last** | `internal_message` | **HOLE** |
| **semicolon separated, internal last** | `internal_email` | **HOLE** |
| **newline separated, internal last** | `internal_email` | **HOLE** |
| **10 externals + 1 internal last** | `internal_email` | **HOLE** |
| display-name form `Nate <outsider@gmail.com>` | `external_email` | HELD |
| display name IS an internal addr, real addr external | `external_email` | HELD |
| angle-bracket internal `Nate <nate@<org>>` | `external_email` | HELD (over-gates; safe direction) |
| RFC group syntax `Team: a@evil.com, nate@<org>;` | `external_email` | HELD |

### B — the internal/external domain boundary

| attack | result | verdict |
|---|---|---|
| suffix glue `x@<org>.evil.com` | `external_email` | HELD |
| prefix glue `x@evil<org>` | `external_email` | HELD |
| uppercase `X@<ORG>` | `internal_email` | HELD (by design) |
| trailing-dot FQDN `x@<org>.` | `external_email` | HELD |
| zero-width suffix `x@<org>​` | `external_email` | HELD |
| Cyrillic homograph `stеpnetwork.dk` | `external_email` | HELD |
| IDN punycode of an org domain | `external_email` | HELD |
| unicode fullwidth `＠` | `external_email` | HELD |
| subdomain `x@mail.<org>` | `internal_email` | HELD (by design — see §4) |
| plus-address `nate+ext@<org>` | `internal_email` | HELD (delivers internally) |

### C — egress in a field the classifier does not read

`_recipient` (`classifier.py:162-167`) reads `recipient`, `to`,
`recipient_email`, `email` — **first `str` wins**, and reads nothing else.

| attack | result | verdict |
|---|---|---|
| `recipient` internal + `to` external | `internal_email` | **HOLE (latent)** |
| `to` internal + `cc` external | `internal_email` | **HOLE (latent)** |
| `to` internal + `bcc` external | `internal_email` | **HOLE (latent)** |
| `to` internal + `recipients: [external]` | `internal_email` | **HOLE (latent)** |
| `recipient` internal + `reply_to` external | `internal_email` | **HOLE (latent)** |
| `recipient: ""` shadowing an external `to` | `external_email` | HELD |
| `recipient: None` + external `to` | `external_email` | HELD |

**Latent, NOT closed here** — see §5. The documented brain signature is
`queue_draft(person, channel, draft, why)`; `person` is not among the four keys
either, so a real `person=`-only call yields `""` → external → ceiling
(fail-closed). Whether `cc`/`bcc` are accepted is a property of the **external**
brain MCP, which is not in this repo, so the reachability could not be
established from here and the fix is not made on a guess.

### D — degenerate ends (each executed)

| end | result | fails closed to external? |
|---|---|---|
| no recipient key at all | `external_email` | YES |
| empty string | `external_email` | YES |
| `None` | `external_email` | YES |
| a **list** where a string is expected | `external_email` | YES |
| a list of **internal** addresses | `external_email` | YES |
| **empty** list | `external_email` | YES |
| a dict | `external_email` | YES |
| an int | `external_email` | YES |
| whitespace only | `external_email` | YES |
| no `@` at all | `external_email` | YES |
| `tool_input` = `None` | `external_message` | YES |
| `tool_input` = `{}` | `external_message` | YES |
| **domain allowlist absent / empty / unparseable** | every recipient external | YES — `env.org_domains()` (`framework/env.py:227-273`) swallows every exception and returns the EMPTY tuple; `platform.yml` then `product.yml`, any parse failure `continue`s |

**Every degenerate end fails closed to external.** The stated intent holds and
is now measured, not assumed.

### E — tool-name routing

| attack | result | verdict |
|---|---|---|
| `queue_draft` with **no** `__` (so `_classify_mcp` is never reached) | `ambiguous` | HELD — `risk_of` ⇒ `None` ⇒ propose-only |
| `mcp__resend__send_email` | `ambiguous` | HELD (propose-only) |
| `mcp__gmail__messages_send` | `ambiguous` | HELD |
| `mcp__msgraph__sendMail` | `ambiguous` | HELD |
| `mcp__slack__send_message` | `ambiguous` | HELD |
| unknown tool / empty / `None` tool name | `ambiguous` | HELD |

Confirmed by execution in both postures: `ambiguous` has no `risk_class`, so
`_eval_authority_matrix` step 1 returns `PROPOSE-ONLY (unclassified action
'ambiguous')`. **A renamed or unknown sender cannot auto-act.** It is a
*coverage* gap (a real egress is labelled "unknown" rather than
`external_comms`/`network_write`), not a fail-open.

### F — Bash egress

| attack | result | verdict |
|---|---|---|
| `curl -X POST https://api.resend.com/emails` | `mcp_post` | HELD (network_write ceiling) |
| `sendmail outsider@gmail.com < body` | `local_edit` | **HOLE (reported, not closed)** |
| `mail -s hi outsider@gmail.com` | `local_edit` | **HOLE** |
| `python3 -c "…smtplib…sendmail…"` | `local_edit` | **HOLE** |
| `osascript … "Mail" … send` | `local_edit` | **HOLE** |
| `osascript … "Messages" … send … buddy` | `local_edit` | **HOLE** |
| `curl 'https://hooks.slack.com/…?text=…'` (GET) | `local_edit` | **HOLE** |

See §5 — reported with evidence, deliberately out of this commit's scope.

---

## 3. The gate verdict, measured

Classifier labels are not the control; the verdict is. Each case driven through
the real `_eval_authority_matrix` with the real merged matrix, `read_cell_state`
pinned to `unmeasured` (the day-one state):

| case | action_type | risk_class | guardian | sovereign |
|---|---|---|---|---|
| external control | `external_email` | external_comms | GATED (hard ceiling) | GATED (standing_grant) |
| internal control | `internal_email` | internal_comms | PROPOSE-ONLY | **ALLOW** |
| **R1 comma, internal last** | `internal_email` | internal_comms | PROPOSE-ONLY | **ALLOW** |
| **R1 space, internal last** | `internal_message` | internal_comms | PROPOSE-ONLY | **ALLOW** |
| R2 `sendmail` | `local_edit` | reversible | **ALLOW** | **ALLOW** |
| E unknown sender | `ambiguous` | — | PROPOSE-ONLY | PROPOSE-ONLY |

`internal_comms` is `notify_after` at **every** confidence state in the
sovereign posture table (`framework/policies/authority-matrix.yml`), so R1 is an
auto-send to an outside address on day one, at unmeasured confidence, with no
graduation earned.

**Severity qualifier, measured not assumed.** The matrix gate is not today's
live blocker for this tool. `instance/config/authority-enforcing` exists and is
tracked, but the hook path it enables (`cabinet/scripts/hooks/pre-tool-use.sh:61-70`)
runs `policy-shadow.py`, whose `.decision` field is the **regex** shadow. Driven
with the real hook input, both the plain external send and the R1 string
returned `{"decision": "allow", "policy_version": "shadow-v1",
"reason": "no_shadow_rule_matched"}`. `policy_engine.main()`'s authority loop is
separately gated on `CABINET_AUTHORITY_ENFORCING` defaulting `"0"`
(`policy_engine.py:1921`). So R1 defeats the **designed** ceiling and — live,
today — the consequence-ledger cell key, the graduation math, standing-grant
scoping and the trust ladder, all of which key on `action_type` now. It becomes
a live send-authorisation bypass at the Captain-gated enforcing flip.

---

## 4. What "internal" admits at its widest reading

`_INTERNAL_DOMAINS = env.org_domains()` ← `instance/config/platform.yml`:
`stepnetwork.dk`, `jfmedier.dk`, `jysk-fynske-medier.dk`, `polads.eu`,
`refslund.ai`, `step.dk`. Match is `domain == d or domain.endswith("." + d)`.

At its widest, "internal" currently admits:

1. **Every mailbox in an entire media group.** `jfmedier.dk` /
   `jysk-fynske-medier.dk` is Jysk Fynske Medier — thousands of employees
   across many mastheads, the overwhelming majority of whom are third parties
   to this cabinet's work. The prior gate's finding is unchanged.
2. **Every subdomain, unboundedly** — `endswith("." + d)` admits
   `anything.polads.eu`, including a customer-facing or partner-operated
   subdomain, and any future subdomain nobody re-approves.
3. **Distribution lists and aliases at those domains.** `everyone@jfmedier.dk`
   or a partner-facing alias classifies internal and may fan out to, or forward
   to, arbitrary outside addresses. The classifier sees an address, never a
   delivery graph, so **an internal-looking address that relays externally is
   invisible to it by construction.**
4. **`polads.eu` and `refslund.ai`** are product/brand domains, so any address
   stood up on them (`press@`, `support@`, a forwarding catch-all) is internal.

The set is Captain-owned instance config and fails closed to empty, which is
right. This commit does not narrow it — narrowing it is a Captain call, and (3)
in particular is not solvable by a domain list at all.

---

## 5. What this commit does and does not close

**CLOSED — R1.** `_is_internal_recipient` was `any`-quantified by accident:
`rsplit("@", 1)` over the WHOLE field meant only the LAST address decided. It is
now **ALL**-quantified — every address in the field must be at an org domain —
against the SAME one declared source (`_INTERNAL_DOMAINS`). No second list is
introduced and none is removed. Splitting is on address separators only
(`[\s,;]`), so every other character stays glued to its token and the
display-name form still classifies external exactly as before. **Strictly
narrowing: the predicate can only move a recipient toward the ceiling.**

Arms fail against pre-change code: **5 failed / 128 passed** on pristine
`2e2322d9` with `__pycache__` purged, vs **133 passed** after. The sixth arm
(internal FIRST) passed pre-change — it was already caught — and is pinned so a
future edit cannot open it. Four held-cases are pinned too, so the narrowing
cannot be over-applied and swallow the internal path.

**NOT CLOSED — reported with evidence:**

- **R2 — the Bash catch-all.** `_classify_bash` ends `return "local_edit"`
  (`classifier.py:359`) for everything unmatched, which **contradicts this
  module's own docstring** (`:19-21`: *"Ambiguous / unknown actions resolve to
  `AMBIGUOUS` … NOT silently to `local_edit`. Only a positively-local /
  no-egress signal yields `local_edit`"*). `local_edit` is `reversible` ⇒
  `act_with_undo` in guardian, `auto` in sovereign. Compensating controls exist
  and are real but partial: `instance/config/egress.yml` is `enforce: true` with
  `allow_hosts: []`, and on macOS the launcher additionally asks Seatbelt to
  deny direct external TCP/UDP — which covers `curl`/`smtplib`, but **not** a
  local-IPC path such as `osascript … Messages … send`. No plane in
  `framework/` or `cabinet/` matches `sendmail`/`smtp` at all (grep: zero hits).
  Fixing it means making Bash's fallback `AMBIGUOUS` rather than `local_edit`,
  which is a behaviour change across the whole Bash surface and deserves its own
  unit and its own attack pass — not a rider on a comms fix.
- **R3 — the field-shadow family (§2C).** Needs the external brain MCP's real
  parameter list to know which fields exist; guessing a field list is exactly
  the hand-maintained list this program removes rather than adds.
- **P8/P9/P11 — supplied `action_type` trusted without `ACTION_TYPES`
  membership** in `attention/queue.py:157`, `organs/descriptor.py:145-160`
  (which explicitly disclaims the check) and `grants.py:259`. `risk_class` is
  enum-pinned in `grants.py:255`; `action_types` is not.
- **Coverage, not fail-open:** a renamed/unknown sender lands on `ambiguous`
  (propose-only, correct) rather than on `external_comms`/`network_write`.

---

## 6. Verification

- Both directions proven, `__pycache__` purged: 5 fail pre-change, 133 pass after.
- `framework/authority/` suite: 1039 passed.
- `cognitive-architecture-census.py`: PASS, `framework_production_noncomment_lines`
  69129 <= 69129 — **observed == max, zero headroom preserved**, paid as a
  `recipient-all-internal-quantifier` `temporary_allowances` row (+13) with the
  closed key set. Docstrings counted, **not** reformatted into `#` comments.
- `check-layer-separation.sh`: OK, `new=0`.
- Germline: `germline-lock.sh` **untouched** — `git diff origin/master` on it is
  empty, so the path SET is byte-identical by construction. Extractor proven
  non-vacuous (drop-one and add-one both change the hash; 67 members). Only
  CONTENT of an already-locked file changed — landed-then-ceremonied, the
  Captain unlock/relock re-materialises the landed bytes.
- The contract file is inside the phase-4 frozen-review digest scope (the only
  touched path that is), so the re-bind ceremony rides THIS commit —
  MECHANICAL-DELTA, zero reviewed behaviour bytes in scope.
- No threshold raised, no test weakened, skipped or xfailed. No sender invoked.
