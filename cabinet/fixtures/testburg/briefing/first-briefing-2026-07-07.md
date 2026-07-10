# First briefing — 2026-07-07 (LOCAL-FIRST receipt)

<!-- demo fixture: the Testburg cabinet's hatch-day briefing. Shape mirrors
     framework/frontdoor/run_briefing._run_local_render; every value is
     synthetic (Ada Testburg's fictional bakery cabinet). -->

- composed: 2026-07-07T06:32:00Z on this machine, from local genesis surfaces only
- sent: no — the Telegram channel engages post-hatch when configured
  (channel.py + allow_sends untouched)
- propose-only: every outcome card below is a DRAFT (captain_ratified: false);
  ratify by moving it into instance/config/outcomes.yml

## Proposed outcome cards (org-proposed at genesis, drafts awaiting Ada)

1. **bakery-site: launch the Testburg bakery site**
   - what: testburg.example.com serves menu, hours, and an order form
   - why: You staked bakery-site as a lane at genesis (repo: bakery-site).
   - proof expected: the site answers on the staging box and Ada has signed
     off the copy at the Friday review

2. **newsletter: a weekly letter neighbours actually read**
   - what: issue 1 drafted, reviewed, and approved through the captain path
   - why: You staked newsletter as a lane at genesis.
   - proof expected: a staged draft exists and the send went out only after
     an explicit approve from Ada

3. **library grounding: the cabinet learns Testburg before it acts**
   - what: a genesis research brief lands on the Library shelf
   - why: an org that acts before it reads its own ground acts blind
   - proof expected: instance/memory/library carries the brief (or an honest
     IOU note if the tool was offline)

4. **captain decision loop: receipts Ada can trust from day one**
   - what: every act carries what/why/cost and a working undo handle
   - why: trust is earned through receipts, not claimed
   - proof expected: the first acted card shows all receipt fields and its
     undo reverses cleanly

*(honest note: cards 1-2 derive from the staked lanes, cards 3-4 are the
standing org cards — exactly what genesis proposes from a two-lane init.)*
