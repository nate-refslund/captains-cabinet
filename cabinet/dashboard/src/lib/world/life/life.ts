/**
 * T2 LIFE — the composing reducer: one deterministic step over every LIFE
 * behavior (commute walks, construction sites + crews, fauna, apprentice
 * figures, officer life-states).
 *
 * Contract (same as director.ts): lifeStep(state, input) is a PURE reducer
 * on the logical tick — no wall clock (snapshot ts arrives as data), no
 * unseeded randomness. Feeding two reducers the identical input sequence
 * yields identical output sequences forever (the determinism suite replays
 * exactly this).
 *
 * Grammar law: every behavior is gated on its show-grammar v3 LIFE block
 * (life-grammar.ts). config = null or a block absent → that behavior is
 * OFF (fail-closed: no pixels without Captain-merged law).
 *
 * Killswitch law: the world halts — the reducer freezes its effective tick
 * at the freeze point and re-emits (fauna stop mid-flap, crews mid-swing,
 * commuters mid-stride), matching the director's freeze semantics.
 */
import type { ChronicleRecord, OfficerPresence } from '../types'
import {
  commuteStep,
  commuterProgress,
  initialCommuteState,
  passingGlance,
  type CommuteState,
  type CommuteWalk,
  type District,
} from './commute'
import {
  crewFor,
  foldSiteLedger,
  resolveGreatWork,
  siteProgress,
  siteSign,
  type KeyframeObs,
  type SiteSign,
  type SiteProgress,
  type WorkSite,
  type WrightSprite,
  type GreatWorkResolution,
} from './sites'
import { faunaAt, type FaunaInput, type FaunaSprite } from './fauna'
import {
  apprenticesAt,
  type ApprenticesResult,
} from './apprentices'
import { officerLifeState, type OfficerLifeState } from './states'
import type { LifeGrammar } from './life-grammar'

export interface LifeState {
  commutes: Record<string, CommuteState>
  /**
   * The output captured on the first killswitch tick — re-emitted verbatim
   * while frozen (byte-stable even though the chronicle may keep tailing;
   * frozen mid-stride/mid-flap is the point). Null = live.
   */
  frozenOut: LifeOut | null
}

export function initialLifeState(): LifeState {
  return { commutes: {}, frozenOut: null }
}

export interface LifeOfficerInput {
  presence: OfficerPresence
  /** Current tile position (director/engine-owned). */
  x: number
  y: number
  /** True when the director seated this officer in a group scene. */
  inGroupScene?: boolean
}

export interface LifeInput {
  tick: number
  /** Server-stamped snapshot timestamp (ms epoch) — time as DATA. */
  nowTsMs: number
  clockHour?: number | null
  killswitch?: boolean
  officers: Record<string, LifeOfficerInput>
  records: ChronicleRecord[]
  /** Product-lane roster (instance data — lanes with projects/*.yml). */
  productLanes: ReadonlySet<string>
  /** Parsed P-SITES ledger entries + great-work keyframe observations. */
  siteEntries: WorkSite[]
  siteKeyframes: Record<string, { target: number; obs: KeyframeObs[] }>
  /** Fauna anchors (engine-owned geometry). */
  fauna: Omit<FaunaInput, 'tick' | 'clockHour'>
  /** Grammar law — null = everything OFF (fail-closed). */
  config: LifeGrammar | null
}

export interface CommuterOut {
  slug: string
  walk: CommuteWalk
  /** Road progress 0..1 (engine maps onto the road polyline). */
  progress: number
  /** Facing a passer-by at the crossroads this tick (seeded life). */
  glance: boolean
}

export interface SiteOut {
  site: WorkSite
  progress: SiteProgress
  resolution: GreatWorkResolution
  crew: WrightSprite[]
  sign: SiteSign
}

export interface LifeOut {
  commuters: CommuterOut[]
  districts: Record<string, District>
  sites: SiteOut[]
  fauna: FaunaSprite[]
  apprentices: ApprenticesResult
  states: Record<string, OfficerLifeState>
  /** Honest validation problems (ledger rejects etc.) for the badge layer. */
  problems: string[]
}

const EMPTY_APPRENTICES: ApprenticesResult = { figures: [], overflow: {} }

/** Shift a commute state's clocks +1 for one frozen tick, so journeys and
 * dwell resume EXACTLY where they froze on release (director freeze law —
 * no teleport on unfreeze, no dwell consumed by the halt). */
function shiftFrozenCommute(s: CommuteState): CommuteState {
  return {
    ...s,
    lastArrivalTick: s.lastArrivalTick + 1,
    lastEvalTick: s.lastEvalTick + 1,
    walking: s.walking
      ? { ...s.walking, startTick: s.walking.startTick + 1 }
      : null,
  }
}

