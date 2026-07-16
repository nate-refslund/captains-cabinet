'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { dockerExec } from '@/lib/docker'
import redis from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'

const IS_MOCK = process.env.MOCK_DATA === 'true' || !process.env.REDIS_URL

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
    if (IS_MOCK) {
      console.log(`[mock] Would switch to project: ${slug}`)
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
  if (IS_MOCK) {
    return 'widgets'
  }
  try {
    const redisValue = await redis.get('cabinet:active-project')
    if (redisValue) return redisValue
    const { stdout } = await dockerExec(
      `cat ${cabinetPath('instance/config/active-project.txt')} 2>/dev/null || echo widgets`
    )
    return stdout.trim() || 'widgets'
  } catch {
    return 'widgets'
  }
}

export async function getProjects(): Promise<ProjectInfo[]> {
  if (!(await requireDashboardAuth())) return []
  if (IS_MOCK) {
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

    if (projects.length === 0) {
      return [{ slug: 'widgets', name: 'Widgets', active: true }]
    }

    return projects
  } catch {
    return [{ slug: 'widgets', name: 'Widgets', active: true }]
  }
}
