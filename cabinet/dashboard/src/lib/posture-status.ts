/**
 * WHAT YOUR CABINET IS ALLOWED TO DO — read from the one resolver, said in
 * plain words.
 *
 * WHY IT MOVED HERE. `/posture` rendered this JSON for an audience that
 * already knows what `earn_up` means. The wake flow needs the same reading for
 * an audience that does not: before an operator agrees to start agents on
 * their own Mac, they are owed a sentence about what those agents may do
 * without asking — and it has to be the REAL setting, not a reassuring
 * paragraph somebody wrote once.
 *
 * ONE RESOLVER, NEVER A SECOND OPINION. `cabinet/scripts/posture-status.py`
 * shells into `framework/authority/posture.py` — the same chain the runtime
 * itself obeys. Nothing here re-derives a level from config files; a surface
 * that computed its own answer could disagree with the enforcement plane, and
 * a consent screen that overstates the limits is worse than no consent screen.
 *
 * FAIL-CLOSED, AND SAYING SO. `guardian` is the resolver's answer to every
 * ambiguity, so an unreadable probe reports guardian AND reports that it could
 * not read — the caller renders both. A quiet fallback would be this app
 * claiming a permission level it never measured.
 */

import { execFile } from 'node:child_process'
import path from 'node:path'
import { promisify } from 'node:util'
import { cabinetRoot } from './cabinet-root'

const execFileAsync = promisify(execFile)

export interface PostureStatus {
  level: string
  flavor: string | null
  target: string | null
  attested: boolean
  narrow_cap: string | null
  error?: string
}

/**
 * One sentence per level, written for somebody deciding whether to switch this
 * on. Each is a plain-word statement of the level's own static table:
 *   earn_up   — everything below the ceilings is propose-only;
 *   guardian  — trust-first rows may act day one, with an undo and a receipt;
 *   sovereign — reversible work runs, and tells you after.
 */
export const POSTURE_IN_PLAIN_WORDS: Record<string, string> = {
  earn_up: 'It proposes everything and waits for your yes before it acts.',
  guardian:
    'It can do small, reversible things on its own — each one leaves a receipt you can undo — and asks you first for anything else.',
  sovereign:
    'It gets on with reversible work and tells you afterwards; anything with real consequences still waits for your yes.',
}

/**
 * True in EVERY posture — the external-comms ceiling is structurally
 * non-grantable, so no level makes this sentence false.
 */
export const POSTURE_ALWAYS = 'Nothing goes to anyone outside your org without your approval.'

export function postureSentence(status: PostureStatus): string {
  return POSTURE_IN_PLAIN_WORDS[status.level] ?? POSTURE_IN_PLAIN_WORDS.guardian
}

/** The fail-closed shape, with the reason attached. */
export function guardianFallback(reason: string): PostureStatus {
  return {
    level: 'guardian',
    flavor: null,
    target: null,
    attested: false,
    narrow_cap: null,
    error: reason,
  }
}

export async function readPosture(): Promise<PostureStatus> {
  // Fixed script path under the checkout root — no request input reaches exec.
  const root = cabinetRoot()
  const script = path.join(root, 'cabinet', 'scripts', 'posture-status.py')
  try {
    const { stdout } = await execFileAsync('python3', [script], {
      timeout: 10_000,
      env: { ...process.env, CABINET_ROOT: root },
    })
    return JSON.parse(stdout) as PostureStatus
  } catch (err) {
    return guardianFallback(
      err instanceof Error ? err.message : 'posture-status.py unavailable'
    )
  }
}
