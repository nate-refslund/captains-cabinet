# Pensionist test — rubric (captain-surface spec §7, final gate)

A vision agent is handed a real screenshot of ONE captain-facing card and
must answer, **using no cabinet vocabulary**:

1. **What is being asked of me?**
2. **What happens if I press each button?**
3. **What happens if I ignore it?**

## Fail law

A card FAILS its arm when the agent:

- cannot answer all three questions in plain words, or
- can only answer by resorting to a **banned term the card forced on it**
  (the banned list is `framework.attention.plain.BANNED` — the same table
  the jargon linter enforces). A banned term the agent introduces on its own
  initiative, when the card offered a plain alternative, is a WARN, not a
  fail — the runner reports both.

## Card inventory (spec §7)

TG: suggestion · draft · permission ask · escalation · briefing · nudge ·
"next 5?" · pin · acted+undo · withdrawn.
Dashboard (/queue): list · item detail · arm/confirm step · stale-verdict.

The committed `shots/` set covers the dashboard faces + the TG card sheet;
regenerate per `README.md` whenever any surface copy changes.
