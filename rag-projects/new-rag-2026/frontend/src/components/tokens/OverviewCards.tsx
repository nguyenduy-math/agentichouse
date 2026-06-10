import type { AdminTokenRow } from '../../types/token'

interface Props {
  rows: AdminTokenRow[]
}

interface CardProps {
  label: string
  value: string
  sub?: string
}

function MetricCard({ label, value, sub }: CardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex flex-col gap-1">
      <span className="text-xs text-slate-400 uppercase tracking-wide">{label}</span>
      <span className="text-2xl font-bold text-slate-100">{value}</span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  )
}

export default function OverviewCards({ rows }: Props) {
  const totalTokens = rows.reduce((s, r) => s + r.total_tokens, 0)
  const totalCost = rows.reduce((s, r) => s + r.total_cost_usd, 0)
  const sessionCount = rows.length
  const avgTokens = sessionCount > 0 ? Math.round(totalTokens / sessionCount) : 0

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <MetricCard
        label="Tổng token"
        value={totalTokens.toLocaleString()}
        sub="tất cả phiên"
      />
      <MetricCard
        label="Chi phí ước tính"
        value={`$${totalCost.toFixed(4)}`}
        sub="USD"
      />
      <MetricCard
        label="Phiên làm việc"
        value={sessionCount.toLocaleString()}
        sub="có dữ liệu token"
      />
      <MetricCard
        label="Trung bình / phiên"
        value={avgTokens.toLocaleString()}
        sub="tokens"
      />
    </div>
  )
}
