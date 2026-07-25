# Germline amendment proposal — the `commitment` ungrantable ceiling — 2026-07-25

**Status:** AWAITING CAPTAIN. Every file this touches is germline
(`framework/authority/classifier.py`, `framework/authority/matrix.py`,
`framework/authority/policy_engine.py`, `framework/authority/grants.py`,
`framework/policies/authority-matrix.yml` — the whole `framework/policies/`
dir is locked `-R`), and applying it also moves three deliberate
enum-growth pins in shipped test files. Both are Captain acts. Reply
**"apply commitment ceiling"** and a session applies exactly the diffs below,
adds the CI proofs in the SAME commit, records the ruling in
`captain-decisions.md`, and re-runs the golden evals.

**Companion, already landed:** `framework/channels/counterparty.py` +
`instance/config/counterparties.yml.example` (branch
`feat/counterparty-commitment`). That half needed no ruling — it is additive,
non-germline, and gates nothing. This half cannot be built the same way, and
the reason is the whole point of the document.

---

## 0 · What this changes, in one paragraph

It makes **entering an obligation** a first-class action the cabinet can
recognise and can never take alone. Today the authority plane has thirty
action types, thirteen risk classes and six ceiling categories, and not one of
them is about *binding the org to a counterparty*. A cabinet that signs, agrees
a price, promises a date, or accepts terms does so today as `external_message`
— it is ceilinged as *a message*, which is the wrong noun: the ceiling is
protecting the outbound channel, not the obligation. This amendment adds one
risk class (`commitment`), two action types (`commitment_enter`,
`commitment_amend`), one ceiling category (`commitment`), and — the load-bearing
part — a **new ceiling TIER** that no posture and no standing grant can
resolve.

---

## 1 · The finding that forced a new tier (dissent-first)

The brief that produced this document asked for "a `commitment` risk class that
is HARD-CEILINGED BY CONSTRUCTION — no posture and no standing grant may
auto-resolve it". Adding a seventh row to the existing `hard_ceiling` list does
**not** deliver that, and it is worth being blunt about why, because the name
"hard ceiling" invites exactly the wrong conclusion.

`framework/policies/authority-matrix.yml:233-238` maps **every** ceiling row to
`standing_grant` under the sovereign posture, and
`framework/authority/policy_engine.py:1566-1585` resolves that verdict into an
**attributed allow** when a Captain-signed standing grant with a satisfied
scope predicate exists. So today's hard ceiling means:

> gated in guardian and earn_up; auto-resolvable in sovereign IFF a standing
> grant covers it.

That is correct for the existing six. A production deploy, a spend, a secret
read — each is a thing a Captain can reasonably pre-authorise in scope, and
each has some recovery path (roll back, refund, rotate). **A commitment does
not have one.** Once the org has told a counterparty "yes", the obligation
exists in the counterparty's world, not in a journal the cabinet controls.
There is no inverse to register, no undo window to open, and no revocation the
cabinet can perform unilaterally. A pre-authorisation is therefore
categorically wrong for it: a standing grant is a promise made *before* the
facts of the particular commitment are known.

So the amendment introduces a second, strictly stronger tier rather than a
seventh row in the first one:

| tier | guardian | earn_up | sovereign | code |
|---|---|---|---|---|
| hard ceiling (existing six) | `always_gated` | `always_gated` | `standing_grant` | `matrix.RISK_CLASSES` ∩ `hard_ceiling` |
| **ungrantable ceiling (new)** | `always_gated` | `always_gated` | **`always_gated`** | `matrix.UNGRANTABLE_CEILING` |

The ungrantable tier is a subset of `hard_ceiling` (so every existing ceiling
invariant, test and golden eval keeps applying to it unchanged) with one added
rule: `standing_grant` on an ungrantable row is a **validation error**, in
every table, in every posture, forever.

---

## 2 · Why `commitment` is not `external_comms` in a costume

