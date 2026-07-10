# Sovereign posture activation — the "fully autonomous" flip (Captain ritual)

**Why this is a proposal, not something an agent flips:** widening to
`sovereign` is, by your own ratified axes contract (§3, germline), the ONE
change that happens ONLY through the Captain's *attested ritual*. The resolver
(`framework/authority/posture.py`) honors sovereign **only** from a
`posture.yml` that is (a) present, (b) `deployment:`-matched to `CABINET_ID`,
and (c) `schg`-immutable (root-locked). No officer, env var, dashboard, or chat
verb can widen — a "go sovereign" button is a forge vector and is structurally
refused. So this is genuinely yours to run; I cannot, and the system would not
honor it if I tried.

## What sovereign actually changes (and what it does NOT)

Today you are at **guardian + act-first** (`act-first-enabled` present) — the
cabinet already ACTS on reversible things with a 48h undo handle, then tells
you. Sovereign is the next rung:

| step class | guardian (today) | sovereign |
|---|---|---|
| **reversible** (calendar, task create/update, reminders) | act-with-undo (tell after) | **auto** (act, journaled) |
| **internal_comms** (officer↔officer), **deploy_nonprod** | propose / gated | **act-and-tell** (`notify_after` — the digest line IS the audit) |
| **hard ceiling** (spend, prod deploy, `officer_dispatch`) | propose | acts ONLY under a Captain-signed standing grant; else gates + files a `NEED-<hex>` |
| **external recipients** (email, Teams, any human off-machine) | **per-item Captain-approved** | **per-item Captain-approved — UNCHANGED** |

**The load-bearing safety fact:** "fully autonomous" does **not** mean the
cabinet emails or messages people for you. External comms stay `queue_draft` +
your approval in *every* posture (your ACT-AND-DRAFT ruling). The `never_grant:
[external_comms]` line below makes that structural — even a signed standing
grant in that class is dropped fail-closed. Keep it.

## The ritual (copy-paste)

```bash
cd /Users/nate/captains-cabinet

# 1. UNLOCK the germline posture path (root — schg needs sudo)
sudo bash cabinet/scripts/germline-lock.sh unlock instance/config/posture.yml

# 2. WRITE the ruling (this exact content — deployment MUST equal CABINET_ID=hq-macbook)
cat > instance/config/posture.yml <<'YAML'
version: 1
status: ruled
ruled_at: 2026-07-09T18:30:00Z            # set to your real ruling moment
basis: "Captain ruling 2026-07-09 — go fully autonomous (sovereign); external comms stay gated"
deployment: hq-macbook                     # == CABINET_ID (verified)
flavor: personal
posture: sovereign
deployment_target: macbook
never_grant: [external_comms]              # KEEP — sovereign still never auto-sends to humans off-machine
YAML

# 3. RE-LOCK (root) — the resolver only honors sovereign when schg-immutable
sudo bash cabinet/scripts/germline-lock.sh lock

# 4. VERIFY the resolver now reads sovereign
python3.12 -c "from framework.authority import posture; r=posture.resolve_posture(); print('posture =', r)"
```

Expected: `posture = sovereign`. If it prints `guardian`, the file isn't
schg-locked or `deployment` ≠ `hq-macbook` — the fail-closed default held (as
designed). Re-check steps 2–3.

## Reversing it (instant, no ritual)

Narrowing is always allowed, from anywhere, with no attestation:
- Emergency drop-brake: `export CABINET_POSTURE=guardian` (or `earn_up`).
- Durable: `echo guardian > instance/config/posture-narrow` (unlocked by design).
- Or unlock → set `posture: guardian` → re-lock.

## Note on interaction with the attention gateway

Sovereign governs what the cabinet ACTS on. The attention gateway (P1–P5)
governs how it MESSAGES you. They're orthogonal: sovereign makes reversible
world-actions auto; the gateway (once its P6 integration routes the action-lane
through it) makes the resulting notifications quiet, deduped, and standing-card
based. Both keep the same external-comms floor.
