# Checkpoint review (FW-019) — feat/germline-authority-security cp1

**Branch:** `feat/germline-authority-security` off `origin/master @3c579e31`
**Batch:** land the two staged Wave-B germline security fixes (#7 curl ceiling,
#9 MCP-command RCE) + governance (amendment doc, ledger rows, plan rows).
**Provenance:** Captain-authorized 2026-07-19 ("go with your recommendation" =
fold both Wave-B security fixes into the framework), under the 2026-07-07
full-autonomy grant. Reviewer/integrator on Opus 4.8 per the Captain 2026-07-18
Fable-exhausted exception.

## Diff under review

Code (485 LOC churn, both germline files + their non-locked test files):

- `framework/authority/classifier.py` (+25/-9) — audit #7
- `framework/authority/tests/test_classifier.py` (+35) — #7 tests
- `cabinet/scripts/gen-officer-mcp-config.py` (+196/-…) — audit #9
- `cabinet/scripts/tests/test_gen_officer_mcp_config.py` (+229) — #9 tests

Governance (docs, not exercised by the test battery): this review artifact, the
amendment doc `docs/proposals/germline-amendment-authority-security-2026-07-19.md`,
two ledger rows + two plan-doc rows.

## Provenance integrity — the code IS the reviewed+verified staged patch

The two code fixes were already reviewed in Wave B, and #9 was independently
re-verified (RCE closed on every vector, captain-agnostic, 41/41). This landing
applies the SAME staged patches, unchanged. Verified byte-identity, not just
intent:

- `git apply --check` of both `designs/hook-patches/*.patch` against this
  worktree: clean.
- `git apply --reverse --check` of both patches against the APPLIED tree:
  clean — i.e. the working tree reverses exactly to the staged patch, proving
  the landed content equals the reviewed staged content with no drift.

So this checkpoint review confirms (a) the landed bytes equal the reviewed
staged patch, and (b) the fixes are correct and non-regressing on current
master. It is not a fresh from-scratch security re-derivation of Wave B.

## #7 — curl ceiling escapes (classifier.py)

- `_curl_method` regex widened from `(?:-X|--request)\s+([A-Za-z]+)` to
  `(?:-X\s*|--request[=\s]+)([A-Za-z]+)` — now catches bundled `-XDELETE` and
  `--request=PUT` while still catching the whitespace forms. Correct and
  minimal.
- New `_curl_targets_remote()` is conservative and fail-to-ceiling: explicit
  non-local scheme-full URL → remote; else a localhost marker → local; else
  (scheme-less host, no localhost) → remote. Only reached for a curl MUTATION
  (method in POST/PUT/DELETE/PATCH), so the "no-localhost ⇒ remote" default
  never touches non-curl commands — confirmed by the call site swap at the
  network_write ceiling (`_command_targets_remote` → `_curl_targets_remote`
  only inside the `method in (...)` branch).
- Over-block risk: localhost curl mutations must stay `local_edit`. Covered by
  `test_localhost_curl_mutations_stay_local_edit` (http://localhost,
  127.0.0.1:port, `-X DELETE http://127.0.0.1`). Plain GET stays a read
  (`test_plain_curl_get_unchanged_not_ceiling`). Verdict: closed, no over-block.

## #9 — cross-officer MCP-command RCE (gen-officer-mcp-config.py)

- Root cause: scope gate matched server NAME, boot COMMAND came from the
  jq-merged input where the officer-writable `extra-mcps.json` overrides the
  committed base. Fix emits the TRUSTED spec for every kept server; the overlay
  command/args/env/cwd are never emitted.
- Trust sources (`_load_trusted_specs`): committed base (`.mcp.json.mac-native`
  preferred), committed `cabinet/mcp-overlays/*.mcp.json`, and an OPTIONAL
  `instance/config/trusted-mcps.json` trusted ONLY when write-protected
  (`_is_write_protected`: schg via `st_flags & SF_IMMUTABLE`, or `!os.access(W_OK)`;
  fail-closed on stat error). `extra-mcps.json` is never a trusted layer.
- Behaviour: override → NEUTRALIZED (trusted boots, injected never does; no DoS
  of a legit server), unknown-to-trusted scoped server → REFUSED (fail-closed).
  `_cmd_equivalent` is used ONLY to decide loud-vs-silent logging (benign path
  localization stays silent), NEVER keep-vs-refuse — so a mis-equivalence can
  only add/suppress a log line, never boot an untrusted command. Sound.
- Captain-agnostic on master: no `instance/config/trusted-mcps.json` is shipped;
  a fresh captain has no officer-only servers, so committed servers (incl.
  cabinet-comms) all boot and nothing is dropped. The brain/perplexity
  over-block is a current-fleet-only concern deliberately NOT addressed here
  (no companion manifest added) — correct per the authorization.
- Tests: 41/41 across the RCE neutralize battery (rogue-command, args-injection,
  env-injection, case-variant, cabinet-comms localization silent-keep,
  write-protected-manifest gate, extra-mcps-never-trusted, mac-native
  precedence, fail-closed writable-manifest end-to-end).

## Germline-lockstep

Both files were ALREADY on `germline-lock.sh`'s FILES list; this changes
CONTENT, not the FILES list, and `germline-lock.sh` is untouched.
`framework/tests/test_germline_lockstep_consistency.py` → 371 passed (green).
The relaunch's own `germline-lock.sh lock` re-applies schg to the live copies.

## Verification at this checkpoint

- #7 suite 123 pass; #9 suite 41 pass.
- `framework/` 6042 passed / 31 skipped / 0 failed; `framework/sources
  framework/tests` 1106 passed; `cabinet/scripts/lib/tests` 236 passed;
  golden evals 28/28; `null-hatch.sh` PASS (1105/2s);
  `check-layer-separation.sh` new=0; germline-lockstep 371 passed.
- Only pre-existing red anywhere is
  `test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`
  (bare-worktree evidence-runtime condition; reproduced byte-identical on
  pristine `origin/master`; green on master CI — CI is the authority). Untouched
  by this diff (evidence-access.sh is not in scope).

## Verdict

APPROVE for PR-gate land. The landed content is byte-identical to the
reviewed+verified staged patches; the fixes close the two ceiling/RCE holes
without over-block; captain-agnostic; germline-lockstep holds; no live schg file
edited; the only red is a documented pre-existing bare-worktree condition that
master CI does not share.
