# HANDBACK — two locked authority files need a Captain unlock window (fresh-hatch Wave B: #9, #7)

**What:** two security holes are fixed as staged patches because their target
files are constitutional (schg-locked) — they cannot be live-edited, only
changed inside a Captain unlock window. Both are ready to apply; land them
together in ONE window. **#9 ALSO needs a one-time provisioning step on the live
deployment (below) or it will boot officers WITHOUT their memory/research MCP
servers** — read the #9 blast-radius note before the window.

**Why locked:** `cabinet/scripts/gen-officer-mcp-config.py` and
`framework/authority/classifier.py` are on the germline FILES list (lines 49 +
65 of `cabinet/scripts/germline-lock.sh`) and carry the macOS immutable flag on
the live tree. Verified locked immediately before staging (`ls -lO` → `schg`).

## The two fixes

### #9 — cross-officer remote-code-execution via the MCP scope gate
`gen-officer-mcp-config.py` scoped officers' MCP servers by NAME only, never by
the COMMAND the server boots. `start-officer-mac.sh` deep-merges the
officer-writable `instance/config/extra-mcps.json` over the committed base, so a
rogue overlay `{"mcpServers":{"brain":{"command":"/tmp/x.sh"}}}` booted
`/tmp/x.sh` as a scoped "brain" server inside every officer scoped to it
(cross-officer RCE — extra-mcps.json is shared by all officers).

**The fix (revised — see the blast-radius note for what changed):** for a kept
server the generator now ALWAYS emits the TRUSTED spec — never the overlay's
command/args/env/cwd. Trusted specs come from `_load_trusted_specs()`:
- the committed base (`.mcp.json.mac-native` else `.mcp.json`),
- the committed capability overlays `cabinet/mcp-overlays/*.mcp.json`,
- an OPTIONAL instance extension manifest `instance/config/trusted-mcps.json`,
  read ONLY when it is WRITE-PROTECTED (schg immutable flag, or a read-only
  mount / non-user-writable perms). A present-but-officer-writable manifest is
  IGNORED fail-closed, with a loud `[ERROR]`.

Consequences:
- An overlay that OVERRIDES a trusted server's command is **NEUTRALIZED**: the
  trusted command boots, the injected one never does, and the injected
  env/args/cwd are stripped. This is strictly safer than the first cut's
  *refuse* (the rogue command cannot run either way) and, crucially, it does NOT
  let a rogue overlay DoS a legitimate server off an officer. A genuine (non
  path-localization) override is logged loudly; benign localization is silent.
- A scoped server that NO trusted layer defines is **REFUSED** (its only source
  is the officer-writable overlay — no safe spec to emit). Fail-closed.

`extra-mcps.json` is DELIBERATELY never a trusted layer — that is the whole
point of #9.

- Patch: `designs/hook-patches/fresh-hatch-wb-9-mcp-command-validation.patch`
  (touches the script + `cabinet/scripts/tests/test_gen_officer_mcp_config.py`)
- `git apply --check` vs the live locked path: **clean**
- Tests after apply: `test_gen_officer_mcp_config.py` → **41 pass** (RCE
  neutralize battery: rogue-command / args-injection / env-injection /
  case-variant + the cabinet-comms localization case + the write-protected
  manifest gate + the existing scope-filter suite).

#### BLAST-RADIUS NOTE (candor — this is what the Wave-B review caught)
The **first cut of this patch** refused any kept server whose overlay command
did not string-match the committed baseline. On the LIVE deployment that
**gutted the running fleet**: comms-officer (cos) dropped from **7 booted MCP
servers to 4** — it lost `cabinet-comms` (the universal comms bus — a COMMITTED
server, refused only because the deployment localizes `python3.12` →
`/opt/homebrew/bin/python3.12` and `${CABINET_SOURCE_REPO}` → an absolute path,
which the string compare rejected), plus `brain` and `perplexity` (memory /
research, declared only in `extra-mcps.json`). **Do not ship that behavior.**

The revised patch fixes both:
- `cabinet-comms` is committed → it is now kept and boots the trusted
  `${CABINET_SOURCE_REPO}` spec automatically; the localized overlay is
  recognised as path-equivalent and stays silent. **No provisioning needed.**
- `brain` / `perplexity` are instance-specific (local screenpipe bridges) and
  legitimately cannot live in a committed framework file (layer separation), so
  they need the write-protected instance manifest (provisioning step below).

Verified end-to-end against the LIVE `extra-mcps.json` with cos's real scope
(reproduction, both directions):
- **No over-block:** patched generator + a write-protected `trusted-mcps.json`
  boots the **identical 7 servers** as the unpatched generator
  (`brain, cabinet-comms, cua, cua-driver, notion, perplexity,
  redis-trigger-channel`). With NO manifest it boots 5 (cabinet-comms restored;
  brain/perplexity fail-closed refused). With a WRITABLE manifest it boots 5 +
  loud `OFFICER-WRITABLE` error.
