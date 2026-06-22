import { create } from "zustand";
import { ChunkSource } from "../api/client";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  rewrittenQuery?: string;
  domainsUsed?: string[];
  isOutOfScope?: boolean;
  sources?: ChunkSource[];
}

interface ChatStore {
  sessionId: string | null;
  messages: Message[];
  loading: boolean;
  setSessionId: (id: string) => void;
  addMessage: (msg: Message) => void;
  setLoading: (v: boolean) => void;
  clear: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  sessionId: null,
  messages: [],
  loading: false,
  setSessionId: (id) => set({ sessionId: id }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setLoading: (v) => set({ loading: v }),
  clear: () => set({ messages: [], sessionId: null }),
}));
