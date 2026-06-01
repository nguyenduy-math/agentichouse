import { useEffect, useRef } from 'react'
import { Message } from '../types'
import MessageBubble from './MessageBubble'

interface Props {
  messages: Message[]
  isLoading: boolean
}

export default function ChatWindow({ messages, isLoading }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="chat-window">
      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isLoading && (
        <div className="message-row bot">
          <div className="avatar bot-avatar">🤖</div>
          <div className="message-bubble bot typing">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
