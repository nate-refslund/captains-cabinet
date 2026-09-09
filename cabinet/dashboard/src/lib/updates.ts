/**
 * updates.ts — the dashboard's read side of the update path, plus the ONE
 * exec seam the update actions are allowed to use.
 *
 * WHY THIS MODULE EXISTS AT ALL. An installed Cabinet is an unpacked export
 * with no version control in it. `cabinet/scripts/cabinet-update.sh` is the
 * only thing on the box that knows whether better bytes are waiting, and until
 * this module existed nothing on the web door could ask it. The Captain's
 * whole update path was a terminal, which is the door of last resort.
 *
 * WHY IT DOES NOT USE `dockerExec`. That helper is gated on store posture and
 * REJECTS when the store is not live (lib/docker.ts — an absent `REDIS_URL`,
 * which is an installed single-worker Cabinet's normal state). Taking an
 * update is a file-and-ledger act with no store in it, so routing it through a
 * store gate would mean the one deployment shape this leg exists for is the
 * one that cannot update itself. This module therefore carries a plain exec
 * seam of its own — narrow on purpose: a fixed argv, a fixed script, cwd at
 * the cabinet root, and no shell string anywhere.
 *
 * READ-ONLY except `spawnUpdater`, which is the detached launch the actions
 * use. It is here rather than in the action module so a test can replace the
 * seam instead of the process table.
 */

import { execFile, spawn } from 'child_process'
import { promisify } from 'util'
import { cabinetRoot } from './cabinet-root'

const execFileAsync = promisify(execFile)

/** The updater, resolved against the running checkout. */
export const UPDATER_REL = 'cabinet/scripts/cabinet-update.sh'

/** A bundle id is the source commit it was cut from — hex, nothing else. */
export const BUNDLE_SHA_RE = /^[0-9a-f]{7,64}$/

/** A snapshot stamp is `<utc>-<sha>`; the CLI validates it too. */
export const SNAPSHOT_STAMP_RE = /^[0-9A-Za-z_-]{1,128}$/

export interface AvailableBundle {
  sha: string
  short: string
  built_at: string
  from_sha: string | null
  file_count: number
  changelog: string[]
  owner: string
  mtime: string
}

/**
 * A refusal, as the updater wrote it down (A5.15).
 *
 * `paths` is the load-bearing field: "refused" on its own cannot be turned
 * into a sentence anyone can act on, and what a constitutional refusal needs
 * is a person deciding about NAMED files. It is empty for the refusals that
 * are not about the constitutional set at all — a digest mismatch, an
 * unreadable bundle, a second updater already running.
 */
export interface UpdateRefusal {
  bundle: string
  reason: string
  paths: string[]
  ts: string
  door?: string
}

export interface UpdateState {
  phase?: string
  from_sha?: string
  to_sha?: string
  changed?: number
  deleted?: number
  reason?: string
  finished_at?: string
  started_at?: string
  snapshot?: string
  door?: string
  skipped_preserved?: string[]
  bundle?: string
  paths?: string[]
  ts?: string
  last_refusal?: UpdateRefusal
  event_fallback?: boolean
  ledger_error?: string
}

export interface UpdateStatus {
  installed_sha: string
  installed_short: string
  phase: string
  last: UpdateState | null
  available: AvailableBundle[]
  latest: AvailableBundle | null
  snapshots: string[]
  /** The last refusal the updater recorded, or null. Outlives the phase. */
  last_refusal?: UpdateRefusal | null
  /** A record is held outside the ledger because this install's emitter
   *  does not know the event kind yet (A5.16). */
  event_fallback?: boolean
  /** Non-empty when the ledger did not DECLINE the record but FAILED to take
   *  it — a full disk, a permission. The next update files version skew; it
   *  files none of these, so the two must not read the same on any surface. */
  ledger_error?: string
}

/**
 * A refusal is timing, or it is a verdict about the bundle.
 *
 * `busy` means another updater held the lock — it says nothing about these
 * bytes, so it must not stick to them and turn a perfectly applicable bundle
 * into one the card refuses to offer. Every other refusal IS about the bundle
 * and follows it until something changes.
 */
function refusalIsAboutTheBundle(refusal: UpdateRefusal): boolean {
  return refusal.reason !== 'busy'
}

/**
 * The refusal this screen should be speaking about, or null.
 *
 * Shared by the headline and the card so the two cannot disagree — a card
 * naming files under a headline that says "Update ready" is worse than either
 * on its own. An apply in flight outranks it: that is the live state, and a
 * busy refusal recorded a second ago is a note about a request, not about what
 * the box is doing now.
 *
 * SCOPED TO THE SHA, and `phase` is not part of the scope. Round 1 returned
 * early on `phase === 'refused'`, which reads as harmless and is not: nothing
 * moves that phase except a later apply, so after ONE constitutional refusal
 * the card showed that refusal's headline and files over every bundle that
 * arrived afterwards and withdrew Apply with them — and Apply is the only
 * no-terminal way to take the update that would have cleared the phase. The
 * door this whole leg exists to open, bricked by the record of one refusal.
 * The same three rules are `run_briefing._update_refusal_line`, deliberately:
 * two surfaces reading one state file must not be able to disagree. Round 2
 * WROTE that claim with only two of the three actually mirrored — the briefing
 * had no `applying` guard at all — so through every retry of a digest-mismatch
 * or busy refusal (the two this card deliberately keeps Apply for) the card
 * said "Taking an update" while the briefing said "Update refused", and an
 * interrupted apply made that disagreement durable. It is no longer only a
 * claim: the six states the two surfaces must agree on are one checked-in
 * fixture, `framework/frontdoor/tests/update_surface_parity.json`, driven
 * through BOTH readers — the parity block in `updates.test.ts` and its twin in
 * `framework/frontdoor/tests/test_card_update_notice.py`. Change one side's
 * ranking and the other side's suite is what goes red.
 */
