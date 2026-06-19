import { useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import type { GraphData } from '../../types/chat'

const NODE_COLORS: Record<string, string> = {
  POLICY: '#3b82f6',
  RULE: '#f97316',
  PERSON: '#14b8a6',
  DEPARTMENT: '#8b5cf6',
  BENEFIT: '#22c55e',
  PROCEDURE: '#ec4899',
}
const DEFAULT_COLOR = '#94a3b8'

function nodeColor(type: string): string {
  return NODE_COLORS[type?.toUpperCase()] ?? DEFAULT_COLOR
}

interface Props {
  graphData: GraphData
  width: number
}

export default function GraphPanel({ graphData, width }: Props) {
  const tooltipRef = useRef<HTMLDivElement>(null)

  const fgData = {
    nodes: graphData.nodes.map((n) => ({ ...n })),
    links: graphData.edges.map((e) => ({
      source: e.source,
      target: e.target,
      label: e.relation.replace(/_/g, ' '),
    })),
  }

  const paintNode = useCallback(
    (node: { id?: string; label?: string; type?: string; x?: number; y?: number }, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = (node.label ?? node.id ?? '') as string
      const fontSize = Math.max(10 / globalScale, 3)
      const r = Math.max(14 / globalScale, 4)
      const x = node.x ?? 0
      const y = node.y ?? 0

      ctx.beginPath()
      ctx.arc(x, y, r, 0, 2 * Math.PI)
      ctx.fillStyle = nodeColor(node.type ?? '')
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1.5 / globalScale
      ctx.stroke()

      ctx.font = `${fontSize}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#1e293b'
      ctx.fillText(label.length > 18 ? label.slice(0, 16) + '…' : label, x, y + r + fontSize)
    },
    []
  )

  const handleNodeHover = useCallback(
    (node: { id?: string; description?: string } | null) => {
      if (!tooltipRef.current) return
      if (node?.description) {
        tooltipRef.current.textContent = node.description
        tooltipRef.current.style.display = 'block'
      } else {
        tooltipRef.current.style.display = 'none'
      }
    },
    []
  )

  return (
    <div className="flex flex-col h-full">
      {/* Legend */}
      <div className="flex flex-wrap gap-2 px-3 py-2 border-b border-gray-100 flex-shrink-0">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-xs text-gray-500">{type}</span>
          </div>
        ))}
      </div>

      <div className="relative flex-1 min-h-0">
        <ForceGraph2D
          graphData={fgData}
          nodeCanvasObject={paintNode as Parameters<typeof ForceGraph2D>[0]['nodeCanvasObject']}
          nodeCanvasObjectMode={() => 'replace'}
          linkLabel="label"
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkColor={() => '#cbd5e1'}
          linkWidth={1.5}
          onNodeHover={handleNodeHover as Parameters<typeof ForceGraph2D>[0]['onNodeHover']}
          backgroundColor="#f8fafc"
          cooldownTicks={80}
          width={width}
        />
        <div
          ref={tooltipRef}
          className="absolute bottom-2 left-2 right-2 bg-white border border-gray-200 rounded-md px-2 py-1.5 text-xs text-gray-700 shadow-sm pointer-events-none"
          style={{ display: 'none' }}
        />
      </div>
    </div>
  )
}
