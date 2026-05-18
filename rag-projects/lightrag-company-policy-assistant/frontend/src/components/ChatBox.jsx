import { useEffect, useRef, useState } from 'react'
import { sendChat, uploadFiles } from '../api.js'
import Message from './Message.jsx'

const DOC_TYPES = [
  { value: 'hr_policies',  label: 'Nội quy lao động' },
  { value: 'benefits',     label: 'Phúc lợi & đãi ngộ' },
  { value: 'conduct',      label: 'Quy tắc ứng xử' },
  { value: 'procedures',   label: 'Quy trình & thủ tục' },
  { value: 'handbooks',    label: 'Sổ tay nhân viên' },
  { value: 'medical',      label: 'Chính sách y tế' },
  { value: 'it_security',  label: 'CNTT & Bảo mật' },
  { value: 'compliance',   label: 'Tuân thủ & Pháp lý' },
  { value: 'finance',      label: 'Chính sách tài chính' },
  { value: 'training',     label: 'Đào tạo & Phát triển' },
]

export default function ChatBox() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [docType, setDocType] = useState('hr_policies')
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
          domains: data.domains_consulted,
          citations: data.citations,
          entities: data.entities,
        },
      ])
    } catch (err) {
      setError(err.message || 'Đã xảy ra lỗi khi gọi máy chủ.')
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(event) {
    const files = event.target.files
    if (!files || files.length === 0) return
    setUploadStatus('Đang tải lên…')
    try {
      const result = await uploadFiles(files, docType)
      setUploadStatus(`Đã nạp ${result.count} tài liệu vào lĩnh vực "${docType}".`)
    } catch (err) {
      setUploadStatus(`Lỗi tải lên: ${err.message}`)
    }
    event.target.value = ''
  }

  return (
    <div className="chatbox">
      {/* Upload bar */}
      <div className="chatbox__upload-bar">
        <select
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
          className="chatbox__doc-type"
          title="Lĩnh vực tài liệu"
        >
          {DOC_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <button
          className="chatbox__upload-btn"
          onClick={() => fileRef.current?.click()}
          title="Tải lên tài liệu chính sách"
        >
          Tải lên tài liệu
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          multiple
          style={{ display: 'none' }}
          onChange={handleUpload}
        />
        {uploadStatus && (
          <span className="chatbox__upload-status">{uploadStatus}</span>
        )}
      </div>

      {/* Messages */}
      <div className="chatbox__messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chatbox__empty">
            Hỏi bất kỳ điều gì về chính sách của công ty — nội quy lao động, phúc lợi,
            quy tắc ứng xử, y tế, CNTT, tài chính, đào tạo và nhiều hơn nữa.
          </div>
        )}
        {messages.map((m, i) => (
          <Message
            key={i}
            role={m.role}
            content={m.content}
            domains={m.domains}
            citations={m.citations}
          />
        ))}
        {loading && (
          <div className="message message--assistant message--loading">
            Đang tham vấn các chuyên gia tư vấn…
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
