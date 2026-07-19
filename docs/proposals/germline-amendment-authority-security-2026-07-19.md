# Germline amendment — authority-security: land the two staged Wave-B constitutional fixes (#7 curl ceiling, #9 MCP-command RCE)

**Status:** APPLIED. Landed onto `origin/master` via a governed PR-gate (no
live-tree edit, no sudo). This is the corrective landing of the two schg-locked
fixes that `FRESH-HATCH-B` deliberately STAGED as apply-clean handback patches
(`designs/hook-patches/`, `HANDBACK-fresh-hatch-wb-schg-7-9.md`) rather than
apply.

**Provenance:** Captain-authorized 2026-07-19 — "go with your recommendation" =
fold both Wave-B security fixes into the framework so the imminent fresh
relaunch inherits them. Recorded under the 2026-07-07 full-autonomy grant. This
supersedes the handback's Captain-unlock/relock ceremony path: the relaunch is
a clean hatch from `master`, so landing on `master` is the correct delivery and
no live schg file is touched here.

**Ledger:** `docs/plans/operative-egg-ledger-2026-07-07.yml` ids
`FRESH-HATCH-B-SCHG-7` (curl ceiling) + `FRESH-HATCH-B-SCHG-9` (MCP-command
RCE); plan-doc pair `docs/plans/operative-egg-plan-2026-07-07.md` §52.

## Why a germline edit is legitimate here

Both target files are on the germline FILES list of
`cabinet/scripts/germline-lock.sh` and carry the macOS immutable flag (schg) on
a *locked live tree*:

