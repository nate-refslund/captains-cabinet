# Outbound identity — separating the cabinet from the Captain (2026-07-25)

**Status:** landed as code, with one open Captain question and one reported test
contradiction. Self-ratified per the 2026-07-07 full-autonomy grant + the
2026-07-21 ownership-on-GO extension.

**Measured against** master `05871f128da8e2be9e94e50ff531f35f6f9bd719`.

---

## 1. The finding, re-verified

An independent assessor reported this at master `138a2532`; master has moved, so
every claim was re-confirmed at `05871f12` before any code was written. **All
four premises held**, at the same file:line:

| Claim | State at `05871f12` |
|---|---|
| `framework/frontdoor/chair_drafts.py:56` appends the Captain's own email signature to outbound before he sees it | **TRUE** — `draft = get_dispatch().ensure_signature(draft, channel_name)`, unconditional |
| `instance/config/act-first-surfaces.yml:47-50` is a ratified "act like me" credential policy | **TRUE** — verbatim, lines 47-57 |
| Zero AI-generated disclosure anywhere in the tree | **TRUE** — the only hit for any disclosure phrasing is the Monday-board obligation text at `act-first-surfaces.yml:82-86` |
| internal-vs-external is an email-domain suffix match, org list includes a media group | **TRUE** — `framework/authority/classifier.py:154-159` against `framework.env.org_domains()`; `instance/config/platform.yml:60-66` lists six domains including a whole media group |

The consequence is one sentence: **the cabinet had no identity of its own, so
every message it sent was, on its face, written and signed by the Captain
personally.** That was survivable while it only ever wrote to him. It is not
survivable now that it writes to real people.

## 2. What this change does

Two separable things, both deployment-config driven, neither hardcoding an
address, a person or an org.

**Identity** — `framework/outbound_identity.py` resolves
`instance/config/outbound-identity.yml` into a from-address / reply-to / display
name / credential-env NAME / sign-off, plus a `mode` switch:

* `mode: cabinet` (**the default**) — the Captain's personal signature is *never*
  applied. The cabinet's own configured sign-off is used, and if none is
  configured the message goes out unsigned rather than borrowing his.
* `mode: captain` — the pre-change behaviour, reachable only by an explicit,
  well-formed opt-in.

**Disclosure** — a loud, human-legible machine-provenance line on every channel
that reaches a non-Captain human. This is not a new obligation; it is the one
the act-first Monday surfaces already carry
(`act-first-surfaces.yml` `provenance-banner`), lifted out of "board artifacts
only" and made channel-general. It applies in **both** identity modes: signing as
the Captain does not buy silence.

Wired at four seams:

| Seam | What changed |
|---|---|
| `chair_drafts.present_draft` | composition — whose sign-off closes it, plus the disclosure. The Captain approves the exact bytes the recipient reads |
| `chair_drafts.deliver_draft` | fail-closed egress — stamps whatever is actually about to leave, including a Captain `edit: <text>` override that never passed through `present_draft`, and any draft written into the store by a path that bypassed it |
| `action_exec` Monday note bodies | `monday_task_update` posts onto items the lane did **not** create, so the body is the only thing a colleague reads — it carried an opaque correlation id and no human-legible authorship. The obligation always covered it; only the title half was implemented |
| `channels.ChannelAdapter` | the outbox ledger now records `disclosure_required` / `disclosed`, so an undisclosed outbound message is a visible fact instead of an invisible one |

**Fail-closed, to the safe side.** Absent, unreadable, symlinked, unparseable,
unknown-key, wrong-version or malformed-in-any-way config all resolve to
`mode: cabinet` + disclosure on + every address empty. There is no partial
parse: one bad key returns the whole file to that default, so a typo cannot
silently half-configure who the cabinet is. Every malformed-config test arm
plants a valid `mode: captain` beside the malformation and asserts the resolved
mode is `cabinet` — that is the discriminator between "the file was refused" and
"the bad field was ignored", which otherwise look identical.

**Secrets.** The config carries the NAME of a credential environment variable,
never a value; the module never reads that variable. Same discipline as the
act-first acting-identity block.

**A configured from-address is a promise, and it is kept or refused.**
`instance/flavor-a` sends through the Captain's own mailbox and has exactly one
identity. If a deployment configures a distinct cabinet `from_address`, that
dispatch now **refuses the send** rather than quietly delivering under the
Captain's name — a silent fallback would be precisely the confusion this file
exists to end. Records with no `sender` block are byte-identical to before.

