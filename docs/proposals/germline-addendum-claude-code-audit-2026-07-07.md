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
a `--settings` overlay (`allowedMcpServers` mirror,
`enableAllProjectMcpServers: false`). Scope-parse failure boots the officer
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
