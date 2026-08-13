'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { assertRuntimeWritesAllowed, dockerExec } from '@/lib/docker'
import { removeEnvKey, removeYamlKey } from '@/lib/config-write'
import redis, { isMockRedis, storeReading } from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'

/**
 * A DASHBOARD THAT HAS NOT CONTACTED A CABINET MAY NOT SAY IT STOPPED ONE.
 *
 * `dockerExec` short-circuited whenever the store was not live — demo OR
 * `unconfigured` — returning the string `mock: command executed` instead of
 * running anything. No action below branched on that, so with `REDIS_URL` unset
 * the Captain pressed Stop on an officer, nothing was executed,
 * `redis.set(expected:stopped)` landed in an in-process object, and the card
 * read "stopped" over an autonomous agent that was still running and still
 * acting.
 *
 * This is the crons defect and the emergency-stop defect on the officer fleet.
 * The read-back that fixes the killswitch cannot fix it — the in-process store
 * echoes back whatever was written — so the posture is the gate, exactly as in
 * `actions/crons.ts`.
 *
 * SINCE 2026-07-31 the source refuses too: an unrun command REJECTS with
 * `CommandNotExecutedError` (`lib/docker.ts`), so an action IN THIS FILE THAT
 * SHELLS OUT cannot report success even if it forgets this guard. An action
 * that only wrote to the store would still need the guard — the in-process
 * store answers happily — which is the other half of why it stays. `createOfficer` WAS that action — the one
 * hole in this patch, found by sweeping the enabler, and it accepted a live
 * Telegram bot token before rendering "Officer Created". Both belts are worn
 * deliberately: the guard means no exec is attempted and the Captain gets one
 * sentence, the rejection means the next action added to this file is safe on
 * the day it is written rather than on the day somebody remembers.
 */
function notLiveRefusal(): { success: false; error: string } | null {
  return isMockRedis
    ? {
        success: false,
        error: `this dashboard is not connected to a cabinet, so nothing was done — ${storeReading.source}`,
      }
    : null
}

/** `set -a; source cabinet/.env; set +a; bash <script> <args>` against the
 *  resolved checkout root (dockerExec native mode already cwd's there, but
 *  absolute paths keep docker mode + explicit invocations working).
 *
 *  `set -a` around the `source` is what exports the sourced keys to the child
 *  `bash`. The prior `export $(grep -v "^#" … | xargs)` re-parsed the file a
 *  second time through `xargs`, whose quote rules are not bash's — a safe-quoted
 *  value (config-write.ts single-quotes anything shell-unsafe) would be mangled
 *  by xargs and then override the value `source` had already set correctly. The
 *  `set -a` form has no second parser and is what every other boot script uses. */
function envAndRun(script: string, args: string): string {
  const envFile = cabinetPath('cabinet/.env')
  return `set -a && source ${envFile} && set +a && bash ${cabinetPath(script)} ${args}`
}

export async function startOfficer(role: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  const notLive = notLiveRefusal()
  if (notLive) return notLive
  try {
    await dockerExec(envAndRun('cabinet/scripts/start-officer.sh', role))
    await redis.set(`cabinet:officer:expected:${role}`, 'active')
    revalidatePath('/officers')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to start officer',
    }
  }
}

export async function stopOfficer(role: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  const notLive = notLiveRefusal()
  if (notLive) return notLive
  try {
    await dockerExec(`tmux kill-window -t cabinet:officer-${role}`)
    await redis.set(`cabinet:officer:expected:${role}`, 'stopped')
    revalidatePath('/officers')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to stop officer',
    }
  }
}

export async function restartOfficer(role: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  const notLive = notLiveRefusal()
  if (notLive) return notLive
  try {
    await dockerExec(`tmux kill-window -t cabinet:officer-${role}`)
    // Brief delay to let tmux clean up
    await new Promise((resolve) => setTimeout(resolve, 2000))
    await dockerExec(envAndRun('cabinet/scripts/start-officer.sh', role))
    await redis.set(`cabinet:officer:expected:${role}`, 'active')
    revalidatePath('/officers')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to restart officer',
    }
  }
}

