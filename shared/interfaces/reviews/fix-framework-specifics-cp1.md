# fix/framework-specifics — checkpoint 1

Four specifics removed from `framework/`, each one binding a stranger to the
launching operator's trade, currency or org chart. Every claim below was
measured on this tree, both directions, `__pycache__` purged.

## 1. The closed action vocabulary (worst-binding)

Measured before the change:

    submit-filing --court district   -> ambiguous, risk_class None -> propose_only
    rx-dispense --patient 12         -> ambiguous, risk_class None -> propose_only
    order-concrete --yards 40        -> ambiguous, risk_class None -> propose_only

`ambiguous` carries no risk class by design and no risk class resolves
fail-safe to `propose_only`. The fail-safe was right; its REACH was the defect.
The 30 members are one industry's verbs, so outside that industry the autonomy
ladder was unreachable — permanently, for every act. Symmetrically the
always-gated ceilings guarded classes with no members in such an operator's
world: `deploy_prod`'s members were pinned EXACTLY, so a non-software operator
could not put their own irreversible operations behind the ceiling either.
`matrix._validate_ceiling_class_mapping` enforced that exactness, and
`load_policies` refuses a layered authority matrix (D8), so there was no seam
at all.

**Now**: the framework keeps the CLASSES of consequence and the verdict each
earns; the deployment supplies the operations that fall in them
(`env.declared_operations`, `instance/config/operations.yml`). A declared id is
NAMESPACED, which is the property that keeps the two vocabularies from ever
colliding — the same never-overload law the extension-manifest plane already
uses. `ACTION_TYPES` is unchanged at 30 and still CI-pinned.

Safety properties, each an asserted arm rather than a claim
(`framework/authority/tests/test_declared_operations.py`, 27 arms):

| property | arm |
|---|---|
| un-collidable | all 30 members proven un-matchable by the id shape |
| ceiling-safe | the lookup runs after every positive ceiling rule; `cat .env` declared as harmless still classifies `secret_read` |
| fail-closed | malformed row / unknown class / unreadable file / absent file all leave the operation unclassified ⇒ propose-only |
| a function | a declaration never re-points an existing binding |
| relocation still red | moving `external_email` off its ceiling row still raises |
| typo still red | a bare non-namespaced id still raises |
| ledger reachable | a namespaced id validates as a consequence `action_type`, so the cell can be graduated AND demoted |

The consequence-event schema's `action_type` became a `oneOf` — null | the
CLOSED branch (still exactly `ACTION_TYPES`, still CI-asserted, located by
shape not position) | a pattern-gated OPEN branch, asserted un-able to match
any of the 30.

## 2. Currency

`scope.max_eur_per_day` was a CLOSED key: a grant carrying any other currency
was rejected as MALFORMED, not converted, so the spend ceiling was ungrantable
outside one currency area — while `spending-limits.yml` counted in a different
currency again. Two units, neither ever decided.

**Now** the framework compares NUMBERS and names no currency:
`max_amount_per_day` / `amount`, with the old spellings still readable so
existing grant files and executors keep working, and a row carrying both
spellings rejected (one number, one name). Printed scope no longer asserts a
unit. `spending-limits.yml` stops claiming its numbers are one currency; the
`_usd` key suffix stays, recorded as debt, because the live gate, the dashboard
and the eval harness all read those exact names.

## 3. The default actor

A role literal appeared across the acting, frontdoor, attention, watchdog,
learning, measurement, fidelity and matrix planes. A default IS needed — the
graduation/demotion cell key is `(actor, lane, action_type)`, so an act
recorded against nobody can be neither earned nor lost — but WHICH actor is a
fact about one operator's org shape, and a sole practitioner inherited a
coordinating-officer org chart plus ledger cells keyed on a stranger's role.

**Now** `env.chair_officer()` returns the deployment's own first roster entry;
no roster resolves to the EMPTY string, so the failure mode is visibly empty
rather than a name the framework picked. Verified byte-identical on this
deployment (`_ACTOR`, canary actor, chair, watchdog chair all still resolve the
same role). A shrink-only forcing arm keeps it that way: no framework
production module may construct an officer-typed actor from a literal, with one
allowed entry that is a component name rather than a role. The arm is
shape-based, never name-based — a rule keyed on this roster's actual names
would go red on a stranger's fresh deployment, which is the opposite of the
point.

## 4. The safety floor named one supplier

`no-production-deploy` was named for the category and implemented as
`["vercel deploy", "vercel --prod"]`, so the gap was invisible from the rule's
own name. Measured against the pre-change floor — every one ALLOWED:

    kubectl apply -f a.yml --context production
    helm upgrade app ./c --namespace prod
    fly deploy --app store --primary-region prod
    ./publish.sh --stage prod
    ansible-playbook release.yml -l live
    terraform apply -var env=prod

**Now** `no-production-publish` states the category in two shapes, neither
naming a supplier: an explicit live-target selection, and a publish verb
together with the live target. All six block; a control set (`ls`, `git
status`, `npm run build`, `grep -r 'deploy' docs/`, `cat
docs/production-notes.md`, `git push origin feat/x`, `brew upgrade`) does not.
The live hook carries the same two shapes — the broad one on the
already-quote-stripped command, so a mention inside a quoted argument cannot
fire it (the FW-042 lesson). The shadow fallback regex was widened the same
way, with its reason token left stable because consumers join on it.

The launching deployment's own stricter stance — its publishing CLI needs the
Captain even with no live target named — moved to
`instance/config/policies/publish-surfaces.yml`, under a distinct name so it
ADDS to the floor rather than replacing it. That directory is schg-locked, so
it is not an officer-writable weakening of the floor, and it is scrubbed from
the packaged export, so a stranger inherits the category and never the list.

## Verification

* `framework/` — 7530 passed, 25 skipped, 1 failed
  (`test_retro_shim::test_reexports_constants`, red on this machine only,
  unrelated: a model-id constant).
* `cabinet/scripts/lib/tests` — 504 passed.
* Specifics ratchet 43 passed · layer separation `new=0` · census PASS at zero
  headroom (74107, raised visibly from 73846 with the per-item breakdown in
  the contract).
* Every new arm was run against pre-change code with the fix stashed: 8 failed
  + 19 errors, i.e. no arm is silently green.
* Germline SET proven unchanged with a non-vacuous extractor (84 entries both
  sides, symmetric difference empty); `germline-lock.sh` untouched.
* No test weakened, skipped or xfailed. Two assertions were re-pointed at
  renamed identifiers and each gained a stronger companion arm.

## What was NOT fixed, and is recorded rather than relabelled

* The `_usd` suffix on the spend-cap keys (§2). The rejection defect is fixed;
  the naming is debt, because renaming reaches the live spend gate, the
  dashboard and the eval harness at once.
* `_RESERVED_SLUGS` in the onboarding estate still spells one org's role set.
* A vendor still appears in the classifier's own deploy arm and in two
  `action_type` member names; renaming a member would re-key its ledger
  history, so it stays on the existing shrink-only specifics baseline.
* Cadence and threshold constants encoding one operator's day are still
  unmeasured — named in the specifics gate's own "what this cannot see" list,
  and deliberately not claimed as covered here.
