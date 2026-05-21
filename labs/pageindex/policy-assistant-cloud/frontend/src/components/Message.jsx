// Một bong bóng tin nhắn, kèm tài liệu đã tham vấn và trích dẫn trang.

export default function Message({ role, content, citations, documents }) {
  const isUser = role === 'user'
  return (
    <div className={`message ${isUser ? 'message--user' : 'message--assistant'}`}>
      <div className="message__meta">
        <span className="message__role">{isUser ? 'Bạn' : 'Trợ lý'}</span>
        {!isUser && documents && documents.length > 0 && (
          <span className="message__domains">
            {documents.map((d) => (
              <span key={d} className="doc-chip" title={d}>
                {d}
              </span>
            ))}
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
