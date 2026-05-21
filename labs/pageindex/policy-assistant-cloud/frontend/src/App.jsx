import { useCallback, useEffect, useState } from 'react'
import ChatBox from './components/ChatBox.jsx'
import { getHealth } from './api.js'

export default function App() {
  const [health, setHealth] = useState(null)
  // Tăng mỗi khi nạp/xoá tài liệu để làm mới health + danh sách tài liệu.
  const [refreshKey, setRefreshKey] = useState(0)

  const onDocsChanged = useCallback(() => setRefreshKey((k) => k + 1), [])

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))
  }, [refreshKey])

  const missingKeys = []
  if (health && health.status !== 'unreachable') {
    if (!health.gemini_key_present) missingKeys.push('GEMINI_API_KEY')
    if (!health.pageindex_key_present) missingKeys.push('PAGEINDEX_API_KEY')
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>Trợ lý Chính sách Doanh nghiệp</h1>
        <p className="app__subtitle">PageIndex Cloud + Gemini · tiếng Việt</p>
        {health && (
          <div className="app__status-row">
            <span
              className={`app__status app__status--${
                health.status === 'unreachable' ? 'unreachable' : 'ok'
              }`}
            >
              {health.status === 'unreachable'
                ? 'Không kết nối được máy chủ'
                : `${health.indexed_count ?? 0} tài liệu đã nạp`}
            </span>
            {missingKeys.map((k) => (
              <span key={k} className="app__status app__status--degraded">
                Thiếu {k}
              </span>
            ))}
          </div>
        )}
      </header>

      <main className="app__main">
        <ChatBox refreshKey={refreshKey} onDocsChanged={onDocsChanged} />
      </main>

      <footer className="app__footer">
        Thông tin chỉ mang tính tham khảo. Vui lòng liên hệ phòng ban phụ trách để được xác nhận chính thức.
      </footer>
    </div>
  )
}
