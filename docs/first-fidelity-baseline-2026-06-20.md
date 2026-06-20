# First real intent-fidelity measurement — 2026-06-20

The first honest measurement of how Nate-like the digital clone is. Held-out,
leak-safe, clone identity ON, real OAuth judge, 10 scoreable reply cases.

## Result (n=10)
- **INTENT-fidelity: 5/10 aligned (50%)** — the clone served Nate's actual
  intent half the time. (5 aligned, 0 partial, 5 divergent.)
- **DECISION/surface: 1 match + 5 partial + 4 divergent** — vs the 0.083 (8.3%)
  generic-assistant baseline, the clone is at least *partial* on Nate's literal
  words 6/10. Surface is the lesser axis (design: intent dominates).
- **Leaks: 0** — the cutoff fence redacted ~180 post-cutoff items on live data
  and hard-failed nothing. Leak-safety is real and working on real data.

## Honest reading
50% intent-fidelity is a real, un-gamed baseline — meaningfully above
generic/chance, with clear room to grow. This is the "before" number every
future improvement is measured against. NOT a precise figure: n=10, single run,
single judge.

## Known levers to lift it (next)
1. **lessons = 0** — `drafting_lessons(cutoff)` returned nothing (the cap-then-
   filter ordering drops valid pre-cutoff lessons). Wiring Nate's correction
   corpus in is the most likely near-term lift.
2. **Scoreable fairness filter** into `build_cases` (so every eval is clean —
   this run filtered inline; ~5% of the universe is degenerate link/credential/
   ack cases that can never align).
3. **Larger run (n=30-50)** for a stable baseline.
4. **F5 ensemble judge** — single-judge verdicts have noise at the margin; some
   `divergent` may be judge strictness.
5. **Endorsement axis** — some `divergent` may be cases where the clone was
   arguably fine but differed from Nate's exact move (score vs endorsed best
   self, not raw actual).
6. **Richer context** — gather is thin for 1:1 replies (the thread IS the
   context); meeting-backed cases gather more.

## Provenance
`/tmp/filtered_intent_eval.py` (n=10 scoreable, clone arm, gather+intent).
Clone identity: voice 4000ch + nate_model patterns 4215ch injected (privacy-
fenced, never egress). Cases drawn from the send-1to1-reply universe.
