# fix/briefing-and-recall — CP2: five claims the card could not support

Reproduced through the real chain — answers → `generate-instance.py` →
`first-briefing.sh --local` — on a 138-note folder, before any of them was
written. Every arm below FAILS against `origin/master`'s `genesis.py` and
passes on this branch (verified in a copied tree with `__pycache__` purged;
the pre-change output is visible in the failure text:
*"Acme Storefront: 3 of your own notes (2026-07-21), never read together"*).

| Claim the card made | What the citations actually show |
|---|---|
| **"never read together"**, the headline of every join card | nothing the cabinet can read shows the operator's reading history. Removed; the headline now states the join, which the citations below it support. |
| the WHY quote — *"I did not ask you for this, I read it: …"* | quoted a markdown **table**: `"\| Path \| Locked via \| Change \| \|---\|---\|…"`. The cabinet's own rendering machinery, presented as the operator's sentence, on the one line whose entire job is to be their checkable prose. |
| the quote's citation | pinned to the newest cited hit, which held only while a quote could never be empty. The quote now walks to the first hit with prose; its citation walks with it, or the card attributes one file's words to another. |
| **"Shared wording: X"** beside three citations | the threshold was 2 of 3, so a term could be absent from a file printed next to it. |
| the headline date span | dated all cited notes while the citation lines below said "(undated)" for some of them. |

## Two things deliberately NOT done, both measured first

* **Requiring the shared terms in ALL cited files.** Tried first; it silences
  a genuine 2-of-3 join, and "fix it by deleting the honest case" is what the
  previous pass wrote an arm against. Instead the count travels with the
  claim: *"Shared wording (in 2 of the 3): migration, billing"*. The old arm
  keeps passing and the sentence is now true.
* **A distinctiveness re-rank for the join terms.** Built and measured: on the
  same 138-note folder it produced the identical four Evidence terms in a
  different order and swapped two Cabinet-World terms for two no better. Not
  in the code — the same verdict, from the same kind of measurement, that the
  relative retrieval band got in CP1.

## Also fixed while measuring

A hard-wrapped sentence was severed by the short-line floor, so the card
quoted the operator mid-clause with no ellipsis: *"…require the unlock
ceremony to update on an"*, because the next line was *"armed Mac:"*. A short
line now continues a kept prose line. Inline emphasis markers are stripped
from quotes — every word and mark of punctuation is kept, and the quote then
matches what the operator SEES when they open the note rather than the raw
`**bold**` source.

## `local_root` (unit item d) was ALREADY FIXED on master — verified, not redone

```
branch        resolve_root -> None | available -> False | binding -> {'declared': False, …}
origin/master resolve_root -> None | available -> False | binding -> {'declared': False, …}
```

A hatch with no `sources.notes_root` produces:
*"Recall: bound to NOTHING — no folder has been granted, so it answers nothing
rather than guessing"*, with the declaration that fixes it. The arm is
`framework/sources/tests/test_local_source.py`. Nothing was changed here.

## Every citation in the produced briefing was verified by reading the source

7 dated citations: file exists, and the stated date equals the date derivable
from frontmatter or filename. 2 quotes: verbatim in the file the card cites
for them. 8 shared-wording terms: present in 3 of 3 cited files, matching the
claim. 2 headlines: the count equals the distinct files cited, and neither
asserts a reading history.

## Honest score: 2 of 3

Shipped scale (`cabinet/scripts/lib/briefing_score.py`): 0 wouldn't read it ·
1 read it, no value · 2 told me something I didn't know · 3 changed what I did
next.

**Not 3.** Rung 3 is a thing the OPERATOR does and reports. I am not the
operator and cannot observe it, and claiming it would be the unfounded claim
that produced the 1 in the first place.

**Defensibly 2**, and the weakest part named: the individual facts are the
operator's own, but the join — these three files, this span, these words in
common, never lined up — is a fact about their own corpus they did not have,
and every part of it opens. The Cabinet World card's join is genuinely
distinctive (`show-grammar`, `morphology`). The Evidence card's is not:
`framework, tests, file, path` are words most of that corpus uses. It is TRUE
— verified in all three cited files — and it is thin. A card that is honest
and thin is the correct trade against a card that is interesting and unearned,
but it is the ceiling of what term overlap can reach, and saying so is part of
the score.
