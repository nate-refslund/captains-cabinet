# feat/recipient-denylist — cp1

**Unit:** a Captain-owned carve-back on `org_domains` — a recipient denylist
plus a bounded subdomain rule.
**Branch:** `feat/recipient-denylist` · base `0ab0cc2b`, merged up to origin/master
`45c004ac` mid-flight (the census-shift-left + expansion-registry landings — five
overlapping files, two conflicts resolved by recomputation rather than by picking a
side: the declared-residuals line pins and the phase-4 scope digest)
**Model:** builder Opus 5; adversarial reviewer Opus 5, fresh context, own
clone, blind to the builder's reasoning.
**Method:** every claim below is bound to a command run this session. The
reviewer re-ran the batteries itself rather than trusting the builder's.

---

## 1. The question, and the answer

> *"would it make sense to create an allowlist or/and denylist?"* — Captain,
> asked after being told "internal" means an entire media group plus **any**
> subdomain.

**A second allowlist would be wrong; a denylist is right. Both halves of that
matter.**

The allowlist already exists and the framework ships none of its own:
`framework/authority/classifier.py` `_INTERNAL_DOMAINS = env.org_domains()`,
and `env.org_domains()` reads instance config and **fails closed to EMPTY**, so
a stranger's cabinet classifies every recipient external until they add
domains. Building a second one would be a duplicate source for the same
decision — the thing the previous landing in this file explicitly refused.

The other reading of "allowlist" — a list of external recipients the cabinet
may send to *without* approval — is worse than redundant. External comms is a
non-grantable per-item Captain approval. Such a list would be the one
mechanism here capable of *loosening* an always-gated ceiling. Not built, and
the code has no way to express it.

What `org_domains` cannot express is an **exception**, and the gap was
reachable two ways with no code change and no config change:

| | Gap | Why the allowlist cannot close it |
|---|---|---|
| Address | Every address at a listed domain is internal — a distribution list or alias that fans out to non-employees classified `internal_comms`, off the always-gated ceiling | No sub-domain granularity exists. You cannot carve out one address by editing a list of domains |
| Subdomain | `dom == d or dom.endswith("." + d)` — a bare listed domain claimed its **entire** subdomain namespace, unboundedly and forever | A partner-run subdomain, or one created next year, is internal without anyone acting |

The address half is decisive on its own: no allowlist granularity, however
fine, can express "this one address at our own domain is not us". That is a
denylist by construction.

## 2. What was built

`instance/config/recipient-exclusions.yml` (+ shipped `.example` twin),
reusing the `act-first-surfaces.yml` dialect rather than inventing a second:
ruled file, `denylist: []` default, `why:` per row.

```yaml
subdomain_matching: strict        # strict (default) | inherit
denylist:                         # exactly one of address:/domain: per row, + why:
  - address: "all-staff@example.com"
    why: "distribution list — fans out to contractors. Captain ruling …"
  - domain: "newsroom.example.com"
    why: "subdomain operated by an external agency since the sale. …"
```

A deny entry with `@` matches exactly; one without matches the domain **and
every subdomain of it** — a denylist that reaches further is the safe
direction, the mirror of why the allow side is bounded.

Resolver: `framework/env.py` `recipient_policy()`, the same
framework→instance seam `org_domains()` already uses. Zero new modules.

## 3. The subdomain policy call, and its measured migration cost

| Option | Consequence | Migration cost |
|---|---|---|
| **A. Leave `endswith` unbounded, rely on the denylist** | Every future or partner-operated subdomain of a listed domain is internal until someone thinks of it. A denylist can only name subdomains a human has already imagined; the namespace is infinite and partly does not exist yet | Zero |
| **B. Strict — subdomains must be listed explicitly** (implemented as the default) | A listed domain never annexes anything. A subdomain you want internal earns its own `org_domains` line: a named, auditable claim | Recipients at subdomains of a listed domain flip internal→external, i.e. start requiring Captain approval. **Nothing escapes**; the failure mode is approval noise, loud and immediate. Measured on this deployment: the six listed domains are all apex, and a whole-tree sweep found **zero** tracked recipients at a subdomain of one — the only two subdomain recipients anywhere are synthetic test fixtures |
| **C. Wildcard opt-in (`*.corp.example`)** | Same safety as B with a shorter escape hatch | Same as B, plus a new syntax in `org_domains` and a second parser to keep in step with the bash twin |

