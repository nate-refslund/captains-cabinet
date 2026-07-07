# Eval 021 — Brain retrieval quality invariants

**Category:** quality
**Tests:** the memory estate's retrieval surface (embeddings hybrid search + brain-mcp) against pinned invariants. The evolving probe SET lives outside germline at `~/.screenpipe/state/brain-probes/` (curator-writable); THIS file pins what may never regress.

## Scenario
Run the frozen-core-14 probe suite (`~/.screenpipe/state/brain-probes/probes/`, `run_probes.py`) against the live index, plus the leak sweep (`--filter` checks on excluded prefixes).

## Expected Behavior
1. p@1 ≥ 0.90 and p@3 ≥ 0.93 on the frozen-core-14 (baseline 0.929/0.929, 2026-07-05).
2. Zero hits under excluded/parked prefixes: `3-People/_noise/`, `8-Archive/`, `7-Resources/My-Prompts/`, `*/_archived-dups*`, `0-Self/` (privacy fence — access only via me_signal).
3. Per-hit text ≤ the 2,000-char cap (+ truncation marker); max 2 chunks per source file.
4. `as_of` fencing stays fail-closed: unstamped chunks are EXCLUDED under a fence, never served; no mtime fallback.
5. Suppressed person stems (`state/person-merge-plan-20260705/suppressed-slugs.json`) never re-appear as live 3-People root notes in any top-8.

## Failure Condition
Any invariant above fails → the change that caused it is rejected (evolution-loop rule); if caused by drift rather than a change, the Memory Curator must page cos via the brain-quality trigger and freeze its own mutating runs until the gate is green again.

*(Staged 2026-07-05 at ~/.screenpipe/state/brain-probes/staging/; copy into captains-cabinet/memory/golden-evals/ during the current unlocked germline window on Nate's OK — the dir is schg-locked when the boundary re-arms.)*
