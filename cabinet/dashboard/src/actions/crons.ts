'use server'

import { revalidatePath } from 'next/cache'
import redis, { isMockRedis, storeReading } from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { isNativeRuntime } from '@/lib/docker'
import { resolveStorePosture } from '@/lib/store-posture'
import {
  applyAdd,
  applyDelete,
  applyUpdate,
  commitCrontab,
  watchdogCrontabIO,
  type CrontabIO,
} from '@/lib/crontab'

/**
 * THE SCHEDULER'S WRITE PATH — nothing here says "saved" unless it read the
 * schedule back and found what it wrote.
 *
 * Every mutation below used to return `{ success: true }` from having ISSUED a
 * shell pipeline, and a pipeline's exit code is its LAST stage's. Reproduced
 * against the real handlers and a real crontab(1) on 2026-07-31: a failing
 * `crontab -l` piped nothing into `crontab -`, the dashboard went from three
 * scheduled jobs to "0 jobs", and the Captain was told the edit saved.
 * `lib/crontab.ts` carries the full measurement, the four false-success shapes,
 * and why the pipelines had to go rather than be wrapped.
 *
 * This is the same defect PR #330 closed for the emergency stop, on the surface
 * that decides when every scheduled thing on the machine runs.
 */

const prefix = process.env.CABINET_PREFIX || 'cabinet'

/** The state shape every cron form renders. `note` discloses a write deliberately not made. */
export interface CronActionState {
  error?: string
  success?: boolean
  note?: string
}

/**
 * Fabrication is an EXPLICIT, non-production opt-in (`lib/store-posture.ts`).
 * Read per call rather than at module scope so a test — and a process whose env
 * changed — sees the posture it is actually running under.
 */
const fabricated = () => resolveStorePosture(process.env).fabricated

const DEMO_NOTE =
  'demo mode — nothing was written to any schedule. Unset MOCK_DATA / CABINET_DEMO_DATA to edit the real one.'

/**
 * Mac-native deployments schedule with launchd, not crontab.
 *
 * `getCronSchedule()` KNOWS this — in native mode it lists `com.cabinet.*`
 * launchd labels and renders them with the literal schedule "launchd". The
 * write path did not know it: Edit, Add and Delete ran `docker exec
 * cabinet-watchdog crontab ...` regardless, so on a Mac mini the buttons under a
 * launchd row wrote to a completely different scheduling plane and reported
 * success either way. Refusing is the honest answer, and it names the tool that
 * can actually do it.
 */
const NATIVE_REFUSAL =
  'this cabinet schedules with launchd, not cron — the jobs listed here are launchd agents and cannot be edited from the dashboard. Use `launchctl` on the Cabinet Mac, or edit the plists in ~/Library/LaunchAgents.'

function crontabIO(): CrontabIO {
  return watchdogCrontabIO(`${prefix}-watchdog`)
}

/** Auth, posture and runtime — the three reasons a cron write must not proceed. */
async function refuseCronWrite(): Promise<CronActionState | null> {
  if (!(await requireDashboardAuth())) return { error: 'Unauthorized' }
  if (fabricated()) return { success: true, note: DEMO_NOTE }
  if (isNativeRuntime()) return { error: NATIVE_REFUSAL }
  return null
}

export async function updateCronSchedule(
  _prev: CronActionState | null,
  formData: FormData
): Promise<CronActionState> {
  const refusal = await refuseCronWrite()
  if (refusal) return refusal

  const originalSchedule = formData.get('originalSchedule') as string
  const newSchedule = formData.get('schedule') as string
  const command = formData.get('command') as string

  if (!newSchedule || !command) {
    return { error: 'Schedule and command are required' }
  }
  if (newSchedule.trim().split(/\s+/).length !== 5) {
    return { error: 'Cron expression must have exactly 5 fields (minute hour day month weekday)' }
  }

  const result = await commitCrontab(crontabIO(), (text) =>
    applyUpdate(text, { originalSchedule, command, newSchedule })
  )
  if (!result.ok) return { error: result.error }
  revalidatePath('/crons')
  return { success: true }
}