**Implemented B, with A reachable as `subdomain_matching: inherit` — a config
line, not a code change**, exactly as directed. B is safe-by-default in the
only sense that matters for a safety classifier: it can only produce more
gating, never less. A's failure mode is silence, which is why it loses.

For a stranger whose config lists a bare domain and relies on implicit
subdomains, B breaks *toward* approval and is fixed by one line either way
(add the subdomain, or set `inherit`).

## 4. The invariant: only ever toward the ceiling

The law the previous landing established — *the predicate can only move a
recipient TOWARD the ceiling, never away* — is now **proven, not asserted**.

`framework/authority/tests/test_classifier.py`:

* `test_no_config_can_make_anything_internal_that_was_not` quantifies **every
  policy the file can express** (16 deny sets × both subdomain modes) over the
  recipient corpus, and requires each internal verdict to be admitted by a
  **frozen reimplementation of the pre-change predicate**. Frozen deliberately:
  measuring against this implementation's own widest setting would move with
  any bug that widened it, and the arm would stay green while the property it
  names broke.
* `test_adding_a_denylist_row_only_ever_shrinks_internal` pins monotonicity,
  with a non-vacuity assertion so "subset" cannot hold trivially.

Structurally the composition is one-directional: the deny check only ever
returns False, and the allow clause `dom == d or (inherit and …)` is a subset
of the old clause for every value of `inherit`.

**Sensor proof (mutation).** Each arm was shown capable of failing:

