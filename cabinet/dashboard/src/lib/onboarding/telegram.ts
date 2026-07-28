/** Telegram is a complete skin over the canonical onboarding journey. */
import {
  applyOnboardingAction,
  getOnboarding,
  OnboardingBridgeError,
  recordOnboardingEvidence,
} from './bridge'
import type {
  OnboardingAction,
  OnboardingResponse,
  OwnershipClass,
} from './types'

type RelationshipDestination = 'earn' | 'reversible' | 'sovereign'

/**
 * Telegram is an OUTBOUND channel: an excerpt rendered into a message is a
 * verbatim line from the source shipped to a third-party messaging service.
 * The core decides the egress verdict (framework/authority/ownership.py) and
 * withholds the words of anything the operator does not own; this surface
 * renders that verdict and must never reconstruct what was withheld.
 */
const OWNERSHIP_WORDS: Record<string, OwnershipClass> = {
  mine: 'self',
  my: 'self',
  own: 'self',
  self: 'self',
  employer: 'employer',
  work: 'employer',
  employers: 'employer',
  client: 'third_party',
  customer: 'third_party',
  theirs: 'third_party',
  'third-party': 'third_party',
  third_party: 'third_party',
}

const OWNERSHIP_SYNTAX =
  'Add whose data it is and under what right, as the last segment:\n' +
  '/onboard folder /full/path | what you want made easier | mine: my own laptop\n' +
  'Use mine, employer, or client. I will not guess — an unclassified folder is refused.'

/**
 * Take a trailing `| <who>: <basis>` segment. Absent means ABSENT: this returns
 * nothing rather than a plausible default, and the core then refuses with a
 * code this surface turns back into the syntax line above.
 */
function takeOwnership(value: string): {
  value: string
  ownership?: OwnershipClass
  authorityBasis?: string
} {
  const match = value.match(/\|\s*([A-Za-z][A-Za-z_-]*)\s*:\s*([^|]+?)\s*$/)
  if (!match) return { value }
  const ownership = OWNERSHIP_WORDS[match[1].toLowerCase()]
  if (!ownership) return { value }
  return {
    value: value.slice(0, match.index).trim(),
    ownership,
    authorityBasis: match[2].trim(),
  }
}

const OWNERSHIP_REFUSAL_CODES = new Set([
  'ownership_unclassified',
  'ownership_class_unknown',
  'authority_basis_required',
  'authority_basis_too_long',
])

export interface TelegramInlineButton {
  text: string
  callback_data: string
}

export interface TelegramOnboardingMessage {
  text: string
  plain: true
  buttons?: TelegramInlineButton[][]
}

const INTENT = /^\s*\/?(?:onboard|onboarding|orientation)\b/i

export function isOnboardingIntent(text: string): boolean {
  return INTENT.test(text)
}

function buttonsFor(result: OnboardingResponse): TelegramInlineButton[][] {
  const stage = result.card.stage
  const callback: Partial<Record<OnboardingAction, string>> = {
    ratify_charter: 'onboard:accept',
    continue: 'onboard:continue',
    pause: 'onboard:pause',
    revoke: 'onboard:revoke',
    undo: 'onboard:undo',
    purge: 'onboard:purge_prompt',
  }
  if (stage === 'purged') return []
  if (stage === 'welcome') {
    // The one-tap Documents buttons are GONE, deliberately. A tap cannot carry
    // whose data the folder is, and the core refuses an unclassified source, so
    // a button here would be a dead end that reads like an offer. The typed
    // form in the welcome body is the only path, because the question has to be
    // answered before anything is read.
    return []
  }
  if (stage === 'dividend_ready') {
    return [
      [{ text: '👍 Useful', callback_data: 'onboard:feedback:useful' }],
      [{ text: 'Not useful yet', callback_data: 'onboard:feedback:not_useful' }],
      [{ text: 'Something is wrong', callback_data: 'onboard:feedback:corrected' }],
      ...result.card.options
        .filter((option) => callback[option.action])
        .map((option) => [{
          text: option.label,
          callback_data: callback[option.action]!,
        }]),
    ]
  }
  return result.card.options
    .filter((option) => callback[option.action])
    .map((option) => [{ text: option.label, callback_data: callback[option.action]! }])
}

