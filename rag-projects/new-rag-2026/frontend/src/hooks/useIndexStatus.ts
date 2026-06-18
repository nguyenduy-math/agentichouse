import { useEffect, useRef, useState } from 'react'
import { getIndexStatus } from '../api/adminApi'
import type { IndexStatus } from '../api/adminApi'

export function useIndexStatus(enabled: boolean) {
  const [status, setStatus] = useState<IndexStatus | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!enabled) {
      if (timerRef.current) clearInterval(timerRef.current)
      return
    }

    const poll = async () => {
      try {
        const s = await getIndexStatus()
        setStatus(s)
        // Stop polling when indexing is complete or errored
        if (s.status === 'ready' || s.status === 'error') {
          if (timerRef.current) clearInterval(timerRef.current)
        }
      } catch {
        // ignore transient errors
      }
    }

    poll()
    timerRef.current = setInterval(poll, 2000)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [enabled])

  return status
}
