# Germline amendment proposal — COG-5 FROZEN-HOLDOUT Ring-0 listing in immutable-core.yml — 2026-07-24 (CG-34)

**Status:** AWAITING CAPTAIN — FILED AT COG-5 CONTRACT LANDING, NOTHING
APPLIED. Like the CG-33 precedent (and unlike CG-4, whose edit was already
staged under an open window), the one germline file named below —
`framework/policies/immutable-core.yml` — is byte-unchanged everywhere
(master and live tree) at filing time: this document IS the complete
proposed edit text, filed at maximum lead time per COG-5 contract §7.5.1
(MR1) so the Captain can open the window at convenience. Until the window
opens, every dependent COG-5 **freeze-verification unit PARKS with a dated
marker** (the arming-record `holdout_freeze` line; any sim arm premised on
Ring-0 refusal) — schg is NEVER edited or worked around (a recorded
handback beats a workaround). Reply **"apply holdout-freeze"** to authorize
the window; a decline leaves the file untouched (there is nothing to revert
before apply).

**BATCHABLE WITH CG-33 — say the word once, open one window:** the CG-33
extension-gate amendment (HANDBACKS item 19,
`~/cabinet-meta/HANDBACKS-perfect-cabinet-2026-07-10.md:319-327`) is
already awaiting the same ceremony shape (sudo unlock → land reviewed
edit(s) → same-day relock). This amendment is explicitly batchable with
that window at the Captain's convenience: ONE window, up to three reviewed
germline edits (the CG-33 pair + this one-entry listing), same-day relock.
The batching offer is DATED as of 2026-07-24 and re-verified at COG-5 WG
(contract §7.5.3): if item 19's window has meanwhile opened and closed,
this handback stands alone.

**Branch of record:** none yet — the edit is NOT staged. COG-5 W5+ units
build AGAINST this document's proposed text; the windowed micro-unit
applies it via the normal worktree → PR → per-job-CI → master flow INSIDE
the window, then the live tree syncs checkout-from-master with blob-verify
(the CG-27/CG-31 ceremony precedent). Ledger row: **CG-34**
(`docs/plans/operative-egg-ledger-2026-07-07.yml`, captain-gated).

**Naming note:** the COG-5 contract (§7.5.1, §14.1) names this document by
its drafting title `germline-amendment-holdout-ring0-2026-07-24.md`; it
lands as THIS file (`germline-amendment-immutable-core-holdout-2026-07-24.md`,
named for the one germline file it edits). Same document, one filename of
record — this one.

**Encodes (already-ruled — reference only, do NOT re-paste):**

- **COG-5 contract of record**
  (`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md`) §7.4 (the
  STAGED freeze truth — Stage A/Stage B), §7.5 (the germline ceremony:
  proposal doc + CG row + NAMED handback, all filed at contract landing —
  MR1), §7.3 (league invisibility rows + AST pin), §6.3 (the league-open
  checklist requires Stage B LANDED), §19 MR1 (the attack's serious #1,
  adopted: the synthesis's "no sudo window needed" was a FILES-only grep,
  refuted against the DIRS cover). Premise-check `wf_fc493c16-a6a`
  READY-TO-PLAN + attack UPHOLD; four-lens panel + rev-1 + independent
  MF-verify LAND.
- **Evolution spec** `docs/plans/evolution-engine-spec-2026-07-05.md` :19 —
  the holdout is separately versioned, league-invisible, and Ring-0-listed
  so the Foundry can never optimize its own exam (the intended
  self-protection this listing delivers).
- **CG-33 precedent**
  `docs/proposals/germline-amendment-extension-manifest-organ-2026-07-23.md`
  — filed-at-landing shape, PARK fallback, window ceremony; **CG-4
  precedent** `docs/proposals/germline-amendment-manifest-sunset-2026-07-07.md`
  — the additive-optional one-file amendment with one-revert rollback.
- **Provenance:** per the 2026-07-07 full-autonomy grant + the Captain
  2026-07-20 cognitive-masterplan grant (contract landing filed this doc);
  the germline window itself is Captain-only, non-grantable.

## §0 · What this changes, in one paragraph

