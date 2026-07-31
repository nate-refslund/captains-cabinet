/**
 * The crontab plane: the transform, and the commit that has to PROVE what it
 * wrote.
 *
 * Every arm here names a way the previous shell pipelines reported success over
 * a write that did not happen. The measured reproductions are in
 * `lib/crontab.ts`'s header; `actions/crons.test.ts` drives the same failures
 * through the real server actions and a real crontab(1) stand-in, because a
 * fake `CrontabIO` proves the ALGORITHM and cannot prove the process boundary.
 */
import { describe, expect, it, vi } from 'vitest'
import {
  applyAdd,
  applyDelete,
  applyUpdate,
  commitCrontab,
  jobLines,
  matchJobs,
  type CrontabIO,
  type CrontabRead,
  type CrontabWrite,
} from './crontab'

const CT = [
  '# Health check',
  '*/5 * * * * /opt/watchdog/health-check.sh',
  '# Morning briefing',
  '0 6 * * * /opt/watchdog/morning-briefing.sh',
  '0 18 * * * /opt/watchdog/evening-briefing.sh',
  '',
].join('\n')

/** A crontab in a variable. Behaviour is injected per arm. */
function fakeIO(
  initial: string,
  opts: {
    readFails?: string
    writeFails?: string
    /** the write is accepted and thrown away — a read-only spool, a full disk */
    dropWrites?: boolean
    /** the write lands as something else entirely */
    corruptTo?: string
    /** the restore write also fails */
    restoreFails?: boolean
  } = {}
) {
  const state = { text: initial, writes: [] as string[], reads: 0 }
  const io: CrontabIO = {
    describe: () => 'docker exec cabinet-watchdog crontab -l',
    async read(): Promise<CrontabRead> {
      state.reads++
      if (opts.readFails) return { ok: false, reason: opts.readFails }
      return { ok: true, text: state.text }
    },
    async write(text: string): Promise<CrontabWrite> {
      state.writes.push(text)
      const isRestore = state.writes.length > 1
      if (opts.writeFails) return { ok: false, reason: opts.writeFails }
      if (isRestore && opts.restoreFails) return { ok: false, reason: 'spool is read-only' }
      if (opts.dropWrites && !isRestore) return { ok: true } // accepted, kept nothing
      state.text = opts.corruptTo !== undefined && !isRestore ? opts.corruptTo : text
      return { ok: true }
    },
  }
  return { io, state }
}

describe('parsing', () => {
  it('reads the schedulable lines and ignores comments, blanks and env assignments', () => {
    const jobs = jobLines(`# comment\n\nPATH=/usr/bin\n0 6 * * * /a.sh\n`)
    expect(jobs.map((j) => j.command)).toEqual(['/a.sh'])
  })

  it('matches on schedule AND command — never the schedule alone', () => {
    // THE COLLATERAL DELETE. `grep -v "^0 6 \* \* \*.*"` removed both of these.
    const two = '0 6 * * * /opt/watchdog/morning-briefing.sh\n0 6 * * * /opt/watchdog/backup.sh\n'
    expect(matchJobs(two, '0 6 * * *', '/opt/watchdog/backup.sh')).toHaveLength(1)
    expect(applyDelete(two, { schedule: '0 6 * * *', command: '/opt/watchdog/backup.sh' })).toMatchObject({
      ok: true,
      text: '0 6 * * * /opt/watchdog/morning-briefing.sh\n',
    })
  })

  it('is insensitive to whitespace on both sides of the match', () => {
    expect(matchJobs('0   6 * * *   /a.sh\n', '0 6 * * *', '/a.sh')).toHaveLength(1)
  })
})

