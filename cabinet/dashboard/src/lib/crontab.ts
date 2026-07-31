/**
 * THE MACHINE'S SCHEDULE — read it, change it in memory, write it whole, and
 * prove what landed.
 *
 * WHY THIS FILE EXISTS. `actions/crons.ts` edited the watchdog's crontab with
 * three shell pipelines built by string interpolation:
 *
 *     crontab -l | sed "s|^<schedule>.*<command>.*|<new>|" | crontab -
 *     (crontab -l; echo "<comment>"; echo "<line>")        | crontab -
 *     crontab -l | grep -v "^<schedule>.*"                 | crontab -
 *
 * and returned `{ success: true }` from having ISSUED them. A pipeline's exit
 * status is its LAST stage's, so every one of these reports success from
 * `crontab -`, which cannot fail on input it was handed. MEASURED against the
 * real handlers, a real /bin/sh and a real crontab(1) stand-in (2026-07-31,
 * photographs in the meta workspace under
 * `designs/crons-false-success-2026-07-31/`):
 *
 *   `crontab -l` fails (permissions, spool gone)  → pipeline exits 0 having
 *       piped NOTHING into `crontab -`. The dashboard showed 3 scheduled jobs
 *       before the edit and "0 jobs" after it. THE ENTIRE SCHEDULE WAS
 *       DESTROYED and the Captain was told the edit saved.
 *   `sed` matches nothing (any drift in schedule or command text) → exit 0,
 *       crontab byte-identical, "saved".
 *   `crontab -` accepts the write and keeps the old content (read-only spool,
 *       full disk, a line cron rejects) → exit 0, "saved".
 *   delete → `grep -v "^<schedule>.*"` ignores the command entirely, so
 *       deleting the 06:00 briefing also deleted the 06:00 backup nobody
 *       mentioned. Reported success.
 *
 * That is the emergency-stop defect (PR #330: "returned success from having
 * ISSUED a command it never confirmed") on the surface that decides when every
 * scheduled thing on the machine runs.
 *
 * A READ-BACK ALONE WOULD NOT HAVE BEEN ENOUGH, which is why this module is a
 * plane and not three extra lines in the action. A read-back tells you
 * AFTERWARDS that you destroyed the schedule. The pipelines had to go:
 *
 *   - the whole crontab is read FIRST, and a failed read is a refusal to write,
 *     not an empty input to write from. This is the single change that turns
 *     the destructive case into an error message.
 *   - the transform runs in TypeScript over an array of lines. No `sed`, no
 *     `grep`, no delimiter to collide with, no BRE metacharacter to escape (the
 *     old code escaped for JavaScript's regex dialect and fed the result to
 *     sed, where `\|` is GNU alternation and `\+` a quantifier), and no shell
 *     to interpolate a `$(...)` from a form field into.
 *   - the new crontab is handed to `crontab -` on stdin as ONE document.
 *     crontab(1) validates it and installs it atomically or refuses it whole;
 *     there is no half-written state to be surprised by.
 *   - THEN the read-back, and on mismatch the pre-image is restored and the
 *     restore is itself verified. See `commitCrontab` for why the backup is
 *     worth keeping even though the write is atomic.
 *
 * Everything above the I/O boundary is pure and takes text in, text out, so the
 * degenerate ends — an empty crontab, no matching line, the same line twice, a
 * crontab that is only comments — are testable without a machine.
 */
import { spawn } from 'node:child_process'

// ---------------------------------------------------------------------------
// The I/O boundary
// ---------------------------------------------------------------------------

export type CrontabRead =
  | { ok: true; text: string }
  | { ok: false; reason: string }

export type CrontabWrite = { ok: true } | { ok: false; reason: string }

/**
 * Everything this module needs from a crontab. Injected, so every arm below can
 * be driven without a container — and so the tests exercise THIS interface
 * rather than a twin of it.
 */
export interface CrontabIO {
  read(): Promise<CrontabRead>
  write(text: string): Promise<CrontabWrite>
  /** The exact command a human can run to see the same thing. Printed in errors. */
  describe(): string
}

/**
 * Ten seconds, then the child is killed and the call fails.
 *
 * An unbounded `docker exec` against a wedged daemon is a request that never
 * returns and a page that never renders — the shape `lib/store-reachability.ts`
 * was written for on the store side. A bound that fires is an error; no bound
 * is a hang, and a hang is the one failure the Captain cannot read.
 */
export const EXEC_TIMEOUT_MS = 10_000

interface RunResult {
  code: number | null
  stdout: string
  stderr: string
  spawnError?: string
  timedOut?: boolean
}

