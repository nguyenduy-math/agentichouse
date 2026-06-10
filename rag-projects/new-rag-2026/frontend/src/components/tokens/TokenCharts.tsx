import { useEffect, useRef } from 'react'
import type { Chart as ChartType } from 'chart.js'
import type { AdminTokenRow, CallTypeBreakdown } from '../../types/token'

interface Props {
  rows: AdminTokenRow[]
  callTypeData: CallTypeBreakdown[]
}

const CHART_COLORS = [
  'rgba(96,165,250,0.7)',   // blue
  'rgba(52,211,153,0.7)',   // emerald
  'rgba(251,146,60,0.7)',   // orange
  'rgba(167,139,250,0.7)',  // violet
  'rgba(250,204,21,0.7)',   // yellow
  'rgba(248,113,113,0.7)',  // red
  'rgba(34,211,238,0.7)',   // cyan
  'rgba(163,230,53,0.7)',   // lime
]

export default function TokenCharts({ rows, callTypeData }: Props) {
  const barRef = useRef<HTMLCanvasElement>(null)
  const doughnutRef = useRef<HTMLCanvasElement>(null)
  const barChart = useRef<ChartType | null>(null)
  const doughnutChart = useRef<ChartType | null>(null)

  // Top 10 sessions bar chart
  useEffect(() => {
    if (!barRef.current) return

    import('chart.js').then(
      ({ Chart, BarController, CategoryScale, LinearScale, BarElement, Tooltip }) => {
        Chart.register(BarController, CategoryScale, LinearScale, BarElement, Tooltip)

        if (barChart.current) {
          barChart.current.destroy()
          barChart.current = null
        }

        const top10 = [...rows]
          .sort((a, b) => b.total_tokens - a.total_tokens)
          .slice(0, 10)

        barChart.current = new Chart(barRef.current!, {
          type: 'bar',
          data: {
            labels: top10.map((r) => r.session_id.slice(0, 8) + '…'),
            datasets: [
              {
                label: 'Tokens',
                data: top10.map((r) => r.total_tokens),
                backgroundColor: 'rgba(96,165,250,0.7)',
                borderRadius: 4,
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
                ticks: { color: '#94a3b8', font: { size: 10 } },
                grid: { color: '#1e293b' },
              },
              y: {
                ticks: { color: '#94a3b8', font: { size: 10 } },
                grid: { display: false },
              },
            },
          },
        })
      }
    )

    return () => {
      barChart.current?.destroy()
      barChart.current = null
    }
  }, [rows])

  // Call-type doughnut chart
  useEffect(() => {
    if (!doughnutRef.current) return

    import('chart.js').then(
      ({ Chart, DoughnutController, ArcElement, Tooltip, Legend }) => {
        Chart.register(DoughnutController, ArcElement, Tooltip, Legend)

        if (doughnutChart.current) {
          doughnutChart.current.destroy()
          doughnutChart.current = null
        }

        if (callTypeData.length === 0) return

        doughnutChart.current = new Chart(doughnutRef.current!, {
          type: 'doughnut',
          data: {
            labels: callTypeData.map((c) => c.call_type),
            datasets: [
              {
                data: callTypeData.map((c) => c.total_tokens),
                backgroundColor: CHART_COLORS.slice(0, callTypeData.length),
                borderColor: '#1e293b',
                borderWidth: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'bottom',
                labels: { color: '#94a3b8', font: { size: 10 }, padding: 8 },
              },
              tooltip: {
                callbacks: {
                  label: (ctx) =>
                    ` ${ctx.label}: ${(ctx.raw as number).toLocaleString()} tokens`,
                },
              },
            },
          },
        })
      }
    )

    return () => {
      doughnutChart.current?.destroy()
      doughnutChart.current = null
    }
  }, [callTypeData])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Top sessions bar */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Top 10 phiên theo token
        </h3>
        <div style={{ height: 260 }}>
          <canvas ref={barRef} />
        </div>
      </div>

      {/* Call-type doughnut */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Phân bổ theo loại gọi
        </h3>
        <div style={{ height: 260 }}>
          {callTypeData.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-500 text-sm">
              Chưa có dữ liệu
            </div>
          ) : (
            <canvas ref={doughnutRef} />
          )}
        </div>
      </div>
    </div>
  )
}
