import { useChatStore } from '../../store'
import MessageBubble from './MessageBubble'
import { useScrollToBottom } from '../../hooks/useScrollToBottom'

export default function ChatWindow() {
  const messages = useChatStore((s) => s.messages)
  const isLoading = useChatStore((s) => s.isLoading)
  const scrollRef = useScrollToBottom<HTMLDivElement>([messages, isLoading])

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 gap-3 pt-16">
          <div className="text-5xl">🏢</div>
          <p className="text-lg font-medium text-gray-500">Xin chào! Tôi là trợ lý nội quy Agentic House.</p>
          <p className="text-sm max-w-sm">
            Hỏi tôi về trang phục, nghỉ phép, phúc lợi, làm việc từ xa, hay bất kỳ chính sách nào của công ty.
          </p>
          <div className="grid grid-cols-1 gap-2 mt-2 text-left text-sm">
            {[
              'Quy định trang phục cho nhân viên kỹ thuật là gì?',
              'Nhân viên được nghỉ phép bao nhiêu ngày mỗi năm?',
              'Tóm tắt toàn bộ chính sách phúc lợi của công ty',
              'Quy trình xin làm thêm giờ như thế nào?',
            ].map((q) => (
              <button
                key={q}
                className="px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg text-left border border-blue-200 transition-colors"
                onClick={() => {
                  const input = document.getElementById('chat-input') as HTMLInputElement
                  if (input) { input.value = q; input.dispatchEvent(new Event('input', { bubbles: true })) }
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isLoading && (
        <div className="flex items-center gap-2 text-gray-400 text-sm pl-2">
          <span className="flex gap-1">
            <span className="animate-bounce [animation-delay:0ms]">•</span>
            <span className="animate-bounce [animation-delay:150ms]">•</span>
            <span className="animate-bounce [animation-delay:300ms]">•</span>
          </span>
          Đang tìm kiếm trong đồ thị tri thức...
        </div>
      )}
    </div>
  )
}