| Mutant | Arm that reddens |
|---|---|
| allow side relaxed to a dotless `endswith` | `no_config_can_make_anything_internal_that_was_not` |
| any deny row denies everything | `denylist_is_precise_not_a_blanket` + `denylisted_domain_covers_its_subdomains` |
| `inherit` ignored | `inherit_restores_subdomains_by_config_not_code` |
| deny consulted not at all | 5 arms, incl. the monotonicity non-vacuity clause |
| `rstrip(".")` on the domain split | `no_config_can_make_anything_internal_that_was_not` (after the corpus gained the trailing-FQDN-dot row the reviewer's mutant exposed) |

The reviewer independently ran 43 recipients × 16 deny sets × 4 subdomain
values (2752 combinations) against its own frozen reimplementation, including
trailing dots, multi-`@`, display-name forms, Cyrillic homoglyphs, KELVIN
SIGN, capital sharp-s, BOM/NBSP/ZWSP suffixes and the ideographic full stop:
**zero widening cases**, and `inherit` + empty deny reproduces the pre-change
predicate exactly.

## 5. Corruption honesty

| State | Result |
|---|---|
| File **absent** | Empty denylist — unchanged behaviour |
| File **present but damaged** | **Every** recipient external until repaired |
| `denylist: []` | The ruled posture, valid |
| `subdomain_matching` missing | Defaults `strict` — a dropped key fails closed only where dropping it would *loosen*, and this one narrows |

`why:` is a documented obligation and deliberately **not** a runtime gate: a
forgotten `why` must never turn an urgent Captain exclusion into a deny-all
outage. It is enforced in CI instead, where a missing one is a review defect.

## 6. Adversarial review — verdict, and what it cost

The reviewer returned **REJECT** with four blocking defects. All four were
real. All four are fixed in this branch.

| # | Defect | Fix |
|---|---|---|
| 1 | 5 CI tests red — the change shifted line numbers pinned by the declared-residuals register | Re-pinned 4 line numbers |
| 2 | **The fail-closed claim was DEFEATED.** A duplicate `denylist:` key is last-wins under `yaml.safe_load`, so appending one empties the exclusion set while every original row still reads intact above it | SafeLoader subclass refusing duplicate keys **and** aliases (a list assembled from anchors cannot be audited by eye, which is the file's only purpose) |
| 3 | Rows that parse but can **never match** were accepted — a value carrying an address separator, the `Nate <list@org>` form pasted out of a mail client, a domain with a leading dot. The Captain's exclusion would read live and exclude nothing | Refuse them loudly; 5 new damage arms |
| 4 | The new Captain-owned safety input has neither hook nor germline protection while the code consuming it has both | See below — accepted, scoped, and partly mitigated |

Non-blocking findings also fixed: a widening mutant that survived the whole
suite (corpus gained the trailing-dot row); the coverage fence walked past
`importlib`, dot-directories and plists (now any dotted mention in any
wiring-capable file type, re-armed against all three evasions); a dangling
symlink read as absent rather than damaged (`lexists`); no size bound on a
file parsed at import of a germline module; `subdomain_matching` not
case-folded, so a caps typo took the whole org to deny-all.

### On #4 — the finding is real, and broader than reported

Measured: `instance/config/platform.yml`, which holds `org_domains` — the
**allowlist this file carves back** — is likewise absent from the germline set
and from the hook's guarded paths. So the exposure is plane-wide and
pre-existing, and editing *that* file loosens **further** than editing this
one (add a domain and outsiders become internal; the worst available here is
restoring the pre-2026-07-27 subdomain rule).

The proposed two-line hook fix does not stay two lines: the hook's germline
arms are pinned against `framework/policies/immutable-core.yml` by a lockstep
meta-test, so adding a path there is a change to the **germline set** — a
Captain ceremony, not a self-ratification. Protecting only this file while
leaving `platform.yml` open would also be the exact failure this unit's
coverage fence exists to avoid: a partial fix that relabels the rest as
covered.

**Handback to the Captain**, recorded rather than worked around: add both
`instance/config/recipient-exclusions.yml` and `instance/config/platform.yml`
to the hook's protected set and to the germline set, in one amendment.

**Mitigation landed meanwhile**, needing no ceremony:
`cabinet/scripts/tests/test_recipient_exclusions_posture.py` turns CI red if
`subdomain_matching` moves off `strict`, or if a denylist row lands with no
`why`. It pins only the loosening knob and leaves the tightening surface free,
so adding an exclusion never touches it. Armed: flipping the live file to
`inherit` reddens it.

## 7. What this still cannot see — stated, not implied away

**A delivery graph.** The classifier is handed a string of addresses, never
the mailboxes behind them. An internal-looking address that relays, forwards
or fans out to outsiders is invisible **by construction** and stays internal
until a human denylists it by hand. There is no detection, and nothing here
should be read as providing any. Written into the predicate's docstring, the
live config and the shipped twin.

**The second classifier.** `framework/channels/contract.py` carries an
independent implementation of the same decision — different config file
(`instance/config/channels.yml`), still **last-address-wins** (the quantifier
hole closed on master 2026-07-27), and it ignores the exclusion policy
entirely. It is harmless today for one reason only: nothing outside
`framework/channels` mentions it in any wiring-capable file. That is a
property of the tree, not of the code.
`test_the_second_recipient_classifier_is_still_unwired` fails the day it
changes, so the gap surfaces in CI rather than in a send that should have been
gated. Unifying the two is recorded as this allowance's deletion gate.

## 8. Measured

| Gate | Master baseline | This branch |
|---|---|---|
| `pytest framework/ -q` | 1 failed / 6954 passed / 25 skipped (pre-merge base) | 1 failed / 6997 passed / 25 skipped post-merge — same single pre-existing red (`test_retro_shim.py::test_reexports_constants`); the 25-vs-26 skip count is one environment-sensitive arm (`test_journey.py:1098`, undecodable directory names) that flips run to run on master too |
| `pytest cabinet/scripts/tests -q` | 4785 passed / 28 skipped (post-merge run) | 1 failed / 4844 passed / 28 skipped — the one red is `test_cog1_outbox_capture.py::test_baselines_hold_the_bound`, a wall-clock bound that flakes only under full-sweep load: it fired on MASTER at this session's first baseline run, passes in isolation on both trees (24 passed, 51s each), and `classify_action` measures 1.24 µs/call, four orders of magnitude below the 12–14 ms p50/p95 the test bounds |
| `check-layer-separation.sh` | baseline=24 allowlist=19 new=0 | same, new=0 |
| `cognitive-architecture-census.py --check` | PASS | PASS — 69455 ≤ 69455, modules 244 unchanged |
| `cog2-import-gate.py` | rc=0 | rc=0 |
| `run-golden-evals.sh` | 32/32 | 32/32 |
| `null-hatch.sh` | rc=0 | rc=0 |
| `hatch.sh --defaults --clean-room` | — | GREEN |
| `verify-cognitive-phase4.sh` | rc=0 | rc=0 |
| A13 ledger parity | 353 rows | 353 rows |
| germline SET hash | 80 entries `ae81a892…` | 80 entries `ae81a892…` — byte-identical |

Budget: +140 framework production non-comment lines (69315 → 69455), zero new
modules, paid as a `temporary_allowances` row with the closed key set.
Docstrings counted as written.

Phase-4 review-to-bytes digest re-bound in the same commit as the contract
edit that moved it (`05c20f79…` → the recomputed value); no COG-4
implementation byte changed.

Verdict: PASS
