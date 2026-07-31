'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { assertRuntimeWritesAllowed, dockerExec } from '@/lib/docker'
import { writeYamlScalar } from '@/lib/config-write'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { AVAILABILITY_REFUSAL, parseAvailabilityValue } from '@/lib/availability'
import { revalidatePath } from 'next/cache'

/**
 * EVERY FIELD EDITOR IN THIS FILE USED TO BE A `sed -i`, AND NONE OF THEM EVER
 * RAN. BSD `sed` takes the in-place suffix as a mandatory argument, so on the
 * Captain's Mac — the only deployment there is — each of these exited 1 with
 * `invalid command code` and left `product.yml` byte-identical. They now edit
 * the document in this process: read it whole, change one line, write it back
 * atomically, read it back and compare. `lib/config-write.ts` carries the
 * measurement and the rest of the reasoning.
 *
 * Two things change for the caller, both of them the point. A field that is not
 * in the file is now an ERROR rather than a silent success — `sed` exits 0 when
 * its pattern matches nothing, which is the same write-lie with no shell
 * dialect involved. And a value that would make the YAML unparseable is refused
 * instead of landed.
 *
 * A function, not a module constant, so `CABINET_ROOT` is honoured at write
 * time — the rule `lib/cabinet-root.ts` exists to state.
 */
const configPath = () => cabinetPath('instance/config/product.yml')

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
    assertRuntimeWritesAllowed(`set product.${field} in product.yml`)
    await writeYamlScalar(configPath(), ['product', field], value)
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
// REQUIRED before this action reports success: a write is claimed only when the
// writer says it wrote. This is an OUTPUT-SHAPE control and is deliberately
// independent of the store posture — `lib/docker.ts` now rejects a command it
// declined to run, which covers the not-live case for every action in this
// file, but a writer that genuinely ran and printed something else is a
// different failure and this is the only thing that catches it.
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
    assertRuntimeWritesAllowed(`set voice.${field} in product.yml`)
    await writeYamlScalar(configPath(), ['voice', field], value)
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
    assertRuntimeWritesAllowed(`set image_generation.${field} in product.yml`)
    await writeYamlScalar(configPath(), ['image_generation', field], value)
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
    assertRuntimeWritesAllowed(`set embeddings.${field} in product.yml`)
    // `models.storage` / `models.query` are one level deeper; the walker takes
    // the whole path, so the nesting is data rather than a second sed dialect.
    await writeYamlScalar(configPath(), ['embeddings', ...field.split('.')], value)
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
    // field is like "voices", "stability", "speeds", "naturalize_prompts", "models"
    // These are under voice.<field>.<role>
    if (!/^[a-z]{2,4}$/.test(role)) {
      return { success: false, error: 'Invalid role identifier' }
    }
    assertRuntimeWritesAllowed(`set voice.${field}.${role} in product.yml`)
    await writeYamlScalar(configPath(), ['voice', field, role], value)
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
    assertRuntimeWritesAllowed(`set notion.${field} in product.yml`)
    await writeYamlScalar(configPath(), ['notion', field], value)
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
    assertRuntimeWritesAllowed(`set linear.${field} in product.yml`)
    await writeYamlScalar(configPath(), ['linear', field], value)
    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update Linear config',
    }
  }
}
