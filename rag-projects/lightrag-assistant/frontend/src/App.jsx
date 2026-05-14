import { useEffect, useState } from 'react'
import ChatBox from './components/ChatBox.jsx'
import { getHealth } from './api.js'

const STATUS_LABELS = {
  ok: 'Hệ thống sẵn sàng',
  degraded: 'Hệ thống chưa sẵn sàng',
  unreachable: 'Không kết nối được máy chủ',
}

export default function App() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))
  }, [])

  return (
    <div className="app">
      <header className="app__header">
        <h1>Trợ lý Bảo hiểm Việt Nam</h1>
        <p className="app__subtitle">
          Hỏi đáp dựa trên tài liệu bảo hiểm — LightRAG + Neo4j + Gemini
        </p>
        {health && (
          <span className={`app__status app__status--${health.status}`}>
            {STATUS_LABELS[health.status] || health.status}
          </span>
        )}
      </header>

      <main className="app__main">
        <ChatBox />
      </main>

      <footer className="app__footer">
        Thông tin chỉ mang tính tham khảo, không thay thế tư vấn pháp lý hoặc tài chính chính thức.
      </footer>
    </div>
  )
}
