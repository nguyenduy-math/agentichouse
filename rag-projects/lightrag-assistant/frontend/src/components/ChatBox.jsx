import { useEffect, useRef, useState } from 'react'
import { sendChat } from '../api.js'
import Message from './Message.jsx'

// LightRAG query modes — exposed so the user can experiment.
const MODES = ['naive', 'local', 'global', 'hybrid', 'mix']

// The chatbox owns the conversation: `messages` is the source of truth, and the
// prior history is sent with every request (the backend is stateless).
export default function ChatBox() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [mode, setMode] = useState('hybrid')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  async function handleSubmit(event) {
    event.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    setError(null)
    setInput('')
    // History as the backend expects it — before this turn is appended.
    const history = messages.map((m) => ({ role: m.role, content: m.content }))
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)

    try {
      const data = await sendChat(text, history, mode)
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }])
    } catch (err) {
      setError(err.message || 'Đã xảy ra lỗi khi gọi máy chủ.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chatbox">
      <div className="chatbox__messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chatbox__empty">
            Hãy đặt câu hỏi về tài liệu bảo hiểm đã được nạp vào hệ thống.
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} role={m.role} content={m.content} />
        ))}
        {loading && (
          <div className="message message--assistant message--loading">Đang trả lời…</div>
        )}
      </div>

      {error && <div className="chatbox__error">{error}</div>}

      <form className="chatbox__form" onSubmit={handleSubmit}>
        <select
          className="chatbox__mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          title="Chế độ truy vấn LightRAG"
        >
          {MODES.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <input
          className="chatbox__input"
          type="text"
          placeholder="Nhập câu hỏi của bạn…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button
          className="chatbox__send"
          type="submit"
          disabled={loading || !input.trim()}
        >
          Gửi
        </button>
      </form>
    </div>
  )
}
