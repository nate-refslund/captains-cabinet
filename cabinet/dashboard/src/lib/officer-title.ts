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
 * Role words a lane officer's slug may END in, mapped to how they are WRITTEN.
 *
 * Deliberately tiny and deliberately a closed set: a trailing token is only
 * read as a role when it is unambiguously one, so `bakery-ceo` splits into the
 * `bakery` lane plus "CEO" while `first-lane` (a lane, not an officer) does
 * not split at all. Nothing here names a product, a person or an industry —
 * the LANE supplies the noun, this supplies only the job word.
 */
export const ROLE_WORDS: Record<string, string> = {
  ceo: 'CEO',
  cto: 'CTO',
  cpo: 'CPO',
  cro: 'CRO',
  coo: 'COO',
  officer: 'Officer',
  lead: 'Lead',
}

/**
 * Split `<lane>-<role>` into its two halves, or `null` when the slug does not
 * end in a role word. Pure string work — the caller supplies lane names.
 */
export function splitLaneRole(role: string): { lane: string; roleWord: string } | null {
  const cut = role.lastIndexOf('-')
  if (cut <= 0) return null
  const tail = role.slice(cut + 1).toLowerCase()
  const word = ROLE_WORDS[tail]
  if (!word) return null
  return { lane: role.slice(0, cut), roleWord: word }
}

/**
 * Everything a caller can teach the resolver about THIS deployment.
 *
 * Both maps are deployment-local facts read server-side (`lib/crew-roster.ts`)
 * and passed in, so this module stays pure and client-safe:
 *   `titles` — `instance/config/roster.yml` `<slug>.title`, the hire record's
 *              own words ("First Lane CEO"), which is what the operator named;
 *   `laneNames` — `instance/config/contexts/<lane>.yml` `name`, so an officer
 *              the roster has not hired yet still reads as its LANE plus its
 *              job word rather than as a slug.
 */
export interface OfficerNameSources {
  titles?: Record<string, string>
  laneNames?: Record<string, string>
}

/**
 * Resolve an officer slug to the name a human reads.
 *
 * The chain, widest-known first:
 *   1. a framework officer's configured title (`cos` → "First Mate");
 *   2. this deployment's roster title — the hire record's own words;
 *   3. the officer's LANE display name plus its job word ("First Lane CEO"),
 *      which is what #346's rule means for a lane officer the roster has not
 *      hired: the name comes from the thing it belongs to, never from its id;
 *   4. readable Title Case of the slug, the last resort that at least reads as
 *      words.
 *
 * Step 3 is why "Hired Lane Ceo" was a defect rather than a cosmetic nit: it
 * was a machine id title-cased and printed where a person's name goes, about
 * an officer the operator never chose. Calling it by its lane says what it
 * actually is.
 */
export function officerTitle(role: string, sources: OfficerNameSources = {}): string {
  const known = OFFICER_TITLES[role]
  if (known) return known

  const rostered = sources.titles?.[role]
  if (rostered && rostered.trim()) return rostered.trim()

  const split = splitLaneRole(role)
  if (split) {
    const laneName = sources.laneNames?.[split.lane]
    if (laneName && laneName.trim()) return `${laneName.trim()} ${split.roleWord}`
    // No lane declaration either — still better than a slug shout: Title Case
    // the lane half and keep the job word spelled the way it is written.
    return `${titleCaseSlug(split.lane)} ${split.roleWord}`
  }

  return titleCaseSlug(role)
}