## 3. The ratified policy is NOT overturned

`act-first-surfaces.yml:47-53` carries the Captain's ruling: *"Use my existing
Monday API key with full privilege as the agent token — I want the cabinet to be
able to act like me."* That file is germline (schg-locked,
`cabinet/scripts/germline-lock.sh:90`) and **was not touched**.

Nothing here contradicts it. That ruling is about the **project-management
estate**, where the audience is a board row. This change addresses the **comms
estate**, where the audience is a human being. It makes the alternative exist and
be selectable; pointing both estates at one identity is now a choice rather than
the only available behaviour.

### Open Captain question (does not block this landing)

The disclosure now covers the comms estate. The Monday estate still acts under
the Captain's full-privilege personal token, so a board write is still
attributable to him personally — the `🤖 cabinet:` banner tells a reader a
machine wrote the text, but the audit log still says he did it. Closing that
would mean a scoped agent user on the PM estate, which **would** contradict the
ratified line. That is the Captain's call, not this session's.

## 4. Reported contradiction — the channel-adapter body is NOT stamped

The strongest form of "every channel discloses" would stamp inside
`ChannelAdapter.send()`, before `_dispatch_send`. **Three existing tests pin
verbatim body passthrough** and forbid it:

* `framework/channels/tests/test_contract.py:196` — `assert a.calls == [("bob@acme.com", "hello world", "t-1")]`
* `framework/channels/tests/test_contract.py:211` — `body_sha256 == sha256(b"hello world")`
* `framework/channels/tests/test_teams_outlook.py:66` — `assert transport.calls == [("bob@acme.com", "hello", "19:thread")]`
* `framework/channels/tests/test_slack.py:62` — `assert call["payload"] == {"channel": "C123", "text": "hello"}`

Those tests encode a real contract — `send()` hands the transport the caller's
bytes — and they were not edited. Two facts bound the exposure: the Teams and
Outlook adapters cannot reach a human at all (their default transport is
`queue_draft_stub`, which raises), and Slack's live transport is gated on
`framework.env.allow_sends()`. The live path to real people is `chair_drafts` →
dispatch, which **is** fully covered.

What shipped at that seam instead is audit, not mutation: `disclosure_state()`
plus two ledger booleans, so an undisclosed outbound send on any adapter is a
recorded fact. Making it a refusal or a stamp is a deliberate follow-up that has
to reckon with those four assertions first.

## 5. Evidence

Serial sweep, `__pycache__` purged and `PYTHONDONTWRITEBYTECODE=1` before every
run, against a re-measured baseline at `05871f12`:

| Gate | Baseline | After | Delta |
|---|---|---|---|
| `pytest framework/ --collect-only` | 6515 | 6578 | +63 |
| `pytest framework/ -q -rs` | 1 failed, 6489 passed, 25 skipped | 1 failed, 6552 passed, 25 skipped | +63 passed; the one failure is the known out-of-repo `test_retro_shim.py::test_reexports_constants`, unchanged |
| `pytest cabinet/scripts/tests -q` | 4543 passed, 28 skipped | 4543 passed, 28 skipped | 0 |
| `check-layer-separation.sh` | baseline=24 allowlist=19 current=43 new=0 | identical | 0 — neither the baseline nor the allowlist grew |
| `docs-track-code-sweep.sh` | GREEN (files=60 findings=0) | GREEN (files=60 findings=0) | 0 |
| `pytest framework/sources framework/tests` (null-source subset) | — | 1152 passed, 1 skipped | green |

**Both directions.** The new module is brand new, so absence-failure proves
nothing about it; its guards are proven by mutation instead — each arm in
`TestGuardsAreLoadBearing` disables exactly one guard (the closed key sets, the
version pin, the mode vocabulary, the realpath containment probe, the fallback
posture itself) and asserts the protected property flips. The wiring was proven
the other way: the two new test files were copied onto a clean checkout of
`05871f12` **together with `framework/outbound_identity.py`**, so the only thing
missing was the wiring. 14 of 16 wiring arms went red there; the 2 that stayed
green are explicitly no-regression arms (an already-disclosed draft is
byte-unchanged; the body still never reaches the ledger).

## 6. What a deployment does now

Nothing, to be safe — the default is the safe posture and needs no file. To sign
as the Captain again, or to give the cabinet a real mailbox of its own, copy
`instance/config/outbound-identity.yml.example` and edit it.
