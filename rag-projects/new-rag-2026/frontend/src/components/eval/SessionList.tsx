import { useEffect, useState } from 'react'
import { listSessions } from '../../api/evalApi'
import { getAdminTokenSummary } from '../../api/tokenApi'
import { useEvalStore } from '../../store/evalStore'
import type { SessionSummary } from '../../types/eval'
import type { AdminTokenRow } from '../../types/token'

const PAGE_SIZE = 20

export default function SessionList() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [tokenMap, setTokenMap] = useState<Record<string, AdminTokenRow>>({})

  const selectedSessionId = useEvalStore((s) => s.selectedSessionId)
  const setSelectedSessionId = useEvalStore((s) => s.setSelectedSessionId)

  const fetchSessions = async (off = 0) => {
    setLoading(true)
    try {
      const res = await listSessions(PAGE_SIZE, off)
      if (off === 0) {
        setSessions(res.data.sessions)
      } else {
        setSessions((prev) => [...prev, ...res.data.sessions])
      }
      setTotal(res.data.total)
      setOffset(off + PAGE_SIZE)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  const fetchTokenSummary = async () => {
    try {
      const res = await getAdminTokenSummary()
      const map: Record<string, AdminTokenRow> = {}
      for (const row of res.data) {
        map[row.session_id] = row
      }
      setTokenMap(map)
    } catch {
      // ignore — token data is optional
    }
  }

  useEffect(() => {
    fetchSessions(0)
    fetchTokenSummary()
    const interval = setInterval(() => {
      fetchSessions(0)
      fetchTokenSummary()
    }, 30_000)
    return () => clearInterval(interval)
  }, [])

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
          Phiên ({total})
        </span>
        {loading && (
          <span className="text-xs text-slate-500 animate-pulse">Đang tải...</span>
        )}
      </div>

      {sessions.length === 0 && !loading && (
        <p className="text-xs text-slate-500 italic">Chưa có phiên nào. Hãy thử hỏi đáp trước.</p>
      )}

      {sessions.map((s) => (
        <button
          key={s.session_id}
          onClick={() => setSelectedSessionId(s.session_id)}
          className={`w-full text-left px-3 py-2 rounded-md text-xs transition-colors ${
            selectedSessionId === s.session_id
              ? 'bg-blue-900/60 border border-blue-700 text-blue-100'
              : 'bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono truncate">{s.session_id.slice(0, 12)}…</span>
            <div className="flex items-center gap-1 shrink-0">
              {tokenMap[s.session_id] && (
                <span className="px-1.5 py-0.5 bg-indigo-900/60 border border-indigo-700 rounded-full text-indigo-300 text-[10px] tabular-nums">
                  {(tokenMap[s.session_id].total_tokens / 1000).toFixed(1)}k tok
                </span>
              )}
              <span className="px-1.5 py-0.5 bg-slate-700 rounded-full text-slate-300">
                {s.turn_count} lượt
              </span>
            </div>
          </div>
          <div className="flex items-center justify-between mt-0.5">
            <span className="text-slate-500">{fmt(s.last_active)}</span>
            {tokenMap[s.session_id] && (
              <span className="text-[10px] text-slate-500 tabular-nums">
                ${tokenMap[s.session_id].total_cost_usd.toFixed(5)}
              </span>
            )}
          </div>
        </button>
      ))}

      {sessions.length < total && (
        <button
          onClick={() => fetchSessions(offset)}
          disabled={loading}
          className="mt-1 w-full py-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 rounded-md transition-colors"
        >
          Xem thêm
        </button>
      )}
    </div>
  )
}
