/**
 * A stand-in for api.telegram.org — TEST FIXTURE ONLY, imported by
 * `connect.test.ts` and `actions/telegram-connect.test.ts` and by nothing the
 * app ships.
 *
 * WHY A REAL SERVER RATHER THAN A STUBBED `fetch`. The properties worth pinning
 * are properties of the REQUEST: that `getUpdates` carries no `offset` (so
 * nothing is consumed), that the token rides in the path and nowhere else, that
 * a 409 is handled before the body is read. A `fetch` stub asserts what the code
 * meant to send; a socket asserts what it sent. Every request is recorded here,
 * so a test can read the URL that actually left the process.
 *
 * WHY NO REAL BOT IS EVER USED. Creating one is an account action against a
 * third party in the Captain's name — not something a test may do. The live
 * halves of this flow (getMe validating a real token, a real message landing on
 * a real phone) are proven by the Captain's own connect, once. Everything
 * mechanical is proven here.
 */

import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import type { AddressInfo } from 'node:net'

export interface RecordedCall {
  method: string
  /** The bot path segment as sent — this is where a token leak would show. */
  tokenSegment: string
  /** The Bot API method name. */
  apiMethod: string
  /** Query parameters, exactly as they arrived. */
  query: Record<string, string>
  /** JSON body for a POST, else null. */
  body: Record<string, unknown> | null
}

export interface MockTelegram {
  base: string
  calls: RecordedCall[]
  /** Replace what a Bot API method answers, per method. */
  reply(apiMethod: string, handler: () => { status?: number; body: unknown }): void
  close(): Promise<void>
}

export async function startMockTelegram(): Promise<MockTelegram> {
  const calls: RecordedCall[] = []
  const handlers = new Map<string, () => { status?: number; body: unknown }>()

  const server: Server = createServer((req: IncomingMessage, res: ServerResponse) => {
    const url = new URL(req.url ?? '/', 'http://localhost')
    const [, tokenSegment = '', apiMethod = ''] = url.pathname.split('/')
    const query: Record<string, string> = {}
    url.searchParams.forEach((value, key) => {
      query[key] = value
    })

    const chunks: Buffer[] = []
    req.on('data', (chunk: Buffer) => chunks.push(chunk))
    req.on('end', () => {
      let body: Record<string, unknown> | null = null
      if (chunks.length) {
        try {
          body = JSON.parse(Buffer.concat(chunks).toString('utf8')) as Record<string, unknown>
        } catch {
          body = null
        }
      }
      calls.push({ method: req.method ?? 'GET', tokenSegment, apiMethod, query, body })

      const handler = handlers.get(apiMethod)
      const answer = handler ? handler() : { status: 404, body: { ok: false, description: 'no handler' } }
      res.writeHead(answer.status ?? 200, { 'content-type': 'application/json' })
      res.end(typeof answer.body === 'string' ? answer.body : JSON.stringify(answer.body))
    })
  })

  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const { port } = server.address() as AddressInfo

  return {
    base: `http://127.0.0.1:${port}`,
    calls,
    reply(apiMethod, handler) {
      handlers.set(apiMethod, handler)
    },
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  }
}

/** A syntactically valid token that has never existed. */
export const FAKE_TOKEN = '8123456789:AAF3kQ7pLm2xR9tYvB1cN4dW6eZ0hJ8sKqM'

/** One private message from `who`, in the Bot API's own envelope shape. */
export function privateMessage(
  chatId: number,
  who: { username?: string; first_name?: string; is_bot?: boolean } = {}
) {
  return {
    update_id: chatId,
    message: {
      message_id: 1,
      chat: { id: chatId, type: 'private' },
      from: { id: chatId, ...who },
      text: 'hi',
    },
  }
}

/** One group message — a room, never a candidate for the Captain's address. */
export function groupMessage(chatId: number) {
  return {
    update_id: Math.abs(chatId),
    message: {
      message_id: 2,
      chat: { id: chatId, type: 'supergroup', title: 'Ops room' },
      from: { id: 999, first_name: 'Someone' },
      text: 'hi',
    },
  }
}
