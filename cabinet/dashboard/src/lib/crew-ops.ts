/**
 * THE ONLY TWO THINGS THIS DASHBOARD MAY DO TO launchd.
 *
 * This module exists because the feature it serves — a button on a web page
 * that starts and stops background jobs on the operator's Mac — is exactly the
 * shape of thing that becomes a remote-execution seam the moment it is built
 * as one. So it is not built as one.
 *
 * THE CLOSED TABLE. `OPS` below is the complete set of commands this app can
 * ever run against the fleet: `deploy-mac.sh --officer <slug>` and
 * `deploy-mac.sh --stop <slug>`. Two operations, one script, and the script is
 * resolved from the checkout root — never from input. There is no "run this
 * command" entry point here, no template string, no shell: `execFile` is
 * handed a program and an ARGV ARRAY, so nothing a caller passes can become a
 * new word, a pipe, a redirect or a second command. Widening the allowlist
 * requires editing this table, which is the point — `lib/crew-ops.test.ts`
 * fails if the table grows an entry, so widening it cannot happen quietly.
 *
 * THE ONE INTERPOLATED VALUE is the officer slug, and it is not free text: it
 * comes from `instance/config/roster.yml` (the deployment's own hire record),
 * and it is re-validated HERE against `^[a-z0-9-]{1,64}$` at call time rather
 * than trusted from the caller. Both belts are worn deliberately — the roster
 * is operator-owned config rather than untrusted input, and a future caller
 * that forgets where slugs come from still cannot get a `--force`, a path, or
 * a flag through this door.
 *
 * WHY NOT `dockerExec`. That is a generic `bash -c <string>` transport. Every
 * property above would be lost by reaching the same scripts through it.
 *
 * WHY REUSE `deploy-mac.sh` AT ALL rather than driving launchctl directly: it
 * owns the atomic plist install, the bootout-first idiom that makes a repeat
 * press a no-op instead of `Bootstrap failed: 5`, the per-service rollback,
 * and the consultant guard. Re-implementing any of that in TypeScript would be
 * a second, worse copy of the thing hatch already runs.
 */

import { execFile } from 'node:child_process'
import fs from 'node:fs'
import { promisify } from 'node:util'
import { cabinetPath } from './cabinet-root'

const execFileAsync = promisify(execFile)

/**
 * Officer slugs are launchd label components; keep them boring — and note the
 * FIRST character class, which is the whole point of this being two classes.
 *
 * `^[a-z0-9-]+$` (what this was, until its own adversarial test caught it)
 * accepts `--force`, `--all` and `-officer`, because a hyphen is a permitted
 * slug character and nothing said it could not lead. Every one of those would
 * have been handed to `deploy-mac.sh` as the VALUE of `--officer` or `--stop`.
 * No shell was involved and nothing would have been injected — it is worse
 * than that: they are the script's own flags, so the allowlist would have been
 * widening itself through the one field it interpolates.
 */
export const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,63}$/

/**
 * `all` is `deploy-mac.sh`'s wildcard for BOTH legs, and it is the reason this
 * list exists rather than a comment. `--stop all` boots out every installed
 * `com.cabinet.*` LaunchAgent — the dashboard serving this page included — and
 * `--officer all` deploys the entire roster rather than the one officer named.
 * Neither is an operation this app offers, so neither may be reachable by
 * naming an officer.
 */
export const RESERVED_SLUGS = new Set(['all'])

export type CrewOp = 'wake' | 'sleep'

/**
 * The whole allowlist. `args(slug)` returns the argv AFTER the script path.
 *
 * `--officer <slug>` renders + installs + bootstraps that officer's
 * LaunchAgent (idempotent: it boots the label out first). `--stop <slug>`
 * boots it out and leaves the plist on disk, which is what makes the pair
 * reversible from the same screen.
 */
export const OPS: Record<CrewOp, { args: (slug: string) => string[]; verb: string }> = {
  wake: { args: (slug) => ['--officer', slug], verb: 'start' },
  sleep: { args: (slug) => ['--stop', slug], verb: 'stop' },
}

/**
 * Membership is an OWN-property check, never `OPS[op]` truthiness.
 *
 * `OPS['toString']` and `OPS['__proto__']` both resolve up the prototype chain
 * to something truthy, so a plain `if (!OPS[op])` would wave those two names
 * past the door and then crash on `entry.args`. That is a refusal that never
 * fires — the disabled-sensor shape — on the one gate in this feature that has
 * to hold.
 */
export function isCrewOp(op: string): op is CrewOp {
  return Object.prototype.hasOwnProperty.call(OPS, op)
}

/** The one script this module may run, resolved from the checkout root. */
export function deployScriptPath(): string {
  return cabinetPath('cabinet/scripts/deploy-mac.sh')
}

export class CrewOpRefused extends Error {}

export interface CrewOpResult {
  op: CrewOp
  slug: string
  ok: boolean
  /** The last line of real output — what a person would read in a terminal. */
  detail: string
}

/** Last non-empty line, trimmed and capped: enough to diagnose, never a dump. */
export function lastLine(text: string, cap = 400): string {
  const line =
    text
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(-1)[0] || ''
  return line.length > cap ? line.slice(0, cap - 1) + '…' : line
}

/**
 * Run one allowlisted operation against one officer.
 *
 * Refuses — never runs anything — when the op is not in the table, the slug is
 * not slug-shaped, or the script is not where it should be. A refusal throws
 * `CrewOpRefused`; a script that RAN and failed comes back as `ok: false` with
 * its own words, because those are different facts and the flow says different
 * things about them.
 */
export async function runCrewOp(
  op: CrewOp,
  slug: string,
  timeoutMs = 120_000
): Promise<CrewOpResult> {
  if (!isCrewOp(op)) {
    throw new CrewOpRefused(`not an allowed crew operation: ${String(op)}`)
  }
  const entry = OPS[op]
  if (!SLUG_RE.test(slug) || RESERVED_SLUGS.has(slug)) {
    throw new CrewOpRefused(`not an officer id: ${slug}`)
  }

  const script = deployScriptPath()
  if (!fs.existsSync(script)) {
    throw new CrewOpRefused(
      `this cabinet's deploy script is not where it should be (${script}), so nothing was run`
    )
  }

  const root = cabinetPath()
  try {
    const { stdout, stderr } = await execFileAsync('bash', [script, ...entry.args(slug)], {
      cwd: root,
      timeout: timeoutMs,
      maxBuffer: 1024 * 1024 * 4,
      env: { ...process.env, CABINET_ROOT: root, CABINET_SOURCE_REPO: root },
    })
    return { op, slug, ok: true, detail: lastLine(stdout) || lastLine(stderr) }
  } catch (err) {
    const e = err as { stdout?: string; stderr?: string; message?: string }
    return {
      op,
      slug,
      ok: false,
      detail: lastLine(e.stderr || '') || lastLine(e.stdout || '') || e.message || 'it did not finish',
    }
  }
}
