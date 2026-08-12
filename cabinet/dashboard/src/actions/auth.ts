'use server'

import { createSession, destroySession, checkPassword } from '@/lib/auth'
import { redirect } from 'next/navigation'
import { headers } from 'next/headers'
import { cabinetPath } from '@/lib/cabinet-root'
import { readEnvDocument, writeEnvValue } from '@/lib/config-write'
import {
  hasRealPassword,
  isLocalRequest,
  validateChosenPassword,
} from '@/lib/first-run'

// Path to the checkout's cabinet/.env — the SAME store every other secret lives
// in and the SAME one actions/env.ts writes. Override via CABINET_ENV_PATH;
// otherwise resolve from CABINET_ROOT (set by start-dashboard.sh). A function,
// not a const, so a test that sandboxes the path and a server that resolves the
// checkout after this module loads both edit the file that is live at write time.
const envPath = () => process.env.CABINET_ENV_PATH || cabinetPath('cabinet/.env')

export async function login(
  _prevState: { error: string } | null,
  formData: FormData
) {
  const password = formData.get('password') as string
  if (!checkPassword(password)) {
    return { error: 'Invalid password' }
  }
  await createSession()
  redirect('/')
}

export async function logout() {
  await destroySession()
  redirect('/login')
}

/**
 * FIRST-RUN: the operator chooses their own dashboard password.
 *
 * This is the ONE action allowed before any password exists. Its two guards are
 * the whole security of that window:
 *
 *   1. FIRST-RUN ONLY. If a real password already exists — in this live process
 *      OR in the durable cabinet/.env — this is inert. Without that, anyone who
 *      could reach /login (which is exempt from the auth middleware by design)
 *      could overwrite the password and take the door.
 *   2. LOCAL ONLY. The request must come from the Cabinet computer itself, so a
 *      tailnet peer cannot claim the password during the un-set window.
 *
 * On success it writes the password to the SAME plaintext store the verifier
 * reads (DASHBOARD_PASSWORD in cabinet/.env — plaintext because that value is
 * also the HMAC key that signs the session cookie, so it cannot be one-way
 * hashed), sets it live in THIS process so the session below is valid with no
 * restart, mints the session, and lands the operator on the dashboard.
 */
export async function createPassword(
  _prevState: { error: string } | null,
  formData: FormData
) {
  // Guard 1a — the live process already has a real password.
  if (hasRealPassword()) {
    return { error: 'A password is already set. Enter it to sign in.' }
  }
  // Guard 1b — the durable file already has one, even if this process has not
  // loaded it yet. A missing/unreadable .env is the normal first-run state.
  let stored: { DASHBOARD_PASSWORD?: string } = {}
  try {
    stored = await readEnvDocument(envPath())
  } catch {
    stored = {}
  }
  if (hasRealPassword(stored)) {
    return { error: 'A password is already set. Enter it to sign in.' }
  }

  // Guard 2 — only from the machine the dashboard runs on.
  if (!isLocalRequest(await headers())) {
    return {
      error: 'For safety, choose your first password on the Cabinet computer itself.',
    }
  }

  const password = (formData.get('password') as string) ?? ''
  const confirm = (formData.get('confirm') as string) ?? ''
  const check = validateChosenPassword(password, confirm)
  if (!check.ok) {
    return { error: check.error }
  }

  try {
    await writeEnvValue(envPath(), 'DASHBOARD_PASSWORD', password, {
      createIfMissing: true,
    })
  } catch (err) {
    return {
      error: err instanceof Error ? err.message : 'Could not save the password.',
    }
  }
  // Live in this process (middleware runs in the Node runtime, so it shares this
  // env) — the session minted next is immediately valid, no dashboard restart.
  process.env.DASHBOARD_PASSWORD = password

  await createSession()
  redirect('/')
}
