export default function ProgressBar({ pct, isComplete }) {
  const color = isComplete ? '#22c55e' : pct > 60 ? '#3b82f6' : '#f59e0b'
  return (
    <div style={{ padding: '8px 16px', background: '#fff', borderBottom: '1px solid #e5e7eb' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12, color: '#6b7280' }}>
        <span>{isComplete ? 'Hồ sơ hoàn tất' : `Đã thu thập thông tin`}</span>
        <span style={{ fontWeight: 600, color }}>{pct}%</span>
      </div>
      <div style={{ height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  )
}
