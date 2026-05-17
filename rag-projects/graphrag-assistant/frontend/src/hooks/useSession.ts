import { useEffect } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { createSession } from '../api/sessionApi'
import { useSessionStore } from '../store'

export function useSession() {
  const { sessionId, setSessionId } = useSessionStore()

  useEffect(() => {
    if (sessionId) return
    createSession()
      .then((s) => setSessionId(s.session_id))
      .catch(() => setSessionId(uuidv4()))
  }, [sessionId, setSessionId])
}
