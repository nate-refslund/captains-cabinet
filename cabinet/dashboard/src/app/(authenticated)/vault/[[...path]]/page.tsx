/**
 * /vault/[[...path]] — redirect alias to /library (Captain naming ruling
 * 2026-07-17: "keep the name Library — it fits the world; the vault is where
 * it's kept, the Library is where you read").
 *
 * The phase-1 vault browser MOVED to /library/[[...path]]; this stub keeps
 * every /vault deep link working: /vault → /library, /vault/a/b.md →
 * /library/a/b.md. The target is built EXCLUSIVELY by re-percent-encoding
 * the decoded route segments under the /library prefix (vaultHref) — never
 * from query strings, headers, or a full URL — so it is ALWAYS a same-origin
 * internal path: a decoded `%2F` inside a segment is re-encoded, never
 * emitted as `//` (no open redirect). Auth posture unchanged: the route
 * stays inside (authenticated), so the middleware cookie gate runs before
 * this redirect is ever computed. No fs, no DB, no rendering.
 *
 * Docs: docs/runbooks/vault-browser-2026-07-17.md.
 */

import { redirect } from 'next/navigation'
import { vaultHref } from '@/lib/vault-wikilinks'

export const dynamic = 'force-dynamic'

export default async function VaultRedirect({
  params,
}: {
  params: Promise<{ path?: string[] }>
}) {
  const { path: segments } = await params
  const rel = (segments ?? []).join('/')
  redirect(rel === '' ? '/library' : vaultHref(rel))
}
