// Một bong bóng tin nhắn với nhãn lĩnh vực và trích dẫn trang.

const DOMAIN_COLORS = {
  HR_POLICY:   { bg: '#dbeafe', color: '#1e40af', label: 'Nội quy LĐ' },
  BENEFITS:    { bg: '#dcfce7', color: '#15803d', label: 'Phúc lợi' },
  CONDUCT:     { bg: '#fef9c3', color: '#854d0e', label: 'Quy tắc ứng xử' },
  PROCEDURES:  { bg: '#f3e8ff', color: '#6b21a8', label: 'Quy trình' },
  HANDBOOK:    { bg: '#ffedd5', color: '#9a3412', label: 'Sổ tay NV' },
  MEDICAL:     { bg: '#fce7f3', color: '#9d174d', label: 'Y tế' },
  IT_SECURITY: { bg: '#e0e7ff', color: '#3730a3', label: 'CNTT & BM' },
  COMPLIANCE:  { bg: '#f1f5f9', color: '#334155', label: 'Tuân thủ & PL' },
  FINANCE:     { bg: '#fefce8', color: '#713f12', label: 'Tài chính' },
  TRAINING:    { bg: '#ecfdf5', color: '#065f46', label: 'Đào tạo' },
}

export default function Message({ role, content, domains, citations }) {
  const isUser = role === 'user'
  return (
    <div className={`message ${isUser ? 'message--user' : 'message--assistant'}`}>
      <div className="message__meta">
        <span className="message__role">{isUser ? 'Bạn' : 'Trợ lý'}</span>
        {!isUser && domains && domains.length > 0 && (
          <span className="message__domains">
            {domains.map((d) => {
              const style = DOMAIN_COLORS[d] || { bg: '#f3f4f6', color: '#374151', label: d }
              return (
                <span
                  key={d}
                  className="domain-badge"
                  style={{ background: style.bg, color: style.color }}
                >
                  {style.label}
                </span>
              )
            })}
          </span>
        )}
      </div>
      <div className="message__content">{content}</div>
      {!isUser && citations && citations.length > 0 && (
        <div className="message__citations">
          {citations.map((c, i) => (
            <span key={i} className="citation-badge" title={c.section || ''}>
              {c.document} · tr.{c.page}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
