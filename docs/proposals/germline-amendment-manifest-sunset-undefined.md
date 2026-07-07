# Germline amendment proposal — MANIFEST-SUNSET optional lifecycle field — undefined (authored 2026-07-07, CG-4)

**Status:** AWAITING CAPTAIN. The one germline file named below is
Captain-applied only; the Captain unlocked the schg boundary for this wave, so
the edit is staged on `feat/fidelity-harness-design` under that window. Reply
**"apply manifest-sunset"** to ratify keeping it at the next re-lock; a decline
executes the one-revert rollback (§3) before `germline-lock.sh lock`.

**Branch of record:** `feat/fidelity-harness-design` (live checkout
`/Users/nate/captains-cabinet`). The branch is the diff; this document is its
Captain-readable contract for the **germline** subset (1 file).

**Encodes (already-ruled — reference only, do NOT re-paste):**

- **APOPTOSIS / egg-compression program (2026-07-06/07, Captain-ruled)** —
  cabinet artifacts carry an explicit lifecycle bound so the apoptosis reaper
  can card removal-wave reviews instead of the estate growing forever.
  Wave-1α T4 already stamped date-typed `sunset: '2026-10-05'` frontmatter on
  the doctrine-pack SKILL copies (`packs/README.md`, `packs/doctrine-pack/`);
  this amendment lifts the same vocabulary to the extension-manifest layer so
  a whole extension (channel/source/skill/mcp) can declare its own sunset.

## §0 · What this changes, in one paragraph

`framework/schemas/extension-manifest.schema.json` gains ONE **optional**
top-level property, `sunset` (string, `minLength 1`): an ISO date
(e.g. `'2026-10-05'`) or a condition string (e.g. `'undefined +90d review'`),
documented in the schema as read by the **apoptosis reaper**, which cards the
extension for removal-wave review once the date passes / the condition holds.
`sunset` is NOT added to `required`, so every existing manifest stays valid
byte-for-byte; `additionalProperties: false` is untouched, so any OTHER
unknown key still fails closed exactly as before. The companion gate
`cabinet/scripts/validate-extension.sh` needs **zero edits**: both its
`jsonschema` fast path and its hand-rolled fallback interpreter read
`properties`/`required`/`additionalProperties` from the schema JSON at
runtime, so the new property flows through schema-driven (verified
empirically in §4 — including the fallback path with `jsonschema` shimmed
out, and the negative case that a non-string `sunset` is refused). No verdict
table, threshold, authority path, entrypoint containment rule, axis-linter
behavior, or control flow is touched.

## §1 · Per-file inventory (the branch is the diff)

| File (absolute) | Edit | Fail-closed proof |
|---|---|---|
| `/Users/nate/captains-cabinet/framework/schemas/extension-manifest.schema.json` | Added optional `properties.sunset` — `{"type": "string", "minLength": 1}` with a description naming the apoptosis reaper as its consumer. `required` unchanged; `additionalProperties: false` unchanged. | Absent `sunset` = valid (all 5 shipped `packs/*/manifest.yml` unchanged and green); unknown extra key still rejected on BOTH validator paths; non-string `sunset` rejected. |

`cabinet/scripts/validate-extension.sh` (also germline) is **not edited** by
this amendment — verified zero-change because its validation is entirely
schema-driven (§4).

## §2 · Correctness proof (additive-optional only)

1. The only delta is a new entry inside `properties`. JSON-Schema semantics:
   an optional property constrains a key ONLY when present; every previously
   valid manifest remains valid, and every previously invalid manifest
   remains invalid (nothing was removed from `required`, no enum widened,
   `additionalProperties: false` intact).
2. The hand-rolled interpreter in `validate-extension.sh` computes
   `extra = set(instance) - set(props)` and validates `props` sub-schemas
   generically — `sunset` joins `props`, so it is validated per its
   sub-schema and no longer counts as an unknown key; all other unknown keys
   still do. The `jsonschema` fast path is the reference implementation of
   the same semantics.
3. No consumer is required to change: loaders that ignore `sunset` keep
   working; the apoptosis reaper (its consumer) reads it opportunistically.

## §3 · One-revert rollback

**One-revert rollback:** a single checkout of the one named germline file
restores the pre-amendment bytes; the edit is a self-contained schema
property with no cross-file coupling, no state migration, and no consumer
that requires it:

```bash
git -C /Users/nate/captains-cabinet checkout HEAD~1 -- \
  framework/schemas/extension-manifest.schema.json
```

Every germline file in this amendment:
`framework/schemas/extension-manifest.schema.json`.
(`cabinet/scripts/validate-extension.sh` carries no edit — nothing to revert.)

## §4 · Verification evidence (run 2026-07-07)

```bash
# Gate A — a sunset-bearing manifest validates (doctrine-pack copy +
# `sunset: '2026-10-05'`), on BOTH validator paths:
bash cabinet/scripts/validate-extension.sh <ext-with-sunset>
# validate-extension: manifest OK (manifest.yml) … OK          [jsonschema]
PYTHONPATH=<shim-blocking-jsonschema> bash cabinet/scripts/validate-extension.sh <ext-with-sunset>
# validate-extension: manifest OK (manifest.yml) … OK          [hand_validate]

# Gate B — an invalid extra field is still rejected fail-closed, both paths:
#   jsonschema:    FAIL — Additional properties are not allowed ('frobnicate' …)
#   hand_validate: FAIL — manifest: unknown keys ['frobnicate']

# Negative type check — `sunset: 42` (non-string) is refused:
#   FAIL — manifest.sunset: expected string

# Amendment-doc lint stays green with this doc in the proposals union:
python3.12 -m pytest framework/tests/test_amendment_doc_lint.py -q
```

## §5 · Scope boundary

This amendment covers ONLY the optional `sunset` schema property. The
apoptosis reaper itself (its scan cadence, card format, and what it does at
sunset), any stamping of `sunset` into shipped `packs/*/manifest.yml`, and
the SKILL.md-frontmatter sunset convention from Wave-1α T4 are the property
of the apoptosis workstream and are NOT authorized or altered here. CG-2
(`run_action_lane.py` rewire) remains DEFERRED and untouched.
