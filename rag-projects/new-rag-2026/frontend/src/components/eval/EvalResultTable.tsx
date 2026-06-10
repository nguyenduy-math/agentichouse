import { useEffect, useState } from 'react'
import { exportRun, getRunResult } from '../../api/evalApi'
import { useEvalStore } from '../../store/evalStore'
import { useEvalRuns } from '../../hooks/useEvalRuns'
import type { EvalRunResult, EvalTurnScore } from '../../types/eval'
import { METRIC_NAMES, METRIC_LABELS } from '../../types/eval'
import MetricBarChart from './MetricBarChart'

function scoreColor(val: number | null): string {
  if (val === null) return 'text-slate-500'
  if (val >= 0.8) return 'text-green-400'
  if (val >= 0.6) return 'text-yellow-400'
  return 'text-red-400'
}

function scoreBg(val: number | null): string {
  if (val === null) return ''
  if (val >= 0.8) return 'bg-green-900/20'
  if (val >= 0.6) return 'bg-yellow-900/20'
  return 'bg-red-900/20'
}

function delta(current: number | null, baseline: number | null): string | null {
  if (current == null || baseline == null) return null
  const d = current - baseline
  return `${d >= 0 ? '+' : ''}${d.toFixed(3)}`
}

function deltaColor(current: number | null, baseline: number | null): string {
  if (current == null || baseline == null) return 'text-slate-500'
  const d = current - baseline
  if (Math.abs(d) < 0.01) return 'text-slate-400'
  return d > 0 ? 'text-green-400' : 'text-red-400'
}

function fmt(val: number | null): string {
  return val === null ? '–' : val.toFixed(3)
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function EvalResultTable() {
  const selectedRunId = useEvalStore((s) => s.selectedRunId)
  const compareRunId = useEvalStore((s) => s.compareRunId)
  const setCompareRunId = useEvalStore((s) => s.setCompareRunId)

  const [result, setResult] = useState<EvalRunResult | null>(null)
  const [compareResult, setCompareResult] = useState<EvalRunResult | null>(null)
  const [loading, setLoading] = useState(false)
  const { runs } = useEvalRuns()

  useEffect(() => {
    if (!selectedRunId) {
      setResult(null)
      return
    }
    setLoading(true)
    getRunResult(selectedRunId)
      .then((r) => setResult(r.data))
      .catch(() => setResult(null))
      .finally(() => setLoading(false))
  }, [selectedRunId])

  useEffect(() => {
    if (!compareRunId) {
      setCompareResult(null)
      return
    }
    getRunResult(compareRunId)
      .then((r) => setCompareResult(r.data))
      .catch(() => setCompareResult(null))
  }, [compareRunId])

  if (!selectedRunId) {
    return (
      <p className="text-xs text-slate-500 italic mt-4">
        Chọn một lần đánh giá đã xong để xem kết quả.
      </p>
    )
  }

  if (loading) return <p className="text-xs text-slate-500 animate-pulse mt-4">Đang tải...</p>
  if (!result) return <p className="text-xs text-red-400 mt-4">Không tải được kết quả.</p>

  const compareScoreMap: Record<string, EvalTurnScore> = {}
  if (compareResult) {
    for (const s of compareResult.scores) {
      compareScoreMap[s.turn_id] = s
    }
  }

  const donRuns = runs.filter((r) => r.status === 'done' && r.run_id !== selectedRunId)

  const turnIdsA = new Set(result.scores.map((s) => s.turn_id))
  const turnIdsB = compareResult ? new Set(compareResult.scores.map((s) => s.turn_id)) : null
  const mismatch =
    turnIdsB &&
    (turnIdsA.size !== turnIdsB.size ||
      [...turnIdsA].some((id) => !turnIdsB.has(id)))

  const handleExport = async () => {
    try {
      const res = await exportRun(selectedRunId)
      downloadBlob(res.data, `eval_run_${selectedRunId.slice(0, 8)}.csv`)
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-xs text-slate-400">
          Run <span className="font-mono text-slate-300">{selectedRunId.slice(0, 8)}</span>
          {' · '}{result.judge_provider}/{result.judge_model.split('/').pop()}
          {' · '}{result.turn_count} lượt
        </span>
        <div className="flex items-center gap-2">
          <select
            value={compareRunId ?? ''}
            onChange={(e) => setCompareRunId(e.target.value || null)}
            className="text-xs bg-slate-800 border border-slate-700 rounded-md px-2 py-1 text-slate-300"
          >
            <option value="">So sánh với...</option>
            {donRuns.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id.slice(0, 8)} ({r.judge_provider})
              </option>
            ))}
          </select>
          <button
            onClick={handleExport}
            className="px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md transition-colors"
          >
            Tải CSV
          </button>
        </div>
      </div>

      {mismatch && (
        <p className="text-xs text-yellow-400 bg-yellow-900/20 px-3 py-1.5 rounded-md">
          ⚠️ Các lượt không khớp hoàn toàn giữa hai lần chạy
        </p>
      )}

      {/* Chart */}
      <MetricBarChart averages={result.averages} />

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-800 text-slate-400">
              <th className="px-3 py-2 text-left">Câu hỏi</th>
              <th className="px-2 py-2 text-left">Miền</th>
              {METRIC_NAMES.map((m) => (
                <th key={m} className="px-2 py-2 text-center whitespace-nowrap">
                  {METRIC_LABELS[m]}
                  {compareRunId && <span className="text-slate-600"> / Δ</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.scores.map((s) => {
              const cmp = compareScoreMap[s.turn_id]
              return (
                <tr key={s.turn_id} className="border-t border-slate-700 hover:bg-slate-800/50">
                  <td className="px-3 py-2 text-slate-200 max-w-xs">
                    <span className="line-clamp-2">{s.question}</span>
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap gap-1">
                      {s.domain_keys.map((d) => (
                        <span
                          key={d}
                          className="px-1 py-0.5 bg-slate-700 text-slate-400 rounded-full text-[10px]"
                        >
                          {d}
                        </span>
                      ))}
                    </div>
                  </td>
                  {METRIC_NAMES.map((m) => {
                    const val = s[m]
                    const cmpVal = cmp ? cmp[m] : null
                    const d = delta(val, cmpVal)
                    const dc = deltaColor(val, cmpVal)
                    return (
                      <td
                        key={m}
                        className={`px-2 py-2 text-center font-mono ${scoreBg(val)}`}
                      >
                        <span className={scoreColor(val)}>{fmt(val)}</span>
                        {compareRunId && d && (
                          <span className={`ml-1 text-[10px] ${dc}`}>{d}</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}

            {/* Averages footer */}
            <tr className="border-t-2 border-slate-600 bg-slate-800 font-semibold">
              <td className="px-3 py-2 text-slate-300" colSpan={2}>
                Trung bình
              </td>
              {METRIC_NAMES.map((m) => {
                const val = result.averages[m] ?? null
                const cmpVal = compareResult ? (compareResult.averages[m] ?? null) : null
                const d = delta(val, cmpVal)
                const dc = deltaColor(val, cmpVal)
                return (
                  <td key={m} className={`px-2 py-2 text-center font-mono ${scoreBg(val)}`}>
                    <span className={scoreColor(val)}>{fmt(val)}</span>
                    {compareRunId && d && (
                      <span className={`ml-1 text-[10px] ${dc}`}>{d}</span>
                    )}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
