/**
 * The guided Telegram connect — the vocabulary both sides share.
 *
 * WHY IT IS ITS OWN FILE. `lib/telegram/connect.ts` holds the transport: it
 * builds `…/bot<token>/…` URLs and calls them. The step components are a CLIENT
 * bundle, and they need four things from this flow — the words of the test
 * message, the shape of a captured chat, an env var NAME, and the sentence a
 * failure turns into. Importing the transport to get them would ship the
 * token-bearing URL builder to a browser that has no business holding it. So
 * everything free of `fetch` and free of `process.env` lives here, and the
 * transport imports from it rather than the other way round.
 */

/** The one message the Cabinet sends to prove the line is open. */
export const CONNECTED_MESSAGE = "I'm connected. This is where I'll reach you."

/**
 * The env var name the runtime reads for the Chair's bot token.
 * `framework/frontdoor/channel.py` resolves TELEGRAM_BOT_TOKEN first and
 * TELEGRAM_COS_TOKEN second; the preset, `cabinet/scripts/setup-env.sh` and
 * `cabinet/scripts/telegram-capture-chat-id.sh` all name the latter, so that is
 * the one this flow writes.
 */
export const TOKEN_ENV_NAME = 'TELEGRAM_COS_TOKEN'

/**
 * The env var name the runtime reads for the Captain's chat id — the sole
 * recipient of every outbound message (`channel.py _captain_id`) and the
 * default-deny identity gate the inbound poller applies to DMs.
 */
export const CHAT_ENV_NAME = 'CAPTAIN_TELEGRAM_ID'

/**
 * A numeric chat id. Mirrors `CHAT_ID_RE` in cabinet/scripts/generate-instance.py
 * — the generator refuses anything else, so accepting more here would write a
 * value the next regenerate rejects.
 */
export const CHAT_ID_RE = /^-?\d{4,20}$/

/**
 * A shape check, NOT the authority. The live `getMe` decides whether a token
 * works; this only catches "you pasted the wrong thing entirely" (a chat id, a
 * URL, an empty box) before spending a network call on it. It is deliberately
 * looser than `lib/botfather.ts BOT_TOKEN_STRICT_RE`, which pins today's exact
 * 35-character secret: a token format Telegram widens later must be refused by
 * Telegram, not by a regex here.
 */
export function looksLikeBotToken(raw: string): boolean {
  return /^\d{5,16}:[A-Za-z0-9_-]{20,}$/.test(String(raw ?? '').trim())
}

/**
 * A name from a stranger's Telegram profile is UNTRUSTED TEXT that this app
 * renders back to the operator. React escapes what it interpolates, so markup
 * cannot execute — but a control character, a right-to-left override or a
 * 400-character display name still wrecks the confirmation line the operator is
 * supposed to read carefully before saying "yes, that's me". Same treatment the
 * capture script's parser applies, for the same reason.
 */
export function sanitizeLabel(raw: unknown): string {
  const text = typeof raw === 'string' ? raw : ''
  let out = ''
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0
    // C0/C1 controls, the bidi overrides, and the zero-width characters a name
    // can carry to make two different accounts render identically.
    const hostile =
      code < 0x20 ||
      (code >= 0x7f && code <= 0x9f) ||
      (code >= 0x200b && code <= 0x200f) ||
      (code >= 0x202a && code <= 0x202e) ||
      (code >= 0x2066 && code <= 0x2069)
    out += hostile ? ' ' : ch
  }
  return out.replace(/\s+/g, ' ').trim().slice(0, 48)
}

export interface ChatCandidate {
  /** The address a message is sent to. For a private chat this IS the user id. */
  chatId: string
  /** Who Telegram says sent it, sanitized for display. May be empty. */
  label: string
}

export type TelegramFailureReason =
  /** Telegram answered, and said no (bad token, revoked bot, …). */
  | 'rejected'
  /** Another poller or a webhook already holds this token. */
  | 'conflict'
  /** Telegram asked us to slow down. A wait, never a wrong token. */
  | 'rate_limited'
  /** Could not reach the host, or it did not answer in time. */
  | 'unreachable'
  /** It answered with something that is not a Bot API envelope. */
  | 'unreadable'

/**
 * Why nothing happened, in the operator's words. The transport's reasons are
 * stable and diagnostic; these are the sentences that tell somebody what to DO.
 */
export function plainFailure(
  reason: TelegramFailureReason,
  what: 'token' | 'listen' | 'send'
): string {
  if (reason === 'rejected') {
    return what === 'token'
      ? 'That token did not work — check you copied all of it, including the digits before the colon.'
      : 'Telegram refused that. The token may have been replaced since you pasted it.'
  }
  if (reason === 'rate_limited') {
    // Distinct from `rejected` DELIBERATELY. A 429 comes back in the same
    // `ok: false` envelope as a bad token, and telling somebody their token was
    // refused when Telegram merely asked them to wait sends them back to
    // BotFather for a problem that fixes itself in a minute.
    return 'Telegram asked me to slow down. Wait a moment and try again — nothing is wrong with your bot.'
  }
  if (reason === 'conflict') {
    return 'Something else is already reading this bot — your Cabinet may already be running, or another app holds the same token. Stop it and try again.'
  }
  if (reason === 'unreachable') {
    return 'I could not reach Telegram just now. Check this machine is online and try again.'
  }
  return 'Telegram answered with something I could not read. Try again in a moment.'
}
