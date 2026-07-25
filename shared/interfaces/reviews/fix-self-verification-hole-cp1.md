# Checkpoint review — fix/self-verification-hole cp1

Base: master `05871f12`. Reviewer: fresh-context adversarial subagent (Opus 5, own
clone, no session priors), re-running every battery itself. Verdict on the first
pass: **changes-requested**, 11 findings. This artifact records what was accepted,
what was rejected, and what is deliberately left open.

## What the change closes

`org-runtime missions complete` marked work `verified` with `--actor` defaulting
to `"cos"` — the owner role. It never read `verifier_role`, never compared actor
to owner, never called `require_active_role`. Measured on master: self-verify
accepted (exit 0), actor `totally-fake-role-does-not-exist` written verbatim,
`--actor` omitted silently recorded as `cos`. The officer-facing twin
(`work-graph-complete.sh` → `_apply_status_from_events`) had no actor check at all.

Also: `WorkGraph.to_json/from_json` silently dropped six declared `WorkNode`
fields including `verifier_role` — the field naming who may verify.

## Strength claim (held to deliberately)

The actor is a caller-supplied string and every officer runs as the same OS user.
This is **separation of duties**, not authentication. It stops the **defaulted,
unattributed and accidental** cases. It does **not** stop an officer who types
another role's name. Reviewer finding 4 caught the original wording
("prevents self-dealing, not impersonation") as backwards — self-dealing here *is*
one typed word — and it was corrected in `--help`, both SKILL.md files, the shell
header, and every docstring.

## Findings accepted and fixed

| # | Sev | Finding | Fix |
|---|-----|---------|-----|
| 3 | HIGH | Legacy nodes (`verifier_role=''`, the column default) became **permanently un-completable** — no `set-verifier` subcommand exists and a recompile mints new ids, so the mission could never reach `remaining==0`. | Degrade to the owner-only rule: any active role except the owner may verify. Self-verification stays closed. |
| 4 | MED | Overclaim in `--help` and 5 other sites. | Reworded everywhere to "defaulted, unattributed and accidental cases, NOT a deliberate rename". |
| 5 | MED | `verification_is_independent` compared raw strings: `Engineering`, `ENGINEERING`, fullwidth `ｅngineering`, and a zero-width-space variant were all **credited**. | `normalize_role_name()` — NFKC + strip control/format chars + casefold, shared by the CLI gate and the overlay so both fold identically. |
| 6 | MED | Shell gate matched the literal `"system"`, so `"System"` / `"system "` passed; the overlay then credited `system` while the shell refused it. | Shell folds before comparing; overlay refuses the `UNATTRIBUTED_ACTOR` sentinel. |
| 7 | MED | `owner == verifier` guarded in both `org_runtime` compile paths but not in `framework.missions.compiler` — the path the live fleet compiles from. Unsatisfiable node, compiles clean, verifiable by nobody. | Moved onto `WorkNode.__post_init__`, covering compiler, `from_json` and direct construction. Fires only when both fields are non-empty, so legacy nodes still load. |
| 9 | LOW | Dangling `docs/plans/` reference in a comment. | Removed. |
| 10 | LOW | Usage synopsis missing `--actor`; "REQUIRED" was false (`OFFICER_NAME` also satisfies it). | Corrected. |

## Findings accepted and NOT fixed — handed back

**2 (HIGH) — the fix does not reach the metric.** `framework/ovi/compute.py:121`
computes `verification_pass_rate = |work_item_verified| / |work_item_completed|`
from raw replay with no independence check, and `framework/evidence_mirror.py:191`
mirrors every `work_item_verified` as an org signal. A refused verification is
still counted there, so **self-verification still pays in the number the org
optimises**. Closing it means deciding where independence is evaluated for a pure
event counter that has no graph context — a design call, not a quiet patch.
This is the most important residual.

