import { FileText } from 'lucide-react'
import type { PolicySource } from '../../types/chat'

const DOC_TYPE_COLORS: Record<string, string> = {
  handbooks: 'bg-blue-100 text-blue-700',
  hr_policies: 'bg-green-100 text-green-700',
  conduct: 'bg-orange-100 text-orange-700',
  benefits: 'bg-purple-100 text-purple-700',
  procedures: 'bg-gray-100 text-gray-700',
}

interface Props {
  source: PolicySource
}

export default function SourceCard({ source }: Props) {
  const colorClass = DOC_TYPE_COLORS[source.doc_type] ?? 'bg-gray-100 text-gray-700'
  const score = Math.round(source.relevance_score * 100)

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white hover:shadow-sm transition-shadow">
      <div className="flex items-start gap-2">
        <FileText className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colorClass}`}>
              {source.doc_type_label || source.doc_type}
            </span>
            <span className="text-xs text-gray-400">Trang {source.page_number}</span>
            {score > 0 && (
              <span className="text-xs text-gray-400 ml-auto">{score}% phù hợp</span>
            )}
          </div>
          <p className="text-xs font-medium text-gray-700 truncate">{source.source_file}</p>
          <p className="text-xs text-gray-500 mt-1 line-clamp-3">{source.excerpt}</p>
          {source.entities && (
            <p className="text-xs text-blue-500 mt-1 italic truncate">
              Thực thể: {source.entities}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
