# The onboarding flow, screen by screen

Captured 2026-08-16 by driving the real product — `next build` + `next start`,
the live `/api/onboarding` bridge, the real core writing a real journey. Not
mockups: every screen below is the shipping component rendering committed state.

The set replaces the 40-file capture of the accumulating card. That flow no
longer exists: the card is a ROUTER now, and screens replace each other.

## Both branches, end to end

| # | File | Screen | What it is evidence of |
|---|---|---|---|
| 01 | `01-welcome.png` | S1 welcome | the door. One tap, four steps named, nothing asked yet. |
| 02 | `02-you-blocked.png` | S2 you | the no-mistake rule: Continue is refused AND says why ("Tell me what you do first — one sentence is enough."). |
| 03 | `03-dream.png` | S3 dream | the name is used the moment it is given; skipping is a real control, not an empty Continue. |
| 04 | `04-begin.png` | S4 begin | the branch, with the primary refused until one is chosen. |
| 05 | `05-folder.png` | S5A folder | the two CUT fields are gone (no purpose box, no trust-destination radio); the breadth caveat is folded, not deleted. |
| 06 | `06-approve.png` | S6 approve | the consent screen with every term UNFOLDED, each labelled by the question it answers — and the purpose seeded from the dream, which is the field cut working end to end. |
| 07 | `07-look.png` | S7 look | the read running, in the operator's words, with no controls — it flows into S8 with no click. |
| 08 | `08-find.png` | S8 find | the finding as a message from the First Mate: avatar, name via the title resolver, the citation as an inline chip, the rating INSIDE the message footer with its correction field. |
| 09 | `09-find-fold-open.png` | S8, fold open | the three layers: headline, "What I found", then "The full record" with every ledger row. Shorter never meant deleted. |
| 10 | `10-arrival.png` | S9 arrival | the ending, and the management view a revisit gets. |
| 11 | `11-connect.png` | S5B connect | the catalog (61 tools, browsable by shelf), what is connected with each tool's own sweep state, and the retry for a refused key. |
| 12 | `12-identity.png` | earned ask | which account is you — reached by RESUME, straight past the catalog, because the record already carries a sweep. |
| 13 | `13-salience.png` | earned ask | asked once, not twice: the operator's own word turns the open question into a one-tap confirm, with the full list still under it. |
| 14 | `14-sweep.png` | sweep | "I read across 2 of 3" — a count that cannot overstate itself — plus the core's own message, the per-tool table, the probe log and the open questions. |
| 15 | `15-connect-sheet.png` | S5B, one tool | the per-tool sheet: how to get the key in that product's own words, where the credential goes, and Connect refused with its reason until the key is pasted. |

## How to re-capture

```bash
cd cabinet/dashboard && npm ci && npx next build
DASHBOARD_PASSWORD= NODE_ENV=development npx next start --port 3177
```

Then drive `http://127.0.0.1:3177/onboarding`. The connect branch needs a
committed sweep; the mocked one used here writes `connector_sweep` and
`salience_rows` straight onto the journey state exactly as a real
`gather_connectors` leaves them — the connectors are mocked, the screens are not.

## What these cannot show

A screenshot proves a screen rendered; it cannot prove no disclosure was lost.
That is the parity gate's job, in two halves:
`framework/onboarding/tests/test_disclosure_parity.py` (every row the pre-change
tree emitted is still emitted, byte for byte) and
`cabinet/dashboard/src/components/onboarding/disclosure-render.test.tsx` (every
emitted row reaches the screen). Both are proven able to fail.
