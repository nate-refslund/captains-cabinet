'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { dockerExec } from '@/lib/docker'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'
import { resolveStorePosture } from '@/lib/store-posture'

const FABRICATED = resolveStorePosture(process.env).fabricated

const ASSEMBLE_SCRIPT = cabinetPath('cabinet/scripts/assemble-config.sh')
const PROJECTS_DIR = cabinetPath('instance/config/projects')

// Whitelisted sections that may be edited through this action
const ALLOWED_SECTIONS = ['product', 'notion', 'linear', 'neon', 'telegram']

/**
 * Resolve the active project slug so we know which YAML to edit.
 */
async function getActiveSlug(): Promise<string> {
  if (FABRICATED) return 'widgets'
  try {
    const { stdout } = await dockerExec(
      `cat ${cabinetPath('instance/config/active-project.txt')} 2>/dev/null`
    )
    // EMPTY, never 'widgets'. The invented fallback did not just mislabel the
    // page: this slug is interpolated into `${PROJECTS_DIR}/${slug}.yml`, so a
    // box with no active project had its config edits written into a file named
    // after a project it does not have. The caller refuses instead.
    return stdout.trim()
  } catch {
    return ''
  }
}

/**
 * Update a field inside the active project's config YAML, then reassemble
 * product.yml so every running officer picks up the change.
 *
 * `section`  — top-level YAML key (must be in ALLOWED_SECTIONS)
 * `path`     — dot-separated path beneath the section, e.g. "team_key" or
 *              "dashboard.page_id"
 * `value`    — the new scalar value to write
 */
export async function updateProjectConfig(
  section: string,
  path: string,
  value: string,
): Promise<{ success: boolean; error?: string }> {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!ALLOWED_SECTIONS.includes(section)) {
      return { success: false, error: `Section not allowed: ${section}` }
    }

    // Sanitise value for shell interpolation
    const safeValue = value.replace(/'/g, "'\\''")
    const slug = await getActiveSlug()
    if (!slug) {
      // Refusing beats writing. With no resolvable active project the old code
      // built `${PROJECTS_DIR}/.yml` and edited that.
      return {
        success: false,
        error:
          'no active project could be resolved on this box, so there is no config file to edit',
      }
    }
    const projectFile = `${PROJECTS_DIR}/${slug}.yml`

    if (FABRICATED) {
      console.log(`[demo] Would update ${section}.${path} = ${value} in ${projectFile}`)
      revalidatePath('/project')
      return { success: true }
    }

    const parts = path.split('.')

    if (parts.length === 1) {
      // Simple field directly under the section, e.g. product.name or linear.team_key
      const field = parts[0]
      await dockerExec(
        `sed -i '/^${section}:/,/^[a-z]/{s/^  ${field}: .*/  ${field}: ${safeValue}/}' ${projectFile}`
      )
    } else if (parts.length === 2) {
      // Nested field, e.g. notion.dashboard.page_id
      const [sub, field] = parts
      await dockerExec(
        `sed -i '/^${section}:/,/^[a-z]/{/^  ${sub}:/,/^  [a-z]/{s/^    ${field}: .*/    ${field}: ${safeValue}/}}' ${projectFile}`
      )
    } else {
      return { success: false, error: `Path too deep: ${path} (max 2 levels)` }
    }

    // Reassemble product.yml from platform + project sources
    await dockerExec(`bash ${ASSEMBLE_SCRIPT}`)

    revalidatePath('/project')
    revalidatePath('/settings')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update project config',
    }
  }
}
