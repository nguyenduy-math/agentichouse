import { useEffect, useRef } from 'react'

const STAGE_LABELS: Record<string, string> = {
  idle: 'Chờ bắt đầu',
  indexing: 'Đang lập chỉ mục GraphRAG...',
  importing: 'Đang nhập vào Neo4j...',
  ready: 'Hoàn thành',
  error: 'Lỗi',
}

interface Props {
  status: string
  isStreaming: boolean
  pct: number
  lines: string[]
}

export default function IndexStatus({ status, isStreaming, pct, lines }: Props) {
  const logRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom whenever new lines arrive
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [lines])

  const isDone = status === 'ready'
  const isError = status === 'error'
  const isRunning = isStreaming || status === 'indexing' || status === 'importing'

  return (
    <div className="mt-4 p-4 bg-slate-800 border border-slate-700 rounded-lg space-y-3">
      {/* Stage label + badge + percentage */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-300 font-medium">
          {STAGE_LABELS[status] ?? status}
        </span>
        <div className="flex items-center gap-2">
          {isRunning && (
            <span className="text-xs font-mono text-blue-300">{pct}%</span>
          )}
          {isDone && (
            <span className="text-xs font-mono text-green-300">100%</span>
          )}
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              isDone
                ? 'bg-green-900/60 text-green-300'
                : isError
                ? 'bg-red-900/60 text-red-300'
                : isRunning
                ? 'bg-blue-900/60 text-blue-300'
                : 'bg-slate-700 text-slate-400'
            }`}
          >
            {isDone ? 'Xong' : isError ? 'Lỗi' : isRunning ? 'Đang chạy' : 'Chờ'}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            isError ? 'bg-red-500' : isDone ? 'bg-green-500' : 'bg-blue-500'
          }`}
          style={{ width: `${isDone ? 100 : pct}%` }}
        />
      </div>

      {/* Live log console */}
      {lines.length > 0 && (
        <div
          ref={logRef}
          className="h-48 overflow-y-auto bg-slate-900 rounded p-2 text-xs font-mono space-y-0.5 scroll-smooth"
        >
          {lines.map((line, i) => (
            <div
              key={i}
              className={
                /error|ERROR|failed|FAILED/i.test(line)
                  ? 'text-red-400'
                  : /warning|WARN/i.test(line)
                  ? 'text-yellow-400'
                  : /done|complete|success/i.test(line)
                  ? 'text-green-400'
                  : 'text-slate-400'
              }
            >
              {line}
            </div>
          ))}
          {isRunning && (
            <div className="text-blue-400 animate-pulse">▋</div>
          )}
        </div>
      )}

      {isDone && (
        <p className="text-xs text-green-400">
          Lập chỉ mục hoàn tất. Bạn có thể bắt đầu hỏi đáp.
        </p>
      )}
    </div>
  )
}
