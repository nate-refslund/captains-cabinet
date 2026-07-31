import { exec as execCb } from 'child_process'
import { promisify } from 'util'
import { cabinetRoot } from './cabinet-root'
import {
  isNotLiveStore,
  isUnconfiguredInProduction,
  resolveStorePosture,
  type StorePosture,
} from './store-posture'

const exec = promisify(execCb)
const prefix = process.env.CABINET_PREFIX || 'cabinet'
const container = `${prefix}-officers`
/**
 * Two different questions, which used to share one flag (2026-07-31).
 *
 *   IS_FABRICATED — may this module INVENT an answer? Only from the explicit,
 *     non-production demo opt-in. `getTmuxWindows()` returning the five-officer
 *     roster is what rendered "Officers: 4/5 running" on a dashboard that had
 *     contacted nothing.
 *   NOT_LIVE — should this module refrain from shelling into a runtime that is
 *     not there? True for `unconfigured` as well. This one is a REFUSAL: the
 *     call REJECTS, and each caller's existing `catch` is what turns it into
 *     that caller's honest empty value.
 *
 * Collapsing them was the defect. An absent `REDIS_URL` is a reason not to
 * exec; it was never a reason to answer — which is what the no-op sentinel this
 * guard used to RETURN did, for 19 write actions, until 2026-07-31.
 */
const storeReading = resolveStorePosture(process.env)
const IS_FABRICATED = storeReading.fabricated
const NOT_LIVE = isNotLiveStore(storeReading)

// ---------------------------------------------------------------------------
// Runtime mode: Docker (Hetzner) vs Mac-native (Mac mini).
// ---------------------------------------------------------------------------
// Docker deployment: the dashboard runs INSIDE a container and exec's into the
// sibling `${prefix}-officers` container. Commands resolve against /opt/...
//
// Mac-native deployment: the dashboard runs as a plain Node process on the same
// Mac mini as the officers + Redis + the cabinet repo. There is no container —
// commands must run LOCALLY with cwd = CABINET_ROOT so relative paths like
// `cabinet/scripts/org-runtime.py` resolve. This is what powers the office
// wall-display + the rest of the dashboard on the Mac mini.
//
// Mode resolution: explicit CABINET_RUNTIME_MODE wins; else infer native when
// CABINET_ROOT is set (deploy-mac.sh / start-officer-mac.sh export it).
//
// NOTE (Wave B): repo-FILE reads/writes no longer route through this module —
// governance.ts and files.ts use direct node:fs against the checkout root. A
// docker-mode dashboard without the checkout mounted therefore renders honest
// "file not found" blocks for repo-file reads (docker mode is extinct per egg
// plan R086; the exec path below survives for the remaining runtime probes).
const RUNTIME_MODE: 'native' | 'docker' =
  process.env.CABINET_RUNTIME_MODE === 'native'
    ? 'native'
    : process.env.CABINET_RUNTIME_MODE === 'docker'
      ? 'docker'
      : process.env.CABINET_ROOT
        ? 'native'
        : 'docker'

const CABINET_ROOT = cabinetRoot()

// cabinet/.env path — resolved against the checkout root in every mode.
// CABINET_ENV_PATH overrides.
const ENV_PATH = process.env.CABINET_ENV_PATH || `${CABINET_ROOT}/cabinet/.env`

export const isNativeRuntime = () => RUNTIME_MODE === 'native'

