export default function ProposalCard({ proposal }) {
  if (!proposal) return null

  const raw = proposal._raw || {}
  const displayEntries = Object.entries(proposal).filter(([k]) => k !== '_raw' && proposal[k] != null)

  function downloadJSON() {
    const blob = new Blob([JSON.stringify(raw, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'ho-so-bao-hiem.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{
      margin: '16px 0', padding: 16, background: '#f0fdf4', border: '1px solid #86efac',
      borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
    }}>
      <div style={{ fontWeight: 700, fontSize: 15, color: '#15803d', marginBottom: 12 }}>
        Hồ sơ yêu cầu bồi thường
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <tbody>
          {displayEntries.map(([label, value]) => (
            <tr key={label} style={{ borderBottom: '1px solid #dcfce7' }}>
              <td style={{ padding: '6px 8px', color: '#6b7280', width: '45%', verticalAlign: 'top' }}>{label}</td>
              <td style={{ padding: '6px 8px', color: '#1f2937', fontWeight: 500 }}>
                {typeof value === 'number' ? value.toLocaleString('vi-VN') + ' VNĐ' : String(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        onClick={downloadJSON}
        style={{
          marginTop: 12, padding: '8px 16px', background: '#16a34a', color: '#fff',
          border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600,
        }}
      >
        Tải xuống JSON
      </button>
    </div>
  )
}
