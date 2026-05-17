import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import clsx from 'clsx'
import type { Message } from '../../types/chat'
import { useChatStore } from '../../store'
import type { GraphData } from '../../types/chat'

const QUERY_TYPE_LABELS: Record<string, string> = {
  LOCAL: 'Tìm kiếm cụ thể',
  GLOBAL: 'Tổng quan',
}

const QUERY_TYPE_COLORS: Record<string, string> = {
  LOCAL: 'bg-green-100 text-green-700',
  GLOBAL: 'bg-purple-100 text-purple-700',
}

interface Props {
  message: Message
}

export default function MessageBubble({ message }: Props) {
  const setActiveSources = useChatStore((s) => s.setActiveSources)
  const setActiveGraphData = useChatStore((s) => s.setActiveGraphData)
  const isUser = message.role === 'user'

  return (
    <div className={clsx('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'max-w-[80%] rounded-2xl px-4 py-3 text-sm shadow-sm',
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-white text-gray-800 border border-gray-200 rounded-bl-sm'
        )}
      >
        {!isUser && message.query_type && (
          <span
            className={clsx(
              'inline-block text-xs px-2 py-0.5 rounded-full font-medium mb-2',
              QUERY_TYPE_COLORS[message.query_type] ?? 'bg-gray-100 text-gray-600'
            )}
          >
            {QUERY_TYPE_LABELS[message.query_type] ?? message.query_type}
          </span>
        )}
        <div className={clsx('prose prose-sm max-w-none', isUser && 'prose-invert')}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
        {!isUser && (message.sources.length > 0 || message.graph_data?.nodes.length) && (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.sources.length > 0 && (
              <button
                className="text-xs text-blue-500 hover:text-blue-700 underline"
                onClick={() => setActiveSources(message.sources)}
              >
                Xem {message.sources.length} nguồn tham khảo →
              </button>
            )}
            {message.graph_data && message.graph_data.nodes.length > 0 && (
              <button
                className="text-xs text-indigo-500 hover:text-indigo-700 underline"
                onClick={() => setActiveGraphData(message.graph_data as GraphData)}
              >
                Xem đồ thị quan hệ ({message.graph_data.nodes.length} thực thể) →
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
