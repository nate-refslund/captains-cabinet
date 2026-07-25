# feat/deproduct — cp1 checkpoint review

De-product the seed surface: the onboarding questionnaire, and the dead SQL
column. Reviewed against the staged diff at branch `feat/deproduct`, base
`origin/master` = `05871f128da8e2be9e94e50ff531f35f6f9bd719`.

## Premise check (findings were measured at 138a2532; master has moved 24 commits)

| Claim | Verdict on current master |
|---|---|
| `generate-instance.py` answers template asks every lane for repos / task_system / boards / neon_project / vercel_project, and asks nothing about customers, revenue, obligations or people | TRUE. Line drift only: 952–963, not 950–963. |
| `genesis.py:463` "(no product lanes declared yet)" and a brief "for the product lanes below" | TRUE at :463 and :469. |
| `genesis.py:466` "company/market/product research brief" | TRUE but at **:468**, not :466. |
| Three onboarding personas exist as EVALUATION fixtures, not questionnaire branches | TRUE — `framework/onboarding/fixtures/{software-product,client-services,community-nonprofit}`, consumed by `evaluate_personas.py`. |
| `045-org-runtime-slice.sql` has `product_slug NOT NULL` on 12 tables, in 3 PRIMARY KEYs and 6 FOREIGN KEYs, mirrored across ~175 lines of `org_runtime.py` | TRUE. 12 tables, PKs on `claude_native_tasks`/`org_roles`/`ovi_weeks`, 6 composite FKs, 175 matching lines in `org_runtime.py`. |
| `course.ts:176` states in code that the column carries only `captains-cabinet\|default` | TRUE, exactly at :176. |
| **Blast radius is "the SQL and org_runtime.py"** | **FALSE — understated.** The column is also named by `framework/events/emitter.py` (INSERT column list + kwarg), `bootstrap-roles.sh`, `claude-task-bridge.py`, `test-org-roles.sh`, the dashboard row type, and the honest-zero copy in `course.ts`/`morphology.yml`. A rename confined to two files would have left every one of those querying a column that no longer exists. Scope widened to the column's full reference set; module renames were NOT done, per the brief. |

## Dead-dimension verification (done before renaming, as instructed)

Not taken on the repo's word. Measured directly:

- Live store, read-only copy of `cabinet/cache/org-runtime.sqlite3` (245 MB):
  `org_events` = 225,559 rows over exactly two values —
  `captains-cabinet` (175,487) and `default` (50,072). `org_roles` (4),
  `role_lineage_events` (4), `claude_native_tasks` (14) hold one value each.
  The other eight lane-keyed tables are empty.
- Postgres: the schema is deployed **nowhere**. `information_schema.tables`
  queried against both candidate Neon projects returns `[]` for all twelve
  table names; the cabinet project (`sensed`) carries `cabinet_memory`,
  `officer_tasks`, `library_records` etc. but no org-runtime slice.

Conclusion: no product data exists in the column anywhere. Proceed.

## What changed

**1. Company-shaped questionnaire.**
`company: {does, serves, owes}` at top level and per lane; optional, validated
for type/length only. `render_context` now describes the lane by what it does,
who it serves and what it owes, and emits the estate recital **only when the
lane declared an estate** — the old code recited `Repo(s): (none declared).
Task board(s): (none declared).` for every lane, which for a repair firm is a
list of things it is failing to have. `SKILL.md` §2 asks the company questions
first and §2b opens the estate branch only for lanes that build or run
software. `--defaults` surfaces all three questions blank and the generated
description says "Not described yet" rather than reciting an empty inventory.

**2. `product_slug` → `lane_slug`.** SQL, SQLite mirror, and every consumer
that names the column. `Store.migrate_lane_key()` renames it in place on any
pre-existing database (catalog-only; PK/FK/index follow), guarded and
idempotent; 045 carries the equivalent guarded `DO $$` block plus drops of the
four legacy index names. `--product-slug` survives as an argparse alias and
`ORG_RUNTIME_PRODUCT` as an env fallback, so no caller breaks.

