import { useRef, useState } from 'react'
import { newSession, sendMessage } from './api'
import ChatWindow from './components/ChatWindow'
import ModeSelector from './components/ModeSelector'
import OptionChips from './components/OptionChips'
import ProgressBar from './components/ProgressBar'

const MODE_META = {
  claim_filing:   { label: 'Khai thác bảo hiểm',   color: '#3b82f6' },
  recommendation: { label: 'Tư vấn gói bảo hiểm',  color: '#16a34a' },
}

export default function App() {
  const [mode, setMode] = useState(null)          // null = show ModeSelector
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [options, setOptions] = useState(null)
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [isComplete, setIsComplete] = useState(false)
  const [proposal, setProposal] = useState(null)
  const [recommendation, setRecommendation] = useState(null)
  const inputRef = useRef(null)

  async function handleSelectMode(selectedMode) {
    try {
      const data = await newSession(selectedMode)
      setMode(selectedMode)
      setSessionId(data.session_id)
      const welcome = selectedMode === 'recommendation'
        ? 'Xin chào! Tôi sẽ giúp bạn tìm gói bảo hiểm phù hợp nhất dựa trên hồ sơ sức khỏe của bạn. Trước tiên, bạn bao nhiêu tuổi?'
        : 'Xin chào! Tôi sẽ hỗ trợ bạn khai thác quyền lợi bảo hiểm. Bạn muốn khai thác BHYT hay bảo hiểm thương mại?'
      const initialOptions = selectedMode === 'recommendation'
        ? null
        : ['BHYT ngoại trú', 'BHYT nội trú', 'Bảo hiểm thương mại']
      setMessages([{ role: 'model', content: welcome }])
      setOptions(initialOptions)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleSend(text) {
    const msg = (text ?? input).trim()
    if (!msg || isLoading || isComplete) return
    setInput('')
    setOptions(null)
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setIsLoading(true)
    try {
      const data = await sendMessage(sessionId, msg)
      setMessages(prev => [...prev, { role: 'model', content: data.reply }])
      setProgress(data.progress_pct)
      setIsComplete(data.is_complete)
      setOptions(data.options ?? null)
      if (data.proposal) setProposal(data.proposal)
      if (data.recommendation) setRecommendation(data.recommendation)
    } catch {
      setMessages(prev => [...prev, { role: 'model', content: 'Đã xảy ra lỗi. Vui lòng thử lại.' }])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleReset() {
    setMode(null)
    setSessionId(null)
    setMessages([])
    setOptions(null)
    setProgress(0)
    setIsComplete(false)
    setProposal(null)
    setRecommendation(null)
    setInput('')
  }

  const accentColor = mode ? (MODE_META[mode]?.color ?? '#3b82f6') : '#3b82f6'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', maxWidth: 720, margin: '0 auto', background: '#fff', boxShadow: '0 0 40px rgba(0,0,0,0.08)' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', background: accentColor, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 17 }}>Trợ lý Bảo hiểm</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>
            {mode ? MODE_META[mode]?.label : 'Hỗ trợ khai thác & tư vấn bảo hiểm'}
          </div>
        </div>
        {mode && (
          <button onClick={handleReset} style={{ background: 'rgba(255,255,255,0.2)', border: 'none', color: '#fff', padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}>
            Bắt đầu lại
          </button>
        )}
      </div>

      {/* Mode selector or chat */}
      {!mode ? (
        <ModeSelector onSelectMode={handleSelectMode} />
      ) : (
        <>
          <ProgressBar pct={progress} isComplete={isComplete} />

          <ChatWindow
            messages={messages}
            proposal={proposal}
            recommendation={recommendation}
            isLoading={isLoading}
          />

          {!isLoading && !isComplete && (
            <OptionChips options={options} onSelect={handleSend} />
          )}

          {/* Input */}
          <div style={{ padding: '12px 16px', borderTop: '1px solid #e5e7eb', background: '#fff', display: 'flex', gap: 8, flexShrink: 0 }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading || isComplete}
              placeholder={isComplete ? 'Hoàn tất. Nhấn "Bắt đầu lại" để dùng lại.' : 'Nhập thông tin của bạn... (Enter để gửi)'}
              rows={2}
              style={{
                flex: 1, padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: 12,
                resize: 'none', fontSize: 14, outline: 'none', fontFamily: 'inherit',
                background: isComplete ? '#f9fafb' : '#fff',
              }}
            />
            <button
              onClick={() => handleSend()}
              disabled={isLoading || !input.trim() || isComplete}
              style={{
                padding: '10px 20px', background: accentColor, color: '#fff', border: 'none',
                borderRadius: 12, cursor: 'pointer', fontWeight: 600, fontSize: 14,
                opacity: (isLoading || !input.trim() || isComplete) ? 0.5 : 1,
                alignSelf: 'flex-end',
              }}
            >
              Gửi
            </button>
          </div>
        </>
      )}
    </div>
  )
}
