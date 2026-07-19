# Checkpoint review — feat/fresh-hatch-wb cp2 (Wave-B #9 over-block fix)

**Batch:** the corrected staged `#9` MCP-command-validation patch + rewritten
handback + trusted-manifest surface hygiene. Closes the Wave-B **blocking**
finding (the first cut of #9 over-blocked legitimate core MCP servers) and the
**medium** finding (handback understated the blast radius).

## Files in this batch
- `designs/hook-patches/fresh-hatch-wb-9-mcp-command-validation.patch` —
  regenerated. Staged patch for the schg-locked
  `cabinet/scripts/gen-officer-mcp-config.py` (+ its unlocked test). NOT applied
  to the tree here; lands in the Captain unlock window.
- `designs/hook-patches/HANDBACK-fresh-hatch-wb-schg-7-9.md` — rewritten with a
  candid blast-radius note + the one-time provisioning step.
- `.gitignore` — ignore the real `instance/config/trusted-mcps.json` (instance
  payload, like `extra-mcps.json`).
- `instance/config/trusted-mcps.json.example` — tracked template twin.

## What the fix changes (in the patch)
The first cut refused any kept server whose overlay command != committed
baseline (exact string compare). That **gutted the live fleet**: cos dropped
7→4 booted servers, losing `cabinet-comms` (committed, refused only because the
deployment localizes `python3.12`→`/opt/homebrew/bin/python3.12` and
`${CABINET_SOURCE_REPO}`→abs path), `brain`, `perplexity`.

Revised `filter_config`: for a kept server, ALWAYS emit the TRUSTED spec
(committed base + committed overlays + a WRITE-PROTECTED
`instance/config/trusted-mcps.json`). An overlay override is **NEUTRALIZED**
(trusted boots, injected command/env/args never emitted) rather than refused —
same security, no DoS. A server with NO trusted definition is REFUSED
(fail-closed). The extension manifest is trusted only when `_is_write_protected`
(schg immutable OR non-user-writable); a writable manifest is skipped loud.

## Verification (both directions, mechanical)
Reproduced against the LIVE `instance/config/extra-mcps.json` with cos's real
scope (`cabinet/mcp-scope.yml`), patched vs unpatched generator:
- **No over-block:** patched + write-protected `trusted-mcps.json` boots the
  identical **7** servers as unpatched. No manifest → 5 (cabinet-comms restored;
  brain/perplexity fail-closed). Writable manifest → 5 + loud OFFICER-WRITABLE.
- **Hole closed:** rogue overrides in `extra-mcps.json` for cos's in-scope
  servers (`brain`/`notion`→`/tmp/x.sh`, `LD_PRELOAD`, `--exfil`): unpatched
  emits 6 rogue markers (RCE); patched emits **0** (all boot trusted specs).
- Unit suite: `test_gen_officer_mcp_config.py` **41 pass** (rogue-command /
  args-injection / env-injection / case-variant neutralize battery +
  cabinet-comms localization + write-protection gate). Full context (with the
  hook sibling + observe-only): **52 pass** via `python3.12`.
- `git apply --check` clean vs the live locked path; layer-sep `new=0`
  (pre and post apply); no product/captain tokens in the changed framework files.

## Residuals / not this batch
- `trusted-mcps.json` needs one-time provisioning + write-protection on the live
  tree (documented in the handback) for brain/perplexity; cabinet-comms needs
  none. Durable germline registration of the manifest is an optional follow-up.
- Two pre-existing harness reds (`test_actfirst_gate` acted-rows,
  evidence-seam replay) reproduce on origin/master @3e9038b and touch nothing
  here — separate owner.
- `#7` (curl ceiling) patch unchanged — Wave-B verdict: closed, no over-block.
