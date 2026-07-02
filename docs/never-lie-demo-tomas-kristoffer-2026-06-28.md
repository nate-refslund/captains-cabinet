# Proof-not-promises: deep-dive dossier on the real Tomás+Kristoffer thread (2026-06-28)

Ran the proposed dossier (read-only: gather_context + search_brain + open_commitments) on the
exact thread where the cabinet blind-drafted "ja det lyder godt - online møde i morgen passer fint 👍".
This is the demonstration Nate asked for: what deep investigation surfaces vs the blind agree.

## What the BLIND draft said
"ja det lyder godt - online møde i morgen passer fint 👍"
→ sycophantic (reflex yes), unverified (asserted "tomorrow's fine" — Nate's booked all day), context-free
(treated it as a generic "meeting").

## What the DEEP DIVE surfaced (the dossier)
- WHO: Kristoffer = Technical Project Manager (close colleague + sanctioned test partner). Tomás Soucek =
  PolAds v2 engineering (ran the autonomous Claude agent on polads-v2).
- THE REAL MEETING (not generic): it's the standing **fix-and-test session Kristoffer proposed YESTERDAY**
  (commitment cmt-1074cd6d9425, 2026-06-28: "kan vi to aftale vi fixer og tester hele ugen" = "can we two
  agree to fix and test all week"). The "online møde i morgen" is to DO that.
- WHY NOW / stakes: **hard ONE-WEEK launch deadline** (06-26 weekly check-in: "only one week left").
  PolAds v1.0 launch crunch.
- WHAT it covers (specific, from open commitments owed BY Nate to Kristoffer):
  · #2 Pro-spinner — "Vi tager pro plan purchase spinner-fejlen sammen over skærmdeling" (cmt-437fc2b71b60)
    = the meeting is where they screenshare-debug #2.
  · Credits top-up bug — "skal fixes" (cmt-16dc59246022).
  · "Sige til når alt er live" (cmt-1178ddbea8e6); bundle-discount fast-follow (cmt-b9975ac44da4).
- NATE'S STANCE: he WANTS this (it's his own commitment + the launch he owns) → agreeing is right, but the
  reply should be INFORMED + own the slot, not a blind "fine".
- TRUTHFULNESS CATCH: "tomorrow passer fint" asserts availability he doesn't have (booked all day) → the
  calendar guard + dossier turn this into propose-the-slot, not assert-it.

## The reply the design WOULD produce (truthful + investigated + stance-aware)
Something like: "ja, lad os tage fix/test-sessionen 👍 jeg indkalder i morgen omkring formiddag — så tager vi
Pro-spinner'en (#2) over skærmdeling + credits-bug'en, så vi er foran deadline." (Convene-the-slot, names the
ACTUAL work, reflects the deadline — vs blind "passer fint".)

## KEY CONNECTION this revealed (matters for the prod-release decision)
The meeting's #2 (Pro-spinner) is the SAME bug whose root cause is the prod-migration drift. So the
Kristoffer fix/test session CAN'T fully close #2 until prod is migrated 0089→0104. → The prod-release
decision (briefing item #1) is what unblocks the meeting's main agenda. Worth noting to Nate: approving the
migration makes tomorrow's Kristoffer session productive on #2 rather than blocked.

## Verdict
The dossier mechanism WORKS on real data — it surfaced the workstream, the why, the specific bugs, the
deadline, Nate's commitments, and the calendar conflict, ALL of which the blind draft missed. Empirical
validation of the never-lie/deep-investigate design (anti-shallowness, on Nate's own case).