Worth stating because the cheap version of this amendment is "just route it
through the existing external-comms ceiling and call it done".

* **Different object.** `external_comms` ceilings the *channel* — it asks "is
  this leaving the machine?". `commitment` ceilings the *obligation* — it asks
  "is the org now bound?". An internal commitment (a promise to an employee, an
  internal budget allocation) never touches the external-comms ceiling and is
  currently `internal_comms` → `auto_with_veto_window` at `graduated`. That is
  a live path to an unattended binding obligation.
* **Different recovery.** `external_comms` is ceilinged partly because a
  message cannot be unsent; a commitment cannot be *unmade*, which is strictly
  worse and is why the grant path must close.
* **Different evidence.** The cell key is `(actor, lane, action_type)`. Folding
  commitments into `external_message` makes their consequence history
  indistinguishable from ordinary outbound, so the org can never measure how it
  performs at entering obligations — the exact thing it would most want to know
  before ever loosening this.

---

## 3 · The exact diffs

### 3.1 `framework/authority/classifier.py` (germline)

```python
# commitment (UNGRANTABLE ceiling) — entering or amending an obligation that
# BINDS the org to a counterparty. No inverse exists: the obligation lives in
# the counterparty's world, not in a journal this cabinet controls.
_COMMITMENT = {"commitment_enter", "commitment_amend"}

CEILING_ACTION_TYPES = frozenset(
    _SECRETS | _NETWORK_WRITE | _CREDENTIALS_GRANT | _COMMITMENT)

ACTION_TYPES = frozenset(
    _REVERSIBLE | _PM_WRITE | _CALENDAR_WRITE | _INTERNAL_COMMS
    | _EXTERNAL_COMMS | _DEPLOY | _SPEND | _SECRETS | _NETWORK_WRITE
    | _CREDENTIALS_GRANT | _COMMITMENT | {AMBIGUOUS}
)
```

`_COMMITMENT` joins `CEILING_ACTION_TYPES` (the set that may never fall into the
`AMBIGUOUS` backstop), so a commitment is positively classified or the gate
fails closed — never "unclassified, therefore propose-only", which would be the
right answer by luck rather than by construction.

**Classifier branch.** There is no tool-name heuristic that reliably detects
"this binds the org" — that is a semantic property of the *content*, and
guessing it from a tool name is exactly the false confidence this program has
paid for before. So the classifier gains **no** inference rule. `commitment_*`
is reachable only when a caller DECLARES it (`tool_input["action_type"]`
declaration path, same shape the organ descriptor uses). An undeclared
commitment therefore still lands on whatever its channel classifies as, which
is no worse than today. **This is a known, stated limit of the amendment, not
an oversight** — closing it needs a content classifier and a Captain ruling of
its own, and pretending otherwise would be the "control you never tried to
defeat" failure.

### 3.2 `framework/learning/capability_gaps.py` (NOT germline)

```python
HARD_CEILING_TOUCHES = frozenset({
    "secrets", "spending", "external_comms", "production",
    "network_write", "credentials_grant",
    "commitment",          # NEW — the seventh member
})
```

### 3.3 `framework/authority/matrix.py` (germline)

```python
RISK_CLASSES = frozenset({..., "commitment"})          # 13 -> 14

# The ungrantable tier: a STRICT SUBSET of hard_ceiling whose rows may never
# carry `standing_grant` in ANY table or posture. `always_gated` is the only
# legal cell. Grants are pre-authorisations, and an obligation cannot be
# pre-authorised without knowing its terms.
UNGRANTABLE_CEILING = frozenset({"commitment"})
```

plus **invariant #6** in `_validate_verdicts` / `_validate_postures`:

