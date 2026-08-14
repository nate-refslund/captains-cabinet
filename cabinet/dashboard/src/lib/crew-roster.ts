/**
 * WHO IS ON THIS DEPLOYMENT'S CREW, and what each one is called.
 *
 * The hire record is `instance/config/roster.yml` — the same file
 * `deploy-mac.sh` derives the officer fleet from and `cabinet/scripts/
 * lib_roster.py` parses for Cabinet Doctor. Reading it here rather than
 * re-deriving the roster from store keys is the point: the store says who is
 * REPORTING, the roster says who was HIRED, and the difference between those
 * two sets is exactly what the home card was getting wrong (it alarmed about a
 * generated-but-never-hired lane CEO as though a real officer had died).
 *
 * Lane display names come from `instance/config/contexts/<lane>.yml`, the
 * declaration the operator's own answers produced. That is where "First Lane
 * CEO" comes from instead of "Hired Lane Ceo".
 *
 * ABSENCE IS NOT AN ERROR. A checkout with no roster yet is a legal state
 * (`lib_roster.load_roster` makes the same call for the same reason): it
 * yields zero hires, and every reading downstream degrades to "not hired",
 * never to an invented officer.
 *
 * SERVER ONLY — `fs` + `js-yaml`. The pure half every surface shares is
 * `lib/officer-title.ts`; this module only supplies it with facts.
 */

import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'
import { cabinetPath } from './cabinet-root'
import type { OfficerNameSources } from './officer-title'

export interface RosterMember {
  slug: string
  /** `roster.yml` `<slug>.title`, when the hire record carries one. */
  title: string | null
  /** `type: consultant` — on-demand, never a keepalive LaunchAgent. */
  onDemand: boolean
}

function rosterPath(): string {
  return process.env.CABINET_ROSTER_PATH || cabinetPath('instance/config/roster.yml')
}

function contextsDir(): string {
  return process.env.CABINET_CONTEXTS_DIR || cabinetPath('instance/config/contexts')
}

/**
 * The hire record, in file order. An unreadable or malformed roster yields an
 * EMPTY list rather than throwing: this feeds a render, and the honest render
 * of "we could not read the hire record" is "nothing is hired here", which
 * makes every officer read as un-hired rather than as a fault.
 */
export function readRoster(): RosterMember[] {
  let raw: string
  try {
    raw = fs.readFileSync(rosterPath(), 'utf8')
  } catch {
    return []
  }
  let doc: unknown
  try {
    doc = yaml.load(raw)
  } catch {
    return []
  }
  const roster = (doc as { roster?: unknown } | null)?.roster
  if (!roster || typeof roster !== 'object' || Array.isArray(roster)) return []

  const members: RosterMember[] = []
  for (const [slug, fields] of Object.entries(roster as Record<string, unknown>)) {
    if (!/^[a-z0-9-]+$/.test(slug)) continue
    const row = (fields && typeof fields === 'object' ? fields : {}) as Record<string, unknown>
    const title = typeof row.title === 'string' && row.title.trim() ? row.title.trim() : null
    const type = typeof row.type === 'string' ? row.type.toLowerCase() : 'fulltime'
    members.push({ slug, title, onDemand: type === 'consultant' })
  }
  return members
}

/**
 * `<lane-slug> → display name` from every lane declaration on disk.
 *
 * The filename is NOT trusted as the slug: the file's own `slug:` key is, and
 * a declaration missing either key is skipped rather than half-read.
 */
export function readLaneNames(): Record<string, string> {
  let entries: string[]
  try {
    entries = fs.readdirSync(contextsDir())
  } catch {
    return {}
  }
  const names: Record<string, string> = {}
  for (const entry of entries) {
    if (!entry.endsWith('.yml') || entry.endsWith('.yml.example')) continue
    let doc: unknown
    try {
      doc = yaml.load(fs.readFileSync(path.join(contextsDir(), entry), 'utf8'))
    } catch {
      continue
    }
    const row = (doc && typeof doc === 'object' ? doc : {}) as Record<string, unknown>
    const slug = typeof row.slug === 'string' ? row.slug.trim() : ''
    const name = typeof row.name === 'string' ? row.name.trim() : ''
    if (!slug || !name || !/^[a-z0-9-]+$/.test(slug)) continue
    names[slug] = name
  }
  return names
}

/** Everything `officerTitle` needs to name this deployment's officers. */
export function officerNameSources(roster?: RosterMember[]): OfficerNameSources {
  const members = roster ?? readRoster()
  const titles: Record<string, string> = {}
  for (const m of members) if (m.title) titles[m.slug] = m.title
  return { titles, laneNames: readLaneNames() }
}
