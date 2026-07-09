/**
 * T2 LIFE — apprentice figures for LIVE subagent runs (unified spec v2
 * §15.5, Captain addendum 1.2 — population law).
 *
 * HUMAN-SHAPED SPRITES = REAL ACTORS ONLY. Subagents ARE real actors, so a
 * live run renders as a small transient APPRENTICE figure near its
 * spawning officer's workplace for the duration of the real run. This
 * supersedes the bestiary's chick-per-subagent mapping (the chicken flock
 * demotes to coop-yard fauna); the `tool.call[Agent]` / `crew.completed`
 * bindings move HERE.
 *
 * Honesty: an apprentice appears only on a real chronicle spawn record and
 * retires on the matching completion record or an explicit TTL — the codex
 * states the TTL semantics outright ("the figure is the run's witness, not
 * a running-count claim"). Cap + numeric overflow keep the render honest
 * without crowding (no fictional villagers, ever).
 *
 * Pure: figures are a fold over chronicle records + the logical tick; no
 * wall clock (record ages are measured against the server-stamped snapshot
 * ts, arriving as data), seeded offsets via fnv1a.
 */
import { fnv1a } from '../hash'
import type { ChronicleRecord } from '../types'

/** Honest fallback retirement when no crew.completed ever arrives (20 min —
 * generous for real runs, bounded for crashed ones). */
export const APPRENTICE_TTL_TICKS = 20 * 60 * 4
/** Max rendered figures per officer (ratified grammar v3
 * apprentices.cap_per_officer); beyond it the count is shown as a numeric
 * badge (never invented extra bodies, never hidden runs, never a crowd). */
export const APPRENTICE_CAP = 3
export const TICKS_PER_SECOND = 4

/** Closed spawn predicate: a chronicle tool.call whose tool is the Agent/
 * Task spawner (the estate's real subagent door). */
const SPAWN_TOOLS = new Set(['Agent', 'Task'])

export function isSpawnRecord(r: ChronicleRecord): boolean {
  if (r.verb !== 'tool.call') return false
  return SPAWN_TOOLS.has(r.attrs?.tool ?? '') || r.kind === 'Agent'
}

export function isEndRecord(r: ChronicleRecord): boolean {
  return r.verb === 'crew.completed'
}

export interface ApprenticeFigure {
  id: string
  /** The spawning officer (real actor — the figure stands near them). */
  officer: string
  x: number
  y: number
  /** Chronicle iid of the spawn record (the PROOF). */
  spawnIid: number
  /** Ticks since spawn (drives the walk-in-place frame). */
  frame: number
}

export interface ApprenticesResult {
  figures: ApprenticeFigure[]
  /** Live runs beyond the cap, per officer (rendered as a numeric badge). */
  overflow: Record<string, number>
}

export interface ApprenticesInput {
  records: ChronicleRecord[]
  /** Server-stamped snapshot timestamp (ms epoch) — time as DATA. */
  nowTsMs: number
  tick: number
  /** Current officer positions (tile space) — figures cluster nearby. */
  officerPos: Record<string, { x: number; y: number }>
  /** Grammar-PR cap override (ratified value is the default). */
  cap?: number
}

interface OpenRun {
  iid: number
  ageTicks: number
}

/**
 * Fold the chronicle into live apprentice figures at a tick. Spawn records
 * open a run for their actor; each crew.completed by the same actor closes
 * that actor's OLDEST open run (FIFO — deterministic); runs older than the
 * TTL retire on their own. Officers with no known position render nothing
 * (a figure may never float free of its real actor).
 */
export function apprenticesAt(input: ApprenticesInput): ApprenticesResult {
  const open = new Map<string, OpenRun[]>()
  // Records arrive oldest→newest (snapshot contract) — fold in order.
  for (const r of input.records) {
    if (!r.ts || r.actor === 'unknown' || !r.actor) continue
    const t = Date.parse(r.ts)
    if (Number.isNaN(t)) continue
    const ageTicks = Math.max(
      0,
      Math.round(((input.nowTsMs - t) / 1000) * TICKS_PER_SECOND)
    )
    if (isSpawnRecord(r)) {
      const runs = open.get(r.actor) ?? []
      runs.push({ iid: r.iid, ageTicks })
      open.set(r.actor, runs)
    } else if (isEndRecord(r)) {
      const runs = open.get(r.actor)
      if (runs && runs.length > 0) runs.shift() // FIFO close
    }
  }

  const cap = input.cap ?? APPRENTICE_CAP
  const figures: ApprenticeFigure[] = []
  const overflow: Record<string, number> = {}
  for (const officer of [...open.keys()].sort()) {
    const pos = input.officerPos[officer]
    const live = (open.get(officer) ?? []).filter(
      (run) => run.ageTicks < APPRENTICE_TTL_TICKS
    )
    if (!pos || live.length === 0) continue
    if (live.length > cap) {
      overflow[officer] = live.length - cap
    }
    live.slice(0, cap).forEach((run, i) => {
      // Seeded near-officer offset: a small ring below/beside the desk.
      const h = fnv1a(`${officer}:appr:${run.iid}`)
      const dx = (h % 5) - 2 // -2..2
      const dy = 1 + ((h >>> 8) % 2) // 1..2 (in front, never on top)
      const phase = (h >>> 16) % 4
      figures.push({
        id: `appr:${officer}:${run.iid}`,
        officer,
        x: pos.x + dx,
        y: pos.y + dy,
        spawnIid: run.iid,
        frame: (input.tick + phase + i) % 4,
      })
    })
  }
  return { figures, overflow }
}

/** WHAT/NOW/PROOF card for an apprentice figure. */
export function apprenticeCard(fig: ApprenticeFigure): {
  what: string
  now: string
  proof: string
} {
  return {
    what: `Apprentice — a live subagent run spawned by ${fig.officer}.`,
    now:
      'Present while the run is live; retires on crew.completed or a ' +
      `${APPRENTICE_TTL_TICKS / TICKS_PER_SECOND / 60}-minute TTL. The figure is ` +
      'the run’s witness, not a running-count claim.',
    proof: `chronicle iid ${fig.spawnIid} (tool.call[Agent] by ${fig.officer})`,
  }
}
