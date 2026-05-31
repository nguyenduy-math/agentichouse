import { useState } from 'react'
import ClaimForm from '../components/ClaimForm'
import FloatingChat from '../components/FloatingChat'

export default function ClaimPage() {
  const [chatFields, setChatFields] = useState(null)
  const [formProgress, setFormProgress] = useState(0)

  return (
    <div style={{ minHeight: '100vh', background: '#f9fafb' }}>
      {/* Header */}
      <div style={{ background: '#3b82f6', color: '#fff', padding: '16px 24px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <a href="/" style={{ color: 'rgba(255,255,255,0.8)', textDecoration: 'none', fontSize: 13 }}>← Trang chủ</a>
        <div>
          <div style={{ fontWeight: 700, fontSize: 17 }}>Khai thác quyền lợi bảo hiểm</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>Điền form hoặc dùng chat để tự động điền thông tin</div>
        </div>
      </div>

      {/* Body */}
      <div style={{ maxWidth: 680, margin: '0 auto', padding: '32px 24px 120px' }}>
        <div style={{ background: '#fff', borderRadius: 12, padding: 28, boxShadow: '0 1px 8px rgba(0,0,0,0.07)' }}>
          <div style={{ marginBottom: 20 }}>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#111827' }}>Thông tin khai thác</h2>
            <p style={{ margin: '6px 0 0', fontSize: 13, color: '#6b7280' }}>
              Bạn có thể điền trực tiếp hoặc nhấn vào nút 💬 ở góc phải để chat với trợ lý — trợ lý sẽ tự động điền thông tin vào form.
            </p>
          </div>

          <ClaimForm
            externalFields={chatFields}
            onProgressChange={setFormProgress}
          />
        </div>
      </div>

      {/* Floating chat widget */}
      <FloatingChat onFieldsCollected={setChatFields} />
    </div>
  )
}
