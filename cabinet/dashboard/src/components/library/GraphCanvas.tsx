'use client'

/**
 * GraphCanvas — the Library's force-directed [[wikilink]] graph.
 *
 * Resurrected 2026-07-17 (Captain ruling: the reader returns) from the
 * pre-retirement Spec 045 component, repointed at the FILESYSTEM graph:
 *   - data arrives fully computed as a SERIALIZED PROP from the server
 *     component (lib/vault-graph.ts) — no fetch, no API route, no DB;
 *   - grouping/colors key on the note's top-level vault folder (the
 *     filesystem analog of the retired per-Space clustering);
 *   - clicking a node navigates INTO the Library via vaultHref(relpath),
 *     which percent-encodes every segment — always an internal /library/…
 *     path, never an external href;
 *   - dir filter + search run client-side over the prop data.
 *
 * Visual choices preserved from the original: 2D mode, node-size by degree,
 * warmupTicks=100 / cooldownTicks=0 (instant render, no jitter), label
 * culling at zoom<1.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
// TYPE-ONLY import — vault-graph.ts reaches fs on the server; its types are
// erased at compile time so none of that enters the client bundle.
import type { VaultGraphData, VaultGraphNode } from '@/lib/vault-graph'
// Value import is safe: vault-wikilinks is a PURE module (no fs, no DB).
import { vaultHref } from '@/lib/vault-wikilinks'
// Hover tooltip label — HTML-ESCAPED (float-tooltip renders string labels
// via innerHTML; frontmatter titles / dir names are untrusted). See
// graph-tooltip.ts for the sink analysis + its XSS negative controls.
import { graphNodeTooltipHtml, ROOT_DIR_LABEL } from './graph-tooltip'

// react-force-graph-2d ships as ESM and reaches for `window` at import time —
// next/dynamic with ssr:false keeps the bundle out of the SSR pass entirely.
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false })

interface Props {
  data: VaultGraphData
}

interface GraphNode extends VaultGraphNode {
  x?: number
  y?: number
  vx?: number
  vy?: number
}

interface GraphLink {
  [key: string]: unknown
  source: string | GraphNode
  target: string | GraphNode
}

// Color palette indexed by top-level-dir position (stable across renders:
// the dir list is derived deterministically from the server-provided data).
const DIR_PALETTE = [
  '#60a5fa', // blue-400
  '#a78bfa', // violet-400
  '#34d399', // emerald-400
  '#fbbf24', // amber-400
  '#f87171', // red-400
  '#fb7185', // rose-400
  '#22d3ee', // cyan-400
  '#a3e635', // lime-400
  '#f472b6', // pink-400
  '#94a3b8', // slate-400
]

export default function GraphCanvas({ data }: Props) {
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [showLabels, setShowLabels] = useState(true)
  const [selectedDirs, setSelectedDirs] = useState<Set<string>>(new Set())
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ width: 800, height: 600 })

  // Deterministic top-level-dir list (sorted; root first when present).
  const dirs = useMemo(() => {
    const seen = new Set<string>()
    for (const n of data.nodes) seen.add(n.dir)
    return [...seen].sort((a, b) => a.localeCompare(b))
  }, [data])

  const dirColor = useMemo(() => {
    const map = new Map<string, string>()
    dirs.forEach((d, i) => map.set(d, DIR_PALETTE[i % DIR_PALETTE.length]))
    return map
  }, [dirs])

  // Client-side dir filter over the serialized data (the old component
  // re-fetched per filter; the filesystem graph is already fully loaded).
  // Nodes are shallow-cloned so the force simulation can decorate them with
  // x/y without mutating the server-serialized props.
  const graphData = useMemo(() => {
    const active =
      selectedDirs.size === 0 ? null : selectedDirs
    const nodes = data.nodes
      .filter((n) => active === null || active.has(n.dir))
      .map((n) => ({ ...n }))
    const visible = new Set(nodes.map((n) => n.id))
    const links = data.edges
      .filter((e) => visible.has(e.source) && visible.has(e.target))
      .map((e) => ({ source: e.source, target: e.target }))
    return { nodes: nodes as GraphNode[], links: links as unknown as GraphLink[] }
  }, [data, selectedDirs])

  // Resize observer for responsive canvas sizing.
  useEffect(() => {
    if (!containerRef.current) return
    const el = containerRef.current
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setSize({ width: Math.max(300, width), height: Math.max(400, height) })
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const searchLower = search.trim().toLowerCase()
  const matchedNodeIds = useMemo(() => {
    if (!searchLower) return null
    return new Set(
      graphData.nodes
        .filter(
          (n) =>
            n.title.toLowerCase().includes(searchLower) ||
            n.id.toLowerCase().includes(searchLower)
        )
        .map((n) => n.id)
    )
  }, [searchLower, graphData])

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      if (!node.id) return
      // vaultHref percent-encodes every segment → always an internal
      // /library/… path.
      router.push(vaultHref(node.id))
    },
    [router]
  )

  const nodeCanvasObject = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      if (typeof node.x !== 'number' || typeof node.y !== 'number') return
      const baseRadius = 4 + Math.min(8, Math.sqrt(node.degree || 0) * 1.5)
      const isMatch = matchedNodeIds === null || matchedNodeIds.has(node.id)
      const fill = dirColor.get(node.dir) ?? '#94a3b8'

      ctx.beginPath()
      ctx.arc(node.x, node.y, baseRadius, 0, 2 * Math.PI)
      ctx.fillStyle = isMatch ? fill : 'rgba(120, 120, 120, 0.25)'
      ctx.fill()
      ctx.strokeStyle = isMatch ? 'rgba(255,255,255,0.6)' : 'rgba(255,255,255,0.15)'
      ctx.lineWidth = 1 / globalScale
      ctx.stroke()

      // Label culling — only render labels at zoom>=1 unless toggle forces them.
      if (showLabels && (globalScale >= 1 || isMatch)) {
        const fontSize = Math.max(10, 12 / globalScale)
        ctx.font = `${fontSize}px sans-serif`
        ctx.fillStyle = isMatch ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.25)'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        const label = node.title.length > 32 ? node.title.slice(0, 30) + '…' : node.title
        ctx.fillText(label, node.x + baseRadius + 2, node.y)
      }
    },
    [dirColor, matchedNodeIds, showLabels]
  )

  const linkColor = useCallback(() => 'rgba(140, 140, 140, 0.35)', [])

  const toggleDir = (d: string) => {
    setSelectedDirs((prev) => {
      const next = new Set(prev)
      if (next.has(d)) next.delete(d)
      else next.add(d)
      return next
    })
  }

  const totalNodes = graphData.nodes.length
  const totalEdges = graphData.links.length
  const matchedCount = matchedNodeIds === null ? null : matchedNodeIds.size

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-sm">
        <input
          type="search"
          placeholder="Search notes…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-white placeholder:text-zinc-500 focus:border-zinc-500 focus:outline-none"
        />
        <label className="flex items-center gap-1.5 text-zinc-300">
          <input
            type="checkbox"
            checked={showLabels}
            onChange={(e) => setShowLabels(e.target.checked)}
          />
          Labels
        </label>
        <div className="flex flex-wrap items-center gap-1.5">
          {dirs.map((d) => {
            const active = selectedDirs.size === 0 || selectedDirs.has(d)
            const color = dirColor.get(d) ?? '#94a3b8'
            return (
              <button
                key={d || ROOT_DIR_LABEL}
                type="button"
                onClick={() => toggleDir(d)}
                className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
                  active
                    ? 'border-zinc-600 bg-zinc-800 text-white'
                    : 'border-zinc-800 bg-zinc-950 text-zinc-500'
                }`}
              >
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: color }}
                />
                {d || ROOT_DIR_LABEL}
              </button>
            )
          })}
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs text-zinc-500">
          <span>
            {totalNodes} note{totalNodes === 1 ? '' : 's'} · {totalEdges} link
            {totalEdges === 1 ? '' : 's'}
            {matchedCount !== null && ` · ${matchedCount} matched`}
          </span>
          {data.truncated && (
            <span
              className="rounded-md border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 text-zinc-400"
              title="The bounded vault walk hit a depth/file/parse cap — this graph is a slice of the corpus."
            >
              truncated
            </span>
          )}
          {totalNodes > 1000 && (
            <span
              className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-amber-300"
              title="Large graphs may be sluggish on iOS Safari and low-power devices. Filter by folder to scope."
            >
              large graph — perf may degrade
            </span>
          )}
        </div>
      </div>

      {/* Canvas */}
      <div
        ref={containerRef}
        className="relative flex-1 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950"
      >
        {graphData.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
            No notes in the graph yet. Add [[wikilinks]] between vault notes to
            grow it.
          </div>
        )}
        {graphData.nodes.length > 0 && (
          <ForceGraph2D
            graphData={graphData}
            width={size.width}
            height={size.height}
            backgroundColor="#09090b"
            warmupTicks={100}
            cooldownTicks={0}
            nodeRelSize={4}
            nodeCanvasObject={(node, ctx, globalScale) =>
              nodeCanvasObject(node as GraphNode, ctx, globalScale)
            }
            nodePointerAreaPaint={(node, color, ctx) => {
              const n = node as GraphNode
              if (typeof n.x !== 'number' || typeof n.y !== 'number') return
              const r = 4 + Math.min(8, Math.sqrt(n.degree || 0) * 1.5)
              ctx.fillStyle = color
              ctx.beginPath()
              ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
              ctx.fill()
            }}
            linkSource="source"
            linkTarget="target"
            linkColor={linkColor}
            linkWidth={0.6}
            onNodeClick={(node) => handleNodeClick(node as GraphNode)}
            // NEVER hand this accessor a raw-interpolated string: float-tooltip
            // renders string labels via innerHTML (d3 .html()), and title/dir
            // come from untrusted note frontmatter / folder names. The helper
            // HTML-escapes every field (graph-tooltip.test.ts pins it).
            nodeLabel={(node) => graphNodeTooltipHtml(node as GraphNode)}
          />
        )}
      </div>
    </div>
  )
}
