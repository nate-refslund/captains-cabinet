# Re-baseline after the vault-search foundation fix — 2026-06-20

Follows `docs/first-fidelity-baseline-2026-06-20.md` (the 50% baseline). Nate's
directive: "fix foundation, re-baseline." We found + fixed a real foundation
bug, then re-ran the SAME n=10 held-out reply eval. This records the honest
result and what it means for the goal.

## The foundation bug we fixed (real, structural)
The harness runs in-process under system Python 3.9.6, whose sqlite3 lacks
loadable-extension support (`enable_load_extension` absent) → the embeddings
vector extension can't load → `context_lib._fetch_vault` silently returned **0
vault hits for the entire life of the harness, including the 50% baseline.**
Brain runs embeddings under python3.12 (extension support present). Fix
(commit `ba4707e`): the default `BrainAdapter` routes `gather_vault` through a
python3.12 subprocess reusing `context_lib.gather` wholesale; the content_ts
leak-fence still runs in the 3.9.6 parent. Measured: vault_hits **0/12 → 12/12**
(1–6 fenced pre-cutoff hits/case). Also fixed `drafting_lessons` cap-then-filter
(feed the full corpus). 347 fidelity tests green.

## Re-baseline result (n=10, same cases, vault context now flowing)
- **INTENT: 4/10 aligned (40%)**, 0 partial, 6 divergent. (Prior: 5/10 = 50%.)
- **DECISION/surface: 0 match + 4 partial + 6 divergent.** (Prior: 1 + 5 + 4.)
- **0 leaks, 0 errors** — clean run, vault context confirmed flowing.

## Honest reading — vault context did NOT lift the reply cell
The 50%→40% delta is **one case at n=10** — statistically flat, inside
single-run/single-judge noise. The real signal is the **absence of a lift**:
giving the clone real, leak-fenced vault context made no difference to
intent-fidelity on 1:1 replies. The vault fix is still correct and necessary —
the harness was structurally broken — but it is **not the lever for this cell.**

Why: the 6 divergent cases are social/closing/short exchanges — *"Okay. fedt!"*,
*"booket os mandag"*, *"smutter i seng"*, an external cold email. These are
conversational glue, not decisions. Their "intent" is thin/ambiguous, and the
clone diverges on surface phrasing where Nate is terse. **The reply cell is
dominated by VOICE + thread + brevity, not vault recall** — so vault context
can't move it (and a richer draft can even dilute a one-line reply).

## What this means for the goal (the strategic signal)
"Replace Nate as Head of Tech" is about **decisions** — triage, prioritization,
technical judgment, course-of-action. Those are the F3 **decision cell**, where
vault context (just fixed) actually pays off and where intent-fidelity maps to
*doing the job*. The **reply cell measures the VOICE axis** (which has its own
authenticity scorer), not intent. Conclusion:
1. Keep the vault fix (correct + necessary for every context-rich cell).
2. Stop chasing the reply-cell intent number — it's a voice surface, ~40–50%,
   and ~half its cases are social glue that can't be intent-scored.
3. **The next real foundation lever is the decision cell (F3)** — extract cases
   where Nate made a real decision/triage/course-of-action (Monday activity,
   closed commitments, the decisions corpus) and measure intent-fidelity THERE.

## Caveats
n=10, single run, single judge — directional. A larger run would tighten the
reply-cell number but would not change the strategic read (reply ≈ voice cell).
