'use server'

import { readFile } from 'node:fs/promises'
import yaml from 'js-yaml'
import { cabinetPath } from '@/lib/cabinet-root'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import type { ConnectorTemplateChoice, ConnectorTemplateField } from '@/lib/onboarding/types'

// The curated pick-list, shipped as DATA in the instance layer so the framework
// (and this dashboard) name no vendor in code — the tool names live in the file.
// Overridable for tests. Absent ⇒ an empty list, and the connect step falls
// back to "point me at a folder", which always works.
const templatesPath = () =>
  process.env.CABINET_CONNECTOR_TEMPLATES ||
  cabinetPath('instance/config/connector-templates.yml.example')

/**
 * Read the connector-template pack and project it to what the connect step
 * draws. This reads a NON-secret DATA file — never cabinet/.env, never a
 * connector body beyond the host and env var NAME. A malformed pack yields an
 * empty list rather than an exception, because the pick-list is a convenience
 * and its absence must not take onboarding down.
 */
export async function getConnectorTemplates(): Promise<ConnectorTemplateChoice[]> {
  if (!(await requireDashboardAuth())) throw new Error('Unauthorized')

  let doc: unknown
  try {
    doc = yaml.load(await readFile(templatesPath(), 'utf8'))
  } catch {
    return []
  }
  const templates =
    doc && typeof doc === 'object' && 'templates' in doc
      ? (doc as { templates?: unknown }).templates
      : null
  if (!Array.isArray(templates)) return []

  const choices: ConnectorTemplateChoice[] = []
  for (const raw of templates) {
    if (!raw || typeof raw !== 'object') continue
    const tpl = raw as Record<string, unknown>
    const id = String(tpl.id ?? '').trim()
    const connector = tpl.connector as Record<string, unknown> | undefined
    // The same floor the core's loader holds a template to: an id, and a
    // connector whose inventory is a mapping. A half-built one is dropped, so
    // the surface never offers a tool the core would then refuse to build.
    const usable =
      id !== '' &&
      connector != null &&
      typeof connector === 'object' &&
      typeof connector.inventory === 'object'
    if (!usable) continue

    const fields: ConnectorTemplateField[] = (Array.isArray(tpl.fields) ? tpl.fields : [])
      .map((f) => (f && typeof f === 'object' ? (f as Record<string, unknown>) : null))
      .filter((f): f is Record<string, unknown> => f != null && String(f.key ?? '').trim() !== '')
      .map((f) => ({
        key: String(f.key).trim(),
        label: String(f.label ?? f.key).trim(),
        help: String(f.help ?? '').trim(),
        placeholder: String(f.placeholder ?? '').trim(),
        required: Boolean(f.required),
      }))

    choices.push({
      id,
      label: String(tpl.label ?? id).trim(),
      summary: String(tpl.summary ?? '').trim(),
      host: String(tpl.host ?? '').trim(),
      credential_env: String(tpl.credential_env ?? '').trim(),
      credential_help: String(tpl.credential_help ?? '').trim(),
      fields,
    })
  }
  // Concrete tools first, the open-ended "rest" last — it is the fallback, not
  // the headline.
  choices.sort(
    (a, b) => Number(a.id === 'rest') - Number(b.id === 'rest') || a.label.localeCompare(b.label)
  )
  return choices
}
