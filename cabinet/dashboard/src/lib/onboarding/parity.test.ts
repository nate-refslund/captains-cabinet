/**
 * core ↔ surface parity — the sensor that was missing while the journey grew
 * two dead-end buttons.
 *
 * `framework/onboarding/journey.py` owns the action vocabulary. Three
 * TypeScript surfaces mirror it by hand — the bridge's admission set, the
 * action union, and Telegram's command table — and nothing compared them, so
 * `answer_salience` existed in the core, was printed on the card as an option,
 * and was refused by the bridge as `action_invalid` before the core ever saw
 * it. The core's own source says so in as many words, in the note beside
 * `salience_relation`: a question printed with no way to send an answer is a
 * dead end wearing an invitation's clothes.
 *
 * WHAT IS COMPARED, AND AGAINST WHAT. Two of the three mirrors are imported and
 * compared as LIVE objects (`ACTIONS` from the bridge, `ONBOARDING_ACTIONS` from
 * types) rather than re-parsed from their own source — a sensor pointed at a
 * copy of the control is the dominant failure class in this program's own
 * history. The union is pinned to `ONBOARDING_ACTIONS` at COMPILE time (see
 * `ActionsAgree` in ./types), so `tsc --noEmit` carries that arm and this file
 * carries the rest. The Python side and Telegram's command table are parsed,
 * because neither can be imported here.
 *
 * FULL CONSUMPTION, EVERYWHERE. Every parser below throws on input it cannot
 * read rather than skipping it. A tripwire that silently drops what it does not
 * understand is not a tripwire: a dispatch branch written at another indent, or
 * a relation entry wrapped across two lines, would vanish from the expected set
 * and the comparison would go green while the surfaces diverged.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { ACTIONS } from './bridge'
import { ONBOARDING_ACTIONS, WINDOW_RELATIONS } from './types'

// <root>/cabinet/dashboard/src/lib/onboarding → five levels up = <root>
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..')
const CORE = path.join(REPO_ROOT, 'framework', 'onboarding', 'journey.py')
const TELEGRAM = path.resolve(__dirname, 'telegram.ts')

/**
 * Telegram branches the core's own vocabulary deliberately does NOT get, each
 * with the reason it cannot have one. An exemption is a claim about the
 * channel, not a to-do: "not wired yet" is drift with a note on it, and the
 * test below refuses an empty or placeholder reason so this map cannot become
 * a place to file work and call the gate green.
 */
const TELEGRAM_EXEMPT: Record<string, string> = {
  record_operator_identity:
    'carries a handles map over connectors whose candidate lists run to dozens ' +
    'of estate-spelled account identifiers; the core requires a picker (a typed ' +
    'spelling the estate does not use resolves the operator and attributes ' +
    'nothing) and an inline keyboard cannot carry that offer inside the 64-byte ' +
    'callback_data bound. A Telegram identity picker is its own unit.',
}

const PLACEHOLDER = /\b(tbd|todo|later|not (yet )?wired|coming soon|n\/?a)\b/i

function read(file: string): string {
  expect(
    fs.existsSync(file),
    `expected ${file} — parity cannot be verified without it, and an absent ` +
      'source IS drift rather than a reason to skip'
  ).toBe(true)
  return fs.readFileSync(file, 'utf8')
}

/**
 * The body of a top-level `def <name>(` up to the next column-0 `def`/`class`.
 */
function pythonFunctionBody(source: string, name: string): string {
  const start = source.search(new RegExp(`^def ${name}\\(`, 'm'))
  if (start < 0) throw new Error(`no top-level def ${name}( in the core`)
  const rest = source.slice(start)
  const end = rest.slice(1).search(/^(def |class )/m)
  return end < 0 ? rest : rest.slice(0, end + 1)
}