/** One deterministic LIFE step. */
export function lifeStep(
  state: LifeState,
  input: LifeInput
): { state: LifeState; out: LifeOut } {
  const cfg = input.config

  // Killswitch, later ticks: the world halts — the frozen output re-emits
  // verbatim (byte-stable even though the chronicle may keep tailing) and
  // every commute clock shifts forward one tick so nothing teleports on
  // release.
  if (input.killswitch && state.frozenOut) {
    const commutes: Record<string, CommuteState> = {}
    for (const slug of Object.keys(state.commutes)) {
      commutes[slug] = shiftFrozenCommute(state.commutes[slug])
    }
    return {
      state: { commutes, frozenOut: state.frozenOut },
      out: state.frozenOut,
    }
  }

  const { tick, nowTsMs } = input
  const slugs = Object.keys(input.officers).sort()

  // ── commute ───────────────────────────────────────────────────────────
  const commutes: Record<string, CommuteState> = {}
  const commuters: CommuterOut[] = []
  const districts: Record<string, District> = {}
  for (const slug of slugs) {
    const prev = state.commutes[slug] ?? initialCommuteState()
    if (!cfg?.commute || input.killswitch) {
      // Suspended: no law, or the first frozen tick (the freeze frame).
      commutes[slug] = input.killswitch ? shiftFrozenCommute(prev) : prev
    } else {
      const cg = cfg.commute
      const { state: next } = commuteStep(prev, {
        slug,
        records: input.records,
        presenceVerb: input.officers[slug].presence.verb ?? null,
        nowTsMs,
        tick,
        productLanes: input.productLanes,
        // Ratified grammar-PR constants win over module defaults.
        switchShare: cg.switchShare,
        switchEvals: cg.switchEvals,
        minDwellTicks: cg.dwellS * 4,
      })
      commutes[slug] = next
    }
    districts[slug] = commutes[slug].district
    const walking = commutes[slug].walking
    if (walking) {
      commuters.push({
        slug,
        walk: walking,
        progress: commuterProgress(walking, tick),
        glance: false,
      })
    }
  }
  // Crossroads passing glances (pairwise over the tiny commuter set).
  for (let i = 0; i < commuters.length; i++) {
    for (let j = i + 1; j < commuters.length; j++) {
      if (
        passingGlance(
          { walk: commuters[i].walk, tick },
          { walk: commuters[j].walk, tick }
        )
      ) {
        commuters[i].glance = true
        commuters[j].glance = true
      }
    }
  }

  // ── construction sites ────────────────────────────────────────────────
  const sites: SiteOut[] = []
  let problems: string[] = []
  if (cfg?.construction) {
    const fold = foldSiteLedger(input.siteEntries)
    problems = [...fold.problems]
    for (const site of fold.sites) {
      const kf = input.siteKeyframes[site.id]
      const resolution: GreatWorkResolution =
        site.siteClass === 'great'
          ? kf
            ? resolveGreatWork(kf.target, kf.obs)
            : 'building'
          : 'confirmed'
      sites.push({
        site,
        progress: siteProgress(site, tick),
        resolution,
        crew: crewFor(site, tick, resolution),
        sign: siteSign(site, tick),
      })
    }
  }

  // ── fauna (ratified per-species law: kind renders iff its species has a
  //    grammar entry — bird→birds, butterfly→butterflies, fish→fish,
  //    cat→cat, dog→dog) ────────────────────────────────────────────────
  const SPECIES_OF: Record<string, string> = {
    bird: 'birds',
    butterfly: 'butterflies',
    fish: 'fish',
    cat: 'cat',
    dog: 'dog',
    chicken: 'chicken_flock',
  }
  const fauna: FaunaSprite[] = cfg?.fauna
    ? faunaAt({ ...input.fauna, tick, clockHour: input.clockHour }).filter(
        (f) => SPECIES_OF[f.kind] in cfg.fauna!
      )
    : []

  // ── apprentices ───────────────────────────────────────────────────────
  const officerPos: Record<string, { x: number; y: number }> = {}
  for (const slug of slugs) {
    officerPos[slug] = { x: input.officers[slug].x, y: input.officers[slug].y }
  }
  const apprentices = cfg?.apprentices
    ? apprenticesAt({
        records: input.records,
        nowTsMs,
        tick,
        officerPos,
        cap: cfg.apprentices.capPerOfficer,
      })
    : EMPTY_APPRENTICES

  // ── life states ───────────────────────────────────────────────────────
  const states: Record<string, OfficerLifeState> = {}
  for (const slug of slugs) {
    states[slug] = officerLifeState({
      presence: input.officers[slug].presence,
      clockHour: input.clockHour,
      killswitch: input.killswitch,
      commuting: commutes[slug].walking !== null,
      inGroupScene: input.officers[slug].inGroupScene,
    })
  }

  const out: LifeOut = {
    commuters,
    districts,
    sites,
    fauna,
    apprentices,
    states,
    problems,
  }
  return {
    state: { commutes, frozenOut: input.killswitch ? out : null },
    out,
  }
}
