import { v4 as uuidv4 } from 'uuid'
import { sendMessage } from '../api/chatApi'
import { useChatStore, useSessionStore } from '../store'
import type { ChatResponse, Message } from '../types/chat'

function buildAssistantMsg(response: ChatResponse): Message {
  return {
    id: uuidv4(),
    role: 'assistant',
    content: response.reply,
    timestamp: new Date().toISOString(),
    sources: response.sources,
    query_type: response.query_type,
    graph_data: response.graph_data,
  }
}

export function useChat() {
  const { addMessage, setLoading, setActiveSources, setActiveGraphData, maxRetries } = useChatStore()
  const { sessionId } = useSessionStore()

  const send = async (text: string) => {
    if (!sessionId || !text.trim()) return

    const userMsg: Message = {
      id: uuidv4(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
      sources: [],
    }
    addMessage(userMsg)
    setLoading(true)

    let lastResponse: ChatResponse | null = null

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await sendMessage({ session_id: sessionId, message: text })
        if (!response.is_fallback) {
          addMessage(buildAssistantMsg(response))
          setActiveSources(response.sources)
          setActiveGraphData(response.graph_data ?? null)
          setLoading(false)
          return
        }
        lastResponse = response
      } catch {
        if (attempt === maxRetries) break
      }
    }

    // All attempts exhausted — show last fallback or generic error
    if (lastResponse) {
      addMessage(buildAssistantMsg(lastResponse))
      setActiveSources(lastResponse.sources)
      setActiveGraphData(lastResponse.graph_data ?? null)
    } else {
      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content: 'Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại hoặc liên hệ Phòng Nhân sự.',
        timestamp: new Date().toISOString(),
        sources: [],
      })
    }
    setLoading(false)
  }

  return { send }
}
