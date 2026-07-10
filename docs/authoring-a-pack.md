# Authoring a capability pack

> **DRAFT — private-side prep (Perfect Cabinet, Wave C).** Not published
> anywhere yet; publication is Captain-gated (CG-7). Content is written for
> a third-party author, but every claim below was verified against this
> checkout only.

This is the end-to-end walkthrough for building an installable Cabinet
capability pack. The running example is a real pack in this repo,
**`packs/lighthouse-log-pack/`** — small, neutral, and authored expressly
so a stranger can copy its shape. Every field explanation below comes from
reading the actual validator (`cabinet/scripts/validate-extension.sh`) and
schema (`framework/schemas/extension-manifest.schema.json`), not from
intent docs.

A pack is ONE directory that satisfies TWO contracts at once:

1. **A Claude Code plugin** — `.claude-plugin/plugin.json` + `skills/`, so
   `/plugin install` works.
2. **A Cabinet extension** — `manifest.yml` at the pack root, so the
   governed gate passes:

   ```bash
   bash cabinet/scripts/validate-extension.sh packs/<your-pack>
   ```

Rail overview: `packs/README.md`. Install doc:
`cabinet/docs/cabinet-plugin-installation.md` § Capability packs.

## Anatomy (the exemplar's full tree)

```
packs/lighthouse-log-pack/
├── .claude-plugin/
│   └── plugin.json                      # Claude Code plugin manifest
├── manifest.yml                         # Cabinet extension manifest
├── README.md                            # install / uninstall / gate
└── skills/
    └── daily-lighthouse-log/
        └── SKILL.md                     # the one skill (frontmatter + body)
```

Four files. No code files are required — a skill pack can be pure
markdown, and the exemplar deliberately is.

## The extension manifest, field by field (what the validator REALLY checks)

`validate-extension.sh` runs three fail-closed gates — it stops at the
first failure, never writes anything, and never executes manifest content
(`yaml.safe_load` / `json` only). The script and the schema are
**germline-locked** (schg): consume them as-is. If your pack seems to need
a validator change, that is a CG ledger row + proposal under
`docs/proposals/`, never an edit.

### Gate 1 — MANIFEST (schema)

The manifest must be `manifest.yml`, `manifest.yaml`, or `manifest.json`
at the pack root (first found wins), a **regular real file** — a symlinked
manifest, or one whose realpath resolves outside the pack, is refused
outright (a dangling symlink is seen and refused, not skipped). YAML needs
PyYAML; the gate picks its own interpreter (`command -v python3.12 ||
command -v python3`), so on a machine with `python3.12` it just works —
on one without it, ship `manifest.json` instead (the gate's own failure
message says exactly this). It validates against `extension-manifest.schema.json` via
`jsonschema` when available, else a hand-rolled interpreter of exactly the
schema features used.

The schema sets `additionalProperties: false` — **any unknown top-level
key fails**. Fields:

| Field | Required | The actual check |
|---|---|---|
| `name` | yes | string matching `^[a-z0-9][a-z0-9._-]*$` (first char a lowercase letter or digit, then lowercase/digits/`._-`) |
| `version` | yes | any non-empty string — quote it (`"0.1.0"`) so YAML keeps it a string |
| `kind` | yes | enum: `channel` \| `source` \| `skill` \| `mcp` |
| `action_types` | yes | array of non-empty strings this extension EMITS; `[]` is valid and normal for pure skills/sources |
| `risk_classes` | yes | array from the closed 13-value enum (`calendar_write`, `credentials_grant`, `deploy_nonprod`, `deploy_prod`, `draft_only`, `external_comms`, `internal_comms`, `network_write`, `pm_write`, `read_only_dispatch`, `reversible`, `secrets`, `spend`) — drift-pinned to `framework.authority.matrix.RISK_CLASSES` by `test_axes_contract.py`. You DECLARE what your action_types map to; the authority matrix decides what happens to them |
| `undo_contract` | yes | string matching `^(none\|delete_window\([0-9]+\))$`. `none` means no pseudo-undo exists, so your action_types can **never be act-first-eligible in any posture** (the inverse-required rule) — declare `none` honestly rather than promising undo you don't implement |
| `axis_compat` | no | object with only `autonomy_level` / `flavor` / `deployment_target`, each a non-empty array from the closed axis vocabularies. **Absent = compatible with all** (the default). Consumed by loaders only — never read by the extension itself |
| `entrypoints` | yes | object mapping capability name → file path, at least one entry (gate 2 checks the paths) |
| `sunset` | no | ISO date (`'2026-10-05'`, quote it so YAML keeps a string) or condition string; the apoptosis reaper cards the pack for removal-wave review once it passes. Absent = never reaped. Originals like the exemplar carry none; parallel copies of core skills do |

