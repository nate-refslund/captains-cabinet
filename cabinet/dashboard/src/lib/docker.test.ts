// docker.ts — the DEMO-path contract for the exported runtime-probe helpers.
//
// This file ASKS FOR the fabricated answers (2026-07-31). It used to get them
// by leaving REDIS_URL unset — which is exactly how a dashboard with no store
// came to report "Officers: 4/5 running". The invented roster now requires an
// explicit non-production opt-in; the honest no-store behaviour of these same
// helpers is driven by `no-store-honesty.test.ts`.
//
// dockerWriteFile/dockerReadFile are GONE (Wave B): repo-file I/O moved to
// real node:fs in governance.ts/files.ts — the mock write here used to
// console-log no-op a Captain's save while the action claimed success.
// A source pin below keeps them from quietly returning.
//
// Real path (docker exec / crontab -l / curl telegram) requires
// child_process mocking + is deferred — this harness pins the mock
// contract that the /health admin pages rely on during local dev.

import { beforeAll, describe, it, expect } from 'vitest'

// Ensure the DEMO path is active before dynamic import.
delete process.env.REDIS_URL
delete process.env.MOCK_DATA
process.env.CABINET_DEMO_DATA = 'true'

type Mod = typeof import('./docker')
let mod: Mod

beforeAll(async () => {
  mod = await import('./docker')
})

describe('dockerExec — an unrun command REJECTS, it never answers', () => {
  // This block used to assert `resolves.toEqual({ stdout: 'mock: command
  // executed' })` — it pinned the defect as the contract. 19 write actions read
  // that resolved value as success for work that never happened.
  it('rejects rather than resolving a fabricated stdout', async () => {
    await expect(mod.dockerExec('echo hi')).rejects.toThrow()
    await expect(mod.dockerExec('echo hi')).rejects.not.toThrow(
      /mock: command executed/
    )
  })

  it('the rejection says nothing ran, in words a Captain can act on', async () => {
    // These messages are rendered VERBATIM by the callers' catch blocks.
    await expect(mod.dockerExec('echo hi')).rejects.toThrow(
      /nothing was run and nothing was changed/i
    )
  })

  it('and it names DEMO, not a misconfigured deploy — the two sentences differ', async () => {
    // `/nothing was run/` alone matches BOTH refusal texts, so it could not tell
    // the demo sentence from the production-misconfiguration one. This module is
    // in the demo posture (top of file); the wrong sentence here would send a
    // developer who typed the flag off to check REDIS_URL on a real deploy.
    await expect(mod.dockerExec('echo hi')).rejects.toThrow(/demo data/i)
    await expect(mod.dockerExec('echo hi')).rejects.not.toThrow(/misconfiguration/i)
  })

  it('carries the posture and the command it did not run', async () => {
    const err = await mod.dockerExec('rm -rf /nope').then(
      () => null,
      (e: unknown) => e as InstanceType<typeof mod.CommandNotExecutedError>
    )
    expect(err).toBeInstanceOf(mod.CommandNotExecutedError)
    expect(err!.name).toBe('CommandNotExecutedError')
    expect(err!.posture).toBe('demo')
    expect(err!.command).toBe('rm -rf /nope')
  })

  it('an EMPTY command is refused too — the degenerate end is still not a run', async () => {
    await expect(mod.dockerExec('')).rejects.toThrow(/nothing was run/i)
  })

  it('shell metacharacters change nothing — the refusal is before any escaping', async () => {
    await expect(mod.dockerExec("echo 'a' && echo 'b'")).rejects.toThrow(
      /nothing was run/i
    )
  })

  it('the no-op sentinel string is gone from the module surface entirely', () => {
    // A constant that still exists is a constant a new caller can compare
    // against, which is how three read paths came to carry dead string checks.
    expect('MOCK_EXEC_SENTINEL' in mod).toBe(false)
  })
})

describe('getTmuxWindows — mock path', () => {
  it('returns the 5-officer roster', async () => {
    expect(await mod.getTmuxWindows()).toEqual(['cos', 'cto', 'cpo', 'cro', 'coo'])
  })

  it('returns a stable array (same reference-value across calls)', async () => {
    const a = await mod.getTmuxWindows()
    const b = await mod.getTmuxWindows()
    expect(a).toEqual(b)
  })
})

