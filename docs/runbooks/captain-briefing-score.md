# The 14-day briefing trial — did the Captain get value?

**Status: BUILT, nothing scheduled** (2026-07-26). One number per briefing,
stored append-only, summarised on demand. Nothing runs it, nothing gates on
it, it has no launchd job and no `cabinet/services.yml` row — it works in a
propose-only, no-launchd hatch because it is a file and a function.

## Why it exists

Nothing in this cabinet measured whether the Captain reads or values anything
it sends him. The only value composite that exists — OVI
(`framework/ovi/components.yml`) — has never been published and has no
`services.yml` row. Until 2026-07-26 it also scored its attention term
**inverse**, treating Captain contact as a cost to minimise, which is the
opposite question; that term is now `captain_attention_well_spent` — the share
of his attention spent on decisions only he could make, reading 0.0 when the
org never asked at all. Even corrected it infers from telemetry. This
instrument asks him, which is the only way to learn whether a briefing was
worth reading.

## The scale

| | |
|---|---|
| **0** | wouldn't read it |
| **1** | read it, no value |
| **2** | told me something I didn't know |
| **3** | changed what I did next |

Rung 3 was **"I'd act on it"** until 2026-07-27. It conflated how good the item
was with whether the reader had the AUTHORITY to act on it. For an operator
inside an organisation they do not run, the honest answer to an excellent
briefing is often *"I can't act on that, it isn't mine"* — a permanent 2, with
the ceiling set by the org chart instead of by the cabinet. *"Changed what I
did next"* is reachable at every altitude and is still a number he typed about
the cabinet's output, so the never-a-score exemption is untouched. There is
deliberately no second, per-altitude rubric.

The summary is **never comparable across operators** — the scale is
self-referenced against one reader's own week — and it says so in its own
output. `unscored` stays in the readout: an unscored briefing is probably a 0.

## How he scores one — the phone path

Reply on Telegram:

```
/score 3
/score 2 knew half of it already
```

The inbound poller answers it mechanically from its own process — the same
shape as `/killswitch`, and for the same reason: the Captain's control must
not wait on an officer being awake. He gets one confirmation line naming the
briefing that was scored. No terminal, no app, about three seconds.

The command is anchored, so `/score` inside a sentence is ordinary
conversation for the Chair. `/score 4` and `/score 32` are refused. Any
failure — library missing, disk unwritable, Telegram refusing — relays his
message to the Chair instead of swallowing it, and a confirmation is never
sent for a score that did not reach disk.

## The terminal path (same instrument, for whoever runs the trial)

```
python3.12 cabinet/scripts/lib/briefing_score.py score 3
python3.12 cabinet/scripts/lib/briefing_score.py score 2 --note "knew half of it"
python3.12 cabinet/scripts/lib/briefing_score.py reply "/score 3 the pricing row is wrong"
python3.12 cabinet/scripts/lib/briefing_score.py summary
python3.12 cabinet/scripts/lib/briefing_score.py summary --days 14 --json
```

`score` binds to the most recently archived briefing — "the one I just got".
`--briefing <id>` overrides it.

## Reading the summary

```
9 briefings scored · median 2
0=1  1=2  2=4  3=2
Trend: 1 → 2 (up)
Briefings sent: 14 · no score: 5 (an unscored briefing is probably a 0)
```

- **n / median / distribution** over the scored briefings.
- **Trend** = median of the first half vs the last half, chronologically.
  Under four scores it prints "not enough scores yet" rather than inventing a
  direction.
- **no score** is the point of the whole line. Silence is data: a briefing he
  never scored is far more likely a 0 than a missing 2. If it is not counted,
  the trial flatters itself. With no briefing archive on the machine the
  summary says so instead of printing a reassuring zero.
- A **re-score** of the same briefing is a correction, not a duplicate: the
  last row wins, and both rows stay on disk.

## Where the data lives, and why it survives a deploy

`instance/memory/briefing-scores.jsonl` — one JSON object per line,
append-only, never rewritten.

`cabinet/scripts/runtime-provision.sh` links `instance/memory` as a **whole
directory** (`INSTANCE_PERSISTENT_SEEDED_DIRS`), so a file that did not exist
when the release was cut still lands in the shared instance-data store and
survives a deploy, a rollback and a slot swap — no persistence-list edit
needed. `cabinet/scripts/lib/tests/test_briefing_score.py` asserts this
against that script's real text, so a future edit to the persistence lists
turns the suite red rather than silently stranding fourteen days of scores.

Two nearby homes were rejected at authoring time, because against the base
commit neither survived a deploy:

- top-level **`memory/tier3/`** — then named by no `INSTANCE_PERSISTENT_*`
  list, so a deploy stranded it on the old slot;
- a new **`shared/interfaces/*.jsonl`** series — its persistence list is
  per-file, and the loop then linked only a leaf that already existed in the
  shared store, so the FIRST write of a brand-new series was lost.

**Landing note, 2026-07-26.** The state-persistence preflight landed on master
while this unit was in flight and closed both holes: `memory/tier3` joined
`INSTANCE_PERSISTENT_SEEDED_DIRS`, and the per-file loop gained adoption of a
runtime-created file. Neither rejected home is deploy-unsafe any more, so the
two bullets above are the dated reason of record rather than a live warning.
`instance/memory` remains the right home for the reason that did not change:
it is co-located with the briefing archive this instrument scores, so one env
knob fences both, and a whole-directory link needs no persistence-list edit at
all.

The briefing archive it scores, `instance/memory/briefings/`
(`framework/frontdoor/run_briefing.py`), sits under the same surviving
directory.

## Why this is not a never-a-score violation

EVAL-025 bars **evidence-derived aggregates** from becoming officer-visible
scores or inputs to generation/selection. A number here is one the **Captain
typed** about the cabinet's output — the class the law's own fixture already
exempts by name (`feedback_rating`: "a value the Captain typed about the
cabinet, not an evidence-derived aggregate about an officer"). It is not
derived from evidence, it is not about an officer, and nothing in this
instrument reaches `cabinet_projection` or any officer read surface.

## What this deliberately is not

Not a metrics framework, not a dashboard, not a north-star computation, not an
aggregation pipeline. One number per briefing, stored honestly, summarised on
demand. If a future session finds itself adding a scheduler, a weighting
scheme or a second consumer, that is the failure mode this instrument was
built to avoid — `test_nothing_schedules_this` fails the suite if it gets a
`services.yml` row or a launchd plist.

## Files

| Path | What |
|---|---|
| `cabinet/scripts/lib/briefing_score.py` | the whole instrument (library + CLI) |
| `cabinet/scripts/officer-inbound-poller.py` | the `/score` phone door (`is_score_command`, `score_command_reply`) |
| `cabinet/scripts/lib/tests/test_briefing_score.py` | library suite |
| `cabinet/scripts/tests/test_briefing_score_command.py` | phone-door suite |
| `conftest.py` | `CABINET_BRIEFING_SCORES_DIR` test fence — no test run can write the live store |
| `.gitignore` | the store is runtime data, never committed |
