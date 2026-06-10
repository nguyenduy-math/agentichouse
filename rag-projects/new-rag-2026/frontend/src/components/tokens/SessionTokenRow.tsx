import { useState, useEffect, useRef } from 'react'
import { ChevronDown, ChevronUp, Copy, Check } from 'lucide-react'
import type { Chart as ChartType } from 'chart.js'
import type { AdminTokenRow, SessionTokenSummary } from '../../types/token'
import { getSessionTokens } from '../../api/tokenApi'

interface Props {
  row: AdminTokenRow
  index: number
}

function costClass(cost: number): string {
  if (cost < 0.001) return 'text-green-400'
  if (cost <= 0.01) return 'text-amber-400'
  return 'text-red-400'
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs} giây trước`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins} phút trước`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} giờ trước`
  const days = Math.floor(hours / 24)
  return `${days} ngày trước`
}

function CallTypeMiniBar({ data }: { data: SessionTokenSummary['by_call_type'] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<ChartType | null>(null)

  useEffect(() => {
    if (!canvasRef.current || data.length === 0) return

    import('chart.js').then(
      ({ Chart, BarController, CategoryScale, LinearScale, BarElement, Tooltip }) => {
        Chart.register(BarController, CategoryScale, LinearScale, BarElement, Tooltip)

        if (chartRef.current) {
          chartRef.current.destroy()
          chartRef.current = null
        }

        chartRef.current = new Chart(canvasRef.current!, {
          type: 'bar',
          data: {
            labels: data.map((d) => d.call_type),
            datasets: [
              {
                data: data.map((d) => d.total_tokens),
                backgroundColor: 'rgba(96,165,250,0.7)',
                borderRadius: 3,
                borderSkipped: false,
              },
            ],
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  label: (ctx) => ` ${(ctx.raw as number).toLocaleString()} tokens`,
                },
              },
            },
            scales: {
              x: {
                ticks: { color: '#94a3b8', font: { size: 9 } },
                grid: { color: '#1e293b' },
              },
              y: {
                ticks: { color: '#94a3b8', font: { size: 9 } },
                grid: { display: false },
              },
            },
          },
        })
      }
    )

    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [data])

  if (data.length === 0) return <p className="text-slate-500 text-xs">Không có dữ liệu</p>

  return (
    <div style={{ height: Math.max(80, data.length * 28) }}>
      <canvas ref={canvasRef} />
    </div>
  )
}

function DetailPanel({ sessionId }: { sessionId: string }) {
  const [summary, setSummary] = useState<SessionTokenSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getSessionTokens(sessionId)
      .then((res) => setSummary(res.data))
      .catch(() => setError('Không thể tải chi tiết'))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <div className="p-4 text-slate-400 text-sm">Đang tải chi tiết…</div>
    )
  }

  if (error || !summary) {
    return (
      <div className="p-4 text-red-400 text-sm">{error ?? 'Lỗi không xác định'}</div>
    )
  }

  return (
    <div className="p-4 space-y-5 bg-slate-850">
      {/* Call-type breakdown */}
      <div>
        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
          Loại gọi
        </h4>
        <CallTypeMiniBar data={summary.by_call_type} />
      </div>

      {/* Model breakdown table */}
      <div>
        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
          Mô hình
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left py-1 pr-3">Provider</th>
                <th className="text-left py-1 pr-3">Model</th>
                <th className="text-right py-1 pr-3">Prompt</th>
                <th className="text-right py-1 pr-3">Completion</th>
                <th className="text-right py-1 pr-3">Total</th>
                <th className="text-right py-1">Chi phí</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_model.map((m, i) => (
                <tr key={i} className="border-b border-slate-800 hover:bg-slate-800/50">
                  <td className="py-1.5 pr-3 text-slate-300">{m.provider}</td>
                  <td className="py-1.5 pr-3 text-slate-300 font-mono">{m.model}</td>
                  <td className="py-1.5 pr-3 text-right text-slate-400">
                    {m.prompt_tokens.toLocaleString()}
                  </td>
                  <td className="py-1.5 pr-3 text-right text-slate-400">
                    {m.completion_tokens.toLocaleString()}
                  </td>
                  <td className="py-1.5 pr-3 text-right text-slate-200">
                    {m.total_tokens.toLocaleString()}
                  </td>
                  <td className={`py-1.5 text-right ${costClass(m.cost_usd)}`}>
                    ${m.cost_usd.toFixed(6)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Turn breakdown */}
      {summary.turn_breakdown.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            Lượt hội thoại
          </h4>
          <div className="overflow-x-auto max-h-48 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-900">
                <tr className="text-slate-500 border-b border-slate-700">
                  <th className="text-left py-1 pr-3">Lượt</th>
                  <th className="text-right py-1 pr-3">Tokens</th>
                  <th className="text-right py-1 pr-3">Calls</th>
                  <th className="text-right py-1">Chi phí</th>
                </tr>
              </thead>
              <tbody>
                {summary.turn_breakdown.map((t, i) => (
                  <tr key={i} className="border-b border-slate-800 hover:bg-slate-800/50">
                    <td className="py-1.5 pr-3 text-slate-300">
                      {t.turn_number !== null ? `Lượt ${t.turn_number}` : t.turn_id.slice(0, 8) + '…'}
                    </td>
                    <td className="py-1.5 pr-3 text-right text-slate-200">
                      {t.total_tokens.toLocaleString()}
                    </td>
                    <td className="py-1.5 pr-3 text-right text-slate-400">{t.calls}</td>
                    <td className={`py-1.5 text-right ${costClass(t.cost_usd)}`}>
                      ${t.cost_usd.toFixed(6)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export default function SessionTokenRow({ row, index }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  function copyId() {
    navigator.clipboard.writeText(row.session_id).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const isEven = index % 2 === 0

  return (
    <>
      <tr
        className={`border-b border-slate-800 hover:bg-slate-700/40 transition-colors ${
          isEven ? 'bg-slate-900' : 'bg-slate-800/30'
        }`}
      >
        {/* Session ID */}
        <td className="py-2.5 px-3">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs text-slate-300">
              {row.session_id.slice(0, 12)}…
            </span>
            <button
              onClick={copyId}
              className="text-slate-500 hover:text-slate-300 transition-colors"
              title="Sao chép ID"
            >
              {copied ? (
                <Check className="w-3 h-3 text-green-400" />
              ) : (
                <Copy className="w-3 h-3" />
              )}
            </button>
          </div>
        </td>

        {/* Calls */}
        <td className="py-2.5 px-3 text-right text-xs text-slate-400">
          {row.total_calls.toLocaleString()}
        </td>

        {/* Total tokens */}
        <td className="py-2.5 px-3 text-right text-xs text-slate-200">
          {row.total_tokens.toLocaleString()}
        </td>

        {/* Estimated cost */}
        <td className={`py-2.5 px-3 text-right text-xs ${costClass(row.total_cost_usd)}`}>
          ${row.total_cost_usd.toFixed(4)}
        </td>

        {/* Last active */}
        <td className="py-2.5 px-3 text-right text-xs text-slate-500">
          {relativeTime(row.last_call)}
        </td>

        {/* Expand button */}
        <td className="py-2.5 px-3 text-right">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors ml-auto"
          >
            {expanded ? (
              <>
                Ẩn <ChevronUp className="w-3.5 h-3.5" />
              </>
            ) : (
              <>
                Xem chi tiết <ChevronDown className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </td>
      </tr>

      {/* Expandable detail row */}
      {expanded && (
        <tr className={isEven ? 'bg-slate-900' : 'bg-slate-800/30'}>
          <td colSpan={6} className="border-b border-slate-700">
            <DetailPanel sessionId={row.session_id} />
          </td>
        </tr>
      )}
    </>
  )
}
