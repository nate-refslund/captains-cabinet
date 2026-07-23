# Germline amendment proposal — ORGAN packaging on the extension gate pair — 2026-07-23 (CG-33)

**Status:** AWAITING CAPTAIN — FILED AT COG-4 CONTRACT LANDING, NOTHING
APPLIED. Unlike the CG-4 sunset precedent (whose edit was already staged
under an open window), the two germline files named below are byte-unchanged
everywhere (master and live tree) at filing time: this document IS the
complete proposed edit text, filed at maximum lead time per COG-4 contract
§4.5 so the Captain can open the window at convenience. The actual edit is
the COG-4 W4 Captain-windowed MICRO-UNIT (schema + validator together, one
window, same-day relock); until the window opens, every dependent COG-4
organ-validation unit PARKS with a dated marker — schg is NEVER worked
around. Reply **"apply organ-packaging"** to authorize the window; a decline
leaves both files untouched (there is nothing to revert before apply).

**Branch of record:** none yet — the edit is NOT staged. W4+ COG-4 units
build AGAINST this document's proposed text (corpus + fixtures target it);
the windowed micro-unit applies it via the normal worktree → PR → per-job-CI
→ master flow INSIDE the window, then the live tree syncs checkout-from-
master with blob-verify (the CG-27/CG-31 ceremony precedent). Ledger row:
**CG-33** (`docs/plans/operative-egg-ledger-2026-07-07.yml`, captain-gated).

**Encodes (already-ruled — reference only, do NOT re-paste):**

- **COG-4 contract of record** (`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md`)
  §4.5 (route: proposal doc + CG row + NAMED handback, all filed at contract
  landing — MF-G1), §4.2 (the field set, verbatim source of §1a below), §4.3
  (validation mechanics + the named mutants), §16 (one-revert rollback rides
  a Captain window). Premise-check `wf_8625da64-a2a` READY-TO-PLAN + attack
  UPHOLD; four-lens panel + rev-1 + independent MF-verify LAND.
- **Foundry charter** `docs/cognitive-core-foundry.md` §4.5 L114 (organ
  contract fields), L116 (six forbidden powers + separate dispatcher), L118
  (launchd/floors law).
- **CG-4 precedent** `docs/proposals/germline-amendment-manifest-sunset-2026-07-07.md`
  — the SAME schema file amended under a Captain window with a one-revert
  rollback; this proposal mirrors its shape.
- **Provenance:** per the 2026-07-07 full-autonomy grant + the Captain
  2026-07-20 cognitive-masterplan grant (contract landing filed this doc);
  the germline window itself is Captain-only, non-grantable.

## §0 · What this changes, in one paragraph

The two schg-locked files of "the extension gate pair"
(`cabinet/scripts/germline-lock.sh` FILES[] :128-129, comment :120) are
extended so an **organ** — COG-4's packaged unit of periodic cognition — is
an ordinary extension: (a)
`framework/schemas/extension-manifest.schema.json` gains `"organ"` in the
`kind` enum, FOURTEEN new OPTIONAL top-level properties (the charter-§4.5
organ contract fields: `inputs`, `outputs`, `domain_operations` with the
namespaced-id pattern, `descriptor`, `permissions`, `idempotency`,
`state_ownership`, `cost_model`, `starvation_bound`, `freshness_needs`,
`trigger_policy`, `health_proof`, `fallback`, `dependencies`), and the
`undo_contract` pattern extended in place to the full AUTHORITY grammar
`^(none|delete_window\([0-9]+\)|journal:[A-Za-z0-9._:/-]+)$`; the schema
STAYS draft-07 and `additionalProperties: false` is untouched, so every
unknown key still fails closed and every existing manifest stays valid
byte-for-byte (no property leaves `required`; the undo pattern is a strict
superset). (b) `cabinet/scripts/validate-extension.sh`'s hand-rolled
interpreter gains exactly two features in lockstep with the schema features
now used — an `integer`/`minimum` branch and the ORGAN BLOCK
(required-when-`kind == organ` enforcement over thirteen of the fourteen
fields; `starvation_bound` stays optional-with-scheduler_policy-default per
contract SF2) — running on BOTH validator paths (jsonschema and fallback
converge through it). No verdict table, threshold, authority path,
entrypoint containment rule, or axis-linter behavior is touched; the
cross-manifest `state_ownership` disjointness check is deliberately NOT here
(suite-level by necessity — the per-file validator sees one manifest at a
time; contract §4.3 N-b).

