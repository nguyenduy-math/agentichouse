import { useEffect } from 'react'
import axios from 'axios'
import { v4 as uuidv4 } from 'uuid'
import { createSession } from '../api/sessionApi'
import { useSessionStore } from '../store'
import type { HealthResponse } from '../types/session'

export function useSession() {
  const { sessionId, setSessionId, setLlmProvider } = useSessionStore()

  useEffect(() => {
    if (sessionId) return

    // Fetch health to get provider info
    axios
      .get<HealthResponse>('/health')
      .catch(() => null)

    // Fetch provider from env (backend may expose it — ignore error)
    axios
      .get<{ llm_provider?: string }>('/api/v1/config')
      .then((r) => {
        if (r.data.llm_provider) setLlmProvider(r.data.llm_provider)
      })
      .catch(() => {})

    createSession()
      .then((s) => setSessionId(s.session_id))
      .catch(() => setSessionId(uuidv4()))
  }, [sessionId, setSessionId, setLlmProvider])
}
