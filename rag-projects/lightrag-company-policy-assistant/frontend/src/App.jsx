import { useEffect, useState } from 'react'
import ChatBox from './components/ChatBox.jsx'
import { getHealth } from './api.js'

const AGENT_LABELS = {
  HR_POLICY:   'Nội quy LĐ',
  BENEFITS:    'Phúc lợi',
  CONDUCT:     'Quy tắc ứng xử',
  PROCEDURES:  'Quy trình',
  HANDBOOK:    'Sổ tay NV',
  MEDICAL:     'Y tế',
  IT_SECURITY: 'CNTT & Bảo mật',
  COMPLIANCE:  'Tuân thủ & PL',
  FINANCE:     'Tài chính',
  TRAINING:    'Đào tạo',
}

export default function App() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable', agents: {} }))
  }, [])

  const agentEntries = health?.agents ? Object.entries(health.agents) : []
  const readyCount = agentEntries.filter(([, h]) => h.ready).length

  return (
    <div className="app">
      <header className="app__header">
        <h1>Trợ lý Chính sách Doanh nghiệp</h1>
        <p className="app__subtitle">
          Đa tác nhân RAG &mdash; LightRAG + PageIndex + Gemini
        </p>
        {health && (
          <div className="app__status-row">
            <span className={`app__status app__status--${health.status}`}>
              {health.status === 'ok' ? 'Tất cả tác nhân sẵn sàng' :
               health.status === 'unreachable' ? 'Không kết nối được máy chủ' :
               `${readyCount}/${agentEntries.length} tác nhân sẵn sàng`}
            </span>
            <div className="app__agents">
              {agentEntries.map(([domain, h]) => (
                <span
                  key={domain}
                  className={`agent-chip agent-chip--${h.ready ? 'ready' : 'idle'}`}
                  title={`${h.engine_type} · ${h.indexed_docs} tài liệu`}
                >
                  {AGENT_LABELS[domain] || domain}
                </span>
              ))}
            </div>
          </div>
        )}
      </header>

      <main className="app__main">
        <ChatBox />
      </main>

      <footer className="app__footer">
        Thông tin chỉ mang tính tham khảo. Vui lòng liên hệ phòng ban phụ trách để được xác nhận chính thức.
      </footer>
    </div>
  )
}
