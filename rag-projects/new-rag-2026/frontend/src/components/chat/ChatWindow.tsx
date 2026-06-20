import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '../../store'
import MessageBubble from './MessageBubble'
import AgentProgressPanel from './AgentProgressPanel'
import { BrainCircuit } from 'lucide-react'
import { getSessionTokens } from '../../api/tokenApi'
import type { TurnBreakdown } from '../../types/token'

export default function ChatWindow() {
  const messages = useChatStore((s) => s.messages)
  const sessionId = useChatStore((s) => s.sessionId)
  const isLoading = useChatStore((s) => s.isLoading)
  const bottomRef = useRef<HTMLDivElement>(null)
  // Map turn_number (1-based) → TurnBreakdown
  const [turnTokenMap, setTurnTokenMap] = useState<Record<number, TurnBreakdown>>({})

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Refresh token data whenever the session or message count changes
  useEffect(() => {
    if (!sessionId) return
    getSessionTokens(sessionId)
      .then((res) => {
        const map: Record<number, TurnBreakdown> = {}
        for (const t of res.data.turn_breakdown) {
          if (t.turn_number != null) {
            map[t.turn_number] = t
          }
        }
        setTurnTokenMap(map)
      })
      .catch(() => {
        // token data is optional — ignore errors
      })
  }, [sessionId, messages.length])

  // Build per-assistant-message turn index (1-based)
  let assistantIndex = 0

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-center text-slate-500 gap-4 pt-12">
          <BrainCircuit className="w-14 h-14 text-slate-600" />
          <div>
            <p className="text-lg font-semibold text-slate-300">
              Trợ lý Tri thức
            </p>
            <p className="text-sm text-slate-500 mt-1 max-w-xs">
              Hỏi tôi về nhân sự, phúc lợi, bảo mật CNTT, tài chính, tuân thủ
              hoặc quy trình nội bộ.
            </p>
          </div>
        </div>
      )}

      {messages.map((msg) => {
        let turnData: TurnBreakdown | undefined
        if (msg.role === 'assistant') {
          assistantIndex += 1
          turnData = turnTokenMap[assistantIndex]
        }
        return (
          <MessageBubble key={msg.id} message={msg} turnTokenData={turnData} />
        )
      })}

      {isLoading && <AgentProgressPanel />}

      <div ref={bottomRef} />
    </div>
  )
}
