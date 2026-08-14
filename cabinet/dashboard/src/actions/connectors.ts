'use server'

import { readFile } from 'node:fs/promises'
import yaml from 'js-yaml'
import { cabinetPath } from '@/lib/cabinet-root'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import type {
  ConnectorCatalog,
  ConnectorTemplateChoice,
  ConnectorTemplateField,
} from '@/lib/onboarding/types'

// The curated catalog, shipped as DATA in the instance layer so the framework
// (and this dashboard) name no vendor in code — the tool names live in the file.
// Overridable for tests. Absent ⇒ an empty list, and the connect step falls
// back to "point me at a folder", which always works.
const templatesPath = () =>
  process.env.CABINET_CONNECTOR_TEMPLATES ||
  cabinetPath('instance/config/connector-templates.yml.example')

// The shelf a template lands on when its pack entry names no category, or names
// one the pack never declared. A browsable catalog needs every entry to be
// SOMEWHERE: silently dropping an uncategorised tool would hide a connectable
// source behind a data typo.
const OTHER = 'other'
const OTHER_LABEL = 'Anything else'

/** Trim to a string, whatever the YAML put there. */
const text = (value: unknown): string => String(value ?? '').trim()

/**
 * The steps a template lists for producing its credential, as an ordered list of
 * plain sentences. A single string is accepted as a one-step list so a terse
 * pack entry is not silently stepless; anything else yields `[]`, and the step
 * renders with no instructions rather than with half of them.
 */
function steps(value: unknown): string[] {
  if (typeof value === 'string') return text(value) ? [text(value)] : []
  if (!Array.isArray(value)) return []
  return value.map(text).filter((step) => step !== '')
}

/**
 * Read the connector-template pack and project it to what the connect step
 * draws. This reads a NON-secret DATA file — never cabinet/.env, never a
 * connector body beyond the host and env var NAME. A malformed pack yields an
 * empty catalog rather than an exception, because the catalog is a convenience
 * and its absence must not take onboarding down.
 */
export async function getConnectorCatalog(): Promise<ConnectorCatalog> {
  if (!(await requireDashboardAuth())) throw new Error('Unauthorized')

  let doc: unknown
  try {
    doc = yaml.load(await readFile(templatesPath(), 'utf8'))
  } catch {
    return { templates: [], categories: [] }
  }
  const root = doc && typeof doc === 'object' ? (doc as Record<string, unknown>) : null
  const templates = root?.templates
  if (!Array.isArray(templates)) return { templates: [], categories: [] }

  // The shelf LABELS are data too: the framework names no vendor and no vertical,
  // so "Where your code lives" is a string in the pack, not a constant here.
  const labels = new Map<string, string>()
  const declared = root?.categories
  if (declared && typeof declared === 'object' && !Array.isArray(declared)) {
    for (const [id, label] of Object.entries(declared as Record<string, unknown>)) {
      if (text(id) && text(label)) labels.set(text(id), text(label))
    }
  }

  const choices: ConnectorTemplateChoice[] = []
  for (const raw of templates) {
    if (!raw || typeof raw !== 'object') continue
    const tpl = raw as Record<string, unknown>
    const id = text(tpl.id)
    const connector = tpl.connector as Record<string, unknown> | undefined
    // The same floor the core's loader holds a template to: an id, and a
    // connector declaring a read call in one of the two lanes — `inventory:`
    // for a list of the operator's own things, `search:` for a question sent
    // out. A half-built one is dropped, so the surface never offers a tool the
    // core would then refuse to build. MIRRORED, not derived: the core is the
    // authority (`research._spec_kind`), and this file exists on the other side
    // of a process boundary, so it re-states the floor rather than importing it.
    const usable =
      id !== '' &&
      connector != null &&
      typeof connector === 'object' &&
      (typeof connector.inventory === 'object' || typeof connector.search === 'object')
    if (!usable) continue

    const fields: ConnectorTemplateField[] = (Array.isArray(tpl.fields) ? tpl.fields : [])
      .map((f) => (f && typeof f === 'object' ? (f as Record<string, unknown>) : null))
      .filter((f): f is Record<string, unknown> => f != null && text(f.key) !== '')
      .map((f) => ({
        key: text(f.key),
        label: text(f.label) || text(f.key),
        help: text(f.help),
        placeholder: text(f.placeholder),
        required: Boolean(f.required),
      }))

    const category = text(tpl.category)
    const shelf = category && labels.has(category) ? category : OTHER
    choices.push({
      id,
      label: text(tpl.label) || id,
      summary: text(tpl.summary),
      host: text(tpl.host),
      credential_env: text(tpl.credential_env),
      credential_help: text(tpl.credential_help),
      fields,
      category: shelf,
      category_label: labels.get(shelf) ?? OTHER_LABEL,
      how_to_connect: steps(tpl.how_to_connect),
      key_looks_like: text(tpl.key_looks_like),
    })
  }
  // Alphabetical within the catalog, with the open-ended `rest` template last —
  // it is the fallback for everything the pack does not name, not the headline.
  choices.sort(
    (a, b) => Number(a.id === 'rest') - Number(b.id === 'rest') || a.label.localeCompare(b.label)
  )

  // Shelves in the pack's own declared ORDER (a pack author groups them the way
  // an operator reads them), with anything uncategorised last. A shelf nothing
  // sits on is not offered: an empty filter is a dead tap.
  const counts = new Map<string, number>()
  for (const choice of choices) counts.set(choice.category, (counts.get(choice.category) ?? 0) + 1)
  const categories = [...labels.keys(), OTHER]
    .filter((id) => (counts.get(id) ?? 0) > 0)
    .map((id) => ({
      id,
      label: id === OTHER ? OTHER_LABEL : (labels.get(id) as string),
      count: counts.get(id) as number,
    }))

  return { templates: choices, categories }
}
