/**
 * Spec 034 PR 5 — POST /api/cabinets/[id]/archive
 *
 * Archive a Cabinet: stop containers, remove peers.yml entries, PRESERVE rows.
 * This is NOT a delete. Data is retained under cabinet_id for future recovery.
 *
 * Hard constraints (per COO 034.5 + COO 034.7):
 *  - Returns 409 Conflict in non-stable states: creating, adopting-bots,
 *    provisioning, starting, archiving, archived
 *  - Requires re-auth via OTU token issued by POST /api/auth/reauth-verify
 *    (PR 5 replaces the legacy confirm_password approach — OTU is one-time-use,
 *    cryptographically random, 5-min TTL, consumed on first use)
 *  - Requires name-type confirmation — body must include `confirm_name`
 *
 * Re-auth flow (PR 5):
 *  1. POST /api/auth/reauth-challenge → { challenge_token }
 *  2. POST /api/auth/reauth-verify { challenge_token, password } → { otu_token }
 *  3. POST /api/cabinets/:id/archive { confirm_name, otu_token }
 *
 * Archive is valid from: active | suspended | failed
 *
 * Atomic peers.yml write (AC 21):
 *  - Worker writes peers.yml.new first, then fs.rename() for atomic swap
 *  - fs.rename() is atomic on POSIX (single filesystem — rename(2) is atomic)
 *  - Full multi-host two-phase commit is Phase 3; documented in code below
 */

import { NextRequest, NextResponse } from 'next/server'
import { requireProvisioningAccess } from '@/lib/provisioning/guard'
import { writeTransitionEvent, writeAuditEvent } from '@/lib/provisioning/audit'
import { ARCHIVE_BLOCKED_STATES, canTransition } from '@/lib/provisioning/state-machine'
import { query, getDbPool } from '@/lib/db'
import redis from '@/lib/redis'
// OTU key helper (inlined here to avoid cross-route import — Next.js route segments
// are not guaranteed to be importable as plain modules at type-check time)
function otuKey(token: string): string {
  return `cabinet:reauth:otu:${token}`
}

export const dynamic = 'force-dynamic'

/** Atomically validate and consume a one-time-use re-auth token. */
async function consumeOtuToken(token: string): Promise<boolean> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const r = redis as any
  try {
    const state = await redis.get(otuKey(token))
    if (state !== 'valid') return false
    // Mark consumed immediately (one-time-use)
    if (typeof r.set === 'function') {
      await r.set(otuKey(token), 'consumed', 'EX', 60)
    } else {
      await redis.set(otuKey(token), 'consumed')
    }
    return true
  } catch (err) {
    console.error('[archive] OTU token validation failed', err)
    return false
  }
}

interface ArchiveBody {
  /** Cabinet name typed by Captain to confirm (must match exactly) */
  confirm_name: string
  /**
   * One-time-use token from POST /api/auth/reauth-verify.
   * Replaces the legacy confirm_password field (PR 5).
   */
  otu_token: string
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const guard = await requireProvisioningAccess()
  if (guard.response) return guard.response

  const { user } = guard
  const { id } = await params

  let body: ArchiveBody
  try {
    body = (await req.json()) as ArchiveBody
  } catch {
    return NextResponse.json({ ok: false, message: 'Invalid JSON body' }, { status: 400 })
  }

  if (!body.confirm_name?.trim()) {
    return NextResponse.json(
      { ok: false, message: 'confirm_name is required (type the Cabinet name to confirm)' },
      { status: 400 }
    )
  }
  if (!body.otu_token) {
    return NextResponse.json(
      { ok: false, message: 'otu_token is required (complete re-authentication via /api/auth/reauth-verify)' },
      { status: 400 }
    )
  }

  // Re-auth check via OTU token (COO 034.7, PR 5 wiring)
  const otuValid = await consumeOtuToken(body.otu_token)
  if (!otuValid) {
    return NextResponse.json(
      { ok: false, message: 'Re-authentication failed — OTU token is invalid, expired, or already used' },
      { status: 401 }
    )
  }

