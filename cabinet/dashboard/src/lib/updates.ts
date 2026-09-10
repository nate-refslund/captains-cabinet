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


// The shape and the wording live in `updates-view.ts` and are re-exported
// here, so every server-side importer still says `@/lib/updates`. The split is
// not cosmetic: this module imports `child_process`, and the home card is a
// client component — see the header of `updates-view.ts` for the build that
// failed when the two halves were one file.
export * from './updates-view'
import { UPDATER_REL, type UpdateStatus } from './updates-view'

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

