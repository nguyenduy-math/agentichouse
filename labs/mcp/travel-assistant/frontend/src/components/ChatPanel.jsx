import { useState, useRef, useEffect } from 'react'
import { chatSend } from '../api.js'

const PROVIDERS = [
  { value: 'gemini', label: 'Gemini' },
  { value: 'siliconflow', label: 'SiliconFlow' },
]

const SUGGESTIONS = [
  'Gợi ý 3 điểm du lịch biển ấm áp tháng 12, ngân sách vừa phải',
  'Tôi muốn đi Nhật mùa thu, có lễ gì cần tránh không?',
  'Tìm chuyến bay từ TP.HCM đi Hà Nội ngày mai',
]

// Maps orchestrator agent keys to friendly Vietnamese labels for the route badge.
const AGENT_LABELS = {
  travel: 'Du lịch',
  flights: 'Đặt vé',
}

export default function ChatPanel({ city }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [provider, setProvider] = useState('gemini')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const listRef = useRef(null)

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, loading])

  async function send(text) {
    const content = (text ?? input).trim()
    if (!content || loading) return

    // Seed destination context once, if the user is viewing a city.
    const next = [...messages, { role: 'user', content }]
    if (messages.length === 0 && city) {
      next.unshift({ role: 'user', content: `Bối cảnh: tôi đang xem thành phố ${city}.` })
    }

    setMessages(next)
    setInput('')
    setError(null)
    setLoading(true)
    try {
      const data = await chatSend(next, provider)
      setMessages([...next, {
        role: 'assistant',
        content: data.reply,
        tools: data.tool_calls,
        agents: data.agents,
      }])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <span style={styles.header}>🤖 Trợ lý du lịch AI</span>
        <select
          value={provider}
          onChange={e => setProvider(e.target.value)}
          style={styles.select}
          title="Chọn mô hình AI"
        >
          {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </div>

      <div ref={listRef} style={styles.messages}>
        {messages.length === 0 && (
          <div style={styles.empty}>
            <p style={{ marginBottom: '0.75rem' }}>Hỏi tôi để tìm chuyến du lịch phù hợp 👇</p>
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => send(s)} style={styles.suggestion}>{s}</button>
            ))}
          </div>
        )}

        {messages
          .filter(m => !m.content.startsWith('Bối cảnh:'))
          .map((m, i) => (
            <div
              key={i}
              style={{ ...styles.bubble, ...(m.role === 'user' ? styles.userBubble : styles.botBubble) }}
            >
              <div style={styles.bubbleText}>{m.content}</div>
              {m.agents && m.agents.length > 0 && (
                <div style={styles.agents}>
                  🤝 {[...new Set(m.agents)].map(a => AGENT_LABELS[a] || a).join(' + ')}
                </div>
              )}
              {m.tools && m.tools.length > 0 && (
                <div style={styles.tools}>🛠️ {[...new Set(m.tools)].join(', ')}</div>
              )}
            </div>
          ))}

        {loading && <div style={{ ...styles.bubble, ...styles.botBubble }}>⏳ Đang suy nghĩ…</div>}
      </div>

      {error && <div style={styles.error}>⚠️ {error}</div>}

      <div style={styles.inputRow}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
          rows={2}
          style={styles.textarea}
          disabled={loading}
        />
        <button onClick={() => send()} disabled={loading || !input.trim()} style={styles.button}>
          {loading ? '⏳' : 'Gửi'}
        </button>
      </div>
    </div>
  )
}

const styles = {
  card: {
    background: '#1a1d27',
    border: '1px solid #2a2d3a',
    borderRadius: '14px',
    padding: '1.25rem 1.5rem',
    marginTop: '1.25rem',
  },
  headerRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '1rem',
  },
  header: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: '#7a7f9a',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  select: {
    padding: '0.4rem 0.6rem',
    borderRadius: '8px',
    border: '1px solid #2a2d3a',
    background: '#0f1117',
    color: '#e8eaf0',
    fontSize: '0.9rem',
    cursor: 'pointer',
  },
  messages: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.6rem',
    maxHeight: '420px',
    overflowY: 'auto',
    marginBottom: '0.75rem',
    minHeight: '120px',
  },
  empty: {
    color: '#7a7f9a',
    fontSize: '0.9rem',
    textAlign: 'center',
    padding: '1rem 0',
  },
  suggestion: {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    margin: '0.35rem 0',
    padding: '0.6rem 0.75rem',
    borderRadius: '8px',
    border: '1px solid #2a2d3a',
    background: '#0f1117',
    color: '#b9bdd0',
    fontSize: '0.88rem',
    cursor: 'pointer',
  },
  bubble: {
    maxWidth: '85%',
    padding: '0.65rem 0.9rem',
    borderRadius: '12px',
    fontSize: '0.92rem',
    lineHeight: 1.5,
  },
  userBubble: {
    alignSelf: 'flex-end',
    background: '#4f8ef7',
    color: '#fff',
  },
  botBubble: {
    alignSelf: 'flex-start',
    background: '#0f1117',
    border: '1px solid #2a2d3a',
    color: '#e8eaf0',
  },
  bubbleText: {
    whiteSpace: 'pre-wrap',
  },
  agents: {
    marginTop: '0.4rem',
    fontSize: '0.75rem',
    color: '#4f8ef7',
    fontWeight: 600,
  },
  tools: {
    marginTop: '0.25rem',
    fontSize: '0.75rem',
    color: '#7a7f9a',
  },
  inputRow: {
    display: 'flex',
    gap: '0.5rem',
    alignItems: 'flex-end',
  },
  textarea: {
    flex: 1,
    padding: '0.6rem 0.75rem',
    borderRadius: '8px',
    border: '1px solid #2a2d3a',
    background: '#0f1117',
    color: '#e8eaf0',
    fontSize: '0.95rem',
    resize: 'vertical',
    outline: 'none',
  },
  button: {
    padding: '0.7rem 1.25rem',
    borderRadius: '8px',
    border: 'none',
    background: '#4f8ef7',
    color: '#fff',
    fontSize: '0.95rem',
    fontWeight: 600,
    cursor: 'pointer',
  },
  error: {
    color: '#f87171',
    fontSize: '0.9rem',
    marginBottom: '0.5rem',
  },
}
