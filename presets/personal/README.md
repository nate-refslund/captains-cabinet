# Personal preset — for one operator who owns a project

**Status: active.** Activate it with:

```bash
echo personal > instance/config/active-preset
bash cabinet/scripts/load-preset.sh
```

(Until 2026-07-27 this file said the opposite — "Placeholder … Empty until
Phase 2", and it forbade writing `personal` into
`instance/config/active-preset`. That sentence is why the one preset shaped
for an operator who does not run a company was the one preset that shipped
inert. It is superseded.)

## Who this is for

Someone who owns **a project**, not a company. A developer inside a large
organisation. A designer running one product line. A researcher, a freelancer,
a person with a side project and a day job. The cabinet's north star — *the
cabinet becomes the company and runs it* — is an **aim**, not an entry bar, and
most operators will never reach it. This preset is for the majority case.

Every other shipped preset (`work`, `developer`, `portfolio`) stands up a
C-suite — a CoS, a CTO, a CPO, a CRO, a COO — for a company the operator does
not run. This one ships **no C-suite at all**.

## What it ships

| Role | What it is for |
|---|---|
| **Navigator** | What to do next on the project, and the evidence for why that |
| **Librarian** | Context assembled from what the operator already legitimately reads — cited, dated, joined across time |
| **Reviewer** | Fresh eyes on the operator's own work before it meets anyone else |
| **Physical Coach** | Sleep, training, nutrition, recovery over months |
| **Mindfulness Coach** | Reflection and emotional awareness, consent-gated |

All five ship as **scaffolds**. `cabinet/mcp-scope.yml` is the single source of
truth for hired-vs-scaffold; move a slug from `scaffolds:` to `agents:` there
to hire it.

Also shipped: a consent-first constitution addendum, a privacy/redaction safety
addendum, four longitudinal schemas (`longitudinal_metrics`,
`coaching_narratives`, `coaching_consent_log`, `coaching_experiments`), and a
role-adaptation measurement scenario so the self-improvement validation gate
has something to measure instead of failing closed on activation.

## Recall: a folder, read-only

Set `autonomy.flavor: personal` in your answers file, point
`sources.notes_root` at your own notes folder, and
`cabinet/scripts/generate-instance.py` writes an
`instance/config/sources.yml` binding
`framework.sources.local:LocalNotesSource` over exactly that folder. Search is
exact-term over it, ranked, with the file and heading on every hit.

**There is no default, and that is deliberate.** Until 2026-07-28 an
undeclared folder resolved to `<root>/vault` — the cabinet's own shipped
documentation — so a fresh personal box reported live recall while answering
out of the framework's docs. Now an undeclared folder is UNSET: `available()`
is False, every gather is honestly empty, and the first briefing says so with
the one line that fixes it. `CABINET_LOCAL_SOURCE_ROOT` overrides at runtime.

**The first briefing reads it.** Genesis asks this seam about every subject you
declared and composes its outcome cards from what comes back — your own
sentence quoted, each file cited with the date derived from its frontmatter or
filename, and the wording two or more of your notes share. Nothing is asserted
that a citation does not already show, and when recall holds nothing the cards
are identical to what they would have been without it.

Bounds are structural, not settings: text extensions only, a file-count cap, a
per-file byte cap, hidden directories skipped, and every path realpath-jailed
inside the declared root — a symlink pointing out of the folder is skipped, not
followed. Dates are derived from frontmatter or from the filename, or are
**absent**; never from mtime, because a checkout or a sync rewrites mtime
wholesale and a fabricated date defeats the leak fence downstream.

**There is no write side.** `framework/sources/local.py` has no write method,
and no `dispatch:` is emitted, so material this reads can never be written
back. That matters most at exactly this altitude: what an individual may
legitimately *read* at work is often not what they may *change*, and an agent
editing a colleague's ticket is not recoverable — undoing the write does not
un-notify the colleague.

## What this preset promises, and what it does not

**It promises context and leverage.** Nothing prevents an individual from
holding a picture of their project — and of the organisation around it — that
no one at their altitude usually holds, assembled from systems they already
legitimately access, and from proposing with evidence nobody else can put
together. That is real, and it is what the Librarian is for.

**It does not promise growing authority, and it never will.** The six hard
ceilings — external comms, production deploys, spend, secrets, network writes,
credential grants — belong to whoever owns the resources. Inside an employer's
estate that is the employer, not the operator. A grant is valid only when
signed by the authority root, so no posture, no trust ladder and no amount of
earned evidence can climb there. The ladder has no rungs to climb at this
altitude, and that is a property of who owns the resources — not a limitation
of the cabinet.

So: **authority is granted downward and capped by the org chart; context is
assembled sideways and capped only by access.** Copy claiming this preset grows
into running the company would be false, and the first person who reads it and
hits the ceiling would rightly conclude the framework lied to them.

## Judging whether it is working

One question after each briefing: **did it change what you did next?**
(`cabinet/scripts/lib/briefing_score.py`, rung 3.) Deliberately not *"would you
act on it"* — at this altitude the honest answer to an excellent briefing is
often *"I can't act on that, it isn't mine"*, which pegs the scale at 2 forever
and measures the operator's place in an org chart rather than the cabinet's
quality. Scores are per-operator and never comparable between operators.