function run(
  cmd: string,
  args: string[],
  stdin?: string,
  timeoutMs = EXEC_TIMEOUT_MS
): Promise<RunResult> {
  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>
    try {
      child = spawn(cmd, args, { stdio: ['pipe', 'pipe', 'pipe'] })
    } catch (err) {
      resolve({
        code: null,
        stdout: '',
        stderr: '',
        spawnError: err instanceof Error ? err.message : String(err),
      })
      return
    }
    let stdout = ''
    let stderr = ''
    let done = false
    const timer = setTimeout(() => {
      if (!done) {
        done = true
        child.kill('SIGKILL')
        resolve({ code: null, stdout, stderr, timedOut: true })
      }
    }, timeoutMs)
    child.stdout?.on('data', (d) => (stdout += String(d)))
    child.stderr?.on('data', (d) => (stderr += String(d)))
    child.on('error', (err) => {
      if (done) return
      done = true
      clearTimeout(timer)
      resolve({ code: null, stdout, stderr, spawnError: err.message })
    })
    child.on('close', (code) => {
      if (done) return
      done = true
      clearTimeout(timer)
      resolve({ code, stdout, stderr })
    })
    if (stdin !== undefined) {
      child.stdin?.on('error', () => {})
      child.stdin?.end(stdin)
    } else {
      child.stdin?.end()
    }
  })
}

/**
 * "No crontab for <user>" is an EMPTY crontab, not a failed read — and telling
 * them apart is the whole difference between adding the first job and being
 * refused, so it is matched narrowly and everything else is a failure.
 *
 * Fail-closed on purpose: a crontab implementation whose empty-state message we
 * do not recognise gets treated as unreadable, and an unreadable crontab is
 * never written over. The cost is an error the Captain can act on; the cost of
 * the other default is the schedule this module exists to stop losing.
 */
const NO_CRONTAB = /no crontab for/i

function describeFailure(r: RunResult, what: string): string {
  if (r.spawnError) return `${what} could not be started: ${r.spawnError}`
  if (r.timedOut) return `${what} did not finish within ${EXEC_TIMEOUT_MS / 1000}s`
  const detail = r.stderr.trim() || r.stdout.trim() || `exit status ${r.code}`
  return `${what} failed: ${detail}`
}

/** The watchdog container's crontab, over `docker exec`. No shell involved. */
export function watchdogCrontabIO(container: string): CrontabIO {
  return {
    describe: () => `docker exec ${container} crontab -l`,
    async read(): Promise<CrontabRead> {
      const r = await run('docker', ['exec', container, 'crontab', '-l'])
      if (r.code === 0) return { ok: true, text: r.stdout }
      if (r.code === 1 && NO_CRONTAB.test(r.stderr)) return { ok: true, text: '' }
      return { ok: false, reason: describeFailure(r, `\`crontab -l\` in ${container}`) }
    },
    async write(text: string): Promise<CrontabWrite> {
      // -i so the child gets a stdin to read the document from.
      const r = await run('docker', ['exec', '-i', container, 'crontab', '-'], text)
      if (r.code === 0) return { ok: true }
      return { ok: false, reason: describeFailure(r, `\`crontab -\` in ${container}`) }
    },
  }
}

// ---------------------------------------------------------------------------
// Pure transforms
// ---------------------------------------------------------------------------

/** A crontab line that schedules something (not blank, not a comment). */
export interface JobLine {
  index: number
  schedule: string
  /** Everything after the five schedule fields, whitespace-normalised. */
  command: string
}

const norm = (s: string) => s.trim().replace(/\s+/g, ' ')

/** Split into raw lines WITHOUT losing a trailing newline's meaning. */
function splitLines(text: string): string[] {
  const t = text.replace(/\r\n/g, '\n')
  const lines = t.split('\n')
  // A trailing newline yields a final empty element; drop it so joins are clean.
  if (lines.length && lines[lines.length - 1] === '') lines.pop()
  return lines
}

function joinLines(lines: string[]): string {
  return lines.length ? lines.join('\n') + '\n' : ''
}

/**
 * Every schedulable line, parsed the same way `lib/docker.ts:getCronSchedule`
 * parses them for the table — five fields then the rest.
 *
 * Deliberately NOT a cron-expression parser: the table's rows and this module's
 * matching have to agree, and the way to guarantee that is to split identically
 * rather than to be independently clever.
 */
export function jobLines(text: string): JobLine[] {
  const out: JobLine[] = []
  splitLines(text).forEach((raw, index) => {
    const t = raw.trim()
    if (!t || t.startsWith('#')) return
    const parts = t.split(/\s+/)
    if (parts.length < 6) return // not a job line: an env assignment, or junk
    out.push({
      index,
      schedule: parts.slice(0, 5).join(' '),
      command: parts.slice(5).join(' '),
    })
  })
  return out
}

