'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { dockerExec } from '@/lib/docker'
import redis from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'
import { resolveStorePosture } from '@/lib/store-posture'

/**
 * FABRICATION, not "no store". `!REDIS_URL` used to send every function here
 * down a branch that invented a project called "Widgets" — measured rendering
 * in the nav header of a dashboard whose store was merely unreachable. A
 * project identifier is not a measurement of health, money or attention, which
 * is why it survived the last pass; it is still a name for something that does
 * not exist, presented as this cabinet's.
 *
 * Only the explicit, non-production demo opt-in fabricates now. Everything else
 * reads the real sources and renders honest absence when they answer nothing.
 */
const FABRICATED = resolveStorePosture(process.env).fabricated

export interface ProjectInfo {
  slug: string
  name: string
  active: boolean
}

export async function switchProject(slug: string): Promise<{ success: boolean; error?: string }> {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (FABRICATED) {
      console.log(`[demo] Would switch to project: ${slug}`)
      return { success: true }
    }
    const safeSlug = slug.replace(/[^a-z0-9_-]/g, '')
    await dockerExec(`bash ${cabinetPath('cabinet/scripts/switch-project.sh')} ${safeSlug}`)
    revalidatePath('/')
    revalidatePath('/settings')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to switch project',
    }
  }
}

export async function getActiveProject(): Promise<string> {
  if (!(await requireDashboardAuth())) return ''
  if (FABRICATED) {
    return 'widgets'
  }
  try {
    const redisValue = await redis.get('cabinet:active-project')
    if (redisValue) return redisValue
  } catch {
    // The store did not answer. The file below is an independent source, so
    // fall through to it rather than giving up — but never to a made-up name.
  }
  try {
    const { stdout } = await dockerExec(
      `cat ${cabinetPath('instance/config/active-project.txt')} 2>/dev/null`
    )
    // `|| echo widgets` used to live in that shell command, so a box with no
    // active-project file reported a project it does not have. An empty string
    // is the honest answer; the nav renders no project rather than a fiction.
    return stdout.trim()
  } catch {
    return ''
  }
}

export async function getProjects(): Promise<ProjectInfo[]> {
  if (!(await requireDashboardAuth())) return []
  if (FABRICATED) {
    return [
      { slug: 'widgets', name: 'Widgets', active: true },
      { slug: 'demo-project', name: 'Demo Project', active: false },
    ]
  }

  try {
    const activeSlug = await getActiveProject()
    const { stdout } = await dockerExec(
      `for f in ${cabinetPath('instance/config/projects')}/*.yml; do
        slug=$(basename "$f" .yml)
        name=$(grep -m1 "^  name:" "$f" 2>/dev/null | sed 's/.*name: *//')
        [ -z "$name" ] && name=$(grep -m1 "name:" "$f" 2>/dev/null | sed 's/.*name: *//')
        echo "$slug|$name"
      done`
    )

    const projects: ProjectInfo[] = stdout
      .split('\n')
      .filter((line) => line.includes('|'))
      .filter((line) => !line.split('|')[0].trim().startsWith('_'))
      .map((line) => {
        const [slug, name] = line.split('|')
        return {
          slug: slug.trim(),
          name: name.trim() || slug.trim(),
          active: slug.trim() === activeSlug,
        }
      })

    // EMPTY, never a placeholder project.
    //
    // These two fallbacks are where "Widgets" ACTUALLY came from on a real box:
    // not the demo branch, but the real path's own catch. A cabinet whose
    // project listing failed, or which has no projects yet, rendered
    // "Captain's Cabinet / Widgets" in the nav header — a name for something
    // that does not exist, presented as this Captain's. Measured in the built
    // app while fixing the store-unreachable hang, which is how it was found.
    //
    // The nav renders the project chip only when the list is non-empty, so an
    // empty list is an honest blank rather than a broken layout.
    return projects
  } catch {
    return []
  }
}
