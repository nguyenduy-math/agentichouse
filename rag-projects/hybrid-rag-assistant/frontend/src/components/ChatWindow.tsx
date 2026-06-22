import { useState, KeyboardEvent } from "react";
import { useChatStore } from "../store/chatStore";
import { useChat } from "../hooks/useChat";
import SourcesPanel from "./SourcesPanel";
import UploadPanel from "./UploadPanel";

const DOMAIN_COLORS: Record<string, string> = {
  hr: "bg-green-100 text-green-700",
  legal: "bg-purple-100 text-purple-700",
  finance: "bg-yellow-100 text-yellow-700",
  general: "bg-gray-100 text-gray-600",
};

export default function ChatWindow() {
  const { messages, loading } = useChatStore();
  const { submit, bottomRef } = useChat();
  const [input, setInput] = useState("");

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    submit(text);
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto px-4">
      {/* Header */}
      <div className="py-4 border-b border-gray-200">
        <h1 className="text-xl font-semibold text-gray-800">Hybrid RAG Assistant</h1>
        <p className="text-xs text-gray-400">
          BM25 + Vector Search · RRF · Cross-encoder Reranking · Multi-domain Agents
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-16">
            <p className="text-lg">Xin chào!</p>
            <p className="text-sm mt-1">Hãy đặt câu hỏi về tài liệu của bạn.</p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] space-y-2 ${
                msg.role === "user" ? "items-end" : "items-start"
              } flex flex-col`}
            >
              {/* Rewritten query */}
              {msg.rewrittenQuery && (
                <div className="text-xs text-gray-400 px-1">
                  Câu hỏi được viết lại: <em>{msg.rewrittenQuery}</em>
                </div>
              )}

              {/* Domain badges */}
              {msg.domainsUsed && msg.domainsUsed.length > 0 && (
                <div className="flex gap-1 flex-wrap">
                  {msg.domainsUsed.map((d) => (
                    <span
                      key={d}
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        DOMAIN_COLORS[d] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {d}
                    </span>
                  ))}
                </div>
              )}

              {/* Bubble */}
              <div
                className={`rounded-2xl px-4 py-3 whitespace-pre-wrap leading-relaxed ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white"
                    : msg.isOutOfScope
                    ? "bg-amber-50 border border-amber-200 text-amber-800"
                    : "bg-white border border-gray-200 text-gray-800"
                }`}
              >
                {msg.content}
              </div>

              {/* Sources */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="w-full">
                  <SourcesPanel sources={msg.sources} rewrittenQuery={msg.rewrittenQuery} />
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 text-gray-400 text-sm">
              Đang phân tích và tổng hợp từ các lĩnh vực...
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Upload + Input */}
      <div className="py-4 border-t border-gray-200 space-y-3">
        <UploadPanel />
        <div className="flex gap-2 items-end">
          <textarea
            className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-32"
            rows={1}
            placeholder="Nhập câu hỏi của bạn... (Enter để gửi)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            disabled={loading}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="bg-blue-600 text-white rounded-xl px-5 py-3 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Gửi
          </button>
        </div>
      </div>
    </div>
  );
}
