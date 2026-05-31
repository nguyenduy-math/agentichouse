export default function RecommendationCard({ recommendation }) {
  if (!recommendation || !recommendation.recommendations) return null

  const packages = recommendation.recommendations

  function downloadJSON() {
    const blob = new Blob([JSON.stringify(recommendation, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'de-xuat-bao-hiem.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const rankColors = ['#16a34a', '#2563eb', '#9333ea']
  const rankLabels = ['Khuyến nghị hàng đầu', 'Lựa chọn thứ hai', 'Lựa chọn thứ ba']

  return (
    <div style={{ margin: '16px 0' }}>
      <div style={{ fontWeight: 700, fontSize: 14, color: '#374151', marginBottom: 10 }}>
        Các gói bảo hiểm được đề xuất
      </div>

      {packages.map((pkg, i) => (
        <div
          key={i}
          style={{
            marginBottom: 12, padding: 16,
            background: '#fff', border: `1.5px solid ${rankColors[i] ?? '#e5e7eb'}`,
            borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{
              background: rankColors[i] ?? '#6b7280', color: '#fff',
              borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600,
            }}>
              {rankLabels[i] ?? `Lựa chọn ${pkg.rank}`}
            </span>
            <span style={{ fontWeight: 700, fontSize: 15, color: '#1f2937' }}>{pkg.package_type}</span>
          </div>

          {/* Insurers + premium */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 12, color: '#6b7280' }}>
              <span style={{ fontWeight: 600 }}>Công ty:</span> {pkg.insurer_examples.join(', ')}
            </div>
            <div style={{ fontSize: 12, color: '#16a34a', fontWeight: 600 }}>
              {pkg.estimated_premium_range}
            </div>
          </div>

          {/* Coverage highlights */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Quyền lợi nổi bật:</div>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {pkg.coverage_highlights.map((h, j) => (
                <li key={j} style={{ fontSize: 12, color: '#374151', marginBottom: 2 }}>{h}</li>
              ))}
            </ul>
          </div>

          {/* Why suitable */}
          <div style={{ marginBottom: 8, padding: '8px 10px', background: '#f0fdf4', borderRadius: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#15803d', marginBottom: 2 }}>Tại sao phù hợp:</div>
            <div style={{ fontSize: 12, color: '#374151' }}>{pkg.why_suitable}</div>
          </div>

          {/* Considerations */}
          {pkg.key_considerations.length > 0 && (
            <div style={{ padding: '6px 10px', background: '#fefce8', borderRadius: 8, border: '1px solid #fde047' }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#854d0e', marginBottom: 2 }}>Lưu ý:</div>
              {pkg.key_considerations.map((c, j) => (
                <div key={j} style={{ fontSize: 11, color: '#713f12' }}>• {c}</div>
              ))}
            </div>
          )}
        </div>
      ))}

      <button
        onClick={downloadJSON}
        style={{
          marginTop: 4, padding: '8px 16px', background: '#2563eb', color: '#fff',
          border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600,
        }}
      >
        Tải xuống JSON
      </button>
    </div>
  )
}
