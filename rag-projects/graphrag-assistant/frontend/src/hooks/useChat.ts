import { v4 as uuidv4 } from 'uuid'
import { sendMessage } from '../api/chatApi'
import { useChatStore, useSessionStore } from '../store'
import type { Message } from '../types/chat'

export function useChat() {
  const { addMessage, setLoading, setActiveSources, setActiveGraphData } = useChatStore()
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

    try {
      const response = await sendMessage({ session_id: sessionId, message: text })
      const assistantMsg: Message = {
        id: uuidv4(),
        role: 'assistant',
        content: response.reply,
        timestamp: new Date().toISOString(),
        sources: response.sources,
        query_type: response.query_type,
        graph_data: response.graph_data,
      }
      addMessage(assistantMsg)
      setActiveSources(response.sources)
      setActiveGraphData(response.graph_data ?? null)
    } catch {
      const errMsg: Message = {
        id: uuidv4(),
        role: 'assistant',
        content: 'Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại hoặc liên hệ Phòng Nhân sự.',
        timestamp: new Date().toISOString(),
        sources: [],
      }
      addMessage(errMsg)
    } finally {
      setLoading(false)
    }
  }

  return { send }
}
