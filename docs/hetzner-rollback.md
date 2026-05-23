# Hetzner Cabinet Rollback Procedure

If the Mac native Cabinet fails post-cutover and we need to fall back to the Hetzner deployment, this is the runbook. Estimated rollback time: **30-60 minutes total** (including BotFather token regeneration + .env update).

Per Captain Mac Migration Directive (msg 2599 §Risk Mitigation): Hetzner stays alive in frozen state for fast rollback, NOT decommissioned. Per Spec 065 v1.1 Checkpoint 8.5.

## Pre-conditions

- Hetzner cabinet was suspended (not destroyed) at Phase 8 — `docker stop $(docker ps -q --filter "name=cabinet-")` only.
- Phase 0 + Phase 8 snapshots both kept (different purposes — pre-cutover vs Hetzner-suspension state).
- `v0-hetzner-suspended` git tag points to the last-live Hetzner commit.

## Step 1 — Decide which snapshot to restore from

- **Phase 0 snapshot (rollback target)** — restores Hetzner to the moment we *started* migrating. Use if you want to undo everything since cutover, including any state changes that happened during Mac native operation.
- **Phase 8 snapshot (Hetzner-suspension state)** — restores Hetzner to the moment we *paused* it. Use if Hetzner-side state was still useful through cutover (e.g., the Hetzner backlog continued to be updated until you literally flipped the switch).

Default: **Phase 8 snapshot** (more recent; what most rollback scenarios actually need).

## Step 2 — Restore Postgres + Redis from snapshot

```bash
# Restore Postgres (assumes the snapshot was made with pg17 client per Spec 065 v1.1 CTO #3)
/opt/homebrew/opt/postgresql@17/bin/psql "$NEON_CONNECTION_STRING" < <phase8-suspend-postgres.sql>

# Restore Redis from .rdb snapshot
# (On Hetzner host: stop redis, copy snapshot to /var/lib/redis/dump.rdb, start redis)
docker stop cabinet-redis
sudo cp <phase8-redis-dump.rdb> /var/lib/redis/dump.rdb
docker start cabinet-redis
```

## Step 3 — Restart Hetzner officer containers

```bash
# Bring all officer containers back online
docker start cabinet-cos cabinet-cto cabinet-cpo cabinet-cro cabinet-coo cabinet-redis cabinet-postgres
docker ps  # verify all 5 + supporting services running
```

## Step 4 — BotFather token regeneration (CRITICAL — revocation is one-way)

When we suspended Hetzner at Phase 8, we revoked the 4 officer bot tokens at BotFather (cabinet-cto-bot, cabinet-cpo-bot, cabinet-cro-bot, cabinet-coo-bot — keeping only cabinet-cos-bot for Mac single-Lead Telegram). To restore Hetzner officers, we must **regenerate** new tokens — revoke is NOT reversible.

Procedure on Telegram (Captain hands-on):

1. Open Telegram, message `@BotFather`
2. `/mybots` → select `cabinet-cto-bot` → **"API Token" → "Generate new token"**
3. Copy the new token
4. Repeat for `cabinet-cpo-bot`, `cabinet-cro-bot`, `cabinet-coo-bot` (3 more)

## Step 5 — Update Hetzner `.env` with new tokens

```bash
# On Hetzner host
cd /opt/founders-cabinet
# Edit cabinet/.env — replace the 4 stale token values:
# TELEGRAM_CTO_TOKEN=<new-cto-token>
# TELEGRAM_CPO_TOKEN=<new-cpo-token>
# TELEGRAM_CRO_TOKEN=<new-cro-token>
# TELEGRAM_COO_TOKEN=<new-coo-token>
$EDITOR cabinet/.env
```

## Step 6 — Restart officer containers so they pick up new tokens

```bash
docker compose restart cabinet-cto cabinet-cpo cabinet-cro cabinet-coo
```

## Step 7 — Verify Hetzner officers operational

```bash
# Check heartbeats
for o in cos cto cpo cro coo; do
  redis-cli -h <hetzner-redis> GET "cabinet:heartbeat:$o" | xargs -I{} echo "$o: {}"
done

# Test each officer's Telegram bot by sending a DM
# Each should receive + react + respond
```

## Step 8 — Sunset Mac native Cabinet (optional)

If you're rolling back permanently:

```bash
# On Mac: bootout all LaunchAgents
for o in cos cto cpo cro coo; do
  launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.$o.plist 2>/dev/null
done
# Bootout watchdog + cost-summary + worktree-listener too
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.heartbeat-watchdog.plist 2>/dev/null
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.cost-summary.plist 2>/dev/null
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.worktree-listener.plist 2>/dev/null
```

If you're rolling back temporarily (debug Mac failure, then re-cutover), leave Mac LaunchAgents in place but `launchctl bootout` them — they can be re-bootstrapped after the issue is resolved.

## Estimated rollback time

- Snapshot restore: 5-10 min (Postgres + Redis)
- Container restart + verification: 5 min
- BotFather regen + .env update + restart: 15-20 min (mostly Captain-hands-on Telegram tapping)
- Verification + smoke-test: 5-10 min

**Total: 30-45 min if everything goes smoothly, up to 60 min with debug headroom.**

## When NOT to roll back

- Single officer crash on Mac → bootout + bootstrap the individual LaunchAgent; don't roll back the whole fleet.
- Single config bug → fix the config + reload via `reload-officer-mac.sh`; don't roll back.
- Performance question → soak more, gather data, don't roll back on first impression.

Rollback is for **substrate-level failure** that can't be patched in <2 hours on Mac. Bias is to fix forward on Mac.

## Per Spec 065 v1.1 Checkpoint 8.5 + CTO v1.1 #4 (BotFather regen procedure).
