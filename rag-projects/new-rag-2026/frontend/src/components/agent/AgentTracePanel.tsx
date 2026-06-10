import { useState } from 'react'
import { ChevronDown, ChevronRight, X, Activity } from 'lucide-react'
import { useChatStore } from '../../store'
import DomainBadge, { DOMAIN_CONFIG } from './DomainBadge'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface DomainRowProps {
  domainKey: string
  domainNameVi: string
  answer: string
  sourcesCount: number
}

function DomainRow({ domainKey, domainNameVi, answer, sourcesCount }: DomainRowProps) {
  const [open, setOpen] = useState(false)
  const config = DOMAIN_CONFIG[domainKey]
  const borderColor = config?.classes.match(/border-(\S+)/)?.[1] ?? 'border-slate-600'

  return (
    <div className={`border-l-2 ${borderColor} pl-3 mb-3`}>
      <button
        className="w-full flex items-center gap-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        )}
        <DomainBadge domainKey={domainKey} />
        <span className="text-xs text-slate-400 ml-auto flex-shrink-0">
          {sourcesCount} nguồn
        </span>
      </button>
      {open && (
        <div className="mt-2 text-xs text-slate-300 leading-relaxed prose prose-sm prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
          <p className="text-slate-500 mt-1 not-prose">
            Chuyên gia: {domainNameVi}
          </p>
        </div>
      )}
    </div>
  )
}

export default function AgentTracePanel() {
  const { agentTrace, traceOpen, setTraceOpen } = useChatStore()

  if (!traceOpen || !agentTrace) return null

  return (
    <div className="w-72 flex-shrink-0 bg-slate-800/80 border-l border-slate-700 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-700">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
          <Activity className="w-4 h-4 text-indigo-400" />
          Nhân vật tham gia
        </div>
        <button
          onClick={() => setTraceOpen(false)}
          className="text-slate-500 hover:text-slate-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Meta */}
      <div className="px-3 py-2 border-b border-slate-700/50 text-xs text-slate-500">
        <p className="truncate" title={agentTrace.last_question}>
          Câu hỏi: {agentTrace.last_question}
        </p>
        <p className="mt-0.5">
          Chế độ:{' '}
          <span className="text-slate-400">
            {agentTrace.search_mode === 'global' ? 'Toàn cục' : 'Cục bộ'}
          </span>
        </p>
      </div>

      {/* Agent results */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {agentTrace.agent_results.map((r) => (
          <DomainRow
            key={r.domain_key}
            domainKey={r.domain_key}
            domainNameVi={r.domain_name_vi}
            answer={r.answer}
            sourcesCount={r.sources_count}
          />
        ))}
      </div>
    </div>
  )
}
