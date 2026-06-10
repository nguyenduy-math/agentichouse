import { useEffect, useState } from 'react'
import { getSessionTurns } from '../../api/evalApi'
import { useEvalStore } from '../../store/evalStore'
import type { EvalTurn } from '../../types/eval'

interface Props {
  onRunEval: () => void
}

export default function TurnTable({ onRunEval }: Props) {
  const selectedSessionId = useEvalStore((s) => s.selectedSessionId)
  const selectedTurnIds = useEvalStore((s) => s.selectedTurnIds)
  const toggleTurnId = useEvalStore((s) => s.toggleTurnId)
  const setSelectedTurnIds = useEvalStore((s) => s.setSelectedTurnIds)
  const clearTurnIds = useEvalStore((s) => s.clearTurnIds)

  const [turns, setTurns] = useState<EvalTurn[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!selectedSessionId) {
      setTurns([])
      clearTurnIds()
      return
    }
    setLoading(true)
    getSessionTurns(selectedSessionId)
      .then((res) => setTurns(res.data.turns))
      .catch(() => setTurns([]))
      .finally(() => setLoading(false))
  }, [selectedSessionId])

  if (!selectedSessionId) {
    return (
      <p className="text-xs text-slate-500 italic mt-4">
        Chọn một phiên để xem các lượt hỏi đáp.
      </p>
    )
  }

  const allSelected = turns.length > 0 && turns.every((t) => selectedTurnIds.has(t.turn_id))

  const toggleAll = () => {
    if (allSelected) clearTurnIds()
    else setSelectedTurnIds(turns.map((t) => t.turn_id))
  }

  const fmt = (iso: string) => {
    try {
      return new Date(iso).toLocaleTimeString('vi-VN', {
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
          Lượt hỏi đáp ({turns.length})
        </span>
        <div className="flex items-center gap-2">
          {selectedTurnIds.size > 0 && (
            <span className="text-xs px-2 py-0.5 bg-blue-900/60 text-blue-300 rounded-full">
              Đã chọn {selectedTurnIds.size} lượt
            </span>
          )}
          <button
            disabled={selectedTurnIds.size === 0}
            onClick={onRunEval}
            className="px-3 py-1 text-xs rounded-md font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-500 text-white"
          >
            Chạy đánh giá
          </button>
        </div>
      </div>

      {loading && (
        <p className="text-xs text-slate-500 animate-pulse">Đang tải lượt hỏi đáp...</p>
      )}

      {!loading && turns.length === 0 && (
        <p className="text-xs text-slate-500 italic">Phiên này chưa có lượt hỏi đáp.</p>
      )}

      {turns.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-800 text-slate-400">
                <th className="px-2 py-2 w-8">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="rounded"
                  />
                </th>
                <th className="px-2 py-2 text-left w-8">#</th>
                <th className="px-2 py-2 text-left">Câu hỏi</th>
                <th className="px-2 py-2 text-left">Miền</th>
                <th className="px-2 py-2 text-left w-14">Giờ</th>
              </tr>
            </thead>
            <tbody>
              {turns.map((t) => (
                <tr
                  key={t.turn_id}
                  onClick={() => toggleTurnId(t.turn_id)}
                  className={`border-t border-slate-700 cursor-pointer transition-colors ${
                    selectedTurnIds.has(t.turn_id)
                      ? 'bg-blue-900/30'
                      : 'hover:bg-slate-800'
                  }`}
                >
                  <td className="px-2 py-2 text-center" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedTurnIds.has(t.turn_id)}
                      onChange={() => toggleTurnId(t.turn_id)}
                      className="rounded"
                    />
                  </td>
                  <td className="px-2 py-2 text-slate-500">{t.turn_number}</td>
                  <td className="px-2 py-2 text-slate-200">
                    <span className="line-clamp-1">{t.question.slice(0, 80)}</span>
                    {t.is_fallback && (
                      <span className="ml-1 px-1 py-0.5 bg-orange-900/50 text-orange-400 rounded text-[10px]">
                        fallback
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap gap-1">
                      {t.domain_keys.map((d) => (
                        <span
                          key={d}
                          className="px-1.5 py-0.5 bg-slate-700 text-slate-300 rounded-full text-[10px]"
                        >
                          {d}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-2 py-2 text-slate-500">{fmt(t.timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
