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
