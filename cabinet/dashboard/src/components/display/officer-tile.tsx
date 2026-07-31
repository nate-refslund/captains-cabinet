/**
 * One officer tile for the kiosk wall grid. Server component — pure render.
 *
 * Big status dot + slug + title + current task + WIP badge, sized to be
 * legible from across a room. Status colors:
 *   unreadable        → dashed amber (heartbeat unparseable or future-dated)
 *   online            → green  (heartbeat < 15min)
 *   alive-but-stale   → amber  (heartbeat present but ≥ 15min old)
 *   offline           → zinc   (no heartbeat)
 */

import type { DisplayOfficer } from '@/lib/display-data'
import { WIP_CAP } from '@/lib/display-data'

interface OfficerTileProps {
  officer: DisplayOfficer
  title: string
}

export default function OfficerTile({ officer, title }: OfficerTileProps) {
  const { online, stale, unknown, wipCount, currentTaskTitle, blockedCount } = officer

  // Status → palette
  // `unknown` leads every ternary: an unreadable heartbeat may never fall out
  // the green end of a chain on a wall nobody is standing next to.
  const dotColor = unknown ? 'bg-amber-400' : online ? 'bg-green-500' : stale ? 'bg-amber-500' : 'bg-zinc-600'
  const dotGlow = online
    ? 'shadow-[0_0_16px_3px_rgba(34,197,94,0.6)]'
    : stale
      ? 'shadow-[0_0_16px_3px_rgba(245,158,11,0.5)]'
      : ''
  const statusLabel = unknown ? '? unreadable' : online ? 'online' : stale ? 'stale' : 'offline'
  const statusText = unknown ? 'text-amber-300' : online ? 'text-green-400' : stale ? 'text-amber-400' : 'text-zinc-500'
  const ring = online
    ? 'border-green-500/30'
    : stale
      ? 'border-amber-500/30'
      : 'border-zinc-800'

  return (
    <div
      className={`flex flex-col gap-4 rounded-2xl border ${ring} bg-zinc-900/80 p-6 xl:p-7`}
    >
      {/* Header row: dot + slug + status label */}
      <div className="flex items-center gap-4">
        <span
          className={`inline-block h-5 w-5 shrink-0 rounded-full ${dotColor} ${dotGlow} ${online && !unknown ? 'animate-pulse' : ''}`}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <div className="truncate text-3xl font-black uppercase tracking-tight text-white xl:text-4xl">
            {officer.slug}
          </div>
          <div className="truncate text-sm font-medium text-zinc-400 xl:text-base">
            {title}
          </div>
        </div>
        <span className={`shrink-0 text-sm font-semibold uppercase tracking-wide ${statusText}`}>
          {statusLabel}
        </span>
      </div>

      {/* Current task */}
      <div className="min-h-[3.5rem]">
        <div className="text-[0.7rem] font-semibold uppercase tracking-widest text-zinc-600">
          Working on
        </div>
        {currentTaskTitle ? (
          <div className="mt-1 line-clamp-2 text-xl font-semibold leading-snug text-zinc-100 xl:text-2xl">
            {currentTaskTitle}
          </div>
        ) : (
          <div className="mt-1 text-xl font-medium italic text-zinc-600 xl:text-2xl">idle</div>
        )}
      </div>

      {/* WIP + blocked badges */}
      <div className="flex items-center gap-3">
        <span className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-base font-bold text-white">
          {wipCount}
          <span className="text-zinc-500">/{WIP_CAP}</span>
          <span className="ml-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">
            wip
          </span>
        </span>
        {blockedCount > 0 && (
          <span className="rounded-lg border border-red-500/40 bg-red-900/25 px-3 py-1.5 text-base font-bold text-red-400">
            {blockedCount}
            <span className="ml-1.5 text-xs font-medium uppercase tracking-wide">blocked</span>
          </span>
        )}
      </div>
    </div>
  )
}
