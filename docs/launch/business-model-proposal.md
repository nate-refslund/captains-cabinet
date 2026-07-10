<!-- DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated. -->

**DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated.**

# Business model — PROPOSAL ONLY

**Status: proposal.** Nothing in this document is a commitment, a price, or
an offer. **No pricing goes live without Captain approval + employer-IP
clearance** (see the CG-7 section). This document exists so that when CG-7
opens, the commercial conversation starts from a written, honest baseline
instead of a whiteboard.

## 1. What the license already decides

The repo ships under **Business Source License 1.1** (`LICENSE`), which
already draws the commercial line — no new licensing work is needed for
launch:

- **Free forever for users:** fork, self-host, modify, production use —
  as a founder, an employee, a solo operator, or a team.
- **Reserved:** offering the Licensed Work to third parties on a hosted or
  embedded basis that competes with the Licensor's paid managed service.
- **Change Date:** each version converts to **Apache 2.0 four years** after
  that version's publication.
- **Naming split (README):** the open-source framework is **Captain's
  Cabinet** (this repo); a commercial productization built on it
  (installer, billing, managed dashboard, support) uses the shorter name
  **Cabinet**. Only the repo is open source.

So the model below is the standard BSL shape: open core with a reserved
hosted lane — chosen at licensing time, sketched here.

## 2. Proposed tier sketch (draft — all names/pricing illustrative)

| Tier | What it is | Price posture |
|---|---|---|
| **Self-host** | The whole repo: full governance core (receipts, authority matrix, hard ceilings, kill switch, gate), all presets, hatch tooling. No feature-crippling — the open tier IS the product | **Free** (BSL grant) |
| **Hosted managed instance** | The BSL-reserved lane: a managed Cabinet org — provisioned host, updates, monitored proof gates, receipts-vault backup, restore drills. The customer stays the Captain; hard ceilings still route to THEM (governance is never the upsell) | Paid, monthly per org |
| **Support + marketplace** | Paid support (onboarding help, upgrade windows, SLA) and a preset/skill marketplace with **rev-share** to third-party authors | Paid support plans; marketplace % rev-share |

Two commitments worth making explicit in any public pricing page later:
governance features are never paywalled (a free self-hoster gets every
ceiling, veto, and receipt), and customer receipts/vault data never leaves
the customer's org.

## 3. Category price anchors (pattern, not research)

The familiar indie-infrastructure pattern is a **$29 / $99 / $249 per
month** three-step ladder. Mapping that pattern onto the tier sketch —
purely as an illustrative anchor, NOT researched pricing:

- **~$29/mo** — supported self-host: priority upgrade notes, support
  channel access.
- **~$99/mo** — hosted managed instance, single org.
- **~$249/mo** — hosted portfolio (multi-org / multi-lane), priority
  support, restore-drill SLA.

Honesty notes that must survive into any real pricing work:

- **These numbers are a category pattern, not competitor research.** No
  competitor's actual pricing has been verified by this program
  (`comparison.md` policy applies here too).
- **Unit economics are NOT typical SaaS.** A hosted org rides a Claude Max
  subscription plus a dedicated-Mac-class host per customer org. COGS per
  hosted seat is high and the $99 anchor may be below cost; a real floor
  calculation is unresolved and CG-7-blocking for the hosted tier.
- Marketplace rev-share % is deliberately unstated — depends on payment
  rails and volume assumptions that don't exist yet.

## 4. What CG-7 must resolve BEFORE any of this goes live

In order; the first two are absolute:

1. **Employer-IP clearance, in writing.** The author is employed; the
   employer IP agreement must be cleared in writing for any commercial
   offering (and for the public launch itself) before a single price is
   shown anywhere. Named here abstractly on purpose — resolving it is a
   Captain-side legal errand, not a build task.
2. **Captain approval of external publication at all** — publishing is
   external comms: a hard-ceiling class, per-item Captain approval,
   structurally non-grantable.
3. **Trademark / name check** for "Cabinet" and "Captain's Cabinet" in the
   target markets.
4. **Real pricing research** to replace §3's pattern anchors (competitor
   pricing, willingness-to-pay in the wedge persona, hosted COGS floor).
5. **Billing rails** (provider choice, VAT/tax handling, refund policy)
   and the legal entity that sells.
6. **Support commitment sizing** — what SLA a one-person Licensor can
   honestly sell; under-promise beats churn.
7. **Hosted-at-v1 decision** — whether the hosted tier launches at all in
   v1, or the launch is self-host + support only (lower risk, lower COGS,
   defers the floor problem).

## 5. Explicit non-goals

- No ads, no data sale, no telemetry-funded free tier.
- No governance paywall — ceilings, receipts, vetoes, kill switch are
  never premium features.
- No pricing page, checkout, or "coming soon" tease ships with the launch
  kit. **No pricing goes live without Captain + employer-IP clearance.**
