import { useEvalRuns } from '../../hooks/useEvalRuns'
import { useEvalStore } from '../../store/evalStore'
import type { EvalRunSummary } from '../../types/eval'

function StatusBadge({ status }: { status: EvalRunSummary['status'] }) {
  const cfg = {
    pending: 'bg-yellow-900/60 text-yellow-300',
    running: 'bg-blue-900/60 text-blue-300',
    done: 'bg-green-900/60 text-green-300',
    failed: 'bg-red-900/60 text-red-300',
  }[status]

  const labels = {
    pending: 'Chờ',
    running: 'Đang chạy',
    done: 'Xong',
    failed: 'Lỗi',
  }

  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg}`}>
      {status === 'running' && (
        <span className="inline-block w-1.5 h-1.5 mr-1 rounded-full bg-blue-400 animate-pulse" />
      )}
      {labels[status]}
    </span>
  )
}

export default function RunList() {
  const { runs, loading } = useEvalRuns()
  const selectedRunId = useEvalStore((s) => s.selectedRunId)
  const setSelectedRunId = useEvalStore((s) => s.setSelectedRunId)

  const fmt = (iso: string) => {
    try {
      return new Date(iso).toLocaleString('vi-VN', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
          Lần chạy gần đây
        </span>
        {loading && (
          <span className="text-xs text-slate-500 animate-pulse">...</span>
        )}
      </div>

      {runs.length === 0 && !loading && (
        <p className="text-xs text-slate-500 italic">Chưa có lần đánh giá nào.</p>
      )}

      {runs.map((r) => (
        <button
          key={r.run_id}
          onClick={() => r.status === 'done' && setSelectedRunId(r.run_id)}
          className={`w-full text-left px-3 py-2 rounded-md text-xs border transition-colors ${
            r.status !== 'done' ? 'cursor-default opacity-70' : ''
          } ${
            selectedRunId === r.run_id
              ? 'bg-blue-900/60 border-blue-700 text-blue-100'
              : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono">{r.run_id.slice(0, 8)}</span>
            <StatusBadge status={r.status} />
          </div>
          <div className="flex items-center justify-between text-slate-500 mt-0.5">
            <span>
              {r.turn_count} lượt · {r.judge_provider}/{r.judge_model.split('/').pop()}
            </span>
            <span>{fmt(r.created_at)}</span>
          </div>
          {r.status === 'failed' && r.error && (
            <p className="text-red-400 text-[10px] mt-0.5 truncate">{r.error}</p>
          )}
        </button>
      ))}
    </div>
  )
}