**3. Genesis brief wording.** No longer asks for a "company/market/product
research brief for the product lanes below"; asks about the business, carries
each lane's own does/serves/owes, and states outright not to assume software.

## Deliberate boundaries (each one a decision, not an omission)

- `framework/learning/capability_gaps.py` keeps `product_slug` — it is a
  payload dimension with its own env knob, not a column of 045. Six
  cross-module kwargs in `org_runtime.py` were caught mid-rename and restored;
  a blanket replace had silently converted them to `lane_slug=`, which would
  have been a `TypeError` on every `gaps` subcommand.
- `CABINET_PRODUCT_SLUG` / `ORG_RUNTIME_PRODUCT` / `DEFAULT_PRODUCT` env names
  are unchanged — renaming a live deployment's environment is a separate change.
- `bootstrap-roles.sh` writes `lane_slug:` into role ymls and reads
  `lane_slug` **then** `product_slug`, so ymls written before the rename still
  retire the right row.
- `genesis.py` is net-ZERO on non-comment lines (616 → 616). The census sits at
  `framework_production_noncomment_lines: 66934 <= 66934` with no headroom, so
  any growth would have required moving a budget. Composition was changed, not
  the threshold. Threading the `company:` block into the brief prompt is a
  natural follow-up that *would* need an allowance row; deliberately not spent
  here.

## Test-side edits (carry-along, not weakening)

`test_emitter.py` (16 lines), `test_purge_sqlite_mirror.py` (6),
`test_world_chronicle.py` (1), `test-org-roles.sh` (3), `course.test.ts` (1).
Every one names the column in SQL text, an INSERT column list, a kwarg, a
schema-parity set, or a fixture `CREATE TABLE` mirroring `org_events`. No
assertion was relaxed; only the identifier being asserted about was renamed.
`test_emitter.py::test_insert_columns_are_subset_of_045_schema` is in fact the
guard that would have caught a half-done rename, and it still is.

## Non-vacuity

All three new files run against a pristine clone of `05871f12`:

| File | Pre-change | Post-change |
|---|---|---|
| `test_company_shaped_seed.py` | 17 failed, 3 passed | 20 passed |
| `test_genesis_company_brief.py` | 6 failed, 2 passed | 8 passed |
| `test_lane_key_rename.py` | 12 failed, 3 passed | 15 passed |

The 8 pre-change passers are all explicitly-labelled back-compat or
regression guards (old answers files still generate; the secret gate still
fires; `--product-slug` and `ORG_RUNTIME_PRODUCT` still resolve; the brief
still leaks no chat id).

Two rounds of hardening were needed to get here, both against vacuity:

1. First draft imported `SHAPE_MAX_LEN`, `SHAPE_KEYS`, `ESTATE_KEYS` and
   `LANE_KEYED_TABLES` from the modules under test. Pre-change that produced
   **collection errors** — no assertion executed, which is weak evidence — and
   it made the arms agree with whatever the module happened to say. The
   contract is now stated in the test files.
2. The CLI/env arms failed pre-change on `AttributeError: no attribute
   'lane_arg'`. They now resolve the function by fallback, so pre-change they
   fail on real behaviour (`SystemExit: 2` for an unknown `--lane-slug`,
   `'legacy-env' == 'new-env'`) instead of on a missing symbol.

After both rounds, **zero** pre-change failures are missing-symbol errors;
every one is an assertion failure, a `SystemExit`, or `sqlite3.OperationalError:
no such column: lane_slug`.

## Migration proven against real data

A copy of the live 245 MB store was migrated end to end: 225,559 org_events
rows in, 225,559 out; lane distribution byte-identical
(`captains-cabinet` 175,487 / `default` 50,072); `org_events` gained
`lane_slug` and lost `product_slug`; re-opening reports nothing to migrate;
legacy index names replaced by their lane names. The live store itself was
never opened for writing.

## Verdict

APPROVE. Full serial sweep green against a re-measured baseline; the only red
is the known out-of-repo `test_retro_shim.py::test_reexports_constants`, which
is red on the untouched baseline too and is never collected in CI.
