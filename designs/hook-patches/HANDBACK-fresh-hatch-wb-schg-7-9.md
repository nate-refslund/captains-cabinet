# HANDBACK — two locked authority files need a Captain unlock window (fresh-hatch Wave B: #9, #7)

**What:** two security holes are fixed as staged patches because their target
files are constitutional (schg-locked) — they cannot be live-edited, only
changed inside a Captain unlock window. Both are ready to apply; land them
together in ONE window.

**Why locked:** `cabinet/scripts/gen-officer-mcp-config.py` and
`framework/authority/classifier.py` are on the germline FILES list (lines 49 +
65 of `cabinet/scripts/germline-lock.sh`) and carry the macOS immutable flag on
the live tree. Verified locked immediately before staging (`ls -lO` → `schg`).

## The two fixes

### #9 — cross-officer remote-code-execution via the MCP scope gate
`gen-officer-mcp-config.py` scoped officers' MCP servers by NAME only, never by
the COMMAND the server boots. `start-officer-mac.sh` deep-merges the
officer-writable `instance/config/extra-mcps.json` over the committed base, so a
rogue overlay `{"mcpServers":{"neon":{"command":"/tmp/x.sh"}}}` booted
`/tmp/x.sh` as a "neon" server inside a neon-scoped officer. The patch validates
every kept server's command+args against the TRUSTED COMMITTED baseline
(`.mcp.json.mac-native` else `.mcp.json` + `cabinet/mcp-overlays/*.mcp.json` —
never the officer-writable overlay) and emits the trusted spec (stripping any
injected env/args/cwd). Servers with a diverging command, or absent from every
committed layer, are REFUSED and boot WITHOUT them. Fail-closed, self-contained
in the one file (no caller change).

- Patch: `designs/hook-patches/fresh-hatch-wb-9-mcp-command-validation.patch`
  (touches the script + `cabinet/scripts/tests/test_gen_officer_mcp_config.py`)
- `git apply --check` vs the live locked path: **clean**
- Tests after apply: `test_gen_officer_mcp_config.py` → 32 pass (5 new
  command-validation cases + the existing scope-filter suite, kept green).

**Residual to confirm (candor):** a legitimate EXTENSION server declared only in
`extra-mcps.json` and granted scope via a germline `mcp-scope.yml` amendment
would be REFUSED (no committed definition). That is the correct posture — a
Captain-sanctioned server's boot command belongs in a committed/trusted manifest,
not the officer-writable overlay — but if you intend to allow extension servers
to self-define their command, add a second trusted extension-manifest path.
Getting a name into scope already requires a locked-file amendment, so the RCE is
closed either way.

### #7 — curl mutations escape the network_write ceiling
`framework/authority/classifier.py` let two live-mutating curl calls fall through
to `local_edit` (auto-eligible): (a) the bundled short form `-XDELETE` (the verb
regex required whitespace), and (b) a scheme-less host
`curl -X POST api.vendor.com/… -d …` (the remote check only matched `https?://`).
The patch (i) tolerates `-XVERB` and `--request=VERB`, and (ii) adds a
conservative curl-remote check that fails to the ceiling when a curl mutation has
no localhost marker. Only reached for curl, so non-curl commands are untouched.

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
4. Run the suites above (`python3.12 -m pytest …`) — expect all green.
5. Commit (Fable trailer) + push per the multi-writer push protocol.
6. **Re-lock the SAME day:** `sudo cabinet/scripts/germline-lock.sh lock <path>`
   and verify `ls -lO` shows `schg` again.

The patches were generated against `origin/master @3e9038b`; the two locked
files are byte-identical between that commit and the live tree HEAD, so the
apply-checks above already passed against the live locked paths.
