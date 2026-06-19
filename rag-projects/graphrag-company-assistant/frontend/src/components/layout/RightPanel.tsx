import { useState, useEffect, useRef, useCallback } from 'react'
import { BookOpen, Network, X } from 'lucide-react'
import SourcesPanel from '../sources/SourcesPanel'
import GraphPanel from '../graph/GraphPanel'
import { useChatStore } from '../../store'

type Tab = 'sources' | 'graph'

const MIN_WIDTH = 280
const MAX_WIDTH = 720
const DEFAULT_WIDTH = 380

export default function RightPanel() {
  const activeSources = useChatStore((s) => s.activeSources)
  const activeGraphData = useChatStore((s) => s.activeGraphData)
  const setActiveSources = useChatStore((s) => s.setActiveSources)
  const setActiveGraphData = useChatStore((s) => s.setActiveGraphData)

  const [activeTab, setActiveTab] = useState<Tab>('graph')
  const [panelWidth, setPanelWidth] = useState(DEFAULT_WIDTH)
  const dragState = useRef<{ startX: number; startWidth: number } | null>(null)

  // Auto-switch to graph tab when graph data arrives
  useEffect(() => {
    if (activeGraphData !== null) setActiveTab('graph')
  }, [activeGraphData])

  // Auto-switch to sources tab when sources arrive and there's no graph data
  useEffect(() => {
    if (activeSources.length > 0 && activeGraphData === null) setActiveTab('sources')
  }, [activeSources, activeGraphData])

  // Ensure active tab stays valid if its data disappears
  useEffect(() => {
    if (activeTab === 'graph' && activeGraphData === null && activeSources.length > 0) {
      setActiveTab('sources')
    }
    if (activeTab === 'sources' && activeSources.length === 0 && activeGraphData !== null) {
      setActiveTab('graph')
    }
  }, [activeTab, activeGraphData, activeSources.length])

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragState.current = { startX: e.clientX, startWidth: panelWidth }

    const onMove = (ev: MouseEvent) => {
      if (!dragState.current) return
      const delta = dragState.current.startX - ev.clientX
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, dragState.current.startWidth + delta))
      setPanelWidth(next)
    }

    const onUp = () => {
      dragState.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [panelWidth])

  const closePanel = () => {
    setActiveSources([])
    setActiveGraphData(null)
  }

  const hasGraph = activeGraphData !== null
  const hasSources = activeSources.length > 0

  return (
    <div
      className="relative flex flex-col border-l border-gray-200 bg-white flex-shrink-0 overflow-hidden"
      style={{ width: panelWidth }}
    >
      {/* Drag handle */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-indigo-300 active:bg-indigo-400 transition-colors z-10"
        onMouseDown={handleDragStart}
      />

      {/* Tab bar */}
      <div className="flex items-center border-b border-gray-200 bg-gray-50 flex-shrink-0 pl-2">
        <button
          onClick={() => setActiveTab('graph')}
          disabled={!hasGraph}
          className={[
            'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors',
            activeTab === 'graph' && hasGraph
              ? 'border-indigo-500 text-indigo-600'
              : 'border-transparent',
            hasGraph
              ? 'text-gray-600 hover:text-gray-900'
              : 'text-gray-300 cursor-not-allowed',
          ].join(' ')}
        >
          <Network className="w-3.5 h-3.5" />
          Đồ thị quan hệ
          {hasGraph && (
            <span className="ml-0.5 text-xs bg-indigo-100 text-indigo-600 rounded-full px-1.5 py-0.5 leading-none">
              {activeGraphData!.nodes.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('sources')}
          disabled={!hasSources}
          className={[
            'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors',
            activeTab === 'sources' && hasSources
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent',
            hasSources
              ? 'text-gray-600 hover:text-gray-900'
              : 'text-gray-300 cursor-not-allowed',
          ].join(' ')}
        >
          <BookOpen className="w-3.5 h-3.5" />
          Nguồn tham khảo
          {hasSources && (
            <span className="ml-0.5 text-xs bg-blue-100 text-blue-600 rounded-full px-1.5 py-0.5 leading-none">
              {activeSources.length}
            </span>
          )}
        </button>

        <button
          onClick={closePanel}
          className="ml-auto mr-2 p-1 text-gray-400 hover:text-gray-600 transition-colors"
          title="Đóng"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === 'graph' && hasGraph && (
          <GraphPanel graphData={activeGraphData!} width={panelWidth} />
        )}
        {activeTab === 'sources' && hasSources && (
          <SourcesPanel sources={activeSources} />
        )}
      </div>
    </div>
  )
}
