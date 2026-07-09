# Germline amendment — ATTENTION TRANSPORT FLOOR — 2026-07-09

**Status:** PROPOSED on `feat/attention-gateway` (PR #124); the Captain's
merge of that PR is the apply, and the post-merge `germline-lock.sh lock`
run covers the new entries with schg.

**Wave:** attention-gateway P3 (one-door transport), final merge review
finding 3 (`shared/interfaces/reviews/` cp-final).

## What is added to the locked set

Four files join `framework/policies/immutable-core.yml` (single source),
`cabinet/scripts/germline-lock.sh` FILES, `pre-tool-use.sh` §5 + §5b, and
`framework/policies/base-safety.yml`, in one lockstep change (carried as
`patches/germline-lock-extension-attention.patch`):

| Path | Why it is germline |
|---|---|
| `framework/frontdoor/channel.py` | P3 made it THE only Telegram door: it now carries the spec §4.10 floors — the `allow_sends()` kill-gate, token scrub, chunk-no-false-ACK, and transport feed journaling. An officer edit here forges the send perimeter itself (the enforcer-self-protection class). |
| `framework/attention/situation.py` | Canonical-ref identity feeds every dedup/suppression verdict in the acting lanes. An officer edit can widen suppression (attention-DoS: mute situations from the Captain) — a judge-plane surface. |
| `framework/attention/feed.py` | The append-only feed journal + cursor plane — the audit substrate that makes "instant on your word" and undo trustworthy (spec §4.10.2). An officer edit can blind the org or forge history. |
| `framework/attention/acted_overlay.py` | The act-once / reversal-awareness judgment (spec §4.10.4): what counts as "already acted" and what a Captain undo un-covers. An officer edit widens its own act surface. |

## What does NOT change

- No behavior change: the four files are byte-identical to their reviewed
  P3 state; only their write-protection changes.
- Evolution of these files continues via the established carry ritual
  (scratch-diff patch on a branch, PR review, Captain merge = apply,
  relock) — the same path `action_lane.py` already follows.
- The §4.10 invariant-core doctrine is unchanged; this closes the gap the
  final merge review named: the floors' NEW home was outside the lock.

Reply by merging PR #124; run `sudo bash cabinet/scripts/germline-lock.sh
lock` afterward to arm schg over the extended set.
