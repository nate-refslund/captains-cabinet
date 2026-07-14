# DRAFT — egg export + publish gate runbook (2026-07-10, PC-C)

> **PRIVATE-SIDE PREP.** This runbook, the exporter, its manifest, and the
> publish gate never ship in the egg. **Publishing anything remains CG-7
> Captain-gated — a GREEN gate does not lift CG-7.** No step below posts,
> pushes, or publishes.

## What the egg is

A **fresh tree cut from git HEAD** (`git archive`), shaped by a
row-cited exclusion/transform pass. It is **never this repo flipped public**:
the git history carries personal/employer data, so history never travels.

## How to run

```bash
# 1. cut the export (must be OUTSIDE the repo tree; --force clears a non-empty dir)
bash cabinet/scripts/egg-export.sh --out /tmp/egg-export

# 2. judge it (fail-closed; exit 0 = GREEN, 1 = RED)
bash cabinet/scripts/egg-publish-gate.sh --export /tmp/egg-export
```

The exporter writes `egg-manifest.json` (source commit, commit-clock date,
file count, applied rules) into the export root and refuses: an `--out`
inside the repo, an `--out` containing the repo, `/`, `$HOME`, symlinks, and
non-empty dirs without `--force`. The source checkout is read-only throughout.

## What ships / what leaves

Rules live in `cabinet/scripts/egg-export-manifest.txt` — one comment per
rule citing its `operative-egg-ledger` row. Summary:

| Ships | Leaves (row) |
|---|---|
| framework/, cabinet/, packs/, presets/, docs (non-plans), `.example` twins | live `instance/config/*` values (R120) |
| `cabinet/fixtures/testburg/` — the synthetic demo estate | `instance/flavor-a/` personal-source pack (R127) |
| `instance/config/{policies,posture-presets}/`, `contexts/_default.yml` **+ the Testburg lane-declaration twins `contexts/{bakery-site,newsletter}.yml.example`** (Wave G lane instance-split — the fresh-hatch model for the lane resolvers), `projects/_template.yml` (R122/R123/R124/R125) | `instance/agents/`, `instance/fidelity/`, live lane contexts/projects/officer-skills (R128/R124/R125) |
| `shared/interfaces` as **header contract + empty body** (R116; captain-vetoes.yml is the model) | captain rules/knowledge content (R116) |
| the 4 germline-pinned normative specs + `ARCHIVED-NOTE.md` stub | the rest of `docs/plans/` incl. the egg plan+ledger (R145) |
| `framework/docs` LIVING contract docs (`work-model.md`, `consequence-ledger.md`, `outcome-watchdog.md`) + `ARCHIVED-NOTE.md` stub (R162 `framework-docs-archive`) | the DATED `framework/docs/*-2026-*.md` design snapshots — instance history (live paths, lane names, the Captain by name); rewording dated records would falsify them |
| `act-first-surfaces.yml` **as the scrubbed `.example` bytes** (R126 — the germline lockstep suite requires the wired file on disk; live rulings leave) | the live ruled `act-first-surfaces.yml` (Captain rulings + board ids) |
| empty `bin/` mount (R059); CI retargeted to `[master]` (R159) | node_modules/.next (R088); gitignored LimeZu assets (structural — archive ships tracked files only) |
| launchd **`.template.plist` twins + `officer-entitlements.plist` + `INSTALL-flip.md` + `com.cabinet.gate-apply.plist` PORTABLE-DARK** (PC-E `launchd-portable-only`, R160 amendment: the germline-lockstep suite requires the wired gate-apply FILES entry on disk, so the export copy ships with envsubst-placeholder paths, DARK flags preserved, source untouched) | every other rendered static `com.cabinet.*.plist` — this deployment's artifacts (home paths + live roster); a fresh target renders from `services.yml` + templates |
| **`docs/templates/CLAUDE-egg.md` swapped in AS `CLAUDE.md`** (PC-E `claude-egg-swap` — captain-agnostic operating context; prints a loud UNSWAPPED note until the template is tracked at HEAD) | the live officer-loaded `CLAUDE.md` (deployment facts, absolute paths — live-coupling rule: excluded via transform, never scrub-edited) |
| — | the egg tooling itself (this runbook, exporter, manifest, gate — real-value doctrine) |
| — | `docs/launch/` drafts (CG-7 **per-item** publication material — Show HN draft, business-model proposal; integration ruling 2026-07-10, they never bulk-publish by riding the egg) |
| — | `WINDOW-RUNBOOK.md` — the live deployment's germline-window ceremony contract (Captain sudo steps, window shas, private integration-branch names); instance coordination material, same class as the R145 plans archive (PC-E fix pass, delete + expect-absent pair) |

