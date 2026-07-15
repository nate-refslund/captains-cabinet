# Comms MCP — Activation Ritual (Captain-applied)

**Status:** superseded/applied — the server is now registered in both shipped
base MCP configs and structurally narrowed by the officer config generator.
**What it activates:** the channel-agnostic, LLM-native **Comms MCP** (`cabinet-comms`) — every officer's one door to the Captain. Officers call `send_card` / `react` / `poll` / `pin` / `open_thread` / `stream_thinking` / `send_rich_card` / `read_feed` as MCP tools; each routes through `framework.attention.gate` (charter, dedup→standing card, quiet-hours, external-comms floor, Chair T2) and the bound `ChannelAdapter`, then the feed journals it. There is no path around the gate.

The framework code (C1–C4) is in the PR. Activation is **instance registration + a germline scope grant + an officer role grant + a reboot** — all Captain-applied, because scope is germline and registration is live-deployment state. Nothing here runs by itself.

---

## Why it's safe to stage in this order
- The germline scope grant (step 2) is **inert until the server is registered** (step 1): `gen-officer-mcp-config.py` filters the merged `.mcp.json` to the scope set — a grant for a server that isn't in the merged config simply isn't there to bind. So step 2 can even land first with zero effect.
- The server binds the **null adapter** on any box with no `channel:` configured (`instance/config/sources.yml`), so every tool degrades to a logged no-op. A clean-room / Flavor-B deployment inherits nothing.
- Every send is still hard-gated by `env.allow_sends()` — a non-`runtime` session physically cannot send, exactly as today.

---

## Step 1 — Register the server (historical; now shipped)
The registration now lives directly in `.mcp.json` and
`.mcp.json.mac-native`; no untracked extension step is required. The old
instance recipe below is retained only as historical context:

```yaml
mcps:
  - name: cabinet-comms
    command: /opt/homebrew/bin/python3.12
    args: [ /Users/nate/captains-cabinet/framework/comms/mcp/server.py ]
    env: { COMMS_MCP_TRANSPORT: stdio }
```

Then render it into `extra-mcps.json` (do NOT hand-edit that file):

```bash
bash cabinet/scripts/install-extensions.sh
```

This deep-merges `cabinet-comms` into every officer's `.mcp.json` at their next boot.

## Step 2 — Grant scope (germline — unlock window)
`cabinet/mcp-scope.yml` is germline. The carry-patch adds `cabinet-comms` to `universal:` (every hired officer). Apply it in an unlock window, then re-lock:

```bash
# in an unlock window:
git apply patches/activate-comms-scope.patch      # universal += cabinet-comms
# review, then re-lock per the germline relock ritual
```

(If you'd rather not give it to every officer at once, grant per-officer instead: add `cabinet-comms` to a specific officer's `mcps:` bracket-list.)

## Step 3 — Grant the role tool (instance overlay)
Each officer's role-def must list the server prefix in `tools:` to actually call it. Add `mcp__cabinet-comms` to the officer overlay (e.g. `instance/agents/cos.md` frontmatter `tools:`). Match the config key **literally** (hyphen, not underscore) to avoid the documented drift.

## Step 4 — Reboot the officers
Officers pick up the new merged `.mcp.json` at boot:

```bash
bash cabinet/scripts/start-officer-mac.sh <officer>   # or restart the fleet
```

Verify: the officer's session lists `mcp__cabinet-comms__send_card` et al., and a smoke `read_feed` returns `{status: ok}`.

---

## Verification checklist
- [x] Both shipped base MCP configs register `cabinet-comms`.
- [ ] `mcp-scope.yml` shows `cabinet-comms` in `universal:` (or the intended officer), and the file is re-locked.
- [ ] The officer role-def `tools:` includes `mcp__cabinet-comms`.
- [ ] After reboot, `gen-officer-mcp-config.py` did NOT filter it out (it's in the boot `.mcp.json`).
- [ ] A live `send_card` shows the standing card; a repeat edits it in place (no duplicate) — the original bug this foundation fixes.

## Rollback
Narrowing is always allowed and instant: remove the `extensions.yml` entry + re-run `install-extensions.sh` (the server disappears from every officer at next boot). The scope grant then goes inert again. No germline unlock needed to rollback registration.