export async function addCronJob(
  _prev: CronActionState | null,
  formData: FormData
): Promise<CronActionState> {
  const refusal = await refuseCronWrite()
  if (refusal) return refusal

  const schedule = formData.get('schedule') as string
  const command = formData.get('command') as string
  const description = formData.get('description') as string

  if (!schedule || !command) {
    return { error: 'Schedule and command are required' }
  }
  if (schedule.trim().split(/\s+/).length !== 5) {
    return { error: 'Cron expression must have exactly 5 fields' }
  }

  const result = await commitCrontab(crontabIO(), (text) =>
    applyAdd(text, { schedule, command, description })
  )
  if (!result.ok) return { error: result.error }
  revalidatePath('/crons')
  return { success: true }
}

export async function deleteCronJob(
  _prev: CronActionState | null,
  formData: FormData
): Promise<CronActionState> {
  const refusal = await refuseCronWrite()
  if (refusal) return refusal

  const schedule = formData.get('schedule') as string
  const command = formData.get('command') as string

  if (!schedule || !command) {
    return { error: 'Schedule and command are required to identify the job' }
  }

  const result = await commitCrontab(crontabIO(), (text) =>
    applyDelete(text, { schedule, command })
  )
  if (!result.ok) return { error: result.error }
  revalidatePath('/crons')
  return { success: true }
}

// === Officer Task Actions ===

/**
 * WHY A POSTURE CHECK AND NOT JUST A READ-BACK.
 *
 * These three write to the store. The obvious fix is the killswitch's: write,
 * then read the key back. It is not enough here, and the reason is the reason
 * this program keeps finding sensors pointed at twins: with no `REDIS_URL`,
 * `lib/redis.ts` hands out an in-process object (`emptyStore`), so `set` then
 * `get` returns exactly what was just written. The read-back PASSES while
 * nothing was persisted and no cabinet was contacted. `isMockRedis` is
 * `isNotLiveStore(storeReading)` — demo OR unconfigured — and it is the only
 * thing that can tell the difference.
 *
 * So: refuse when the store is not live, and read back when it is.
 */
const notLiveRefusal = (): CronActionState | null =>
  isMockRedis
    ? {
        error: `this dashboard is not connected to a cabinet, so the timer was not changed — ${storeReading.source}`,
      }
    : null

const nowStamp = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z')
const timerKey = (officer: string, task: string) =>
  `cabinet:schedule:last-run:${officer}:${task}`

export async function resetTaskTimer(
  officer: string,
  task: string
): Promise<CronActionState> {
  if (!(await requireDashboardAuth())) return { error: 'Unauthorized' }
  const refusal = notLiveRefusal()
  if (refusal) return refusal
  try {
    const key = timerKey(officer, task)
    const now = nowStamp()
    await redis.set(key, now)
    const after = await redis.get(key)
    if (after !== now) {
      return {
        error: `the timer did not take: after writing "${now}" the store reads ${
          after === null ? '(absent)' : JSON.stringify(after)
        }`,
      }
    }
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to reset timer' }
  }
}

export async function deleteTaskTimer(
  officer: string,
  task: string
): Promise<CronActionState> {
  if (!(await requireDashboardAuth())) return { error: 'Unauthorized' }
  const refusal = notLiveRefusal()
  if (refusal) return refusal
  try {
    const key = timerKey(officer, task)
    await redis.del(key)
    const after = await redis.get(key)
    if (after !== null) {
      return {
        error: `the task was not deleted: the store still reads ${JSON.stringify(
          after
        )} for ${key}`,
      }
    }
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to delete task' }
  }
}

export async function createTaskTimer(
  _prev: CronActionState | null,
  formData: FormData
): Promise<CronActionState> {
  if (!(await requireDashboardAuth())) return { error: 'Unauthorized' }
  const officer = formData.get('officer') as string
  const task = formData.get('task') as string

  if (!officer || !task) {
    return { error: 'Officer and task name are required' }
  }
  if (!/^[a-z-]+$/.test(task)) {
    return { error: 'Task name must be lowercase with dashes (e.g. research-sweep)' }
  }
  if (!/^[a-z-]+$/.test(officer)) {
    return { error: 'Officer must be lowercase with dashes (e.g. cos, cto)' }
  }

  const refusal = notLiveRefusal()
  if (refusal) return refusal
  try {
    const key = timerKey(officer, task)
    const now = nowStamp()
    await redis.set(key, now)
    const after = await redis.get(key)
    if (after !== now) {
      return {
        error: `the task was not created: after writing "${now}" the store reads ${
          after === null ? '(absent)' : JSON.stringify(after)
        }`,
      }
    }
    revalidatePath('/crons')
    return { success: true }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to create task' }
  }
}
