# Checkpoint review — fix/hatch-roster-authz cp2 (FW-019)

Reviewer: Claude Opus 5 (1M), fresh clone of the branch @ `6d667ffa`, own
scratch dir. Closes the three findings that BLOCKED cp1. Each was reproduced
here before being fixed, and each fix is pinned by an arm proven to fail
against `6d667ffa` and pass after.

## A (HIGH) — the "paste-ready" germline rows were not paste-ready

Reproduced on the repo's own Acme fixture: captured the printed block verbatim,
appended it literally to the two files it names, re-ran the generator. Roster
unchanged, `PENDING AUTHORIZATION` still present, **exit 0, no diagnostic**.

Two format bugs, both measured:

* mcp-scope rows printed at 4-space while real agent keys sit at 2-space, so
  the paste nested the new key inside the previous agent's mapping —
  `agents['acme-store-ceo'] == {'mcps': ['neon'], 'acme-labs-ceo': {...}}`.
  The neighbour's scope is corrupted too.
* conf rows printed with 2 leading spaces while real rows start at column 0.
  The generator's own parser `.strip()`s, so it saw the officer; the parsers
  that ENFORCE do not. `grep -q "^acme-labs-ceo:deploys_code$"`
  (`cabinet/scripts/hooks/post-tool-use.sh:54`) and `grep -qxF`
  (`cabinet/scripts/hooks/pre-captain-dm.sh:75`): both **NO MATCH**. So once
  the Captain hand-fixed the nesting, the lane was hired with every capability
  gate silently off — the same silent lockout this change exists to prevent,
  invisible to the new lockstep gate because the gate reads through the lenient
  parser while enforcement reads through the strict ones.

Fixed in `cabinet/scripts/generate-instance.py`:

1. `germline_rows_for` — conf rows at column 0; mcp-scope keys at 2-space with
   their fields at 4. Section delimiters became `#` comments (`CONF_ROWS_HEADER`
   / `SCOPE_ROWS_HEADER`), which both target formats ignore, so pasting a
   section *including its header* is safe rather than corrupting.
2. `_conf_officer_column` now REFUSES a padded row (leading **or** trailing
   whitespace), naming file and line. The authorization VIEW can no longer be
   more permissive than the greps that enforce it; a mis-indented row is a loud
   failure instead of a silent lockout. Verified: the real
   `cabinet/officer-capabilities.conf` has 0 padded rows, so nothing existing
   trips it.
3. The CLI now says the indentation is load-bearing and the headers are safe to
   paste.

Root cause of the miss: one existing arm asserted substrings in stdout, another
applied rows **the test itself constructed in correct format** — nothing
connected printed to applied. The new
`TestPrintedGermlineRowsCloseTheErrand` reads the block out of **stdout**
(locating the two headers by the file paths they name, ending at the next
numbered Next-steps item — deliberately independent of the module's internals),
appends each half byte-for-byte, re-runs, and asserts: lane hired,
`PENDING AUTHORIZATION` gone, `grep -q "^<slug>-ceo:deploys_code$"` matches,
`grep -qxF` matches, `agents:` gained a **sibling** key, and the neighbour's
scope is still exactly `{'mcps': ['neon']}`.

## B (MEDIUM-HIGH) — the gitless prune deleted shipped content

`git ls-files --others --ignored --exclude-standard` in a fresh `git init`
lists every ignored path regardless of whether the source repo **force-tracks**
it. Measured on this repo: 131 force-tracked ignored files, including 3 tracked
`.tsx` under `cabinet/dashboard/src/app/(authenticated)/officers/` (product
source), 3 `memory/tier3/` `.gitkeep`s, `shared/interfaces/deployment-status.md`
(a manifest `expect-present` in the egg) and 124
`shared/interfaces/reviews/*.md`. All ship in `git archive HEAD`; the prune
deleted all of them. Parity before: `only in git-archive branch: 131`,
`only in gitless: 0`, **PARITY: BROKEN**.

(The brief said the prune set was "exactly those 3" — it is 127 prune entries
covering 131 files. The defect is real and larger than briefed.)

The tree cannot distinguish "shipped ignored" from "deployment-local ignored",
so the export ships the answer:

* `cabinet/scripts/egg-export.sh` writes
  `cabinet/scripts/shipped-ignored-paths.txt` from
  `git ls-files -c -i --exclude-standard` at HEAD, filtered to what survived the
  packaging pass (so it never names a path the egg does not have), after the
  manifest pass (so no rule can remove it).
* `cabinet/scripts/null-hatch.sh` honours it by ADDING those paths to the
  throwaway index via `hash-object -w` + `update-index --add --cacheinfo`. An
  indexed path is no longer "other", so `ls-files` skips it **and**
  `--directory` stops collapsing any directory containing one — which matters,
  because the prune entries were collapsed directories (`memory/tier3/`), not
  the files. Literal `--cacheinfo` paths, not `git add`: real paths here contain
  pathspec metacharacters (`[role]`). **Absent list ⇒ nothing seeded ⇒
  byte-identical to the previous behaviour**, so a git work tree is unaffected.
* `cabinet/scripts/hatch.sh` + the hatch runbook: the prescribed `--clean-room`
  scratch export (`git archive HEAD | tar -x`) is gitless too, so the
  prescription now emits the same list.

Parity after, measured on the real tree: `only in git-archive branch: []`,
`only in gitless: []`, **PARITY: OK**. Prune set fell from 127 entries to 11
genuine deployment-local ones.

The existing parity arm could not catch this because its fixture had no
force-added ignored file. `_fake_tree` now force-adds one (`git add -f`) and
ships a keep-list, which strengthens `test_both_staging_paths_agree` (it fails
at `6d667ffa`) and adds four arms including the fail-safe boundary: with the
keep-list removed the file IS pruned, proving the keep-list is what does the
work and that the absent-list case keeps nothing extra.

## C (MEDIUM) — a new destructive write path in load-preset

`list_hired_agents` returns empty both when nothing is hired and when
`cabinet/mcp-scope.yml` is missing or unparseable. Step 2's new un-hired branch
`rm -f`s `.claude/agents/<slug>.md` plus its marker. Step 1, in the identical
condition, logs ERROR and touches nothing. Probed: normal run leaves two agents;
delete the scope file and re-run leaves one, **rc 0, "Preset 'work' loaded
successfully"** — a read failure on the authorization file silently strips a
hired officer off the boot surface and reports success.

Fixed by mirroring step 1's own guard: missing file **or** empty hired list ⇒
ERROR + skip the loop entirely (nothing copied, nothing removed). Structured as
a single nested `if` because the file runs under `set -u`. A real revocation
(file readable, officer simply absent) still removes the stale derived copy —
pinned by a non-regression arm, so the fix distinguishes "not hired" from
"cannot tell" rather than collapsing both into "do nothing".

## Evidence

Every new arm proven in BOTH directions against `6d667ffa` with `__pycache__`
purged and `PYTHONDONTWRITEBYTECODE=1`, by copying only the test files onto the
unfixed head: **16 failed there, all pass here.** Failure reasons at head were
the real property, not import errors — "did not hire the lane", "does not match
post-tool-use.sh's line-anchored capability grep", "not a direct child of
`agents:`" (showing the exact measured nesting), `yaml.scanner.ScannerError`,
`DID NOT RAISE`, force-tracked file missing from staging, hired officer's file
gone.

Non-regression guards that pass in both directions are deliberate and labelled:
indented comments/blank lines still parse; a real un-hire still removes the
stale copy; an absent keep-list keeps nothing extra.

No existing test or threshold was weakened, relaxed or deleted.
