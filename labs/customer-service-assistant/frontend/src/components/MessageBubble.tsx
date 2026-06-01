import { Message } from '../types'

const AGENT_LABELS: Record<string, string> = {
  faq_agent: '📚 FAQ Agent',
  order_agent: '📦 Order Agent',
  complaint_agent: '🛡️ Complaint Agent',
}

interface Props {
  message: Message
}

export default function MessageBubble({ message }: Props) {
  const isBot = message.role === 'assistant'
  const time = message.timestamp.toLocaleTimeString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`message-row ${isBot ? 'bot' : 'user'}`}>
      {isBot && <div className="avatar bot-avatar">🤖</div>}
      <div className={`message-bubble ${isBot ? 'bot' : 'user'}`}>
        <p>{message.content}</p>
        {isBot && message.agentUsed && AGENT_LABELS[message.agentUsed] && (
          <span className="agent-tag">{AGENT_LABELS[message.agentUsed]}</span>
        )}
        <span className="timestamp">{time}</span>
      </div>
      {!isBot && <div className="avatar user-avatar">👤</div>}
    </div>
  )
}
