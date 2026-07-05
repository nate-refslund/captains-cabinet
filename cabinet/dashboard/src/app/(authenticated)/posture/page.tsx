/**
 * /posture — RENDER-ONLY autonomy-posture tile [AX-7].
 *
 * Shows the JSON emitted by `cabinet/scripts/posture-status.py` (the ONE
 * posture resolver chain — this page never re-derives axis state). By
 * Corridor constraint (axes spec §1 + axes-contract §3) this surface has NO
 * state-changing control: a dashboard "go sovereign" button is a forge
 * vector, so the upgrade section prints the attested ritual verbatim and the
 * downgrade section prints the Captain's Telegram binder verb — text only,
 * no buttons, no server actions.
 */
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import path from 'node:path'

export const dynamic = 'force-dynamic'

const execFileAsync = promisify(execFile)

type PostureStatus = {
  level: string
  flavor: string | null
  target: string | null
  attested: boolean
  narrow_cap: string | null
  error?: string
}

const LEVEL_BADGE: Record<string, string> = {
  guardian: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  earn_up: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  sovereign: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
}

// Verbatim — the same ritual the binder verb and cabinet-init print.
const UPGRADE_RITUAL = `sudo bash cabinet/scripts/germline-lock.sh unlock   # Captain unlock window
$EDITOR instance/config/posture.yml                 # posture: sovereign (presets: instance/config/posture-presets/)
git add -A && git commit
sudo bash cabinet/scripts/germline-lock.sh lock     # the lock IS the signature`

async function getPostureStatus(): Promise<PostureStatus> {
  // Fixed script path under CABINET_ROOT — no request input reaches the exec.
  const root = process.env.CABINET_ROOT ?? path.resolve(process.cwd(), '..', '..')
  const script = path.join(root, 'cabinet', 'scripts', 'posture-status.py')
  try {
    const { stdout } = await execFileAsync('python3', [script], {
      timeout: 10_000,
      env: { ...process.env, CABINET_ROOT: root },
    })
    return JSON.parse(stdout) as PostureStatus
  } catch (err) {
    // Fail-closed shape: guardian IS the resolver's answer to every ambiguity.
    return {
      level: 'guardian',
      flavor: null,
      target: null,
      attested: false,
      narrow_cap: null,
      error: err instanceof Error ? err.message : 'posture-status.py unavailable',
    }
  }
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-zinc-800 py-2 last:border-b-0">
      <span className="text-sm text-zinc-500">{label}</span>
      <span className="font-mono text-sm text-zinc-200">{value}</span>
    </div>
  )
}

export default async function PosturePage() {
  const status = await getPostureStatus()
  const badge = LEVEL_BADGE[status.level] ?? LEVEL_BADGE.guardian

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      <div>
        <h1 className="text-2xl font-bold text-white">Autonomy Posture</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Read-only view of the three axes (level · flavor · deployment target).
          This page changes nothing — upgrades are an attested Captain ritual,
          downgrades are the Captain&apos;s Telegram verb.
        </p>
      </div>

      {/* The tile — posture-status.py JSON, rendered verbatim */}
      <div className="max-w-xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <div className="flex items-center gap-3">
          <span
            className={`rounded-full border px-3 py-1 font-mono text-sm ${badge}`}
          >
            {status.level}
          </span>
          {!status.attested && (
            <span className="text-xs text-zinc-500">
              (unattested ruling ⇒ fail-closed default applies)
            </span>
          )}
        </div>
        <div className="mt-4">
          <Row label="flavor" value={status.flavor ?? '— (no ruling)'} />
          <Row label="deployment target" value={status.target ?? '— (unknown)'} />
          <Row label="attested" value={status.attested ? 'yes (locked ruling)' : 'no'} />
          <Row label="narrow cap" value={status.narrow_cap ?? '— (none)'} />
        </div>
        {status.error && (
          <p className="mt-4 text-xs text-red-400">
            status probe failed ({status.error}) — showing the fail-closed
            guardian shape.
          </p>
        )}
      </div>

      {/* Downgrade — always allowed, but only via the Captain-authenticated verb */}
      <div className="max-w-xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="text-sm font-semibold text-white">
          Downgrade (narrow — instant, no unlock)
        </h2>
        <p className="mt-2 text-sm text-zinc-400">
          Reply to the Captain DM (Telegram binder) with:
        </p>
        <pre className="mt-3 overflow-x-auto rounded bg-zinc-950 p-3 font-mono text-xs text-zinc-300">
          {'posture guardian\nposture earn_up'}
        </pre>
        <p className="mt-2 text-xs text-zinc-500">
          Writes <code>instance/config/posture-narrow</code> (narrow-only cap).
          <code> posture clear</code> removes it — WARNING: that restores the
          attested level. Emergency env brake:{' '}
          <code>CABINET_POSTURE=guardian</code>.
        </p>
      </div>

      {/* Upgrade — the ritual, verbatim; never a button */}
      <div className="max-w-xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="text-sm font-semibold text-white">
          Upgrade (widen — attested Captain ritual only)
        </h2>
        <p className="mt-2 text-sm text-zinc-400">
          No dashboard control can widen the posture (forge-vector refusal).
          On the deployment machine, the Captain runs:
        </p>
        <pre className="mt-3 overflow-x-auto rounded bg-zinc-950 p-3 font-mono text-xs text-zinc-300">
          {UPGRADE_RITUAL}
        </pre>
        <p className="mt-2 text-xs text-zinc-500">
          docker target: the ritual is host-side — edit in the host checkout
          and keep the <code>:ro</code> bind mount.
        </p>
      </div>
    </div>
  )
}
