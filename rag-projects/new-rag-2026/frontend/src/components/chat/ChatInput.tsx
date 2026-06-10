import { useState, useRef } from 'react'
import { Send } from 'lucide-react'
import { useChat } from '../../hooks/useChat'
import { useChatStore } from '../../store'

const SUGGESTIONS = [
  'Chính sách nghỉ phép năm của công ty là gì?',
  'Quy trình xin hoàn chi phí công tác?',
  'Chính sách bảo mật mật khẩu và xác thực?',
  'Nhân viên được hưởng phúc lợi bảo hiểm y tế như thế nào?',
]

export default function ChatInput() {
  const [value, setValue] = useState('')
  const { send } = useChat()
  const isLoading = useChatStore((s) => s.isLoading)
  const messages = useChatStore((s) => s.messages)
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

  const handleSuggestion = (q: string) => {
    setValue(q)
    textareaRef.current?.focus()
  }

  return (
    <div className="border-t border-slate-700 bg-slate-900 px-4 py-3">
      {/* Suggestions — only when chat is empty */}
      {messages.length === 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3 max-w-3xl mx-auto">
          {SUGGESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => handleSuggestion(q)}
              className="text-xs text-left px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2 max-w-3xl mx-auto">
        <textarea
          ref={textareaRef}
          className="flex-1 resize-none bg-slate-800 border border-slate-600 rounded-xl px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent min-h-[40px] max-h-[120px]"
          placeholder="Tìm kiếm... (Enter để gửi, Shift+Enter xuống dòng)"
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          rows={1}
        />
        <button
          onClick={handleSubmit}
          disabled={!value.trim() || isLoading}
          className="flex-shrink-0 w-10 h-10 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-xl flex items-center justify-center transition-colors"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
      <p className="text-center text-xs text-slate-600 mt-2">
        Multi-Agent GraphRAG · Neo4j · Vietnamese
      </p>
    </div>
  )
}
