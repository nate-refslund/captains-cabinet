import Link from 'next/link'
import TelegramConnectFlow from '@/components/telegram/connect-flow'
import { getTelegramStatus } from '@/actions/telegram-connect'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: 'Connect Telegram · Cabinet',
}

/**
 * ONE FLOW, TWO ENTRANCES. The home page's power-up card and the Integrations
 * page's Telegram section both link here, so there is a single set of steps to
 * maintain and a single place the operator can be sent back to.
 */
export default async function TelegramConnectPage() {
  const status = await getTelegramStatus()

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <Link href="/integrations" className="text-sm text-zinc-500 hover:text-zinc-300">
          ← Integrations
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">
          Your Cabinet on your phone
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
          Telegram is how your Cabinet reaches you when you are away from this screen. Four steps,
          no terminal, and a message on your phone at the end to prove it works.
        </p>
      </div>
      <TelegramConnectFlow initialStatus={status} />
    </div>
  )
}