describe('isClaudeAlive(role) — mock path', () => {
  it('returns true for cos/cto/cpo/cro (non-coo roles)', async () => {
    expect(await mod.isClaudeAlive('cos')).toBe(true)
    expect(await mod.isClaudeAlive('cto')).toBe(true)
    expect(await mod.isClaudeAlive('cpo')).toBe(true)
    expect(await mod.isClaudeAlive('cro')).toBe(true)
  })

  it('returns false for coo (mock marks coo as down)', async () => {
    expect(await mod.isClaudeAlive('coo')).toBe(false)
  })

  it('returns true for unknown role (only coo is hardcoded-down)', async () => {
    expect(await mod.isClaudeAlive('nobody')).toBe(true)
  })
})

describe('dockerWriteFile + dockerReadFile — pruned (Wave B)', () => {
  it('the silent no-op file transport is gone from the module surface', () => {
    expect('dockerWriteFile' in mod).toBe(false)
    expect('dockerReadFile' in mod).toBe(false)
  })
})

describe('getCronSchedule — mock path', () => {
  it('returns 8 cron entries in mock mode', async () => {
    const schedule = await mod.getCronSchedule()
    expect(schedule).toHaveLength(8)
  })

  it('each entry has {schedule, command, description}', async () => {
    const schedule = await mod.getCronSchedule()
    for (const job of schedule) {
      expect(job).toHaveProperty('schedule')
      expect(job).toHaveProperty('command')
      expect(job).toHaveProperty('description')
      expect(typeof job.schedule).toBe('string')
      expect(typeof job.command).toBe('string')
      expect(typeof job.description).toBe('string')
    }
  })

  it('includes the morning-briefing entry with 0 6 * * *', async () => {
    const schedule = await mod.getCronSchedule()
    const morning = schedule.find((j) => j.command === 'morning-briefing.sh')
    expect(morning).toBeDefined()
    expect(morning!.schedule).toBe('0 6 * * *')
  })

  it('every cron schedule uses 5 space-separated fields', async () => {
    const schedule = await mod.getCronSchedule()
    for (const job of schedule) {
      expect(job.schedule.split(/\s+/)).toHaveLength(5)
    }
  })
})

describe('getEnvVars — mock path', () => {
  it('returns a map of expected API key names', async () => {
    const envs = await mod.getEnvVars()
    expect(envs).toHaveProperty('ANTHROPIC_API_KEY')
    expect(envs).toHaveProperty('LINEAR_API_KEY')
    expect(envs).toHaveProperty('NOTION_API_KEY')
    expect(envs).toHaveProperty('GITHUB_PAT')
    expect(envs).toHaveProperty('TELEGRAM_CTO_TOKEN')
  })

  it('mock values are redacted/placeholder strings, not real creds', async () => {
    const envs = await mod.getEnvVars()
    // Every mock value contains 'mock' substring — pins that no real cred
    // leaked into the mock fixture
    for (const [k, v] of Object.entries(envs)) {
      if (k === 'TELEGRAM_HQ_CHAT_ID' || k === 'CAPTAIN_TELEGRAM_ID') continue
      expect(v.toLowerCase()).toContain('mock')
    }
  })

  it('returns a non-empty map (at least 10 entries)', async () => {
    const envs = await mod.getEnvVars()
    expect(Object.keys(envs).length).toBeGreaterThanOrEqual(10)
  })
})

describe('isTelegramConnected(role) — mock path', () => {
  it('returns true for non-coo roles', async () => {
    expect(await mod.isTelegramConnected('cos')).toBe(true)
    expect(await mod.isTelegramConnected('cto')).toBe(true)
    expect(await mod.isTelegramConnected('cpo')).toBe(true)
    expect(await mod.isTelegramConnected('cro')).toBe(true)
  })

  it('returns false for coo', async () => {
    expect(await mod.isTelegramConnected('coo')).toBe(false)
  })

  it('returns true for unknown role in mock (only coo hardcoded-false)', async () => {
    expect(await mod.isTelegramConnected('unknown-role')).toBe(true)
  })
})
