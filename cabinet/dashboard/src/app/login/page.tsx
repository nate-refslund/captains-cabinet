'use client'

import { useActionState } from 'react'
import { login } from '@/actions/auth'

export default function LoginPage() {
  const [state, formAction, isPending] = useActionState(login, null)

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 md:pl-0">
      <div className="w-full max-w-sm">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">
            Captain&apos;s Cabinet
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Enter the dashboard password to continue
          </p>
        </div>

        <form action={formAction} className="mt-8 space-y-4">
          {state?.error && (
            <div className="rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-500">
              {state.error}
            </div>
          )}

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-zinc-400"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              required
              autoFocus
              className="mt-1.5 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
              placeholder="Enter password"
            />
          </div>

          <button
            type="submit"
            disabled={isPending}
            className="w-full rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-zinc-900 transition-colors hover:bg-zinc-200 disabled:opacity-50"
          >
            {isPending ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-sm text-zinc-400">
          <p className="font-medium text-zinc-300">Forgot the password?</p>
          <p className="mt-1">
            On the Cabinet Mac, open Terminal in the Cabinet folder and run:
          </p>
          <code className="mt-2 block overflow-x-auto rounded bg-zinc-950 px-2 py-1.5 text-xs text-zinc-300">
            bash cabinet/scripts/dashboard-password.sh --copy
          </code>
          <p className="mt-2 text-xs text-zinc-500">
            This copies it to your clipboard without printing it. Paste it above.
          </p>
        </div>
      </div>
    </div>
  )
}
