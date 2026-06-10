import { useEffect, useState } from 'react'
import { getSessionTokens } from '../../api/tokenApi'
import type { SessionTokenSummary } from '../../types/token'

interface Props {
  sessionId: string
}

export default function TokenSummaryPanel({ sessionId }: Props) {
  const [data, setData] = useState<SessionTokenSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    getSessionTokens(sessionId)
      .then((res) => setData(res.data))
      .catch(() => setError('Không thể tải dữ liệu token.'))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <div className="text-xs text-slate-500 animate-pulse px-1 py-2">
        Đang tải token…
      </div>
    )
  }

  if (error) {
    return <div className="text-xs text-red-400 px-1 py-2">{error}</div>
  }

  if (!data || data.total_tokens === 0) {
    return (
      <div className="text-xs text-slate-500 italic px-1 py-2">
        Chưa có dữ liệu token cho phiên này.
      </div>
    )
  }

  const maxTokens = Math.max(...data.by_call_type.map((r) => r.total_tokens), 1)

  return (
    <div className="flex flex-col gap-3 text-xs text-slate-300">
      {/* Header totals */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex flex-col">
          <span className="text-slate-500 text-[10px] uppercase tracking-wide">Tổng token</span>
          <span className="font-semibold text-slate-100 tabular-nums">
            {data.total_tokens.toLocaleString()}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-slate-500 text-[10px] uppercase tracking-wide">Chi phí ước tính</span>
          <span className="font-semibold text-green-400 tabular-nums">
            ${data.total_cost_usd.toFixed(5)}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-slate-500 text-[10px] uppercase tracking-wide">Số lần gọi</span>
          <span className="font-semibold tabular-nums">{data.total_calls}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-slate-500 text-[10px] uppercase tracking-wide">Prompt / Completion</span>
          <span className="tabular-nums">
            {data.total_prompt_tokens.toLocaleString()} /{' '}
            {data.total_completion_tokens.toLocaleString()}
          </span>
        </div>
      </div>

      {/* By call type — horizontal bar chart */}
      {data.by_call_type.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
            Theo bước xử lý
          </div>
          <div className="flex flex-col gap-1">
            {data.by_call_type.map((row) => (
              <div key={row.call_type} className="flex items-center gap-2">
                <span className="w-36 shrink-0 text-slate-400 truncate font-mono text-[10px]">
                  {row.call_type}
                </span>
                <div className="flex-1 bg-slate-700 rounded-full h-2 overflow-hidden">
                  <div
                    className="h-2 bg-indigo-500 rounded-full"
                    style={{ width: `${(row.total_tokens / maxTokens) * 100}%` }}
                  />
                </div>
                <span className="w-16 text-right tabular-nums text-slate-400">
                  {row.total_tokens.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* By model */}
      {data.by_model.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
            Theo model
          </div>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-500 uppercase">
                <th className="text-left py-0.5 pr-2">Model</th>
                <th className="text-right py-0.5 pr-2">Prompt</th>
                <th className="text-right py-0.5 pr-2">Completion</th>
                <th className="text-right py-0.5">Chi phí</th>
              </tr>
            </thead>
            <tbody>
              {data.by_model.map((row) => (
                <tr key={`${row.provider}/${row.model}`} className="border-t border-slate-700/50">
                  <td className="py-0.5 pr-2 font-mono text-[10px] text-slate-300">
                    {row.model}
                  </td>
                  <td className="text-right py-0.5 pr-2 tabular-nums text-slate-400">
                    {row.prompt_tokens.toLocaleString()}
                  </td>
                  <td className="text-right py-0.5 pr-2 tabular-nums text-slate-400">
                    {row.completion_tokens.toLocaleString()}
                  </td>
                  <td className="text-right py-0.5 tabular-nums text-green-400">
                    ${row.cost_usd.toFixed(5)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Per-turn breakdown */}
      {data.turn_breakdown.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
            Theo lượt hỏi
          </div>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-500 uppercase">
                <th className="text-left py-0.5 pr-2">Lượt</th>
                <th className="text-right py-0.5 pr-2">Token</th>
                <th className="text-right py-0.5 pr-2">Gọi</th>
                <th className="text-right py-0.5">Chi phí</th>
              </tr>
            </thead>
            <tbody>
              {data.turn_breakdown.map((row) => (
                <tr key={row.turn_id} className="border-t border-slate-700/50">
                  <td className="py-0.5 pr-2 tabular-nums text-slate-300">
                    #{row.turn_number ?? '?'}
                  </td>
                  <td className="text-right py-0.5 pr-2 tabular-nums text-slate-400">
                    {row.total_tokens.toLocaleString()}
                  </td>
                  <td className="text-right py-0.5 pr-2 tabular-nums text-slate-400">
                    {row.calls}
                  </td>
                  <td className="text-right py-0.5 tabular-nums text-green-400">
                    ${row.cost_usd.toFixed(5)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
