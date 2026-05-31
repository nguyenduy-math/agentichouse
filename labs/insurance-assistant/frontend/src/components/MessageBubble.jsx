export default function MessageBubble({ role, content }) {
  const isUser = role === 'user'
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', marginBottom: 12 }}>
      {!isUser && (
        <div style={{
          width: 32, height: 32, borderRadius: '50%', background: '#3b82f6',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, color: '#fff', flexShrink: 0, marginRight: 8, alignSelf: 'flex-end',
        }}>B</div>
      )}
      <div style={{
        maxWidth: '70%', padding: '10px 14px', borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
        background: isUser ? '#3b82f6' : '#fff',
        color: isUser ? '#fff' : '#1f2937',
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
        fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap',
      }}>
        {content}
      </div>
    </div>
  )
}