**1 (HIGH) — `presets/{developer,portfolio,work}/measurement/scenarios/outcome_to_verified.py`
now fails 12/13** (`all_nodes_verified_after_overlay`), 13/13 on master. Root cause
verified directly: `task-002`'s inferred owner is `operations` and the scenario's
validator emits `actor="operations"` (`:107`) — a real self-verification. The
assertion therefore *requires crediting one*, which pins the defect, so it was
**not edited** per the standing rule. Proven fix on a scratch copy: point the
validator at a role that owns nothing (`compliance`) → **13/13, all original
assertions intact**. No workflow runs preset scenarios, so CI stays green while
the seeded artifact is broken.

**Two CI-blocking evals pin the defect** (`cabinet-ci.yml:275`):
`test-org-runtime.sh:110` and `test-org-roles.sh:127` both complete a `cos`-owned
node with `--actor cos`. Not edited. Proven fix on a scratch copy: define an
`auditor` role, add `--verifier-role auditor`, complete as `auditor` → eval passes
with every original assertion intact (11 events, lineage checks green).

**8 (LOW)** `from_json` does not type-coerce the five string fields and `float()`
raises on a hostile payload. Pre-existing shape, not worsened; left open.

**Known gap, documented in code:** a node with neither `assigned_role` nor
`verifier_role` has no basis for comparison, so any non-blank actor passes.
Homoglyph attacks (Cyrillic `е`) are not folded by NFKC.

## Findings I attacked and the reviewer confirmed correct

- The `if/elif` restructure preserves `work_item_completed/failed/started` exactly,
  including the refused-verified → failed path (traced with runs).
- The refusal-branch comment accurately describes status vs `verification_passed`:
  a refused verification is downgraded to a plain completion, which is exactly what
  a `work_item_completed` from the same owner would have produced. Nothing escalates.
- `changed` counter: only non-test caller (`compiler.py`) discards the return.
- Nothing in the diff reads as authentication or a security boundary.

## Defect the brief asked for that was REFUTED

Making a partial `depends_on` an error was implemented, then **reverted**. The
silent-ordering hazard is real (3 criteria, one with `depends_on` → the
un-annotated node gets no edge, `validate()` passes, `ready_tasks()` lets "sign"
run before "draft"). But it is structurally identical to a documented, load-bearing
idiom: `depends_on: []` beside un-annotated siblings is how "these run in parallel"
is expressed (`test_supervisor.py:71-93`), and `test_compiler.py:748` legitimately
omits the key on a true root. Both are correct usage. Separating them needs the
outcomes schema to require `depends_on`, which is an owner decision. Only the
unambiguous half was fixed: the inference fallback regenerated auto ids and raised
`Unknown node` for any criterion carrying an explicit `node_id`.

## Verification (serial, `python3.12`, `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`)

Baseline re-measured on a separate clone of `05871f12`.

| Battery | Baseline | Branch |
|---|---|---|
| `framework/` | 1 failed, 6488 passed, 26 skipped | 1 failed, 6503 passed, 26 skipped |
| `cabinet/scripts/lib` | 236 passed | 254 passed |
| `cabinet/scripts/tests` | 4543 passed, 28 skipped | 4543 passed, 28 skipped |
| golden evals | — | 29/29 PASS |
| census · layer-sep · import-gate · docs-sweep · ledger-parity | exit 0 | exit 0 |

The single red (`test_retro_shim.py::test_reexports_constants`, a pinned model-id
constant) is red on master too and is untouched by this diff.

Census note: `framework_production_noncomment_lines` sits at **exactly** 66934/66934.
A mutation test requires observed == budget so a +1 line trips it, so the change is
deliberately **net-zero** on framework production lines — achieved by compaction and
by moving shared predicates into `cabinet/scripts/lib/work_graph.py`, never by
touching the ceiling.

Non-vacuity, both directions, cache purged: 20 failed / 5 passed pre-change vs all
passed after. The 5 passing in both directions are the legitimate-path twins
(independent verifier succeeds; correct DAG orders), proving the refusals are not
blanket breakage.
