import { ActivityItem } from '../types'

const AGENT_META: Record<string, { icon: string; color: string }> = {
  OrchestratorAgent: { icon: '🎯', color: '#f59e0b' },
  FAQAgent:          { icon: '📚', color: '#3b82f6' },
  OrderAgent:        { icon: '📦', color: '#10b981' },
  ComplaintAgent:    { icon: '🛡️', color: '#ef4444' },
  System:            { icon: '⚠️', color: '#6b7280' },
}

interface Props {
  activities: ActivityItem[]
  isLoading: boolean
}

export default function ActivitySidebar({ activities, isLoading }: Props) {
  return (
    <aside className="activity-sidebar">
      <div className="sidebar-header">⚡ Hoạt động tác nhân</div>
      <div className="activity-list">
        {!isLoading && activities.length === 0 && (
          <div className="activity-empty">
            Gửi tin nhắn để xem luồng xử lý của các tác nhân AI theo thời gian thực.
          </div>
        )}
        {isLoading && (
          <div className="activity-loading">
            <div className="spinner" />
            <span>Đang xử lý yêu cầu...</span>
          </div>
        )}
        {activities.map((a, i) => {
          const meta = AGENT_META[a.agent] ?? { icon: '🤖', color: '#94a3b8' }
          return (
            <div key={i} className="activity-item">
              <span className="activity-icon">{meta.icon}</span>
              <div className="activity-content">
                <div className="activity-agent" style={{ color: meta.color }}>
                  {a.agent}
                </div>
                <div className="activity-action">{a.action}</div>
                {a.detail && <div className="activity-detail">{a.detail}</div>}
              </div>
              <span className="activity-check">✓</span>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
