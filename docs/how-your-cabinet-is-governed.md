# How your cabinet is governed

One page, plain language. You are the **Captain**. The cabinet is a small org
of AI officers that works for you — under rules that are enforced in code,
not promised in prose. This is the whole model, top to bottom.

## The constitution and presets

Every officer session starts from one assembled constitution: a framework
base (the rules every deployment shares) plus a short addendum from the
preset you chose at hatch (work, portfolio, …). Addenda can **tighten** the
base, never relax it. The assembled copy your officers actually read is built
fresh at every load by `cabinet/scripts/load-preset.sh`. If that assembly ever
fails, the officer **does not start** — the launcher refuses rather than boot a
worker on rules it cannot vouch for, the supervisor keeps retrying, and the
officer stays visibly down until the assembly succeeds.

## The authority matrix and the hard ceilings

Every action an officer proposes is classified into a risk class, and one
table — the authority matrix (`framework/policies/authority-matrix.yml`) —
says what that class may do at each level of proven confidence: propose it,
act with an undo handle, or act and tell you. Six classes are **hard
ceilings** that no amount of confidence ever lifts: external comms,
production deploys, spend, secrets, network writes, credential grants. Those
wait for you at every confidence level, forever. CI asserts no ceiling row
can resolve to "auto".

## Postures: guardian, earn_up, sovereign

A posture picks which column of that matrix your deployment runs under.
**guardian** (the hatch default, and what an absent file means) trusts the
work that can be taken back: anything with a deterministic undo acts from day
one, and read-only investigation plus **composing a draft** act and then tell
you. It proposes first everywhere else until autonomy is proven, and it drops
any class back to proposing the moment the evidence says so. Composing a
draft is not sending it — a message to a real person outside the org is
external comms, which waits for you at every confidence level. One honest
caveat on "acts from day one": that is the table, and the acting path behind
it is **off in a fresh hatch** — the lane acts unattended only once
`instance/config/act-first-enabled` exists (or `CABINET_ACT_FIRST=1`), and the
export ships neither, so until you flip it your cabinet proposes everything.
**earn_up** is
stricter still: everything starts at propose-only and autonomy exists only
where you grant it on the trust ladder. **sovereign** is the widest and can
only be activated by you, deliberately: the ruling file must be edited,
committed, and locked system-immutable (`instance/config/posture.yml` +
`sudo chflags schg`). Runtime knobs can only narrow a posture, never widen it.

## The trust ladder

Under earn_up, autonomy is climbed in named rungs — *would-like-to* (propose
first) → *intend-to* (announce, act unless vetoed) → *ive-done* (act, report
after) → *ive-been-doing* (fully graduated). A rung is **earned** by a track
record of confirmed outcomes, but it is **never self-granted**: the org can
only surface "this rung looks earned — grant it?" and you grant it by
writing a row into the Captain-locked `instance/config/trust-ladder.yml`.
Delete or corrupt that file and everything drops back to propose-only.

## Vetoes

Reply `never: <why>` to any receipt and that whole kind of action is removed
from unattended acting — recorded **verbatim** in
`shared/interfaces/captain-vetoes.yml`, matched by exact fields (never by an
LLM's paraphrase), and enforced until you explicitly lift it. **Silence
never clears a veto**; no timer, no expiry, no auto-thaw.

## Receipts

When the cabinet acts, you get a receipt: **what** it did (the exact
content), **why**, what it **cost** (unattributed when nothing was spent),
and an **undo** handle with a real 48-hour window backed by a write-ahead
journal and a deterministic inverse — no inverse registered means it never
acted unattended in the first place. Three reply verbs do everything:
`undo <n>` reverses, `👍 <n>` confirms, `never: <why>` vetoes the kind.
Your hatch seeds one clearly-labeled DEMO receipt
(`instance/memory/demo-receipt.md`) so you can read the anatomy before the
org has touched anything real.

## Retros and the falsifier

Your verdicts (confirms, undos, vetoes) feed a per-cell ledger; officers run
scheduled retros over it to turn outcomes into lessons. And every day one
falsifier line is appended to `shared/interfaces/falsifier-series.jsonl` —
acts, reversal rate, graduated cells — numbers chosen so that if the system
is NOT working, the data will say so. Trust here is measured, not asserted.
