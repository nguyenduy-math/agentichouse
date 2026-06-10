import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import clsx from 'clsx'
import { useState } from 'react'
import type { ChatMessage } from '../../types/chat'
import type { TurnBreakdown } from '../../types/token'
import { useChatStore } from '../../store'
import DomainBadge from '../agent/DomainBadge'

const QUERY_TYPE_LABELS: Record<string, string> = {
  local: 'Tìm kiếm cụ thể',
  global: 'Toàn cục',
  LOCAL: 'Tìm kiếm cụ thể',
  GLOBAL: 'Toàn cục',
}

const QUERY_TYPE_COLORS: Record<string, string> = {
  local: 'bg-green-900/60 text-green-300 border border-green-700',
  global: 'bg-purple-900/60 text-purple-300 border border-purple-700',
  LOCAL: 'bg-green-900/60 text-green-300 border border-green-700',
  GLOBAL: 'bg-purple-900/60 text-purple-300 border border-purple-700',
}

interface Props {
  message: ChatMessage
  turnTokenData?: TurnBreakdown
}

export default function MessageBubble({ message, turnTokenData }: Props) {
  const { setActiveSources, setTraceOpen } = useChatStore()
  const isUser = message.role === 'user'
  const [tokenExpanded, setTokenExpanded] = useState(false)

  return (
    <div className={clsx('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'max-w-[82%] rounded-2xl px-4 py-3 text-sm shadow-sm',
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-slate-800 text-slate-100 border border-slate-700 rounded-bl-sm'
        )}
      >
        {/* Assistant meta badges */}
        {!isUser && (
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            {/* Query type badge */}
            {message.query_type && (
              <span
                className={clsx(
                  'inline-block text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                  QUERY_TYPE_COLORS[message.query_type] ??
                    'bg-slate-700 text-slate-300 border border-slate-600'
                )}
              >
                {QUERY_TYPE_LABELS[message.query_type] ?? message.query_type}
              </span>
            )}
            {/* Domain badges */}
            {message.domain_keys?.map((key) => (
              <DomainBadge key={key} domainKey={key} />
            ))}
          </div>
        )}

        {/* Content */}
        <div
          className={clsx(
            'prose prose-sm max-w-none',
            isUser
              ? 'prose-invert'
              : 'prose-invert prose-p:text-slate-200 prose-strong:text-slate-100'
          )}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>

        {/* Action links */}
        {!isUser && (
          <div className="mt-2 flex flex-wrap gap-3">
            {message.sources.length > 0 && (
              <button
                className="text-xs text-blue-400 hover:text-blue-300 underline transition-colors"
                onClick={() => setActiveSources(message.sources)}
              >
                Xem {message.sources.length} nguồn →
              </button>
            )}
            {(message.domain_keys?.length ?? 0) > 1 && (
              <button
                className="text-xs text-indigo-400 hover:text-indigo-300 underline transition-colors"
                onClick={() => setTraceOpen(true)}
              >
                Chi tiết {message.agent_count} nhân vật →
              </button>
            )}
          </div>
        )}

        {/* Token counter chip — only for assistant messages with token data */}
        {!isUser && turnTokenData && (
          <div className="mt-2">
            <button
              className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-400 transition-colors"
              onClick={() => setTokenExpanded((v) => !v)}
            >
              <span className="tabular-nums">
                🔢 {turnTokenData.total_tokens.toLocaleString()} tokens
              </span>
              <span className="text-slate-600">
                · ${turnTokenData.cost_usd.toFixed(5)}
              </span>
              <span className="ml-0.5">{tokenExpanded ? '▲' : '▼'}</span>
            </button>
            {tokenExpanded && (
              <div className="mt-1 pl-1 flex flex-col gap-0.5 text-[10px] text-slate-500 border-l border-slate-700">
                <div>
                  <span className="text-slate-400">Gọi LLM:</span>{' '}
                  <span className="tabular-nums">{turnTokenData.calls} lần</span>
                </div>
                <div>
                  <span className="text-slate-400">Chi phí ước tính:</span>{' '}
                  <span className="tabular-nums text-green-500">
                    ${turnTokenData.cost_usd.toFixed(5)}
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