## §1 · Per-file inventory — the COMPLETE proposed edit text

### §1a · `framework/schemas/extension-manifest.schema.json` (germline, schg)

**Edit 1 — `kind` enum gains `"organ"`** (replace the current enum line):

```json
"kind": {
  "type": "string",
  "enum": ["channel", "source", "skill", "mcp", "organ"]
},
```

**Edit 2 — `undo_contract` extended in place** (replace the whole property;
reconciles the schema grammar with the AUTHORITY grammar at
`framework/evolution/contracts.py` — one grammar, two spellings today is a
latent fork; a non-germline drift-tripwire test binds the two spellings in
the same W4 wave):

```json
"undo_contract": {
  "description": "none = no pseudo-undo exists, so this extension's action_types can never be act-first-eligible in ANY posture (inverse-required rule); delete_window(N) = artifacts deletable for N seconds after send; journal:<id> = a journaled inverse exists under the named journal id (the AUTHORITY undo grammar — framework/evolution/contracts.py; one grammar, two spellings, drift-tripwire-bound).",
  "type": "string",
  "pattern": "^(none|delete_window\\([0-9]+\\)|journal:[A-Za-z0-9._:/-]+)$"
},
```

**Edit 3 — fourteen new OPTIONAL properties** (insert into `properties`
after `sunset`; all optional at schema level — the required-when-organ rule
is the validator's organ block, §1b; `required` and
`additionalProperties: false` at the top level are UNCHANGED):

