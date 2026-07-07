# Germline amendment — BRAIN-BRIDGE SPLIT — 2026-07-07 (wave CG-3)

**Status:** APPLIED under the Captain's CG-wave germline unlock (2026-07-07).
The schg boundary was unlocked by the Captain for this wave; this document is
the mandatory companion record for the one germline file edited. Re-lock at
wind-down: `sudo bash cabinet/scripts/germline-lock.sh lock` (then `status` +
`verify`).

**Encodes (already-ruled, reference only — do NOT re-paste):**

- **FOUNDATION-FIRST + EVOLUTION ENGINE GO (2026-07-05, Captain-ruled)** —
  the framework is the universal, launcher-agnostic artifact; anything
  captain-specific (name, vault paths, artifact ids) belongs in `instance/`
  or adapters, never in framework law. This amendment realizes that clause
  for the brain-bridge germline rule (egg plan rows R132 + R153, wave CG-3,
  `docs/plans/operative-egg-plan-2026-07-07.md`).

## §0 · What this changes, in one paragraph

`.claude/rules/brain-bridge.md` (germline, schg-listed in
`cabinet/scripts/germline-lock.sh` and `framework/policies/immutable-core.yml`)
is rewritten to carry ONLY the framework-generic outbound-gate invariant —
personal-source read-first (gather-then-decide), `queue_draft`-only egress
behind the Captain's approval gate, captain-model/voice informs-never-leaks
taint rule, `append_agent_inbox` as the single write path, and the
`log_reasoning`/`record_run` governance duty — with zero launcher literals
(no captain name, no screenpipe, no vault path). The screenpipe/Nate-specific
binding content moves to a NEW non-germline instance addendum,
`instance/flavor-a/rules/brain-bridge-screenpipe.md`, referenced from the
germline rule by a launcher-neutral pointer (the `instance/flavor-a/rules/`
addenda directory + the `brain-bridge-<adapter>.md` naming convention — the
exact filename would itself be a screenpipe literal and fail the §3 grep). `load-preset.sh` was read first and has NO
assembly hook for `.claude/rules/` (it assembles constitution +
safety-boundaries + agents only), so per the CG-3 instruction the
pointer-line pattern is used instead of inventing a new assembly mechanism.
Root `CLAUDE.md` (row R132) is **deferred**: it is dirty in this checkout
(owned by the parallel org-memory session), so only the brain-bridge half of
CG-3 is executed here.

## §1 · Per-file inventory

| file | change | germline |
|---|---|---|
| `.claude/rules/brain-bridge.md` | Rewritten framework-generic: same five invariant sections, launcher literals removed, pointer line to the instance addendum + `instance/config/sources.yml`/`framework.sources` binding language added. No tool name changed (`queue_draft`, `append_agent_inbox`, `log_reasoning`, `record_run` verbatim — framework code and tests reference them by these names). | yes |
| `instance/flavor-a/rules/brain-bridge-screenpipe.md` | NEW — carries the moved screenpipe binding content: vault path `~/Obsidian/screenpipe-brain/`, `nate_model`/voice artifact ids, Graph/Teams/Make/Telegram concretions, reasoning-review/architect loop names, adapter chain + mcp-scope note. Travels with the flavor-a pack per R153. | no |
| `docs/proposals/germline-amendment-brain-bridge-split-undefined.md` | NEW — this companion record. | no |

## §2 · What this amendment does NOT do

- **No invariant weakened.** `queue_draft` remains the ONLY outbound path;
  the approval gate, the taint rule, the single write path, and the
  governance duty are byte-equivalent in meaning and stated at the same
  MUST/NEVER strength. External recipients stay per-item Captain-approved in
  every posture (ACT-AND-DRAFT, 2026-07-04 — reference only).
- **No tool, hook, or enforcement change.** `pre-tool-use.sh` germline
  protection, `germline-lock.sh` path list, `immutable-core.yml`, and
  `base-safety.yml` are untouched — the file keeps its path, so every
  existing reference (`framework/channels/*`, `framework/authority/veto.py`,
  `cabinet/mcp-scope.yml`, officer-skills prompts) resolves unchanged.
- **No behavior change on this deployment.** The instance addendum restates
  the removed specifics; officers on this deployment read both files and
  operate under identical constraints.
- **CLAUDE.md untouched** (deferred to the parallel session's window — see
  §0).

## §3 · Proof gates (run before commit)

```bash
# 1. Zero launcher literals in the germline rule:
grep -nE '(\bNate\b|[Ss]creenpipe|[Oo]bsidian|/Users/|~/\.|screenpipe-brain)' \
  .claude/rules/brain-bridge.md   # exit 1 (no hits)

# 2. Amendment lint + clean-room boot smoke:
python3.12 -m pytest framework/tests/test_amendment_doc_lint.py \
  framework/tests/test_clean_room.py -q
```

**One-revert rollback:** revert the single commit. It restores
`.claude/rules/brain-bridge.md` verbatim and removes
`instance/flavor-a/rules/brain-bridge-screenpipe.md` and this document;
nothing else changed, no state file to unwind. Then re-lock:
`sudo bash cabinet/scripts/germline-lock.sh lock` and `verify`.

## §4 · Ledger note

On acceptance, egg ledger rows R153 (brain-bridge.md → extract-pack) and CG-3
(brain-bridge half) can be marked done; R132 (CLAUDE.md) stays captain-gated
pending the parallel session releasing the file.