/**
 * A COMMAND THAT WAS NOT RUN. Thrown — never returned.
 *
 * WHAT THIS REPLACED, AND WHY THE SHAPE IS THE FIX. This function used to
 * answer `{ stdout: 'mock: command executed', stderr: '' }` whenever the store
 * was not live. That is a well-formed SUCCESS for work that never happened, and
 * the docstring above it claimed "every caller below already branches on it" —
 * a claim about `docker.ts`'s own three readers, which was never true of the
 * 39 call sites outside this file. Counted 2026-07-31: **19 of them turned that
 * value straight into `{ success: true }`**, and two rendered the sentinel
 * itself as data (an active-project name in the nav, and a filename that config
 * edits were then written into).
 *
 * Reproduced end to end against the BUILT app in `NODE_ENV=production` with
 * `REDIS_URL` unset, driving the real handlers through a real browser:
 *   · `/officers/create` → "Officer Created · the officer is booting and will
 *     announce on the warroom shortly", with `create-officer.sh` never invoked.
 *   · `/integrations` → the add-secret modal closed on `{success:true}` with
 *     `cabinet/.env` byte-identical afterwards.
 * Both screens rendered underneath this app's own banner: "NO STORE CONFIGURED
 * — nothing here is a measurement". The page disclosed that it had measured
 * nothing and claimed an act in the same frame.
 *
 * A REJECTION IS THE ONLY SHAPE A CALLER CANNOT MISTAKE FOR SUCCESS. A
 * discriminated `{ executed: false }` return would have been compiler-enforced,
 * but it would also have forced 39 call sites to be edited in one pass — and
 * "fix every site at once without a per-site reproduction" is how silent holes
 * become green ones. Throwing lands the honest sentence in the failure branch
 * all 19 already had — `catch (err) { return { …, error: err.message } }`,
 * whose flag is `success: false` in most files, `ok: false` in `actions/gaps.ts`
 * and a bare `{ error }` in `createOfficer` — so ONE change at the source closes
 * them, and every read path that already meant "absent" keeps meaning absent
 * through the catch it already had.
 *
 * The message is written to be READ BY THE CAPTAIN, because it is rendered
 * verbatim by those callers.
 */
export class CommandNotExecutedError extends Error {
  readonly posture: StorePosture
  readonly command: string
  constructor(posture: StorePosture, command: string, message: string) {
    super(message)
    this.name = 'CommandNotExecutedError'
    this.posture = posture
    this.command = command
  }
}

/**
 * Why nothing ran, in plain words.
 *
 * Production + `unconfigured` gets its own sentence and that is the production
 * exclusion this plane was missing (`store-posture.ts:isUnconfiguredInProduction`
 * carries the reasoning). Note what is NOT conditional on the environment: the
 * REFUSAL. Both sides refuse; only the diagnosis differs.
 *
 * WHY THIS TRANSPORT DOES NOT SIMPLY EXECUTE IN PRODUCTION, since the store
 * posture is plainly the wrong sensor for "is there a runtime here" (a
 * Mac-native box with a checkout and tmux can run commands whether or not Redis
 * is configured): because widening what THIS module runs — `tmux kill-window`,
 * `rm -f`, `sed -i` on config, `create-officer.sh` — on a deployment nobody has
 * verified is a change nobody asked for, while refusing is one env var away
 * from being resolved (`start-dashboard.sh` already defaults `REDIS_URL`).
 *
 * SCOPE, stated because the claim is otherwise false of the app: this is the
 * only shell transport that consults the store posture at all. `lib/crontab.ts`,
 * `lib/attention/verdict.ts`, `lib/evidence/read.ts`, `lib/library.ts`,
 * `lib/onboarding/bridge.ts` and the `/posture` page shell out with NO posture
 * gate, and always did — they are unaffected by this change and remain open.
 * Replacing the coupling with a real runtime probe, and deciding what those six
 * should do, is the right long-term answer and is deliberately NOT smuggled in
 * here.
 */
function notExecutedReason(): string {
  if (isUnconfiguredInProduction(process.env)) {
    return (
      'this deployment has no store configured (REDIS_URL is unset on a production build), ' +
      'so nothing was run and nothing was changed. That is a misconfiguration of this ' +
      'dashboard rather than a mode it is in — set REDIS_URL to your cabinet’s store ' +
      '(start-dashboard.sh defaults it to redis://localhost:6379) and try again.'
    )
  }
  return `nothing was run and nothing was changed — ${storeReading.source}`
}

