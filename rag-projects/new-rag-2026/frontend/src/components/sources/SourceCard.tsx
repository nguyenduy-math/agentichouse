import { FileText, BarChart3 } from 'lucide-react'
import type { Source } from '../../types/chat'

interface Props {
  source: Source
  index: number
}

export default function SourceCard({ source, index }: Props) {
  const isCommunity = source.type === 'community_report'
  const text = isCommunity ? source.summary : source.text
  const label = isCommunity ? source.title : source.document ?? source.document_id

  return (
    <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3 text-xs space-y-1.5">
      <div className="flex items-start gap-2">
        {isCommunity ? (
          <BarChart3 className="w-3.5 h-3.5 text-purple-400 flex-shrink-0 mt-0.5" />
        ) : (
          <FileText className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400 font-mono">[{index + 1}]</span>
            {label && (
              <span className="text-slate-300 font-medium truncate">{label}</span>
            )}
            <span
              className={`ml-auto flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full ${
                isCommunity
                  ? 'bg-purple-900/60 text-purple-300'
                  : 'bg-blue-900/60 text-blue-300'
              }`}
            >
              {isCommunity ? 'Cộng đồng' : 'Đoạn văn'}
            </span>
          </div>
        </div>
      </div>
      {text && (
        <p className="text-slate-400 leading-relaxed line-clamp-4 pl-5">{text}</p>
      )}
    </div>
  )
}
