'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { dockerExec, getEnvVars as dockerGetEnvVars } from '@/lib/docker'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'

// Path to the checkout's cabinet/.env. Override via CABINET_ENV_PATH env var;
// otherwise resolved from CABINET_ROOT (set by deploy-mac.sh /
// start-officer-mac.sh / start-dashboard.sh) so the env-var editor writes the
// file the cabinet reads.
const ENV_PATH = process.env.CABINET_ENV_PATH || cabinetPath('cabinet/.env')

export async function getEnvVarsAction(): Promise<Record<string, string>> {
  // Reads real cabinet/.env secrets — no error channel in the return type, so
  // an unauthenticated caller must never reach the read: throw, never leak.
  if (!(await requireDashboardAuth())) throw new Error('Unauthorized')
  return dockerGetEnvVars()
}

export async function deleteEnvVar(key: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!/^[A-Z_][A-Z0-9_]*$/.test(key)) {
      return { success: false, error: 'Invalid environment variable name' }
    }
    const safeKey = key.replace(/'/g, "'\\''")
    await dockerExec(`sed -i '/^${safeKey}=/d' ${ENV_PATH}`)
    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to delete environment variable',
    }
  }
}

export async function addEnvVar(key: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!/^[A-Z_][A-Z0-9_]*$/.test(key)) {
      return { success: false, error: 'Invalid name — use UPPER_SNAKE_CASE' }
    }
    // Check if already exists
    const { stdout: exists } = await dockerExec(
      `grep -c "^${key}=" ${ENV_PATH} 2>/dev/null || echo 0`
    )
    if (parseInt(exists.trim()) > 0) {
      return { success: false, error: `${key} already exists — edit it instead` }
    }
    const safeValue = value.replace(/'/g, "'\\''")
    await dockerExec(`echo '${key}=${safeValue}' >> ${ENV_PATH}`)
    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to add environment variable',
    }
  }
}

export async function updateEnvVar(key: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    // Validate key format
    if (!/^[A-Z_][A-Z0-9_]*$/.test(key)) {
      return { success: false, error: 'Invalid environment variable name' }
    }

    const safeValue = value.replace(/'/g, "'\\''")
    const safeKey = key.replace(/'/g, "'\\''")

    // Check if key already exists
    const { stdout: exists } = await dockerExec(
      `grep -c "^${safeKey}=" ${ENV_PATH} 2>/dev/null || echo 0`
    )

    if (parseInt(exists.trim()) > 0) {
      // Update existing line
      await dockerExec(
        `sed -i 's|^${safeKey}=.*|${safeKey}=${safeValue}|' ${ENV_PATH}`
      )
    } else {
      // Append new line
      await dockerExec(
        `echo '${safeKey}=${safeValue}' >> ${ENV_PATH}`
      )
    }

    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update environment variable',
    }
  }
}
