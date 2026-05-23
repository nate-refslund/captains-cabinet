---
name: grep-verify-folds
description: When you claim a fold/amendment/v1.1+/finding-absorption to a spec, doc, or code file, GREP the body for the specific content keywords before committing — verify claim matches execution, not just the header
status: draft
author: cos
date: 2026-05-23
validated_against: ["Spec 050 v1.2", "Spec 060 v1.1", "Spec 057 v1.1"]
usage_count: 0
---

# Skill: Grep-Verify Folds (fold-claim-vs-execute discipline)

> Per Captain pattern A1 (reversibility-gated autonomy) + Spec 050 v1.2 + Spec 060 v1.1 + Spec 057 v1.1 prior incidents.

## When to Use

**Trigger condition (any one):**
- You're about to commit a spec/doc/code change that claims "v1.1 absorbs X findings" / "fold-in Y" / "amendment Z" / "fix lands these AC" / similar claim-vs-execute risk
- You just appended a changelog entry + edited body sections in the same change
- A reviewer (peer, CTO, CRO, COO, or self-spawned review agent) gave you a numbered list of MUST-fold findings to absorb
- You're updating documentation that references a script/config and you've also edited the script/config

**Skip condition:** trivial single-line typo fixes; new-file additions with no prior changelog claim to verify against.

## Procedure

1. **Identify the claim surface.** After editing, list every distinct finding/claim from the changelog or summary:
   - `(1) X changed in Section A`
   - `(2) Y added to Function B`
   - `(3) Z removed from Step C`

2. **Build a grep list.** For each claim, write a `grep -c` command targeting a SPECIFIC keyword from the body content (NOT from the changelog header) that would prove the body change landed:
   - Bad keyword: `"v1.1"` (matches changelog AND nothing else)
   - Good keyword: `"reload-officer-mac.sh"` (the actual symbol referenced in the body fix)
   - Good keyword: `"launchctl bootout"` (the actual command added)

3. **Run all greps in one batch.** Use `&& echo "...:" && grep -c ...` pattern in a single Bash call for parallel discoverability:
   ```bash
   echo "Finding 1 body match:"; grep -c "specific-keyword-1" path/to/file.md
   echo "Finding 2 body match:"; grep -c "specific-keyword-2" path/to/file.md
   ```

4. **Threshold rule.** Each claim should return `>= 2` (one in changelog header + at least one in body). If a claim returns `1` only, that's the drift pattern — the body wasn't actually updated. Halt + fix before commit.

5. **Edge cases (real-world incidents):**
   - **Branch-switch read-cache invalidation:** if you Edit-failed after a branch switch ("File has not been read yet"), re-Read the file before Edit. The read-cache is per-branch.
   - **Gitignored target files:** if the file is gitignored (e.g. captain-patterns.md), grep still works on local working tree — but verify the change persists to source-of-truth (e.g. cabinet-bootstrap.sh + export-state.sh) or it regenerates blank.
   - **Cross-file folds:** if v1.1 amends export-state.sh + Spec 057 body, both need separate greps. Don't assume "I edited script" means "spec body reflects it."

6. **Only after all greps return expected counts → commit.** Include the grep results in commit message (helps the reviewer + future-you).

## Expected Outcome

Zero "fold-claim-vs-execute" drift incidents on commit. CTO/reviewer confirms "clean fold no drift" instead of catching missed body sections.

## Known Pitfalls

- **Trusting the changelog header.** v1.1 changelogs are easy to write; body sections are easy to forget. The changelog is a PROMISE, not a PROOF.
- **Grepping changelog keywords.** Searching for `"v1.1"` or `"CTO fold"` returns matches in the header — that's not evidence the body changed. Always grep for the substantive content keyword.
- **Single-grep complacency.** One match could be just the changelog. Need ≥2 OR explicit grep of body-only section (`sed -n '/Section X/,/Section Y/p' file | grep -c ...`).
- **Skipping after branch switch.** Working tree state for read-cache invalidates on `git checkout`. Re-read before Edit.
- **Skipping for "trivial" folds.** Spec 050 v1.2 was a single-clause amendment — and the body still didn't change.

## Validation Scenarios

- **Scenario 1:** Officer claims "v1.1 absorbs 3 CTO MUST-fold findings."
  - Pre-skill: officer commits, CTO catches that finding #2 body wasn't updated.
  - With skill: officer runs 3 greps before commit, finding #2 returns 1 (changelog only), officer halts + edits body, then commit lands clean.

- **Scenario 2:** Branch switch invalidates read cache.
  - Pre-skill: officer Edit fails silently, missed edits ship.
  - With skill: officer detects "File has not been read yet" error, re-Reads, retries Edit, greps post-edit, commits clean.

- **Scenario 3:** Cross-file fold (script + spec body).
  - Pre-skill: officer updates spec body but forgets to update referenced script.
  - With skill: skill prompts officer to grep BOTH artifacts (script for command, spec for reference); both >= 2 confirms fold matches.

## Origin

- Spec 050 v1.2 drift (2026-05-23): I claimed §5/§7/§9/§4 body updates but only edited changelog header. CTO caught.
- Spec 060 v1.1 drift (2026-05-23): I claimed body updates for 3 CTO MUST-fold findings but only edited changelog. Caught by my own post-commit grep, fixed in follow-up commit 43eb8af.
- Spec 057 v1.1 drift (2026-05-23): I claimed Checkpoint 0.6 body amendment but only edited changelog. Caught by my own pre-commit grep this time (grep returned 1 not 2+), fixed in commit e5b1076.

The Spec 057 incident is the first time the grep-verify discipline caught drift BEFORE shipping — that's the target state for this skill cabinet-wide.
