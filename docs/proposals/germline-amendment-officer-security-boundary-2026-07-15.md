# Germline amendment proposal — officer security boundary

**Status:** applied in lockstep to the immutable manifest, host lock list,
pre-tool enforcement, base policy, and Seatbelt boundary.

## Why

The officer launcher now establishes two authority boundaries before starting
Claude:

1. `cabinet/.env` is parsed as data through an explicit allowlist and Claude is
   launched under `env -i`, so dashboard/session/verdict signing credentials do
   not enter the officer process. The resulting credential-bearing command is
   carried by a mode-0700 one-shot launcher which unlinks itself before exec;
   credentials are never typed into persistent tmux pane history. Integration
   credentials are further intersected with that officer's immutable
   `mcp-scope.yml` entry; an unlisted officer or malformed scope refuses boot.
2. The Mac officer runs under a Seatbelt profile that denies reads of shared
   secret stores, common personal credential homes (`~/.claude`, `~/.codex`,
   SSH/cloud/CLI stores), recovery/backup material, and the private backup
   connection-service directory, and denies writes to the Captain-law triplet. Officer
   observations go through a fixed-policy, capability-authenticated broker that
   owns target selection, officer identity, heading validation, append-only I/O,
   and `[trust:officer]` provenance.

This is a direct-filesystem and Unix-IPC containment layer, not a complete
same-UID security principal. The profile explicitly closes the unsandboxed tmux
proxy escape by allowing only the exact per-officer broker socket (plus DNS and
the configured SSH agent). An officer with computer-control/Accessibility
authority may still be able to drive another GUI process that holds the
Captain's user privileges. When egress enforcement is enabled, the profile
also denies direct external TCP/UDP and leaves remote hostname selection to the
local allowlisting proxy; localhost services remain possible deputies. The durable commercial boundary remains a separate
OS identity/App Sandbox plus a Captain-authenticated service. High-autonomy
release must remain fail-closed until that path is proven or computer-control is
removed from the tested officer profile.

An MCP-scoped credential is still visible to its officer parent process. The
commercial high-autonomy design should move write-capable credentials behind
separate, narrowly authenticated brokers so an officer receives capability,
not a reusable bearer secret. The 72-hour observe-only gate therefore uses
finite source/egress policy and excludes computer-control rather than claiming
that this same-UID boundary is the final multi-tenant design.

The running Seatbelt profile prevents an officer from modifying these boundary
implementations. Host-wide immutable protection should nevertheless cover the
same sources, so a process outside the officer sandbox cannot prepare a weaker
next restart.

## Proposed immutable additions

- `cabinet/scripts/start-officer-mac.sh`
- `cabinet/scripts/start-officer.sh`
- `cabinet/scripts/gen-officer-mcp-config.py`
- `cabinet/scripts/append-interface.sh`
- `cabinet/scripts/captain-law-broker.py`
- `cabinet/scripts/lib/officer-env.py`
- `cabinet/scripts/lib/officer-env.sh`
- `cabinet/scripts/lib/officer-sandbox.sh`
- `cabinet/scripts/observe-only.sh`
- `cabinet/scripts/egress-guard.sh`
- `cabinet/scripts/egress-proxy.py`
- `cabinet/launchd/com.cabinet.egress-proxy.template.plist`
- `framework/comms/channel_adapter.py`
- `framework/comms/tools.py`
- `framework/comms/mcp/server.py`
- `framework/comms/adapters/telegram.py`
- `instance/config/egress.yml`

These paths are now enumerated in lockstep. The host deployment must apply and
verify the immutable flags in the Captain-owned unlock/relock window before the
dogfood clock begins.

## Verification required in the unlock window

- The immutable lock status reports every path above as locked.
- A running officer cannot mutate a boundary source directly, via a split path,
  through an interpreter, or by renaming an ancestor.
- Captain maintenance can still update the boundary only during the explicit
  unlock/relock ceremony.
- `cabinet/scripts/test-mac-dry-run.sh` and
  `cabinet/scripts/lib/tests/test_{officer_env,captain_law_boundary}.py` remain
  green after relock.
