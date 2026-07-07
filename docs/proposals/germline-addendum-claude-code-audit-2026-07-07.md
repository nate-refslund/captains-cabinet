# Germline addendum — Claude Code audit 2026-07-07

Collector for **germline-locked fixes** surfaced by the Claude Code audit
(`~/cabinet-claude-code-audit-2026-07-07.md`). The audit's structural
(non-germline) halves land directly on the branch; anything that requires
editing a schg-locked germline file is PROPOSED here instead, for the
Captain to apply in an unlock window (`sudo cabinet/scripts/germline-lock.sh
unlock` → edit → `lock`). Findings reference the audit doc's numbering.

Sections are appended by the task that hit the wall — keep entries dated and
self-contained.

---

## Finding #4 — MCP scoping (germline half)

The structural half shipped 2026-07-07 (this branch): officers now launch
with a per-officer `--mcp-config` generated FROM `cabinet/mcp-scope.yml` by
`cabinet/scripts/gen-officer-mcp-config.py`, plus `--strict-mcp-config` and
a `--settings` overlay (`enableAllProjectMcpServers: false` only — the
original `allowedMcpServers` mirror was REMOVED later the same day:
managed-settings-only key, unenforced from `--settings`, and CC 2.1.202's
schema validation of it blocked officer boot on the rolling restart).
Scope-parse failure boots the officer
with an EMPTY server set (fail closed). Two follow-ups need germline edits:

### 4a. `cabinet/mcp-scope.yml` — add the trigger-delivery plane to `universal:`

`redis-trigger-channel` is the trigger-delivery MCP every officer session
must boot (it injects `cabinet:triggers:<officer>` content; without it the
officer is deaf to wakes). It appears in no agent's `mcps:` list and not in
`universal:` — under structural scoping it would be filtered out of every
boot. Until amended, `start-officer-mac.sh` carries it as an explicit,
documented launcher infra pass-through (`--extra-allow`), which the
generator ignores whenever the scope parse fails (so it cannot mask a
fail-closed boot).

**Proposed edit** (unlock window):

```yaml
universal: [telegram, library, cabinet, redis-trigger-channel]
```

Once applied, drop `redis-trigger-channel` from the `EXTRA_ALLOW` line in
`cabinet/scripts/start-officer-mac.sh` in the same change (Docs-Must-Track-
Code: the pass-through comment there names this addendum).

### 4b. `cabinet/mcp-scope.yml` — scope the cua overlay for `drives_computer` officers

`cos` holds the `drives_computer` capability and the boot path deep-merges
the cua overlay (`cabinet/mcp-overlays/cua-driver.mcp.json`, server key
`cua-driver`; the mac-native base also defines `cua`) — but neither name is
in any agent's scope, so (a) the call-time hook §9 would block
`mcp__cua-driver__*` calls today, and (b) structural scoping strips the
server the capability gate just merged. The launcher pass-through adds
`cua,cua-driver` only when `drives_computer` is set. Proper fix: grant
`cua-driver` (and `cua` if the base server stays) in the scope entry of each
`drives_computer` officer, e.g.:

```yaml
  cos:
    mcps: [notion, library, telegram, brain, exa, brave-search, perplexity, claude-in-chrome, cua-driver]
```

Then remove the conditional `cua,cua-driver` pass-through from
`start-officer-mac.sh`.

### 4c. `cabinet/scripts/hooks/pre-tool-use.sh` §9 — flip the two fail-open paths

Germline (hooks dir is schg-locked). The audit's exact finding: §9
warns-and-allows when the officer identity is unset/unlisted, and the cache
builder swallows parser failures (`2>/dev/null || true` → stale/absent cache
→ allow). Both contradict the axes-contract "corrupt allowlist loads EMPTY"
doctrine. Proposed: unknown/unlisted officer → `exit 2`; cache-build failure
→ `exit 2` with a loud message naming this file. The structural plane
(above) already fails closed, so flipping the hook completes
defense-in-depth with matching semantics on both planes. Note
`gen-officer-mcp-config.py::parse_scope` deliberately mirrors the §9 cache
builder — if the §9 parser changes shape during this fix, update the
generator (and its parity tests in
`cabinet/scripts/tests/test_gen_officer_mcp_config.py`) in the same window.

---

## Finding #3b — descope the unregistered `cabinet` federation server (`cabinet/mcp-scope.yml`)

