import { useEffect, useRef, useState } from 'react'
import { listRuns } from '../api/evalApi'
import type { EvalRunSummary } from '../types/eval'

const POLL_INTERVAL_MS = 3000

/**
 * Fetches eval runs and polls every 3 s while any run is pending or running.
 */
export function useEvalRuns() {
  const [runs, setRuns] = useState<EvalRunSummary[]>([])
  const [loading, setLoading] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchRuns = async () => {
    try {
      const res = await listRuns()
      setRuns(res.data.runs)
    } catch {
      // silently ignore — UI shows stale data
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    fetchRuns()
  }, [])

  // Start/stop polling based on active runs
  useEffect(() => {
    const hasActive = runs.some(
      (r) => r.status === 'pending' || r.status === 'running'
    )

    if (hasActive && !timerRef.current) {
      timerRef.current = setInterval(fetchRuns, POLL_INTERVAL_MS)
    } else if (!hasActive && timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [runs])

  return { runs, loading, refetch: fetchRuns }
}