`framework/policies/immutable-core.yml` — the single source of Ring-0
paths — gains EXACTLY ONE `files`-class entry:
`framework/evolution/holdout_gen.py`, the COG-5 frozen-holdout generator,
carrying `pending:` flags for all four germline enforcement lists per the
SOV-C8 lockstep mechanism (the axes-amendment precedent). From the listing
ALONE, consumer 1 — `gate.ratify` S0 `touches_ring0`
(`framework/learning/gate.py:347`) — thereafter REFUSES any
self-improvement code-diff touching `holdout_gen.py`: the header's own law
(immutable-core.yml:8-12) is that S0 refusal covers "every class, not just
the locked ones", so refusal does NOT wait on the `pending:` wirings. The
four-list schg/hook/base-safety propagation (germline-lock FILES, hook §5,
hook §5b, base-safety patterns) rides `pending:` and flips list-by-list in
later Captain windows (wire the list, delete the flag, same commit —
immutable-core.yml:41-50; each list is itself germline, so the wirings are
themselves windowed edits). No existing entry, class, list, consumer, or
comment is touched; the edit is one comment block + two YAML lines,
strictly additive.

## §1 · The COMPLETE proposed edit text (`framework/policies/immutable-core.yml`, germline by dir-cover)

**Insertion point:** end of the `files:` section — immediately after the
`ALSO NOT ENUMERATED` comment block's last line
(`#  generate-plists.py. Justified in the cabinet-axes amendment doc.`,
:221 at tip `70bca2ae`), keeping the blank line before `dirs:` (:223).

```yaml
  # --- COG-5 FROZEN HOLDOUT generator (amendment 2026-07-24, docs/proposals/
  #     germline-amendment-immutable-core-holdout-2026-07-24.md, CG-34; COG-5
  #     contract §7.4/§7.5; evolution spec :19): the frozen holdout suite's
  #     generator — separately versioned, league-invisible, Ring-0-listed so
  #     the Foundry can never optimize its own exam. From this listing alone,
  #     gate.ratify S0 (consumer 1 — "every class, not just the locked ones")
  #     REFUSES any self-improvement diff touching it; the four-list
  #     schg/hook/base-safety propagation rides `pending:` per the SOV-C8
  #     lockstep mechanism and flips list-by-list in later Captain windows
  #     (wire the list, delete the flag, same commit). The file is W5-built —
  #     listed before it exists (the gate-apply.sh precedent: germline-lock
  #     skips absent paths; the lockstep meta-test exempts pending entries
  #     from the exists-on-disk guard). ---
  - path: framework/evolution/holdout_gen.py
    pending: [germline-lock, hook-s5, hook-s5b, base-safety]
```

Shape compliance with the lockstep meta-test
(`framework/tests/test_germline_lockstep_consistency.py`, byte-verified at
`70bca2ae`): keys ⊆ `{path, pending}` (closed-key check); `pending` values
⊆ the canonical `lists:` vocabulary (immutable-core.yml:60) and ⊆
`_required_lists("files")` = all four (:213-219); a `files` entry with
`pending` is EXEMPT from the exists-on-disk typo guard (:415-435 — "pending
entries are built by later lanes"), so the listing legally precedes the W5
build of `holdout_gen.py` itself; each pending (path, list) pair runs as
`xfail(strict=False)` (:227-234) and flips to a hard assert when its flag
is deleted at wiring time.

## §2 · Why this needs a Captain window (the dir-cover evidence — MR1)

`framework/policies` is schg-locked as a WHOLE DIRECTORY:

- `cabinet/scripts/germline-lock.sh` `DIRS=(` (:143) carries the entry
  `"framework/policies"` (:145), under the array's own law (:141-142):
  "whole directories locked -R (blocks edit AND new-file/rename/unlink
  inside — closes the `cp evil framework/policies/newfile` class at the FS
  layer)". Any edit to `immutable-core.yml` — including this one-entry
  addition — is blocked at the filesystem until a Captain `sudo` unlock.
- `immutable-core.yml` self-documents the same: the `dirs` class means "any
  path under one is Ring-0 by dir-cover, including this file itself
  (framework/policies/ ⇒ auto-covered by all four lists — no list additions
  needed for it)" (:25-28); its EDIT DISCIPLINE (:52-54): "this file is
  itself Ring-0 (dir-cover). Officers/loops propose changes to the Captain;
  only the Captain applies them in a germline-lock unlock window." The file
  even enumerates itself (`- path: framework/policies/immutable-core.yml`,
  :172) and `framework/policies/` sits in its own `dirs:` list (:225).

The COG-5 premise-check synthesis initially claimed "no sudo window needed"
— a grep against the FILES array only; the adversarial attack's serious #1
refuted it against the DIRS cover and the contract ADOPTED the refutation
(§19 MR1). This proposal is that adoption: the listing is a Captain sudo
ceremony, never an orchestrator act.

