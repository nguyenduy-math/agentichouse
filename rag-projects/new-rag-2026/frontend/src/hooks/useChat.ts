import { v4 as uuidv4 } from 'uuid'
import { sendMessage, getAgentTrace } from '../api/chatApi'
import { useChatStore, useSessionStore } from '../store'
import type { ChatMessage, ChatResponse } from '../types/chat'

function buildAssistantMsg(response: ChatResponse): ChatMessage {
  return {
    id: uuidv4(),
    role: 'assistant',
    content: response.reply,
    timestamp: new Date().toISOString(),
    sources: response.sources,
    domain_keys: response.domain_keys,
    query_type: response.query_type,
    agent_count: response.agent_count,
  }
}

export function useChat() {
  const {
    addMessage,
    setLoading,
    setActiveSources,
    setAgentTrace,
    setTraceOpen,
  } = useChatStore()
  const { sessionId } = useSessionStore()

  const send = async (text: string) => {
    if (!sessionId || !text.trim()) return

    const userMsg: ChatMessage = {
      id: uuidv4(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
      sources: [],
    }
    addMessage(userMsg)
    setLoading(true)

    try {
      const response = await sendMessage({
        session_id: sessionId,
        message: text,
        mode: 'auto',
      })
      addMessage(buildAssistantMsg(response))
      setActiveSources(response.sources)

      // If multi-domain, fetch agent trace automatically
      if (response.domain_keys && response.domain_keys.length > 1) {
        try {
          const trace = await getAgentTrace(sessionId)
          setAgentTrace(trace)
          setTraceOpen(true)
        } catch {
          // trace is optional — don't fail
        }
      }
    } catch {
      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content:
          'Xin lỗi, đã có lỗi xảy ra khi kết nối với máy chủ. Vui lòng thử lại.',
        timestamp: new Date().toISOString(),
        sources: [],
      })
    } finally {
      setLoading(false)
    }
  }

  const fetchTrace = async () => {
    if (!sessionId) return
    try {
      const trace = await getAgentTrace(sessionId)
      setAgentTrace(trace)
      setTraceOpen(true)
    } catch {
      // ignore
    }
  }

  return { send, fetchTrace }
}
