'use client'

import { useActionState } from 'react'
import { login } from '@/actions/auth'

/**
 * The returning-operator form: a password already exists; sign in with it.
 *
 * The hint matters more than it looks: a chosen password may contain spaces and
 * symbols, and it is compared exactly as typed — nothing is trimmed or
 * corrected. Someone who put a space at the end has to type that space here too.
 */
export default function LoginForm() {
  const [state, formAction, isPending] = useActionState(login, null)

  return (
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
        <p className="mt-1.5 text-xs text-zinc-500">
          Type it exactly as you chose it — spaces and symbols count.
        </p>
      </div>

      <button
        type="submit"
        disabled={isPending}
        className="w-full rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-zinc-900 transition-colors hover:bg-zinc-200 disabled:opacity-50"
      >
        {isPending ? 'Signing in...' : 'Sign in'}
      </button>
    </form>
  )
}