## §3 · What the listing does — Stage B semantics (contract §7.4)

The holdout freeze END-STATE is four properties: (i) separately versioned,
(ii) league-invisible, (iii) Ring-0-listed so gate S0 refuses any Foundry
diff touching it, (iv) thereafter mutable only via a Captain
germline-unlock window. **This amendment IS Stage B — it makes (iii) and
(iv) true**, and they are true from this listing onward, never earlier:

- **(iii)** binds from the LISTING alone: `touches_ring0` (gate.py:347)
  reads every entry in every class of immutable-core.yml (header :8-12);
  no `pending:` flag weakens it.
- **(iv)** holds because `framework/policies/` dir-cover schg then covers
  the listing TEXT itself — un-listing `holdout_gen.py` would be another
  Captain-windowed germline edit (which is exactly why LANDING the listing
  needs the window in the first place).
- The `pending:` flags cover ONLY the four enforcement-list propagations
  (schg/hook/base-safety reach for the file's own bytes); they flip when a
  Captain unlock window — the same one or a later one — lands those list
  edits. Gate-S0 refusal does NOT wait on them.
- The COG-5 league-open checklist (contract §6.3) requires **Stage B
  LANDED**; until then the arming record carries
  `holdout_freeze: pending-captain-window`.

## §4 · Until the window — Stage A interim posture, stated honestly (contract §7.5.5)

In-phase, BEFORE this amendment lands, COG-5 ships: (a) a content-pin
sibling test (sha256 of `holdout_gen.py` bytes; drift REDs CI), (b) the
§7.3 league-invisibility boundary rows + AST pin, (c) an egg-export
EXCLUDE + expect-absent line for `holdout_gen.py` (the O-B3 precedent) so
no hatched cabinet ships an unprotected generator — retired when this
listing lands, (d) the oracle CLI as sole sanctioned reader. **HONESTY
CLAUSE: none of this equals the Ring-0 listing** — no schg, no hook guard,
no gate-S0 refusal; until listed, `touches_ring0` does NOT refuse Foundry
diffs to `holdout_gen.py`, and a same-uid actor could edit file and pin in
one commit. The interim posture is honestly NOT Ring-0; no
fitness/promotion claim may ever cite holdout results while interim
(vacuously safe this phase — the league ships CLOSED).

## §5 · Correctness proof (additive-only, fail-closed direction)

1. **Strictly additive:** one new `files` entry; no existing entry, key,
   class, list, or comment changes; the YAML stays a mapping of the same
   four classes; `version: 1` and `lists:` untouched.
2. **The only behavior delta is a REFUSAL widening:** consumer 1 (gate S0)
   refuses strictly MORE diffs (those touching `holdout_gen.py`) — the
   fail-closed direction; it can admit nothing it previously refused.
   Consumer 2 (the lockstep meta-test) gains four `xfail(strict=False)`
   parametrizations (the pending pairs) and the well-formedness checks pass
   by §1's shape compliance — no existing assertion weakens.
3. **No consumer is required to change:** germline-lock.sh is not edited
   (the `germline-lock` wiring rides `pending:`; the script skips absent
   paths by design, so even post-wiring an unbuilt `holdout_gen.py` is
   safe — the gate-apply.sh "enumerated + wired before it exists"
   precedent, immutable-core.yml:153-161); hooks and base-safety likewise
   untouched until their pending flips.
4. **The amendment-doc lint stays green:** the per-package table
   (`framework/tests/test_amendment_doc_lint.py`) is untouched — like the
   CG-33 proposal, a pending amendment adds no package entry; the
   union-coverage test (`test_every_immutable_core_entry_referenced`)
   requires every immutable-core entry to be referenced in SOME
   `germline-amendment-*.md` doc, and THIS document names
   `framework/evolution/holdout_gen.py` — so the union is covered the
   moment the listing lands.
5. **A13/ledger surfaces:** the CG-34 row + plan-doc twin land with the
   COG-5 contract (this filing); the window itself only flips their status.

## §6 · One-revert rollback

**One-revert rollback:** a single checkout of the one named germline file
restores the pre-amendment bytes; the edit is a self-contained one-entry
addition with no cross-file coupling, no state migration, and no consumer
that requires it. The restore is ITSELF a germline edit and rides a
Captain window (a germline edit both ways — COG-5 contract §16):

```bash
git -C /Users/nate/captains-cabinet checkout <pre-amendment-ref> -- \
  framework/policies/immutable-core.yml
```

Every germline file in this amendment:
`framework/policies/immutable-core.yml`.
(`framework/evolution/holdout_gen.py` is the LISTED SUBJECT, not an edited
germline file — it lives outside germline and is built by COG-5 W5;
nothing in it needs reverting here.)

On rollback: gate-S0 refusal over `holdout_gen.py` ceases; every COG-5
freeze-verification unit PARKS again with a dated marker (the same
fallback as a never-opened window); the league-open checklist's Stage-B
requirement returns to unmet and the arming record's
`holdout_freeze: pending-captain-window` line stands. Nothing outside
COG-5 reads the listing.

## §7 · Verification battery (runs in-window; rehearsable pre-window against a COPY of the file)

```bash
# Gate A — the edited file parses and the lockstep meta-test is green
# (the four pending pairs run xfail, everything else hard):
python3.12 -c "import yaml; yaml.safe_load(open('framework/policies/immutable-core.yml'))"
python3.12 -m pytest framework/tests/test_germline_lockstep_consistency.py -q

# Gate B — gate S0 refusal BINDS from the listing alone: a synthetic
# self-improvement diff touching framework/evolution/holdout_gen.py is
# REFUSED by touches_ring0 (gate.py:347); the same probe run pre-window
# (against an edited COPY on an untouched tree) is the rehearsal.

# Gate C — negative control: a diff touching a non-listed
# framework/evolution/ sibling (e.g. archive.py) is NOT refused by the new
# entry — the listing widens refusal by exactly one path.

# Gate D — the amendment-doc lint stays green with this doc in the
# proposals union (incl. union coverage of the new entry via THIS doc):
python3.12 -m pytest framework/tests/test_amendment_doc_lint.py -q
```

## §8 · Captain window procedure (the CG-33 ceremony; batchable)

1. Fetch; re-verify lock state FRESH immediately before acting:
   `cabinet/scripts/germline-lock.sh status` + `ls -lO` on
   `framework/policies/` (boundary state changes across sessions — never
   assume).
2. Captain sudo: `sudo cabinet/scripts/germline-lock.sh unlock`.
3. Apply THIS document's §1 edit text to
   `framework/policies/immutable-core.yml` — landed via the normal
   worktree → PR → per-job-CI → master flow inside the window; the live
   tree then syncs `git checkout origin/master --` on the file with
   blob-verify vs origin/master (CG-27/CG-31 ceremony precedent).
   **If batched with CG-33 (item 19):** apply that proposal's pair in the
   same window, each via its own reviewed flow.
4. Run the §4 battery of each applied amendment: here, §7 gates A-D green.
5. SAME DAY: `sudo cabinet/scripts/germline-lock.sh lock`, then `status` +
   `verify` (write-refused) in the same session.
6. Flip the CG-34 ledger row + its plan-doc twin in the landing commit
   (and CG-33's if batched); COG-5 un-PARKS its freeze-verification units
   and retires the §4(c) egg exclusion in its next wave.

Window not opened by the time COG-5 W5/W7 land: dependent
freeze-verification units PARK with dated markers (contract §7.5.4 build
sequencing); every other COG-5 wave proceeds — nothing else reads the
listing; the phase exits honestly with
`holdout_freeze: pending-captain-window` recorded.

## §9 · Scope boundary

This amendment covers ONLY the one-entry listing in
`framework/policies/immutable-core.yml`. NOT authorized or altered here:
the four enforcement-list wirings themselves (each a later Captain-windowed
edit that deletes its `pending:` flag — germline-lock.sh FILES/DIRS,
pre-tool-use.sh §5/§5b, base-safety.yml patterns); `holdout_gen.py` code
and the oracle CLI (non-germline COG-5 W5 build work); the §7.3 boundary
rows / AST pin / content-pin / egg-export lines (non-germline COG-5
W1/W5); the league-opening event (a post-phase amendment with its own
review); gate-apply arming (the Captain's own `sudo launchctl load`,
untouched); the CG-33 extension-gate pair (its own amendment — batchable
in the same window, never merged into this one);
`CABINET_AUTHORITY_ENFORCING` (Captain-gated, untouched); every other
germline path. COG-5 declares NO germline surface beyond this single
listing (contract header: "Germline surface = EXACTLY ONE Captain-windowed
amendment").
