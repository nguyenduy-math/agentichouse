import { useEffect, useRef } from 'react'
import type { Chart as ChartType } from 'chart.js'
import { METRIC_LABELS, METRIC_NAMES } from '../../types/eval'

interface Props {
  averages: Record<string, number | null>
}

function barColor(val: number | null): string {
  if (val === null) return 'rgba(100,116,139,0.5)' // slate
  if (val >= 0.8) return 'rgba(74,222,128,0.7)' // green
  if (val >= 0.6) return 'rgba(250,204,21,0.7)' // amber
  return 'rgba(248,113,113,0.7)' // red
}

export default function MetricBarChart({ averages }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<ChartType | null>(null)

  useEffect(() => {
    if (!canvasRef.current) return

    // Dynamic import to avoid SSR issues
    import('chart.js').then(
      ({ Chart, BarController, CategoryScale, LinearScale, BarElement, Tooltip }) => {
        Chart.register(BarController, CategoryScale, LinearScale, BarElement, Tooltip)

        if (chartRef.current) {
          chartRef.current.destroy()
          chartRef.current = null
        }

        const labels = METRIC_NAMES.map((m) => METRIC_LABELS[m])
        const values = METRIC_NAMES.map((m) => averages[m] ?? 0)
        const colors = METRIC_NAMES.map((m) => barColor(averages[m]))

        chartRef.current = new Chart(canvasRef.current!, {
          type: 'bar',
          data: {
            labels,
            datasets: [
              {
                data: values,
                backgroundColor: colors,
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
                  label: (ctx) => {
                    const raw = ctx.raw as number
                    const m = METRIC_NAMES[ctx.dataIndex]
                    return averages[m] === null ? '–' : raw.toFixed(3)
                  },
                },
              },
            },
            scales: {
              x: {
                min: 0,
                max: 1,
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
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [averages])

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3" style={{ height: 180 }}>
      <canvas ref={canvasRef} />
    </div>
  )
}
