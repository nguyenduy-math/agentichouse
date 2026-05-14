// A single chat message bubble, styled by role (user vs assistant).
export default function Message({ role, content }) {
  const isUser = role === 'user'
  return (
    <div className={`message ${isUser ? 'message--user' : 'message--assistant'}`}>
      <div className="message__role">{isUser ? 'Bạn' : 'Trợ lý'}</div>
      <div className="message__content">{content}</div>
    </div>
  )
}