export function formatTelegramOnboarding(result: OnboardingResponse): TelegramOnboardingMessage {
  const lines = [
    result.card.title,
    '',
    result.card.body,
  ]
  if (result.card.evidence.length > 0) {
    lines.push('', 'Receipt — where this came from')
    for (const citation of result.card.evidence) {
      lines.push(`• ${citation.path}:${citation.line} — ${citation.excerpt}`)
    }
  }
  const egress = result.card.egress
  if (egress && egress.withheld > 0) {
    lines.push(
      '',
      `I am holding back the words of ${egress.withheld} of ${egress.items} citation(s): ` +
        'this source is not yours to send. The file and line are above so you can open ' +
        'them yourself, or reclassify the source if I have it wrong.'
    )
  }
  if (result.card.stage === 'welcome') {
    lines.push(
      '',
      'Send:',
      '/onboard folder /full/path | what you want made easier | mine: my own laptop',
      'The last segment says whose data it is (mine, employer, or client) and under what right.',
      'An optional final word — earn, reversible, or sovereign — sets a destination, not an authority grant.'
    )
  }
  if (result.card.stage === 'purged') {
    lines.push('', 'No action from an older Dashboard, Telegram message, or World card can recreate that evidence trial.')
  }
  if (result.card.stage === 'charter_pending') {
    lines.push('', `Charter fingerprint: ${result.state.charter?.hash.slice(0, 12)}`)
    lines.push('To change the scope, send another /onboard folder command.')
  }
  lines.push('', `Same card everywhere: ${result.card.id}`)
  return { text: lines.join('\n'), plain: true, buttons: buttonsFor(result) }
}

function purposeAfterPipe(value: string): { source: string; purpose: string } {
  const separator = value.indexOf('|')
  if (separator < 0) {
    return { source: value.trim(), purpose: 'Find one useful thing I may be missing.' }
  }
  return {
    source: value.slice(0, separator).trim(),
    purpose: value.slice(separator + 1).trim() || 'Find one useful thing I may be missing.',
  }
}

function takeDestination(value: string): {
  value: string
  destination: RelationshipDestination
} {
  const match = value.match(/\|\s*(earn|reversible|sovereign)\s*$/i)
  if (!match) return { value, destination: 'reversible' }
  return {
    value: value.slice(0, match.index).trim(),
    destination: match[1].toLowerCase() as RelationshipDestination,
  }
}

async function action(
  name: OnboardingAction,
  actionId: string,
  extra: Record<string, unknown> = {}
): Promise<OnboardingResponse> {
  const current = await getOnboarding()
  return applyOnboardingAction(
    {
      action: name,
      action_id: actionId,
      trace_id: `trace-${actionId}`,
      correlation_id: `corr-${actionId}`,
      expected_revision: current.card.revision,
      ...extra,
    },
    'telegram'
  )
}

async function feedback(
  status: 'useful' | 'not_useful' | 'corrected',
  actionId: string
): Promise<TelegramOnboardingMessage[]> {
  const category = status === 'useful'
    ? 'useful_as_shown'
    : status === 'not_useful'
      ? 'insufficient_value'
      : 'wrong_or_missing_context'
  await recordOnboardingEvidence({
    phase: 'feedback',
    status,
    action_id: `feedback-${actionId}`,
    trace_id: `trace-feedback-${actionId}`,
    correlation_id: `corr-${actionId}`,
    detail: { feedback_rating: status, feedback_category: category },
  }, 'telegram')
  return [{ text: `Feedback recorded: ${status.replace('_', ' ')}.`, plain: true }]
}

function refusal(error: unknown): TelegramOnboardingMessage {
  const message = error instanceof OnboardingBridgeError
    ? error.message
    : 'The Cabinet could not complete that onboarding choice.'
  // An ownership refusal is not a failure to explain away — it is a question
  // the operator has not answered, so the reply carries the exact syntax that
  // answers it instead of a generic "try again".
  const code = error instanceof OnboardingBridgeError ? error.code : undefined
  const tail = code && OWNERSHIP_REFUSAL_CODES.has(code)
    ? `${OWNERSHIP_SYNTAX}\n\nSend /onboard to see the current card.`
    : 'Send /onboard to see the current card.'
  return {
    text: `${message}\n\n${tail}`,
    plain: true,
  }
}

