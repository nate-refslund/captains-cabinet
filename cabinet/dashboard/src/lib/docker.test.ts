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

describe('dockerExec — mock path', () => {
  it('returns the fixed mock stdout + empty stderr', async () => {
    const result = await mod.dockerExec('echo hi')
    expect(result).toEqual({ stdout: 'mock: command executed', stderr: '' })
  })

  it('does not throw on empty command', async () => {
    await expect(mod.dockerExec('')).resolves.toBeDefined()
  })

  it('does not throw on shell metacharacters in mock path', async () => {
    // Real path does single-quote escaping; mock short-circuits before escape
    await expect(mod.dockerExec("echo 'a' && echo 'b'")).resolves.toBeDefined()
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
