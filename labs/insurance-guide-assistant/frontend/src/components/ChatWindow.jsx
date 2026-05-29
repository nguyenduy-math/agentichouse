import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import ProposalCard from './ProposalCard'
import RecommendationCard from './RecommendationCard'

export default function ChatWindow({ messages, proposal, recommendation, isLoading }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
      {messages.map((msg, i) => (
        <MessageBubble key={i} role={msg.role} content={msg.content} />
      ))}
      {proposal && <ProposalCard proposal={proposal} />}
      {recommendation && <RecommendationCard recommendation={recommendation} />}
      {isLoading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#6b7280', fontSize: 13, marginBottom: 12 }}>
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>B</div>
          <span>Đang soạn câu trả lời...</span>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
