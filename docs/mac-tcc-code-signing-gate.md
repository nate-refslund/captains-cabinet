# Mac TCC Code-Signing Gate

Before a Mac mini Cabinet can be declared live, TCC permissions must survive a
reboot. This is a hard gate for GUI driving, Screenpipe, and long-running
LaunchAgents.

Run:

```bash
bash cabinet/scripts/mac-tcc-gate.sh
```

Pass criteria:

- `claude` and `cua-driver` exist on PATH.
- `codesign --verify --deep --strict` passes for the launch binaries or app
  bundles that macOS sees.
- Accessibility is granted to Claude Code, cua-driver, and the officer launcher.
- Screen Recording is granted to Screenpipe and cua-driver.
- Full Disk Access is granted to Claude Code and cua-driver.
- After reboot, the same permissions remain granted and an officer can still
  start from launchd.

If any permission prompt reappears after reboot, do not activate the Cabinet on
the Mac yet. Fix the signing/wrapper identity first.

This gate is separate from `mac-preflight.sh`: preflight checks install/runtime
readiness, while this gate checks the macOS permission persistence needed for a
live appliance.
