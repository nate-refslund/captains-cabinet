# Cabinet Onboarding v2 — one earned organization, three truthful faces

**Status:** Captain-approved design of record, 2026-07-14. The First Window
vertical slice in §7 is implemented. This governs the intelligence journey
after a Cabinet exists. `world-onboarding-hatching-2026-07-09.md` remains the
install/hatch authority.

## 1. Outcome

The Cabinet should feel startlingly intelligent without asking the Captain to
trust theater:

> Give me one narrow window. I will prove useful within minutes, study deeply
> under a Charter, show you what I think your strategy is, propose the
> organization that fits it, and ask you to commission responsibility with
> examples from your actual work.

The low floor is one folder, one purpose sentence, one approval, and one cited
result. The high ceiling is a self-organizing Cabinet with ratified Direction,
source-aware officers, per-lane authority, verification, receipts, and earned
graduation.

## 2. Product doctrine

### One core, three surfaces

There is one Captain identity, journey, Charter, event history, current card,
and organization.

- **Dashboard** is the dense face: scopes, evidence, Strategy Mirror,
  organization, commissioning matrix, receipts, and audit.
- **Telegram** is a complete conversational face. A Captain can start, approve,
  pause, continue, revoke, undo, purge, commission, and operate without a visual
  platform. OS/provider ceremonies may deep-link out and must return to the same
  checkpoint.
- **World** is the spatial and emotional face. Its authenticated overlays render
  and resolve the same cards through the shared service. The map/state engine and
  `/api/world/*` readers gain no independent onboarding write path.
- **Cabinet Companion/app shell** installs, starts, updates, notifies, and routes.
  It is not a fourth database. `Continue Orientation` opens `/onboarding`.

Surfaces have capability parity, not pixel parity. A Dashboard evidence list can
be a Telegram receipt and a World parchment, but card id, revision, allowed
actions, evidence, and resolution are identical.

### One Chair, one voice

The same Chair speaks everywhere. Stable card ids, optimistic revisions, a
process lock, and action idempotency make a decision resolve once. A stale
surface refreshes instead of overwriting the newer choice.

### Human words at the floor

Say Folder, Documents, Calendar, Mail, accounting export, and project board.
Do not require a Captain without technical vocabulary to understand MCP, API, repository, env
var, JSON, YAML, Redis, launchd, or posture.

## 3. Earned-intelligence sequence

### 0. Relationship destination

Ask where the Captain wants the relationship to head:

1. **Earn every responsibility.**
2. **Be proactive where actions are reversible.** Recommended.
3. **Aim for broad autonomy after it is earned.**

This is a destination, not a grant. It cannot activate a posture, grant,
officer, outcome, connector, send, deploy, or purchase.

### 1. First Window Charter

Ask for one purpose and one narrow source. Before reading, show a plain-language,
hash-bound Charter containing the exact root, purpose, read/write/network effect,
limits, exclusions, retention, lifecycle controls, and destination-with-no-grant
statement.

Entering a folder path is not consent to inspect it. Reads begin only after the
Captain accepts the current Charter hash. Resume revalidates hash and scope.

### 2. First Dividend

Within five minutes of usable access, return one useful result with file, line,
excerpt, and content hash: a broken documented command, conflicting delivery
date, uncovered commitment, urgent item, duplicate process, or inconsistency.

If no strong result exists, say so and return an honest orientation map. Never
manufacture a warning for “wow.” Raw contents are not persisted in this slice;
the manifest retains relative paths, sizes, and hashes, while the dividend keeps
only cited, secret-redacted lines.

### 3. Deep Orientation

Offer bounded, resumable study with a ghost deck and progress stream:

- Source Map with truth authority, volatility, sensitivity, and provenance;
- business, role, rhythm, commitment, decision, and entity maps;
- observed facts separated from inferences and Captain rulings;
- workflows, conflicts, risks, reversibility, and verification inventory;
- missing access requested just in time by the outcome it unlocks.

Orientation begins with one or two read-only sources. Operational read/write
tools come later only when the Cabinet can name task, scope, consequence, and
fallback.

### 4. Strategy Mirror

The Cabinet proposes purpose, 90-day success, constraints, bets, trade-offs,
not-goals, uncertainties, and contradictions with citations. Only the Captain
can edit or ratify the Mirror into Direction. The compiler cannot activate an
unratified mirror.

### 5. Formation