`cabinet` is universally granted (`universal:` list, mcp-scope.yml:136),
pre-tool-use.sh §10 implements its peer-trust policy, and CLAUDE.md "MCP
Scope" says "FW-005 done, federation ready" — but **no config layer
registers the server** (checked root `.mcp.json`, `.mcp.json.mac-native`,
`instance/config/extra-mcps.json`, `instance/agents/*/mcp.json`). Every tool
on it is unreachable; the grant is dead policy weight, same class as the
removed `host` grant
(`docs/proposals/germline-amendment-host-grant-removal-2026-07-07.md`).
Per the audit-task ruling the MCP-hygiene pass did NOT invent a server
registration — config layers were left `cabinet`-free.

**Proposed edit** (unlock window): remove `cabinet` from `universal:` until
the FW-005 server is actually wired into a config layer. **Interaction with
§4a above** — apply the two edits to the same line together:

```yaml
universal: [telegram, library, redis-trigger-channel]
```

(= §4a's snippet minus `cabinet`.) Companion doc edit in the same pass
(Docs-Must-Track-Code): CLAUDE.md "MCP Scope" → the "Cabinet — inter-Cabinet
comms … federation ready" bullet should say descoped-until-registered (or be
dropped).

## Finding #15 — `.claude/settings.json` allow-list: underscored trigger-channel entry (germline half)

`.claude/settings.json:20` allows `mcp__redis_trigger_channel`, which can
never match the server named `redis-trigger-channel`.
`.claude/settings.local.json` does not exist, so the allow-list lives ONLY
in germline settings.json → the rename lands here.

**Proposed edits** (same unlock window, same file):

1. `"mcp__redis_trigger_channel"` → `"mcp__redis-trigger-channel"` (line 20).
2. Drop the now-dangling `"mcp__linear"` allow entry (line 15) — the
   `linear` server was deleted from both `.mcp.json` variants on
   2026-07-07 (finding #17: granted to zero agents in mcp-scope.yml,
   `@mseep/*` community package, read-only-archive doctrine). CLAUDE.md
   "MCP Scope" + "Knowledge Systems" still name Linear as the read-only
   archive — trim in the same doc pass (archive access continues via the
   GraphQL API outside MCP).

Non-germline halves of #15 landed on this branch: all 8 agent-def sources
renamed (`instance/agents/cos.md`,
`presets/portfolio/agents/{cos.md,_lane-ceo.md.template}`,
`presets/work/agents/{cos,cto,cpo,cro,coo}.md`);
`cabinet/scripts/generate-instance.py` verified clean (no tools-line
literals). Generated `.claude/agents/*.md` are gitignored and refresh from
these sources via load-preset.sh at next officer start.

---

## AUD-2 (audit #6/#33 fallback half) — loud-fallback Notification page

`--fallback-model 'claude-opus-4-8'` now rides every officer launch line
(start-officer-mac.sh, probed like `--agent`, override
`CABINET_FALLBACK_MODEL`, `none` disables). The remaining AUD-2 gate half —
"simulated model-unavailable engages fallback AND pages via Notification hook
(no silent fallback)" — needs a hook wired in germline `settings.json`
(schg-locked), so it lands here, not on the branch.

**Proposed edit** (next unlock window): add a `Notification` hook entry that
greps the notification message for the CLI's model-fallback engagement text
and, on match, stamps `cabinet:model-fallback:<officer>` in Redis + sends a
Captain page via the existing notify path — the standing Fable/model rule
requires non-primary-model operation to be LOUD. Pair with the AUD-9 batch
(StopFailure/TeammateIdle/PermissionRequest) so one unlock window covers all
four hook wirings.

---

## AUD-12 (audit #32) — post-tool-use.sh safety-net comment is now stale

Consumer-side ACK shipped 2026-07-07: `redis-trigger-channel` no longer XACKs
on notification emit (and no longer XTRIMs); triggers stay pending until the
officer's `trigger_ack` or the hook's XAUTOCLAIM safety net reclaims them.
`cabinet/scripts/hooks/post-tool-use.sh` is schg germline, and its safety-net
comment (~line 335) still scopes the reclaim to "the channel pushed then
crashed, or the channel was down".

**Proposed edit** (next unlock window, comment-only, no behavior change):
extend that sentence — the safety net now ALSO re-surfaces channel-delivered
triggers the officer has not ACKed within the grace window, and its ids_file
write is the normal path by which channel-delivered triggers receive their
consumer-side ACK. Mechanics documented at length in
`cabinet/scripts/lib/triggers.sh` (trigger_read_safety_net header).

---

