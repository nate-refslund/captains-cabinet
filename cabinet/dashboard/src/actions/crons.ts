'use server'

import { exec as execCb } from 'child_process'
import { promisify } from 'util'
import { revalidatePath } from 'next/cache'
import redis from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { resolveStorePosture } from '@/lib/store-posture'

const exec = promisify(execCb)
const prefix = process.env.CABINET_PREFIX || 'cabinet'
const watchdog = `${prefix}-watchdog`
/**
 * FABRICATION, not "no store" — and here the old trigger was not merely
 * mislabelled, it was a FALSE SUCCESS CLAIM about a write.
 *
 * `!REDIS_URL` sent every mutation below down a branch that returned
 * `{ success: true }` without touching the watchdog's crontab. So on any
 * deployment with no store configured — which is a normal, supported posture
 * since the no-store fix — the Captain edited a schedule, was told it worked,
 * and nothing changed. That is the shape PR #330 closed for the emergency stop
 * ("returned success from having ISSUED a command it never confirmed"),
 * reproduced on the scheduler.
 *
 * Crons live in the watchdog container and have nothing to do with the store at
 * all; only the explicit demo opt-in short-circuits them now. Everything else
 * runs the real command and reports the real error.
 */
const FABRICATED = resolveStorePosture(process.env).fabricated

async function watchdogExec(command: string): Promise<string> {
  if (FABRICATED) {
    console.log(`[demo watchdog] Would exec: ${command}`)
    return ''
  }
  const { stdout } = await exec(
    `docker exec ${watchdog} sh -c '${command.replace(/'/g, "'\\''")}'`
  )
  return stdout.trim()
}

export async function updateCronSchedule(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData
) {
  if (!(await requireDashboardAuth())) {
    return { error: 'Unauthorized' }
  }
  const originalSchedule = formData.get('originalSchedule') as string
  const newSchedule = formData.get('schedule') as string
  const command = formData.get('command') as string

  if (!newSchedule || !command) {
    return { error: 'Schedule and command are required' }
  }

  // Validate cron expression (5 fields)
  const cronParts = newSchedule.trim().split(/\s+/)
  if (cronParts.length !== 5) {
    return { error: 'Cron expression must have exactly 5 fields (minute hour day month weekday)' }
  }

  if (FABRICATED) {
    revalidatePath('/crons')
    return { success: true }
  }

  try {
    // Get current crontab, replace the matching line, write it back
    const escapedOriginal = originalSchedule.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const escapedCommand = command.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

    await watchdogExec(
      `crontab -l | sed "s|^${escapedOriginal}.*${escapedCommand}.*|${newSchedule} ${command}|" | crontab -`
    )
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to update cron' }
  }
}

export async function addCronJob(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData
) {
  if (!(await requireDashboardAuth())) {
    return { error: 'Unauthorized' }
  }
  const schedule = formData.get('schedule') as string
  const command = formData.get('command') as string
  const description = formData.get('description') as string

  if (!schedule || !command) {
    return { error: 'Schedule and command are required' }
  }

  const cronParts = schedule.trim().split(/\s+/)
  if (cronParts.length !== 5) {
    return { error: 'Cron expression must have exactly 5 fields' }
  }

  if (FABRICATED) {
    revalidatePath('/crons')
    return { success: true }
  }

  try {
    const comment = description ? `# ${description}` : ''
    const newLine = `${schedule} ${command} >> /var/log/watchdog/cron.log 2>&1`

    if (comment) {
      await watchdogExec(`(crontab -l; echo "${comment}"; echo "${newLine}") | crontab -`)
    } else {
      await watchdogExec(`(crontab -l; echo "${newLine}") | crontab -`)
    }
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to add cron job' }
  }
}

export async function deleteCronJob(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData
) {
  if (!(await requireDashboardAuth())) {
    return { error: 'Unauthorized' }
  }
  const schedule = formData.get('schedule') as string
  const command = formData.get('command') as string

  if (!schedule || !command) {
    return { error: 'Schedule and command are required to identify the job' }
  }

  if (FABRICATED) {
    revalidatePath('/crons')
    return { success: true }
  }

  try {
    const escapedSchedule = schedule.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    // Remove the line matching this schedule + command pattern
    await watchdogExec(
      `crontab -l | grep -v "^${escapedSchedule}.*" | crontab -`
    )
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to delete cron job' }
  }
}

// === Officer Task Actions ===

export async function resetTaskTimer(officer: string, task: string) {
  if (!(await requireDashboardAuth())) {
    return { error: 'Unauthorized' }
  }
  try {
    const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z')
    await redis.set(`cabinet:schedule:last-run:${officer}:${task}`, now)
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to reset timer' }
  }
}

export async function deleteTaskTimer(officer: string, task: string) {
  if (!(await requireDashboardAuth())) {
    return { error: 'Unauthorized' }
  }
  try {
    await redis.del(`cabinet:schedule:last-run:${officer}:${task}`)
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to delete task' }
  }
}

export async function createTaskTimer(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData
) {
  if (!(await requireDashboardAuth())) {
    return { error: 'Unauthorized' }
  }
  const officer = formData.get('officer') as string
  const task = formData.get('task') as string

  if (!officer || !task) {
    return { error: 'Officer and task name are required' }
  }

  if (!/^[a-z-]+$/.test(task)) {
    return { error: 'Task name must be lowercase with dashes (e.g. research-sweep)' }
  }

  try {
    const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z')
    await redis.set(`cabinet:schedule:last-run:${officer}:${task}`, now)
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to create task' }
  }
}