export async function deleteOfficer(role: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  const notLive = notLiveRefusal()
  if (notLive) return notLive
  try {
    if (!/^[a-z]{2,4}$/.test(role)) {
      return { success: false, error: 'Invalid role identifier' }
    }

    // Stop the officer first
    try {
      await dockerExec(`tmux kill-window -t cabinet:officer-${role} 2>/dev/null || true`)
    } catch {
      // May not be running
    }

    // Remove role definition and loop prompt files
    await dockerExec(`rm -f ${cabinetPath('.claude/agents')}/${role}.md`)
    await dockerExec(`rm -f ${cabinetPath('cabinet/loop-prompts')}/${role}.txt`)

    // Remove from product.yml voice sections, then the telegram entry.
    //
    // These seven `sed -i` deletions never ran: BSD sed's in-place suffix is
    // mandatory, so each exited 1 and left product.yml unchanged — a deleted
    // officer kept his voice, his prompt and his Telegram routing on the only
    // machine this is deployed to. `removeYamlKey` tolerates an ABSENT key on
    // purpose (an officer with no voice configured has no such line, and
    // refusing to delete him over it would be rigour with the wrong sign).
    const configPath = cabinetPath('instance/config/product.yml')
    const sections = ['voices', 'naturalize_prompts', 'stability', 'speeds', 'models']
    assertRuntimeWritesAllowed(`remove officer ${role} from product.yml`)
    for (const section of sections) {
      await removeYamlKey(configPath, ['voice', section, role])
    }

    await removeYamlKey(configPath, ['telegram', 'officers', role])

    // Clean up Redis state
    await redis.del(`cabinet:officer:expected:${role}`)
    await redis.del(`cabinet:heartbeat:${role}`)

    // Remove bot token from .env
    const upperRole = role.toUpperCase()
    await removeEnvKey(
      process.env.CABINET_ENV_PATH || cabinetPath('cabinet/.env'),
      `TELEGRAM_${upperRole}_TOKEN`
    )

    revalidatePath('/officers')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to delete officer',
    }
  }
}

export async function createOfficer(
  _prevState: { error?: string; success?: boolean } | null,
  formData: FormData
) {
  if (!(await requireDashboardAuth())) {
    return { error: 'Unauthorized' }
  }
  const abbrev = (formData.get('abbreviation') as string).toLowerCase()
  const title = formData.get('title') as string
  const domain = formData.get('domain') as string
  const botUsername = formData.get('botUsername') as string
  const botToken = formData.get('botToken') as string
  const voiceId = (formData.get('voiceId') as string) || ''
  const voicePrompt = (formData.get('voicePrompt') as string) || ''
  const voiceStability = (formData.get('voiceStability') as string) || '0.5'
  const voiceSpeed = (formData.get('voiceSpeed') as string) || '1.0'
  const interfaceName = (formData.get('interfaceName') as string) || ''

  if (!/^[a-z]{2,4}$/.test(abbrev)) {
    return { error: 'Abbreviation must be 2-4 lowercase letters' }
  }

  if (!title || !domain || !botUsername || !botToken) {
    return { error: 'Title, domain, bot username, and bot token are required' }
  }

  // Validate first, refuse second: the form should still tell the Captain his
  // input is malformed rather than blaming the store for it.
  const notLive = notLiveRefusal()
  if (notLive) return { error: notLive.error }

  // Build optional flags
  const flags: string[] = []
  if (voiceId) flags.push(`--voice-id "${voiceId}"`)
  if (voicePrompt) flags.push(`--voice-prompt "${voicePrompt.replace(/"/g, '\\"')}"`)
  if (voiceStability !== '0.5') flags.push(`--voice-stability ${voiceStability}`)
  if (voiceSpeed !== '1.0') flags.push(`--voice-speed ${voiceSpeed}`)
  if (interfaceName) flags.push(`--interface "${interfaceName}"`)

  const flagStr = flags.length > 0 ? ' ' + flags.join(' ') : ''

  try {
    await dockerExec(
      envAndRun(
        'cabinet/scripts/create-officer.sh',
        `"${abbrev}" "${title}" "${domain}" "${botUsername}" "${botToken}"${flagStr}`
      )
    )
    revalidatePath('/officers')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      error: err instanceof Error ? err.message : 'Failed to create officer',
    }
  }
}
