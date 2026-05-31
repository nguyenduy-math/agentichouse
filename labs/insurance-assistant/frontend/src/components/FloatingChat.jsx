import { useRef, useState, useEffect } from 'react'
import { newSession, sendMessage, uploadPdf, applyFields } from '../api'

const ACCENT = '#3b82f6'

function MessageBubble({ role, content }) {
  const isUser = role === 'user'
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', marginBottom: 8 }}>
      {!isUser && (
        <div style={{ width: 28, height: 28, borderRadius: '50%', background: ACCENT, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, marginRight: 6, flexShrink: 0 }}>B</div>
      )}
      <div style={{
        maxWidth: '78%', padding: '8px 12px', borderRadius: isUser ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
        background: isUser ? ACCENT : '#f3f4f6',
        color: isUser ? '#fff' : '#111827',
        fontSize: 13, lineHeight: 1.5,
        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      }}>
        {content}
      </div>
    </div>
  )
}

function ConfirmationCard({ summaryText, extractedFields, onConfirm, onDismiss }) {
  return (
    <div style={{
      margin: '8px 0', padding: '12px 14px',
      background: '#f0f9ff', border: '1px solid #bae6fd',
      borderRadius: 12, fontSize: 13,
    }}>
      <div style={{ whiteSpace: 'pre-wrap', marginBottom: 10, color: '#0c4a6e' }}>{summaryText}</div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={onConfirm}
          style={{
            flex: 1, padding: '7px 0', background: '#16a34a', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 12,
          }}
        >
          Xác nhận điền form
        </button>
        <button
          onClick={onDismiss}
          style={{
            flex: 1, padding: '7px 0', background: '#e5e7eb', color: '#374151',
            border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 12,
          }}
        >
          Bỏ qua
        </button>
      </div>
    </div>
  )
}

