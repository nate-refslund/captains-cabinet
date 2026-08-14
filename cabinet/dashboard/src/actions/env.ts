'use server'

import { cabinetPath } from '@/lib/cabinet-root'
import { assertRuntimeWritesAllowed, getEnvVars as dockerGetEnvVars } from '@/lib/docker'
import { ensureEnvFile, readEnvDocument, removeEnvKey, writeEnvValue } from '@/lib/config-write'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'

// Path to the checkout's cabinet/.env. Override via CABINET_ENV_PATH env var;
// otherwise resolved from CABINET_ROOT (set by deploy-mac.sh /
// start-officer-mac.sh / start-dashboard.sh) so the env-var editor writes the
// file the cabinet reads.
//
// A FUNCTION, not a module constant, for the reason `lib/cabinet-root.ts` gives:
// the variable is honoured per call, so a process that resolves the checkout
// after this module loads — and any test that sandboxes its writes — edits the
// path that is live at write time rather than at import time.
const envPath = () => process.env.CABINET_ENV_PATH || cabinetPath('cabinet/.env')

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
    assertRuntimeWritesAllowed(`delete ${key} from cabinet/.env`)
    await removeEnvKey(envPath(), key)
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
    assertRuntimeWritesAllowed(`add ${key} to cabinet/.env`)
    // The duplicate check now reads the same document the write edits, in this
    // process. It used to be `grep -c` through the shell — a second read of the
    // file with a gap in between, and a `parseInt` of whatever the shell said.
    const existing = await readEnvDocument(envPath())
    if (key in existing) {
      return { success: false, error: `${key} already exists — edit it instead` }
    }
    await writeEnvValue(envPath(), key, value, { createIfMissing: true })
    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to add environment variable',
    }
  }
}

// Store a connector credential in cabinet/.env under `key`, from the onboarding
// connect flow. It is the ONLY path a credential VALUE travels — the connector
// declaration that follows carries the env var NAME, never this value. Upsert
// (set-or-append) through the same safe writer addEnvVar uses: a provably-inert
// value is written bare so it round-trips, anything else is single-quoted so it
// cannot execute when cabinet/.env is `source`d, and a newline is refused.
export async function saveConnectorCredential(key: string, value: string) {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  try {
    if (!/^[A-Z_][A-Z0-9_]*$/.test(key)) {
      return { success: false, error: 'Invalid name — use UPPER_SNAKE_CASE' }
    }
    assertRuntimeWritesAllowed(`store ${key} in cabinet/.env`)
    await ensureEnvFile(envPath())
    await writeEnvValue(envPath(), key, value, { createIfMissing: true })
    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Could not store the credential',
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
    assertRuntimeWritesAllowed(`set ${key} in cabinet/.env`)
    // Set-or-append in one read → transform → atomic write → read-back. The old
    // shape ran `grep -c` and then either `sed -i 's|^KEY=.*|KEY=v|'` — which
    // exits 1 and changes nothing under BSD sed, i.e. on the only machine this
    // runs on — or an `echo >>` that interpolated the value into a shell string.
    await writeEnvValue(envPath(), key, value, { createIfMissing: true })

    revalidatePath('/integrations')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update environment variable',
    }
  }
}
