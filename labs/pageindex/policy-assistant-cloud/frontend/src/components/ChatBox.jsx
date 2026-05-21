import { useEffect, useRef, useState } from 'react'
import { sendChat, uploadFile } from '../api.js'
import Message from './Message.jsx'
import DocList from './DocList.jsx'

export default function ChatBox({ refreshKey, onDocsChanged }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [uploadStatus, setUploadStatus] = useState(null)
  const scrollRef = useRef(null)
  const fileRef = useRef(null)

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
    const history = messages.map((m) => ({ role: m.role, content: m.content }))
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)

    try {
      const data = await sendChat(text, history)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer,
          citations: data.citations,
          documents: data.documents_consulted,
        },
      ])
    } catch (err) {
      setError(err.message || 'Đã xảy ra lỗi khi gọi máy chủ.')
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploadStatus(`Đang tải lên & xây cây tri thức cho «${file.name}»…`)
    try {
      const result = await uploadFile(file)
      setUploadStatus(`Đã nạp «${result.filename}» (${result.node_count} node).`)
      onDocsChanged?.()
    } catch (err) {
      setUploadStatus(`Lỗi tải lên: ${err.message}`)
    }
    event.target.value = ''
  }

  return (
    <div className="chatbox">
      {/* Thanh tải lên + danh sách tài liệu */}
      <div className="chatbox__upload-bar">
        <button
          className="chatbox__upload-btn"
          onClick={() => fileRef.current?.click()}
          title="Tải lên tài liệu PDF"
        >
          Tải lên PDF
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          style={{ display: 'none' }}
          onChange={handleUpload}
        />
        {uploadStatus && (
          <span className="chatbox__upload-status">{uploadStatus}</span>
        )}
      </div>

      <DocList refreshKey={refreshKey} onDocsChanged={onDocsChanged} />

      {/* Tin nhắn */}
      <div className="chatbox__messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chatbox__empty">
            Hỏi bất kỳ điều gì về các tài liệu chính sách đã nạp — lương thưởng, phúc lợi,
            bảo hiểm, quy trình và nhiều hơn nữa.
          </div>
        )}
        {messages.map((m, i) => (
          <Message
            key={i}
            role={m.role}
            content={m.content}
            citations={m.citations}
            documents={m.documents}
          />
        ))}
        {loading && (
          <div className="message message--assistant message--loading">
            Đang tra cứu tài liệu…
          </div>
        )}
      </div>

      {error && <div className="chatbox__error">{error}</div>}

      <form className="chatbox__form" onSubmit={handleSubmit}>
        <input
          className="chatbox__input"
          type="text"
          placeholder="Hỏi về chính sách của công ty…"
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