- `framework/authority/classifier.py` (audit #7)
- `cabinet/scripts/gen-officer-mcp-config.py` (audit #9)

The germline etiquette routes any germline-content change through a
captain-gated (CG) ledger row plus this amendment doc under `docs/proposals/`.
This landing follows the established governed-germline-edit pattern (precedent:
`0a6e28f5 fix(authority): close T1 ceiling-leak misclassifications
(Captain-authorized germline edit)`; `52ef8d22 GERM-2 APPLIED`). A worktree off
`origin/master` is NOT schg-locked, so the edit applies cleanly on the branch;
the fresh relaunch's own hatch-from-master + `germline-lock.sh lock` re-applies
the immutable flag to the live copy later. No unlock window, no interactive
sudo, no touch of `/Users/nate/captains-cabinet`.

## The two fixes (unchanged from the reviewed+verified staged patches)

### #7 — curl mutations escape the `network_write` ceiling
`framework/authority/classifier.py` let two live-mutating curl calls fall
through to `local_edit` (auto-approvable under enforcing/sovereign posture):

- **(a) bundled short form** `-XDELETE` / equals long form `--request=DELETE`:
  the verb regex required whitespace after `-X`, so `-XDELETE` missed, fell to
  the body/GET default, and escaped the ceiling.
- **(b) scheme-less remote host** `curl -X POST api.vendor.com/charge -d …`:
  the remote check only matched `https?://` URLs, so a scheme-less mutating
  host read as "not remote" and the ceiling was skipped.

The fix (i) tolerates `-XVERB` and `--request=VERB`, and (ii) adds a
conservative `_curl_targets_remote()` that fails to the ceiling when a curl
mutation carries no localhost marker. It is only ever reached for a curl
command (method is `None` otherwise), so non-curl commands and genuine local
edits are untouched, and localhost curl mutations stay `local_edit`.

- Patch: `designs/hook-patches/fresh-hatch-wb-7-curl-ceiling-escapes.patch`
  (touches `classifier.py` + `framework/authority/tests/test_classifier.py`).
- Post-apply: `test_classifier.py` → **123 pass** (bundled/`--request=`/scheme-less
  mutations hit the ceiling; localhost mutations stay local; plain GET unchanged).

### #9 — cross-officer RCE via the MCP scope gate
`cabinet/scripts/gen-officer-mcp-config.py` scoped officers' MCP servers by
NAME only, never by the COMMAND the server boots. `start-officer-mac.sh`
jq-deep-merges the officer-WRITABLE `instance/config/extra-mcps.json` over the
committed base (later layer wins), so a scoped server's *command* in the merged
`--input` is attacker-controllable: a rogue overlay
`{"mcpServers":{"brain":{"command":"/tmp/x.sh"}}}` booted `/tmp/x.sh` as a
scoped "brain" server inside every officer scoped to it (cross-officer RCE —
`extra-mcps.json` is shared by all officers).

The fix: for a kept server the generator now ALWAYS emits the TRUSTED spec —
never the overlay's command/args/env/cwd. Trusted specs come from
`_load_trusted_specs()`: the committed base (`.mcp.json.mac-native` else
`.mcp.json`), the committed capability overlays `cabinet/mcp-overlays/*.mcp.json`,
and an OPTIONAL instance extension manifest `instance/config/trusted-mcps.json`
read ONLY when it is write-protected (schg, or a read-only mount /
non-user-writable perms); a present-but-writable manifest is IGNORED
fail-closed with a loud `[ERROR]`. Consequences: an overlay command override is
NEUTRALIZED (trusted command boots, injected one never does; no DoS of a
legitimate server); a scoped server that no trusted layer defines is REFUSED
(fail-closed). `extra-mcps.json` is deliberately never a trusted layer — that
is the whole point of #9.

- Patch: `designs/hook-patches/fresh-hatch-wb-9-mcp-command-validation.patch`
  (touches the script + `cabinet/scripts/tests/test_gen_officer_mcp_config.py`).
- Independently re-verified in Wave B: RCE closed on every vector
  (rogue-command / args-injection / env-injection / case-variant + the
  write-protected-manifest gate); captain-agnostic; **41/41 tests**.

## What this landing deliberately does NOT do

- **NO current-fleet sync ceremony.** The handback's Captain
  unlock→apply→relock window and the live-tree provisioning step are moot here:
  the current fleet is being REPLACED by the fresh relaunch, which hatches from
  `master`. Nothing is applied to `/Users/nate/captains-cabinet`.
- **NO `instance/config/trusted-mcps.json` companion manifest** and no
  brain/perplexity provisioning. On `master` a fresh captain has NO officer-only
  servers, so nothing is dropped — every committed server (incl. cabinet-comms)
  boots its trusted spec, and the fail-closed refusal only affects an overlay
  server no trusted layer defines. The brain/perplexity over-block was a
  CURRENT-fleet-only concern, deliberately not addressed in this framework land.
  The tracked `instance/config/trusted-mcps.json.example` template already
  shipped with `FRESH-HATCH-B`; the real gitignored manifest is instance
  payload a live deployment would provision, not a framework artifact.

## Germline-lockstep note (why the immutable-files gate stays green)

This changes germline CONTENT, not the germline FILES LIST — both files were
already on `germline-lock.sh`'s FILES set. `germline-lock.sh` is untouched, so
`framework/tests/test_germline_lockstep_consistency.py` holds green. The
relaunch's `germline-lock.sh lock` re-applies schg to the live copies of both
files after hatch.

## Verification (committed tree, `python3.12`)

Full landing battery run against the committed branch tree off `origin/master`;
the two directly-affected suites pin the fixes:

- `framework/authority/tests/test_classifier.py` → 123 pass (#7).
- `cabinet/scripts/tests/test_gen_officer_mcp_config.py` → 41 pass (#9).
- `framework/tests/test_germline_lockstep_consistency.py` → green (files list
  unchanged).
- `framework/` full, `framework/sources framework/tests`, full
  `cabinet/scripts/tests`, `cabinet/scripts/lib/tests`, `null-hatch.sh`, the
  golden-eval suite, and `check-layer-separation.sh` (new=0) — results recorded
  in the `FRESH-HATCH-B-SCHG-7`/`-9` ledger rows. The only pre-existing red is
  `test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`
  (bare-worktree evidence-runtime-not-provisioned condition, reproduced
  byte-identical on pristine `origin/master` and green on master CI — CI is the
  authority).

## Rollback

`git revert` the landing merge/commit — the two germline files revert to their
pre-#7/#9 form, the paired test additions back out, and the ledger/plan rows +
this doc back out. The staged patches under `designs/hook-patches/` are the
historical record and are NOT deleted by this landing. No live schg file was
edited, no service rows added, no DB schema change, nothing installed on the
fleet.