export async function handleTelegramOnboarding(
  text: string,
  actionId: string
): Promise<TelegramOnboardingMessage[]> {
  try {
    const command = text.replace(INTENT, '').trim()
    if (!command || /^(status|show|start)$/i.test(command)) {
      return [formatTelegramOnboarding(await getOnboarding())]
    }
    if (/^documents(?:\s|$)/i.test(command)) {
      const selected = takeDestination(command.replace(/^documents/i, ''))
      const owned = takeOwnership(selected.value)
      const purpose = owned.value.replace(/^\s*\|?\s*/, '').trim()
      const result = await action('propose_window', actionId, {
        source: '~/Documents',
        purpose: purpose || 'Find one useful thing I may be missing.',
        relationship_destination: selected.destination,
        ownership: owned.ownership,
        authority_basis: owned.authorityBasis,
      })
      return [formatTelegramOnboarding(result)]
    }
    if (/^folder\s+/i.test(command)) {
      const selected = takeDestination(command.replace(/^folder\s+/i, ''))
      const owned = takeOwnership(selected.value)
      const parsed = purposeAfterPipe(owned.value)
      const result = await action('propose_window', actionId, {
        ...parsed,
        relationship_destination: selected.destination,
        ownership: owned.ownership,
        authority_basis: owned.authorityBasis,
      })
      return [formatTelegramOnboarding(result)]
    }
    if (/^(accept|approve)$/i.test(command)) {
      const current = await getOnboarding()
      const charterHash = current.state.charter?.hash
      if (!charterHash) throw new OnboardingBridgeError('charter_not_pending', 'There is no Charter waiting for approval.')
      return [formatTelegramOnboarding(await action('ratify_charter', actionId, { charter_hash: charterHash }))]
    }
    // The typed answer to the seed question. Telegram cannot render a text
    // field, and the core marks this option `input: 'seed'` so `buttonsFor`
    // must not offer it as a tap — a tap carries no words. The command is the
    // field: without it the seed question would print here with no way to
    // answer it, which is the dead end this whole path exists to close.
    if (/^seed\s+/i.test(command)) {
      const seed = command.replace(/^seed\s+/i, '').trim()
      return [formatTelegramOnboarding(await action('answer_seed', actionId, { seed }))]
    }
    if (/^continue$/i.test(command)) return [formatTelegramOnboarding(await action('continue', actionId))]
    if (/^pause$/i.test(command)) return [formatTelegramOnboarding(await action('pause', actionId))]
    if (/^revoke$/i.test(command)) return [formatTelegramOnboarding(await action('revoke', actionId))]
    if (/^undo$/i.test(command)) return [formatTelegramOnboarding(await action('undo', actionId))]
    if (/^useful$/i.test(command)) return feedback('useful', actionId)
    if (/^not[ _-]?useful$/i.test(command)) return feedback('not_useful', actionId)
    if (/^(wrong|correction)$/i.test(command)) return feedback('corrected', actionId)
    if (/^purge\s+PURGE$/.test(command)) {
      return [formatTelegramOnboarding(await action('purge', actionId, { confirmation: 'PURGE' }))]
    }
    if (/^purge/i.test(command)) {
      return [{
        text: 'Purging permanently removes the Charter, onboarding event history, manifest, and derived excerpts. To confirm, send exactly:\n/onboard purge PURGE',
        plain: true,
      }]
    }
    return [{
      text: 'I did not recognize that onboarding choice. Send /onboard to see the current card, or use:\n/onboard folder /full/path | what you want made easier',
      plain: true,
    }]
  } catch (error) {
    return [refusal(error)]
  }
}

export async function handleTelegramOnboardingCallback(
  data: string,
  actionId: string
): Promise<TelegramOnboardingMessage[]> {
  const command = data.replace(/^onboard:/, '')
  if (command.startsWith('documents:')) {
    // A callback from a message sent before the ownership ceiling existed.
    // Acting on it would read a folder whose class nobody declared, so it
    // answers with the question instead.
    return [{ text: OWNERSHIP_SYNTAX, plain: true }]
  }
  if (command === 'accept') return handleTelegramOnboarding('/onboard accept', actionId)
  if (command === 'continue') return handleTelegramOnboarding('/onboard continue', actionId)
  if (command === 'pause') return handleTelegramOnboarding('/onboard pause', actionId)
  if (command === 'revoke') return handleTelegramOnboarding('/onboard revoke', actionId)
  if (command === 'undo') return handleTelegramOnboarding('/onboard undo', actionId)
  if (command === 'purge_prompt') return handleTelegramOnboarding('/onboard purge', actionId)
  if (command === 'feedback:useful') return feedback('useful', actionId)
  if (command === 'feedback:not_useful') return feedback('not_useful', actionId)
  if (command === 'feedback:corrected') return feedback('corrected', actionId)
  return handleTelegramOnboarding('/onboard', actionId)
}