```python
if rc in UNGRANTABLE_CEILING:
    if rc not in hard_ceiling:
        raise MatrixValidationError(
            f"{where}.{rc}: an ungrantable row must also be a hard_ceiling row")
    for state, verdict in states.items():
        if verdict != "always_gated":
            raise MatrixValidationError(
                f"{where}.{rc}.{state} = '{verdict}': ungrantable-ceiling rows "
                f"are always_gated in EVERY table and EVERY posture — no "
                f"standing grant may resolve an obligation")
```

Note the ordering: this check runs on the root table AND on every
`postures.*` table, and it is placed so a `standing_grant` cell raises there
rather than passing the existing ceiling-row check (which accepts
`{always_gated, standing_grant}` for a posture table).

### 3.4 `framework/policies/authority-matrix.yml` (germline dir, locked `-R`)

```yaml
    risk_classes:
      commitment:                       # UNGRANTABLE CEILING
        action_types: [commitment_enter, commitment_amend]

    hard_ceiling: [external_comms, deploy_prod, spend, secrets,
                   network_write, credentials_grant, commitment]

    ceiling_frozenset_map:
      commitment: commitment

    verdicts:
      commitment: { "*": always_gated }

    postures:
      earn_up:
        verdicts:
          commitment: { "*": always_gated }
      sovereign:
        verdicts:
          commitment: { "*": always_gated }     # NOT standing_grant
```

The sovereign row is the whole amendment in one line, and invariant #6 is what
stops a later merge from quietly turning it back into `standing_grant`.

### 3.5 `framework/authority/grants.py` (germline) — defence in depth

`CEILING_RISK_CLASSES` currently equals the six. Add `commitment` **and** a
mint-time refusal, so the wall is not config-only:

```python
UNGRANTABLE = frozenset({"commitment"})

# in the grant validator (grants.py:255 neighbourhood)
if g["risk_class"] in UNGRANTABLE:
    return None      # a grant for an ungrantable class is never valid
```

Two independent walls (the matrix cannot *say* `standing_grant`; the grants
plane cannot *mint* one) matter because a merged instance policy that failed
validation is quarantined to propose-only — safe — but a hand-written grant row
should also be inert on its own terms.

### 3.6 `framework/authority/policy_engine.py` (germline) — runtime backstop

In `_eval_authority_matrix`'s ceiling short-circuit, **before** the
`standing_grant` branch:

```python
if risk_class in UNGRANTABLE_CEILING:
    return (f"GATED (ungrantable ceiling: {risk_class}) — entering an "
            f"obligation is Captain-only; no grant and no posture resolves it.")
```

This is the belt to the config's suspenders: even a policy dict that somehow
carried `standing_grant` on the row never reaches `standing_grant_resolution`.

---

## 4 · What this amendment CANNOT do without the Captain, and why the
companion half could land alone

Four independent walls. Any one of them is enough to make this a ruling rather
than a build.

1. **Germline `schg`.** `classifier.py`, `matrix.py`, `policy_engine.py`,
   `grants.py` are in the locked `FILES` set and `framework/policies/` is in
   the locked `DIRS` set (`cabinet/scripts/germline-lock.sh:65-101,143-151`).
   The content can be built in a clone and landed, but the live checkout needs
   a Captain unlock/relock window to re-materialize the bytes.
2. **Three deliberate enum-growth pins in shipped tests.** Applying this
   amendment REQUIRES editing test files, which no build wave may do on its
   own:
   * `framework/authority/tests/test_matrix.py:164` — `len(HARD_CEILING_TOUCHES) == 6` → `7`
   * `cabinet/scripts/tests/test_cog4_exit_fixtures.py:533` — `len(RISK_CLASSES) == 13` → `14`
   * `cabinet/scripts/tests/test_cog4_organ_manifest.py:570` and
     `test_cog4_trajectory_v2.py:339` — `len(ACTION_TYPES) == 30` → `32`

   These are not incidental assertions. The COG-4 contract
   (`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md:47`) names the
   totality raise as "one of the three kept enum-growth mutants (§5.4)" — they
   exist precisely so that growing the constitutional vocabulary is a
   ceremony. Moving them is the ceremony, and it belongs to the Captain.
