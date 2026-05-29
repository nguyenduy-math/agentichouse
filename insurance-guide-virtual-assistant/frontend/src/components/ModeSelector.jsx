export default function ModeSelector({ onSelectMode }) {
  const cards = [
    {
      mode: 'claim_filing',
      title: 'Khai thác bảo hiểm',
      subtitle: 'Nộp hồ sơ yêu cầu bồi thường',
      description: 'Hướng dẫn bạn điền đầy đủ thông tin để khai thác quyền lợi BHYT hoặc bảo hiểm thương mại.',
      icon: '📋',
      accent: '#3b82f6',
      bg: '#eff6ff',
      border: '#93c5fd',
    },
    {
      mode: 'recommendation',
      title: 'Tư vấn gói bảo hiểm',
      subtitle: 'Tìm gói phù hợp với bạn',
      description: 'Dựa trên hồ sơ sức khỏe và ngân sách, tôi sẽ đề xuất 2-3 gói bảo hiểm phù hợp nhất.',
      icon: '🔍',
      accent: '#16a34a',
      bg: '#f0fdf4',
      border: '#86efac',
    },
  ]

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32, gap: 16 }}>
      <div style={{ textAlign: 'center', marginBottom: 8 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: '#1f2937' }}>Tôi có thể giúp gì cho bạn?</div>
        <div style={{ fontSize: 14, color: '#6b7280', marginTop: 4 }}>Chọn loại hỗ trợ bạn cần</div>
      </div>

      {cards.map(card => (
        <button
          key={card.mode}
          onClick={() => onSelectMode(card.mode)}
          style={{
            width: '100%', maxWidth: 480, padding: 20,
            background: card.bg, border: `1.5px solid ${card.border}`,
            borderRadius: 16, cursor: 'pointer', textAlign: 'left',
            display: 'flex', alignItems: 'flex-start', gap: 16,
            transition: 'box-shadow 0.15s, transform 0.1s',
            boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.boxShadow = `0 4px 16px rgba(0,0,0,0.10)`
            e.currentTarget.style.transform = 'translateY(-2px)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.06)'
            e.currentTarget.style.transform = 'none'
          }}
        >
          <div style={{ fontSize: 32, lineHeight: 1 }}>{card.icon}</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: card.accent }}>{card.title}</div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>{card.subtitle}</div>
            <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.5 }}>{card.description}</div>
          </div>
        </button>
      ))}
    </div>
  )
}
