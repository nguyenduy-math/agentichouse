import { useState, useEffect, useCallback } from 'react'
import { RefreshCw } from 'lucide-react'
import type { AdminTokenRow, CallTypeBreakdown } from '../../types/token'
import { getAdminTokenSummary } from '../../api/tokenApi'
import OverviewCards from './OverviewCards'
import SessionTokenRow from './SessionTokenRow'
import TokenCharts from './TokenCharts'

const POLL_INTERVAL_MS = 60_000

// Aggregate call-type data across all session summaries is not available from
// admin summary endpoint alone — we derive a synthetic list from all rows for
// the doughnut chart by using total_tokens per session as a single "session"
// call type. When individual session detail is needed, SessionTokenRow fetches
// it on demand. For the doughnut we show top sessions as segments instead.
function deriveCallTypeData(rows: AdminTokenRow[]): CallTypeBreakdown[] {
  // Group by provider (best proxy we have from admin summary)
  // Since AdminTokenRow doesn't include by_call_type, we use a top-N sessions
  // breakdown as the doughnut segments (labelled by truncated session ID).
  return rows
    .sort((a, b) => b.total_tokens - a.total_tokens)
    .slice(0, 8)
    .map((r) => ({
      call_type: r.session_id.slice(0, 8) + '…',
      total_tokens: r.total_tokens,
      cost_usd: r.total_cost_usd,
      calls: r.total_calls,
    }))
}

export default function TokenReportPage() {
  const [rows, setRows] = useState<AdminTokenRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [search, setSearch] = useState('')

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const res = await getAdminTokenSummary(200)
      setRows(res.data)
      setLastUpdated(new Date())
    } catch {
      setError('Không thể tải dữ liệu token')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Poll every 60s
  useEffect(() => {
    const id = setInterval(fetchData, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [fetchData])

  const filtered = rows.filter((r) =>
    r.session_id.toLowerCase().includes(search.toLowerCase())
  )

  const callTypeData = deriveCallTypeData(rows)

  return (
    <div className="flex-1 overflow-y-auto bg-slate-900 p-5 space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Chi phí token</h1>
          {lastUpdated && (
            <p className="text-xs text-slate-500 mt-0.5">
              Cập nhật: {lastUpdated.toLocaleTimeString('vi-VN')} · tự động làm mới sau 60s
            </p>
          )}
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 border border-slate-700 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Làm mới
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {loading && rows.length === 0 ? (
        <div className="flex items-center justify-center py-20 text-slate-500 text-sm">
          Đang tải…
        </div>
      ) : (
        <>
          {/* Section 1 — Overview cards */}
          <OverviewCards rows={rows} />

          {/* Section 2 — Sessions table */}
          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
              <h2 className="text-sm font-semibold text-slate-200">
                Phiên làm việc
                <span className="ml-2 text-xs font-normal text-slate-500">
                  ({filtered.length} / {rows.length})
                </span>
              </h2>
              <input
                type="text"
                placeholder="Tìm session ID…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="text-xs bg-slate-900 border border-slate-600 text-slate-300 placeholder-slate-600 rounded-md px-2.5 py-1.5 focus:outline-none focus:border-blue-500 w-44"
              />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-700 bg-slate-800/80">
                    <th className="text-left py-2.5 px-3 font-medium">Session ID</th>
                    <th className="text-right py-2.5 px-3 font-medium">Calls</th>
                    <th className="text-right py-2.5 px-3 font-medium">Tổng token</th>
                    <th className="text-right py-2.5 px-3 font-medium">Chi phí ước tính</th>
                    <th className="text-right py-2.5 px-3 font-medium">Hoạt động cuối</th>
                    <th className="text-right py-2.5 px-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center py-10 text-slate-500">
                        Không có dữ liệu
                      </td>
                    </tr>
                  ) : (
                    filtered.map((row, i) => (
                      <SessionTokenRow key={row.session_id} row={row} index={i} />
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 3 — Charts */}
          {rows.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-slate-200 mb-3">Biểu đồ</h2>
              <TokenCharts rows={rows} callTypeData={callTypeData} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
