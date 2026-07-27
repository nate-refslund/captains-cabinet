# Captain dates — the dates the org cannot forget

**Status:** BUILT 2026-07-27. The phone verbs write; the resolver reads; the
briefing renders every open row twice a day. Nothing is scheduled — this is a
value, a resolver and one consumer, not a service.

## What it is

Dated commitments the **Captain** declared. The rule it exists to enforce:

> **A date he sets must be impossible for the org to forget.**

## Why it exists

The 2026-07-26 Captain-Seat dry run's first finding: he set a release date, and
it appeared in **zero** of the next twelve days of briefings. Nothing in the org
held it. The briefing already surfaced dated promises he owed *other* people
(from the personal-source adapter, `briefing_commitments`) and dated follow-ups
the *org* wrote down (`cabinet/scripts/due-followups.sh`) — a date **he**
declared had no store, no resolver and no reader at all, so nothing could
surface it. The cost was his: he had to remember, and re-say, something he had
already said once.

**An empty store is a legal state** and means exactly what it says: he has set no
dates. Consumers then render **nothing** — never a placeholder row.

## Setting one (his phone; no terminal, per the 2026-07-17 controls ruling)

```
date 2026-08-13 board review      put a dated commitment on the org's books
dates                             what is still open, with countdowns
date done board                   close one (id or label prefix)
date move board 2026-09-01        change the date, keeping the history
```

`cabinet/scripts/officer-inbound-poller.py` answers these mechanically from its
own process — the same shape as `/killswitch`, `/score` and `availability` — so a
date he sets never waits on an officer being awake. It **records first and
confirms second**, and any error falls **open** to the Chair relay so his words
are never silently eaten. A selector matching nothing, or matching several rows,
is not an error: he gets a precise reply naming the real open dates, because
refusing beats closing the wrong date.

**Terminal (rarely needed):**

```bash
python3.12 cabinet/scripts/lib/captain_dates.py list
python3.12 cabinet/scripts/lib/captain_dates.py add 2026-08-13 "board review"
python3.12 cabinet/scripts/lib/captain_dates.py done board
python3.12 cabinet/scripts/lib/captain_dates.py move board 2026-09-01
```

## Where the rows live

`instance/config/captain-dates.yml` — append-only, **latest row per `id` wins**.
The path is owned by `framework.env.captain_dates_path()` (the one resolver
writer and readers share, so they cannot drift). The live file is gitignored (his
own calendar, never repo content); the tracked twin
`instance/config/captain-dates.yml.example` documents the shape. It is on
`runtime-provision.sh`'s persistence list, so a deploy or rollback never drops a
date; the egg export deletes it, so a fresh cabinet hatches holding none.

`done` and `move` **append** rather than edit. A `move` writes two rows — the old
`id` goes `moved`, and a fresh `id` carries the new date with `supersedes` naming
the row it replaced — so *"what did he originally say, and when did it change?"*
stays answerable. His verbatim message rides along as an inert comment line.

A row the reader cannot validate reads as **absent**, which leaves the previous
row for that `id` standing. That direction is deliberate: an unreadable `done`
leaves the date **open and still visible**, never silently disappeared.

## Consumers

| consumer | what it does | when there are no open dates |
|---|---|---|
| `framework/frontdoor/morning_synthesis.py` (`captain_date_items`) | ONE briefing item with **one line per open date**, countdown included, overdue rows first and marked `OVERDUE by N days`; rides every 07:30 and 19:30 briefing | emits **no item** — no header, no placeholder |
| `cabinet/scripts/meta-cognition/captain-seat-pack.sh` (DATES section) | lists open dates with `tracked_in_latest_briefing=yes|no` | prints the measured absence line |
| Captain-Seat Review (`memory/skills/cross-officer-retro.md` Part 1c) | an open date the latest briefing does not carry is an in-window paid cost — he held it himself | an empty store is not a finding |

The briefing item is **one item carrying N lines**, not N items: the composer caps
non-`ping-now` tiers at five items (`framework/frontdoor/run_frontdoor.py`), so N
separate items would let the sixth date roll silently into a count line — the
exact failure the store exists to prevent. One item costs one slot no matter how
many dates are open, and the lines inside it are never capped.

## Boundaries

- **Captain-declared input, never a performance number.** These rows are things
  he typed about his own calendar: not derived from evidence, not about an
  officer, and never rendered as an officer-visible measure of anyone. A
  countdown is a reminder, not a score.
- **The label is his words.** It is the only free-text field that becomes a
  value, because the briefing prints it back to him. It is control-character
  stripped, whitespace-collapsed, length-capped at the writer
  (`framework.env.CAPTAIN_DATE_LABEL_MAX`) and written as a quoted scalar, so a
  message can never become a second YAML key.
- **Refuse, don't repair.** `2026-02-31`, a year outside 2000–2100, a bare date
  with no label, and an unknown word after `date` all return "not a dates
  command" and relay to the Chair rather than storing something nobody meant.
- **No new ping channel.** Open dates ride the existing twice-daily briefing at
  `batch` tier. An overdue date gets a louder LINE, not a new interrupt — the
  availability doctrine (the org fits the declared budget) is unchanged.

## Test fence

`CABINET_CAPTAIN_DATES_FILE` relocates the store, and the repo-root
`conftest.py` points it into the pytest session sandbox — fenced at birth. A
fabricated row would put a deadline nobody declared in front of the Captain twice
a day; a deleted one would reproduce the original failure.