R116 note: the ledger row claimed a packaging manifest existed; none did —
`egg-export-manifest.txt` is now that manifest.

## What the gate checks (in order, all run, fail-closed)

- **(a) gitleaks** over the export; binary missing = FAIL with install
  instructions, never skip-pass.
- **(b) null-hatch (Proof 1)** — the export's own `null-hatch.sh`, run against
  the export bytes staged into a scratch git sandbox (null-hatch archives
  HEAD; the export ships without `.git` by design).
- **(c)** `pytest framework/tests/test_no_launcher_hardcode.py -q` inside the
  export (bytecode/cache writes disabled — the artifact stays byte-clean).
- **(d) real-value + colleague grep suite** over the whole export (names,
  employer domains, personal paths, chat/board-id-shaped digit runs — **9+
  digits, unbounded**, mirroring the authoritative testburg guard; supergroup
  ids are 13-digit runs, so a cap would be fail-open). ANY hit = FAIL +
  grouped report; colleague-name hits are the per-person **consent items for
  the Captain** before any public cut. Sole exception: exact strings on the
  recorded **adjudicated allowlist** (ledger row CG-19, captain-gated — the
  Captain ratifies or strikes each entry at CG-7) are masked before a
  same-engine re-test; every masked occurrence still prints as an `[adj]`
  line and lands in the grouped report, and any **other** banned token on the
  same line still fails. Patterns are never relaxed.
- **(e) verdict** — `PUBLISH GATE: GREEN/RED` + the CG-7 reminder line.
  Reports (gitleaks JSON + the grouped real-value report) land in a durable
  mktemp dir whose path prints with the verdict; nothing is written into the
  export itself.

Gate-(d) status after the PC-E scrub-paths wave: the launchd plists and
CLAUDE.md classes are handled by the two transforms above, the shipped docs
(deploy runbooks, normative specs, INSTALL-flip) are reworded at source, and
WINDOW-RUNBOOK.md is excluded outright (instance ceremony; its private
branch names are not gate tokens, so exclusion — not the gate — is what
keeps them out). Remaining known RED sources until their owning rows land:
real-value surfaces outside this wave (marketplace metadata, code/test
fixtures), the unbounded digit-run guard's id-shaped test fixtures
(epoch-millis stream ids, placeholder chat/bot-token ids, the all-zero SHA
constant in the pre-push hook pair — adjudicated as CG-21, with the nil-UUID
config placeholders as CG-22), and the
LICENSE copyright surname (intended value — adjudication row proposed). The
grouped report is the Captain's scrub worklist; fixes belong in the source
rows (reword — e.g. underscored numeric literals, shorter fakes — or
adjudicate the exact string), never in gate thresholds.

## Honest numbers (claims discipline)

Clean-room hatch: **8s with deps present, first receipt 1–2s after** (wave-A
verified). The ratified stranger bar is **≤90 min on a bare Mac — not yet
timed**. Framework suite ≈ **4069 tests**. The honest demo claim is *"first
receipt in minutes once hatched"* — never a "5-minute install".

## Tests

`python3.12 -m pytest cabinet/scripts/tests/test_egg_export.py -q` — runs a
real export into a tmp dir and pins every row above + the safety refusals
(CI-collected via the existing `cabinet/scripts/tests` job; pure-local).
