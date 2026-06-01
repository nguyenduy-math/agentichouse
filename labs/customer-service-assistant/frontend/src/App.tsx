import { useState, useCallback } from 'react'
import { Message, ActivityItem, ChatResponse } from './types'
import ChatWindow from './components/ChatWindow'
import ActivitySidebar from './components/ActivitySidebar'
import InputBar from './components/InputBar'

const CUSTOMER_ID = 'CUST-001'

const WELCOME: Message = {
  id: '0',
  role: 'assistant',
  content:
    'Xin chào! Tôi là trợ lý hỗ trợ khách hàng. Tôi có thể giúp bạn về thông tin sản phẩm, tra cứu đơn hàng, hoặc xử lý khiếu nại. Bạn cần hỗ trợ gì?',
  timestamp: new Date(),
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([WELCOME])
  const [activities, setActivities] = useState<ActivityItem[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const sendMessage = useCallback(async (content: string) => {
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, userMsg])
    setIsLoading(true)
    setActivities([])

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, customer_id: CUSTOMER_ID }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: ChatResponse = await res.json()

      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.reply,
        timestamp: new Date(),
        agentUsed: data.agent_used,
      }
      setMessages(prev => [...prev, botMsg])
      setActivities(data.activities)
    } catch {
      const errMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Xin lỗi, hệ thống gặp sự cố. Vui lòng thử lại sau.',
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setIsLoading(false)
    }
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <span className="header-icon">🤖</span>
          <span className="header-title">Trợ lý Hỗ trợ Khách hàng</span>
        </div>
        <span className="header-subtitle">Powered by Gemini &amp; SiliconFlow · MCP</span>
      </header>
      <div className="app-body">
        <div className="chat-panel">
          <ChatWindow messages={messages} isLoading={isLoading} />
          <InputBar onSend={sendMessage} disabled={isLoading} />
        </div>
        <ActivitySidebar activities={activities} isLoading={isLoading} />
      </div>
    </div>
  )
}