/**
 * Lines matching a schedule AND a command — both, always.
 *
 * The old delete matched `^<schedule>.*` and dropped every job sharing that
 * minute. Matching is exact on both fields (after whitespace normalisation)
 * because the caller's values came from parsing THIS crontab in the first
 * place: the row on screen round-trips. A looser match would buy nothing and
 * would re-open the collateral-deletion the exactness is here to close.
 */
export function matchJobs(text: string, schedule: string, command: string): JobLine[] {
  const s = norm(schedule)
  const c = norm(command)
  return jobLines(text).filter((j) => j.schedule === s && j.command === c)
}

export type Applied =
  | { ok: true; text: string; matched: number; intent: Intent }
  | { ok: false; reason: string }

/** What the write is supposed to have achieved, checkable against the read-back. */
export interface Intent {
  kind: 'present' | 'absent'
  schedule: string
  command: string
}

export const CRON_LOG_SUFFIX = '>> /var/log/watchdog/cron.log 2>&1'

/** 5 fields, none empty. The action validates too; this is the last gate before a write. */
export function validateSchedule(schedule: string): string | null {
  const parts = schedule.trim().split(/\s+/).filter(Boolean)
  if (parts.length !== 5) {
    return 'Cron expression must have exactly 5 fields (minute hour day month weekday)'
  }
  return null
}

/**
 * A command may not contain a newline. Everything else about it is cron's
 * business, not ours — but a newline would smuggle a SECOND crontab line in
 * through a single-line form field, which is the one thing the in-memory
 * transform cannot represent honestly.
 */
export function validateCommand(command: string): string | null {
  if (!command.trim()) return 'Command is required'
  if (/[\r\n]/.test(command)) return 'Command may not contain a line break'
  return null
}

export function applyUpdate(
  text: string,
  args: { originalSchedule: string; command: string; newSchedule: string }
): Applied {
  const bad = validateSchedule(args.newSchedule) || validateCommand(args.command)
  if (bad) return { ok: false, reason: bad }
  const hits = matchJobs(text, args.originalSchedule, args.command)
  if (hits.length === 0) {
    return {
      ok: false,
      reason: `no line in the crontab reads "${norm(args.originalSchedule)} ${norm(
        args.command
      )}" — nothing was changed. The schedule may have been edited elsewhere; reload the page.`,
    }
  }
  const lines = splitLines(text)
  const target = hits[0]
  const raw = lines[target.index]
  const indent = raw.match(/^\s*/)?.[0] ?? ''
  lines[target.index] = `${indent}${norm(args.newSchedule)} ${target.command}`
  const next = joinLines(lines)
  if (next === text) {
    return { ok: false, reason: 'that is already the schedule — nothing to change' }
  }
  return {
    ok: true,
    text: next,
    matched: hits.length,
    intent: { kind: 'present', schedule: norm(args.newSchedule), command: target.command },
  }
}

export function applyAdd(
  text: string,
  args: { schedule: string; command: string; description?: string }
): Applied {
  const bad = validateSchedule(args.schedule) || validateCommand(args.command)
  if (bad) return { ok: false, reason: bad }
  const command = `${norm(args.command)} ${CRON_LOG_SUFFIX}`
  const schedule = norm(args.schedule)
  if (matchJobs(text, schedule, command).length > 0) {
    return {
      ok: false,
      reason: `that job is already scheduled — "${schedule} ${command}" is in the crontab`,
    }
  }
  const lines = splitLines(text)
  // A description may not smuggle in a line break either; it becomes a comment.
  const description = (args.description || '').replace(/[\r\n]+/g, ' ').trim()
  if (description) lines.push(`# ${description}`)
  lines.push(`${schedule} ${command}`)
  return {
    ok: true,
    text: joinLines(lines),
    matched: 0,
    intent: { kind: 'present', schedule, command },
  }
}

export function applyDelete(
  text: string,
  args: { schedule: string; command: string }
): Applied {
  const hits = matchJobs(text, args.schedule, args.command)
  if (hits.length === 0) {
    return {
      ok: false,
      reason: `no line in the crontab reads "${norm(args.schedule)} ${norm(
        args.command
      )}" — nothing was deleted. It may already be gone; reload the page.`,
    }
  }
  // ONE line, even when the same job is scheduled twice: the table draws one row
  // per line, so one click removes one row and a second click removes the next.
  // Comment lines are left alone — a comment can head a whole section, and
  // guessing which ones belong to this job would delete text nobody named.
  const lines = splitLines(text)
  lines.splice(hits[0].index, 1)
  return {
    ok: true,
    text: joinLines(lines),
    matched: hits.length,
    intent: { kind: 'absent', schedule: norm(args.schedule), command: norm(args.command) },
  }
}

