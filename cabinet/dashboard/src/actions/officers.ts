'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { dockerExec } from '@/lib/docker'
import redis, { isMockRedis, storeReading } from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'

/**
 * A DASHBOARD THAT HAS NOT CONTACTED A CABINET MAY NOT SAY IT STOPPED ONE.
 *
 * `dockerExec` short-circuits whenever the store is not live — demo OR
 * `unconfigured` — returning the string `mock: command executed` instead of
 * running anything (`lib/docker.ts`). No action below branched on that, so with
 * `REDIS_URL` unset the Captain pressed Stop on an officer, nothing was
 * executed, `redis.set(expected:stopped)` landed in an in-process object, and
 * the card read "stopped" over an autonomous agent that was still running and
 * still acting. `unconfigured` has no production exclusion, so that is
 * reachable on a real deploy that simply forgot the store.
 *
 * This is the crons defect and the emergency-stop defect on the officer fleet.
 * The read-back that fixes the killswitch cannot fix it — the in-process store
 * echoes back whatever was written — so the posture is the gate, exactly as in
 * `actions/crons.ts`.
 */
function notLiveRefusal(): { success: false; error: string } | null {
  return isMockRedis
    ? {
        success: false,
        error: `this dashboard is not connected to a cabinet, so nothing was done — ${storeReading.source}`,
      }
    : null
}

/** `source cabinet/.env && export … && bash <script> <args>` against the
 *  resolved checkout root (dockerExec native mode already cwd's there, but
 *  absolute paths keep docker mode + explicit invocations working). */
function envAndRun(script: string, args: string): string {
  const envFile = cabinetPath('cabinet/.env')
  return `source ${envFile} && export $(grep -v "^#" ${envFile} | xargs) && bash ${cabinetPath(script)} ${args}`
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

    // Remove from product.yml voice sections
    const CONFIG_PATH = cabinetPath('instance/config/product.yml')
    const sections = ['voices', 'naturalize_prompts', 'stability', 'speeds', 'models']
    for (const section of sections) {
      await dockerExec(
        `sed -i '/^voice:/,/^[a-z]/{/^  ${section}:/,/^  [a-z]/{/^    ${role}: /d}}' ${CONFIG_PATH}`
      )
    }

    // Remove telegram officer entry
    await dockerExec(
      `sed -i '/^telegram:/,/^[a-z]/{/^  officers:/,/^  [a-z]/{/^    ${role}: /d}}' ${CONFIG_PATH}`
    )

    // Clean up Redis state
    await redis.del(`cabinet:officer:expected:${role}`)
    await redis.del(`cabinet:heartbeat:${role}`)

    // Remove bot token from .env
    const upperRole = role.toUpperCase()
    await dockerExec(
      `sed -i '/^TELEGRAM_${upperRole}_TOKEN=/d' ${cabinetPath('cabinet/.env')}`
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
