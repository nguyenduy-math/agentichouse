import { BrainCircuit, BarChart2, MessageSquare, Settings, DollarSign } from 'lucide-react'
import { useSessionStore, useTabStore } from '../../store'
import clsx from 'clsx'

const PROVIDER_BADGES: Record<string, string> = {
  gemini: 'bg-blue-900/60 text-blue-300 border-blue-700',
  openai: 'bg-green-900/60 text-green-300 border-green-700',
  siliconflow: 'bg-orange-900/60 text-orange-300 border-orange-700',
}

const PROVIDER_LABELS: Record<string, string> = {
  gemini: 'Gemini',
  openai: 'OpenAI',
  siliconflow: 'Siliconflow',
}

export default function Header() {
  const { sessionId, llmProvider } = useSessionStore()
  const { activeTab, setActiveTab } = useTabStore()

  const providerClasses =
    PROVIDER_BADGES[llmProvider.toLowerCase()] ??
    'bg-slate-700 text-slate-300 border-slate-600'
  const providerLabel =
    PROVIDER_LABELS[llmProvider.toLowerCase()] ?? llmProvider

  return (
    <header className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-700 flex-shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-2.5">
        <BrainCircuit className="w-5 h-5 text-blue-400" />
        <span className="text-sm font-semibold text-slate-100">
          Trợ lý Tri thức
        </span>
        <span
          className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${providerClasses}`}
        >
          {providerLabel}
        </span>
      </div>

      {/* Tab switcher */}
      <div className="flex items-center gap-1 bg-slate-800 p-0.5 rounded-lg">
        <button
          onClick={() => setActiveTab('chat')}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            activeTab === 'chat'
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-400 hover:text-slate-200'
          )}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          Hỏi đáp
        </button>
        <button
          onClick={() => setActiveTab('admin')}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            activeTab === 'admin'
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-400 hover:text-slate-200'
          )}
        >
          <Settings className="w-3.5 h-3.5" />
          Quản trị
        </button>
        <button
          onClick={() => setActiveTab('eval')}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            activeTab === 'eval'
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-400 hover:text-slate-200'
          )}
        >
          <BarChart2 className="w-3.5 h-3.5" />
          Đánh giá
        </button>
        <button
          onClick={() => setActiveTab('tokens')}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            activeTab === 'tokens'
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-400 hover:text-slate-200'
          )}
        >
          <DollarSign className="w-3.5 h-3.5" />
          Chi phí
        </button>
      </div>

      {/* Session indicator */}
      <div className="text-xs text-slate-600 font-mono hidden sm:block">
        {sessionId ? `${sessionId.slice(0, 8)}…` : 'Đang kết nối...'}
      </div>
    </header>
  )
}