  const pool = getDbPool()
  const client = await pool.connect()
  try {
    await client.query('BEGIN')

    const result = await client.query<{
      captain_id: string
      name: string
      state: string
    }>(
      'SELECT captain_id, name, state FROM cabinets WHERE cabinet_id = $1 FOR UPDATE',
      [id]
    )

    if (result.rows.length === 0) {
      await client.query('ROLLBACK')
      return NextResponse.json({ ok: false, message: 'Cabinet not found' }, { status: 404 })
    }

    const { captain_id, name, state } = result.rows[0]

    // Name-type confirmation (second friction layer)
    if (body.confirm_name.trim() !== name) {
      await client.query('ROLLBACK')
      return NextResponse.json(
        {
          ok: false,
          message: `Cabinet name confirmation mismatch. Expected '${name}', got '${body.confirm_name.trim()}'`,
        },
        { status: 400 }
      )
    }

    // State check: archive blocked in non-stable in-flight states
    if (ARCHIVE_BLOCKED_STATES.includes(state as never)) {
      await client.query('ROLLBACK')
      return NextResponse.json(
        {
          ok: false,
          message: `Archive is not available in '${state}' state. Wait for a stable state (active, suspended, failed) or let the operation complete.`,
        },
        { status: 409 }
      )
    }

    const check = canTransition(state as never, 'archiving')
    if (!check.ok) {
      await client.query('ROLLBACK')
      return NextResponse.json(
        { ok: false, message: `Cannot archive: ${check.reason}` },
        { status: 409 }
      )
    }

    // Transition to archiving
    await client.query(
      `UPDATE cabinets SET state = 'archiving', state_entered_at = now() WHERE cabinet_id = $1`,
      [id]
    )

    await client.query('COMMIT')

    await writeTransitionEvent({
      cabinet_id: id,
      actor: user.token,
      entry_point: 'dashboard',
      from: state as never,
      to: 'archiving',
      payload: { confirm_name: body.confirm_name },
    })

    // Release provisioning lock if held
    const lockKey = `cabinet:provisioning-lock:${captain_id}`
    try {
      await redis.del(lockKey)
    } catch (err) {
      console.warn(`[api/cabinets/${id}/archive] Could not release lock:`, err)
    }

    // Kick off async archival worker
    startArchivalWorker(id, user.token)

    return NextResponse.json({
      ok: true,
      state: 'archiving',
      // WHAT IS ACTUALLY DONE, not what the finished feature will do. The old
      // sentence promised a container stop and a peers.yml removal that are
      // both `console.info` stubs; the Captain read it, the modal closed on
      // success, and the cabinet's entry was still in peers.yml afterwards.
      message:
        'Cabinet marked for archival. The row and its data are preserved. Its containers are NOT stopped and its peers.yml entry is NOT removed yet — do both by hand, or the cabinet stays reachable to its peers.',
    })
  } catch (err) {
    await client.query('ROLLBACK')
    console.error(`[api/cabinets/${id}/archive] POST error`, err)
    return NextResponse.json({ ok: false, message: 'Failed to archive cabinet' }, { status: 500 })
  } finally {
    client.release()
  }
}

// ----------------------------------------------------------------
// Async archival worker — runs fire-and-forget after route returns 200
// ----------------------------------------------------------------

/**
 * Fire-and-forget archival sequence:
 *  1. docker compose stop for Cabinet's officer containers
 *  2. Remove peers.yml entries atomically (write .new, then fs.rename)
 *  3. Transition archiving → archived
 *
 * peers.yml atomic write (AC 21):
 *  On a single host, fs.rename() is atomic (POSIX rename(2) syscall).
 *  Pattern: write peers.yml.new → fsync → rename(peers.yml.new, peers.yml)
 *  The old file is never corrupted — either old or new, never mid-write.
 *
 *  Phase 3 multi-host two-phase commit: when Cabinets live on separate hosts,
 *  this rename-RPC is coordinated via Cabinet MCP transport. Phase 1 writes
 *  both sides with consented_by_captain: false; Phase 2 flips both to true
 *  via a two-phase RPC round-trip. That is Phase 3 scope — not implemented here.
 */
