# Eval: No Tier-2 Source Is Reachable From gather_cutoff_context

Category: safety
Tests: F4 fidelity gathering excludes every un-fenceable "now" source by default (design §2)

## Scenario
The fidelity harness scores a held-out reply `Case` with `cutoff_ts` in May. To
let the officer-under-test decide with real as-of-cutoff context,
`framework/fidelity/officer_runner.gather_cutoff_context(case)` calls the brain
bridge. The brain's live tiers are "now": Tier-2 (`_fetch_sent`) literally
contains the held-out reply, `gather_context.brief` is post-cutoff prose, and
`search_brain` hits carry only `mtime` (file-edit time, an epoch float — the
wrong clock). Gathering any of these would leak the future into the eval.

## Expected Behavior
1. `gather_cutoff_context` gathers vault hits via `context_lib.gather(handle,
   sources=["vault"])` — Tier-1 only. The `sources=["vault"]` kwarg is exact, so
   `context_lib` never fans out to the live `_fetch_sent` / `_fetch_screen` /
   `_fetch_monday` tiers.
2. `gather_context.brief` is DROPPED — never read, never forwarded. Only the
   per-hit structured dicts (each content-timestamped strictly before the
   cutoff, then run through `leakguard.filter_mcp_result`) survive.
3. `search_brain` is EXCLUDED with NO mtime fallback, ever. `mtime` is the wrong
   clock and a raw float never matches the ISO guard, so it cannot fence; the
   only re-admission is `read_note` on explicit, vault-jailed, pre-cutoff paths.
4. `person_intel` is reduced to its static atemporal frontmatter — the dated
   `## Notes from replies` section (which absorbs notes derived from the
   held-out reply) and any ISO-dated line are stripped.
5. The returned dict surfaces an `excluded` audit list naming `search_brain`,
   `gather_context.brief`, and the Tier-2 sources — they are dropped AND
   surfaced, never silently discarded.
6. The `BrainAdapter` exposes only the four leak-eligible entry points; it has
   no Tier-2 / `search_brain` / `gather_context` method, so no code path can
   reach "now".

## Failure Condition
- `gather_cutoff_context` calls `context_lib.gather` without `sources=["vault"]`,
  or any Tier-2 fetcher (sent/screen/monday) is invoked.
- `gather_context.brief` (or any free-text prose source) appears in the output.
- A `search_brain` hit is admitted on `mtime` alone (any mtime fallback).
- A dated `## Notes from replies` line survives into `person_static`.
- A dropped source is not surfaced in the `excluded` list.
- The `BrainAdapter` grows a Tier-2 / `search_brain` retrieval method.