## AUD-8 — sandbox `filesystem.denyWrite` on the comms-officer settings overlay (probed 2026-07-07; exact config, flip deferred to a watched pilot restart)

Not germline-gated (the overlay is generated per boot by
`cabinet/scripts/gen-officer-mcp-config.py` into
`~/Library/Caches/cabinet/officer-settings-<officer>.json`, and that
generator is not schg-locked) — recorded HERE because the audit-collector is
this wave's single findings surface, and because the flip is deliberately
NOT applied tonight.

### Probe evidence (scratch sessions, CC 2.1.202, 2026-07-07)

All three probes ran headless (`claude -p --settings <file>
--setting-sources project --dangerously-skip-permissions`) from a scratch
cwd, no officer touched:

1. **Overlay accepts the key.** `sandbox.enabled` +
   `sandbox.filesystem.denyWrite` in a `--settings` overlay produced no
   schema-validation rejection and no boot block (unlike the
   managed-settings-only `allowedMcpServers` mirror, which 2.1.202 rejected
   with a boot-blocking modal on the 2026-07-07 rolling restart).
2. **denyWrite ENFORCES under `--dangerously-skip-permissions`.** A bash
   write to a denied path failed with exit 1, `operation not permitted`, no
   file created — exactly the structural backstop audit #27 wants for the
   acknowledged glob-bypass in pre-tool-use.sh:988 (and it stacks under
   schg, which already blocks the germline set at the FS layer).
3. **Network egress is UNAFFECTED when no `network` block is configured.**
   `curl https://api.github.com` → HTTP 200 from inside the sandboxed
   session — so a filesystem-only pilot cannot break comms-officer's
   Make/Graph flows by accident.

### Why the live flip is deferred (not-trivially-safe ruling)

The single failure precedent for overlay content (`allowedMcpServers`)
manifested **only at interactive TUI boot**, as a modal dialog that blocked
the officer — headless acceptance did not predict it. Tonight's constraint
is a live fleet with no officer restarts, so the interactive-boot leg
cannot be verified; a wrong call bricks comms-officer silently at its next
launchd keepalive relaunch. Enabling therefore requires the watched pilot
below, not a dark generator edit.

### Exact config (the pilot flip)

Add to the comms-officer settings overlay (via an officer-conditional in
`gen-officer-mcp-config.py`, or a static deep-merge layer in
`start-officer-mac.sh` — implementer's choice; keep the overlay's existing
`enableAllProjectMcpServers: false`):

```json
{
  "enableAllProjectMcpServers": false,
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyWrite": [
        "<CABINET_ROOT>/cabinet/scripts/hooks",
        "<CABINET_ROOT>/framework/policies",
        "<CABINET_ROOT>/memory/golden-evals",
        "<CABINET_ROOT>/instance/config/policies",
        "<CABINET_ROOT>/instance/config/posture-presets",
        "<CABINET_ROOT>/.claude/settings.json",
        "<CABINET_ROOT>/.claude/rules",
        "<CABINET_ROOT>/cabinet/mcp-scope.yml",
        "<CABINET_ROOT>/cabinet/officer-capabilities.conf",
        "<CABINET_ROOT>/cabinet/scripts/germline-lock.sh",
        "<CABINET_ROOT>/cabinet/scripts/kill-switch.sh",
        "<CABINET_ROOT>/cabinet/scripts/policy-shadow.py"
      ]
    }
  }
}
```

(Dir entries mirror `germline-lock.sh` `DIRS=(...)`; file entries are the
enforcer triad + judged-config heads of its `FILES=(...)` list — extend
toward the full list at pilot time; keep in lockstep with germline-lock.sh
per its own header rule. Deliberately NO `network` block in the pilot —
probe 3 shows filesystem-only leaves egress alone; `network.allowedDomains`
+ `sandbox.credentials` scrub are the SECOND pilot step per AUD-8's
gate_cmd, after the filesystem leg proves boot-stable.)

### Pilot procedure (one officer, eyes on the pane)

1. Apply the overlay change for comms-officer only.
2. `launchctl kickstart -k gui/$(id -u)/com.cabinet.officer.comms-officer`
   during a watched window; `tmux attach -t officer-comms-officer` and
   confirm clean boot (no modal, MCP servers up, first tick green).
3. Verify: a germline write attempt from inside the session is denied by
   the sandbox (not just schg/hook); a normal `cabinet/cache/` write
   succeeds; a Make proxy call succeeds.
4. Any failure → remove the overlay block + kickstart again (rollback is
   one generator revert; the overlay regenerates every boot).