The Cabinet proposes lanes, officers, hats, skills, workflows, memory spaces,
sources, verification, action classes, benchmarks, first outcomes, and a
30–60–90 contract. It explains why each exists and the attention it saves.

The landed `framework.onboarding.formation` machine remains the resumable,
compiler-unreadable scaffold. Until real increments land, its IOUs stay honest
and are not shown as completed orientation.

### 6. Commissioning

Return to the destination with actual examples. Commission per lane and action
class, never through one global switch:

- **earn_up:** all classes propose; rungs require Captain grant.
- **guardian:** approved reversible internal classes may act with real undo and
  receipts; external, irreversible, and ceiling classes remain gated.
- **sovereign:** widest operation toward ratified Direction inside hard
  boundaries, `never_grant`, budgets, verification, and attested grants.

Each cell shows consequence, verification, receipt, undo, and hard ceiling.
Selecting broad autonomy at arrival never bypasses attestation.

### 7. First Campaign and apprenticeship

Run one ratified outcome. Report movement, evidence, actions taken/proposed/
blocked/undone, cost, corrections, and Captain attention. Then onboarding becomes
governance: graduation/demotion digests, expiring grants, permission shrinkage,
trust repair, re-orientation, and organization review.

## 4. Canonical implementation contract

The first slice lives under compiler-unreadable `instance/onboarding/v2/`:

- `state.json`: current projection;
- `events.jsonl`: append-only before/after events and undo references;
- `orientation-charter.json`: payload, hash, and status;
- `first-window-manifest.json`: scope and file hashes, no raw contents;
- `first-dividend.json`: finding and cited redacted lines;
- `../purge-receipts/`: content-free purge proof.

`framework/onboarding/journey.py` is the sole writer and card builder. It uses a
process lock, atomic owner-only files, idempotent action ids, optimistic
revisions, fixed limits, no network/subprocess, and no source writes.

| Face | Reader/action path | Shadow state allowed? |
|---|---|---|
| Dashboard | `GET/POST /api/onboarding` | No |
| World | same `/api/onboarding` overlay | No |
| Telegram | authenticated webhook → same core | No |
| Companion | opens `/onboarding` | No |

Purge requires literal `PURGE`, removes all journey content, and cannot be
undone. Revoke stops future reads while retaining derived artifacts until undo
or purge. Undo is event-backed.

## 5. Validation personas

1. **Software product development — primary dogfood.** Repository, release docs,
   backlog/runbooks, deployments, and strategy. Fixture: documented production
   command missing from `package.json` plus conflicting launch dates. Expected
   dividend: the broken command, cited.
2. **Client-services business.** Proposals, meetings, deliverables, and strict
   external-comms boundaries. Fixture: conflicting delivery dates. Expected:
   both sources cited.
3. **Community/nonprofit coordinator.** Ordinary documents and volunteer rotas;
   low technical confidence; meaning cannot depend on pixel art, color, or
   jargon. Fixture: uncovered welcome-desk shift. Expected: plain-language gap.

Every estate also tests sensitive content, symlinks, binary data, stale cards,
duplicate actions, and lifecycle controls. Secret leakage is a hard failure.

## 6. Acceptance bars

- No content read before exact Charter ratification.
- One cited real-source result targeted within five minutes.
- Honest orientation-only result when no strong finding exists.
- Cross-surface continuation with zero repeated answer or conflicting mutation.
- Telegram performs every slice action, including typed purge.
- World uses the shared service; no onboarding POST below `/api/world`.
- Text labels, 44px targets, DOM evidence, keyboard/screen-reader paths, and no
  critical color-only state.
- Relationship destination has zero authority effect.
- Journey cannot activate outcomes, officers, posture, workflows, grants,
  external communications, spend, or deploy.
- Revoke, undo, purge, stale revision, and idempotency are tested.

## 7. Sequence from here

1. First Window vertical slice — implemented.
2. Replace Formation IOUs with bounded discovery and real progress while
   retaining Charter validation and spend/call caps.
3. Source Map and provisional memory classes.
4. Strategy Mirror → Captain Direction ratification.
5. Formation dossier and organization ratification.
6. Per-lane commissioning and deliberate sovereign ceremony.
7. First Campaign and apprenticeship governance.
8. Commercial hardening: notarization, secure credentials, update/restore,
   managed hosts, and real usability trials.

Do not build three onboarding applications. Build one commissioning engine and
give it three truthful faces.