### Gate 2 — PATHS (entrypoint containment)

For every `entrypoints` value:

- absolute paths are refused;
- the joined path must **realpath-resolve INSIDE the pack directory** —
  `../` traversal and symlink escapes are refused;
- the file must exist.

The exemplar's single entrypoint:

```yaml
entrypoints:
  skill_daily_lighthouse_log: skills/daily-lighthouse-log/SKILL.md
```

### Gate 3 — AXIS LINT (empty allowlist)

`framework/tests/test_axes_contract.py --scan <pack>` runs with the
**empty allowlist**: extensions RECEIVE resolved axis values from their
loader; they never read or branch on axis config. The linter AST-scans
every `*.py` under the pack (skipping `tests/` directories and
`__pycache__`) and flags any comparison or `match` that binds an axis
NAME (`posture`, `posture_name`, `autonomy_level`, `flavor`,
`deployment_target`, `level`, `postures` — including `x["posture"]` and
`x.get("posture")` forms) to an axis VALUE (`earn_up` / `guardian` /
`sovereign`, `personal` / `org`, `macbook` / `mac_mini` / `docker` — as
literals, constants like `SOVEREIGN`, or containers of those). Fail-closed
details that will bite you: an unparseable `.py` is a violation, not a
skip, and a symlink escaping the scanned tree is itself reported. A
markdown-only pack has nothing to scan — the gate still runs, and starts
mattering the moment you add any `.py`.

## Build steps (scratch → validated), exemplar as the running example

Step 1 — skeleton and the skill:

```bash
mkdir -p packs/lighthouse-log-pack/.claude-plugin \
         packs/lighthouse-log-pack/skills/daily-lighthouse-log
```

Write `skills/daily-lighthouse-log/SKILL.md`: YAML frontmatter with
`name` (match the directory) and `description` (what it does + when to
use it — this is the trigger text Claude Code matches on), then the body.
If your description contains `": "`, YAML-quote the whole string or
`claude plugin validate` will choke on the nested colon. Scope the body
tightly: the exemplar reads ONE org-event surface
(`shared/interfaces/world/chronicle-YYYY-MM-DD.jsonl`, read-only,
append-only — the skill never writes it) plus one narrow, explicit
carve-out (the `ref`-named undo-journal line, read-only, solely to
demo-check `undo.journaled` rows — see the skill's Sources and Rules
sections for the exact wording), and writes ONE surface the officer
already owns (`instance/memory/tier2/<role>/`). No network, no scripts,
no new tools. Any extra read your skill needs should be carved out that
explicitly — named surface, read-only, stated purpose — never a blanket
"read what you need".

Step 2 — `.claude-plugin/plugin.json` (the Claude Code half):

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
  "name": "lighthouse-log-pack",
  "displayName": "Cabinet Lighthouse Log Pack",
  "version": "0.1.0",
  "description": "One officer skill, daily-lighthouse-log: ...",
  "author": { "name": "Captain's Cabinet contributors" },
  "license": "BUSL-1.1",
  "keywords": ["ai-organization", "daily-log"],
  "skills": ["./skills/"]
}
```

`name` must match the pack directory and the extension manifest's `name`;
keep `version` in lockstep between the two manifests. Pick the license
that fits YOUR pack — `BUSL-1.1` is this repo's, not a requirement.

Step 3 — `manifest.yml` (the Cabinet half). The exemplar's, complete:

```yaml
name: lighthouse-log-pack
version: "0.1.0"
kind: skill
action_types: []
risk_classes: []
undo_contract: none
axis_compat:
  autonomy_level: [earn_up, guardian, sovereign]
  flavor: [personal, org]
  deployment_target: [macbook, mac_mini, docker]
entrypoints:
  skill_daily_lighthouse_log: skills/daily-lighthouse-log/SKILL.md
```

A pure skill bundle emits no action_types, so no risk classes and
`undo_contract: none`. (The explicit all-values `axis_compat` and omitting
it entirely are equivalent; the exemplar spells it out so you can see the
vocabulary.)

Step 4 — `README.md`: what the pack ships, install AND uninstall for both
paths (interactive + governed), and the extension-gate command. State
whether skills are originals or parallel copies of core skills — copies
carry a date-typed `sunset:` in their frontmatter for the apoptosis
reaper; originals don't.

Step 5 — validate (both halves):

```bash
bash cabinet/scripts/validate-extension.sh packs/lighthouse-log-pack
# validate-extension: manifest OK (manifest.yml)
# validate-extension: OK — packs/lighthouse-log-pack