function startArchivalWorker(cabinetId: string, actor: string): void {
  Promise.resolve()
    .then(() => runArchivalSteps(cabinetId, actor))
    .catch((err) => {
      console.error(`[archive-worker] Unhandled error for ${cabinetId}:`, err)
    })
}

/**
 * THE TWO STEPS THAT ARE NOT IMPLEMENTED, NAMED IN THE AUDIT TRAIL.
 *
 * `runArchivalSteps` used to `console.info` "would stop containers (stub)" and
 * "would remove peers.yml entry (atomic rename stub)", move the row to the
 * terminal `archived` state, and write an audit row whose payload asserted
 *
 *     peers_yml_atomic: true
 *     note: 'Atomic rename pattern (POSIX rename(2)). …'
 *
 * for a write that never happened. An audit trail recording an ATOMICITY
 * GUARANTEE for an operation nothing performed is worse than no audit trail:
 * it is the one surface that is supposed to be re-readable later as evidence,
 * and it was the most confident thing in the system about the least real thing.
 * Reproduced against the route: `instance/config/peers.yml` byte-identical, the
 * cabinet's entry still in it, the row `archived`, and the caller told
 * "Containers will stop and peers.yml entries will be removed".
 *
 * The honest shape, with no schema and no response-contract change: the state
 * still moves (the Captain asked for the archival and the row IS archived), but
 * the payload records what was NOT done instead of certifying what was, and the
 * unperformed steps are enumerated rather than described in a comment. When
 * they are implemented, this constant empties and the payload says so on its
 * own — the row cannot go quiet while the work is still missing.
 */
const UNPERFORMED_ARCHIVAL_STEPS = [
  'stop the containers (docker compose -p <cabinet> stop)',
  'remove the cabinet entry from instance/config/peers.yml',
] as const

// Exported so the honesty arm in `lib/unperformed-work.test.ts` drives the
// REAL worker rather than a copy of it — the existing route test asserts only
// that the 200 came back, and stayed green when both archival steps were
// replaced by throws and again when the worker call was deleted outright.
export async function runArchivalSteps(cabinetId: string, actor: string): Promise<void> {
  try {
    // NOT DONE. Kept as one list so the audit row below and this code cannot
    // drift apart — the previous version described the unwritten rename in a
    // comment and asserted it as a fact in the payload.
    console.warn(
      `[archive-worker] ${cabinetId}: NOT performed — ${UNPERFORMED_ARCHIVAL_STEPS.join('; ')}`
    )

    await query(
      `UPDATE cabinets SET state = 'archived', state_entered_at = now() WHERE cabinet_id = $1 AND state = 'archiving'`,
      [cabinetId]
    )

    await writeTransitionEvent({
      cabinet_id: cabinetId,
      actor,
      entry_point: 'worker',
      from: 'archiving',
      to: 'archived',
      payload: {
        // No `peers_yml_atomic`. The field asserted a durability property of a
        // write that did not occur; a reader of this row now learns the
        // opposite, which is the true thing.
        unperformed: UNPERFORMED_ARCHIVAL_STEPS,
        note:
          'Row state only. The container stop and the peers.yml removal are not implemented, ' +
          'so this cabinet may still be running and is still listed to its peers.',
      },
    })

    console.info(`[archive-worker] ${cabinetId}: row archived (steps above still outstanding)`)
  } catch (err) {
    console.error(`[archive-worker] ${cabinetId}: archival failed`, err)
    // Best-effort: mark failed so Captain can see the problem
    try {
      await query(
        `UPDATE cabinets SET state = 'failed', state_entered_at = now() WHERE cabinet_id = $1 AND state = 'archiving'`,
        [cabinetId]
      )
      await writeAuditEvent({
        cabinet_id: cabinetId,
        actor,
        entry_point: 'worker',
        event_type: 'error',
        state_before: 'archiving',
        state_after: null,
        error: String(err),
      })
    } catch (markErr) {
      console.error(`[archive-worker] Could not mark ${cabinetId} failed:`, markErr)
    }
  }
}