describe('transforms — the degenerate ends', () => {
  it('update: no matching line is a REFUSAL, not a silent success', () => {
    const r = applyUpdate(CT, {
      originalSchedule: '0 3 * * *',
      command: '/opt/watchdog/nothing.sh',
      newSchedule: '0 7 * * *',
    })
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.reason).toMatch(/no line in the crontab reads/)
  })

  it('update: rewrites only the schedule, byte-preserving the command', () => {
    const r = applyUpdate(CT, {
      originalSchedule: '0 6 * * *',
      command: '/opt/watchdog/morning-briefing.sh',
      newSchedule: '0 7 * * *',
    })
    expect(r).toMatchObject({ ok: true, matched: 1 })
    expect(r.ok && r.text).toContain('0 7 * * * /opt/watchdog/morning-briefing.sh')
    expect(r.ok && r.text).not.toContain('0 6 * * *')
    expect(r.ok && r.text).toContain('*/5 * * * * /opt/watchdog/health-check.sh')
  })

  it('update: the same schedule twice — the first line, and the count is reported', () => {
    const dup = '0 6 * * * /a.sh\n0 6 * * * /a.sh\n'
    const r = applyUpdate(dup, { originalSchedule: '0 6 * * *', command: '/a.sh', newSchedule: '0 7 * * *' })
    expect(r).toMatchObject({ ok: true, matched: 2 })
    expect(r.ok && r.text).toBe('0 7 * * * /a.sh\n0 6 * * * /a.sh\n')
  })

  it('update: a no-op change is a refusal — a transform that changed nothing is not a save', () => {
    const r = applyUpdate(CT, {
      originalSchedule: '0 6 * * *',
      command: '/opt/watchdog/morning-briefing.sh',
      newSchedule: '0 6 * * *',
    })
    expect(r.ok).toBe(false)
  })

  it('add: the FIRST job, onto an empty crontab', () => {
    const r = applyAdd('', { schedule: '*/30 * * * *', command: '/opt/w/new.sh', description: 'New' })
    expect(r).toMatchObject({ ok: true })
    expect(r.ok && r.text).toBe('# New\n*/30 * * * * /opt/w/new.sh >> /var/log/watchdog/cron.log 2>&1\n')
  })

  it('add: keeps every existing job', () => {
    const r = applyAdd(CT, { schedule: '*/30 * * * *', command: '/opt/w/new.sh' })
    expect(jobLines(r.ok ? r.text : '')).toHaveLength(4)
  })

  it('add: refuses an exact duplicate rather than creating an ambiguous pair', () => {
    const once = applyAdd('', { schedule: '*/30 * * * *', command: '/opt/w/new.sh' })
    const twice = applyAdd(once.ok ? once.text : '', { schedule: '*/30 * * * *', command: '/opt/w/new.sh' })
    expect(twice.ok).toBe(false)
    expect(twice.ok === false && twice.reason).toMatch(/already scheduled/)
  })

  it('add: a newline in the command cannot smuggle in a second crontab line', () => {
    const r = applyAdd('', { schedule: '*/5 * * * *', command: '/a.sh\n* * * * * /evil.sh' })
    expect(r.ok).toBe(false)
  })

  it('add: a newline in the description cannot either', () => {
    const r = applyAdd('', { schedule: '*/5 * * * *', command: '/a.sh', description: 'x\n* * * * * /evil.sh' })
    expect(r).toMatchObject({ ok: true })
    expect(jobLines(r.ok ? r.text : '')).toHaveLength(1)
  })

  it('delete: nothing matches → a refusal, and the text is untouched', () => {
    const r = applyDelete(CT, { schedule: '9 9 9 9 9', command: '/ghost.sh' })
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.reason).toMatch(/nothing was deleted/)
  })

  it('delete: the same line twice → one goes, one stays', () => {
    const dup = '0 6 * * * /a.sh\n0 6 * * * /a.sh\n'
    const r = applyDelete(dup, { schedule: '0 6 * * *', command: '/a.sh' })
    expect(r).toMatchObject({ ok: true, matched: 2 })
    expect(r.ok && r.text).toBe('0 6 * * * /a.sh\n')
  })

  it('delete: an empty crontab refuses instead of writing an empty one', () => {
    expect(applyDelete('', { schedule: '0 6 * * *', command: '/a.sh' }).ok).toBe(false)
  })

  it('a crontab of nothing but comments survives an add intact', () => {
    const r = applyAdd('# just notes\n# and more\n', { schedule: '0 1 * * *', command: '/a.sh' })
    expect(r.ok && r.text.startsWith('# just notes\n# and more\n')).toBe(true)
  })
})