3. **Zero-headroom growth budgets.** `cabinet/config/cognitive-architecture-contract.yml:8-11`
   pins `central_action_types.maximum: 30` with `observed == max` by design
   (the structural-compaction mutant gate requires zero headroom). Two new
   action types require that ceiling re-ratified to 32.
4. **Lockstep mirrors that must move in the same commit** (mechanical, listed
   so the applying session does not miss one):
   * `framework/schemas/consequence-event.schema.json:42` — the closed
     `action_type` enum must equal `ACTION_TYPES` (+ null)
   * `framework/schemas/extension-manifest.schema.json:29` — the inline
     13-member `risk_class` enum, drift-pinned by
     `framework/tests/test_axes_contract.py:489`
   * `framework/schemas/cognitive-trajectory.v2.schema.json` — the inline
     risk-class enum, pinned by `test_cog4_trajectory_v2.py:413`
   * `framework/evolution/contracts.py` catalog — pinned by
     `framework/evolution/tests/test_contracts.py:59`
   * `docs/authoring-a-pack.md:77` — the "closed 13-value enum" prose
   * a new golden eval, `memory/golden-evals/eval-0NN-authority-commitment-never-granted.md`,
     mirroring `eval-011`/`eval-012` (germline dir, locked `-R`)

By contrast the counterparty registry needed none of this: it is a new
non-germline module plus a new example config, it moves no closed vocabulary,
it changes no verdict, and its one wiring point (`_base_payload`) is additive
in a file no lock covers. That asymmetry is the honest reason this document
exists instead of a second half of the branch.

---

## 5 · Proof obligations for the applying session

Both directions, cache purged, `python3.12`, serial:

1. **Positive** — a `commitment_enter` call under **sovereign posture with a
   matching, valid, unexpired standing grant present** still returns
   `GATED (ungrantable ceiling: commitment)`. This is the arm that must fail
   against pre-change code, and it is the only arm that proves the amendment
   did anything: the same scenario with `external_comms` returns an attributed
   allow today.
2. **Validator** — a matrix carrying `commitment: { "*": standing_grant }` in
   `postures.sovereign` raises `MatrixValidationError`. Mutate invariant #6 out
   and prove the arm flips (the module is not new, so absence-failure is fine
   here, but the mutant is cheap).
3. **Grants plane** — a standing-grant row with `risk_class: commitment` is
   refused at mint AND is inert if hand-written into the locked file.
4. **No widening elsewhere** — `no_ceiling_or_prod_auto()` still True; the
   earn_up narrows-validator still passes; every existing golden eval
   (011/012/013/015) still passes unchanged.
5. **Vocabulary totality** — `_validate_risk_classes` still covers every
   mappable `ACTION_TYPES` member (the new pair is mapped, nothing orphaned).

## 6 · Open questions for the ruling

1. **Two action types or one?** `commitment_enter` + `commitment_amend`, or a
   single `commitment_enter` with amendment folded in? Two gives separate
   consequence cells (amending an existing obligation is a different act from
   entering a new one); one is a smaller vocabulary bump — and the growth
   budget in §4.3 makes vocabulary size a real cost.
2. **Should `commitment` be ungrantable, or ungrantable-*for-now*?** The
   proposal makes it structural (no grant path exists at all). The softer
   alternative is a grant path that requires a per-commitment Captain
   signature rather than a standing scope predicate — narrower than today's
   grants but not a hard wall. The Captain should pick deliberately; the
   structural version is the one that matches "there is no undo".
3. **Does the counterparty registry become a precondition?** A natural next
   rule is "an obligation may only be entered with a registered counterparty
   whose consent is `granted`". That is buildable on the landed registry but is
   a second ruling, not this one.
4. **Discovery.** §3.1 states plainly that an undeclared commitment is not
   detected. Is a content classifier in scope later, and under whose gate?
