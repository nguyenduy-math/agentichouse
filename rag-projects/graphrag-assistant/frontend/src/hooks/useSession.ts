import axios from 'axios'
import { useEffect } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { createSession } from '../api/sessionApi'
import { useChatStore, useSessionStore } from '../store'

export function useSession() {
  const { sessionId, setSessionId } = useSessionStore()
  const { setMaxRetries } = useChatStore()

  useEffect(() => {
    if (sessionId) return
    axios
      .get<{ status: string; max_chat_retries?: number }>('/health')
      .then((res) => setMaxRetries(res.data.max_chat_retries ?? 3))
      .catch(() => {})
    createSession()
      .then((s) => setSessionId(s.session_id))
      .catch(() => setSessionId(uuidv4()))
  }, [sessionId, setSessionId, setMaxRetries])
}
