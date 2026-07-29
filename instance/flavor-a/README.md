# instance/flavor-a — the built-in screenpipe personal-source adapter

This directory is a **pre-developed, opt-in adapter pack**: one concrete
implementation of the framework's launcher-neutral personal-sensing seam
(`framework.sources.base.PersonalSource` / `PersonalDispatch`), built on
[screenpipe](https://github.com/mediar-ai/screenpipe) + an Obsidian vault.
It is **not** part of framework CORE — framework never imports anything in
this tree statically (`framework/tests/test_no_screenpipe_in_core.py` is
the CI ratchet that keeps that true), and it is **default OFF**: a
deployment that never touches this directory runs the whole framework
against `NullPersonalSource` / `NullPersonalDispatch` with no crash, no
missing-import error, and no captain data of any kind.

## Contract: connect-by-config, fail-closed

`framework/sources/__init__.py` (`get_source()` / `get_dispatch()`) is the
**only** way framework CORE reaches this pack, and it does so entirely
through **data**, never a static import:

1. It reads `instance/config/sources.yml` for an `adapter:` (read) and/or
   `dispatch:` (write) key of the form `"<module>:<Class>"`.
2. If the file is absent, malformed, or the module/class fails to import —
   for ANY reason — it fails closed to `NullPersonalSource` /
   `NullPersonalDispatch`. Nothing crashes; every read returns its honest
   empty (`[]` / `{}` / `""`), tri-state probes return `None`.
3. Only if `sources.yml` names a module INSIDE this directory (or the
   framework-shipped `framework.sources.org:OrgSource`) does it get loaded,
   and only after `instance/flavor-a` is added to `sys.path` for that one
   import (defense-in-depth: a same-named module resolving from anywhere
   else on `sys.path` is refused, see `_load_bound`'s trusted-dir check).

**To opt in**, a deployment copies the two lines already documented at the
top of `instance/config/sources.yml`:

```yaml
adapter: flavor_a.screenpipe_source:ScreenpipeSource
dispatch: flavor_a.screenpipe_dispatch:ScreenpipeDispatch
```

Doing nothing (leaving `sources.yml` absent or omitting these keys) is the
supported, tested, default-off path — this is the same contract the
`null-hatch` CI job asserts (`.github/workflows/cabinet-ci.yml`, running
`cabinet/scripts/null-hatch.sh` stages 2-4; the separate `clean-room-source`
job it superseded was deleted 2026-07-29 as a strict subset), golden eval
`memory/golden-evals/eval-021-source-boundary.md`.

## What's in here

- `flavor_a/` — the adapter package: `screenpipe_source.py`
  (`ScreenpipeSource`, the READ side), `screenpipe_dispatch.py`
  (`ScreenpipeDispatch`, the WRITE/actuator side), `acting.py` (the
  draft-lane/briefing surface both bind into), `manifest.yml` (the
  extension-manifest contract read by `cabinet/scripts/validate-extension.sh`
  — already self-describing: `kind: source`, `axis_compat: {flavor:
  [personal]}`, `entrypoints: {source: screenpipe_source.py}`; left
  unchanged, it is correct as written).
- `autoreply/` — a screenpipe-specific autoreply add-on (Kristoffer UAT
  triage/compose flow).
- `rules/brain-bridge-screenpipe.md` — the Flavor-A-specific addendum to
  the framework-generic `.claude/rules/brain-bridge.md` outbound-gate rule.
- `evals/` — the adapter's own golden eval.

## Naming: why "flavor-a" stays, why the directory doesn't move

The seam itself is now genericized to "personal-source" (rule classes
`FRAMEWORK_IMPORTS_PERSONAL_SOURCE` / `FRAMEWORK_PATH_PERSONAL_SOURCE`,
this README) per the Captain's 2026-07-15 decision — but the Captain also
ruled the adapter itself is
**not rebuilt from scratch and keeps the screenpipe name inside it**. The
`flavor-a` / `flavor_a` naming (an existing "Flavor-A = personal estate,
Flavor-B = org/clean-room" axis convention, documented throughout
`docs/plans/source-adapter-boundary-2026-07-05.md`) is kept **in place**
rather than relocated or renamed to something like `adapters/screenpipe/`,
because the exact literal path string `"instance/flavor-a"` is load-bearing
in multiple places that would all need coordinated, high-risk changes for
no functional gain:
`framework/sources/__init__.py` (`sys.path` insertion + the trusted-dir
check), `framework/tests/test_personal_source_protocol.py` (the dynamic
conformance-test import), and the source-adapter-boundary spec + this
pack's own `manifest.yml`. Given the framework SEAM (not the adapter's
internal name) is what needed to read as adapter-agnostic, moving this
directory was judged higher risk than value — the cleanest fit, given the
existing structure, is documenting it clearly in place.

## NOT YET DONE — flagged for a Captain-scoped follow-up, not fixed here

`cabinet/scripts/egg-export-manifest.txt` still fully excludes this
directory from the public egg export (`delete instance/flavor-a`, rule
R127) — **this wave does not flip that rule**, and does not otherwise
change anything else under `instance/flavor-a/` besides adding this file.

Before that exclusion can responsibly flip (i.e. before this pack actually
ships as the opt-in built-in adapter, rather than just being documented as
one), the following files carry real personal-identity content — a first
name and a real home-directory vault path, in some cases woven into
realistic Danish/English message fixtures for functional test coverage —
that a dedicated scrub pass should review file-by-file (renaming a name
string is not always safe: some of these tests exercise name-detection
logic keyed to the literal captain-name value, so a careless global
replace can silently defang the assertion it's supposed to be checking):

| File | Personal-content mentions |
|---|---|
| `flavor_a/screenpipe_source.py` | 2 name, 8 path |
| `flavor_a/screenpipe_dispatch.py` | 2 name, 5 path |
| `flavor_a/acting.py` | 4 path |
| `flavor_a/__init__.py` | 1 name |
| `autoreply/wiring.py` | 1 path |
| `rules/brain-bridge-screenpipe.md` | 5 name, 3 path |
| `evals/eval-021-brain-retrieval-quality.md` | 1 name, 3 path |
| `flavor_a/tests/test_acting.py` | 11 name |
| `autoreply/tests/test_kristoffer_uat.py` | 12 name |
| `flavor_a/tests/test_screenpipe_dispatch.py` | 2 name, 1 path |
| `flavor_a/tests/test_adapter_internals.py` | 1 name |

Note: `nate_model` and `me_signal` are kept verbatim everywhere they occur
(external fidelity-contract artifact identifiers, not personal color) —
that instruction is unaffected by the table above, which is about the
prose/fixture content, not those identifiers.

`instance/config/sources.yml` (the live binding) already carries no
personal content and is left as-is, consistent with how every sibling
`instance/config/*.yml` (`platform.yml`, `posture.yml`, `directions.yml`,
…) is handled today: tracked in this private repo, excluded only at
egg-export time (R120-class rules) — not converted to a gitignored+
`.example` pair as a one-off for this file alone.

## Mac install + permissions (only if you opt in)

The shipped `cabinet/scripts/{setup-mac,install-mac-tools,grant-mac-
permissions}.sh` cover the framework-required tool stack (cua-driver,
chrome-devtools-mcp, Playwright, Stagehand) and are excluded from this
note — they run on every deployment. This adapter's own dependency,
`screenpipe` (the 24/7 screen+audio capture layer at
[screenpi.pe](https://screenpi.pe)), is confined here instead (R168,
2026-07-16 confirmed-gaps pass) so the shipped scripts stay silent about
a specific personal-productivity brand a fresh Captain has never chosen:

1. Install: `brew install screenpipe` (or download from
   [screenpi.pe](https://screenpi.pe) if you don't use Homebrew), then
   `brew services start screenpipe` and complete its own setup wizard.
2. Grant macOS TCC permissions to the `screenpipe` process (System
   Settings → Privacy & Security):
   - **Screen Recording** — screen/window capture.
   - **Accessibility** — window/app context.
   - **Microphone** — audio transcription.
   - **Input Monitoring** (optional) — keyboard/clipboard timeline.
3. Verify it's running: `pgrep -f screenpipe`.
4. Wire it in: add the two `adapter:`/`dispatch:` lines from the top of
   this file to `instance/config/sources.yml` (see "Contract" above).

Do this BEFORE or AFTER the framework-required Mac setup — the two are
independent; nothing in `setup-mac.sh`'s default (no `--with-sensors`)
path touches screenpipe at all.
