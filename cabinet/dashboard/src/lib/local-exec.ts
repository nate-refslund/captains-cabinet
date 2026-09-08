/**
 * localExec — run a command against the checkout, with NO store-posture gate.
 *
 * WHY THIS EXISTS BESIDE `dockerExec`. That transport refuses whenever the
 * store is not live (`lib/docker.ts`: `CommandNotExecutedError` on demo OR
 * unconfigured), and refusing is right for what it carries: tmux control,
 * officer creation, secret reads — work that has no meaning without a runtime.
 * The store posture is the wrong sensor for a FILE act. Ratifying a proposed
 * card writes two YAML files and appends one ledger line; none of it touches
 * Redis, and an installed Cabinet with no `REDIS_URL` — which is that
 * deployment's NORMAL state — would have the one control the whole no-terminal
 * law exists for throw before it ran.
 *
 * That is the same reasoning `lib/docker.ts` already writes down about the six
 * modules that shell out with no posture gate (crontab, verdicts, evidence,
 * library, onboarding bridge): five of them "shell to the local checkout or a
 * local interpreter and are right to run whether or not Redis is configured".
 * This is the sixth case, given a name instead of a copy of `exec`.
 *
 * WHAT IT IS NOT. It is not a widening of what the dashboard may run: the only
 * callers are this app's own file+ledger acts, every one of them building its
 * argv from a validated id, and none of them accepting a caller-supplied
 * command. A failure REJECTS — the caller's catch is what turns it into an
 * honest error, exactly as it does for the gated transport.
 */

import { execFile as execFileCb } from 'child_process'
import { promisify } from 'util'
import { cabinetRoot } from './cabinet-root'

const execFile = promisify(execFileCb)

/** The interpreter every unlocked cabinet script pins. Never a bare python3:
 *  the officer PATH's python3 is 3.9 on the live deployment. */
export const CABINET_PYTHON = process.env.CABINET_PYTHON || 'python3.12'

export interface LocalExecResult {
  stdout: string
  stderr: string
}

/**
 * Run `argv` in the checkout root. ARGV, never a shell string — there is no
 * shell here to quote for, so an id that slipped a validator still cannot be a
 * command.
 */
export async function localExec(argv: string[]): Promise<LocalExecResult> {
  const [command, ...rest] = argv
  const { stdout, stderr } = await execFile(command, rest, {
    cwd: cabinetRoot(),
    env: { ...process.env, CABINET_ROOT: cabinetRoot() },
    maxBuffer: 1024 * 1024 * 16,
  })
  return { stdout: String(stdout).trim(), stderr: String(stderr).trim() }
}
