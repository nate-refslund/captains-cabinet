/**
 * Cabinet World — shared types (E1 Wardroom).
 *
 * The world is a PURE READ-MODEL: these types describe what the chronicle
 * daemon (E0b) and census writer (E0a) already emit. Nothing here models a
 * write path — the renderer never writes (observer-class doctrine,
 * docs/plans/cabinet-world-build-kickoff-2026-07-07.md).
 */

/** One verb-normalized chronicle record (E0b output; PII-scrubbed at ingest). */
export interface ChronicleRecord {
  v: number
  iid: number
  src: 'org_events' | 'consequence' | 'undo' | 'toollog'
  verb: string
  kind: string
  actor: string
  ts: string | null
  ref: string | null
  agg?: string
  esrc?: string
  attrs?: Record<string, string>
}

/** Per-officer presence entry from cabinet:world:presence (ephemeral, T2). */
export interface OfficerPresence {
  present: boolean
  verb?: string
  since?: string
  object?: string
  hb_ttl_s?: number
}

/** The instant-join snapshot the E0b daemon SETs every tick (EX 60). */
export interface PresenceSnapshot {
  v: number
  ts: string
  killswitch: boolean
  iid_high: number
  officers: Record<string, OfficerPresence>
}

/**
 * Officer entry as served by /api/world/stream: slug is T2 (authed surface);
 * sel is the OPAQUE handle — the ONLY identifier that may appear in URLs
 * (S1-F4: slug/pid-family ids never in URLs).
 */
export interface WorldOfficer {
  slug: string
  sel: string
  presence: OfficerPresence
}

/** Snapshot event payload sent on SSE connect. */
export interface WorldSnapshot {
  connectedAt: string
  killswitch: boolean
  iidHigh: number
  officers: WorldOfficer[]
  /** Most recent chronicle records, oldest→newest (already scrubbed). */
  chronicle: ChronicleRecord[]
  /** Grammar state: loaded versions or the honest pending marker. */
  grammar: GrammarStatus
}

export interface GrammarStatus {
  pending: boolean
  showGrammarVersion: number | null
  morphologyVersion: number | null
  /** Codex coverage 0..1 over grammar+morphology entries (Legend Law gauge). */
  codexCoverage: number | null
}

/** A station in the Wardroom an officer can occupy. */
export interface Station {
  id: string
  x: number
  y: number
  label: string
}

/** Deterministic director output for one officer at one logical tick. */
export interface OfficerScene {
  slug: string
  /** Current interpolated tile position (float tiles). */
  x: number
  y: number
  /** The station the officer is walking toward / occupying. */
  stationId: string
  /** Animation state derived from the grammar verb mapping. */
  anim: 'idle' | 'walk' | 'work' | 'asleep'
  /** The live verb (T2 label text), or null when the activity TTL expired. */
  verb: string | null
  /** Facing derived from walk direction; render-only. */
  facing: 'left' | 'right'
}

/** Camera state — quantized zoom, world-space center. */
export interface CameraState {
  z: 0.5 | 1 | 2
  x: number
  y: number
}

/** Parsed + validated URL state (?z&x&y&sel&at). */
export interface WorldUrlState {
  camera: CameraState
  sel: string | null
  at: string | null
}