const DISPATCH_RE = /^ {8}if action == "([a-z_]+)":$/
const STRAY_COMPARISON_RE = /\baction\s*==\s*["']/

/**
 * Every action `_act_core` dispatches on — the vocabulary of record.
 *
 * Full consumption: any OTHER line in that function comparing `action` to a
 * string literal throws. A branch written as `elif`, at a different indent, or
 * against a tuple would otherwise be silently absent from the expected set,
 * which would let a surface drop it and stay green.
 */
function coreDispatchActions(source: string): string[] {
  const body = pythonFunctionBody(source, '_act_core')
  const found: string[] = []
  const unreadable: string[] = []
  for (const line of body.split('\n')) {
    const match = line.match(DISPATCH_RE)
    if (match) {
      found.push(match[1])
      continue
    }
    if (STRAY_COMPARISON_RE.test(line)) unreadable.push(line.trim())
  }
  if (unreadable.length > 0) {
    throw new Error(
      'unreadable action-dispatch line(s) in _act_core — every branch must be ' +
        'a single-line `if action == "name":` at eight spaces, or it is missing ' +
        'from the parity check (a hole in the tripwire, not a formatting nit):' +
        `\n  ${unreadable.join('\n  ')}`
    )
  }
  return found
}

/**
 * Every action the core can put on a card, from the `{"action": "name"}`
 * literals it builds options and `next_actions` out of.
 */
function coreOfferedActions(source: string): string[] {
  return [...source.matchAll(/"action":\s*"([a-z_]+)"/g)].map((m) => m[1])
}

const RELATION_ENTRY_RE = /^\s*(['"])([a-z_]+)\1\s*:\s*(['"])(.*?)\3\s*,?\s*(?:#.*)?$/

/** `WINDOW_RELATIONS = { "key": "sentence", … }`, read as a plain record. */
function coreWindowRelations(source: string): Record<string, string> {
  const assignment = source.match(/^WINDOW_RELATIONS\s*=\s*\{([\s\S]*?)^\}/m)
  if (!assignment) {
    throw new Error(
      'no module-level WINDOW_RELATIONS dict in the core — the surface mirror ' +
        'cannot be parity-checked without it'
    )
  }
  const entries: Record<string, string> = {}
  const unreadable: string[] = []
  for (const line of assignment[1].split('\n')) {
    if (!line.trim() || /^\s*#/.test(line)) continue
    const match = line.match(RELATION_ENTRY_RE)
    if (!match) {
      unreadable.push(line.trim())
      continue
    }
    entries[match[2]] = match[4]
  }
  if (unreadable.length > 0) {
    throw new Error(
      'unreadable WINDOW_RELATIONS line(s) — every entry must be a single-line ' +
        `'key': 'sentence' pair or it vanishes from the check:\n  ${unreadable.join('\n  ')}`
    )
  }
  return entries
}

/** Every action Telegram's command/callback table can actually dispatch. */
function telegramActions(source: string): string[] {
  return [...source.matchAll(/\baction\(\s*'([a-z_]+)'/g)].map((m) => m[1])
}

const core = read(CORE)
const dispatch = coreDispatchActions(core)
const sorted = (values: Iterable<string>): string[] => [...new Set(values)].sort()

describe('the core dispatch chain is readable at all', () => {
  it('parses a non-trivial set of actions', () => {
    expect(
      dispatch.length,
      'parsed zero dispatch branches — the parser, not the surfaces, is what broke'
    ).toBeGreaterThan(5)
  })

  it('has no duplicate branch (a second branch for one action is dead code)', () => {
    expect(sorted(dispatch)).toEqual([...dispatch].sort())
  })

  it('the parser fails loudly on a branch it cannot read', () => {
    expect(() =>
      coreDispatchActions('def _act_core(\n    x = 1\n    elif action == "sneaky":\n')
    ).toThrow(/unreadable action-dispatch line/)
  })
})

describe('every surface accepts exactly the core vocabulary', () => {
  it('the dashboard bridge admission set equals the core dispatch set', () => {
    expect(
      sorted(ACTIONS),
      'an action the core dispatches and the bridge omits is refused as ' +
        'action_invalid BEFORE the core sees it — unreachable from every web ' +
        'surface; an action the bridge admits and the core does not is a ' +
        'request forwarded to a refusal'
    ).toEqual(sorted(dispatch))
  })

  it('the TypeScript action vocabulary equals the core dispatch set', () => {
    expect(
      sorted(ONBOARDING_ACTIONS),
      'ONBOARDING_ACTIONS drives the union every surface types its requests ' +
        'against (pinned to it at compile time by ActionsAgree in ./types)'
    ).toEqual(sorted(dispatch))
  })
})

describe('nothing the core offers is unreachable', () => {
  const offered = sorted(coreOfferedActions(core))

  it('parses the offered actions at all', () => {
    expect(offered.length, 'parsed zero offered actions').toBeGreaterThan(5)
  })

  it('every action the core prints on a card is one it can dispatch', () => {
    expect(offered.filter((action) => !dispatch.includes(action))).toEqual([])
  })

  it('every offered action has a Telegram branch or a named exemption', () => {
    const telegram = new Set(telegramActions(read(TELEGRAM)))
    const unreachable = offered.filter(
      (action) => !telegram.has(action) && !TELEGRAM_EXEMPT[action]
    )
    expect(
      unreachable,
      'the core prints these on a Telegram card with no command able to send ' +
        'them — wire the branch, or add an entry to TELEGRAM_EXEMPT saying what ' +
        'about the channel makes it impossible'
    ).toEqual([])
  })

  it('an exemption states a real reason and never files work as covered', () => {
    for (const [action, reason] of Object.entries(TELEGRAM_EXEMPT)) {
      expect(offered, `${action} is exempted but the core never offers it`).toContain(action)
      expect(reason.length, `${action}: an exemption needs its reason`).toBeGreaterThan(60)
      expect(reason, `${action}: "${reason}" defers work rather than stating a limit`)
        .not.toMatch(PLACEHOLDER)
    }
  })

  it('an exemption cannot cover an action Telegram already handles', () => {
    const telegram = new Set(telegramActions(read(TELEGRAM)))
    for (const action of Object.keys(TELEGRAM_EXEMPT)) {
      expect(telegram.has(action), `${action} is wired AND exempted — drop the exemption`).toBe(false)
    }
  })
})

describe('the window-relation vocabulary', () => {
  it('mirrors the core key for key', () => {
    const py = coreWindowRelations(core)
    expect(Object.keys(py).length, 'parsed zero relations').toBeGreaterThan(0)
    expect(
      { ...WINDOW_RELATIONS },
      'a surface offering a relation the core does not accept is a button that ' +
        'can only earn salience_relation_invalid; a relation the core accepts ' +
        'and no surface offers is a refusal with no way out of it'
    ).toEqual(py)
  })

  it('the parser fails loudly on a wrapped entry', () => {
    expect(() =>
      coreWindowRelations('WINDOW_RELATIONS = {\n    "a": "one",\n    "b":\n        "two",\n}\n')
    ).toThrow(/unreadable WINDOW_RELATIONS line/)
  })
})
