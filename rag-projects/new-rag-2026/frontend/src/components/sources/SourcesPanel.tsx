import { BookOpen, X } from 'lucide-react'
import { useChatStore } from '../../store'
import SourceCard from './SourceCard'

export default function SourcesPanel() {
  const { activeSources, setActiveSources } = useChatStore()

  if (activeSources.length === 0) return null

  return (
    <div className="w-72 flex-shrink-0 bg-slate-800/80 border-l border-slate-700 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-700">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
          <BookOpen className="w-4 h-4 text-blue-400" />
          Nguồn tham khảo
          <span className="text-xs text-slate-500">({activeSources.length})</span>
        </div>
        <button
          onClick={() => setActiveSources([])}
          className="text-slate-500 hover:text-slate-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Source list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {activeSources.map((source, i) => (
          <SourceCard key={source.id ?? i} source={source} index={i} />
        ))}
      </div>
    </div>
  )
}