// ---------------------------------------------------------------------------
// The verified commit
// ---------------------------------------------------------------------------

export type CommitResult =
  | { ok: true; matched: number }
  | { ok: false; error: string }

const RELOAD_HINT = 'Reload the page to see what the schedule actually says.'

/**
 * Read → transform → write → PROVE, and put the old crontab back if the proof
 * fails.
 *
 * WHY THE BACKUP-AND-RESTORE IS HERE EVEN THOUGH `crontab -` IS ATOMIC. The
 * atomicity is a property of the crontab implementation, not a property this
 * code can check, and "the implementation is atomic" is exactly the kind of
 * assumption this whole defect class is made of. The pre-image costs one string
 * we are already holding; the restore costs one write on a path that is already
 * failing. When the read-back disagrees, one of two things is true — the write
 * did not land (restore is a no-op) or it landed as something we did not intend
 * (restore is the only way back) — and neither is distinguishable from here.
 *
 * The restore is itself verified, and when it cannot be verified the error says
 * so in those words rather than claiming a rollback. A rollback that reports
 * success without proof would be this same defect, one level down.
 */
export async function commitCrontab(
  io: CrontabIO,
  transform: (text: string) => Applied
): Promise<CommitResult> {
  const before = await io.read()
  if (!before.ok) {
    // THE destructive case. The old pipeline piped an empty read into
    // `crontab -` and wiped the schedule while exiting 0.
    return {
      ok: false,
      error: `the schedule could not be read, so nothing was changed — ${before.reason}. Check it with: ${io.describe()}`,
    }
  }

  const applied = transform(before.text)
  if (!applied.ok) return { ok: false, error: applied.reason }

  const written = await io.write(applied.text)
  if (!written.ok) {
    // The write was refused. Verify the schedule is still the one we read,
    // because "refused" is a claim too.
    const check = await io.read()
    if (check.ok && check.text === before.text) {
      return { ok: false, error: `the schedule was not changed — ${written.reason}` }
    }
    return {
      ok: false,
      error: `the write was refused (${written.reason}) AND the schedule can no longer be confirmed unchanged. Inspect it now: ${io.describe()}`,
    }
  }

  const after = await io.read()
  if (!after.ok) {
    return {
      ok: false,
      error: `the change was written but could not be verified — ${after.reason}. ${RELOAD_HINT} Inspect it with: ${io.describe()}`,
    }
  }

  if (after.text === applied.text && intentHolds(after.text, applied.intent)) {
    return { ok: true, matched: applied.matched }
  }

  // It did not take. Put back exactly what was there and prove that landed.
  const mismatch = describeMismatch(after.text, applied)
  const restore = await io.write(before.text)
  const restored = restore.ok ? await io.read() : null
  if (restored?.ok && restored.text === before.text) {
    return {
      ok: false,
      error: `the schedule did not take — ${mismatch}. Your previous schedule has been restored and verified.`,
    }
  }
  // Nothing here may claim a rollback it cannot show.
  console.error(
    '[crons] crontab is in an UNVERIFIED state; the pre-change content was:\n' +
      before.text
  )
  return {
    ok: false,
    error: `the schedule did not take — ${mismatch} — and putting the old one back could not be confirmed${
      restore.ok ? '' : ` (${restore.reason})`
    }. The crontab is in an UNKNOWN state: inspect it now with ${io.describe()} (the previous content was written to the dashboard's server log).`,
  }
}

function intentHolds(text: string, intent: Intent): boolean {
  const found = matchJobs(text, intent.schedule, intent.command).length
  return intent.kind === 'present' ? found > 0 : found === 0
}

function describeMismatch(after: string, applied: { text: string; intent: Intent }): string {
  const want = applied.intent
  const found = matchJobs(after, want.schedule, want.command).length
  if (want.kind === 'present' && found === 0) {
    return `"${want.schedule} ${want.command}" is not in the crontab after writing it`
  }
  if (want.kind === 'absent' && found > 0) {
    return `"${want.schedule} ${want.command}" is still in the crontab after deleting it`
  }
  const a = jobLines(after).length
  const b = jobLines(applied.text).length
  return `the crontab now holds ${a} scheduled job${a === 1 ? '' : 's'}, not the ${b} that were written`
}
