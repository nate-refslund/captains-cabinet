'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { dockerExec } from '@/lib/docker'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { AVAILABILITY_REFUSAL, parseAvailabilityValue } from '@/lib/availability'
import { revalidatePath } from 'next/cache'

const CONFIG_PATH = cabinetPath('instance/config/product.yml')

const PRODUCT_FIELDS = ['name', 'description', 'repo', 'repo_branch', 'captain_name', 'mount_path']
const VOICE_FIELDS = ['enabled', 'provider', 'model', 'mode', 'naturalize']
const IMAGE_GEN_FIELDS = ['enabled', 'provider', 'model']
const EMBEDDINGS_FIELDS = ['provider', 'dimensions']
const VOICE_OFFICER_FIELDS = ['stability', 'speeds', 'voices', 'models', 'naturalize_prompts']

export async function updateProductConfig(field: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!PRODUCT_FIELDS.includes(field)) {
      return { success: false, error: `Invalid field: ${field}` }
    }
    // field is like "name", "description", etc. under the product: section
    const safeValue = value.replace(/'/g, "'\\''")
    await dockerExec(
      `sed -i '/^product:/,/^[a-z]/{s/^  ${field}: .*/  ${field}: ${safeValue}/}' ${CONFIG_PATH}`
    )
    revalidatePath('/settings')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update product config',
    }
  }
}

// ---------------------------------------------------------------------------
// The Captain's availability dial — adjustable from the dashboard, not only
// from Telegram (Captain direction 2026-07-26; the captain-controls ruling says
// his controls must work without a terminal, and a phone-only control is one
// missing app away from no control at all).
// ---------------------------------------------------------------------------

// The writer is the lib that OWNS the store, never a sed. Two reasons this is
// not the shape of the config actions above: instance/config/platform.yml is a
// marker-managed generator output with exactly ONE writer
// (framework/onboarding/availability.py), and the value the resolver actually
// serves is the append-only adjustment store — which carries the grammar, the
// refuse-don't-round rule, the provenance comment and the range check with it.
// The dashboard therefore writes the way the phone writes: it runs the
// recorder. Re-implementing the write here would be a second writer of the one
// number the whole org budgets against.
const AVAILABILITY_WRITER = cabinetPath('cabinet/scripts/lib/captain_availability.py')

// The writer's receipt, e.g.
//   recorded 30 min/day (part_time) -> /…/instance/config/captain-availability.yml
// REQUIRED before this action reports success. dockerExec's mock branch returns
// "mock: command executed" having written nothing, and that exact shape — a
// save the dashboard called done while nothing reached disk — is why
// dockerWriteFile/dockerReadFile were deleted (see lib/docker.ts). A write is
// claimed only when the writer says it wrote.
const AVAILABILITY_RECEIPT = /recorded \d+ min\/day \([a-z_]+\) -> \S/

/**
 * Record how much of the Captain's day the cabinet may use.
 *
 * `value` is either a canonical mode verb (away | minimal | part_time |
 * substantial | full_time) or whole minutes 0..1440. Anything else is REFUSED,
 * not rounded or repaired — a number the dial cannot represent has to come back
 * to him. Only the canonical token the parser returns is ever interpolated into
 * the command.
 */
export async function updateCaptainAvailability(value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  const parsed = parseAvailabilityValue(value)
  if (!parsed) {
    return { success: false, error: AVAILABILITY_REFUSAL }
  }
  try {
    const { stdout } = await dockerExec(
      `python3.12 '${AVAILABILITY_WRITER}' set ${parsed.cli} --source dashboard`
    )
    if (!AVAILABILITY_RECEIPT.test(stdout || '')) {
      return {
        success: false,
        error: 'The cabinet did not confirm the change — nothing was recorded.',
      }
    }
    revalidatePath('/settings')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update availability',
    }
  }
}

export async function updateGlobalVoiceConfig(field: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!VOICE_FIELDS.includes(field)) {
      return { success: false, error: `Invalid field: ${field}` }
    }
    const safeValue = value.replace(/'/g, "'\\''")
    await dockerExec(
      `sed -i '/^voice:/,/^[a-z]/{s/^  ${field}: .*/  ${field}: ${safeValue}/}' ${CONFIG_PATH}`
    )
    revalidatePath('/settings')
    revalidatePath('/')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update voice config',
    }
  }
}

export async function updateImageGenConfig(field: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!IMAGE_GEN_FIELDS.includes(field)) {
      return { success: false, error: `Invalid field: ${field}` }
    }
    const safeValue = value.replace(/'/g, "'\\''")
    await dockerExec(
      `sed -i '/^image_generation:/,/^[a-z]/{s/^  ${field}: .*/  ${field}: ${safeValue}/}' ${CONFIG_PATH}`
    )
    revalidatePath('/settings')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update image generation config',
    }
  }
}

export async function updateEmbeddingsConfig(field: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!EMBEDDINGS_FIELDS.includes(field) && field !== 'models.storage' && field !== 'models.query') {
      return { success: false, error: `Invalid field: ${field}` }
    }
    const safeValue = value.replace(/'/g, "'\\''")
    // Handle nested models section
    if (field === 'models.storage' || field === 'models.query') {
      const subField = field.split('.')[1]
      await dockerExec(
        `sed -i '/^embeddings:/,/^[a-z]/{/^  models:/,/^  [a-z]/{s/^    ${subField}: .*/    ${subField}: ${safeValue}/}}' ${CONFIG_PATH}`
      )
    } else {
      await dockerExec(
        `sed -i '/^embeddings:/,/^[a-z]/{s/^  ${field}: .*/  ${field}: ${safeValue}/}' ${CONFIG_PATH}`
      )
    }
    revalidatePath('/settings')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update embeddings config',
    }
  }
}

export async function updateOfficerVoiceConfig(role: string, field: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!VOICE_OFFICER_FIELDS.includes(field)) {
      return { success: false, error: `Invalid field: ${field}` }
    }
    const safeValue = value.replace(/'/g, "'\\''")
    // field is like "voices", "stability", "speeds", "naturalize_prompts", "models"
    // These are under voice.<field>.<role>
    await dockerExec(
      `sed -i '/^voice:/,/^[a-z]/{/^  ${field}:/,/^  [a-z]/{s/^    ${role}: .*/    ${role}: ${safeValue}/}}' ${CONFIG_PATH}`
    )
    revalidatePath(`/officers/${role}`)
    revalidatePath('/officers')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update officer voice config',
    }
  }
}

export async function updateNotionConfig(field: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    const safeValue = value.replace(/'/g, "'\\''")
    await dockerExec(
      `sed -i '/^notion:/,/^[a-z]/{s/^  ${field}: .*/  ${field}: ${safeValue}/}' ${CONFIG_PATH}`
    )
    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update Notion config',
    }
  }
}

export async function updateLinearConfig(field: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    const safeValue = value.replace(/'/g, "'\\''")
    await dockerExec(
      `sed -i '/^linear:/,/^[a-z]/{s/^  ${field}: .*/  ${field}: ${safeValue}/}' ${CONFIG_PATH}`
    )
    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update Linear config',
    }
  }
}
