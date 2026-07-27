# Channel-flatline alarm — "the proactive-card channel has gone quiet"

**Status:** LIVE. Fleet half runs inside `cabinet/scripts/cabinet-doctor.sh`
(check 16); Captain half rides the twice-daily briefing that already goes out.
Nothing new is scheduled and nothing new is sent.

## Why it exists

A captain-facing channel ran at roughly 146 proactive cards a week, then
emitted **zero for seven consecutive days**, and nothing anywhere said so.
Briefings kept flowing the whole time, so from the Captain's seat the org
looked healthy while one of its two channels to him was dead.

The number that recorded the collapse was already on disk and already being
read twice a day: `shared/interfaces/falsifier-series.jsonl` carries
`proactive_cards_7d` on every daily line, and the digest parsed it and then
rendered `acted_7d` / `reversal_rate_7d` / cells instead. The data was never
missing. **Nobody asked it a question.** This alarm is that question.

## What it asks, and how often

> the proactive-card channel has been silent since `<date>` — deliberate?

Once per silent episode. Not once per briefing, not once per day — once. The
whole point is that an alarm about noise must not become noise; a question the
Captain has already been asked and has not answered is not new information.

## Where the two halves live

| half | file | property |
|---|---|---|
| detector (pure) | `framework/frontdoor/card_flatline.py` | series + current gates → one verdict; no store, no clock beyond `now` |
| Captain line — text path | `framework/frontdoor/tell_digest.py` (`render_loop_readout`, leads the 📈 LOOP section) | crossing day only |
| Captain line — card path | `framework/frontdoor/run_briefing.py` (`_plain_headline`) | crossing day only; card mode archives the composed body, so the headline is the only thing he sees |
| fleet probe | `cabinet/scripts/card-flatline-probe.py` → `cabinet/scripts/cabinet-doctor.sh` check 16 | standing: reports for as long as the channel is dark |

The split is deliberate. The Captain-facing question is once-per-episode; the
doctor's is standing. A single sensor cannot honestly be both.

## The bar

- **48 hours** of `proactive_cards_7d == 0`, measured in HOURS off the series
  dates — a box that slept through a day must not silently shorten the window.
- The verdict `announce`s on the **crossing** row only (the previous row of the
  same run was under the bar), and only while that row is fresh
  (`ANNOUNCE_FRESH_HOURS`, 26h from the series date). Under the shipped 08:05
  producer cadence and the 07:30/19:30 briefings that is exactly one briefing
  per detection.
- **Recovery is the cooldown.** One row with a card in it ends the run, so the
  next silence is a new episode and asks again. There is no stored
  "already announced" flag, because there is nothing to store: the answer is a
  function of the series.

## What it refuses to call an alarm

| state | why it is not an alarm |
|---|---|
| `no-series` | the daily falsifier has never written a line on this box — measured absence, not silence |
| `never-active` | zero from birth: a channel that never spoke has not gone silent (this is the fresh-hatch shape, and it keeps the doctor GREEN) |
| `quiet` | no cards **and** no acts, no new stamped rows, no labels — the fleet stopped, and that is the fleet floors' finding, not this one |
| `deliberate` | a gate explains it: the `action-lane` fleet row carries `disabled: true` (ABSENCE-DISABLE or a staging park), or the Captain declared himself **away** |
| `unmeasured` | the newest line carries no `proactive_cards_7d`; null is not zero |
| `stale` | nothing written for 3 days — the series producer is the broken thing, and no card verdict can be read off it |
| `silent` | zero, unexplained, but still under the 48h bar |

`allow_sends()` (in `framework/env.py`) is deliberately **not** a gate: it
reports whether *this* process may send, and this process is the doctor or the
briefing — not the action lane that mints the cards.

## Reading the doctor line

```
$ python3.12 cabinet/scripts/card-flatline-probe.py --probe
BREACH since=2026-07-24 hours=72 announced=1
```

`announced=1` means the Captain's question already rode a briefing for this
episode; `announced=0` on a BREACH means it was asked on an earlier day and the
channel is still dark. Every state is AMBER-max in the doctor — a quiet captain
channel is a quality finding, never dead config.

Full verdict, including the gate reasons:

```
$ python3.12 cabinet/scripts/card-flatline-probe.py --json
```

Exit code: 0 for every honest non-alarm state, 1 on a BREACH (so a hand-run is
scriptable). Read-only: no DB, no network, no Redis, no writes.

## When it fires

1. Run `python3.12 cabinet/scripts/card-flatline-probe.py --json` and read
   `silent_since`.
2. Check the producer: the `action-lane` row in `cabinet/services.yml` and its
   launchd job. `framework/acting/run_action_lane.py` is the one writer of the
   `action-card` rows the series counts.
3. If the silence was intended, park the producer row properly
   (`disabled: true` + `disabled_reason:`) — the alarm then reads it as
   deliberate and stops asking, which is the point of writing the reason down.

## Known bound

The gates are read as of NOW, not as of each series row. A deliberate window
that *ends* in the middle of a silence therefore suppresses the one-time
Captain question for that episode. The doctor probe keeps reporting BREACH for
the whole silence, which is why the standing fleet-side half exists.

Tests: `framework/frontdoor/tests/test_card_flatline.py`,
`cabinet/scripts/tests/test_card_flatline_probe.py`.
