import { hasRealPassword } from '@/lib/first-run'
import LoginForm from './login-form'
import CreatePasswordForm from './create-password-form'

// Evaluate first-run per REQUEST, never bake it at build: whether a password is
// configured is a runtime fact (process.env / cabinet/.env), and a statically
// rendered "create a password" screen would haunt a configured instance.
export const dynamic = 'force-dynamic'

/**
 * The door. This route is exempt from the auth middleware; everything behind it
 * is not. It has two states, decided server-side from whether a real password is
 * configured:
 *
 *   - FIRST RUN (no password yet): show "create a password". This is the only
 *     screen reachable while the cabinet has no password — every gated route and
 *     mutating API is redirected here by the middleware until one is set.
 *   - RETURNING (a password exists): show "sign in", plus a one-click, no-typing
 *     way to reset a forgotten password (double-click a file on the machine).
 */
export default async function LoginPage() {
  const firstRun = !hasRealPassword()

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 md:pl-0">
      <div className="w-full max-w-sm">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Captain&apos;s Cabinet</h1>
          <p className="mt-2 text-sm text-zinc-500">
            {firstRun
              ? 'Create a password for your Cabinet to get started'
              : 'Enter your password to continue'}
          </p>
        </div>

        {firstRun ? <CreatePasswordForm /> : <LoginForm />}

        {!firstRun && (
          <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-sm text-zinc-400">
            <p className="font-medium text-zinc-300">Forgot your password?</p>
            <p className="mt-1">
              On the Cabinet computer, open your Cabinet folder and double-click{' '}
              <span className="font-medium text-zinc-300">Reset Cabinet Password</span>.
            </p>
            <p className="mt-2 text-xs text-zinc-500">
              It clears the old password and brings this screen back so you can
              choose a new one. Nothing is ever shown to you or sent anywhere.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
