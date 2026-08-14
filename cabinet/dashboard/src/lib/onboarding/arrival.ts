/**
 * The arrival summary — assembled from the operator's own recorded answers.
 *
 * WHY THIS IS A DATA STRUCTURE AND NOT A PARAGRAPH. A summary is the easiest
 * place in the whole product to invent: prose is expected there, a plausible
 * sentence costs nothing to write, and nobody checks a closing screen the way
 * they check a finding. So every clause here declares WHERE IN THE JOURNEY
 * STATE it came from, and its words are read out of that path. A clause whose
 * answer is absent does not exist — the screen says less, never something
 * likelier. `arrival.test.ts` asserts both halves: each clause's declared path
 * resolves in a real journey state, and each clause's value appears verbatim in
 * that state.
 *
 * WHAT IT CANNOT PROVE, said plainly: the arm compares the clause's VALUE to
 * the state, not the connective words around it ("You told me:", "You approved
 * read-only access to"). Those are fixed strings in the table below, reviewed
 * once, and they make claims — "you told me", "you approved" — that are true by
 * construction of the path each one is attached to. Changing a label without
 * changing its path is the one edit this file's tests cannot catch, and it is
 * why the labels sit beside the paths rather than in the component.
 */
import type { OnboardingState } from './types'

export interface ArrivalClause {
  id: string
  /**
   * What the operator DID to put this on the record. It is the provenance of
   * the clause, shown beside it — the no-invention law made visible rather
   * than merely obeyed.
   */
  provenance: string
  /** The dotted path in the journey state this was read from. */
  path: string
  /** The recorded answer, verbatim. */
  value: string
  /** The sentence, built from `value` and this clause's fixed connective words. */
  text: string
}

/** Reads a dotted path, returning undefined rather than throwing on a gap. */
export function readPath(state: unknown, path: string): unknown {
  let cursor: unknown = state
  for (const key of path.split('.')) {
    if (cursor === null || typeof cursor !== 'object') return undefined
    cursor = (cursor as Record<string, unknown>)[key]
  }
  return cursor
}

/** A trimmed string, or '' for anything that is not usable text. */
function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

/**
 * ONE ROW PER RECORDED ANSWER, in the order they are worth reading: who the
 * operator is, whose work this is, what they granted, and what came back.
 *
 * The order is also the priority — see `ARRIVAL_CLAUSE_LIMIT`.
 */
const CLAUSES: readonly {
  id: string
  provenance: string
  path: string
  say: (value: string, state: OnboardingState) => string
}[] = [
  {
    id: 'who',
    provenance: 'you told me',
    path: 'seed.text',
    say: (value) => `“${value}”`,
  },
  {
    id: 'organization',
    provenance: 'you told me',
    path: 'organization.name',
    say: (value) => `This Cabinet is for ${value}.`,
  },
  {
    id: 'window',
    provenance: 'you approved',
    // The PATH, never just its last segment. The core learned this the hard
    // way on the Charter card: consent to a basename is not consent to a path,
    // and two different folders make the same sentence when only the name is
    // shown. The arrival repeats back exactly what was approved.
    path: 'source.root',
    say: (value) => `Read-only access to ${value}, and nothing else.`,
  },
  {
    id: 'finding',
    provenance: 'I found',
    path: 'first_dividend.finding.summary',
    // The headline only: the first sentence of the recorded finding, with the
    // rest one click away under "What I found". Layered, never deleted — this
    // is a summary screen, and the complete text with its citations is on the
    // same page below.
    say: (value) => value,
  },
  {
    id: 'tools',
    provenance: 'you connected',
    path: 'connector_sweep.connectors',
    say: (value) => `${value}.`,
  },
]

/**
 * How many clauses the summary shows. Four, because the ruling that ordered
 * this screen asked for three to four and because a summary that lists
 * everything is the accumulating card this screen exists to replace.
 *
 * NOTHING IS LOST TO THE CAP: every clause beyond it names something that has
 * its own section further down the same screen (the window, the finding, the
 * connected tools), so the cap moves a fact rather than dropping one.
 */
export const ARRIVAL_CLAUSE_LIMIT = 4

/** The first sentence of a recorded finding, or the whole thing if it is one. */
function headline(summary: string): string {
  const stop = summary.search(/[.!?](\s|$)/)
  return stop < 0 ? summary : summary.slice(0, stop + 1)
}

/**
 * What is now true, in the operator's own answers. Empty when the journey
 * carries none of them — a state that cannot reach the arrival, and which the
 * screen renders as its headline alone rather than as invented reassurance.
 */
export function arrivalClauses(state: OnboardingState | null | undefined): ArrivalClause[] {
  if (!state) return []
  const out: ArrivalClause[] = []
  for (const clause of CLAUSES) {
    const raw = readPath(state, clause.path)
    let value = ''
    if (clause.id === 'tools') {
      const names = Array.isArray(raw)
        ? raw.map((row) => text((row as { name?: unknown })?.name)).filter(Boolean)
        : []
      if (!names.length) continue
      value = names.join(', ')
    } else if (clause.id === 'finding') {
      const summary = text(raw)
      if (!summary) continue
      value = headline(summary)
    } else {
      value = text(raw)
      if (!value) continue
    }
    out.push({
      id: clause.id,
      provenance: clause.provenance,
      path: clause.path,
      value,
      text: clause.say(value, state),
    })
  }
  return out
}