describe('commitCrontab — the proof', () => {
  it('a write that lands reports success (the inverse arm: honesty must not mean refusing everything)', async () => {
    const { io, state } = fakeIO(CT)
    const r = await commitCrontab(io, (t) =>
      applyUpdate(t, { originalSchedule: '0 6 * * *', command: '/opt/watchdog/morning-briefing.sh', newSchedule: '0 7 * * *' })
    )
    expect(r).toEqual({ ok: true, matched: 1 })
    expect(state.text).toContain('0 7 * * * /opt/watchdog/morning-briefing.sh')
    expect(state.writes).toHaveLength(1) // no restore attempted
  })

  it('THE DESTRUCTIVE CASE: a failed read refuses, and writes NOTHING', async () => {
    // `crontab -l | sed ... | crontab -` piped an empty read into `crontab -`
    // and exited 0, emptying the schedule. The read is now a gate.
    const { io, state } = fakeIO(CT, { readFails: 'Permission denied' })
    const r = await commitCrontab(io, (t) => applyAdd(t, { schedule: '0 1 * * *', command: '/a.sh' }))
    expect(r).toMatchObject({ ok: false })
    expect(r.ok === false && r.error).toMatch(/could not be read, so nothing was changed/)
    expect(r.ok === false && r.error).toMatch(/Permission denied/)
    expect(state.writes).toHaveLength(0)
    expect(state.text).toBe(CT)
  })

  it('a refused write reports the refusal and confirms the schedule is unchanged', async () => {
    const { io, state } = fakeIO(CT, { writeFails: 'bad minute' })
    const r = await commitCrontab(io, (t) => applyAdd(t, { schedule: '0 1 * * *', command: '/a.sh' }))
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.error).toMatch(/was not changed/)
    expect(state.text).toBe(CT)
  })

  it('a write silently dropped is a FAILURE, and the pre-image is restored and verified', async () => {
    const { io, state } = fakeIO(CT, { dropWrites: true })
    const r = await commitCrontab(io, (t) => applyAdd(t, { schedule: '0 1 * * *', command: '/a.sh' }))
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.error).toMatch(/did not take/)
    expect(r.ok === false && r.error).toMatch(/restored and verified/)
    expect(state.text).toBe(CT)
  })

  it('a write that lands as something ELSE is restored to the pre-image', async () => {
    const { io, state } = fakeIO(CT, { corruptTo: '0 6 * * * /opt/watchdog/morning-briefing.sh\n' })
    const r = await commitCrontab(io, (t) => applyAdd(t, { schedule: '0 1 * * *', command: '/a.sh' }))
    expect(r.ok).toBe(false)
    expect(state.text).toBe(CT)
    expect(state.writes).toHaveLength(2) // the write, then the restore
  })

  it('when the RESTORE cannot be proven, it says UNKNOWN — it never claims a rollback', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { io } = fakeIO(CT, { dropWrites: true, restoreFails: true })
    const r = await commitCrontab(io, (t) => applyAdd(t, { schedule: '0 1 * * *', command: '/a.sh' }))
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.error).toMatch(/UNKNOWN state/)
    expect(r.ok === false && r.error).not.toMatch(/restored and verified/)
    expect(r.ok === false && r.error).toMatch(/docker exec cabinet-watchdog crontab -l/)
    // the content that was there is not lost with the process
    expect(err.mock.calls.map(String).join('\n')).toContain('morning-briefing.sh')
    err.mockRestore()
  })

  it('a read-back that itself fails is reported as unverified, never as saved', async () => {
    let reads = 0
    const io: CrontabIO = {
      describe: () => 'CLI',
      async read() {
        reads++
        return reads === 1 ? { ok: true, text: CT } : { ok: false, reason: 'daemon went away' }
      },
      async write() {
        return { ok: true }
      },
    }
    const r = await commitCrontab(io, (t) => applyAdd(t, { schedule: '0 1 * * *', command: '/a.sh' }))
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.error).toMatch(/could not be verified/)
  })

  it('a transform refusal never reaches the write', async () => {
    const { io, state } = fakeIO(CT)
    const r = await commitCrontab(io, (t) => applyDelete(t, { schedule: '9 9 9 9 9', command: '/ghost.sh' }))
    expect(r.ok).toBe(false)
    expect(state.writes).toHaveLength(0)
  })
})
