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
  /** The last refusal the updater recorded, or null. Outlives the phase.
   *
   *  RESOLVED BY `status --json` FROM BOTH CHANNELS. A refusal is written down
   *  twice by one call — `.updates/state.json` and a ledger receipt — and
   *  either half can be the only one that survives (a failed state write, a
   *  truncated or removed file, an emitter one version behind that refuses the
   *  event kind). Round 4 measured the consequence: a locked-path refusal that
   *  had reached only the ledger left this card rendering Apply on a bundle
   *  the box had already turned down. The updater now resolves the two into
   *  ONE record here, so this reader and the briefing cannot be looking at
   *  different facts. */
  last_refusal?: UpdateRefusal | null
  /** Which channel `last_refusal` came from: `state`, `receipt`, or empty when
   *  there is none. Diagnostic — no rendering branches on it — but a state
   *  file that has gone missing is then a fact on the report rather than a
   *  silence, and `cabinet-update.sh status` says so in words. */
  last_refusal_source?: string
  /** THE BUNDLE THIS BOX ALREADY TOOK AND PUT BACK (A5.17.7). Resolved by
   *  `status --json`: the newest record about the waiting bundle is a rollback
   *  FROM it, so it is neither refused nor untried. Apply stays — retrying a
   *  health-gate failure is legitimate — but "Update ready" over it is a
   *  sentence that hides the one fact the Captain would want. Round 5 declared
   *  this a per-surface difference (the briefing said it, this card did not);
   *  the A5.17 gate retired that, and both surfaces now say the same words. */
  waiting_rollback?: { bundle: string; reason: string; ts: string } | null
  /** A timing note: another updater held the lock (A5.17.1). About no bundle,
   *  so never a headline anywhere — `cabinet-update.sh status` says it in
   *  words and this field carries it. */
  last_busy?: { bundle: string; ts: string; door?: string } | null
  /** Non-empty when the durable half of a refusal could not be written
   *  (A5.17.2): named, never swallowed. */
  state_error?: string
  /** A record is held outside the ledger because this install's emitter
   *  does not know the event kind yet (A5.16). */
  event_fallback?: boolean
  /** Non-empty when the ledger did not DECLINE the record but FAILED to take
   *  it — a full disk, a permission. The next update files version skew; it
   *  files none of these, so the two must not read the same on any surface. */
  ledger_error?: string
}

/**
 * The refusal this screen should be speaking about, or null.
 *
 * READS THE ONE RESOLVED `last_refusal` AND NOTHING ELSE. `status --json`
 * resolves every channel a verdict can survive on — the per-bundle marker, the
 * ledger receipt, the legacy state record — and it resolves them ABOUT THE
 * BUNDLE THAT IS WAITING (A5.17.5/6). So the scoping the four rules used to do
 * here is done once, upstream, where the briefing does it too, and neither
 * surface can be looking at a fact about some other bundle.
 *
 * Round 5 measured what the other arrangement costs. The resolver took the
 * newest refusal receipt GLOBALLY: a `busy` note written by a rollback that
 * lost the lock — a record about no bundle at all — blanked the constitutional
 * verdict on the bundle in the inbox, and this card offered Apply on it under
 * a briefing line saying the same thing. Round 4 was card-wrong/briefing-right;
 * that was both wrong, in agreement, which is the worse failure.
 *
 * What is left here is the one rule a resolution cannot carry: an apply IN
 * FLIGHT is the live state, and a refusal recorded before the retry that is
 * running now is a note about a request. Its twin is
 * `run_briefing._refusal_speaks`, and the two are pinned row for row by
 * `framework/frontdoor/tests/update_surface_oracle.json`, which both suites
 * drive — a kind flipped in it reds both.
 */
export function refusalToShow(status: UpdateStatus | null): UpdateRefusal | null {
  if (!status || status.phase === 'applying') return null
  const refusal = status.last_refusal
  if (!refusal || !refusal.bundle) return null
  return refusal
}

/**
 * The bundle the Apply button would take, or null.
 *
 * ONE DEFINITION OF THE GATE, here rather than inline in the card, because it
 * is a contract property with a row of its own in the oracle (`apply_live`) and
 * an inline expression cannot be driven against a table. A constitutional
 * refusal is the one an operator cannot retry into succeeding — those bytes
 * change by a deliberate unlock and relock — and an Apply button there is a
 * button that fails identically every time it is tapped. Every other refusal
 * (a digest mismatch, an unreadable bundle) and a bundle this box rolled back
 * KEEP the button: a retry re-tests, and re-testing is a reasonable thing to
 * do about all three (A5.17.7).
 */
export function applyTarget(status: UpdateStatus | null): AvailableBundle | null {
  if (!status) return null
  const refusal = refusalToShow(status)
  if ((refusal?.paths?.length ?? 0) > 0) return null
  return status.latest ?? null
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
    // A5.17.7 — a bundle this box took and PUT BACK is not a bundle nobody has
    // tried, and the sentence is the briefing's word for word. Apply stays:
    // retrying a health gate that went red is a legitimate thing to do.
    if (status.waiting_rollback) {
      const r = status.waiting_rollback
      return `Update rolled back — ${r.reason || 'it did not come up healthy'}` +
        `; still waiting (${(r.bundle || '').slice(0, 8)})`
    }
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
  // A5.16 — LAST, and only when nothing else has a headline. The card already
  // shows a ledger fault as a sub-line BESIDE whatever it is saying, which is
  // the right shape: it is not the news, it is a fault under the news. But the
  // page renders this card at all only when this function returns non-null
  // (page.tsx), so a fault with an idle phase, nothing waiting and no refusal
  // on record reached no surface on the web door — the one surface a fault
  // must never be lost on, because "the records of what this box did are not
  // being written down" is the sentence nobody goes back to look for.
  if (status.ledger_error) return 'Update records are not reaching the ledger'
  return null
}
