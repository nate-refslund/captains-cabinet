import { exec as execCb } from 'child_process'
import { promisify } from 'util'

const exec = promisify(execCb)
const prefix = process.env.CABINET_PREFIX || 'cabinet'
const container = `${prefix}-officers`
const IS_MOCK = process.env.MOCK_DATA === 'true' || !process.env.REDIS_URL

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
const RUNTIME_MODE: 'native' | 'docker' =
  process.env.CABINET_RUNTIME_MODE === 'native'
    ? 'native'
    : process.env.CABINET_RUNTIME_MODE === 'docker'
      ? 'docker'
      : process.env.CABINET_ROOT
        ? 'native'
        : 'docker'

const CABINET_ROOT = process.env.CABINET_ROOT || '/opt/founders-cabinet'

// cabinet/.env path — parametrized so Mac-native reads the local repo's .env
// and Docker reads the container's /opt path. CABINET_ENV_PATH overrides both.
const ENV_PATH =
  process.env.CABINET_ENV_PATH ||
  (RUNTIME_MODE === 'native' ? `${CABINET_ROOT}/cabinet/.env` : '/opt/founders-cabinet/cabinet/.env')

export const isNativeRuntime = () => RUNTIME_MODE === 'native'

/**
 * Run a shell command against the cabinet runtime.
 *
 * - Docker mode: `docker exec -u cabinet <container> bash -c '<cmd>'`
 * - Native mode: runs the command directly in a shell with cwd = CABINET_ROOT.
 *
 * Mock mode (no REDIS_URL / MOCK_DATA=true) short-circuits for local dev.
 */
export async function dockerExec(command: string): Promise<{ stdout: string; stderr: string }> {
  if (IS_MOCK) {
    console.log(`[mock docker] Would exec: ${command}`)
    return { stdout: 'mock: command executed', stderr: '' }
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
  if (IS_MOCK) {
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
  if (IS_MOCK) {
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
    if (!panePid || panePid === 'mock: command executed') return false
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

export async function dockerWriteFile(path: string, content: string): Promise<void> {
  if (IS_MOCK) {
    console.log(`[mock docker] Would write file: ${path}`)
    return
  }
  // Base64 encode to avoid shell escaping issues
  const b64 = Buffer.from(content).toString('base64')
  await dockerExec(`echo '${b64}' | base64 -d > '${path}'`)
}

export async function dockerReadFile(path: string): Promise<string> {
  if (IS_MOCK) {
    console.log(`[mock docker] Would read file: ${path}`)
    return ''
  }
  const { stdout } = await dockerExec(`cat '${path}' 2>/dev/null || echo ''`)
  return stdout
}

export async function getCronSchedule(): Promise<CronJob[]> {
  if (IS_MOCK) {
    return [
      { schedule: '*/5 * * * *', command: 'health-check.sh', description: 'Health check' },
      { schedule: '*/15 * * * *', command: 'token-refresh.sh', description: 'Token refresh' },
      { schedule: '0 6 * * *', command: 'morning-briefing.sh', description: 'Morning briefing (07:00 CET)' },
      { schedule: '0 18 * * *', command: 'evening-briefing.sh', description: 'Evening briefing (19:00 CET)' },
      { schedule: '0 */4 * * *', command: 'research-sweep.sh', description: 'Research sweep' },
      { schedule: '0 */12 * * *', command: 'backlog-refinement.sh', description: 'Backlog refinement' },
      { schedule: '30 6 * * *', command: 'retrospective.sh', description: 'Retrospective (07:30 CET)' },
      { schedule: '0 19 * * *', command: 'cost-dashboard.sh', description: 'Cost dashboard (20:00 CET)' },
    ]
  }
  try {
    if (RUNTIME_MODE === 'native') {
      // Mac-native schedules are LaunchAgents, not crontab. List the cabinet
      // plists registered with launchd.
      const { stdout } = await dockerExec(
        `launchctl list 2>/dev/null | grep -i 'com.cabinet' || true`
      )
      const lines = stdout.trim().split('\n').filter(Boolean)
      return lines.map((line: string) => {
        // launchctl list cols: PID  Status  Label
        const parts = line.trim().split(/\s+/)
        const label = parts[parts.length - 1] || line
        const name = label.replace('com.cabinet.', '')
        return { schedule: 'launchd', command: label, description: name }
      })
    }
    const watchdogContainer = `${prefix}-watchdog`
    const { stdout } = await exec(
      `docker exec ${watchdogContainer} crontab -l 2>/dev/null`
    )
    const lines = stdout.trim().split('\n').filter((l: string) => l && !l.startsWith('#'))
    return lines.map((line: string) => {
      const parts = line.trim().split(/\s+/)
      const schedule = parts.slice(0, 5).join(' ')
      const command = parts.slice(5).join(' ')
      const scriptName = command.split('/').pop() || command
      return { schedule, command, description: scriptName }
    })
  } catch {
    return []
  }
}

export async function getEnvVars(): Promise<Record<string, string>> {
  if (IS_MOCK) {
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
      TELEGRAM_HQ_CHAT_ID: '-1001234567890',
      CAPTAIN_TELEGRAM_ID: '123456789',
      TELEGRAM_COS_TOKEN: '7001234567:AAE...mock',
      TELEGRAM_CTO_TOKEN: '7001234568:AAE...mock',
      TELEGRAM_CPO_TOKEN: '7001234569:AAE...mock',
      TELEGRAM_CRO_TOKEN: '7001234570:AAE...mock',
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
  if (IS_MOCK) {
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
    if (!trimmedToken || trimmedToken === 'mock: command executed') return false

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