/**
 * Run a shell command against the cabinet runtime.
 *
 * - Docker mode: `docker exec -u cabinet <container> bash -c '<cmd>'`
 * - Native mode: runs the command directly in a shell with cwd = CABINET_ROOT.
 *
 * NOT_LIVE (demo OR unconfigured) REFUSES: a dashboard that has not contacted a
 * store has no business shelling into a runtime, and — the part that was
 * missing — no business answering as though it had.
 */
export async function dockerExec(command: string): Promise<{ stdout: string; stderr: string }> {
  if (NOT_LIVE) {
    console.log(`[no-store] refused to exec (nothing ran): ${command}`)
    throw new CommandNotExecutedError(
      storeReading.posture,
      command,
      notExecutedReason()
    )
  }

  if (RUNTIME_MODE === 'native') {
    // Run locally in the cabinet repo. No container wrapper.
    const { stdout, stderr } = await exec(command, {
      cwd: CABINET_ROOT,
      shell: '/bin/bash',
      maxBuffer: 1024 * 1024 * 16,
    })
    return { stdout: stdout.trim(), stderr: stderr.trim() }
  }

  const escaped = command.replace(/'/g, "'\\''")
  const { stdout, stderr } = await exec(
    `docker exec -u cabinet ${container} bash -c '${escaped}'`
  )
  return { stdout: stdout.trim(), stderr: stderr.trim() }
}

export async function getTmuxWindows(): Promise<string[]> {
  // The roster below is INVENTED. It is what rendered "Officers: 4/5 running"
  // on a dashboard that had contacted nothing, so it is reachable only from
  // the explicit non-production demo opt-in. Unconfigured falls through to the
  // exec path, which REFUSES; the catch below yields an empty roster — an
  // honest absence, and no longer one grown from a fabricated string.
  if (IS_FABRICATED) {
    return ['cos', 'cto', 'cpo', 'cro', 'coo']
  }
  try {
    if (RUNTIME_MODE === 'native') {
      // Mac-native: one tmux SESSION per officer, named "officer-<slug>".
      const { stdout } = await dockerExec(
        `tmux list-sessions -F '#{session_name}' 2>/dev/null || true`
      )
      return stdout
        .split('\n')
        .filter((w) => w.startsWith('officer-'))
        .map((w) => w.replace('officer-', ''))
    }
    // Docker: one session "cabinet" with one WINDOW per officer.
    const { stdout } = await dockerExec(
      'tmux list-windows -t cabinet -F "#{window_name}" 2>/dev/null'
    )
    return stdout
      .split('\n')
      .filter((w) => w.startsWith('officer-'))
      .map((w) => w.replace('officer-', ''))
  } catch {
    return []
  }
}

export async function isClaudeAlive(role: string): Promise<boolean> {
  if (IS_FABRICATED) {
    // In mock mode, most officers are alive except coo
    return role !== 'coo'
  }
  try {
    // Resolve the pane PID. Native = session officer-<role>; Docker = window
    // cabinet:officer-<role>.
    const target = RUNTIME_MODE === 'native' ? `officer-${role}` : `cabinet:officer-${role}`
    const { stdout: panePid } = await dockerExec(
      `tmux list-panes -t ${target} -F '#{pane_pid}' 2>/dev/null | head -1`
    )
    // No sentinel check any more: an unrun command REJECTS, and the catch below
    // is what turns it into "not alive". A dead branch left here would tell the
    // next reader the sentinel still exists.
    if (!panePid) return false
    const pid = panePid.trim()
    if (!pid) return false

    // Find a claude/node child of the pane shell. pgrep -P is portable across
    // macOS + Linux (ps --ppid is Linux-only).
    const { stdout: children } = await dockerExec(
      `pgrep -P ${pid} -l 2>/dev/null || ps -o comm= -p $(pgrep -P ${pid} 2>/dev/null) 2>/dev/null || true`
    )
    const procs = children.toLowerCase()
    return procs.includes('claude') || procs.includes('node')
  } catch {
    return false
  }
}

export interface CronJob {
  schedule: string
  command: string
  description: string
}

// dockerWriteFile / dockerReadFile are GONE (Wave B): their only callers
// (governance.ts, files.ts) now do real node:fs I/O — the mock branch here
// used to console-log no-op a Captain's save while the action claimed success.

/**
 * The schedule, WITH whether it could be read.
 *
 * `getCronSchedule()` swallowed every failure into `[]`, so a crontab the
 * dashboard could not read rendered as the sentence "0 jobs" — a measurement
 * claim about a machine it had just failed to ask. That is the same shape as
 * the emergency stop reading "fleet running" from a store it never contacted,
 * on the read side of this page rather than the write side.
 *
 * `unreadable` is the reason, in plain words, or null when the number is real.
 * An EMPTY crontab is not unreadable: zero jobs and no error is a fact.
 */
export interface CronScheduleReading {
  jobs: CronJob[]
  unreadable: string | null
}

/**
 * The name shown in the "Job" column.
 *
 * `command.split('/').pop()` on a line ending `>> /var/log/watchdog/cron.log
 * 2>&1` yields "cron.log 2>&1" — which every job with a log redirect shares, so
 * the table showed three identical names and the Captain could not tell which
 * row they were about to delete. The redirect is stripped first.
 */
export function cronJobName(command: string): string {
  const withoutRedirect = command.split(/\s+\d?[<>]/)[0].trim() || command
  const first = withoutRedirect.split(/\s+/)[0] || withoutRedirect
  return first.split('/').pop() || first
}

/** The schedule only. Kept for callers that have no way to render a reason. */
export async function getCronSchedule(): Promise<CronJob[]> {
  return (await readCronSchedule()).jobs
}

export async function readCronSchedule(): Promise<CronScheduleReading> {
  if (IS_FABRICATED) {
    return {
      unreadable: null,
      jobs: [
        { schedule: '*/5 * * * *', command: 'health-check.sh', description: 'Health check' },
        { schedule: '*/15 * * * *', command: 'token-refresh.sh', description: 'Token refresh' },
        { schedule: '0 6 * * *', command: 'morning-briefing.sh', description: 'Morning briefing (07:00 CET)' },
        { schedule: '0 18 * * *', command: 'evening-briefing.sh', description: 'Evening briefing (19:00 CET)' },
        { schedule: '0 */4 * * *', command: 'research-sweep.sh', description: 'Research sweep' },
        { schedule: '0 */12 * * *', command: 'backlog-refinement.sh', description: 'Backlog refinement' },
        { schedule: '30 6 * * *', command: 'retrospective.sh', description: 'Retrospective (07:30 CET)' },
        { schedule: '0 19 * * *', command: 'cost-dashboard.sh', description: 'Cost dashboard (20:00 CET)' },
      ],
    }
  }
  try {
    if (RUNTIME_MODE === 'native') {
      // Mac-native schedules are LaunchAgents, not crontab. List the cabinet
      // plists registered with launchd.
      const { stdout } = await dockerExec(
        `launchctl list 2>/dev/null | grep -i 'com.cabinet' || true`
      )
      // The sentinel filter that used to live here is gone with the sentinel.
      // It also hid something worse: filtering the no-op away left
      // `{ unreadable: null, jobs: [] }` — the sentence "0 jobs" as a FACT
      // about a machine this process never asked. An unrun `launchctl list`
      // now rejects, and the catch below reports it as unreadable, with why.
      const lines = stdout
        .trim()
        .split('\n')
        .filter((l: string) => Boolean(l))
      return {
        unreadable: null,
        jobs: lines.map((line: string) => {
          // launchctl list cols: PID  Status  Label
          const parts = line.trim().split(/\s+/)
          const label = parts[parts.length - 1] || line
          const name = label.replace('com.cabinet.', '')
          return { schedule: 'launchd', command: label, description: name }
        }),
      }
    }
    const watchdogContainer = `${prefix}-watchdog`
    // stderr is NOT discarded any more: `2>/dev/null` threw away the only
    // sentence that could distinguish "no jobs" from "could not ask".
    const { stdout } = await exec(`docker exec ${watchdogContainer} crontab -l`)
    const lines = stdout.trim().split('\n').filter((l: string) => l && !l.startsWith('#'))
    return {
      unreadable: null,
      jobs: lines.map((line: string) => {
        const parts = line.trim().split(/\s+/)
        const schedule = parts.slice(0, 5).join(' ')
        const command = parts.slice(5).join(' ')
        return { schedule, command, description: cronJobName(command) }
      }),
    }
  } catch (err) {
    // "no crontab for <user>" is an empty schedule, not a failed read — the
    // same distinction `lib/crontab.ts` makes before it will write anything.
    const detail = err instanceof Error ? err.message : String(err)
    if (/no crontab for/i.test(detail)) return { unreadable: null, jobs: [] }
    return {
      unreadable: `the schedule could not be read — ${detail
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .slice(-1)[0] || detail}`,
      jobs: [],
    }
  }
}

export async function getEnvVars(): Promise<Record<string, string>> {
  if (IS_FABRICATED) {
    return {
      ANTHROPIC_API_KEY: 'sk-ant-...mock1234',
      ELEVENLABS_API_KEY: 'el-...mock5678',
      GITHUB_PAT: 'ghp_...mock9012',
      LINEAR_API_KEY: 'lin_api_...mock3456',
      NOTION_API_KEY: 'ntn_...mock7890',
      NEON_CONNECTION_STRING: 'postgresql://...mock',
      VOYAGE_API_KEY: 'voy-...mock1111',
      PERPLEXITY_API_KEY: 'pplx-...mock2222',
      BRAVE_SEARCH_API_KEY: 'BSA-...mock3333',
      EXA_API_KEY: 'exa-...mock4444',
      MAPBOX_TOKEN: 'pk.ey...mock5555',
      TELEGRAM_HQ_CHAT_ID: '-10012345',
      CAPTAIN_TELEGRAM_ID: '12345678',
      TELEGRAM_COS_TOKEN: '70012345:AAE...mock',
      TELEGRAM_CTO_TOKEN: '70012346:AAE...mock',
      TELEGRAM_CPO_TOKEN: '70012347:AAE...mock',
      TELEGRAM_CRO_TOKEN: '70012348:AAE...mock',
    }
  }
  try {
    const { stdout } = await dockerExec(
      `grep -v '^#' '${ENV_PATH}' | grep -v '^$'`
    )
    const vars: Record<string, string> = {}
    for (const line of stdout.split('\n')) {
      const eqIdx = line.indexOf('=')
      if (eqIdx > 0) {
        const key = line.substring(0, eqIdx).trim()
        const value = line.substring(eqIdx + 1).trim()
        vars[key] = value
      }
    }
    return vars
  } catch {
    return {}
  }
}

export async function isTelegramConnected(role: string): Promise<boolean> {
  if (IS_FABRICATED) {
    // In mock mode, most officers are connected except coo
    return role !== 'coo'
  }
  try {
    // Read the bot token from .env (path is runtime-mode aware)
    const upperRole = role.toUpperCase()
    const { stdout: token } = await dockerExec(
      `grep "^TELEGRAM_${upperRole}_TOKEN=" '${ENV_PATH}' 2>/dev/null | cut -d= -f2`
    )
    const trimmedToken = token.trim()
    if (!trimmedToken) return false

    // Call Telegram getMe to verify the token is valid and bot is reachable
    const { stdout: response } = await dockerExec(
      `curl -s --max-time 5 "https://api.telegram.org/bot${trimmedToken}/getMe"`
    )
    try {
      const parsed = JSON.parse(response)
      return parsed.ok === true
    } catch {
      return false
    }
  } catch {
    return false
  }
}