claude plugin validate packs/lighthouse-log-pack
# ✔ Validation passed
```

## Install flow

- **Captain, interactive:** `/plugin marketplace add <owner>/<repo>`, then
  `/plugin install <pack>@captains-cabinet-marketplace`.
- **Officers / deployments (the governed path):** officers never run
  ad-hoc `/plugin`. Declare the pack in `instance/config/extensions.yml`
  and run `bash cabinet/scripts/install-extensions.sh` (idempotent;
  `setup-mac.sh` runs it as a setup step):

  ```yaml
  plugins:
    - name: lighthouse-log-pack
      marketplace: captains-cabinet-marketplace
      source: <owner>/<repo>
  ```

  Any declared entry with a LOCAL directory (a `dir:` key, or a plugin
  whose `source` is a local path) is routed through
  `validate-extension.sh` BEFORE install; a failing extension is skipped
  fail-closed and a need is filed.

## Distribution (marketplace entry)

Add one entry to `.claude-plugin/marketplace.json` → `plugins[]`:

```json
{
  "name": "lighthouse-log-pack",
  "source": {
    "source": "github",
    "repo": "<owner>/<repo>",
    "ref": "<branch>",
    "path": "packs/lighthouse-log-pack"
  },
  "description": "Daily keeper's log skill: ...",
  "category": "ai-organization",
  "tags": ["ai-organization", "daily-log", "memory", "exemplar"]
}
```

Convention (documented in the file's `_source_note` and the install doc):
**every `plugins[].source` in the manifest points at the SAME `repo` +
`ref` — the repository the marketplace file lives in.** When forking or
retargeting a deployment, update them ALL together. `path` is what varies
per pack.

## Honesty rules for pack authors

- **Label demo content, everywhere it appears.** Seeded rows are stamped
  `"demo": true` and carry a demo-labeled subject (the hatch receipt's
  subject ends in `(demo)`); `"canary": true` marks the guard's own probe
  traffic — both are synthetic. Anything your skill renders from them is
  labeled to match the marker (`(demo)` / `(canary)`) and never counted
  with real data. Mind your input
  surface: if it scrubs those markers away (the chronicle lifts
  identifier fields only — booleans and subjects never survive ingest),
  your skill must either follow the row's `ref` back to a source line
  that still carries them, or say plainly that it cannot tell. The
  exemplar skill encodes exactly this as a hard rule.
- **Never fabricate data.** Every number a skill reports comes from rows
  actually read; a missing source is reported as missing ("no chronicle
  for today"), not papered over with yesterday's file or an invented
  value. Honest zeros are stated as zeros.
- **Claim only what you measured.** README/description numbers (timings,
  counts, coverage) must be reproducible on the reader's machine or
  absent. No "installs in N minutes" unless you timed a cold install.
- **Declare the undo truth.** `undo_contract: none` when you implement no
  inverse — it honestly disqualifies your actions from act-first in every
  posture, which is the correct default for a new pack.

## The safety floor (packs may only narrow, never relax)

The Cabinet's layering doctrine — stated in the preset safety addenda
(`presets/_template/safety-addendum.md`: loaded on top of
`framework/safety-boundaries-base.md`, "ONLY ADD restrictions — never
relax the framework base") and enforced mechanically across the axes
system (the axes spec's narrow-only rules: narrowing is always safe and
needs no attestation; widening is Captain-gated) — applies to packs
verbatim:

- A pack may ADD restrictions, guidance, and capabilities that ride the
  existing gates. It may never instruct an officer to skip a gate, widen
  a posture, or write governance surfaces.
- The manifest **declares** what a pack emits; it grants nothing. Risk
  classes map into the authority matrix, which the pack cannot modify
  (it's germline).
- Gate 3 enforces the read side mechanically: an extension never reads or
  branches on axis config — it receives resolved values. The write side —
  a skill body that tells officers to relax something — is what review is
  for; expect any such pack to be refused.
- Skills should write inside surfaces the installing officer already owns
  (the exemplar: its own `instance/memory/tier2/<role>/` notes) and treat
  shared journals/ledgers as read-only unless the pack's declared
  action_types say otherwise.

## Pre-flight checklist

- [ ] `bash cabinet/scripts/validate-extension.sh packs/<pack>` → exit 0
- [ ] `claude plugin validate packs/<pack>` → passed
- [ ] `name` identical in dir, `plugin.json`, `manifest.yml`; versions in
      lockstep
- [ ] No network calls, no new dependencies, no secrets, no personal or
      employer values anywhere in the pack
- [ ] Demo content labeled; zeros honest; claims measured
- [ ] README documents install AND uninstall (both paths) + the gate
      command
- [ ] Marketplace entry added, `path` correct, repo+ref matching the
      file's other entries
