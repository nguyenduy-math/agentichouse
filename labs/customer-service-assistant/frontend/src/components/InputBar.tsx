import { useState, KeyboardEvent } from 'react'

const QUICK_PROMPTS = [
  'Đơn hàng ORD-2024-001 đang ở đâu?',
  'Chính sách đổi trả hàng?',
  'Sản phẩm tôi nhận bị lỗi',
  'Phí vận chuyển tính như thế nào?',
]

interface Props {
  onSend: (message: string) => void
  disabled: boolean
}

export default function InputBar({ onSend, disabled }: Props) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="input-bar">
      <div className="quick-prompts">
        {QUICK_PROMPTS.map(p => (
          <button
            key={p}
            className="quick-prompt-btn"
            onClick={() => { if (!disabled) onSend(p) }}
            disabled={disabled}
          >
            {p}
          </button>
        ))}
      </div>
      <div className="input-row">
        <textarea
          className="input-textarea"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Nhập tin nhắn... (Enter để gửi, Shift+Enter xuống dòng)"
          disabled={disabled}
          rows={2}
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          title="Gửi"
        >
          ▶
        </button>
      </div>
    </div>
  )
}
