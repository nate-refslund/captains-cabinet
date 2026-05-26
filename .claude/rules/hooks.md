---
globs:
  - "cabinet/scripts/hooks/*.sh"
---

# Hook Development Rules

- Always read HOOK_INPUT from stdin: `HOOK_INPUT=$(cat)`
- Parse with jq: `TOOL_NAME=$(echo "$HOOK_INPUT" | jq -r '.tool_name // empty')`
- Use stderr for block messages (exit 2): `echo "BLOCKED: reason" >&2`
- Exit 0 = allow, exit 2 = block. No other exit codes.
- Emit events via: `python3 "$CABINET_ROOT/framework/events/emitter.py" <type> <actor> '<json>'`
- Keep hooks under 50 lines. Complex logic goes in framework Python modules.
- Test with `bash -n` before committing.
- Run golden evals after any hook change: `bash cabinet/scripts/run-golden-evals.sh`
- Never silently swallow errors — fail-open with stderr WARN, never fail-closed without explanation.
