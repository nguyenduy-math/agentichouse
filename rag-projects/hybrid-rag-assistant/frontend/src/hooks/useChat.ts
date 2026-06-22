import { useEffect, useRef } from "react";
import { createSession, sendMessage } from "../api/client";
import { useChatStore, Message } from "../store/chatStore";

let _sessionInit = false;

export function useChat() {
  const { sessionId, setSessionId, addMessage, setLoading, loading } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!_sessionInit) {
      _sessionInit = true;
      createSession().then(setSessionId);
    }
  }, [setSessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  });

  const submit = async (text: string) => {
    if (!sessionId || loading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    addMessage(userMsg);
    setLoading(true);

    try {
      const res = await sendMessage(sessionId, text);
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.reply,
        rewrittenQuery: res.rewritten_query !== text ? res.rewritten_query : undefined,
        domainsUsed: res.domains_used,
        isOutOfScope: res.is_out_of_scope,
        sources: res.sources,
      };
      addMessage(assistantMsg);
    } catch {
      addMessage({
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.",
      });
    } finally {
      setLoading(false);
    }
  };

  return { submit, loading, bottomRef };
}