export default function FloatingChat({ onFieldsCollected }) {
  const [open, setOpen] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [options, setOptions] = useState(null)
  const [pendingPdf, setPendingPdf] = useState(null) // { summaryText, extractedFields }
  const [isPdfLoading, setIsPdfLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading, pendingPdf])

  async function initSession() {
    if (sessionId) return
    try {
      const data = await newSession('claim_filing')
      setSessionId(data.session_id)
      setMessages([{ role: 'model', content: 'Xin chào! Tôi sẽ hỗ trợ bạn điền form khai thác bảo hiểm. Bạn muốn khai thác BHYT ngoại trú, nội trú hay bảo hiểm thương mại?' }])
      setOptions(['BHYT ngoại trú', 'BHYT nội trú', 'Bảo hiểm thương mại'])
    } catch {
      setMessages([{ role: 'model', content: 'Không thể kết nối. Vui lòng thử lại.' }])
    }
  }

  function handleOpen() {
    setOpen(true)
    initSession()
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  async function handleSend(text) {
    const msg = (text ?? input).trim()
    if (!msg || isLoading || !sessionId) return
    setInput('')
    setOptions(null)
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setIsLoading(true)
    try {
      const data = await sendMessage(sessionId, msg)
      setMessages(prev => [...prev, { role: 'model', content: data.reply }])
      setOptions(data.options ?? null)
      if (data.collected) {
        onFieldsCollected?.(data.collected)
      }
    } catch {
      setMessages(prev => [...prev, { role: 'model', content: 'Đã xảy ra lỗi. Vui lòng thử lại.' }])
    } finally {
      setIsLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  async function handlePdfSelect(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !sessionId) return

    setIsPdfLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: `📎 ${file.name}` }])

    try {
      const data = await uploadPdf(sessionId, file)
      setPendingPdf({ summaryText: data.summary_text, extractedFields: data.extracted_fields })
    } catch (err) {
      setMessages(prev => [...prev, { role: 'model', content: `Không thể đọc file PDF: ${err.message}` }])
    } finally {
      setIsPdfLoading(false)
    }
  }

  async function handlePdfConfirm() {
    const fields = pendingPdf?.extractedFields
    setPendingPdf(null)
    if (!fields || !sessionId) return

    // Fill the visible form immediately
    onFieldsCollected?.(fields)

    // Persist the fields into the backend session so the agent verifies them
    // and continues asking only for the remaining fields.
    setIsLoading(true)
    setOptions(null)
    try {
      const data = await applyFields(sessionId, fields)
      setMessages(prev => [...prev, { role: 'model', content: data.reply }])
      setOptions(data.options ?? null)
      if (data.collected) onFieldsCollected?.(data.collected)
    } catch {
      setMessages(prev => [...prev, { role: 'model', content: 'Đã điền thông tin từ tài liệu vào form. Bạn có thể tiếp tục nhập các thông tin còn lại.' }])
    } finally {
      setIsLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  function handlePdfDismiss() {
    setPendingPdf(null)
    setMessages(prev => [...prev, { role: 'model', content: 'Đã bỏ qua. Bạn có thể tiếp tục nhập thông tin.' }])
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <>
      {/* Chat panel */}
      {open && (
        <div style={{
          position: 'fixed', bottom: 80, right: 24,
          width: 350, height: 500,
          background: '#fff', borderRadius: 16,
          boxShadow: '0 8px 40px rgba(0,0,0,0.18)',
          display: 'flex', flexDirection: 'column',
          zIndex: 1000, overflow: 'hidden',
          border: '1px solid #e5e7eb',
        }}>
          {/* Header */}
          <div style={{ background: ACCENT, color: '#fff', padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14 }}>Trợ lý điền form</div>
              <div style={{ fontSize: 11, opacity: 0.85 }}>Chat để tự động điền thông tin</div>
            </div>
            <button onClick={() => setOpen(false)} style={{ background: 'rgba(255,255,255,0.2)', border: 'none', color: '#fff', width: 28, height: 28, borderRadius: '50%', cursor: 'pointer', fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>×</button>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
            {messages.map((msg, i) => <MessageBubble key={i} role={msg.role} content={msg.content} />)}
            {(isLoading || isPdfLoading) && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#6b7280', fontSize: 12 }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', background: ACCENT, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>B</div>
                <span>{isPdfLoading ? 'Đang đọc PDF...' : 'Đang soạn...'}</span>
              </div>
            )}
            {pendingPdf && !isPdfLoading && (
              <ConfirmationCard
                summaryText={pendingPdf.summaryText}
                extractedFields={pendingPdf.extractedFields}
                onConfirm={handlePdfConfirm}
                onDismiss={handlePdfDismiss}
              />
            )}
            <div ref={bottomRef} />
          </div>

          {/* Option chips */}
          {options && !isLoading && (
            <div style={{ padding: '4px 14px 8px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {options.map(opt => (
                <button
                  key={opt}
                  onClick={() => handleSend(opt)}
                  style={{ padding: '5px 12px', borderRadius: 20, border: `1px solid ${ACCENT}`, background: '#eff6ff', color: '#1d4ed8', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{ padding: '8px 12px', borderTop: '1px solid #e5e7eb', display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              style={{ display: 'none' }}
              onChange={handlePdfSelect}
            />
            {/* Paperclip button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading || isPdfLoading || !sessionId}
              title="Tải lên file PDF"
              style={{
                padding: '7px 9px', background: 'transparent', border: '1px solid #d1d5db',
                borderRadius: 8, cursor: 'pointer', fontSize: 15, color: '#6b7280',
                opacity: (isLoading || isPdfLoading || !sessionId) ? 0.4 : 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              📎
            </button>
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              placeholder="Nhập thông tin..."
              style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
            />
            <button
              onClick={() => handleSend()}
              disabled={isLoading || !input.trim()}
              style={{
                padding: '8px 14px', background: ACCENT, color: '#fff', border: 'none',
                borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 13,
                opacity: (isLoading || !input.trim()) ? 0.5 : 1,
              }}
            >
              Gửi
            </button>
          </div>
        </div>
      )}

      {/* Floating button */}
      <button
        onClick={open ? () => setOpen(false) : handleOpen}
        title="Chat với trợ lý"
        style={{
          position: 'fixed', bottom: 24, right: 24,
          width: 52, height: 52, borderRadius: '50%',
          background: ACCENT, color: '#fff', border: 'none',
          boxShadow: '0 4px 16px rgba(59,130,246,0.5)',
          cursor: 'pointer', fontSize: 22,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1001, transition: 'transform .15s',
        }}
      >
        {open ? '×' : '💬'}
      </button>
    </>
  )
}
