'use client'

import { useActionState } from 'react'
import { createPassword } from '@/actions/auth'
import { PASSWORD_MIN_LENGTH } from '@/lib/first-run'

/**
 * First-run form: no password exists yet, so the operator chooses their own.
 * Their own machine — no email, no username, just a password only they know.
 */
export default function CreatePasswordForm() {
  const [state, formAction, isPending] = useActionState(createPassword, null)

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
          Choose a password only you know
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          autoFocus
          minLength={PASSWORD_MIN_LENGTH}
          className="mt-1.5 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
          placeholder="Your new password"
        />
        <p className="mt-1.5 text-xs text-zinc-500">
          At least {PASSWORD_MIN_LENGTH} characters, so it is not easy to guess.
        </p>
      </div>

      <div>
        <label
          htmlFor="confirm"
          className="block text-sm font-medium text-zinc-400"
        >
          Type it again
        </label>
        <input
          id="confirm"
          name="confirm"
          type="password"
          required
          minLength={PASSWORD_MIN_LENGTH}
          className="mt-1.5 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
          placeholder="Your new password again"
        />
      </div>

      <button
        type="submit"
        disabled={isPending}
        className="w-full rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-zinc-900 transition-colors hover:bg-zinc-200 disabled:opacity-50"
      >
        {isPending ? 'Setting password...' : 'Set password'}
      </button>
    </form>
  )
}
