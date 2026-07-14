/** Telegram is a complete skin over the canonical onboarding journey. */
import {
  applyOnboardingAction,
  getOnboarding,
  OnboardingBridgeError,
} from './bridge'
import type {
  OnboardingAction,
  OnboardingResponse,
} from './types'

type RelationshipDestination = 'earn' | 'reversible' | 'sovereign'

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
  if (stage === 'welcome' || stage === 'purged') {
    return [
      [{ text: 'Documents · reversible (recommended)', callback_data: 'onboard:documents:reversible' }],
      [{ text: 'Documents · earn every step', callback_data: 'onboard:documents:earn' }],
      [{ text: 'Documents · broad autonomy later', callback_data: 'onboard:documents:sovereign' }],
    ]
  }
  const callback: Partial<Record<OnboardingAction, string>> = {
    ratify_charter: 'onboard:accept',
    continue: 'onboard:continue',
    pause: 'onboard:pause',
    revoke: 'onboard:revoke',
    undo: 'onboard:undo',
    purge: 'onboard:purge_prompt',
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
  if (result.card.stage === 'welcome' || result.card.stage === 'purged') {
    lines.push(
      '',
      'Choose a Documents option below, or send:',
      '/onboard folder /full/path | what you want made easier | reversible',
      'The last word can be earn, reversible, or sovereign. It is a destination, not an authority grant.'
    )
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
      expected_revision: current.card.revision,
      ...extra,
    },
    'telegram'
  )
}

function refusal(error: unknown): TelegramOnboardingMessage {
  const message = error instanceof OnboardingBridgeError
    ? error.message
    : 'The Cabinet could not complete that onboarding choice.'
  return {
    text: `${message}\n\nSend /onboard to see the current card.`,
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
      const purpose = selected.value.replace(/^\s*\|?\s*/, '').trim()
      const result = await action('propose_window', actionId, {
        source: '~/Documents',
        purpose: purpose || 'Find one useful thing I may be missing.',
        relationship_destination: selected.destination,
      })
      return [formatTelegramOnboarding(result)]
    }
    if (/^folder\s+/i.test(command)) {
      const selected = takeDestination(command.replace(/^folder\s+/i, ''))
      const parsed = purposeAfterPipe(selected.value)
      const result = await action('propose_window', actionId, {
        ...parsed,
        relationship_destination: selected.destination,
      })
      return [formatTelegramOnboarding(result)]
    }
    if (/^(accept|approve)$/i.test(command)) {
      const current = await getOnboarding()
      const charterHash = current.state.charter?.hash
      if (!charterHash) throw new OnboardingBridgeError('charter_not_pending', 'There is no Charter waiting for approval.')
      return [formatTelegramOnboarding(await action('ratify_charter', actionId, { charter_hash: charterHash }))]
    }
    if (/^continue$/i.test(command)) return [formatTelegramOnboarding(await action('continue', actionId))]
    if (/^pause$/i.test(command)) return [formatTelegramOnboarding(await action('pause', actionId))]
    if (/^revoke$/i.test(command)) return [formatTelegramOnboarding(await action('revoke', actionId))]
    if (/^undo$/i.test(command)) return [formatTelegramOnboarding(await action('undo', actionId))]
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
    const destination = command.slice('documents:'.length)
    if (/^(earn|reversible|sovereign)$/.test(destination)) {
      return handleTelegramOnboarding(`/onboard documents | | ${destination}`, actionId)
    }
  }
  if (command === 'accept') return handleTelegramOnboarding('/onboard accept', actionId)
  if (command === 'continue') return handleTelegramOnboarding('/onboard continue', actionId)
  if (command === 'pause') return handleTelegramOnboarding('/onboard pause', actionId)
  if (command === 'revoke') return handleTelegramOnboarding('/onboard revoke', actionId)
  if (command === 'undo') return handleTelegramOnboarding('/onboard undo', actionId)
  if (command === 'purge_prompt') return handleTelegramOnboarding('/onboard purge', actionId)
  return handleTelegramOnboarding('/onboard', actionId)
}
