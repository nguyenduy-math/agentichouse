import { useIndexStatus } from '../../hooks/useIndexStatus'

const STAGE_LABELS: Record<string, string> = {
  idle: 'Chờ bắt đầu',
  indexing: 'Đang lập chỉ mục GraphRAG...',
  importing: 'Đang nhập vào Neo4j...',
  ready: 'Hoàn thành',
  error: 'Lỗi',
}

interface Props {
  polling: boolean
}

export default function IndexStatus({ polling }: Props) {
  const status = useIndexStatus(polling)

  if (!status) return null

  const isDone = status.status === 'ready'
  const isError = status.status === 'error'
  const isRunning = status.status === 'indexing' || status.status === 'importing'
  const pct = isDone ? 100 : isRunning ? 50 : 0

  return (
    <div className="mt-4 p-4 bg-slate-800 border border-slate-700 rounded-lg space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-300 font-medium">
          {STAGE_LABELS[status.status] ?? status.status}
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            isDone
              ? 'bg-green-900/60 text-green-300'
              : isError
              ? 'bg-red-900/60 text-red-300'
              : 'bg-blue-900/60 text-blue-300'
          }`}
        >
          {isDone ? 'Xong' : isError ? 'Lỗi' : status.status === 'idle' ? 'Chờ' : 'Đang chạy'}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isError ? 'bg-red-500' : isDone ? 'bg-green-500' : 'bg-blue-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {status.message && (
        <p className={`text-xs p-2 rounded ${isError ? 'text-red-400 bg-red-900/20' : 'text-slate-400'}`}>
          {status.message}
        </p>
      )}

      {isDone && (
        <p className="text-xs text-green-400">
          Lập chỉ mục hoàn tất. Bạn có thể bắt đầu hỏi đáp.
        </p>
      )}
    </div>
  )
}