```json
"inputs": {
  "description": "ORGAN: declared input data surfaces the organ reads (path/stream tokens). Required when kind == organ (validate-extension.sh organ block).",
  "type": "array",
  "items": { "type": "string", "minLength": 1 }
},
"outputs": {
  "description": "ORGAN: declared output data surfaces the organ writes (path/stream tokens) — the per-organ freshness-probe artifacts. Required when kind == organ.",
  "type": "array",
  "items": { "type": "string", "minLength": 1 }
},
"domain_operations": {
  "description": "ORGAN: namespaced operation ids '<domain>/<operation>' — organ/domain-owned vocabulary that NEVER extends any central enum; the '/' separator is structurally required, so a flat ACTION_TYPES member can never appear here. Required when kind == organ.",
  "type": "array",
  "minItems": 1,
  "items": { "type": "string", "pattern": "^[a-z0-9_-]+/[a-z0-9._-]+$" }
},
"descriptor": {
  "description": "ORGAN: the ONE resolved constitutional effect/risk/undo descriptor (organ-level; per-operation overrides under 'operations', keyed by declared domain_operations ids — AX-checked). risk_class is the closed 13-member authority-matrix vocabulary (the same inline enum as risk_classes; the test_axes_contract.py drift-pin extends over EVERY occurrence in this schema). action_type is the declared ACTION_TYPES compatibility member and ceiling the declared HARD_CEILING_TOUCHES subset — both validated by the AX suite, which legally imports the constants (no new inline mirror is minted; action_types stays an OPEN string array). Required when kind == organ.",
  "type": "object",
  "additionalProperties": false,
  "required": ["action_type", "risk_class", "ceiling", "undo_contract"],
  "properties": {
    "action_type": { "type": "string", "minLength": 1 },
    "risk_class": {
      "type": "string",
      "enum": ["calendar_write", "credentials_grant", "deploy_nonprod", "deploy_prod", "draft_only", "external_comms", "internal_comms", "network_write", "pm_write", "read_only_dispatch", "reversible", "secrets", "spend"]
    },
    "ceiling": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 }
    },
    "undo_contract": {
      "type": "string",
      "pattern": "^(none|delete_window\\([0-9]+\\)|journal:[A-Za-z0-9._:/-]+)$"
    },
    "operations": {
      "description": "Per-operation descriptor overrides, keyed by a declared domain_operations id (membership AX-checked); each override carries any subset of the four members.",
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "action_type": { "type": "string", "minLength": 1 },
          "risk_class": {
            "type": "string",
            "enum": ["calendar_write", "credentials_grant", "deploy_nonprod", "deploy_prod", "draft_only", "external_comms", "internal_comms", "network_write", "pm_write", "read_only_dispatch", "reversible", "secrets", "spend"]
          },
          "ceiling": {
            "type": "array",
            "items": { "type": "string", "minLength": 1 }
          },
          "undo_contract": {
            "type": "string",
            "pattern": "^(none|delete_window\\([0-9]+\\)|journal:[A-Za-z0-9._:/-]+)$"
          }
        }
      }
    }
  }
},
"permissions": {
  "description": "ORGAN: declared capability needs (capability/MCP names). Required when kind == organ.",
  "type": "array",
  "items": { "type": "string", "minLength": 1 }
},
"idempotency": {
  "description": "ORGAN: idempotency-key discipline per operation — keys are declared domain_operations ids (membership AX-checked), values describe how that operation's idempotency key is derived. Required when kind == organ.",
  "type": "object",
  "minProperties": 1,
  "additionalProperties": { "type": "string", "minLength": 1 }
},
"state_ownership": {
  "description": "ORGAN: paths the organ owns transactionally — MUST be disjoint from every other organ's; the cross-manifest collision check is SUITE-level by necessity (the per-file validator sees one manifest at a time — COG-4 contract §4.3 N-b). Required when kind == organ.",
  "type": "array",
  "items": { "type": "string", "minLength": 1 }
},
"cost_model": {
  "description": "ORGAN: declared budget units per wake — a scheduler budget INPUT, not billing. Required when kind == organ.",
  "type": "object",
  "additionalProperties": false,
  "required": ["units_per_wake"],
  "properties": {
    "units_per_wake": { "type": "integer", "minimum": 0 }
  }
},
"starvation_bound": {
  "description": "ORGAN (OPTIONAL even for organs — the scheduler_policy default applies when absent; COG-4 contract SF2): the per-organ scheduling bound — max wakes and/or seconds an eligible high-urgency operation may wait. A wake-snapshot INPUT, never planner-invented. At least one member when present.",
  "type": "object",
  "additionalProperties": false,
  "minProperties": 1,
  "properties": {
    "max_wakes": { "type": "integer", "minimum": 1 },
    "max_seconds": { "type": "integer", "minimum": 1 }
  }
},
"freshness_needs": {
  "description": "ORGAN: THE watchdog floor-derivation input (COG-4 contract §9.2, MR3) — max_staleness_seconds plus the expected-output token the freshness probe checks per-organ (never only a shared runner log). Required when kind == organ.",
  "type": "object",
  "additionalProperties": false,
  "required": ["max_staleness_seconds", "expected_output"],
  "properties": {
    "max_staleness_seconds": { "type": "integer", "minimum": 1 },
    "expected_output": { "type": "string", "minLength": 1 }
  }
},
"trigger_policy": {
  "description": "ORGAN: when the organ's work is eligible — mode plus mode parameters. Required when kind == organ.",
  "type": "object",
  "additionalProperties": false,
  "required": ["mode"],
  "properties": {
    "mode": { "type": "string", "enum": ["periodic", "event", "on_demand"] },
    "parameters": { "type": "object" }
  }
},
"health_proof": {
  "description": "ORGAN: the health probe — a command/check token plus its expectation. Required when kind == organ.",
  "type": "object",
  "additionalProperties": false,
  "required": ["probe"],
  "properties": {
    "probe": { "type": "string", "minLength": 1 },
    "expectation": { "type": "string", "minLength": 1 }
  }
},
"fallback": {
  "description": "ORGAN: behavior on failure. Required when kind == organ.",
  "type": "string",
  "enum": ["skip", "safe_noop", "escalate"]
},
"dependencies": {
  "description": "ORGAN: declared dependencies — organ names and capability/MCP names (empty lists allowed). Required when kind == organ.",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "organs": { "type": "array", "items": { "type": "string", "minLength": 1 } },
    "capabilities": { "type": "array", "items": { "type": "string", "minLength": 1 } }
  }
}
```