export function refusalToShow(status: UpdateStatus | null): UpdateRefusal | null {
  if (!status || status.phase === 'applying') return null
  const refusal = status.last_refusal
  if (!refusal || !refusal.bundle) return null
  // Nothing is waiting, so there is no other sentence for this to be wrong
  // about: the last thing that happened is still the last thing that happened.
  if (!status.latest) return refusal
  // Something IS waiting. It speaks only about the bundle it is a verdict on:
  // offering a refused bundle as "ready" is a button that cannot work, and
  // refusing one nobody has judged is a button withdrawn for no reason.
  if (status.latest.sha === refusal.bundle && refusalIsAboutTheBundle(refusal)) {
    return refusal
  }
  return null
}

/** The one sentence a refusal becomes. Counts, never a changelog line. */
export function refusalHeadline(refusal: UpdateRefusal): string {
  const short = (refusal.bundle || '').slice(0, 8)
  const n = refusal.paths?.length ?? 0
  if (n > 0) {
    return `Update refused — ${n} constitutional file${n === 1 ? '' : 's'} ` +
      `differ${n === 1 ? 's' : ''}; needs the Captain (${short})`
  }
  return `Update refused — ${refusal.reason || 'the updater would not take it'} (${short})`
}

/**
 * Run the updater with a fixed argv and return its stdout.
 *
 * Exported so the actions can share one seam; `shell` is never used, so a
 * bundle id that got past the regex still cannot become a command.
 */
export async function runUpdateCli(args: string[]): Promise<string> {
  const { stdout } = await execFileAsync('bash', [UPDATER_REL, ...args], {
    cwd: cabinetRoot(),
    maxBuffer: 8 * 1024 * 1024,
  })
  return stdout
}

/**
 * Launch the updater DETACHED and return immediately.
 *
 * The updater restarts the dashboard — that is, the process calling this — so
 * it must outlive its caller. It re-execs itself into `<root>/.updates/run/`
 * under a new session before its first write; `detached` here is the other
 * half of the same property, so the handoff never depends on the action's
 * request finishing first.
 */
export function spawnUpdater(args: string[]): void {
  const child = spawn('bash', [UPDATER_REL, ...args], {
    cwd: cabinetRoot(),
    detached: true,
    stdio: 'ignore',
  })
  child.unref()
}

/**
 * What is installed and what is waiting.
 *
 * NEVER throws: the home card renders on a box with no updater at all (every
 * install that predates this leg), and a card that 500s the whole page because
 * a script is absent is worse than a card that says nothing is waiting. `null`
 * means "could not ask", which the card renders as silence rather than as
 * "you are up to date" — the degenerate answer this return type exists to keep
 * off the Captain's screen.
 */
export async function getUpdateStatus(): Promise<UpdateStatus | null> {
  try {
    const stdout = await runUpdateCli(['status', '--json'])
    if (!stdout) return null
    const parsed = JSON.parse(stdout)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    const status = parsed as UpdateStatus
    if (!Array.isArray(status.available)) return null
    return status
  } catch {
    return null
  }
}

/**
 * The one line the home card shows, or null when there is nothing to say.
 *
 * Pure, so the wording is testable without a process: an apply in flight, a
 * refusal, an update waiting, one that rolled itself back, one that landed —
 * in that order. A waiting bundle leads the last three because it is the only
 * one of them the Captain can act on; a refusal leads it in turn because the
 * bundle waiting is usually the one that was refused, and offering it again is
 * a button that cannot work.
 */
export function updateHeadline(status: UpdateStatus | null): string | null {
  if (!status) return null
  if (status.phase === 'applying') {
    const to = (status.last?.to_sha || '').slice(0, 8)
    return `Taking an update${to ? ` to ${to}` : ''} — this page restarts when it lands`
  }
  // A refusal comes BEFORE the waiting bundle, because the waiting bundle is
  // usually the one that was refused: "Update ready" over a bundle the updater
  // has already turned down is a screen that lies once per refusal, for ever.
  const refusal = refusalToShow(status)
  if (refusal) return refusalHeadline(refusal)
  if (status.latest) {
    const n = status.latest.file_count
    return `Update ready — ${n} file${n === 1 ? '' : 's'} changed (${status.latest.short})`
  }
  if (status.phase === 'rolled_back') {
    const to = (status.last?.to_sha || '').slice(0, 8)
    return `An update was rolled back${to ? ` to ${to}` : ''}${
      status.last?.reason ? `: ${status.last.reason}` : ''
    }`
  }
  if (status.phase === 'applied' && status.last?.to_sha) {
    const n = status.last.changed ?? 0
    return `Updated to ${status.last.to_sha.slice(0, 8)}: ${n} change${n === 1 ? '' : 's'}`
  }
  return null
}
