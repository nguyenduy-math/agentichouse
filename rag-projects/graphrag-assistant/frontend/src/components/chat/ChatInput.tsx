import { useState, useRef } from 'react'
import { Send } from 'lucide-react'
import { useChat } from '../../hooks/useChat'
import { useChatStore } from '../../store'

export default function ChatInput() {
  const [value, setValue] = useState('')
  const { send } = useChat()
  const isLoading = useChatStore((s) => s.isLoading)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = async () => {
    const trimmed = value.trim()
    if (!trimmed || isLoading) return
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    await send(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="flex items-end gap-2 max-w-4xl mx-auto">
        <textarea
          id="chat-input"
          ref={textareaRef}
          className="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent min-h-[40px] max-h-[120px]"
          placeholder="Hỏi về trang phục, nghỉ phép, phúc lợi... (Enter để gửi)"
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          rows={1}
        />
        <button
          onClick={handleSubmit}
          disabled={!value.trim() || isLoading}
          className="flex-shrink-0 w-10 h-10 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white rounded-xl flex items-center justify-center transition-colors"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
      <p className="text-center text-xs text-gray-400 mt-1">
        Powered by Gemini 2.5 Flash + Neo4j GraphRAG
      </p>
    </div>
  )
}
