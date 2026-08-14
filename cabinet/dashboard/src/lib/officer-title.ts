/**
 * The officer display-title resolver — the ONE place a human name for an
 * officer is decided, so every user-facing surface reads the same thing.
 *
 * Why its own module (no `fs`/`yaml` imports): `config.ts` is server-only, but
 * client components (task-board columns) also name officers. A pure resolver
 * both sides can import keeps a single source of truth without dragging Node
 * built-ins into the client bundle.
 *
 * INSTANCE/PRESET layer, never a framework literal: the framework never names
 * an officer. The machine id `cos` is FROZEN — dozens of enforcement, launchd
 * and redis surfaces key on it — so the fix for "COS is offline" was never to
 * rename the id; it is to stop printing the raw id where a name belongs. A
 * known officer resolves to its configured title here; an unknown custom lane
 * degrades to readable Title Case, never a raw uppercased shout (a machine id
 * masquerading as a person).
 *
 * The coordinator is "First Mate" (Captain ruling: not "COS", not "Chief of
 * Staff", not "Chair"; the clean name, no parenthetical).
 */
/**
 * The COORDINATING officer's machine id. Frozen for the reason above — dozens
 * of enforcement, launchd and redis surfaces key on it — and exported so a
 * surface that needs to say who is speaking resolves the NAME through
 * `officerTitle` instead of writing one down. A hardcoded "First Mate" in a
 * component is a second place the Captain's naming ruling has to be applied,
 * and the one that will be missed when it changes.
 */
export const COORDINATOR_ROLE = 'cos'

export const OFFICER_TITLES: Record<string, string> = {
  cos: 'First Mate',
  cto: 'Chief Technology Officer (CTO)',
  cpo: 'Chief Product Officer (CPO)',
  cro: 'Chief Research Officer (CRO)',
  coo: 'Chief Operations Officer (COO)',
}

/**
 * A slug with no configured title and no usable heading, rendered readably:
 * Title Case over word separators, never `role.toUpperCase()`. Only an unknown
 * custom lane ever reaches here — a known officer short-circuits to its title.
 * "bakery-ceo" → "Bakery Ceo", "xyz" → "Xyz": not the name we would pick, but
 * a readable placeholder rather than a slug shouted as if it were a person.
 */
export function titleCaseSlug(role: string): string {
  const words = role.split(/[-_\s]+/).filter(Boolean)
  if (words.length === 0) return role
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

/**
 * Resolve an officer slug to the name a human reads. Known id → its configured
 * title; anything else → a readable Title Case of the slug. Never returns a
 * raw uppercased slug for a known officer — that is the defect this exists to
 * abolish.
 */
export function officerTitle(role: string): string {
  return OFFICER_TITLES[role] || titleCaseSlug(role)
}