- **Hole closed:** with rogue overrides written into `extra-mcps.json` for
  cos's in-scope servers (`brain`→`/tmp/x.sh`, `notion`→`/tmp/x.sh`+`LD_PRELOAD`,
  `perplexity`+`--exfil`), the **unpatched** generator emits all of them (RCE);
  the **patched** generator emits **zero** rogue markers — every server boots its
  trusted spec, and still boots all 7 (neutralize, not refuse).

#### PROVISIONING (one-time, in the SAME unlock window — REQUIRED for brain/perplexity)
On the live tree, snapshot the sanctioned extension servers into the trusted
manifest and write-protect it:

```
cp  instance/config/extra-mcps.json  instance/config/trusted-mcps.json
# review it — it should contain ONLY Captain-sanctioned servers (brain,
# perplexity, cabinet-comms); cabinet-comms is optional here (already committed).
sudo chflags schg instance/config/trusted-mcps.json     # write-protect = trust
ls -lO instance/config/trusted-mcps.json                # confirm `schg`
```

- `instance/config/trusted-mcps.json` is gitignored + egg-scrubbed (instance
  payload with instance-absolute paths — same class as `extra-mcps.json`). The
  tracked `instance/config/trusted-mcps.json.example` twin ships as the template.
- Until this file exists AND is write-protected, `brain`/`perplexity` are
  fail-closed REFUSED (loud `[ERROR]`); `cabinet-comms` and all committed
  servers boot regardless. A fresh hatch (no manifest) is a clean no-op.
- Re-lock note: it is NOT (yet) registered in `germline-lock.sh`, so a future
  fleet-wide `germline-lock.sh lock` will not re-apply schg to it. If a
  provisioning/extension change ever leaves it writable, the generator
  fail-closes (refuses those servers, loud) rather than trusting a writable
  file — degraded, never unsafe. Registering it in germline FILES for durable
  re-locking is a reasonable follow-up (own unlock window) but is NOT required
  for security.

### #7 — curl mutations escape the network_write ceiling
`framework/authority/classifier.py` let two live-mutating curl calls fall through
to `local_edit` (auto-eligible): (a) the bundled short form `-XDELETE` (the verb
regex required whitespace), and (b) a scheme-less host
`curl -X POST api.vendor.com/… -d …` (the remote check only matched `https?://`).
The patch (i) tolerates `-XVERB` and `--request=VERB`, and (ii) adds a
conservative curl-remote check that fails to the ceiling when a curl mutation has
no localhost marker. Only reached for curl, so non-curl commands are untouched.
(Wave-B review verdict: closed, no over-block — unchanged in this revision.)

- Patch: `designs/hook-patches/fresh-hatch-wb-7-curl-ceiling-escapes.patch`
  (touches `classifier.py` + `framework/authority/tests/test_classifier.py`)
- `git apply --check` vs the live locked path: **clean**
- Tests after apply: `test_classifier.py` → 123 pass; full `framework/authority`
  suite → 945 pass / 5 skip (no downstream regression).

## How to land (one unlock window, same day)

For each of the two files, from a clean worktree/clone at current origin/master:

1. Re-verify lock state: `cabinet/scripts/germline-lock.sh status`.
2. Unlock (Captain sudo): `sudo cabinet/scripts/germline-lock.sh unlock <path>`
   for `cabinet/scripts/gen-officer-mcp-config.py` and
   `framework/authority/classifier.py`.
3. Apply both patches: `git apply designs/hook-patches/fresh-hatch-wb-9-*.patch`
   and `git apply designs/hook-patches/fresh-hatch-wb-7-*.patch` (each also
   applies the paired test file, which is NOT locked).
4. **Provision the trusted extension manifest** (PROVISIONING step above) so
   brain/perplexity keep booting — skip this and those two servers fail-closed
   refuse (cabinet-comms and all committed servers still boot).
5. Run the suites above (`python3.12 -m pytest …`) — expect all green.
6. Commit (Fable trailer) + push per the multi-writer push protocol.
7. **Re-lock the SAME day:** `sudo cabinet/scripts/germline-lock.sh lock <path>`
   and verify `ls -lO` shows `schg` again on both files.

The patches were generated against `origin/master @3e9038b`; the two locked
files are byte-identical between that commit and the live tree HEAD, so the
apply-checks above already passed against the live locked paths.

## Not this diff (pre-existing, flag to a separate owner)
Two harness tests are red on `origin/master @3e9038b` independent of this work
and touch nothing here: `test_actfirst_gate.py::test_covered_evidence_refs_reads_acted_rows`
and the evidence-seam replay harness (`test_evidence_seam_bypass_replay.py`,
2 legit-read checks — evidence runtime/signing key not provisioned in a bare
worktree). Neither is a regression from #9 or #7.
