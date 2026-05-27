'use server'

import { dockerExec, getEnvVars as dockerGetEnvVars } from '@/lib/docker'
import { revalidatePath } from 'next/cache'

// Path to cabinet/.env INSIDE the cabinet-officers container (or the
// equivalent location when the dashboard runs Mac-native). Override via
// CABINET_ENV_PATH env var. Default keeps backward compatibility with the
// Docker deployment that ships /opt/founders-cabinet today; the Mac-native
// dashboard reads CABINET_ROOT (set by deploy-mac.sh / start-officer-mac.sh)
// and resolves to ${CABINET_ROOT}/cabinet/.env so the env-var editor
// actually writes the file the cabinet reads.
const ENV_PATH = (
  process.env.CABINET_ENV_PATH ||
  (process.env.CABINET_ROOT ? `${process.env.CABINET_ROOT}/cabinet/.env` : null) ||
  '/opt/founders-cabinet/cabinet/.env'
)

export async function getEnvVarsAction(): Promise<Record<string, string>> {
  return dockerGetEnvVars()
}

export async function deleteEnvVar(key: string) {
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
