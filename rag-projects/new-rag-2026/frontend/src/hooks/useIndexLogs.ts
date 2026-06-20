import { useCallback, useEffect, useRef, useState } from 'react'
import { getIndexStatus, openIndexLogStream, triggerIndex } from '../api/adminApi'

export interface IndexLogsState {
  lines: string[]
  status: string
  isStreaming: boolean
  pct: number
  startIndexing: (reimport?: boolean, domain?: string) => Promise<void>
}

/**
 * Manages the SSE log stream for the indexing pipeline.
 *
 * On mount it checks the backend status so that users who navigate away
 * mid-index and return will automatically reconnect to the live stream.
 * `startIndexing` triggers a new pipeline run and connects from offset 0.
 */
export function useIndexLogs(): IndexLogsState {
  const [lines, setLines] = useState<string[]>([])
  const [status, setStatus] = useState<string>('idle')
  const [isStreaming, setIsStreaming] = useState(false)
  const [pct, setPct] = useState(0)
  const closeRef = useRef<(() => void) | null>(null)

  const connect = useCallback((offset: number) => {
    closeRef.current?.()
    setIsStreaming(true)

    const close = openIndexLogStream(
      offset,
      (line) => setLines((prev) => [...prev, line]),
      (p) => setPct(p),
      (finalStatus) => {
        setStatus(finalStatus)
        setIsStreaming(false)
        if (finalStatus === 'ready') setPct(100)
      },
    )
    closeRef.current = close
  }, [])

  // Auto-resume: if the pipeline is already running when this component
  // mounts (e.g. user navigated away and came back), reconnect immediately.
  useEffect(() => {
    let cancelled = false

    getIndexStatus()
      .then((s) => {
        if (cancelled) return
        setStatus(s.status)
        if (s.status === 'indexing' || s.status === 'importing') {
          connect(0)
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      closeRef.current?.()
    }
  }, [connect])

  const startIndexing = useCallback(
    async (reimport = false, domain = 'general') => {
      setLines([])
      setPct(0)
      setStatus('indexing')
      await triggerIndex(reimport, domain)
      connect(0)
    },
    [connect],
  )

  return { lines, status, isStreaming, pct, startIndexing }
}
