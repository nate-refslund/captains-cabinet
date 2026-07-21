# feat/relaunch-scrub2 — checkpoint cp1 review artifact (FW-019)

Batch: scrub-wave-2 public-egg publish-gate integration. Four independently
built + reviewed lane diffs, integrated in one clean clone off origin/master
`f0a16328` (post-#169), plus one integration-seam fix. Per 2026-07-07
full-autonomy grant.

## What this batch does (public-egg gate-d real-value drive)

1. **Lane 1 — amendments archive-out** (`egg-export.sh`,
   `egg-export-manifest.txt`, `test_egg_export.py`): reverses R167 —
   `docs/proposals/` now archives out of the egg ENTIRELY (only
   `ARCHIVED-NOTE.md` ships). The `germline-amendment-*.md` founding amendments
   are the launching deployment's dated ratified record (home paths, captain
   name, employer/product tokens); rewording a dated record falsifies it, so
   they archive as source-instance-private history (same class as R145 plans /
   R162 framework-docs) and stay with the private archive. Test renamed
   `test_proposals_non_amendments_archived_amendments_kept` →
   `test_proposals_all_archived` (amendments == []). Removes the biggest
   gate-d clusters (`/users/nate`, `nate`, refslund/stepnetwork/jfmedier in the
   amendment docs).

2. **Lane scan-infra — genericize the tracked scan/leak-audit fixtures**
   (`test_no_launcher_hardcode.py`, `test_testburg_fixture.py`,
   `test_preset_developer_parity.py`, `presets/developer/validate.sh`,
   `test_trust_ladder.py`): the tracked ratchet + leak-audit now name NO real
   person/org/product. The no-launcher ratchet hunts a SYNTHETIC demo identity
   (captain `Testburg`, lane `bakery`, domain `*.example`, adapter
   `examplesource`/`examplevault`); its self-tests plant those synthetic tokens
   to prove the scanner engine works. The real per-deployment literals move to
   the UNTRACKED, gitignored `instance/config/publish-scan-patterns.local` (the
   publish gate loads it; the fixture leak-audit + validate.sh load token VALUES
   from it, falling back to the shipped `.example` synthetic twin on a public
   cut). `_BOARD_ID` (`50\d{8}`) dropped — id runs are a generic numeric SHAPE
   covered captain-agnostically by the gate's tracked `id:[0-9]{9,}`.
   `test_trust_ladder.py`: `jobdanmark` → `catering` (synthetic lane).

3. **Lane world-retarget — retarget real product slugs to synthetic example
   lanes** (`manifest.json`, `course.test.ts`, `mcp-scope.yml`,
   `officer-capabilities.conf`, `test_world_port_calls.py`,
   `world-growth-backtest.py`): `polads`→`bakery`, `stephie`→`newsletter`,
   `stepnetwork`→`orchard`, `sensed`→`creamery` across the world/dashboard
   fixtures + the officer roster config, so the public product ships example
   lanes, not the launching captain's real products.

4. **Lane flip-tail — security + marketplace** (`cabinet/mcp-server/server.py`
   + `test_server.py`, `.mcp.json`, `test_mcp_plugin_root.py`, hooks,
   `framework/comms/mcp/server.py`): federation MCP HTTP transport is now
   FAIL-CLOSED (no peer secret ⇒ 401, never open-mode) and binds loopback
   `127.0.0.1` by default (`CABINET_MCP_HOST` opt-out); `.mcp.json` local-command
   servers resolve `${CLAUDE_PLUGIN_ROOT}` (not `${CLAUDE_PROJECT_DIR}` — the
   marketplace-install path bug) with a new regression test; the STEP-Network/
   Sensed private-repo detect tokens in the shipped hooks genericize to
   `example-org`/`example-product`.

## Integration-seam fix (the ONE cross-lane collision)

`world-retarget` and `scan-infra` both use the token `bakery` but for
INCOMPATIBLE roles: scan-infra makes the ratchet HUNT `\bbakery\b` in framework/
with EMPTY residuals, while world-retarget's diff put `bakery` INTO
`framework/acting/run_action_lane.py` (retargeting `polads`). That collision
would turn `test_framework_tree_has_no_launcher_hardcode` RED.

Resolution (integrator): scan-infra owns `test_no_launcher_hardcode.py`
(its full rewrite supersedes world-retarget's 4-line residual edit — dropped).
`framework/acting/run_action_lane.py`'s docstring product-example retargets to
`newsletter` (a sibling synthetic the ratchet does NOT hunt) instead of
`bakery` — keeping framework/ clean of BOTH the real token (`polads`, gate-d)
AND the ratchet's demo token (`bakery`, gate-c). Verified: ratchet 21/21 green;
`run_action_lane.py` carries no product/lane token.

## Verification (committed-tree battery results recorded in the PR body)

- Publish 4-gate verdict + gate-d residual: see PR body / integrator report.
- `pytest framework/` + `cabinet/scripts/tests`, census `--check`, layer-sep
  (new=0), docs-sweep (0), golden-evals, null-hatch: see report.

## Candor

The four lanes do NOT by themselves drive gate-d to 0 — real product/captain
tokens survive in files OUTSIDE the four lanes' scope (e.g.
`egg-export-manifest.txt` launchd expect-absent lines, `start-officer-mac.sh`
comments, several ship-in-egg test fixtures with `polads-ceo`/id-shaped runs,
`test_clean_room.py` nate refs). The exact residual is reported class-by-class
with proposed lane ownership for a residual pass. A non-green gate leads the
integrator report; this batch is the coherent first pass, not the finish line.