**Dialect law (contract §4.5 N-e):** the schema's `$schema` line STAYS
`http://json-schema.org/draft-07/schema#` — every construct above is
draft-07; no `Draft202012Validator` ever runs against this file. The inline
risk_class enum is DUPLICATED (descriptor + per-op overrides) rather than
`$ref`'d because `$ref` is outside the hand-rolled interpreter's feature set
(the validator's own header law: "exactly the schema features used"); the
non-germline `test_axes_contract.py` drift-pin is extended in the same W4
wave to assert EVERY risk-class enum occurrence in this schema equals
`framework.authority.matrix.RISK_CLASSES`.

### §1b · `cabinet/scripts/validate-extension.sh` (germline, schg)

**Edit 1 — `hand_validate` gains an `integer` branch** (the schema now uses
`integer`+`minimum`; insert between the `array` branch's `return errs` and
the `if typ == "string":` line):

```python
    if typ == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            return ["%s: expected integer" % where]
        if "minimum" in sch and instance < sch["minimum"]:
            errs.append("%s: below minimum %s" % (where, sch["minimum"]))
        return errs
```

**Edit 2 — the ORGAN BLOCK** (insert immediately after the schema-validation
failure gate `if errors: fail("manifest invalid: ...")` and BEFORE the
entrypoint path-safety loop — both validator paths, jsonschema and
`hand_validate`, converge through this check):

```python
# --- ORGAN BLOCK (germline amendment 2026-07-23, CG-33) ---------------------
# Draft-07 as interpreted here cannot express "required when kind == organ";
# enforce the organ-conditional requireds fail-closed on BOTH validator
# paths. starvation_bound is deliberately ABSENT from this tuple: it stays
# OPTIONAL for organs (scheduler_policy default when absent — COG-4 SF2).
ORGAN_REQUIRED = (
    "inputs", "outputs", "domain_operations", "descriptor", "permissions",
    "idempotency", "state_ownership", "cost_model", "freshness_needs",
    "trigger_policy", "health_proof", "fallback", "dependencies",
)
if isinstance(manifest, dict) and manifest.get("kind") == "organ":
    missing = sorted(k for k in ORGAN_REQUIRED if k not in manifest)
    if missing:
        fail("organ manifest missing required organ keys %s" % missing)
```

**Edit 3 — header comment** (gate-1 paragraph gains one clause so the doc
tracks the code): after "the system python ships no jsonschema).", append a
line: `Organ manifests (kind: organ) additionally pass the ORGAN BLOCK —
thirteen required-when-organ contract fields, enforced on both paths (CG-33
germline amendment 2026-07-23).`

**Nothing else changes:** gate 2 (entrypoint realpath containment) and gate
3 (axis lint, empty allowlist) are byte-untouched; the script stays
read-only and never executes manifest content.

## §2 · Correctness proof (additive-optional + organ-gated)

1. **Every previously valid manifest stays valid byte-for-byte.** `kind`
   enum growth cannot invalidate existing values; the fourteen new
   properties are optional and nothing joined `required`; the `undo_contract`
   pattern is a strict superset (both old alternatives survive verbatim);
   `additionalProperties: false` is untouched so any OTHER unknown key still
   fails closed exactly as before. The three shipped channel manifests
   (`framework/channels/manifests/{outlook,slack,teams}.json`) validate
   unchanged (§4 gate C).
2. **Every previously invalid manifest stays invalid** EXCEPT the three
   deliberate widenings that ARE this amendment: `kind: organ` (was an enum
   violation), the fourteen new keys (were unknown-key violations), and
   `journal:<id>` undo contracts (were pattern violations).
3. **The organ block only ever REFUSES** — it adds a fail-closed requirement
   to a kind value that did not previously exist, so it cannot admit
   anything the old gate refused. Non-organ kinds never enter the block.
4. **The interpreter's `integer` branch** adds checks only for schemas using
   `integer` — the pre-amendment schema uses none, so pre-amendment behavior
   is byte-identical; post-amendment it enforces exactly what jsonschema's
   draft-07 path enforces for the same keywords (type + minimum; bool
   excluded from int per Python semantics, matching jsonschema).
5. **No consumer is required to change:** loaders that ignore the organ
   fields keep working; the COG-4 organ registry, watchdog
   `_parse_organ_manifests`, and scheduler snapshot are the (non-germline)
   consumers and read it opportunistically.

## §3 · One-revert rollback

**One-revert rollback:** a single checkout of the two named germline files
restores the pre-amendment bytes; the edit is self-contained (schema
properties + a validator block with no cross-file coupling, no state
migration, and no consumer that requires it). The restore is ITSELF a
germline edit and rides a Captain window (COG-4 contract §16 code inverse):

```bash
git -C /Users/nate/captains-cabinet checkout <pre-amendment-ref> -- \
  framework/schemas/extension-manifest.schema.json \
  cabinet/scripts/validate-extension.sh
```

Every germline file in this amendment:
`framework/schemas/extension-manifest.schema.json`,
`cabinet/scripts/validate-extension.sh`.
On rollback, every COG-4 organ-validation unit that depended on the
amendment PARKS again with a dated marker (the same fallback as a
never-opened window); nothing outside COG-4 reads the new fields.

## §4 · Verification battery (runs in-window; rehearsable pre-window against COPIES of the pair)

```bash
# Gate A — an organ fixture manifest carrying ALL fourteen fields validates,
# on BOTH validator paths:
bash cabinet/scripts/validate-extension.sh <organ-fixture>
# validate-extension: manifest OK (manifest.yml) … OK          [jsonschema]
PYTHONPATH=<shim-blocking-jsonschema> bash cabinet/scripts/validate-extension.sh <organ-fixture>
# validate-extension: manifest OK (manifest.yml) … OK          [hand_validate]

# Gate B — the named mutants each FAIL for the exact escape they name:
#   m1 organ manifest missing freshness_needs      -> FAIL (organ block)
#   m2 organ manifest missing descriptor           -> FAIL (organ block)
#   m3 domain_operations id without '/' (a flat ACTION_TYPES-style token,
#      e.g. 'send_email')                          -> FAIL (pattern — the
#      central-enum collision is structurally impossible)
#   m4 unknown extra key on any manifest           -> FAIL (additionalProperties,
#      unchanged behavior — regression control)
#   m5 undo_contract 'journal:' with empty id      -> FAIL (pattern)
#   m6 descriptor.risk_class outside the closed 13 -> FAIL (enum)
#   m7 non-integer max_staleness_seconds           -> FAIL on BOTH paths
#      (proves the interpreter's integer branch bites)
#   (kind: organ BEFORE the amendment fails the enum — the gate stays closed
#   until the window; asserted by the pre-window COG-4 corpus.)

# Gate C — the three shipped channel manifests remain valid unchanged:
for m in framework/channels/manifests/{outlook,slack,teams}.json; do ... OK

# Suite-level (NOT this validator — contract §4.3 N-b): two organs claiming
# the same state_ownership path RED in the AX-suite sweep over ALL organ
# manifests (W4 build work, non-germline).

# Amendment-doc lint stays green with this doc in the proposals union:
python3.12 -m pytest framework/tests/test_amendment_doc_lint.py -q
# AX suite green over the extended schema:
python3.12 -m pytest framework/channels/tests/test_manifests.py -q
```

## §5 · Captain window procedure (the CG-33 ceremony)

1. Fetch; re-verify lock state FRESH immediately before acting:
   `cabinet/scripts/germline-lock.sh status` + `ls -lO` on both files
   (boundary state changes across sessions — never assume).
2. Captain sudo: `sudo cabinet/scripts/germline-lock.sh unlock`.
3. Apply THIS document's §1 edit text to the two files — landed via the
   normal worktree → PR → per-job-CI → master flow inside the window; the
   live tree then syncs `git checkout origin/master --` on the pair with
   blob-verify vs origin/master (CG-27/CG-31 ceremony precedent).
4. Run the §4 battery: gates A/B/C green (mutants RED), AX suite green,
   amendment lint green.
5. SAME DAY: `sudo cabinet/scripts/germline-lock.sh lock`, then `status` +
   `verify` (write-refused) in the same session.
6. Flip the CG-33 ledger row + its plan-doc twin in the landing commit.

Window not opened by the time COG-4 W4 lands: dependent organ-validation
units PARK with dated markers (contract §4.5 build sequencing); the
scheduler/kernel/boundary waves proceed — they do not read the pair.

## §6 · Scope boundary

This amendment covers ONLY the two named germline files. NOT authorized or
altered here: the AX-suite/caller organ checks (the N-d
risk_class/ceiling-vs-matrix consistency check, the ACTION_TYPES/ceiling
membership assertions, the cross-manifest `state_ownership` sweep, the
contracts.py↔schema undo-grammar drift tripwire, the `test_axes_contract.py`
enum drift-pin extension) — all non-germline W4 build work; the organ
registry/scheduler/dispatcher code (the COG-4 contract's, not this
amendment's); any stamping of organ fields into shipped `packs/*/manifest.yml`;
`CABINET_AUTHORITY_ENFORCING` (Captain-gated, untouched); every other
germline path. COG-4 declares NO germline surface beyond this pair (contract
§4.5 "the phase's ONLY germline touches").
